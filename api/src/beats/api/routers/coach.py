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
from beats.coach.chat import handle_chat_turn
from beats.coach.memory import MemoryStore
from beats.coach.memory_rewrite import rewrite_coach_memory
from beats.coach.repos import (
    COACH_CONVERSATIONS_COLLECTION,
    COACH_MEMORY_COLLECTION,
    DAILY_BRIEFS_COLLECTION,
    LLM_USAGE_COLLECTION,
    REVIEW_ANSWERS_COLLECTION,
)
from beats.coach.review import generate_review_questions, get_review, save_answer
from beats.coach.usage import BudgetExceeded, UsageTracker
from beats.infrastructure.database import Database
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


class ReviewQuestionResponse(BaseModel):
    question: str
    derived_from: dict | None = None


class ReviewResponse(BaseModel):
    date: str
    questions: list[ReviewQuestionResponse]
    answers: list[dict | None] = []


class ReviewAnswerRequest(BaseModel):
    date: str
    question_index: int
    answer: str


class MemoryResponse(BaseModel):
    content: str | None = None
    updated_at: datetime | None = None


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
                status_code=400,
                detail={"code": "INVALID_DATE", "message": f"Invalid date: {request.date}"},
            ) from exc

    try:
        doc = await generate_brief(user_id, target_date=target)
    except BudgetExceeded as exc:
        # Distinct from the generic RATE_LIMITED — clients should surface
        # "monthly LLM budget reached", not "slow down your requests".
        raise HTTPException(
            status_code=429,
            detail={"code": "BUDGET_EXCEEDED", "message": str(exc)},
        ) from exc
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
    event_stream = handle_chat_turn(
        user_id=user_id,
        message=request.message,
        conversation_id=request.conversation_id,
    )

    async def sse_generator():
        try:
            async for event in event_stream:
                yield f"data: {json.dumps(event)}\n\n"
        except BudgetExceeded as exc:
            error = {"type": "error", "error": str(exc), "code": 429}
            yield f"data: {json.dumps(error)}\n\n"
        except Exception:
            logger.exception("Chat stream failed for user=%s", user_id)
            error = {"type": "error", "error": "Coach is temporarily unavailable.", "code": 502}
            yield f"data: {json.dumps(error)}\n\n"
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


# ── Chat history ─────────────────────────────────────────────────────


@router.get("/chat/history")
async def get_chat_history(
    user_id: CurrentUserId,
    conversation_id: Annotated[str | None, Query()] = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    """Get chat message history for a conversation."""
    db = Database.get_db()
    query: dict = {"user_id": user_id}
    if conversation_id:
        query["conversation_id"] = conversation_id

    cursor = (
        db[COACH_CONVERSATIONS_COLLECTION]
        .find(query, {"_id": 0})
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


# ── Reviews ──────────────────────────────────────────────────────────


@router.post("/review/start", response_model=ReviewResponse)
async def start_review(user_id: CurrentUserId):
    """Generate 3 end-of-day review questions from today's data."""
    try:
        await generate_review_questions(user_id)
    except BudgetExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail={"code": "BUDGET_EXCEEDED", "message": str(exc)},
        ) from exc
    except Exception as exc:
        logger.exception("Review generation failed for user=%s", user_id)
        raise HTTPException(
            status_code=502,
            detail="Review generation failed — the coach is resting.",
        ) from exc

    doc = await get_review(user_id)
    if not doc:
        raise HTTPException(status_code=500, detail="Review not found after generation")
    return ReviewResponse(
        date=doc["date"],
        questions=[ReviewQuestionResponse(**q) for q in doc.get("questions", [])],
        answers=doc.get("answers", []),
    )


@router.post("/review/answer")
async def answer_review(user_id: CurrentUserId, request: ReviewAnswerRequest):
    """Save an answer to a review question."""
    try:
        target = date.fromisoformat(request.date)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_DATE", "message": str(exc)},
        ) from exc

    await save_answer(user_id, target, request.question_index, request.answer)
    return {"status": "ok"}


@router.get("/review/today", response_model=ReviewResponse | None)
async def get_today_review(user_id: CurrentUserId):
    """Get today's review if it exists."""
    doc = await get_review(user_id)
    if not doc:
        return None
    return ReviewResponse(
        date=doc["date"],
        questions=[ReviewQuestionResponse(**q) for q in doc.get("questions", [])],
        answers=doc.get("answers", []),
    )


# ── Memory ───────────────────────────────────────────────────────────


@router.get("/memory", response_model=MemoryResponse)
async def get_memory(user_id: CurrentUserId):
    """Get the current coach memory for this user."""
    db = Database.get_db()
    store = MemoryStore(db, user_id)
    content = await store.read()
    doc = await db[COACH_MEMORY_COLLECTION].find_one({"user_id": user_id})
    return MemoryResponse(
        content=content,
        updated_at=doc.get("updated_at") if doc else None,
    )


@router.delete("/memory")
async def delete_memory(user_id: CurrentUserId):
    """Delete the coach memory for this user."""
    db = Database.get_db()
    await db[COACH_MEMORY_COLLECTION].delete_one({"user_id": user_id})
    return {"status": "ok"}


@router.delete("/data")
async def delete_all_coach_data(user_id: CurrentUserId):
    """Delete ALL coach data for this user: memory, briefs, reviews,
    conversations, and usage logs. Irreversible."""
    db = Database.get_db()
    for col_name in [
        COACH_MEMORY_COLLECTION,
        DAILY_BRIEFS_COLLECTION,
        REVIEW_ANSWERS_COLLECTION,
        COACH_CONVERSATIONS_COLLECTION,
        LLM_USAGE_COLLECTION,
    ]:
        await db[col_name].delete_many({"user_id": user_id})
    return {"status": "ok", "deleted": "all coach data"}


@router.post("/memory/rewrite", response_model=MemoryResponse)
async def rewrite_memory(user_id: CurrentUserId):
    """Trigger the coach to rewrite its memory from the last 7 days."""
    try:
        content = await rewrite_coach_memory(user_id)
    except BudgetExceeded as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Memory rewrite failed for user=%s", user_id)
        raise HTTPException(status_code=502, detail="Memory rewrite failed.") from exc

    return MemoryResponse(content=content)
