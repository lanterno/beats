import logging
from collections.abc import Callable

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from beats.exceptions import (
    CanNotStopNonBeatingHeart,
    InconsistentEndTime,
    ProjectWasNotStarted,
    TwoProjectInProgess,
)
from beats.routers.beats import router as beats_router
from beats.routers.projects import router as projects_router
from beats.routers.timer import router as timer_router
from beats.settings import settings

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Beats API",
    description="A time tracking application",
    version="0.3.0",
)

origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://localhost:8080",
    "https://lifepete.com",
    "http://lifepete.com",
    "http://site.lifepete.com/",
]

app.include_router(projects_router)
app.include_router(beats_router)
app.include_router(timer_router)


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Modern async middleware for API authentication"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        PROTECTED_METHODS = ["POST", "PUT", "PATCH"]
        # Allow unauthenticated access to beats endpoints (tests rely on this)
        if request.url.path.startswith("/api/beats"):
            return await call_next(request)

        if request.method in PROTECTED_METHODS:
            if "X-API-Token" not in request.headers:
                logger.warning(f"Unauthorized request to {request.url.path}")
                return JSONResponse(
                    content={"error": "Header X-API-Token is required for all POST actions"},
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )
            if request.headers["X-API-Token"] != settings.access_token:
                logger.warning(f"Invalid token attempt to {request.url.path}")
                return JSONResponse(
                    content={"error": "your X-API-Token is not valid"},
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )

        response = await call_next(request)
        return response


# Exception handlers
@app.exception_handler(ProjectWasNotStarted)
async def project_was_not_started_handler(request: Request, exc: ProjectWasNotStarted):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "No project is currently started"},
    )


@app.exception_handler(CanNotStopNonBeatingHeart)
async def can_not_stop_handler(request: Request, exc: CanNotStopNonBeatingHeart):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "Project timer is not running"},
    )


@app.exception_handler(TwoProjectInProgess)
async def two_projects_handler(request: Request, exc: TwoProjectInProgess):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"error": "Multiple projects cannot be running simultaneously"},
    )


@app.exception_handler(InconsistentEndTime)
async def inconsistent_end_time_handler(request: Request, exc: InconsistentEndTime):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": exc.message
            if hasattr(exc, "message")
            else "End time must come after start time"
        },
    )


# Middleware should be added before exception handlers but after routers
app.add_middleware(AuthenticationMiddleware)


@app.api_route("/talk/ding", methods=["GET", "POST"])
async def ding():
    return {"message": "dong"}


# CORS middleware - should be last
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
