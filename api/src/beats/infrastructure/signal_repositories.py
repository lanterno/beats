"""Persistence for what the ambient daemon and the companion record.

Split out of `repositories.py` at the ceiling in roadmaps/file-sizes.md:
flow windows, signal summaries, the coach's pending suggestions and the
day's biometrics.
"""

from datetime import date, datetime
from typing import Any, Protocol

from beats.domain.models import (
    BiometricDay,
    FlowWindow,
    PendingSuggestion,
    SignalSummary,
)
from beats.infrastructure.repositories import (
    MongoStore,
)


class FlowWindowRepository(Protocol):
    async def create(self, window: FlowWindow) -> FlowWindow: ...
    async def list_by_range(
        self,
        start: datetime,
        end: datetime,
        project_id: str | None = None,
        editor_repo: str | None = None,
        editor_language: str | None = None,
        bundle_id: str | None = None,
        dominant_category: str | None = None,
    ) -> list[FlowWindow]: ...


class MongoFlowWindowRepository(MongoStore[FlowWindow], FlowWindowRepository):
    model = FlowWindow

    async def create(self, window: FlowWindow) -> FlowWindow:
        return await self._insert(window)

    async def list_by_range(
        self,
        start: datetime,
        end: datetime,
        project_id: str | None = None,
        editor_repo: str | None = None,
        editor_language: str | None = None,
        bundle_id: str | None = None,
        dominant_category: str | None = None,
    ) -> list[FlowWindow]:
        """Windows overlapping [start, end], narrowed by any filter given.

        Filters are AND-composed and all optional. project_id matches windows
        captured while a timer was running on that project; editor_repo and
        editor_language match what the editor heartbeat reported; bundle_id
        matches the dominant frontmost app; dominant_category matches the
        rolled-up category, e.g. "drift" for the daemon shield's distractions.
        """
        extra: dict[str, Any] = {
            "window_start": {"$gte": start.isoformat(), "$lte": end.isoformat()}
        }
        for field, value in (
            ("active_project_id", project_id),
            ("editor_repo", editor_repo),
            ("editor_language", editor_language),
            ("dominant_bundle_id", bundle_id),
            ("dominant_category", dominant_category),
        ):
            if value is not None:
                extra[field] = value
        return await self._find_many(extra, sort=("window_start", 1))


class PendingSuggestionRepository(Protocol):
    async def create(self, suggestion: PendingSuggestion) -> PendingSuggestion: ...
    async def list_recent(self, since: datetime, limit: int = 20) -> list[PendingSuggestion]: ...


class MongoPendingSuggestionRepository(MongoStore[PendingSuggestion], PendingSuggestionRepository):
    model = PendingSuggestion

    async def create(self, suggestion: PendingSuggestion) -> PendingSuggestion:
        return await self._insert(suggestion)

    async def list_recent(self, since: datetime, limit: int = 20) -> list[PendingSuggestion]:
        return await self._find_many(
            {"suggested_at": {"$gte": since.isoformat()}},
            sort=("suggested_at", -1),
            limit=limit,
        )


class SignalSummaryRepository(Protocol):
    async def upsert(self, summary: SignalSummary) -> SignalSummary: ...
    async def list_by_range(self, start: datetime, end: datetime) -> list[SignalSummary]: ...
    async def delete_all(self) -> int: ...


class MongoSignalSummaryRepository(MongoStore[SignalSummary], SignalSummaryRepository):
    model = SignalSummary

    async def upsert(self, summary: SignalSummary) -> SignalSummary:
        # Filter on the serialized hour, not summary.hour: the two render
        # differently ("...T14:00:00Z" vs "...T14:00:00+00:00") and a mismatch
        # would insert a duplicate rather than update in place.
        data = self._dump(summary)
        return await self._upsert(summary, {"device_id": data["device_id"], "hour": data["hour"]})

    async def list_by_range(self, start: datetime, end: datetime) -> list[SignalSummary]:
        return await self._find_many(
            {"hour": {"$gte": start.isoformat(), "$lte": end.isoformat()}},
            sort=("hour", 1),
        )

    async def delete_all(self) -> int:
        return await self._delete_all()


class BiometricDayRepository(Protocol):
    async def upsert(self, day: BiometricDay) -> BiometricDay: ...
    async def list_by_range(self, start: date, end: date) -> list[BiometricDay]: ...
    async def delete_all(self) -> int: ...


class MongoBiometricDayRepository(MongoStore[BiometricDay], BiometricDayRepository):
    model = BiometricDay

    async def upsert(self, day: BiometricDay) -> BiometricDay:
        data = self._dump(day)
        return await self._upsert(day, {"date": data["date"], "source": data["source"]})

    async def list_by_range(self, start: date, end: date) -> list[BiometricDay]:
        return await self._find_many(
            {"date": {"$gte": start.isoformat(), "$lte": end.isoformat()}},
            sort=("date", 1),
        )

    async def delete_all(self) -> int:
        return await self._delete_all()
