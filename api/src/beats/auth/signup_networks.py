"""The sign-up network signal (docs/backoffice.md § The pages, Trust and
safety): a count of sign-ups per hour per *network*, so a wave from one place
shows while it happens, while keeping less about addresses than the request
log already does.

- **Truncate, then hash.** IPv4 to its /24, IPv6 to its /48, then an HMAC
  under a key derived for the UTC day from `JWT_SECRET` — which the public
  API already holds and the operator deployment never does, so the operator
  can never compute a key and so never test a guess. No new secret: a
  deployment that can sign a session can run this signal.
- **Store only a counter** (`signup_network_counts`): the hour, the opaque
  key, `started` and `completed`, and a TTL of 48 hours. Never an address,
  never an account, never anything that joins one to a network.
- **Never break a sign-up.** Every write here is best effort: a failure is
  logged and the sign-up goes on.

The address is the one `ProxyHeadersMiddleware` resolved, so a change to
`FORWARDED_ALLOW_IPS` or a new proxy changes this signal too. Behind a
self-hosted nginx every visitor is one network, which only makes the signal
quiet, never wrong about a person.
"""

import hashlib
import hmac
import ipaddress
import logging
from datetime import UTC, date, datetime, timedelta

from pymongo.asynchronous.database import AsyncDatabase

from beats.platform_controls import SIGNUP_NETWORK_COUNTS, hour_key
from beats.settings import settings

logger = logging.getLogger(__name__)

COUNTS_TTL = timedelta(hours=48)


def network_of(address: str) -> str | None:
    """The address cut to its network: /24 for IPv4, /48 for IPv6. None for
    anything that is not an address (a test client's name, an empty host)."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv4Address):
        return str(ipaddress.ip_network(f"{ip}/24", strict=False))
    return str(ipaddress.ip_network(f"{ip}/48", strict=False))


def network_key(address: str, day: date, secret: str) -> str | None:
    """An opaque, day-scoped name for the address's network. The same
    network reads the same within a UTC day and differently the next, so a
    stored key stops matching anything at midnight."""
    network = network_of(address)
    if network is None:
        return None
    message = f"signup-network:{day.isoformat()}:{network}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()[:32]


def key_for(address: str | None, now: datetime | None = None) -> str | None:
    """The key for a visitor now, under the deployment's own secret."""
    if not address:
        return None
    return network_key(address, (now or datetime.now(UTC)).date(), settings.jwt_secret)


async def _count(db: AsyncDatabase, address: str | None, field: str) -> None:
    now = datetime.now(UTC)
    key = key_for(address, now)
    if key is None:
        return
    hour = hour_key(now)
    try:
        await db[SIGNUP_NETWORK_COUNTS].update_one(
            {"hour": hour, "key": key},
            {
                "$inc": {field: 1},
                "$setOnInsert": {
                    "expires_at": now.replace(minute=0, second=0, microsecond=0) + COUNTS_TTL
                },
            },
            upsert=True,
        )
    except Exception:  # noqa: BLE001 — the signal must never break a sign-up
        logger.warning("signup_network_counts could not be written; the sign-up goes on")


async def count_started(db: AsyncDatabase, address: str | None) -> None:
    """`POST /register/start` created a user row — abandoned starts included."""
    await _count(db, address, "started")


async def count_completed(db: AsyncDatabase, address: str | None) -> None:
    """A finished passkey registration, or an account a provider created."""
    await _count(db, address, "completed")
