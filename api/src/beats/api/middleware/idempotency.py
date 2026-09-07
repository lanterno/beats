"""Idempotency middleware — de-dupes replayed mutations via a client-id cache.

The offline mutation queue in the UI (Stage 1.4) tags every write with a
`X-Client-Id` UUID. When the client retries a write after a network failure,
the same id arrives again. This middleware keeps the user from being charged
twice for the same action:

  1. Reserve `(user_id, client_id)` in `mutation_log` with a unique-index insert.
  2. If the reservation is taken and the stored response is complete, replay that
     body and mark it `X-Idempotent-Replay`.
  3. If it is taken but still running, the identical request is in flight
     somewhere else: answer 409 rather than executing it a second time.
  4. Otherwise run the handler; on a 2xx, buffer the body onto the reservation.
     Any other outcome releases the reservation so a corrected retry can run.

Reserving before executing rather than checking first is what makes concurrent
replays safe. A check-then-execute pass lets two simultaneous retries of the
same id both miss the lookup and both apply the mutation — which is exactly the
shape the offline queue produces when it drains on reconnect.

Scoped via path prefixes — non-mutation paths and endpoints where replay
semantics are undesired (e.g. anything that shouldn't be idempotent) simply
aren't listed. This keeps the guarantee opt-in and auditable.

Retention: a TTL index on `created_at` with a 72h lifetime. Long enough for a
weekend of spotty wifi; short enough that the collection doesn't grow.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import Request, Response
from pymongo.errors import DuplicateKeyError
from starlette.middleware.base import BaseHTTPMiddleware

from beats.api.errors import envelope as error_envelope
from beats.infrastructure.database import Database

logger = logging.getLogger(__name__)

# Only mutation endpoints that the offline queue may replay are guarded here.
# Add to this list as more write paths gain offline support.
IDEMPOTENT_PATH_PREFIXES: tuple[str, ...] = (
    "/api/projects/",  # covers /{id}/start and /stop (narrow match below)
)

# Within the prefix, require one of these suffixes to opt in. Keeps CRUD paths
# like GET /api/projects/{id} out of the cache.
IDEMPOTENT_PATH_SUFFIXES: tuple[str, ...] = ("/start", "/stop")

_MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_TTL_SECONDS = 72 * 60 * 60  # 72 hours

# How long a reservation may sit unfinished before another request may claim it.
# Only reached when the process holding it died between reserving and recording,
# which would otherwise wedge that client id until the TTL expired it.
_RESERVATION_STALE_SECONDS = 60


def _is_idempotent_path(path: str) -> bool:
    if not any(path.startswith(prefix) for prefix in IDEMPOTENT_PATH_PREFIXES):
        return False
    return any(path.endswith(suffix) for suffix in IDEMPOTENT_PATH_SUFFIXES)


async def ensure_mutation_log_indexes() -> None:
    """Create the TTL + uniqueness indexes on `mutation_log` once per boot."""
    db = Database.get_db()
    await db.mutation_log.create_index(
        [("user_id", 1), ("client_id", 1)],
        unique=True,
        name="uniq_user_client",
    )
    await db.mutation_log.create_index(
        "created_at",
        expireAfterSeconds=_TTL_SECONDS,
        name="ttl_created_at",
    )


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Must be installed inside (after) the authentication middleware so that
    `request.state.user_id` is already set when we consult it."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method not in _MUTATION_METHODS:
            return await call_next(request)

        if not _is_idempotent_path(request.url.path):
            return await call_next(request)

        client_id = request.headers.get("X-Client-Id")
        if not client_id:
            # Back-compat: clients that haven't adopted the queue don't pay
            # for a Mongo round-trip.
            return await call_next(request)

        user_id = getattr(request.state, "user_id", None)
        if not user_id:
            # Unauthenticated — the auth middleware will reject before this,
            # but be defensive.
            return await call_next(request)

        collection = Database.get_db().mutation_log
        key = {"user_id": user_id, "client_id": client_id}

        if not await _reserve(collection, key):
            return await _answer_from_reservation(collection, key, request.url.path)

        try:
            response = await call_next(request)
        except Exception:
            await collection.delete_one(key)
            raise

        if not (200 <= response.status_code < 300):
            # Release, so the user can correct the request and retry with the
            # same client id.
            await collection.delete_one(key)
            return response

        # Drain the streaming body so we can both persist AND return it.
        body_chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            body_chunks.append(chunk)
        body = b"".join(body_chunks)

        await collection.update_one(
            key,
            {
                "$set": {
                    "completed": True,
                    "status_code": response.status_code,
                    "body": body,
                    "media_type": response.headers.get("content-type", "application/json"),
                    "created_at": datetime.now(UTC),
                }
            },
        )

        return Response(
            content=body,
            status_code=response.status_code,
            media_type=response.headers.get("content-type"),
            headers={
                k: v
                for k, v in response.headers.items()
                if k.lower() not in {"content-length", "content-type"}
            },
        )


async def _reserve(collection: Any, key: dict[str, str]) -> bool:
    """Claim `(user_id, client_id)` for this request.

    Returns False when another request already holds it and is either still
    running or has already recorded its response.
    """
    now = datetime.now(UTC)
    try:
        await collection.insert_one({**key, "completed": False, "created_at": now})
        return True
    except DuplicateKeyError:
        pass

    stale_before = now - timedelta(seconds=_RESERVATION_STALE_SECONDS)
    claimed = await collection.update_one(
        {**key, "completed": False, "created_at": {"$lt": stale_before}},
        {"$set": {"created_at": now}},
    )
    if claimed.modified_count == 1:
        logger.warning("Claimed abandoned idempotency reservation for %s", key)
        return True
    return False


async def _answer_from_reservation(collection: Any, key: dict[str, str], path: str) -> Response:
    """Replay a recorded response, or report that one is still being produced."""
    existing = await collection.find_one(key)

    if existing is not None and existing.get("completed"):
        logger.info("Idempotent replay for %s path=%s", key, path)
        return Response(
            content=existing.get("body", b""),
            status_code=existing.get("status_code", 200),
            media_type=existing.get("media_type") or "application/json",
            headers={"X-Idempotent-Replay": "true"},
        )

    # Reserved but not finished — the same mutation is in flight. Executing it
    # here is the double-apply this middleware exists to prevent.
    logger.info("Idempotent request still in flight for %s path=%s", key, path)
    return error_envelope(
        status_code=409,
        detail="An identical request is already being processed.",
        code="IDEMPOTENT_IN_PROGRESS",
    )
