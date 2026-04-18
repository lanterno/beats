"""LLM usage tracking and per-user budget enforcement.

Each Anthropic call logs a row to the `llm_usage` Mongo collection. The
`enforce_budget` method sums the current month's spend and raises if the
ceiling is exceeded.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from beats.coach.repos import LLM_USAGE_COLLECTION
from beats.infrastructure.database import Database
from beats.settings import settings

logger = logging.getLogger(__name__)


class BudgetExceeded(Exception):
    def __init__(self, spent: float, limit: float) -> None:
        self.spent = spent
        self.limit = limit
        super().__init__(f"Monthly LLM budget exceeded: ${spent:.2f} / ${limit:.2f}")


class UsageTracker:
    def __init__(self, user_id: str) -> None:
        self._user_id = user_id
        self._col = Database.get_db()[LLM_USAGE_COLLECTION]

    async def record(
        self,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        cache_creation: int,
        cache_read: int,
        cost_usd: float,
        purpose: str,
    ) -> None:
        await self._col.insert_one(
            {
                "user_id": self._user_id,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_creation,
                "cache_read_input_tokens": cache_read,
                "cost_usd": cost_usd,
                "purpose": purpose,
                "ts": datetime.now(UTC),
            }
        )

    async def month_spend(self) -> float:
        now = datetime.now(UTC)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        pipeline = [
            {"$match": {"user_id": self._user_id, "ts": {"$gte": month_start}}},
            {"$group": {"_id": None, "total": {"$sum": "$cost_usd"}}},
        ]
        result = await self._col.aggregate(pipeline).to_list(1)
        if result:
            return float(result[0]["total"])
        return 0.0

    async def enforce_budget(self) -> None:
        limit = settings.coach_monthly_budget_usd
        if limit <= 0:
            return
        spent = await self.month_spend()
        if spent >= limit:
            logger.info(
                "Budget exceeded for user=%s: $%.2f / $%.2f",
                self._user_id,
                spent,
                limit,
            )
            raise BudgetExceeded(spent, limit)

    async def usage_summary(self, days: int = 30) -> list[dict]:
        """Daily usage breakdown for the cost dashboard."""
        since = datetime.now(UTC) - timedelta(days=days)
        pipeline = [
            {"$match": {"user_id": self._user_id, "ts": {"$gte": since}}},
            {
                "$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$ts"}},
                    "cost_usd": {"$sum": "$cost_usd"},
                    "input_tokens": {"$sum": "$input_tokens"},
                    "output_tokens": {"$sum": "$output_tokens"},
                    "cache_read": {"$sum": "$cache_read_input_tokens"},
                    "cache_creation": {"$sum": "$cache_creation_input_tokens"},
                    "calls": {"$sum": 1},
                }
            },
            {"$sort": {"_id": 1}},
        ]
        return await self._col.aggregate(pipeline).to_list(100)
