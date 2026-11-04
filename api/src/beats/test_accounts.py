"""The account auth-state cache and the account service.

The cache (`auth/account_access.py`) is what makes checking suspension on
every request affordable, so pin the properties that make it safe: it
expires, and a fresh entry is read after `forget`. The service
(`domain/accounts.py`) holds the rules the suspend script — and later the
control plane's commands — drive.
"""

import time
from datetime import UTC, datetime, timedelta

import pytest

from beats.auth import account_access
from beats.brand import CONTACT_EMAIL
from beats.domain.accounts import AccountNotFound, AccountService, suspension_detail
from beats.domain.models import SuspensionKind, User


@pytest.fixture(autouse=True)
def _clean():
    account_access.clear()
    yield
    account_access.clear()


class TestAccountAccessCache:
    def test_unknown_account_is_a_miss(self):
        assert account_access.get("u-1") is None

    def test_remembers_the_state(self):
        access = account_access.AccountAccess(exists=True)
        account_access.remember("u-1", access)
        assert account_access.get("u-1") is access

    def test_forget_makes_the_next_read_a_miss(self):
        account_access.remember("u-1", account_access.AccountAccess(exists=True))
        account_access.forget("u-1")
        assert account_access.get("u-1") is None

    def test_entry_expires(self, monkeypatch):
        clock = [1000.0]
        monkeypatch.setattr(time, "monotonic", lambda: clock[0])

        account_access.remember("u-1", account_access.AccountAccess(exists=True))
        clock[0] += account_access.TTL_SECONDS - 1
        assert account_access.get("u-1") is not None

        clock[0] += 2
        assert account_access.get("u-1") is None

    def test_note_seen_updates_the_cached_day_without_resetting_ttl(self, monkeypatch):
        """The middleware stamps last_seen_on once and tells the cache, so
        the entry's remaining TTL doesn't repeat the write."""
        clock = [1000.0]
        monkeypatch.setattr(time, "monotonic", lambda: clock[0])
        account_access.remember("u-1", account_access.AccountAccess(exists=True))

        today = datetime.now(UTC).date()
        account_access.note_seen("u-1", today)

        cached = account_access.get("u-1")
        assert cached is not None
        assert cached.last_seen_on == today
        clock[0] += account_access.TTL_SECONDS + 1
        assert account_access.get("u-1") is None

    def test_note_seen_is_safe_for_an_uncached_account(self):
        account_access.note_seen("never-seen", datetime.now(UTC).date())

    def test_suspended_reads_off_suspended_at(self):
        plain = account_access.AccountAccess(exists=True)
        suspended = account_access.AccountAccess(exists=True, suspended_at=datetime.now(UTC))
        assert not plain.suspended
        assert suspended.suspended


class _FakeStore:
    def __init__(self, *users: User):
        self._users = {u.id: u for u in users}

    async def get_by_id(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    async def update(self, user: User) -> User:
        assert user.id in self._users
        self._users[user.id] = user
        return user


class TestAccountService:
    def _service(self) -> tuple[AccountService, _FakeStore]:
        store = _FakeStore(User(id="u-1", email="a@b.com"))
        return AccountService(store), store

    async def test_suspend_sets_the_four_fields(self):
        service, store = self._service()
        user = await service.suspend(
            "u-1", kind=SuspensionKind.ABUSE, reason="scraping", by="operator-sub"
        )
        assert user.suspended
        assert user.suspended_kind is SuspensionKind.ABUSE
        assert user.suspended_reason == "scraping"
        assert user.suspended_by == "operator-sub"
        stored = await store.get_by_id("u-1")
        assert stored is not None
        assert stored.suspended

    async def test_unsuspend_clears_all_of_them(self):
        service, _ = self._service()
        await service.suspend("u-1", kind=SuspensionKind.OTHER, reason="r", by="x")
        user = await service.unsuspend("u-1")
        assert not user.suspended
        assert user.suspended_kind is None
        assert user.suspended_reason is None
        assert user.suspended_by is None

    async def test_sign_out_everywhere_sets_the_cut_and_only_the_cut(self):
        """Sign-out ends sessions; it neither suspends nor touches devices."""
        service, _ = self._service()
        before = datetime.now(UTC)
        user = await service.sign_out_everywhere("u-1")
        assert user.sessions_valid_after is not None
        assert user.sessions_valid_after >= before
        assert not user.suspended

    async def test_an_unknown_account_is_not_found(self):
        service, _ = self._service()
        with pytest.raises(AccountNotFound):
            await service.suspend("nope", kind=SuspensionKind.ABUSE, reason="r", by="x")


class TestSuspensionDetail:
    """The one sentence a suspended person reads, everywhere it is refused.
    It carries the contact address and never the operator's reason."""

    def test_names_the_contact_address(self):
        detail = suspension_detail(SuspensionKind.ABUSE, datetime.now(UTC))
        assert CONTACT_EMAIL in detail
        assert "suspended" in detail

    def test_an_erasure_names_the_day_the_window_ends(self):
        queued = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
        detail = suspension_detail(SuspensionKind.ERASURE, queued)
        assert (queued + timedelta(days=7)).date().isoformat() in detail
        assert CONTACT_EMAIL in detail
        assert "deleted" in detail

    def test_a_kind_stored_as_a_string_still_reads_as_its_kind(self):
        """The middleware reads the raw document, where the kind is the
        stored string, not the enum."""
        queued = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
        assert suspension_detail("erasure", queued) == suspension_detail(
            SuspensionKind.ERASURE, queued
        )
