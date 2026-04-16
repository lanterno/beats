"""Coach API router — briefs, chat, reviews, usage, and memory."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from beats.api.dependencies import CurrentUserId
from beats.coach.brief import generate_brief, get_brief, list_briefs
from beats.coach.usage import BudgetExceeded, UsageTracker
from beats.settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/coach", tags=["coach"])


# ── Schemas ──────────────────────────────────────────────────────────


class BriefResponse(BaseModel):
    date: str
    body: str
    model: str | None = None
    cost_usd: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_read: int | None = None
    created_at: datetime | None = None


class GenerateBriefRequest(BaseModel):
    date: str | None = None


class UsageDayResponse(BaseModel):
    date: str
    cost_usd: float
    input_tokens: int
    output_tokens: int
    cache_read: int
    cache_creation: int
    calls: int


class UsageSummaryResponse(BaseModel):
    days: list[UsageDayResponse]
    month_total_usd: float
    budget_usd: float


class ChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


class ChatMessageResponse(BaseModel):
    role: str
    content: str
    tool_calls: list[dict] | None = None
    created_at: datetime


# ── Briefs ───────────────────────────────────────────────────────────


@router.get("/brief/today", response_model=BriefResponse | None)
async def get_today_brief(user_id: CurrentUserId):
    """Get today's brief if it exists."""
    doc = await get_brief(user_id)
    if not doc:
        return None
    return BriefResponse(**doc)


@router.get("/brief/history", response_model=list[BriefResponse])
async def get_brief_history(
    user_id: CurrentUserId,
    limit: int = Query(default=14, ge=1, le=60),
):
    """List recent briefs, newest first."""
    docs = await list_briefs(user_id, limit=limit)
    return [BriefResponse(**d) for d in docs]


@router.post("/brief/generate", response_model=BriefResponse)
async def trigger_brief_generation(
    user_id: CurrentUserId,
    request: GenerateBriefRequest | None = None,
):
    """Generate (or regenerate) a daily brief. Defaults to today."""
    target = None
    if request and request.date:
        try:
            target = date.fromisoformat(request.date)
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"Invalid date: {request.date}"
            ) from exc

    try:
        doc = await generate_brief(user_id, target_date=target)
    except BudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Brief generation failed for user=%s", user_id)
        raise HTTPException(
            status_code=502,
            detail="Brief generation failed — the coach is resting.",
        ) from exc

    return BriefResponse(**doc)


# ── Chat ─────────────────────────────────────────────────────────────


@router.post("/chat")
async def coach_chat(
    user_id: CurrentUserId,
    request: ChatRequest,
):
    """Streaming chat with tool use. Returns SSE."""
    from beats.coach.chat import handle_chat_turn

    try:
        event_stream = handle_chat_turn(
            user_id=user_id,
            message=request.message,
            conversation_id=request.conversation_id,
        )

        async def sse_generator():
            async for event in event_stream:
                yield f"data: {json.dumps(event)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(
            sse_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except BudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


# ── Chat history ─────────────────────────────────────────────────────


@router.get("/chat/history")
async def get_chat_history(
    user_id: CurrentUserId,
    conversation_id: Annotated[str | None, Query()] = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    """Get chat message history for a conversation."""
    from beats.infrastructure.database import Database

    db = Database.get_db()
    query: dict = {"user_id": user_id}
    if conversation_id:
        query["conversation_id"] = conversation_id

    cursor = (
        db.coach_conversations.find(query, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    messages = await cursor.to_list(limit)
    messages.reverse()
    return messages


# ── Usage ────────────────────────────────────────────────────────────


@router.get("/usage", response_model=UsageSummaryResponse)
async def get_usage(
    user_id: CurrentUserId,
    days: int = Query(default=30, ge=1, le=90),
):
    """Usage breakdown for the cost dashboard."""
    tracker = UsageTracker(user_id)
    daily = await tracker.usage_summary(days=days)
    month_total = await tracker.month_spend()

    return UsageSummaryResponse(
        days=[
            UsageDayResponse(
                date=d["_id"],
                cost_usd=d["cost_usd"],
                input_tokens=d["input_tokens"],
                output_tokens=d["output_tokens"],
                cache_read=d["cache_read"],
                cache_creation=d["cache_creation"],
                calls=d["calls"],
            )
            for d in daily
        ],
        month_total_usd=month_total,
        budget_usd=settings.coach_monthly_budget_usd,
    )
