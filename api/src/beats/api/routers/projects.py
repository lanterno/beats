"""Projects API router - thin controller for project operations."""

import http
from datetime import date, timedelta

from fastapi import APIRouter, Query

from beats.api.dependencies import (
    GitHubServiceDep,
    ProjectServiceDep,
    TimerServiceDep,
    WebhookRepoDep,
)
from beats.api.routers.webhooks import dispatch_webhook_event
from beats.api.schemas import (
    CreateProjectRequest,
    DurationResponse,
    GoalOverrideRequest,
    MonthlyTotalsResponse,
    RecordTimeRequest,
    UpdateProjectRequest,
)
from beats.domain.models import GoalOverride, Project

router = APIRouter(
    prefix="/api/projects",
    tags=["Projects"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def list_projects(service: ProjectServiceDep, archived: bool = False):
    """List all projects, optionally filtering by archived status."""
    projects = await service.list_projects(archived=archived)
    return [p.model_dump() for p in projects]


@router.post("/", status_code=http.HTTPStatus.CREATED)
async def create_project(request: CreateProjectRequest, service: ProjectServiceDep):
    """Create a new project."""
    project = Project(
        name=request.name,
        description=request.description,
        estimation=request.estimation,
        color=request.color,
        weekly_goal=request.weekly_goal,
        category=request.category,
    )
    created = await service.create_project(project)
    return created.model_dump()


@router.put("/")
async def update_project(request: UpdateProjectRequest, service: ProjectServiceDep):
    """Update an existing project."""
    # Preserve goal_overrides: UpdateProjectRequest doesn't carry them, so
    # building Project() from the request alone would wipe any overrides on
    # every unrelated edit (e.g. color change). Read existing first.
    existing = await service.project_repo.get_by_id(request.id)
    project = Project(
        id=request.id,
        name=request.name,
        description=request.description,
        estimation=request.estimation,
        color=request.color,
        archived=request.archived,
        weekly_goal=request.weekly_goal,
        goal_type=request.goal_type,
        goal_overrides=existing.goal_overrides,
        github_repo=request.github_repo,
        # category and autostart_repos were silently dropped here —
        # the schema accepted them but the route never forwarded them
        # to the domain, so the daemon's flow-score category_fit
        # never matched and auto-timer autostart rules never fired.
        category=request.category,
        autostart_repos=request.autostart_repos,
    )
    updated = await service.update_project(project)
    return updated.model_dump()


@router.put("/{project_id}/goal-overrides")
async def update_goal_overrides(
    project_id: str,
    overrides: list[GoalOverrideRequest],
    service: ProjectServiceDep,
):
    """Replace goal overrides for a project."""
    project = await service.project_repo.get_by_id(project_id)
    project.goal_overrides = [
        GoalOverride(
            week_of=o.week_of,
            effective_from=o.effective_from,
            weekly_goal=o.weekly_goal,
            goal_type=o.goal_type,
            note=o.note,
        )
        for o in overrides
    ]
    updated = await service.update_project(project)
    return updated.model_dump()


@router.get("/{project_id}/git-activity")
async def get_git_activity(
    project_id: str,
    service: ProjectServiceDep,
    github_service: GitHubServiceDep,
    start: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end: date = Query(default_factory=date.today),
):
    """Get GitHub commit counts correlated with a project's tracked time."""
    project = await service.project_repo.get_by_id(project_id)
    if not project.github_repo:
        return []
    return await github_service.fetch_commit_counts(project.github_repo, start, end)


@router.get("/{project_id}/daily-average")
async def get_daily_average(project_id: str, service: ProjectServiceDep):
    """Get the average daily session time for a project over the last 30 days."""
    return await service.get_daily_average(project_id)


@router.post("/{project_id}/archive")
async def archive_project(project_id: str, service: ProjectServiceDep):
    """Archive a project."""
    await service.archive_project(project_id)
    return {"status": "success"}


@router.get("/{project_id}/today/")
async def today_time_for_project(project_id: str, service: ProjectServiceDep) -> DurationResponse:
    """Get total time spent on project today."""
    duration = await service.get_today_time(project_id)
    return DurationResponse(duration=str(duration))


@router.get("/{project_id}/week/")
async def current_week_time_for_project(
    project_id: str,
    service: ProjectServiceDep,
    weeks_ago: int = 0,
    display_each_log_duration: bool = False,
):
    """Get time breakdown for a week."""
    return await service.get_week_breakdown(
        project_id=project_id,
        weeks_ago=weeks_ago,
        include_log_details=display_each_log_duration,
    )


@router.get("/{project_id}/total/")
async def total_work_time_per_month_on_project(
    project_id: str, service: ProjectServiceDep
) -> MonthlyTotalsResponse:
    """Get total time per month for a project."""
    result = await service.get_monthly_totals(project_id)
    return MonthlyTotalsResponse(**result)


@router.get("/{project_id}/summary/")
async def get_project_summary(project_id: str, service: ProjectServiceDep):
    """Get daily summary for a project."""
    return await service.get_daily_summary(project_id)


@router.post("/{project_id}/start")
async def start_project_timer(
    project_id: str,
    time_validator: RecordTimeRequest,
    service: TimerServiceDep,
    webhook_repo: WebhookRepoDep,
):
    """Start a timer for a project."""
    beat = await service.start_timer(project_id, time_validator.time)
    project = await service.project_repo.get_by_id(project_id)
    await dispatch_webhook_event(
        "timer.start",
        {"project_id": project_id, "project_name": project.name, "beat_id": beat.id},
        webhook_repo,
    )
    return beat.model_dump()


@router.post("/stop")
async def end_project_timer(
    time_validator: RecordTimeRequest,
    service: TimerServiceDep,
    webhook_repo: WebhookRepoDep,
):
    """Stop the currently running timer."""
    beat = await service.stop_timer(time_validator.time)
    await dispatch_webhook_event(
        "timer.stop",
        {
            "project_id": beat.project_id,
            "beat_id": beat.id,
            "duration_minutes": int(beat.duration.total_seconds() / 60),
        },
        webhook_repo,
    )
    return beat.model_dump()
