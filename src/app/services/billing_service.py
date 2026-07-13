from datetime import datetime, timedelta
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.responses import ApiError
from app.models.billing import RechargeOrder, RechargePackage
from app.models.user import User
from app.repositories.billing_repository import BillingRepository


class RechargePackagePayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    package_name: str = Field(alias="packageName")
    package_price: int = Field(alias="packagePrice")
    package_desc: str | None = Field(default=None, alias="packageDesc")
    package_benefit: str | None = Field(default=None, alias="packageBenefit")
    llm_token: int = Field(default=0, alias="llmToken")
    embedding_token: int = Field(default=0, alias="embeddingToken")
    enabled: bool = True
    sort_order: int = Field(default=0, alias="sortOrder")


class BillingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repository = BillingRepository(session)

    async def balance_snapshot(self, user_id: int) -> dict[str, int]:
        return {
            "llmToken": await self.repository.get_token_balance(user_id, "LLM"),
            "embeddingToken": await self.repository.get_token_balance(user_id, "EMBEDDING"),
        }

    async def usage_snapshot(self, user_id: int) -> dict[str, object]:
        balances = await self.balance_snapshot(user_id)
        return {
            "day": datetime.now().date().isoformat(),
            "chatRequestCount": 0,
            "llm": self._quota(balances["llmToken"]),
            "embedding": self._quota(balances["embeddingToken"]),
        }

    async def list_token_records(self, user_id: int, page: int, size: int) -> dict[str, object]:
        records, total = await self.repository.list_token_records(user_id, page, size)
        data = [self._token_record_to_dict(record) for record in records]
        return {
            "content": data,
            "records": data,
            "data": data,
            "totalElements": total,
            "total": total,
            "totalPages": (total + size - 1) // size if size else 0,
            "page": page,
            "size": size,
        }

    async def add_tokens(
        self,
        *,
        user_id: int,
        llm_token: int,
        embedding_token: int,
        reason: str,
        remark: str | None = None,
    ) -> None:
        if llm_token < 0 or embedding_token < 0:
            raise ApiError(400, "Token amount cannot be negative")
        if llm_token == 0 and embedding_token == 0:
            raise ApiError(400, "At least one token amount is required")
        if llm_token:
            await self._add_record(user_id, "LLM", "INCREASE", llm_token, reason, remark)
        if embedding_token:
            await self._add_record(user_id, "EMBEDDING", "INCREASE", embedding_token, reason, remark)
        await self.session.commit()

    async def consume_tokens(
        self,
        *,
        user_id: int,
        token_type: str,
        amount: int,
        reason: str,
        remark: str | None = None,
    ) -> None:
        normalized = max(int(amount), 0)
        if normalized <= 0:
            return
        balance = await self.repository.get_token_balance(user_id, token_type)
        if balance < normalized:
            raise ApiError(402, f"{token_type} Token balance is insufficient")
        await self.repository.add_token_record(
            user_id=user_id,
            token_type=token_type,
            change_type="CONSUME",
            amount=normalized,
            balance_before=balance,
            reason=reason,
            remark=remark,
        )
        await self.session.commit()

    async def ensure_enough(self, user_id: int, token_type: str, amount: int) -> None:
        if amount <= 0:
            return
        balance = await self.repository.get_token_balance(user_id, token_type)
        if balance < amount:
            raise ApiError(402, f"{token_type} Token balance is insufficient")

    async def list_packages(self, include_disabled: bool = False) -> list[dict[str, object]]:
        return [self._package_to_dict(item) for item in await self.repository.list_recharge_packages(include_disabled)]

    async def create_package(self, payload: RechargePackagePayload) -> dict[str, object]:
        package = RechargePackage(**self._package_payload(payload))
        await self.repository.save_recharge_package(package)
        await self.session.commit()
        return self._package_to_dict(package)

    async def update_package(self, package_id: int, payload: RechargePackagePayload) -> dict[str, object]:
        package = await self.repository.find_recharge_package(package_id)
        if package is None:
            raise ApiError(404, "Recharge package not found")
        for key, value in self._package_payload(payload).items():
            setattr(package, key, value)
        await self.session.commit()
        return self._package_to_dict(package)

    async def delete_package(self, package_id: int) -> None:
        package = await self.repository.find_recharge_package(package_id)
        if package is None:
            raise ApiError(404, "Recharge package not found")
        package.deleted = True
        await self.session.commit()

    async def create_order(self, user: User, package_id: int | None, custom_amount: int | None) -> dict[str, object]:
        package = None
        if package_id is not None:
            package = await self.repository.find_recharge_package(package_id)
            if package is None or not package.enabled:
                raise ApiError(404, "Recharge package not found")
            amount = package.package_price
            llm_token = package.llm_token
            embedding_token = package.embedding_token
            description = package.package_name
        else:
            amount = int(custom_amount or 0)
            if amount <= 0:
                raise ApiError(400, "Recharge amount must be greater than 0")
            llm_token = amount * 1000
            embedding_token = amount * 500
            description = "Custom recharge"

        trade_no = f"MOCK{datetime.now():%Y%m%d%H%M%S}{uuid4().hex[:10].upper()}"
        order = RechargeOrder(
            trade_no=trade_no,
            user_id=int(user.id),
            package_id=package.id if package else None,
            amount=amount,
            llm_token=llm_token,
            embedding_token=embedding_token,
            description=description,
            status="NOT_PAY",
        )
        await self.repository.save_order(order)
        await self.session.commit()
        return {
            "outTradeNo": trade_no,
            "appId": "mock-pay",
            "prePayId": trade_no,
            "expireTime": int((datetime.now() + timedelta(minutes=30)).timestamp()),
            "codeUrl": f"mock://pay/{trade_no}",
        }

    async def mock_pay(self, user: User, trade_no: str) -> dict[str, object]:
        order = await self.repository.find_order_by_trade_no(trade_no)
        if order is None or order.user_id != int(user.id):
            raise ApiError(404, "Recharge order not found")
        if order.status == "SUCCEED":
            return self._order_to_dict(order)
        if order.status not in {"NOT_PAY", "PAYING"}:
            raise ApiError(400, "Recharge order cannot be paid")
        order.status = "SUCCEED"
        order.pay_time = datetime.now()
        order.wx_transaction_id = f"MOCK-{trade_no}"
        if order.llm_token:
            await self._add_record(user.id, "LLM", "INCREASE", order.llm_token, "购买套餐充值", trade_no)
        if order.embedding_token:
            await self._add_record(user.id, "EMBEDDING", "INCREASE", order.embedding_token, "购买套餐充值", trade_no)
        await self.session.commit()
        await self.session.refresh(order)
        return self._order_to_dict(order)

    async def list_orders(self, user: User, status: str | None) -> list[dict[str, object]]:
        return [self._order_to_dict(item) for item in await self.repository.list_orders(int(user.id), status)]

    async def get_order(self, user: User, trade_no: str) -> dict[str, object]:
        order = await self.repository.find_order_by_trade_no(trade_no)
        if order is None or order.user_id != int(user.id):
            raise ApiError(404, "Recharge order not found")
        return self._order_to_dict(order)

    async def _add_record(
        self,
        user_id: int,
        token_type: str,
        change_type: str,
        amount: int,
        reason: str,
        remark: str | None,
    ) -> None:
        balance = await self.repository.get_token_balance(user_id, token_type)
        await self.repository.add_token_record(
            user_id=user_id,
            token_type=token_type,
            change_type=change_type,
            amount=amount,
            balance_before=balance,
            reason=reason,
            remark=remark,
        )

    @staticmethod
    def _quota(balance: int) -> dict[str, object]:
        return {
            "enabled": True,
            "usedTokens": 0,
            "limitTokens": balance,
            "remainingTokens": balance,
            "requestCount": 0,
        }

    @staticmethod
    def _package_payload(payload: RechargePackagePayload) -> dict[str, object]:
        data = payload.model_dump(by_alias=False)
        return {key: value for key, value in data.items() if key != "model_config"}

    @staticmethod
    def _package_to_dict(package: RechargePackage) -> dict[str, object]:
        return {
            "id": package.id,
            "packageName": package.package_name,
            "packagePrice": package.package_price,
            "packageDesc": package.package_desc or "",
            "packageBenefit": package.package_benefit or "",
            "llmToken": package.llm_token,
            "embeddingToken": package.embedding_token,
            "enabled": package.enabled,
            "sortOrder": package.sort_order,
            "createdAt": package.created_at.isoformat() if package.created_at else None,
            "updatedAt": package.updated_at.isoformat() if package.updated_at else None,
        }

    @staticmethod
    def _order_to_dict(order: RechargeOrder) -> dict[str, object]:
        return {
            "id": order.id,
            "tradeNo": order.trade_no,
            "outTradeNo": order.trade_no,
            "userId": str(order.user_id),
            "packageId": order.package_id,
            "amount": order.amount,
            "llmToken": order.llm_token,
            "embeddingToken": order.embedding_token,
            "wxTransactionId": order.wx_transaction_id or "",
            "status": order.status,
            "description": order.description or "",
            "payTime": order.pay_time.isoformat() if order.pay_time else None,
            "createdAt": order.created_at.isoformat() if order.created_at else None,
            "updatedAt": order.updated_at.isoformat() if order.updated_at else None,
        }

    @staticmethod
    def _token_record_to_dict(record) -> dict[str, object]:
        return {
            "id": record.id,
            "recordDate": record.record_date.isoformat(),
            "tokenType": record.token_type,
            "changeType": record.change_type,
            "amount": record.amount,
            "balanceBefore": record.balance_before,
            "balanceAfter": record.balance_after,
            "reason": record.reason or "",
            "remark": record.remark,
            "requestCount": record.request_count,
            "createdAt": record.created_at.isoformat() if record.created_at else None,
        }
