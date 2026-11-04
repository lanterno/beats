"""Rules on the account itself: suspension and sign-out everywhere.

Driven today by `api/scripts/suspend_account.py`; the control plane's
`account.*` commands delegate here when step 3 of roadmaps/backoffice.md
ships, so the rule never lives in two places.
"""

from datetime import UTC, datetime, timedelta
from typing import Protocol

from beats.brand import CONTACT_EMAIL
from beats.domain.exceptions import DomainException
from beats.domain.models import SuspensionKind, User


class AccountStore(Protocol):
    """The two calls this service makes. `MongoUserRepository` satisfies it
    structurally, like every port in `domain/ports.py`; declared here because
    accounts are not user-scoped data, so it is not one of that file's."""

    async def get_by_id(self, user_id: str) -> User | None: ...
    async def update(self, user: User) -> User: ...


# The window between queueing an erasure and running it (step 4's job). The
# suspension an erasure places starts when it is queued, so the refusal can
# name the day the window ends.
ERASURE_WINDOW_DAYS = 7


class AccountNotFound(DomainException):
    """No account with that id."""

    status_code = 404
    message = "Account not found"
    code = "ACCOUNT_NOT_FOUND"


def suspension_detail(kind: SuspensionKind | str | None, suspended_at: datetime | None) -> str:
    """The one sentence a suspended account is refused with, everywhere.

    The operator's own reason is never in it — that lives in the audit. An
    erasure's wording differs so that an account holder whose address was
    impersonated in a deletion mail finds out the moment they next open the
    app, inside the week they have to stop it.
    """
    if kind == SuspensionKind.ERASURE and suspended_at is not None:
        ends = (suspended_at + timedelta(days=ERASURE_WINDOW_DAYS)).date().isoformat()
        return (
            f"This account is being deleted on {ends}. "
            f"To keep it, write to {CONTACT_EMAIL} from this account's address."
        )
    return f"This account is suspended. Write to {CONTACT_EMAIL} from this account's address."


class AccountService:
    """Suspend, unsuspend and sign out everywhere.

    Enforcement happens in the auth middleware off a cached lookup
    (`beats.auth.account_access`), so a change made here — or by any other
    process against the same database — takes effect within the cache's TTL
    on every instance. Nothing needs invalidating from this side.
    """

    def __init__(self, users: AccountStore):
        self._users = users

    async def _get(self, user_id: str) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise AccountNotFound()
        return user

    async def suspend(self, user_id: str, *, kind: SuspensionKind, reason: str, by: str) -> User:
        user = await self._get(user_id)
        user.suspended_at = datetime.now(UTC)
        user.suspended_by = by
        user.suspended_kind = kind
        user.suspended_reason = reason
        return await self._users.update(user)

    async def unsuspend(self, user_id: str) -> User:
        user = await self._get(user_id)
        user.suspended_at = None
        user.suspended_by = None
        user.suspended_kind = None
        user.suspended_reason = None
        return await self._users.update(user)

    async def sign_out_everywhere(self, user_id: str) -> User:
        """End every session: a token whose sign-in is older than this moment
        is refused from here on. Devices are untouched — revocation ends one
        device, suspension ends both."""
        user = await self._get(user_id)
        user.sessions_valid_after = datetime.now(UTC)
        return await self._users.update(user)
