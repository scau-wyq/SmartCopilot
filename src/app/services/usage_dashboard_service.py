from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.billing import UserTokenRecord
from app.models.user import User


class UsageDashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def overview(self, days: int) -> dict[str, Any]:
        normalized_days = min(max(int(days or 7), 1), 30)
        today = date.today()
        start_day = today - timedelta(days=normalized_days - 1)

        trends = self._empty_trends(start_day, normalized_days)
        await self._fill_trends(trends, start_day, today)

        user_totals = await self._load_user_totals()
        window_usage = await self._load_window_usage(start_day, today)
        users = await self._load_users()

        llm_rankings = self._rankings(users, user_totals, window_usage, "LLM")
        embedding_rankings = self._rankings(users, user_totals, window_usage, "EMBEDDING")

        return {
            "days": normalized_days,
            "today": trends[-1],
            "trends": trends,
            "llmRankings": llm_rankings,
            "embeddingRankings": embedding_rankings,
            "alerts": self._alerts([*llm_rankings, *embedding_rankings]),
        }

    async def _fill_trends(self, trends: list[dict[str, Any]], start_day: date, end_day: date) -> None:
        trend_map = {item["day"]: item for item in trends}
        result = await self.session.execute(
            select(
                UserTokenRecord.record_date,
                UserTokenRecord.token_type,
                func.coalesce(func.sum(UserTokenRecord.amount), 0),
                func.coalesce(func.sum(UserTokenRecord.request_count), 0),
            )
            .where(
                UserTokenRecord.change_type == "CONSUME",
                UserTokenRecord.record_date >= start_day,
                UserTokenRecord.record_date <= end_day,
            )
            .group_by(UserTokenRecord.record_date, UserTokenRecord.token_type)
        )
        for record_date, token_type, amount, request_count in result.all():
            item = trend_map.get(record_date.isoformat())
            if item is None:
                continue
            if token_type == "LLM":
                item["llmUsedTokens"] = int(amount or 0)
                item["llmRequestCount"] = int(request_count or 0)
                item["chatRequestCount"] = int(request_count or 0)
            elif token_type == "EMBEDDING":
                item["embeddingUsedTokens"] = int(amount or 0)
                item["embeddingRequestCount"] = int(request_count or 0)

    async def _load_user_totals(self) -> dict[int, dict[str, dict[str, int]]]:
        totals: dict[int, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: {"increase": 0, "consume": 0}))
        result = await self.session.execute(
            select(
                UserTokenRecord.user_id,
                UserTokenRecord.token_type,
                UserTokenRecord.change_type,
                func.coalesce(func.sum(UserTokenRecord.amount), 0),
            ).group_by(UserTokenRecord.user_id, UserTokenRecord.token_type, UserTokenRecord.change_type)
        )
        for user_id, token_type, change_type, amount in result.all():
            key = "increase" if change_type == "INCREASE" else "consume"
            totals[int(user_id)][str(token_type)][key] = int(amount or 0)
        return totals

    async def _load_window_usage(self, start_day: date, end_day: date) -> dict[int, dict[str, dict[str, int]]]:
        usage: dict[int, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: {"amount": 0, "requests": 0}))
        result = await self.session.execute(
            select(
                UserTokenRecord.user_id,
                UserTokenRecord.token_type,
                func.coalesce(func.sum(UserTokenRecord.amount), 0),
                func.coalesce(func.sum(UserTokenRecord.request_count), 0),
            )
            .where(
                UserTokenRecord.change_type == "CONSUME",
                UserTokenRecord.record_date >= start_day,
                UserTokenRecord.record_date <= end_day,
            )
            .group_by(UserTokenRecord.user_id, UserTokenRecord.token_type)
        )
        for user_id, token_type, amount, request_count in result.all():
            usage[int(user_id)][str(token_type)] = {
                "amount": int(amount or 0),
                "requests": int(request_count or 0),
            }
        return usage

    async def _load_users(self) -> dict[int, User]:
        result = await self.session.execute(select(User))
        return {int(user.id): user for user in result.scalars().all()}

    @staticmethod
    def _empty_trends(start_day: date, days: int) -> list[dict[str, Any]]:
        return [
            {
                "day": (start_day + timedelta(days=offset)).isoformat(),
                "chatRequestCount": 0,
                "llmUsedTokens": 0,
                "llmRequestCount": 0,
                "embeddingUsedTokens": 0,
                "embeddingRequestCount": 0,
            }
            for offset in range(days)
        ]

    @staticmethod
    def _rankings(
        users: dict[int, User],
        user_totals: dict[int, dict[str, dict[str, int]]],
        window_usage: dict[int, dict[str, dict[str, int]]],
        token_type: str,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for user_id, usage_by_type in window_usage.items():
            usage = usage_by_type.get(token_type) or {"amount": 0, "requests": 0}
            if usage["amount"] <= 0 and usage["requests"] <= 0:
                continue
            totals = user_totals.get(user_id, {}).get(token_type, {"increase": 0, "consume": 0})
            user = users.get(user_id)
            rows.append(
                {
                    "userId": str(user_id),
                    "username": user.username if user else f"User {user_id}",
                    "scope": "llm" if token_type == "LLM" else "embedding",
                    "usedTokens": usage["amount"],
                    "limitTokens": totals["increase"],
                    "remainingTokens": totals["increase"] - totals["consume"],
                    "requestCount": usage["requests"],
                }
            )
        rows.sort(key=lambda item: (int(item["usedTokens"]), int(item["requestCount"])), reverse=True)
        return rows[:10]

    @staticmethod
    def _alerts(rankings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        for item in rankings:
            limit_tokens = int(item["limitTokens"] or 0)
            remaining_tokens = int(item["remainingTokens"] or 0)
            used_tokens = int(item["usedTokens"] or 0)
            if limit_tokens <= 0:
                continue
            usage_ratio = 1 - max(remaining_tokens, 0) / limit_tokens
            if remaining_tokens <= 0:
                level = "critical"
            elif usage_ratio >= 0.9:
                level = "warning"
            else:
                continue
            scope_label = "LLM" if item["scope"] == "llm" else "Embedding"
            alerts.append(
                {
                    "level": level,
                    "userId": item["userId"],
                    "username": item["username"],
                    "scope": item["scope"],
                    "usedTokens": used_tokens,
                    "limitTokens": limit_tokens,
                    "remainingTokens": remaining_tokens,
                    "requestCount": int(item["requestCount"] or 0),
                    "usageRatio": round(usage_ratio, 4),
                    "message": f"{item['username']} 的 {scope_label} Token 余额偏低",
                }
            )
        alerts.sort(key=lambda item: (item["level"] == "critical", item["usageRatio"]), reverse=True)
        return alerts[:20]
