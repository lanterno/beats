import http
import logging

from datetime import date, timedelta
from fastapi import FastAPI

from beats.db_helpers import serialize_from_document, serialize_to_document
from beats.exceptions import ProjectWasNotStarted, MoreThanOneLogOpenForProject, ProjectAlreadyStarted
from beats.models import ProjectRepository, Project, TimeLog, TimeLogRepository
from beats.validation_models import RecordTimeValidator

logger = logging.getLogger(__name__)
app = FastAPI()


@app.get("/projects")
async def list_projects():
    data = [serialize_from_document(p) for p in ProjectRepository.list()]
    for item in data:
        item.pop("archived")
    return data


@app.post("/projects", status_code=http.HTTPStatus.CREATED)
async def create_project(project: Project):
    project = ProjectRepository.create(project.dict(exclude_none=True))
    return serialize_from_document(project)


@app.put("/projects")
async def update_project(project: Project):
    project = ProjectRepository.update(serialize_to_document(project.dict(exclude_none=True)))
    return serialize_from_document(project)


@app.post("/projects/{project_id}/archive")
async def archive_project(project_id: str):
    ProjectRepository.update({'_id': project_id, 'archived': True})
    return {"status": "success"}


@app.get("/projects/{project_id}/today/summary/")
async def today_time_for_project(project_id: str):
    logs = list(TimeLogRepository.list({"project_id": project_id}))
    today_logs = [TimeLog(**serialize_from_document(log)) for log in logs if TimeLog(**log).start.date() == date.today()]
    return {"duration": str(sum([log.duration() for log in today_logs], timedelta()))}


@app.post("/projects/{project_id}/start")
async def start_project_timer(project_id: str, time_validator: RecordTimeValidator):
    available_project_ids = [str(p["_id"]) for p in ProjectRepository.list()]
    if project_id not in available_project_ids:
        return {"project_id": "This project id does not exist"}
    logs = list(TimeLogRepository.list({"project_id": project_id, "end": None}))
    if logs:
        raise ProjectAlreadyStarted
    log = TimeLog(project_id=project_id, start=time_validator.time)
    TimeLogRepository.create(log.dict(exclude_none=True))
    return log


@app.post("/projects/{project_id}/stop")
async def end_project_timer(project_id: str, time_validator: RecordTimeValidator):
    logs = list(TimeLogRepository.list({"project_id": project_id, "end": None}))
    if not logs:
        raise ProjectWasNotStarted
    if len(logs) > 1:
        raise MoreThanOneLogOpenForProject
    log = serialize_from_document(logs[0])
    logger.info(f"We got log {log}")
    log = TimeLog(**log)
    logger.info(f"Validated log: {log.dict()}")
    log.stop_timer(time=time_validator.time)
    TimeLogRepository.update(serialize_to_document(log.dict()))
    return log
