"""Signals API router — flow windows and signal summaries from the daemon."""

import csv
import io
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from beats.api.dependencies import (
    CurrentUserId,
    FlowWindowRepoDep,
    PendingSuggestionRepoDep,
    ProjectServiceDep,
    SignalSummaryRepoDep,
    TimerServiceDep,
)
from beats.domain.models import FlowWindow, PendingSuggestion, SignalSummary

router = APIRouter(prefix="/api/signals", tags=["signals"])


# --- Schemas ---


class PostFlowWindowRequest(BaseModel):
    window_start: datetime
    window_end: datetime
    flow_score: float = Field(ge=0.0, le=1.0)
    cadence_score: float = Field(ge=0.0, le=1.0)
    coherence_score: float = Field(ge=0.0, le=1.0)
    category_fit_score: float = Field(ge=0.0, le=1.0)
    idle_fraction: float = Field(ge=0.0, le=1.0)
    dominant_bundle_id: str = ""
    dominant_category: str = ""
    context_switches: int = 0
    active_project_id: str | None = None
    # Editor heartbeat snapshot at the time the daemon flushed the window.
    # All optional — older daemons (and windows where no editor was active)
    # send these as null / omit them.
    editor_repo: str | None = None
    editor_branch: str | None = None
    editor_language: str | None = None


class FlowWindowResponse(BaseModel):
    id: str
    window_start: datetime
    window_end: datetime
    flow_score: float
    cadence_score: float
    coherence_score: float
    category_fit_score: float
    idle_fraction: float
    dominant_bundle_id: str
    dominant_category: str
    context_switches: int
    active_project_id: str | None
    editor_repo: str | None = None
    editor_branch: str | None = None
    editor_language: str | None = None


class PostSignalSummaryRequest(BaseModel):
    hour: datetime
    categories: dict[str, int] = Field(default_factory=dict)
    total_samples: int = 0
    idle_samples: int = 0


class SignalSummaryResponse(BaseModel):
    id: str
    hour: datetime
    categories: dict[str, int]
    total_samples: int
    idle_samples: int


class DeleteSignalsResponse(BaseModel):
    deleted_summaries: int


class TopBucket(BaseModel):
    """One bucket from a leaderboard within FlowWindowSummaryResponse."""

    key: str
    avg: float
    count: int


class FlowWindowSummaryResponse(BaseModel):
    """Aggregate stats for a flow-window slice — single round-trip alternative
    to fetching the rows and reducing client-side. Mirrors what the UI's
    summarizeFlow / aggregateFlowBy helpers compute, plus the per-axis
    leaderboard top entry so callers don't need a second request."""

    count: int
    avg: float
    peak: float
    peak_at: datetime | None
    top_repo: TopBucket | None
    top_language: TopBucket | None
    top_bundle: TopBucket | None


# --- Endpoints ---


@router.post("/flow-windows", status_code=status.HTTP_201_CREATED)
async def post_flow_window(
    body: PostFlowWindowRequest,
    request: Request,
    user_id: CurrentUserId,
    repo: FlowWindowRepoDep,
) -> dict[str, str]:
    """Store a computed flow window from the daemon (device token required)."""
    device_id = getattr(request.state, "device_id", "")
    window = FlowWindow(
        device_id=device_id,
        window_start=body.window_start,
        window_end=body.window_end,
        flow_score=body.flow_score,
        cadence_score=body.cadence_score,
        coherence_score=body.coherence_score,
        category_fit_score=body.category_fit_score,
        idle_fraction=body.idle_fraction,
        dominant_bundle_id=body.dominant_bundle_id,
        dominant_category=body.dominant_category,
        context_switches=body.context_switches,
        active_project_id=body.active_project_id,
        editor_repo=body.editor_repo,
        editor_branch=body.editor_branch,
        editor_language=body.editor_language,
    )
    created = await repo.create(window)
    return {"id": created.id or ""}


@router.get("/flow-windows", response_model=list[FlowWindowResponse])
async def list_flow_windows(
    user_id: CurrentUserId,
    repo: FlowWindowRepoDep,
    start: datetime = Query(default_factory=lambda: datetime.now(UTC) - timedelta(days=1)),
    end: datetime = Query(default_factory=lambda: datetime.now(UTC)),
    project_id: str | None = Query(default=None),
    editor_repo: str | None = Query(default=None),
    editor_language: str | None = Query(default=None),
    bundle_id: str | None = Query(default=None),
) -> list[FlowWindowResponse]:
    """List flow windows for the current user within a date range.

    Optional filters narrow the result, AND-composed:
    - `project_id` — only windows captured while a timer was running on
      this project (i.e. `active_project_id` matches).
    - `editor_repo` — only windows whose VS Code heartbeat reported this
      workspace path. Use the absolute path the daemon stores; the
      companion / web UI render a shortened display form on top.
    - `editor_language` — only windows whose VS Code heartbeat reported
      this language id (e.g. "go", "typescriptreact").
    - `bundle_id` — only windows whose dominant frontmost app matched
      this macOS bundle id (e.g. "com.microsoft.VSCode").
    """
    windows = await repo.list_by_range(
        start,
        end,
        project_id=project_id,
        editor_repo=editor_repo,
        editor_language=editor_language,
        bundle_id=bundle_id,
    )
    return [
        FlowWindowResponse(
            id=w.id or "",
            window_start=w.window_start,
            window_end=w.window_end,
            flow_score=w.flow_score,
            cadence_score=w.cadence_score,
            coherence_score=w.coherence_score,
            category_fit_score=w.category_fit_score,
            idle_fraction=w.idle_fraction,
            dominant_bundle_id=w.dominant_bundle_id,
            dominant_category=w.dominant_category,
            context_switches=w.context_switches,
            active_project_id=w.active_project_id,
            editor_repo=w.editor_repo,
            editor_branch=w.editor_branch,
            editor_language=w.editor_language,
        )
        for w in windows
    ]


@router.get("/flow-windows.csv")
async def export_flow_windows_csv(
    user_id: CurrentUserId,
    repo: FlowWindowRepoDep,
    start: datetime = Query(default_factory=lambda: datetime.now(UTC) - timedelta(days=1)),
    end: datetime = Query(default_factory=lambda: datetime.now(UTC)),
    project_id: str | None = Query(default=None),
    editor_repo: str | None = Query(default=None),
    editor_language: str | None = Query(default=None),
    bundle_id: str | None = Query(default=None),
) -> StreamingResponse:
    """Download the current flow-window slice as CSV.

    Accepts the same filter params as `GET /flow-windows`, so the user
    can download exactly the slice they're staring at on the Insights
    page (or pulling from `beatsd recent`). One row per window.
    """
    windows = await repo.list_by_range(
        start,
        end,
        project_id=project_id,
        editor_repo=editor_repo,
        editor_language=editor_language,
        bundle_id=bundle_id,
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "window_start",
            "window_end",
            "flow_score",
            "cadence_score",
            "coherence_score",
            "category_fit_score",
            "idle_fraction",
            "dominant_bundle_id",
            "dominant_category",
            "context_switches",
            "active_project_id",
            "editor_repo",
            "editor_branch",
            "editor_language",
        ]
    )
    for w in windows:
        writer.writerow(
            [
                w.window_start.isoformat(),
                w.window_end.isoformat(),
                f"{w.flow_score:.4f}",
                f"{w.cadence_score:.4f}",
                f"{w.coherence_score:.4f}",
                f"{w.category_fit_score:.4f}",
                f"{w.idle_fraction:.4f}",
                w.dominant_bundle_id or "",
                w.dominant_category or "",
                w.context_switches,
                w.active_project_id or "",
                w.editor_repo or "",
                w.editor_branch or "",
                w.editor_language or "",
            ]
        )

    filename = _csv_filename_for_range(start, end)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _csv_filename_for_range(start: datetime, end: datetime) -> str:
    """Build a filename that reflects the queried date range.

    The previous implementation hardcoded today's date, so a user
    exporting `?start=2026-04-01&end=2026-04-30` got a file named
    `beats_flow_windows_<today>.csv` — surprising on a download
    that's clearly an archival range, not "today".

    Rules:
    - Single-day range (start and end fall on the same UTC date):
      `beats_flow_windows_YYYYMMDD.csv`
    - Multi-day range: `beats_flow_windows_YYYYMMDD_to_YYYYMMDD.csv`

    UTC dates are used (matching the API's storage convention) so
    a user exporting around midnight gets a stable name regardless
    of their browser's timezone.
    """
    start_day = start.astimezone(UTC).strftime("%Y%m%d")
    end_day = end.astimezone(UTC).strftime("%Y%m%d")
    if start_day == end_day:
        return f"beats_flow_windows_{start_day}.csv"
    return f"beats_flow_windows_{start_day}_to_{end_day}.csv"


@router.get("/flow-windows/summary", response_model=FlowWindowSummaryResponse)
async def summarize_flow_windows(
    user_id: CurrentUserId,
    repo: FlowWindowRepoDep,
    start: datetime = Query(default_factory=lambda: datetime.now(UTC) - timedelta(days=1)),
    end: datetime = Query(default_factory=lambda: datetime.now(UTC)),
    project_id: str | None = Query(default=None),
    editor_repo: str | None = Query(default=None),
    editor_language: str | None = Query(default=None),
    bundle_id: str | None = Query(default=None),
) -> FlowWindowSummaryResponse:
    """Aggregate stats for the flow-window slice in [start, end].

    Single round-trip alternative to `GET /flow-windows` + client-side
    reduction. Returns avg / peak / count of the slice plus the top
    bucket on each of the three grouping axes (repo, language, app)
    so a caller can render a "you flowed best on X today" headline
    without a second request.

    Accepts the same filter params as `GET /flow-windows`, AND-composed.
    """
    windows = await repo.list_by_range(
        start,
        end,
        project_id=project_id,
        editor_repo=editor_repo,
        editor_language=editor_language,
        bundle_id=bundle_id,
    )

    if not windows:
        return FlowWindowSummaryResponse(
            count=0,
            avg=0.0,
            peak=0.0,
            peak_at=None,
            top_repo=None,
            top_language=None,
            top_bundle=None,
        )

    total = sum(w.flow_score for w in windows)
    peak_window = max(windows, key=lambda w: w.flow_score)

    return FlowWindowSummaryResponse(
        count=len(windows),
        avg=total / len(windows),
        peak=peak_window.flow_score,
        peak_at=peak_window.window_start,
        top_repo=_top_bucket(windows, lambda w: w.editor_repo or ""),
        top_language=_top_bucket(windows, lambda w: w.editor_language or ""),
        top_bundle=_top_bucket(windows, lambda w: w.dominant_bundle_id or ""),
    )


def _top_bucket(windows: list[FlowWindow], key_of) -> TopBucket | None:
    """Group windows by a key, return the bucket with the most windows.

    Empty keys are skipped so an axis with no editor heartbeats returns
    None rather than a meaningless "" bucket. Tie-breaks on avg so the
    higher-quality bucket wins when minutes match — same rule as the
    daemon's `beatsd top` and the UI's aggregation cards."""
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for w in windows:
        k = key_of(w)
        if not k:
            continue
        sums[k] = sums.get(k, 0.0) + w.flow_score
        counts[k] = counts.get(k, 0) + 1
    if not counts:
        return None
    best_key = max(counts, key=lambda k: (counts[k], sums[k] / counts[k]))
    return TopBucket(
        key=best_key,
        avg=sums[best_key] / counts[best_key],
        count=counts[best_key],
    )


@router.post("/summaries", status_code=status.HTTP_200_OK)
async def post_signal_summary(
    body: PostSignalSummaryRequest,
    request: Request,
    user_id: CurrentUserId,
    repo: SignalSummaryRepoDep,
) -> dict[str, str]:
    """Upsert an hourly signal summary from the daemon (device token required)."""
    device_id = getattr(request.state, "device_id", "")
    summary = SignalSummary(
        device_id=device_id,
        hour=body.hour,
        categories=body.categories,
        total_samples=body.total_samples,
        idle_samples=body.idle_samples,
    )
    result = await repo.upsert(summary)
    return {"id": result.id or ""}


@router.get("/summaries", response_model=list[SignalSummaryResponse])
async def list_signal_summaries(
    user_id: CurrentUserId,
    repo: SignalSummaryRepoDep,
    start: datetime = Query(default_factory=lambda: datetime.now(UTC) - timedelta(days=1)),
    end: datetime = Query(default_factory=lambda: datetime.now(UTC)),
) -> list[SignalSummaryResponse]:
    """List signal summaries for the current user within a date range."""
    summaries = await repo.list_by_range(start, end)
    return [
        SignalSummaryResponse(
            id=s.id or "",
            hour=s.hour,
            categories=s.categories,
            total_samples=s.total_samples,
            idle_samples=s.idle_samples,
        )
        for s in summaries
    ]


class TimerStatusResponse(BaseModel):
    timer_running: bool
    project_id: str | None = None
    project_category: str | None = None


class AutoTimerSuggestion(BaseModel):
    should_suggest: bool
    project_id: str | None = None
    project_name: str | None = None


@router.get("/timer-context", response_model=TimerStatusResponse)
async def get_timer_context(
    user_id: CurrentUserId,
    timer_service: TimerServiceDep,
) -> TimerStatusResponse:
    """Get current timer context for the daemon's flow score computation."""
    active = await timer_service.beat_repo.get_active()
    if not active:
        return TimerStatusResponse(timer_running=False)

    project = await timer_service.project_repo.get_by_id(active.project_id)
    return TimerStatusResponse(
        timer_running=True,
        project_id=project.id,
        project_category=project.category,
    )


@router.post("/suggest-timer", response_model=AutoTimerSuggestion)
async def suggest_timer(
    body: PostFlowWindowRequest,
    request: Request,
    user_id: CurrentUserId,
    timer_service: TimerServiceDep,
    project_service: ProjectServiceDep,
    pending_repo: PendingSuggestionRepoDep,
) -> AutoTimerSuggestion:
    """Check if a timer should be auto-started based on flow state.

    Called by the daemon when Flow Score >= 0.7 for 8+ consecutive minutes.

    Matching priority:
    1. editor_repo against project.autostart_repos — if the user's
       editor heartbeat carries a workspace path that one project
       claims as its autostart_repo, that's the most-specific match.
       Disambiguates two coding projects with the same category.
    2. dominant_category against project.category — fallback when
       the editor_repo is empty (no editor active) or no project
       claims it.

    On a positive match the suggestion is also persisted via
    `pending_repo.create` so the companion's notification poller can
    pick it up via `GET /api/signals/pending-suggestions` and fire
    `notifyAutoTimerSuggestion` for users whose desktop daemon isn't
    the OS notifier (mobile, headless servers, etc.).

    Previously only matched by category, so two same-category
    projects couldn't be disambiguated and the docstring's mention
    of autostart_repos didn't reflect the implementation.
    """
    # Don't suggest if timer already running
    active = await timer_service.beat_repo.get_active()
    if active:
        return AutoTimerSuggestion(should_suggest=False)

    projects = await project_service.project_repo.list(archived=False)

    async def _persist_and_return(p: object, editor_repo: str | None) -> AutoTimerSuggestion:
        # `p` is a Project here; typed loosely so the `_persist_and_return`
        # signature stays the same for both match paths below without
        # importing Project just for an annotation.
        await pending_repo.create(
            PendingSuggestion(
                project_id=p.id,  # type: ignore[attr-defined]
                project_name=p.name,  # type: ignore[attr-defined]
                dominant_category=body.dominant_category,
                editor_repo=editor_repo,
            )
        )
        return AutoTimerSuggestion(
            should_suggest=True,
            project_id=p.id,  # type: ignore[attr-defined]
            project_name=p.name,  # type: ignore[attr-defined]
        )

    # 1. Try the most-specific match: editor_repo in autostart_repos.
    if body.editor_repo:
        for p in projects:
            if body.editor_repo in p.autostart_repos:
                return await _persist_and_return(p, body.editor_repo)

    # 2. Fallback: match by category.
    for p in projects:
        if p.category and p.category == body.dominant_category:
            return await _persist_and_return(p, None)

    return AutoTimerSuggestion(should_suggest=False)


class PendingSuggestionResponse(BaseModel):
    id: str
    project_id: str
    project_name: str
    suggested_at: datetime
    editor_repo: str | None = None


class PendingSuggestionsResponse(BaseModel):
    """Auto-timer suggestions the API has surfaced but the user hasn't yet
    acted on. The companion's notification poller queries this every 5 min
    and fires `notifyAutoTimerSuggestion` for any id it hasn't seen,
    deduping via SharedPreferences. `since` defaults to the last 30 minutes
    so a couple of missed poll ticks (5 min apart) don't drop a prompt."""

    suggestions: list[PendingSuggestionResponse]


@router.get("/pending-suggestions", response_model=PendingSuggestionsResponse)
async def get_pending_suggestions(
    user_id: CurrentUserId,
    pending_repo: PendingSuggestionRepoDep,
    since: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> PendingSuggestionsResponse:
    """Return auto-timer suggestions emitted in the last `since` window.

    See [post] /suggest-timer for the write side. This endpoint is the
    companion-side read surface — same shape and semantics as
    `/recent-drift`. Newest-first, capped at 100.
    """
    if since is None:
        since = datetime.now(UTC) - timedelta(minutes=30)
    suggestions = await pending_repo.list_recent(since, limit=limit)
    return PendingSuggestionsResponse(
        suggestions=[
            PendingSuggestionResponse(
                id=s.id or "",
                project_id=s.project_id,
                project_name=s.project_name,
                suggested_at=s.suggested_at,
                editor_repo=s.editor_repo,
            )
            for s in suggestions
        ]
    )


class PostDriftEventRequest(BaseModel):
    started_at: datetime
    duration_seconds: float
    bundle_id: str


@router.post("/drift", status_code=status.HTTP_201_CREATED)
async def post_drift_event(
    body: PostDriftEventRequest,
    request: Request,
    user_id: CurrentUserId,
    repo: FlowWindowRepoDep,
) -> dict[str, str]:
    """Record a distraction drift event from the daemon.

    Stores the drift as a FlowWindow with category="drift", flow
    score 0, and an end timestamp computed from the request's
    duration_seconds — previous versions set window_end to
    started_at, dropping the duration field on the floor and
    making "total distraction time" uncomputable from the data.
    """
    device_id = getattr(request.state, "device_id", "")
    window = FlowWindow(
        device_id=device_id,
        window_start=body.started_at,
        window_end=body.started_at + timedelta(seconds=body.duration_seconds),
        flow_score=0.0,
        dominant_bundle_id=body.bundle_id,
        dominant_category="drift",
        context_switches=0,
    )
    created = await repo.create(window)
    return {"id": created.id or ""}


class DriftEvent(BaseModel):
    id: str
    started_at: datetime
    duration_seconds: float
    bundle_id: str


class RecentDriftResponse(BaseModel):
    """Drift events recent enough to be worth notifying the user about.

    The companion's notification poller queries this endpoint on a 5-minute
    foreground tick, fires `notifyDriftAlert` for any event id it hasn't
    seen, and dedupes via SharedPreferences. `since` defaults to 30 minutes
    ago so a brief network blip doesn't cause the poller to miss a window.
    """

    events: list[DriftEvent]


@router.get("/recent-drift", response_model=RecentDriftResponse)
async def get_recent_drift(
    user_id: CurrentUserId,
    repo: FlowWindowRepoDep,
    since: datetime | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> RecentDriftResponse:
    """Return drift events recorded since `since` (defaults to last 30 min).

    Drift events are stored as flow windows with `dominant_category="drift"`
    by the daemon's `shield` package. This endpoint is the companion-side
    read surface — the daemon already fires a native macOS notification
    on the desktop, so the companion poller adds the same prompt for users
    on iOS / Android / desktops without the daemon installed.
    """
    if since is None:
        since = datetime.now(UTC) - timedelta(minutes=30)
    end = datetime.now(UTC)
    windows = await repo.list_by_range(since, end, dominant_category="drift")
    # Newest first; cap at limit so a runaway day of distractions doesn't
    # produce a multi-MB response.
    windows.sort(key=lambda w: w.window_start, reverse=True)
    return RecentDriftResponse(
        events=[
            DriftEvent(
                id=w.id or "",
                started_at=w.window_start,
                duration_seconds=(w.window_end - w.window_start).total_seconds(),
                bundle_id=w.dominant_bundle_id,
            )
            for w in windows[:limit]
        ]
    )


@router.delete("/all", response_model=DeleteSignalsResponse)
async def delete_all_signals(
    user_id: CurrentUserId,
    summary_repo: SignalSummaryRepoDep,
) -> DeleteSignalsResponse:
    """Delete all signal summaries for the current user (privacy dashboard)."""
    deleted = await summary_repo.delete_all()
    return DeleteSignalsResponse(deleted_summaries=deleted)
