"""Webhooks API router — CRUD and dispatch for timer event webhooks."""

import asyncio
import http
import logging
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from beats.api.dependencies import WebhookRepoDep

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


@router.get("/", response_model=list[WebhookResponse])
async def list_webhooks(repo: WebhookRepoDep):
    """List all registered webhooks."""
    webhooks = await repo.list_all()
    return [w.model_dump(mode="json") for w in webhooks]


@router.post("/", status_code=http.HTTPStatus.CREATED, response_model=WebhookResponse)
async def create_webhook(request: CreateWebhookRequest, repo: WebhookRepoDep):
    """Register a new webhook URL."""
    from beats.domain.models import Webhook

    webhook = Webhook(url=request.url, events=request.events)
    created = await repo.create(webhook)
    return created.model_dump(mode="json")


@router.delete("/{webhook_id}")
async def delete_webhook(webhook_id: str, repo: WebhookRepoDep):
    """Delete a webhook by ID."""
    deleted = await repo.delete(webhook_id)
    return {"deleted": deleted}


async def dispatch_webhook_event(
    event: str,
    payload: dict,
    repo: WebhookRepoDep,
) -> None:
    """Fire-and-forget webhook dispatch for a timer event."""
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
        except Exception:
            logger.warning("Webhook delivery failed for %s to %s", event, url)

    tasks = [_send(w.url) for w in webhooks]
    await asyncio.gather(*tasks, return_exceptions=True)
