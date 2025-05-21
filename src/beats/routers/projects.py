import http
import logging
from datetime import date, timedelta

from fastapi import APIRouter
from starlette import status
from starlette.responses import JSONResponse

from beats.db_helpers import serialize_from_document, serialize_to_document
from beats.domain import ProjectRepository, Project, BeatRepository, Beat
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
    data = [
        serialize_from_document(p)
        for p in ProjectRepository.list({"archived": archived})
    ]
    return data


@router.post("/", status_code=http.HTTPStatus.CREATED)
async def create_project(project: Project):
    project = ProjectRepository.create(project.dict(exclude_none=True))
    return serialize_from_document(project)


@router.put("/")
async def update_project(project: Project):
    project = ProjectRepository.update(
        serialize_to_document(project.dict(exclude_none=True))
    )
    return serialize_from_document(project)


@router.post("/{project_id}/archive")
async def archive_project(project_id: str):
    ProjectRepository.update({"_id": project_id, "archived": True})
    return {"status": "success"}


@router.get("/{project_id}/today/")
async def today_time_for_project(project_id: str):
    logs = list(BeatRepository.list({"project_id": project_id}))
    today_logs = [Beat(**serialize_from_document(log)) for log in logs if Beat(**log).start.date() == date.today()]
@router.get("/{project_id}/week/")
async def current_week_time_for_project(project_id: str):
    logs = list(BeatRepository.list({"project_id": project_id}))
    today = date.today()
    today_logs = [
        Beat(**serialize_from_document(log))
        for log in logs
        if (date.today() - timedelta(days=today.weekday()))
        <= Beat(**log).start.date()
        <= (today + timedelta(days=0))
    ]
    return {"duration": str(sum([log.duration for log in today_logs], timedelta()))}


@router.get("/{project_id}/summary/")
async def get_project_summary(project_id: str):
    logs = list(BeatRepository.list({"project_id": project_id}))
    logs = [Beat(**serialize_from_document(log)) for log in logs]
    statistical = {}
    for log in logs:
        if log.day not in statistical:
            statistical[log.day] = []
        statistical[log.day].append(log.duration)
    statistical = {key: str(sum(statistical[key])) for key in statistical}
    return statistical


@router.post("/{project_id}/start")
async def start_project_timer(project_id: str, time_validator: RecordTimeValidator):
    available_project_ids = [str(p["_id"]) for p in ProjectRepository.list()]
    if project_id not in available_project_ids:
        return {"project_id": "This project id does not exist"}
    logs = list(BeatRepository.list({"project_id": project_id, "end": None}))
    if logs:
        log = logs[0]
        log = Beat(**serialize_from_document(log))
        return JSONResponse(
            content={"error": "another beat already in progress", "beat": log.json(exclude_none=True)},
            status_code=status.HTTP_400_BAD_REQUEST
        )
        # raise ProjectAlreadyStarted
    log = Beat(project_id=project_id, start=time_validator.time)
    log = Beat(**serialize_from_document(BeatRepository.create(log.dict(exclude_none=True))))
    return log


@router.post("/stop")
async def end_project_timer(time_validator: RecordTimeValidator):
    logs = list(BeatRepository.list({"end": None}))
    if not logs:
        raise ProjectWasNotStarted
    if len(logs) > 1:
        raise TwoProjectInProgess
    log = serialize_from_document(logs[0])
    logger.info(f"We got log {log}")
    log = Beat(**log)
    logger.info(f"Validated log: {log.dict()}")
    log.stop_timer(time=time_validator.time)
    BeatRepository.update(serialize_to_document(log.dict()))
    return log
