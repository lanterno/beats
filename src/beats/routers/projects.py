import http
import logging
from collections import defaultdict
from datetime import date, timedelta

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from beats.db_helpers import serialize_from_document, serialize_to_document
from beats.domain import Beat, BeatRepository, Project, ProjectRepository
from beats.exceptions import ProjectWasNotStarted, TwoProjectInProgess
from beats.validation_models import RecordTimeValidator

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/projects",
    tags=["Projects"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
async def list_projects(archived: bool = False):
    """
    List all projects.

    Returns a list of projects with calculated time tracking fields:
    - `spent_hours`: Total number of hours spent on the project across all time
    - `weekly_hours`: Number of hours worked on the project in the current week (Monday-Sunday)
    - `weekly_goal`: Weekly goal in hours for the project (null if not set)

    Results are sorted by `weekly_hours` in descending order by default.

    Args:
        archived: If True, returns only archived projects. If False, returns only active projects.

    Returns:
        List of project objects, each containing:
        - Standard project fields (id, name, description, estimation, archived)
        - `spent_hours` (float): Total hours spent on the project
        - `weekly_hours` (float): Hours worked this week on the project
        - `weekly_goal` (float | null): Weekly goal in hours (null if not set)
    """
    projects = list(ProjectRepository.list({"archived": archived}))
    today = date.today()
    start_of_week = today - timedelta(days=today.weekday())  # Monday
    end_of_week = start_of_week + timedelta(days=6)  # Sunday

    result = []
    for project in projects:
        project_data = serialize_from_document(project)
        project_id = project_data.get("id")

        # Get all beats for this project
        logs = list(BeatRepository.list({"project_id": project_id}))
        beats = [Beat(**serialize_from_document(log)) for log in logs]

        # Calculate total spent hours
        total_duration = sum([beat.duration for beat in beats], timedelta())
        spent_hours = round(total_duration.total_seconds() / 3600, 2)

        # Calculate weekly hours (only beats in current week)
        week_beats = [
            b for b in beats if start_of_week <= b.start.date() <= end_of_week
        ]
        weekly_duration = sum([beat.duration for beat in week_beats], timedelta())
        weekly_hours = round(weekly_duration.total_seconds() / 3600, 2)

        # Add calculated fields
        project_data["spent_hours"] = spent_hours
        project_data["weekly_hours"] = weekly_hours

        # Add weekly_goal field (null if not present, otherwise as float)
        if "weekly_goal" in project_data and project_data["weekly_goal"] is not None:
            project_data["weekly_goal"] = float(project_data["weekly_goal"])
        else:
            project_data["weekly_goal"] = None

        result.append(project_data)

    # Sort by weekly_hours descending
    result.sort(key=lambda x: x.get("weekly_hours", 0), reverse=True)

    return result


@router.post("/", status_code=http.HTTPStatus.CREATED)
async def create_project(project: Project) -> dict:
    project_data = ProjectRepository.create(project.model_dump(exclude_none=True))
    return serialize_from_document(project_data)


@router.put("/")
async def update_project(project: Project) -> dict:
    updated_project = ProjectRepository.update(
        serialize_to_document(project.model_dump(exclude_none=True))
    )
    return serialize_from_document(updated_project)


@router.post("/{project_id}/archive")
async def archive_project(project_id: str):
    ProjectRepository.update({"_id": project_id, "archived": True})
    return {"status": "success"}


@router.get("/{project_id}/today/")
async def today_time_for_project(project_id: str):
    logs = list(BeatRepository.list({"project_id": project_id}))
    beats = [Beat(**serialize_from_document(log)) for log in logs]
    today = date.today()
    today_logs = [b for b in beats if b.start.date() == today]
    return {"duration": str(sum([log.duration for log in today_logs], timedelta()))}


@router.get("/{project_id}/week/")
async def current_week_time_for_project(project_id: str, weeks_ago: int = 0):
    logs = list(BeatRepository.list({"project_id": project_id}))
    today = date.today() - timedelta(weeks=weeks_ago)
    start_of_week = today - timedelta(days=today.weekday())  # Monday
    end_of_week = start_of_week + timedelta(days=6)  # Sunday

    # Filter logs to only this week
    beats = [Beat(**serialize_from_document(log)) for log in logs]
    week_logs = [b for b in beats if start_of_week <= b.start.date() <= end_of_week]

    # Group by weekday
    per_day = defaultdict(timedelta)
    for log in week_logs:
        per_day[log.start.strftime("%A")] += log.duration

    # Ensure all weekdays are present
    result = {}
    total_duration = timedelta()
    for i in range(7):
        day_date = start_of_week + timedelta(days=i)
        day_name = day_date.strftime("%A")
        duration = per_day.get(day_name, timedelta())
        result[day_name] = str(duration)
        total_duration += duration

    # Add total in hours (rounded to 2 decimals)
    result["total_hours"] = round(total_duration.total_seconds() / 3600, 2)

    return result


@router.get("/{project_id}/total/", response_model=None)
async def total_work_time_per_month_on_project(project_id: str):
    logs = list(BeatRepository.list({"project_id": project_id}))

    logs_since_start = []
    warnings = []  # collect warning messages

    for log in logs:
        log = serialize_from_document(log)
        if "end" not in log:
            continue
        if "start" not in log:
            return JSONResponse(
                content={"error": f"Invalid log data - {log}"},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        try:
            beat = Beat(**log)
            if beat.start.date():
                if beat.duration > timedelta(hours=24):
                    warnings.append(
                        f"Warning: Log {beat} has duration longer than 24 hours ({beat.duration})."
                    )
                logs_since_start.append(beat)
        except Exception as e:
            logger.error(f"Error processing log {log}: {e}")
            return JSONResponse(
                content={"error": f"Invalid log data - {log}"},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    # Group durations by month (e.g. "2024-09")
    durations_per_month = defaultdict(timedelta)
    for log in logs_since_start:
        month_key = log.start.strftime("%Y-%m")
        durations_per_month[month_key] += log.duration

    # Convert durations to float hours
    result = {
        month: round(duration.total_seconds() / 3600, 2)
        for month, duration in sorted(durations_per_month.items())
    }

    return {
        "durations_per_month": result,
        "warnings": warnings,
    }


@router.get("/{project_id}/summary/")
async def get_project_summary(project_id: str):
    logs = list(BeatRepository.list({"project_id": project_id}))
    logs = [Beat(**serialize_from_document(log)) for log in logs]
    statistical = {}
    for log in logs:
        if log.day not in statistical:
            statistical[log.day] = []
        statistical[log.day].append(log.duration)
    from datetime import timedelta

    statistical = {key: str(sum(statistical[key], timedelta())) for key in statistical}
    return statistical


@router.post("/{project_id}/start", response_model=None)
async def start_project_timer(project_id: str, time_validator: RecordTimeValidator):
    available_project_ids = [str(p["_id"]) for p in ProjectRepository.list()]
    if project_id not in available_project_ids:
        return {"project_id": "This project id does not exist"}

    active_logs = list(BeatRepository.list({"end": None}))
    if active_logs:
        log = Beat(**serialize_from_document(active_logs[0]))
        return JSONResponse(
            content={
                "error": "another beat already in progress",
                "beat": log.model_dump_json(exclude_none=True),
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    new_log = Beat(project_id=project_id, start=time_validator.time)
    created_log = Beat(
        **serialize_from_document(
            BeatRepository.create(new_log.model_dump(exclude_none=True))
        )
    )
    return created_log


@router.post("/stop", response_model=None)
async def end_project_timer(time_validator: RecordTimeValidator):
    active_logs = list(BeatRepository.list({"end": None}))
    if not active_logs:
        raise ProjectWasNotStarted
    if len(active_logs) > 1:
        raise TwoProjectInProgess

    log_data = serialize_from_document(active_logs[0])
    logger.info(f"We got log {log_data}")
    log = Beat(**log_data)
    logger.info(f"Validated log: {log.model_dump()}")
    log.stop_timer(time=time_validator.time)
    BeatRepository.update(serialize_to_document(log.model_dump(exclude_none=True)))
    return log
