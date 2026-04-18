"""Socratic end-of-day review.

Generates 3 targeted questions from the day's actual data, then persists the
user's answers. Answers feed forward into the next day's UserContextBlock and
into the weekly memory rewrite.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime

from beats.coach.context import build_coach_messages
from beats.coach.gateway import complete
from beats.coach.prompts import REVIEW_PROMPT
from beats.infrastructure.database import Database

logger = logging.getLogger(__name__)

REVIEWS_COLLECTION = "review_answers"


async def generate_review_questions(user_id: str, target_date: date | None = None) -> list[dict]:
    """Generate 3 review questions from the day's data. Returns list of
    {question, derived_from: {kind, data}}.
    """
    today = target_date or datetime.now(UTC).date()
    prompt = REVIEW_PROMPT.format(today=today.isoformat())
    system, messages, spec = await build_coach_messages(user_id, prompt, target_date=today)

    result = await complete(
        user_id=user_id,
        system=system,
        messages=messages,
        cache_spec=spec,
        temperature=0.4,
        max_tokens=1024,
        purpose="review",
    )

    text = ""
    for block in result.content:
        if hasattr(block, "text"):
            text += block.text

    try:
        questions = json.loads(text.strip())
        if not isinstance(questions, list):
            questions = []
    except json.JSONDecodeError, ValueError:
        logger.warning("Failed to parse review questions: %s", text[:200])
        questions = [
            {
                "question": "What was the most meaningful thing you worked on today?",
                "derived_from": {"kind": "fallback", "data": {}},
            },
            {
                "question": "Did today go as planned? What shifted?",
                "derived_from": {"kind": "fallback", "data": {}},
            },
            {
                "question": "What's one thing you'd do differently tomorrow?",
                "derived_from": {"kind": "fallback", "data": {}},
            },
        ]

    db = Database.get_db()
    await db[REVIEWS_COLLECTION].update_one(
        {"user_id": user_id, "date": today.isoformat()},
        {
            "$set": {
                "user_id": user_id,
                "date": today.isoformat(),
                "questions": questions,
                "updated_at": datetime.now(UTC),
            },
            "$setOnInsert": {"created_at": datetime.now(UTC), "answers": []},
        },
        upsert=True,
    )

    return questions


async def save_answer(
    user_id: str,
    target_date: date,
    question_index: int,
    answer: str,
) -> None:
    """Persist a single answer for a review question."""
    db = Database.get_db()
    doc = await db[REVIEWS_COLLECTION].find_one(
        {"user_id": user_id, "date": target_date.isoformat()}
    )
    if not doc:
        return

    answers = doc.get("answers", [])
    while len(answers) <= question_index:
        answers.append(None)
    answers[question_index] = {
        "text": answer,
        "answered_at": datetime.now(UTC).isoformat(),
    }

    await db[REVIEWS_COLLECTION].update_one(
        {"_id": doc["_id"]},
        {"$set": {"answers": answers, "updated_at": datetime.now(UTC)}},
    )


async def get_review(user_id: str, target_date: date | None = None) -> dict | None:
    today = target_date or datetime.now(UTC).date()
    db = Database.get_db()
    return await db[REVIEWS_COLLECTION].find_one(
        {"user_id": user_id, "date": today.isoformat()},
        {"_id": 0},
    )


async def list_reviews(user_id: str, limit: int = 14) -> list[dict]:
    db = Database.get_db()
    cursor = (
        db[REVIEWS_COLLECTION].find({"user_id": user_id}, {"_id": 0}).sort("date", -1).limit(limit)
    )
    return await cursor.to_list(limit)
