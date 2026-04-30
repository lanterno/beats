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
    ProjectServiceDep,
    SignalSummaryRepoDep,
    TimerServiceDep,
)
from beats.domain.models import FlowWindow, SignalSummary

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

    filename = f"beats_flow_windows_{datetime.now(UTC).strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
) -> AutoTimerSuggestion:
    """Check if a timer should be auto-started based on flow state.

    Called by the daemon when Flow Score >= 0.7 for 8+ consecutive minutes.
    Matches the dominant app category against projects with autostart_repos.
    """
    # Don't suggest if timer already running
    active = await timer_service.beat_repo.get_active()
    if active:
        return AutoTimerSuggestion(should_suggest=False)

    # Find a project matching the dominant category
    projects = await project_service.project_repo.list(archived=False)
    for p in projects:
        if p.category and p.category == body.dominant_category:
            return AutoTimerSuggestion(
                should_suggest=True,
                project_id=p.id,
                project_name=p.name,
            )

    return AutoTimerSuggestion(should_suggest=False)


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
    """Record a distraction drift event from the daemon."""
    device_id = getattr(request.state, "device_id", "")
    window = FlowWindow(
        device_id=device_id,
        window_start=body.started_at,
        window_end=body.started_at,
        flow_score=0.0,
        dominant_bundle_id=body.bundle_id,
        dominant_category="drift",
        context_switches=0,
    )
    created = await repo.create(window)
    return {"id": created.id or ""}


@router.delete("/all", response_model=DeleteSignalsResponse)
async def delete_all_signals(
    user_id: CurrentUserId,
    summary_repo: SignalSummaryRepoDep,
) -> DeleteSignalsResponse:
    """Delete all signal summaries for the current user (privacy dashboard)."""
    deleted = await summary_repo.delete_all()
    return DeleteSignalsResponse(deleted_summaries=deleted)
