import logging

from datetime import datetime, date, timedelta
from fastapi import FastAPI

from beats.db_helpers import serialize_from_document, serialize_to_document
from beats.exceptions import ProjectWasNotStarted, MoreThanOneLogOpenForProject, ProjectAlreadyStarted
from beats.models import ProjectManager, Project, TimeLog, TimeLogManager
from beats.validation_models import RecordTimeValidator

logger = logging.getLogger(__name__)
app = FastAPI()


@app.get("/projects")
async def list_projects():
    return [serialize_from_document(p) for p in ProjectManager.list()]


@app.post("/projects")
async def create_project(project: Project):
    ProjectManager.create(project.dict(exclude_none=True))
    return project


@app.get("/projects/{project_id}/today/summary/")
async def today_time_for_project(project_id: str):
    logs = list(TimeLogManager.list({"project_id": project_id}))
    today_logs = [TimeLog(**serialize_from_document(log)) for log in logs if TimeLog(**log).start.date() == date.today()]

    return {"duration": str(sum([log.duration() for log in today_logs], timedelta()))}


@app.post("/projects/{project_id}/start")
async def start_project_timer(project_id: str, time_validator: RecordTimeValidator):
    available_project_ids = [str(p["_id"]) for p in ProjectManager.list()]
    if project_id not in available_project_ids:
        return {"project_id": "This project id does not exist"}
    logs = list(TimeLogManager.list({"project_id": project_id, "end": None}))
    if logs:
        raise ProjectAlreadyStarted
    log = TimeLog(project_id=project_id, start=time_validator.time)
    TimeLogManager.create(log.dict(exclude_none=True))
    return log


@app.post("/projects/{project_id}/stop")
async def end_project_timer(project_id: str, time_validator: RecordTimeValidator):
    logs = list(TimeLogManager.list({"project_id": project_id, "end": None}))
    if not logs:
        raise ProjectWasNotStarted
    if len(logs) > 1:
        raise MoreThanOneLogOpenForProject
    log = serialize_from_document(logs[0])
    logger.info(f"We got log {log}")
    log = TimeLog(**log)
    logger.info(f"Validated log: {log.dict()}")
    log.stop_timer(time=time_validator.time)
    TimeLogManager.update(serialize_to_document(log.dict()))
    return log

@app.post("/projects/sync-sheets")
def sync_sheets():
    import json
    with open('beats/sheets/' + "projects" + '.json', 'r') as p_file:
        projects = json.load(p_file)

    existing_projects = {}
    for p in ProjectManager.list():
        existing_projects[p["name"]] = p

    for project in projects.items():
        print(f"{project[0]} updating..")
        project[1].update(existing_projects[project[0]])
        project[1].pop("state")
        project[1].pop("total_spent_time")
        project[1].pop("details", None)
        if project[1]["estimated time"] == "undefined":
            project[1].pop("estimated time")
        ProjectManager.update(project[1])

    return {"status": "done"}


def format_time(t, is_date=False):
    separator = "-" if is_date else ":"
    t = t.split(separator)
    for i in [0, 1, 2]:
        if len(t[i]) == 1:
            t[i] = "0" + t[i]
    t = separator.join(t)

    if not is_date:
        t = "T" + t + "+02:00"
    return t

@app.post("/sync-logs")
def sync_logs():
    import json
    from datetime import datetime, timedelta

    existing_projects = {}
    for p in ProjectManager.list():
        existing_projects[p["name"]] = p
    for project in existing_projects.items():
        print(f"{project[0]} starting...")
        try:
            with open("beats/sheets/logs/" + project[0] + '.json', 'r') as logs_f:
                logs = json.load(logs_f)
        except Exception:
            print(f"no logs file for {project[0]}")
            continue

        for log in logs:
            if "Not" in log["end"]:
                print(f"one log for {project[0]} wasn't closed correctly!")
                continue
            if log.get("date") is None:
                # print(f"couldn't find date for project {project[0]}")
                continue

            _date = format_time(log["date"], is_date=True)
            start_time = datetime.fromisoformat(_date + format_time(log["start"]))
            end_time = datetime.fromisoformat(_date + format_time(log["end"]))

            if end_time < start_time:
                end_time = end_time + timedelta(days=1)

            log = TimeLog(project_id=str(project[1]["_id"]), start=start_time, end=end_time)

            if not project[0] == "cube":
                TimeLogManager.create(log.dict(exclude_none=True))

    return {"status": "done"}