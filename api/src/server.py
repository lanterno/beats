"""FastAPI application entry point with DDD architecture."""

import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from beats.api.routers.analytics import router as analytics_router
from beats.api.routers.auth import get_session_manager
from beats.api.routers.auth import router as auth_router
from beats.api.routers.beats import router as beats_router
from beats.api.routers.daily_notes import router as daily_notes_router
from beats.api.routers.device import router as device_router
from beats.api.routers.export import router as export_router
from beats.api.routers.intelligence import router as intelligence_router
from beats.api.routers.intentions import router as intentions_router
from beats.api.routers.projects import router as projects_router
from beats.api.routers.timer import router as timer_router
from beats.api.routers.webhooks import router as webhooks_router
from beats.domain.exceptions import DomainException
from beats.infrastructure.database import Database
from beats.settings import settings

logger = logging.getLogger(__name__)

# Paths that never require authentication
PUBLIC_PREFIXES = ("/api/auth", "/health", "/talk/ding")


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
    version="0.5.0",
    lifespan=lifespan,
)

# CORS origins
origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://localhost:8080",
    "https://beats.elghareeb.space",
    "https://lifepete.com",
    "https://api.beats.elghareeb.space",
]


async def _resolve_owner_id() -> str | None:
    """Look up the first (owner) user's ID for X-API-Token auth."""
    try:
        db = Database.get_db()
        doc = await db.users.find_one({}, sort=[("created_at", 1)])
        if doc:
            return str(doc["_id"])
    except Exception:
        pass
    return None


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Async middleware for API authentication.

    All requests (except public paths) require authentication.
    Supports two methods:
    1. JWT Bearer token (WebAuthn sessions) - preferred
    2. X-API-Token header (legacy, for backwards compatibility)

    Sets request.state.user_id on successful auth.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Allow OPTIONS requests (CORS preflight) to pass through
        if request.method == "OPTIONS":
            return await call_next(request)

        # Allow public endpoints without auth
        if any(request.url.path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
            return await call_next(request)

        # Try JWT Bearer token first (WebAuthn session)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            session_manager = get_session_manager()
            payload = session_manager.validate_session_token(token)
            if payload is not None:
                request.state.user_id = payload["sub"]
                return await call_next(request)
            else:
                origin = request.headers.get("origin", "unknown")
                logger.warning(
                    "Invalid JWT token to %s from origin: %s",
                    request.url.path,
                    origin,
                )
                return JSONResponse(
                    content={"error": "Invalid or expired session token"},
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )

        # Fall back to legacy X-API-Token header
        if "X-API-Token" in request.headers:
            if request.headers["X-API-Token"] == settings.access_token:
                # Map to owner user
                owner_id = await _resolve_owner_id()
                if owner_id:
                    request.state.user_id = owner_id
                return await call_next(request)
            else:
                origin = request.headers.get("origin", "unknown")
                path = request.url.path
                logger.warning("Invalid X-API-Token to %s from origin: %s", path, origin)
                return JSONResponse(
                    content={"error": "Your X-API-Token is not valid"},
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )

        # No valid authentication provided
        origin = request.headers.get("origin", "unknown")
        logger.warning("Unauthorized request to %s from: %s", request.url.path, origin)
        return JSONResponse(
            content={"error": "Authentication required. Use Bearer token or X-API-Token."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


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
app.include_router(auth_router)
app.include_router(projects_router)
app.include_router(beats_router)
app.include_router(timer_router)
app.include_router(analytics_router)
app.include_router(intentions_router)
app.include_router(daily_notes_router)
app.include_router(device_router)
app.include_router(export_router)
app.include_router(intelligence_router)
app.include_router(webhooks_router)

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
