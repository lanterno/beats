from fastapi import FastAPI

from ptc.models import ProjectManager

app = FastAPI()


@app.get("/projects")
async def list_projects():
    return list(ProjectManager.list())


@app.post("/projects")
async def create_project():
    pass


@app.post("/projects/{project_id}/start")
async def start_project_timer(project_id: int):
    pass


@app.post("/projects/{project_id}/stop")
async def end_project_timer(project_id: int):
    pass
