"""Per-account rate limits on the write routes that matter.

The IP-keyed limits in `routers/auth.py` protect the unauthenticated doors;
these protect the authenticated write paths — beats, signals, import — keyed
on the account, so a hostile or broken client is capped as itself, not as
whatever address Cloud Run's front end saw. Same limiter, same decision about
per-instance counts (the comment above `limiter` in `routers/auth.py`).

How the pieces fit slowapi:

- `account_key` is the `key_func`; the middleware set `request.state.user_id`
  before any route runs.
- Each limit provider takes `key`, so slowapi hands it `account_key(request)`
  and it can read the account's own ceiling — the cached lookup the middleware
  just filled (`auth/account_access.py`), falling back to the global setting.
- Each `*_off` is an `exempt_when` taking the request: with no ceiling set
  anywhere, the route is exempt and nothing is counted. The provider still
  never returns an unparsable limit — exemption is checked against the built
  limit, so it answers a ceiling no client reaches when off.
"""

from fastapi import Request

from beats import platform_controls
from beats.auth import account_access
from beats.settings import settings

# What the provider answers while the route is exempt: parsed by slowapi,
# reached by nobody.
_UNLIMITED = 1_000_000


def account_key(request: Request) -> str:
    # slowapi calls the `key_func` on every request to a route that carries
    # one of these limits, refused or not, so setting the flag here is how
    # the 429 handler tells an account-keyed refusal from an address-keyed
    # one — without repeating the list of routes, and without `api/errors.py`
    # importing this module, which reads `beats.settings` and so may not be
    # reached from the operator's composition root.
    request.state.account_limited = True
    return getattr(request.state, "user_id", "")


def _ceiling(user_id: str, override: str, default: int | None) -> int | None:
    """The account's own ceiling when one is set, else the operator's
    platform-wide one (`platform_controls`, set without a deploy), else the
    setting — which stays, for a self-hosted install with no operator. Both
    caches were filled by the middleware on the way in."""
    access = account_access.get(user_id)
    value: int | None = getattr(access, override, None) if access is not None else None
    if value is not None:
        return value
    control = platform_controls.current().limit(override)
    return control if control is not None else default


def beats_writes_limit(key: str) -> str:
    ceiling = _ceiling(key, "writes_per_minute_beats", settings.writes_per_minute_beats)
    return f"{ceiling if ceiling is not None else _UNLIMITED}/minute"


def beats_writes_off(request: Request) -> bool:
    key = account_key(request)
    return _ceiling(key, "writes_per_minute_beats", settings.writes_per_minute_beats) is None


def signals_writes_limit(key: str) -> str:
    ceiling = _ceiling(key, "writes_per_minute_signals", settings.writes_per_minute_signals)
    return f"{ceiling if ceiling is not None else _UNLIMITED}/minute"


def signals_writes_off(request: Request) -> bool:
    key = account_key(request)
    return _ceiling(key, "writes_per_minute_signals", settings.writes_per_minute_signals) is None


def imports_limit(key: str) -> str:
    ceiling = _ceiling(key, "imports_per_hour", settings.imports_per_hour)
    return f"{ceiling if ceiling is not None else _UNLIMITED}/hour"


def imports_off(request: Request) -> bool:
    return _ceiling(account_key(request), "imports_per_hour", settings.imports_per_hour) is None
