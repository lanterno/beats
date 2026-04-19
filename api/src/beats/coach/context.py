"""Context builders — assemble structured blocks for the coach's prompt.

Each block maps to a cache-control boundary:
  - SystemBlock: persona + tool schemas (~2k tokens, cached)
  - UserContextBlock: 30-day aggregates + memory (~3–5k tokens, cached nightly)
  - DayContextBlock: today's raw signals (~0.5–2k tokens, not cached)

The blocks are composed into messages by the brief/chat/review callers.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from beats.coach.memory import MemoryStore
from beats.coach.prompts import COACH_PERSONA
from beats.coach.repos import CoachRepos, build_repos, fmt_minutes
from beats.domain.intelligence import IntelligenceService
from beats.infrastructure.database import Database

if TYPE_CHECKING:
    from beats.coach.gateway import CacheSpec

logger = logging.getLogger(__name__)


def build_system_block() -> str:
    return COACH_PERSONA


async def build_user_context(user_id: str, repos: CoachRepos) -> str:
    """30-day aggregates + coach memory. Designed to be cached."""
    db = Database.get_db()

    projects = await repos.project.list()
    active = [p for p in projects if not p.archived]
    project_map = {p.id: p.name for p in projects}

    now = datetime.now(UTC)
    thirty_days_ago = now - timedelta(days=30)

    beats = await repos.beat.list_all_completed()
    recent_beats = [b for b in beats if b.start >= thirty_days_ago]

    # Per-project hours (last 30 days)
    project_hours: dict[str, float] = {}
    for b in recent_beats:
        name = project_map.get(b.project_id, "Unknown")
        project_hours[name] = project_hours.get(name, 0) + b.duration.total_seconds() / 3600

    # Weekly totals for the last 4 weeks
    week_totals: list[str] = []
    for w in range(4):
        start = now - timedelta(days=now.weekday() + 7 * (w + 1))
        end = start + timedelta(days=7)
        week_hours = sum(
            b.duration.total_seconds() / 3600 for b in recent_beats if start <= b.start < end
        )
        week_label = start.strftime("%b %d")
        week_totals.append(f"  Week of {week_label}: {week_hours:.1f}h")

    # Productivity score
    intel = IntelligenceService(
        beat_repo=repos.beat,
        project_repo=repos.project,
        intention_repo=repos.intention,
        daily_note_repo=repos.note,
    )
    try:
        score_data = await intel.compute_productivity_score()
        score_line = (
            f"Productivity score: {score_data['score']}/100 "
            f"(consistency={score_data['components']['consistency']}, "
            f"intentions={score_data['components']['intentions']}, "
            f"goals={score_data['components']['goals']}, "
            f"quality={score_data['components']['quality']})"
        )
    except Exception:
        logger.debug("Productivity score unavailable", exc_info=True)
        score_line = "Productivity score: unavailable"

    # Goals
    goals = []
    for p in active:
        if p.weekly_goal:
            goals.append(f"  {p.name}: {p.weekly_goal}h/week ({p.goal_type})")

    # Coach memory
    memory_store = MemoryStore(db, user_id)
    memory = await memory_store.read()
    memory_section = memory if memory else "(No coach memory yet — generated after first week.)"

    lines = [
        "## User profile (30-day window)",
        "",
        f"Active projects: {', '.join(p.name for p in active)}",
        "",
        "### Hours by project (last 30 days)",
        *[
            f"  {name}: {hours:.1f}h"
            for name, hours in sorted(project_hours.items(), key=lambda x: -x[1])
        ],
        "",
        "### Weekly totals",
        *week_totals,
        "",
        score_line,
        "",
        "### Weekly goals",
        *(goals if goals else ["  (No goals set)"]),
        "",
        "## Coach memory",
        memory_section,
    ]
    return "\n".join(lines)


async def build_day_context(
    user_id: str, repos: CoachRepos, target_date: date | None = None
) -> str:
    """Today's raw signals. Small and NOT cached."""
    project_map = {p.id: p.name for p in await repos.project.list()}

    today = target_date or datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)

    # Today's beats
    all_beats = await repos.beat.list_all_completed()
    today_beats = [b for b in all_beats if b.day == today]
    yesterday_beats = [b for b in all_beats if b.day == yesterday]

    def beats_summary(beats_list, label: str) -> list[str]:
        if not beats_list:
            return [f"  No sessions {label}."]
        lines = []
        for b in sorted(beats_list, key=lambda b: b.start):
            name = project_map.get(b.project_id, "?")
            dur = fmt_minutes(b.duration.total_seconds() / 60)
            time_str = b.start.strftime("%H:%M")
            note_suffix = f" [note: {b.note}]" if b.note else ""
            lines.append(f"  {time_str} — {name} ({dur}){note_suffix}")
        total = sum(b.duration.total_seconds() / 3600 for b in beats_list)
        lines.append(f"  Total: {total:.1f}h across {len(beats_list)} sessions")
        return lines

    # Intentions
    today_intentions = await repos.intention.list_by_date(today)
    intention_lines = []
    for i in today_intentions:
        name = project_map.get(i.project_id, "?")
        status = "done" if i.completed else "pending"
        intention_lines.append(f"  {name}: {i.planned_minutes}min [{status}]")

    # Yesterday's mood
    yesterday_note = await repos.note.get_by_date(yesterday)
    mood_line = ""
    if yesterday_note:
        mood = yesterday_note.mood
        note_text = yesterday_note.note
        note_part = f' — "{note_text[:100]}"' if note_text else ""
        mood_line = f"Yesterday's mood: {mood}/5{note_part}"

    # Calendar events (if connected)
    calendar_lines: list[str] = []
    try:
        db = Database.get_db()
        cal_doc = await db.calendar_integrations.find_one({"user_id": user_id, "enabled": True})
        if cal_doc:
            from beats.domain.calendar import CalendarService

            cal_service = CalendarService(cal_doc)
            events = await cal_service.get_events(
                datetime.combine(today, datetime.min.time()),
                datetime.combine(today, datetime.max.time()),
            )
            for ev in events[:5]:
                calendar_lines.append(f"  {ev['start'][:5]}–{ev['end'][:5]} {ev['summary']}")
    except Exception:
        logger.debug("Calendar fetch failed for day context", exc_info=True)

    lines = [
        f"## Today: {today.isoformat()} ({today.strftime('%A')})",
        "",
        "### Yesterday's sessions",
        *beats_summary(yesterday_beats, "yesterday"),
        "",
        *(["", mood_line, ""] if mood_line else [""]),
        "### Today's sessions so far",
        *beats_summary(today_beats, "today"),
        "",
        "### Today's intentions",
        *(intention_lines if intention_lines else ["  No intentions set for today."]),
    ]

    if calendar_lines:
        lines += ["", "### Calendar today", *calendar_lines]

    # Biometric data (if available)
    try:
        db = Database.get_db()
        yesterday_str = yesterday.isoformat()
        bio_doc = await db.biometric_days.find_one(
            {"user_id": user_id, "date": yesterday_str},
            sort=[("created_at", -1)],
        )
        if bio_doc:
            bio_lines = [""]
            if bio_doc.get("sleep_minutes"):
                efficiency = bio_doc.get("sleep_efficiency")
                eff_str = f" (efficiency {efficiency * 100:.0f}%)" if efficiency else ""
                bio_lines.append(f"  Sleep: {bio_doc['sleep_minutes'] / 60:.1f}h{eff_str}")
            if bio_doc.get("hrv_ms"):
                bio_lines.append(f"  HRV: {bio_doc['hrv_ms']:.0f}ms")
            if bio_doc.get("resting_hr_bpm"):
                bio_lines.append(f"  Resting HR: {bio_doc['resting_hr_bpm']} bpm")
            if bio_doc.get("readiness_score"):
                bio_lines.append(f"  Readiness: {bio_doc['readiness_score']}/100")
            if len(bio_lines) > 1:
                lines += ["", "### Last night's biometrics", *bio_lines]
    except Exception:
        logger.debug("Biometric fetch failed for day context", exc_info=True)

    return "\n".join(lines)


async def build_coach_messages(
    user_id: str,
    user_message: str,
    *,
    history: list[dict] | None = None,
    target_date: date | None = None,
) -> tuple[str, list[dict], CacheSpec]:
    """Build the full (system, messages, cache_spec) tuple for a coach call.

    Used by both brief.py and chat.py to avoid duplicating the context assembly.
    Returns (system, messages, cache_spec).
    """
    from beats.coach.gateway import CacheSpec

    repos = await build_repos(user_id)

    system = build_system_block()
    user_ctx = await build_user_context(user_id, repos)
    day_ctx = await build_day_context(user_id, repos, target_date)

    preamble = [
        {"role": "user", "content": user_ctx},
        {"role": "assistant", "content": "Context loaded."},
        {"role": "user", "content": day_ctx},
        {"role": "assistant", "content": "Ready."},
    ]

    messages = preamble + (history or []) + [{"role": "user", "content": user_message}]
    spec = CacheSpec(system_cached=True, cached_turn_indices=[0])

    return system, messages, spec
