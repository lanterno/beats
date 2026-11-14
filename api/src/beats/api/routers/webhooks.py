"""Webhooks API router — CRUD and dispatch for timer event webhooks."""

import asyncio
import http
import logging
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from beats import platform_controls
from beats.api.dependencies import (
    CurrentUserId,
    WebhookRepoDep,
)
from beats.auth import account_access
from beats.domain.models import Webhook
from beats.infrastructure.database import Database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


class CreateWebhookRequest(BaseModel):
    url: str
    events: list[str] = ["timer.start", "timer.stop"]


class WebhookResponse(BaseModel):
    id: str
    url: str
    events: list[str]
    active: bool
    created_at: datetime


async def _webhooks_disabled(user_id: str) -> bool:
    """The operator's per-account switch (`account_limits`): outbound HTTP
    from our servers to arbitrary URLs is ours to answer for. On the account,
    not the webhook, so deleting and re-creating one gets around nothing;
    `Webhook.active` stays what it is, the owner's own flag."""
    access = await account_access.resolve(Database.get_db(), user_id)
    return access.webhooks_disabled


@router.get("/", response_model=list[WebhookResponse])
async def list_webhooks(repo: WebhookRepoDep):
    """List all registered webhooks."""
    webhooks = await repo.list_all()
    return [w.model_dump(mode="json") for w in webhooks]


@router.post("/", status_code=http.HTTPStatus.CREATED, response_model=WebhookResponse)
async def create_webhook(
    request: CreateWebhookRequest, user_id: CurrentUserId, repo: WebhookRepoDep
):
    """Register a new webhook URL."""
    if await _webhooks_disabled(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "WEBHOOKS_DISABLED",
                "message": "Webhooks are disabled on this account.",
            },
        )
    webhook = Webhook(url=request.url, events=request.events)
    created = await repo.create(webhook)
    return created.model_dump(mode="json")


@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str, repo: WebhookRepoDep):
    """Delete a webhook by ID."""
    deleted = await repo.delete(webhook_id)
    return {"deleted": deleted}


# Module-level set holding strong references to in-flight webhook
# dispatch tasks. asyncio.create_task only stores a weak reference
# internally — without keeping a strong ref somewhere, Python's GC
# can reap the task mid-execution and the webhook silently never
# fires. The standard pattern (per the asyncio.create_task docs)
# is to track tasks in a set and discard on completion.
_pending_dispatches: set[asyncio.Task] = set()


async def dispatch_webhook_event(
    event: str,
    payload: dict,
    repo: WebhookRepoDep,
    user_id: str,
) -> None:
    """Fire-and-forget webhook dispatch for a timer event.

    The docstring used to claim "fire-and-forget" but the function
    awaited the actual HTTP delivery — so a single slow webhook URL
    could block timer start/stop for up to 10s × N webhooks. Now
    truly fire-and-forget: the repo lookup is awaited (we need the
    webhook list before scheduling), but the HTTP POSTs run in
    detached background tasks. Callers return immediately to the
    user; webhook delivery happens out-of-band.
    """
    # The operator's switch is checked at dispatch too, not only at create:
    # a webhook registered before the switch was thrown must also fall
    # silent. Suspension can be undone; so can this.
    if await _webhooks_disabled(user_id):
        return
    # The operator's platform-wide pause drops too — there is no outbox to
    # hold a delivery — with one line per event so the loss can be counted
    # (docs/backoffice.md § Controls).
    if await platform_controls.webhooks_paused(Database.get_db()):
        logger.warning("WEBHOOKS_PAUSED_DROPPED event=%s account=%s", event, user_id)
        return
    webhooks = await repo.list_by_event(event)
    if not webhooks:
        return

    body = {
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(),
        "data": payload,
    }

    async def _send(url: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(url, json=body)
        except Exception:  # noqa: BLE001
            logger.warning("Webhook delivery failed for %s to %s", event, url)

    # Detach delivery so the request that triggered the dispatch
    # returns to the user without waiting on each webhook URL's
    # response. Pin task references in _pending_dispatches so the
    # GC doesn't reap them mid-flight — discard on done so the set
    # doesn't grow unboundedly.
    for w in webhooks:
        task = asyncio.create_task(_send(w.url))
        _pending_dispatches.add(task)
        task.add_done_callback(_pending_dispatches.discard)
