"""Coach tool definitions and implementations.

Each tool is a Python async function that the chat loop calls when the LLM
requests it. Tool schemas are Anthropic-format JSON for the `tools` parameter.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from beats.coach.repos import CoachRepos, build_repos, fmt_contract_goal, fmt_hours, fmt_minutes
from beats.domain.intelligence import IntelligenceService
from beats.domain.utils import local_date, local_dt

UTC_TZ = ZoneInfo("UTC")

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
            "consistency, goal progress, session quality."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_patterns",
        "description": (
            "Get detected productivity patterns: day patterns, peak hours, "
            "stale projects, session trends."
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

    def __init__(self, repos: CoachRepos, projects: list, tz: ZoneInfo) -> None:
        self.repos = repos
        self.projects = projects
        self.tz = tz
        self.project_map = {p.id: p.name for p in projects}

    def _build_intel(self):
        # With the contract reader, as the Inbox's service is built: the
        # pacing and stale-project cards get_patterns returns quote a
        # governed week's adjusted expectation, not the nominal term.
        return IntelligenceService(
            beat_repo=self.repos.beat,
            project_repo=self.repos.project,
            contracts=self.repos.contracts,
        )


async def _handle_get_projects(ctx: _ToolContext, tool_input: dict) -> str:
    include_archived = tool_input.get("include_archived", False)
    filtered = ctx.projects if include_archived else [p for p in ctx.projects if not p.archived]
    # This week in the request timezone, as the goal line and the day
    # context's contract week are, so the three name the same term.
    today = datetime.now(ctx.tz).date()
    monday = today - timedelta(days=today.weekday())
    lines = []
    for p in filtered:
        term = p.goal_term(monday)
        if term is not None:
            # A governing term of 0 hours is no goal, and hides the personal one.
            # The hours to the hundredth, as the page's term reads (`fmt_hours`).
            hours, _ = p.effective_goal(monday)
            goal = f" (goal: {fmt_hours(hours)}h/wk, {fmt_contract_goal(term)})" if hours else ""
        elif p.weekly_goal:
            goal = f" (goal: {p.weekly_goal}h/wk {p.goal_type})"
        else:
            goal = ""
        status = " [archived]" if p.archived else ""
        lines.append(f"- {p.name}{goal}{status}")
    return "\n".join(lines) if lines else "No projects found."


async def _handle_get_beats(ctx: _ToolContext, tool_input: dict) -> str:
    # The user's days, as the day context's: a session belongs to the local
    # date it started on and is listed at its local time, so the dates the
    # coach is asked about and the ones it answers with are the user's.
    today = datetime.now(ctx.tz).date()
    start_str = tool_input.get("start_date")
    end_str = tool_input.get("end_date")
    start_d = date.fromisoformat(start_str) if start_str else today - timedelta(days=7)
    end_d = date.fromisoformat(end_str) if end_str else today

    beats = await ctx.repos.beat.list_all_completed()
    filtered = [b for b in beats if start_d <= local_date(b.start, ctx.tz) <= end_d]

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
        start = local_dt(b.start, ctx.tz)
        lines.append(f"{start.date().isoformat()} {start.strftime('%H:%M')} | {name} | {dur}{note}")

    total_h = sum(b.duration.total_seconds() / 3600 for b in filtered)
    summary = f"\n{len(filtered)} sessions, {total_h:.1f}h total."
    return ("\n".join(lines) + summary) if lines else "No sessions found."


async def _handle_get_productivity_score(ctx: _ToolContext, _tool_input: dict) -> str:
    intel = ctx._build_intel()
    try:
        score = await intel.compute_productivity_score(tz=ctx.tz)
        c = score["components"]
        return (
            f"Score: {score['score']}/100\n"
            f"  Consistency: {c['consistency']}\n"
            f"  Goals: {c['goals']}\n"
            f"  Quality: {c['quality']}"
        )
    except Exception as exc:  # noqa: BLE001
        return f"Could not compute score: {exc}"


async def _handle_get_patterns(ctx: _ToolContext, _tool_input: dict) -> str:
    intel = ctx._build_intel()
    try:
        patterns = await intel.detect_patterns(tz=ctx.tz)
        if not patterns:
            return "No patterns detected yet."
        lines = []
        for p in patterns[:10]:
            lines.append(f"**{p.title}** ({p.type})\n  {p.body}")
        return "\n\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        return f"Pattern detection failed: {exc}"


async def _handle_search_beats(ctx: _ToolContext, tool_input: dict) -> str:
    query = tool_input.get("query", "").lower()
    if not query:
        return "No search query provided."
    beats = await ctx.repos.beat.list_all_completed()
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
        lines.append(f"{local_date(b.start, ctx.tz).isoformat()} | {name} | {dur}{note}")
    return "\n".join(lines) if lines else f"No sessions matching '{query}'."


_TOOL_HANDLERS = {
    "get_projects": _handle_get_projects,
    "get_beats": _handle_get_beats,
    "get_productivity_score": _handle_get_productivity_score,
    "get_patterns": _handle_get_patterns,
    "search_beats": _handle_search_beats,
}


async def execute_tool(
    user_id: str,
    tool_name: str,
    tool_input: dict,
    *,
    repos: CoachRepos | None = None,
    projects: list | None = None,
    tz: ZoneInfo = UTC_TZ,
) -> str:
    """Execute a tool and return the result as a string for the LLM.

    ``tz`` is the request's timezone, and every tool reads the user's days
    and weeks in it: `get_projects`' week, the dates `get_beats` takes and
    prints, and the score's and the patterns' weeks and days."""
    if repos is None:
        repos = await build_repos(user_id)
    if projects is None:
        projects = await repos.project.list()
    ctx = _ToolContext(repos, projects, tz)

    handler = _TOOL_HANDLERS.get(tool_name)
    if handler:
        return await handler(ctx, tool_input)
    return f"Unknown tool: {tool_name}"
