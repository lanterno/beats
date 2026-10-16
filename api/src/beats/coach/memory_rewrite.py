"""Memory rewrite — coach rewrites its own memory from recent data.

Triggered manually via POST /coach/memory/rewrite or (later) by a weekly
scheduler. Reads the last 7 days of sessions and the current memory file,
then asks the coach to produce an updated Markdown summary.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from anthropic.types import TextBlock

from beats.coach.context import UTC_TZ, build_coach_messages
from beats.coach.gateway import complete
from beats.coach.memory import MemoryStore
from beats.coach.prompts import MEMORY_REWRITE_PROMPT
from beats.coach.repos import build_repos, fmt_minutes
from beats.domain.utils import local_date
from beats.infrastructure.database import Database


async def _recent_data_summary(user_id: str, tz: ZoneInfo = UTC_TZ) -> str:
    """Build a textual summary of the last 7 days for the rewrite prompt.

    The days are the user's in ``tz``, as the rest of the coach's are: a
    session is filed under the local date it started on, and the seven days
    end on the user's today.
    """
    repos = await build_repos(user_id)
    project_map = {p.id: p.name for p in await repos.project.list()}

    today = datetime.now(tz).date()
    week_ago = today - timedelta(days=7)

    beats = await repos.beat.list_all_completed()
    dated = ((local_date(b.start, tz), b) for b in beats)
    recent = [(d, b) for d, b in dated if d >= week_ago]

    # Per-day summary
    by_day: dict[date, list[str]] = {}
    hours: dict[date, float] = {}
    for d, b in sorted(recent, key=lambda pair: pair[1].start):
        name = project_map.get(b.project_id, "?")
        dur = fmt_minutes(b.duration.total_seconds() / 60)
        by_day.setdefault(d, []).append(f"{name} ({dur})")
        hours[d] = hours.get(d, 0.0) + b.duration.total_seconds() / 3600

    lines = ["## Last 7 days of sessions"]
    for d in sorted(by_day.keys()):
        total = hours[d]
        lines.append(f"**{d.isoformat()}** ({total:.1f}h): {', '.join(by_day[d])}")
    if not by_day:
        lines.append("(No sessions in the last 7 days)")

    return "\n".join(lines)


async def rewrite_coach_memory(user_id: str, tz: ZoneInfo = UTC_TZ) -> str:
    """Rewrite the coach memory from the last 7 days of data.

    ``tz`` is the user's timezone: the last seven days of sessions are its
    days, and the day context the rewrite reads names the user's today and
    each day job's contract week in it, as the brief's does.
    """

    recent = await _recent_data_summary(user_id, tz)
    prompt = f"{recent}\n\n---\n\n{MEMORY_REWRITE_PROMPT}"

    system, messages, spec = await build_coach_messages(user_id, prompt, tz=tz)

    result = await complete(
        user_id=user_id,
        system=system,
        messages=messages,
        cache_spec=spec,
        max_tokens=2048,
        purpose="memory_rewrite",
    )

    content = ""
    for block in result.content:
        if isinstance(block, TextBlock):
            content += block.text

    content = content.strip()

    db = Database.get_db()
    store = MemoryStore(db, user_id)
    await store.write(content)

    return content
