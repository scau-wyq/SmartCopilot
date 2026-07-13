from datetime import date

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import RechargeOrder, RechargePackage, UserModelPreference, UserTokenRecord


class BillingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_token_balance(self, user_id: int, token_type: str) -> int:
        increase = await self._sum_amount(user_id, token_type, "INCREASE")
        consume = await self._sum_amount(user_id, token_type, "CONSUME")
        return increase - consume

    async def list_token_records(self, user_id: int, page: int, size: int) -> tuple[list[UserTokenRecord], int]:
        statement = (
            select(UserTokenRecord)
            .where(UserTokenRecord.user_id == user_id)
            .order_by(UserTokenRecord.created_at.desc(), UserTokenRecord.id.desc())
            .offset(max(page, 0) * size)
            .limit(size)
        )
        count_statement = select(func.count()).select_from(UserTokenRecord).where(UserTokenRecord.user_id == user_id)
        records = await self.session.execute(statement)
        total = await self.session.execute(count_statement)
        return list(records.scalars().all()), int(total.scalar_one())

    async def add_token_record(
        self,
        *,
        user_id: int,
        token_type: str,
        change_type: str,
        amount: int,
        balance_before: int,
        reason: str,
        remark: str | None = None,
        request_count: int = 1,
    ) -> UserTokenRecord:
        normalized_amount = max(int(amount), 0)
        balance_after = balance_before + normalized_amount if change_type == "INCREASE" else balance_before - normalized_amount
        record = UserTokenRecord(
            user_id=user_id,
            record_date=date.today(),
            token_type=token_type,
            change_type=change_type,
            amount=normalized_amount,
            balance_before=balance_before,
            balance_after=balance_after,
            reason=reason,
            remark=remark,
            request_count=request_count,
        )
        self.session.add(record)
        await self.session.flush()
        return record

    async def list_recharge_packages(self, include_disabled: bool = False) -> list[RechargePackage]:
        conditions = [RechargePackage.deleted.is_(False)]
        if not include_disabled:
            conditions.append(RechargePackage.enabled.is_(True))
        statement = select(RechargePackage).where(and_(*conditions)).order_by(
            RechargePackage.sort_order.asc(),
            RechargePackage.id.asc(),
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def find_recharge_package(self, package_id: int) -> RechargePackage | None:
        result = await self.session.execute(
            select(RechargePackage).where(
                RechargePackage.id == package_id,
                RechargePackage.deleted.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def save_recharge_package(self, package: RechargePackage) -> RechargePackage:
        self.session.add(package)
        await self.session.flush()
        return package

    async def find_order_by_trade_no(self, trade_no: str) -> RechargeOrder | None:
        result = await self.session.execute(select(RechargeOrder).where(RechargeOrder.trade_no == trade_no))
        return result.scalar_one_or_none()

    async def list_orders(self, user_id: int, status: str | None = None) -> list[RechargeOrder]:
        conditions = [RechargeOrder.user_id == user_id]
        if status:
            conditions.append(RechargeOrder.status == status)
        result = await self.session.execute(
            select(RechargeOrder).where(and_(*conditions)).order_by(RechargeOrder.created_at.desc(), RechargeOrder.id.desc())
        )
        return list(result.scalars().all())

    async def save_order(self, order: RechargeOrder) -> RechargeOrder:
        self.session.add(order)
        await self.session.flush()
        return order

    async def get_model_preference(self, user_id: int) -> UserModelPreference | None:
        result = await self.session.execute(select(UserModelPreference).where(UserModelPreference.user_id == user_id))
        return result.scalar_one_or_none()

    async def save_model_preference(self, preference: UserModelPreference) -> UserModelPreference:
        self.session.add(preference)
        await self.session.flush()
        return preference

    async def _sum_amount(self, user_id: int, token_type: str, change_type: str) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.sum(UserTokenRecord.amount), 0)).where(
                UserTokenRecord.user_id == user_id,
                UserTokenRecord.token_type == token_type,
                UserTokenRecord.change_type == change_type,
            )
        )
        return int(result.scalar_one() or 0)
