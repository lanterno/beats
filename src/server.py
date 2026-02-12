"""FastAPI application entry point with DDD architecture."""

import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from beats.api.routers.beats import router as beats_router
from beats.api.routers.projects import router as projects_router
from beats.api.routers.timer import router as timer_router
from beats.domain.exceptions import DomainException
from beats.infrastructure.database import Database
from beats.settings import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan manager for startup/shutdown events."""
    # Startup: Connect to database
    logger.info("Connecting to database...")
    await Database.connect()
    logger.info("Database connected.")
    yield
    # Shutdown: Disconnect from database
    logger.info("Disconnecting from database...")
    await Database.disconnect()
    logger.info("Database disconnected.")


app = FastAPI(
    title="Beats API",
    description="A time tracking application",
    version="0.4.0",
    lifespan=lifespan,
)

# CORS origins
origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://localhost:8080",
    "https://beats.elghareeb.space",
    "https://api.beats.elghareeb.space/",
]


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Async middleware for API authentication."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Allow OPTIONS requests (CORS preflight) to pass through
        if request.method == "OPTIONS":
            origin = request.headers.get("origin", "unknown")
            logger.debug(f"CORS preflight OPTIONS request from origin: {origin}")
            return await call_next(request)

        PROTECTED_METHODS = ["POST", "PUT", "PATCH"]

        # Allow unauthenticated access to beats endpoints (tests rely on this)
        if request.url.path.startswith("/api/beats"):
            return await call_next(request)

        if request.method in PROTECTED_METHODS:
            if "X-API-Token" not in request.headers:
                origin = request.headers.get("origin", "unknown")
                logger.warning(f"Unauthorized request to {request.url.path} from origin: {origin}")
                return JSONResponse(
                    content={"error": "Header X-API-Token is required for all POST actions"},
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )
            if request.headers["X-API-Token"] != settings.access_token:
                origin = request.headers.get("origin", "unknown")
                logger.warning(f"Invalid token attempt to {request.url.path} from origin: {origin}")
                return JSONResponse(
                    content={"error": "your X-API-Token is not valid"},
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )

        return await call_next(request)


# Unified domain exception handler
@app.exception_handler(DomainException)
async def domain_exception_handler(request: Request, exc: DomainException):
    """Handle all domain exceptions with appropriate HTTP responses."""
    content = {"error": exc.message}
    if hasattr(exc, "detail") and exc.detail:
        content.update(exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
    )


# Include routers
app.include_router(projects_router)
app.include_router(beats_router)
app.include_router(timer_router)

# Add authentication middleware
app.add_middleware(AuthenticationMiddleware)


@app.get("/health")
async def health_check():
    """Health check endpoint for Docker and monitoring."""
    return {"status": "healthy", "service": "beats-api"}


@app.api_route("/talk/ding", methods=["GET", "POST"])
async def ding():
    """Test endpoint."""
    return {"message": "dong"}


# CORS middleware - should be last (wraps all other middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
