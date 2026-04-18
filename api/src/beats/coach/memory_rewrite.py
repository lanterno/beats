"""Memory rewrite — coach rewrites its own memory from recent data.

Triggered manually via POST /coach/memory/rewrite or (later) by a weekly
scheduler. Reads the last 7 days of sessions, intentions, reviews, mood,
and the current memory file, then asks the coach to produce an updated
Markdown summary.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from beats.coach.context import build_coach_messages
from beats.coach.gateway import complete
from beats.coach.memory import MemoryStore
from beats.coach.prompts import MEMORY_REWRITE_PROMPT
from beats.coach.repos import build_repos, fmt_minutes
from beats.coach.review import list_reviews
from beats.infrastructure.database import Database


async def _recent_data_summary(user_id: str) -> str:
    """Build a textual summary of the last 7 days for the rewrite prompt."""
    project_repo, beat_repo, intention_repo, note_repo, _ = await build_repos(user_id)
    project_map = {p.id: p.name for p in await project_repo.list()}

    today = datetime.now(UTC).date()
    week_ago = today - timedelta(days=7)

    beats = await beat_repo.list_all_completed()
    recent = [b for b in beats if b.day >= week_ago]

    # Per-day summary
    by_day: dict[date, list[str]] = {}
    for b in sorted(recent, key=lambda b: b.start):
        name = project_map.get(b.project_id, "?")
        dur = fmt_minutes(b.duration.total_seconds() / 60)
        by_day.setdefault(b.day, []).append(f"{name} ({dur})")

    lines = ["## Last 7 days of sessions"]
    for d in sorted(by_day.keys()):
        total = sum(b.duration.total_seconds() / 3600 for b in recent if b.day == d)
        lines.append(f"**{d.isoformat()}** ({total:.1f}h): {', '.join(by_day[d])}")
    if not by_day:
        lines.append("(No sessions in the last 7 days)")

    # Intentions
    lines.append("\n## Recent intentions")
    for offset in range(7):
        d = today - timedelta(days=offset)
        intentions = await intention_repo.list_by_date(d)
        if intentions:
            items = []
            for i in intentions:
                name = project_map.get(i.project_id, "?")
                status = "done" if i.completed else "missed"
                items.append(f"{name} {i.planned_minutes}m [{status}]")
            lines.append(f"**{d.isoformat()}**: {', '.join(items)}")

    # Mood
    lines.append("\n## Mood")
    for offset in range(7):
        d = today - timedelta(days=offset)
        note = await note_repo.get_by_date(d)
        if note and note.mood:
            text = f' — "{note.note[:80]}"' if note.note else ""
            lines.append(f"**{d.isoformat()}**: {note.mood}/5{text}")

    # Reviews
    reviews = await list_reviews(user_id, limit=7)
    if reviews:
        lines.append("\n## Review answers")
        for r in reviews:
            answers = r.get("answers", [])
            answered = [a for a in answers if a]
            if answered:
                lines.append(f"**{r['date']}**:")
                for a in answered:
                    lines.append(f"  - {a['text'][:150]}")

    return "\n".join(lines)


async def rewrite_coach_memory(user_id: str) -> str:
    """Rewrite the coach memory from the last 7 days of data."""

    recent = await _recent_data_summary(user_id)
    prompt = f"{recent}\n\n---\n\n{MEMORY_REWRITE_PROMPT}"

    system, messages, spec = await build_coach_messages(user_id, prompt)

    result = await complete(
        user_id=user_id,
        system=system,
        messages=messages,
        cache_spec=spec,
        temperature=0.3,
        max_tokens=2048,
        purpose="memory_rewrite",
    )

    content = ""
    for block in result.content:
        if hasattr(block, "text"):
            content += block.text

    content = content.strip()

    db = Database.get_db()
    store = MemoryStore(db, user_id)
    await store.write(content)

    return content
