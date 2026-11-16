"""The People and Hours pages (docs/backoffice.md § The pages, decided
2026-11-16): every account with its dates and counts, and the hours logged
across the platform all told and in buckets the reader picks. The wall over
both is `test_operator.py`'s; this is what the figures are.
"""

from datetime import UTC, date, datetime, timedelta

import pytest
from bson import ObjectId

from beats.infrastructure.operator_usage import bucket_start, periods_back
from beats.operator.reads import HOURS_DEFAULT_PERIODS, HOURS_MAX_PERIODS


class TestBuckets:
    """The pure half: which day a bucket starts on, and how far back
    `periods` of them reach."""

    def test_a_week_starts_on_its_monday_and_a_month_on_its_first(self):
        wed = date(2026, 11, 18)
        assert bucket_start(wed, "day") == wed
        assert bucket_start(wed, "week") == date(2026, 11, 16)
        assert bucket_start(wed, "month") == date(2026, 11, 1)
        assert bucket_start(date(2026, 11, 16), "week") == date(2026, 11, 16)
        assert bucket_start(date(2026, 11, 15), "week") == date(2026, 11, 9)

    def test_periods_back_ends_on_todays_bucket(self):
        today = date(2026, 11, 16)
        assert periods_back(today, "day", 1) == today
        assert periods_back(today, "day", 30) == date(2026, 10, 18)
        assert periods_back(today, "week", 2) == date(2026, 11, 9)
        assert periods_back(today, "month", 12) == date(2025, 12, 1)
        # Across a year end, to the first of January.
        assert periods_back(date(2026, 1, 20), "month", 2) == date(2025, 12, 1)

    def test_every_unit_has_a_default_inside_its_bound(self):
        for unit, default in HOURS_DEFAULT_PERIODS.items():
            assert 1 <= default <= HOURS_MAX_PERIODS[unit]


def _session(user_id: str, start: datetime, hours: float, **extra) -> dict:
    return {
        "user_id": user_id,
        "project_id": str(ObjectId()),
        "start": start,
        "end": start + timedelta(hours=hours) if hours else None,
        **extra,
    }


class TestHoursRead:
    @pytest.fixture(autouse=True)
    def _clean(self, mongo):
        yield
        mongo.timeLogs.delete_many({})
        mongo.users.delete_many({})
        mongo.projects.delete_many({})

    def test_hours_are_summed_by_the_day_a_session_started_and_a_timer_is_none(
        self, operator_client, mongo
    ):
        ana, ben = str(ObjectId()), str(ObjectId())
        now = datetime.now(UTC)
        today = datetime(now.year, now.month, now.day, tzinfo=UTC)
        mongo.timeLogs.insert_many(
            [
                _session(ana, today + timedelta(hours=9), 1.5),
                _session(ben, today + timedelta(hours=10), 0.5),
                # Started yesterday at 23:30, so yesterday's, though it ends today.
                _session(ana, today - timedelta(minutes=30), 1),
                # Still running: not hours yet.
                _session(ana, today + timedelta(hours=12), 0),
                # Decades back: in the totals, outside the buckets.
                _session(ben, datetime(1999, 4, 12, 9, tzinfo=UTC), 1),
            ]
        )
        body = operator_client.get("/api/operator/hours?unit=day&periods=7").json()
        assert body["unit"] == "day"
        assert body["periods"] == 7
        assert body["total_hours"] == 4.0
        assert body["total_sessions"] == 4
        assert body["accounts_ever"] == 2
        assert body["accounts_last_30d"] == 2
        by_day = {b["period"]: b for b in body["buckets"]}
        assert set(by_day) == {
            today.date().isoformat(),
            (today - timedelta(days=1)).date().isoformat(),
        }
        assert by_day[today.date().isoformat()] == {
            "period": today.date().isoformat(),
            "hours": 2.0,
            "sessions": 2,
            "accounts": 2,
        }
        assert by_day[(today - timedelta(days=1)).date().isoformat()]["hours"] == 1.0

    def test_a_week_bucket_is_named_by_its_monday(self, operator_client, mongo):
        now = datetime.now(UTC)
        monday = now.date() - timedelta(days=now.weekday())
        mongo.timeLogs.insert_one(
            _session(
                str(ObjectId()), datetime(monday.year, monday.month, monday.day, 8, tzinfo=UTC), 2
            )
        )
        body = operator_client.get("/api/operator/hours?unit=week&periods=4").json()
        assert body["since"] == (monday - timedelta(weeks=3)).isoformat()
        assert [b["period"] for b in body["buckets"]] == [monday.isoformat()]

    def test_periods_are_held_to_the_units_bound_and_a_bad_unit_is_422(
        self, operator_client, mongo
    ):
        body = operator_client.get("/api/operator/hours?unit=month&periods=5000").json()
        assert body["periods"] == HOURS_MAX_PERIODS["month"]
        assert operator_client.get("/api/operator/hours?unit=year").status_code == 422

    def test_an_empty_platform_reads_as_nothing(self, operator_client):
        body = operator_client.get("/api/operator/hours").json()
        assert body["total_hours"] == 0
        assert body["buckets"] == []
        assert body["periods"] == HOURS_DEFAULT_PERIODS["day"]


class TestPeopleRead:
    @pytest.fixture(autouse=True)
    def _clean(self, mongo):
        # The page counts every account there is, so the harness's own row
        # goes too, before as well as after.
        mongo.users.delete_many({})
        yield
        mongo.timeLogs.delete_many({})
        mongo.users.delete_many({})
        mongo.projects.delete_many({})

    def test_newest_first_with_counts_and_the_summary(self, operator_client, mongo):
        now = datetime.now(UTC)
        old, new, quiet = ObjectId(), ObjectId(), ObjectId()
        mongo.users.insert_many(
            [
                {
                    "_id": old,
                    "email": "old@example.test",
                    # A BSON date, as older rows have it.
                    "created_at": now - timedelta(days=400),
                    "last_seen_on": (now - timedelta(days=2)).date().isoformat(),
                    "suspended_at": now.isoformat(),
                },
                {
                    "_id": new,
                    "email": "new@example.test",
                    "created_at": (now - timedelta(days=3)).isoformat(),
                    "last_seen_on": now.date().isoformat(),
                },
                {"_id": quiet, "email": "quiet@example.test"},
            ]
        )
        mongo.projects.insert_many(
            [
                {"user_id": str(old), "name": "a"},
                {"user_id": str(old), "name": "b"},
                # An organisation's project has no user_id and is nobody's count.
                {"organisation_id": str(ObjectId()), "name": "c"},
            ]
        )
        mongo.timeLogs.insert_one(_session(str(old), now - timedelta(hours=3), 1))
        body = operator_client.get("/api/operator/accounts").json()
        assert body["total"] == 3
        assert body["created_last_30d"] == 1
        assert body["seen_last_7d"] == 2
        assert body["seen_last_30d"] == 2
        assert body["suspended"] == 1
        assert [r["email"] for r in body["rows"]] == [
            "new@example.test",
            "old@example.test",
            "quiet@example.test",
        ]
        oldest = body["rows"][1]
        assert oldest["projects"] == 2
        assert oldest["sessions"] == 1
        assert oldest["suspended"]
        assert oldest["last_seen_on"] == (now - timedelta(days=2)).date().isoformat()
        assert body["rows"][2]["last_seen_on"] is None

    def test_the_limit_cuts_the_rows_and_not_the_total(self, operator_client, mongo):
        mongo.users.insert_many([{"email": f"p{i}@example.test"} for i in range(3)])
        body = operator_client.get("/api/operator/accounts?limit=2").json()
        assert body["total"] == 3
        assert len(body["rows"]) == 2
