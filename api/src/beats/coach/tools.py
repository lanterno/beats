"""Coach tool definitions and implementations.

Each tool is a Python async function that the chat loop calls when the LLM
requests it. Tool schemas are Anthropic-format JSON for the `tools` parameter.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from beats.coach.repos import build_repos, fmt_minutes
from beats.domain.intelligence import IntelligenceService

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_projects",
        "description": "List the user's projects with weekly goals and status.",
        "input_schema": {
            "type": "object",
            "properties": {
                "include_archived": {
                    "type": "boolean",
                    "description": "Include archived projects. Default false.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_beats",
        "description": (
            "Get work sessions (beats) for a date range. "
            "Returns project name, start/end times, duration, notes, tags."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "start_date": {
                    "type": "string",
                    "description": "ISO date (YYYY-MM-DD). Defaults to 7 days ago.",
                },
                "end_date": {
                    "type": "string",
                    "description": "ISO date (YYYY-MM-DD). Defaults to today.",
                },
                "project_name": {
                    "type": "string",
                    "description": "Filter by project name (case-insensitive).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_productivity_score",
        "description": (
            "Get the current productivity score (0–100) with component breakdown: "
            "consistency, intention completion, goal progress, session quality."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_intentions",
        "description": "Get daily intentions for a specific date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {
                    "type": "string",
                    "description": "ISO date (YYYY-MM-DD). Defaults to today.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "get_patterns",
        "description": (
            "Get detected productivity patterns: day patterns, peak hours, "
            "stale projects, mood correlation, session trends."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "search_beats",
        "description": "Search sessions by note text or tags.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Text to search in notes and tags.",
                },
            },
            "required": ["query"],
        },
    },
]


class _ToolContext:
    """Shared state for a single tool execution round."""

    __slots__ = (
        "project_repo",
        "beat_repo",
        "intention_repo",
        "note_repo",
        "digest_repo",
        "projects",
        "project_map",
    )

    def __init__(self, repos, projects):
        (
            self.project_repo,
            self.beat_repo,
            self.intention_repo,
            self.note_repo,
            self.digest_repo,
        ) = repos
        self.projects = projects
        self.project_map = {p.id: p.name for p in projects}

    def _build_intel(self):
        return IntelligenceService(
            beat_repo=self.beat_repo,
            project_repo=self.project_repo,
            intention_repo=self.intention_repo,
            daily_note_repo=self.note_repo,
        )


async def _handle_get_projects(ctx: _ToolContext, tool_input: dict) -> str:
    include_archived = tool_input.get("include_archived", False)
    filtered = ctx.projects if include_archived else [p for p in ctx.projects if not p.archived]
    lines = []
    for p in filtered:
        goal = f" (goal: {p.weekly_goal}h/wk {p.goal_type})" if p.weekly_goal else ""
        status = " [archived]" if p.archived else ""
        lines.append(f"- {p.name}{goal}{status}")
    return "\n".join(lines) if lines else "No projects found."


async def _handle_get_beats(ctx: _ToolContext, tool_input: dict) -> str:
    today = datetime.now(UTC).date()
    start_str = tool_input.get("start_date")
    end_str = tool_input.get("end_date")
    start_d = date.fromisoformat(start_str) if start_str else today - timedelta(days=7)
    end_d = date.fromisoformat(end_str) if end_str else today

    beats = await ctx.beat_repo.list_all_completed()
    filtered = [b for b in beats if start_d <= b.day <= end_d]

    proj_filter = tool_input.get("project_name", "").lower()
    if proj_filter:
        filtered = [
            b for b in filtered if ctx.project_map.get(b.project_id, "").lower() == proj_filter
        ]

    filtered.sort(key=lambda b: b.start)
    lines = []
    for b in filtered[:50]:
        name = ctx.project_map.get(b.project_id, "?")
        dur = fmt_minutes(b.duration.total_seconds() / 60)
        note = f" — {b.note}" if b.note else ""
        lines.append(f"{b.day.isoformat()} {b.start.strftime('%H:%M')} | {name} | {dur}{note}")

    total_h = sum(b.duration.total_seconds() / 3600 for b in filtered)
    summary = f"\n{len(filtered)} sessions, {total_h:.1f}h total."
    return ("\n".join(lines) + summary) if lines else "No sessions found."


async def _handle_get_productivity_score(ctx: _ToolContext, _tool_input: dict) -> str:
    intel = ctx._build_intel()
    try:
        score = await intel.compute_productivity_score()
        c = score["components"]
        return (
            f"Score: {score['score']}/100\n"
            f"  Consistency: {c['consistency']}\n"
            f"  Intentions: {c['intentions']}\n"
            f"  Goals: {c['goals']}\n"
            f"  Quality: {c['quality']}"
        )
    except Exception as exc:
        return f"Could not compute score: {exc}"


async def _handle_get_intentions(ctx: _ToolContext, tool_input: dict) -> str:
    date_str = tool_input.get("date")
    target = date.fromisoformat(date_str) if date_str else datetime.now(UTC).date()
    intentions = await ctx.intention_repo.list_by_date(target)
    if not intentions:
        return f"No intentions set for {target.isoformat()}."
    lines = []
    for i in intentions:
        name = ctx.project_map.get(i.project_id, "?")
        status = "done" if i.completed else "pending"
        lines.append(f"- {name}: {i.planned_minutes}min [{status}]")
    return "\n".join(lines)


async def _handle_get_patterns(ctx: _ToolContext, _tool_input: dict) -> str:
    intel = ctx._build_intel()
    try:
        patterns = await intel.detect_patterns()
        if not patterns:
            return "No patterns detected yet."
        lines = []
        for p in patterns[:10]:
            lines.append(f"**{p.title}** ({p.type})\n  {p.body}")
        return "\n\n".join(lines)
    except Exception as exc:
        return f"Pattern detection failed: {exc}"


async def _handle_search_beats(ctx: _ToolContext, tool_input: dict) -> str:
    query = tool_input.get("query", "").lower()
    if not query:
        return "No search query provided."
    beats = await ctx.beat_repo.list_all_completed()
    matched = [
        b
        for b in beats
        if (b.note and query in b.note.lower()) or any(query in t.lower() for t in (b.tags or []))
    ]
    matched.sort(key=lambda b: b.start, reverse=True)
    lines = []
    for b in matched[:20]:
        name = ctx.project_map.get(b.project_id, "?")
        dur = fmt_minutes(b.duration.total_seconds() / 60)
        note = f" — {b.note}" if b.note else ""
        lines.append(f"{b.day.isoformat()} | {name} | {dur}{note}")
    return "\n".join(lines) if lines else f"No sessions matching '{query}'."


_TOOL_HANDLERS = {
    "get_projects": _handle_get_projects,
    "get_beats": _handle_get_beats,
    "get_productivity_score": _handle_get_productivity_score,
    "get_intentions": _handle_get_intentions,
    "get_patterns": _handle_get_patterns,
    "search_beats": _handle_search_beats,
}


async def execute_tool(user_id: str, tool_name: str, tool_input: dict) -> str:
    """Execute a tool and return the result as a string for the LLM."""
    repos = await build_repos(user_id)
    projects = await repos[0].list()
    ctx = _ToolContext(repos, projects)

    handler = _TOOL_HANDLERS.get(tool_name)
    if handler:
        return await handler(ctx, tool_input)
    return f"Unknown tool: {tool_name}"
