"""The platform controls' reading rules (docs/backoffice.md § Controls), with
no database: what the documents mean, and what the cache does when the
database cannot be read. The routes that refuse are test_account_controls.py;
the commands that write are test_operator_commands.py.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest

from beats import platform_controls
from beats.platform_controls import PlatformControls, controls_from_docs

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def _doc(name: str, **fields) -> dict:
    return {"name": name, "until": None, "value": None, "reason": None, **fields}


class TestReading:
    def test_no_document_means_open(self):
        controls = controls_from_docs([], NOW)
        assert controls == PlatformControls()
        for name in platform_controls.PAUSES:
            assert controls.paused(name, NOW) is False
        for name in platform_controls.LIMITS:
            assert controls.limit(name) is None

    def test_a_pause_in_force_pauses_and_an_expired_one_is_open(self):
        later = (NOW + timedelta(hours=1)).isoformat()
        earlier = (NOW - timedelta(seconds=1)).isoformat()
        assert controls_from_docs([_doc("coach", until=later)], NOW).paused("coach", NOW) is True
        assert controls_from_docs([_doc("coach", until=earlier)], NOW).paused("coach", NOW) is False
        # The boundary: a pause ends at its instant, not after it.
        at = controls_from_docs([_doc("coach", until=NOW.isoformat())], NOW)
        assert at.paused("coach", NOW) is False

    def test_signups_with_a_value_are_slowed_rather_than_paused(self):
        later = (NOW + timedelta(hours=1)).isoformat()
        slowed = controls_from_docs([_doc("signups", until=later, value=20)], NOW)
        assert slowed.paused("signups", NOW) is False
        assert slowed.signups_per_hour(NOW) == 20
        paused = controls_from_docs([_doc("signups", until=later)], NOW)
        assert paused.paused("signups", NOW) is True
        assert paused.signups_per_hour(NOW) is None

    def test_a_limit_is_a_setting_and_does_not_expire(self):
        controls = controls_from_docs([_doc("writes_per_minute_beats", value=120)], NOW)
        assert controls.limit("writes_per_minute_beats") == 120
        assert controls.limit("writes_per_minute_signals") is None

    def test_a_name_nobody_knows_is_ignored(self):
        controls = controls_from_docs([_doc("everything", until="2099-01-01T00:00:00+00:00")], NOW)
        assert controls == PlatformControls()


class _Cursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self):
        return self._docs


class _Collection:
    def __init__(self, docs=None, *, fail=False):
        self.docs = docs or []
        self.fail = fail

    def find(self, _query):
        if self.fail:
            raise ConnectionError("mongo is away")
        return _Cursor(self.docs)


class _Db:
    def __init__(self, col):
        self._col = col

    def __getitem__(self, name):
        assert name == platform_controls.COLLECTION
        return self._col


def _db(col) -> Any:
    """A stand-in for the one collection `resolve` reads."""
    return cast("Any", _Db(col))


class TestCache:
    @pytest.fixture(autouse=True)
    def _fresh(self):
        platform_controls.clear()
        yield
        platform_controls.clear()

    async def test_a_failed_read_keeps_the_last_value(self):
        later = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        col = _Collection([_doc("imports", until=later)])
        first = await platform_controls.resolve(_db(col))
        assert first.paused("imports", datetime.now(UTC)) is True

        col.fail = True
        platform_controls._expires_at = 0.0  # the bound has passed
        again = await platform_controls.resolve(_db(col))
        assert again.paused("imports", datetime.now(UTC)) is True, "the last value stands"

    async def test_a_failed_first_read_is_open(self):
        """The switches must not be a way for a database blip to turn the
        product off: with nothing ever read, a failure reads as open."""
        controls = await platform_controls.resolve(_db(_Collection(fail=True)))
        assert controls == PlatformControls()

    async def test_the_bound_holds_between_reads(self):
        col = _Collection([])
        await platform_controls.resolve(_db(col))
        later = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        col.docs = [_doc("coach", until=later)]
        cached = await platform_controls.resolve(_db(col))
        assert cached.paused("coach", datetime.now(UTC)) is False, "not re-read inside the bound"
