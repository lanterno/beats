"""Webhooks API router — CRUD and dispatch for timer event webhooks."""

import asyncio
import http
import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

import httpx
from fastapi import APIRouter, Query
from pydantic import BaseModel

from beats.api.dependencies import (
    BeatServiceDep,
    DailyNoteRepoDep,
    IntentionRepoDep,
    ProjectServiceDep,
    WebhookRepoDep,
)

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


@router.post("/daily-summary/trigger")
async def trigger_daily_summary(
    webhook_repo: WebhookRepoDep,
    beat_service: BeatServiceDep,
    project_service: ProjectServiceDep,
    intention_repo: IntentionRepoDep,
    daily_note_repo: DailyNoteRepoDep,
    target_date: date = Query(default_factory=date.today),
):
    """Trigger a daily summary webhook for a given date (defaults to today)."""
    beats = await beat_service.list_beats(date_filter=target_date)
    completed = [b for b in beats if b.end is not None]

    # Project breakdown
    by_project: dict[str, timedelta] = defaultdict(timedelta)
    for b in completed:
        by_project[b.project_id] += b.duration

    projects = await project_service.list_projects()
    project_map = {p.id: p.name for p in projects}

    breakdown = [
        {
            "project_id": pid,
            "project_name": project_map.get(pid, "Unknown"),
            "minutes": round(dur.total_seconds() / 60),
        }
        for pid, dur in sorted(by_project.items(), key=lambda x: -x[1].total_seconds())
    ]

    total_minutes = sum(item["minutes"] for item in breakdown)

    # Intentions
    intentions = await intention_repo.list_by_date(target_date)
    intentions_data = [
        {"project_id": i.project_id, "planned_minutes": i.planned_minutes, "completed": i.completed}
        for i in intentions
    ]

    # Daily note
    daily_note = await daily_note_repo.get_by_date(target_date)

    payload = {
        "date": target_date.isoformat(),
        "total_minutes": total_minutes,
        "session_count": len(completed),
        "project_breakdown": breakdown,
        "intentions": intentions_data,
        "daily_note": daily_note.note if daily_note else None,
        "mood": daily_note.mood if daily_note else None,
    }

    await dispatch_webhook_event("daily.summary", payload, webhook_repo)
    return payload


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
