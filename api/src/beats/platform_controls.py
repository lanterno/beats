"""The platform's switches and global write limits (docs/backoffice.md
§ Controls).

One document per control in `platform_controls`, written only by the
operator's `control.set` and `control.clear` commands, read by the public API
through a short-lived process-local cache in the shape of
`auth/account_access.py`, and with the same bound: a pause lands within
`TTL_SECONDS` on every instance.

Three properties keep the switches from becoming a way for a database blip
to turn the product off:

- **an absent document means open**, so a self-hosted install with no
  operator at all behaves as it always did;
- **every pause expires**: `until` is required and capped at `MAX_PAUSE`, and
  an expired document reads as open, so no job clears it;
- **a failed read keeps the last value**, and open if there is none.

This module imports no settings and nothing under `beats.auth`, because the
operator's composition root loads it too (through the commands) and must
never load the API's secrets. The settings fallback for the three limits stays
in `api/rate_limits.py`, which is the public API's alone.

Refusals are 409 with a code of their own and fixed text — never the
operator's `reason`, which is for the operator's page. Not 503, which would
page the owner the moment they pause something on purpose; not 403 or 429,
which `api_rejections` counts.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal, get_args

from pydantic import TypeAdapter
from pymongo.asynchronous.database import AsyncDatabase

from beats.domain.exceptions import DomainException

logger = logging.getLogger(__name__)

PauseName = Literal["coach", "webhooks", "imports", "signups"]
LimitName = Literal["writes_per_minute_beats", "writes_per_minute_signals", "imports_per_hour"]
ControlName = Literal[
    "coach",
    "webhooks",
    "imports",
    "signups",
    "writes_per_minute_beats",
    "writes_per_minute_signals",
    "imports_per_hour",
]

PAUSES: tuple[str, ...] = get_args(PauseName)
LIMITS: tuple[str, ...] = get_args(LimitName)
CONTROL_NAMES: tuple[str, ...] = get_args(ControlName)

# No pause outlives this. An incident that lasts longer is set again, on
# purpose, by somebody looking at it.
MAX_PAUSE = timedelta(days=7)
# How long an instance keeps what it last read. The page says a pause lands
# within this.
TTL_SECONDS = 30.0

COLLECTION = "platform_controls"
# Where the sign-up network signal keeps its hourly counters
# (`auth/signup_networks.py` writes them; the operator reads them). Named here
# so a network-scoped `signups` control can read the hour's count without this
# module importing anything under `beats.auth`.
SIGNUP_NETWORK_COUNTS = "signup_network_counts"


def hour_key(at: datetime) -> str:
    """The UTC hour as the counters key it: `2026-11-14T09`."""
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H")


_iso = TypeAdapter(datetime)


@dataclass(frozen=True)
class Control:
    """One document, as read. A pause carries `until`; a limit carries
    `value`; `signups` may carry both, which is the third state — slowed to
    `value` an hour until `until`."""

    name: str
    until: datetime | None = None
    value: int | None = None
    reason: str | None = None
    set_by: str | None = None
    set_at: datetime | None = None
    # `signups` only: the opaque network key the ceiling applies to, from the
    # sign-up network signal. The key is derived for the UTC day, so such a
    # control is capped at the next midnight, when it would stop matching.
    network: str | None = None

    def in_force(self, now: datetime) -> bool:
        if self.name in LIMITS:
            return self.value is not None
        return self.until is not None and self.until > now


@dataclass(frozen=True)
class PlatformControls:
    """Every control as it stands, with the expired ones already read as
    open."""

    controls: dict[str, Control] = field(default_factory=dict)

    def paused(self, name: str, now: datetime) -> bool:
        """Whether the kind of work `name` stands for is stopped outright.
        `signups` with a `value` is slowed, not paused."""
        control = self.controls.get(name)
        if control is None or not control.in_force(now):
            return False
        slowed = control.value is not None or control.network is not None
        return not (name == "signups" and slowed)

    def signups_control(self, now: datetime) -> Control | None:
        """The `signups` control in force, whatever its state."""
        control = self.controls.get("signups")
        if control is None or not control.in_force(now):
            return None
        return control

    def signups_per_hour(self, now: datetime) -> int | None:
        """The ceiling on sign-ups an hour while *every* sign-up is slowed."""
        control = self.signups_control(now)
        if control is None or control.network is not None:
            return None
        return control.value

    def limit(self, name: str) -> int | None:
        control = self.controls.get(name)
        return control.value if control is not None else None


OPEN = PlatformControls()


def _as_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    return None


def control_from_doc(doc: dict) -> Control:
    value = doc.get("value")
    return Control(
        name=str(doc.get("name", "")),
        until=_as_datetime(doc.get("until")),
        value=int(value) if isinstance(value, int | float) else None,
        reason=doc.get("reason") if isinstance(doc.get("reason"), str) else None,
        set_by=doc.get("set_by") if isinstance(doc.get("set_by"), str) else None,
        set_at=_as_datetime(doc.get("set_at")),
        network=doc.get("network") if isinstance(doc.get("network"), str) else None,
    )


def controls_from_docs(docs: list[dict], now: datetime) -> PlatformControls:
    """The documents as the public API reads them: a name it does not know
    is ignored, and one no longer in force is left out, so an expired pause
    is open without anybody clearing it."""
    controls: dict[str, Control] = {}
    for doc in docs:
        control = control_from_doc(doc)
        if control.name in CONTROL_NAMES and control.in_force(now):
            controls[control.name] = control
    return PlatformControls(controls)


# ── the cache ────────────────────────────────────────────────────────

_state: PlatformControls = OPEN
_expires_at = 0.0


def current() -> PlatformControls:
    """What this process last read, whatever its age: for the synchronous
    rate-limit callables, which run after the middleware refreshed it."""
    return _state


async def resolve(db: AsyncDatabase) -> PlatformControls:
    """The controls, re-read when the last read is older than the bound. A
    failed read keeps the last value and tries again after the bound, so a
    database blip neither turns the product off nor hammers the database."""
    global _state, _expires_at
    if _expires_at > time.monotonic():
        return _state
    try:
        docs = await db[COLLECTION].find({}).to_list()
        _state = controls_from_docs(docs, datetime.now(UTC))
    except Exception:  # noqa: BLE001 — the last value stands, by design
        logger.warning("platform_controls could not be read; keeping the last value")
    _expires_at = time.monotonic() + TTL_SECONDS
    return _state


def clear() -> None:
    """Forget what was read. Used by tests, and by nothing else: the
    operator deployment is another process and cannot reach this."""
    global _state, _expires_at
    _state = OPEN
    _expires_at = 0.0


# ── the refusals ─────────────────────────────────────────────────────


class CoachPaused(DomainException):
    status_code = 409
    code = "COACH_PAUSED"
    message = "The coach is paused for everyone at the moment. Try again later."


class ImportsPaused(DomainException):
    status_code = 409
    code = "IMPORTS_PAUSED"
    message = "Imports are paused for everyone at the moment. Try again later."


class SignupsPaused(DomainException):
    """Also the answer while sign-ups are slowed and the hour's ceiling is
    reached: one code, one sentence. Never a sign-in or an added passkey."""

    status_code = 409
    code = "SIGNUPS_PAUSED"
    message = "Sign-ups are paused at the moment. Try again later."


async def refuse_if_coach_paused(db: AsyncDatabase) -> None:
    if (await resolve(db)).paused("coach", datetime.now(UTC)):
        raise CoachPaused()


async def refuse_if_imports_paused(db: AsyncDatabase) -> None:
    if (await resolve(db)).paused("imports", datetime.now(UTC)):
        raise ImportsPaused()


async def webhooks_paused(db: AsyncDatabase) -> bool:
    return (await resolve(db)).paused("webhooks", datetime.now(UTC))


# Sign-ups in the last hour, counted at most once a bound: the ceiling is a
# brake on a wave, and a wave is not measured to the request.
_signups_last_hour = 0
_signups_counted_at = 0.0


async def refuse_if_signups_paused(db: AsyncDatabase) -> None:
    """Paused outright: refused. What `/register/verify` checks, so a row a
    script started before the pause cannot be finished during it. Not the
    slow-down: that is a ceiling on sign-ups *started*, applied at the start,
    and a visitor it let through is already in the count — checked again at
    verify, the ceiling would refuse them against their own start, and a
    ceiling of one would refuse everyone."""
    if (await resolve(db)).paused("signups", datetime.now(UTC)):
        raise SignupsPaused()


async def refuse_if_signups_closed(db: AsyncDatabase, network_key: str | None = None) -> None:
    """Paused: refused. Slowed: refused once the hour holds `value` sign-ups
    already. Slowed for one network: refused once *that network* started
    `value` sign-ups this hour, read off the signal's own counter, and only
    when the visitor's key is that network's. `users.created_at` is stored
    in the model's JSON form (an ISO string, see `MongoUserRepository`), so
    the bound is written the same way and the comparison is lexical."""
    global _signups_last_hour, _signups_counted_at
    now = datetime.now(UTC)
    controls = await resolve(db)
    if controls.paused("signups", now):
        raise SignupsPaused()
    control = controls.signups_control(now)
    if control is not None and control.network is not None:
        if network_key is None or network_key != control.network or control.value is None:
            return
        doc = await db[SIGNUP_NETWORK_COUNTS].find_one(
            {"hour": hour_key(now), "key": control.network}, projection=["started"]
        )
        if doc is not None and int(doc.get("started", 0)) >= control.value:
            raise SignupsPaused()
        return
    ceiling = controls.signups_per_hour(now)
    if ceiling is None:
        return
    if _signups_counted_at + TTL_SECONDS <= time.monotonic():
        since = _iso.dump_python(now - timedelta(hours=1), mode="json")
        _signups_last_hour = await db.users.count_documents({"created_at": {"$gte": since}})
        _signups_counted_at = time.monotonic()
    if _signups_last_hour >= ceiling:
        raise SignupsPaused()
