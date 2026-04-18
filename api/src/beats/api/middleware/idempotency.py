"""Idempotency middleware — de-dupes replayed mutations via a client-id cache.

The offline mutation queue in the UI (Stage 1.4) tags every write with a
`X-Client-Id` UUID. When the client retries a write after a network failure,
the same id arrives again. This middleware keeps the user from being charged
twice for the same action:

  1. Lookup `(user_id, client_id)` in `mutation_log`.
  2. If present, replay the stored response body and mark it `X-Idempotent-Replay`.
  3. Else, let the handler run; on a 2xx response, buffer the body and record it.

Scoped via path prefixes — non-mutation paths and endpoints where replay
semantics are undesired (e.g. anything that shouldn't be idempotent) simply
aren't listed. This keeps the guarantee opt-in and auditable.

Retention: a TTL index on `created_at` with a 72h lifetime. Long enough for a
weekend of spotty wifi; short enough that the collection doesn't grow.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

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

        db = Database.get_db()
        collection = db.mutation_log

        existing = await collection.find_one(
            {"user_id": user_id, "client_id": client_id},
        )
        if existing is not None:
            logger.info(
                "Idempotent replay for user=%s client_id=%s path=%s",
                user_id,
                client_id,
                request.url.path,
            )
            return Response(
                content=existing.get("body", b""),
                status_code=existing.get("status_code", 200),
                media_type=existing.get("media_type") or "application/json",
                headers={"X-Idempotent-Replay": "true"},
            )

        response = await call_next(request)

        if 200 <= response.status_code < 300:
            # Drain the streaming body so we can both persist AND return it.
            body_chunks: list[bytes] = []
            async for chunk in response.body_iterator:
                body_chunks.append(chunk)
            body = b"".join(body_chunks)

            try:
                await collection.insert_one(
                    {
                        "user_id": user_id,
                        "client_id": client_id,
                        "status_code": response.status_code,
                        "body": body,
                        "media_type": response.headers.get("content-type", "application/json"),
                        "created_at": datetime.now(UTC),
                    },
                )
            except Exception:  # noqa: BLE001
                # Duplicate-key races or transient storage errors must never
                # block a successful write. Log and move on — the client may
                # double-apply on the next retry, which is rare enough.
                logger.warning(
                    "mutation_log insert failed for user=%s client_id=%s",
                    user_id,
                    client_id,
                    exc_info=True,
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

        return response
