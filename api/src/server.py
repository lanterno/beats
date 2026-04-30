"""FastAPI application entry point with DDD architecture."""

import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from beats.api.middleware import IdempotencyMiddleware, ensure_mutation_log_indexes
from beats.api.routers.account import router as account_router
from beats.api.routers.analytics import router as analytics_router
from beats.api.routers.auth import get_session_manager, limiter
from beats.api.routers.auth import router as auth_router
from beats.api.routers.auto_start import router as auto_start_router
from beats.api.routers.beats import router as beats_router
from beats.api.routers.biometrics import router as biometrics_router
from beats.api.routers.calendar import router as calendar_router
from beats.api.routers.coach import router as coach_router
from beats.api.routers.daily_notes import router as daily_notes_router
from beats.api.routers.device import router as device_router
from beats.api.routers.export import router as export_router
from beats.api.routers.fitbit import router as fitbit_router
from beats.api.routers.github import router as github_router
from beats.api.routers.intelligence import router as intelligence_router
from beats.api.routers.intentions import router as intentions_router
from beats.api.routers.oura import router as oura_router
from beats.api.routers.planning import router as planning_router
from beats.api.routers.projects import router as projects_router
from beats.api.routers.signals import router as signals_router
from beats.api.routers.timer import router as timer_router
from beats.api.routers.webhooks import router as webhooks_router
from beats.domain.exceptions import DomainException
from beats.infrastructure.database import Database
from beats.infrastructure.repositories import MongoDeviceRegistrationRepository

logger = logging.getLogger(__name__)

# Paths that never require authentication
PUBLIC_PREFIXES = ("/api/auth", "/health", "/talk/ding", "/api/device/pair/exchange")

# Paths that device tokens (daemon) are allowed to access
DEVICE_ALLOWED_PREFIXES = (
    "/api/device/heartbeat",
    "/api/device/favorites",
    "/api/signals",
    "/api/biometrics/daily",
    "/api/timer",
    "/api/projects",
    # Companion's "How did it go?" prompt updates the just-stopped beat with
    # an optional note + tags via PUT /api/beats/.
    "/api/beats",
    "/api/coach/brief",
    "/api/coach/review",
    "/api/intentions",
    "/api/daily-notes",
    # Companion timer screen renders today/week totals + streak from the heatmap.
    # Other /api/analytics/* endpoints remain off-limits.
    "/api/analytics/heatmap",
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan manager for startup/shutdown events."""
    # Startup: Connect to database
    logger.info("Connecting to database...")
    await Database.connect()
    logger.info("Database connected.")
    await ensure_mutation_log_indexes()
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
    "https://lifepete.com",
    "https://api.lifepete.com",
]


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """Async middleware for API authentication.

    All requests (except public paths) require a JWT Bearer token (WebAuthn sessions).
    Sets request.state.user_id on successful auth.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Allow OPTIONS requests (CORS preflight) to pass through
        if request.method == "OPTIONS":
            return await call_next(request)

        is_public = any(request.url.path.startswith(prefix) for prefix in PUBLIC_PREFIXES)

        # Try to extract user_id from Bearer token (for both public and protected paths)
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            session_manager = get_session_manager()

            # Try session token first
            payload = session_manager.validate_session_token(token)
            if payload is not None:
                request.state.user_id = payload["sub"]
                return await call_next(request)

            # Try device token
            device_payload = session_manager.validate_device_token(token)
            if device_payload is not None:
                device_id = device_payload["device_id"]

                # Verify device is not revoked
                db = Database.get_db()
                repo = MongoDeviceRegistrationRepository(db.device_registrations)
                reg = await repo.get_by_device_id(device_id)
                if not reg or reg.revoked:
                    return JSONResponse(
                        content={"error": "Device token has been revoked"},
                        status_code=status.HTTP_403_FORBIDDEN,
                    )

                # Check path allowlist
                path = request.url.path
                if not any(path.startswith(p) for p in DEVICE_ALLOWED_PREFIXES):
                    return JSONResponse(
                        content={"error": "Device token not authorized for this endpoint"},
                        status_code=status.HTTP_403_FORBIDDEN,
                    )

                request.state.user_id = device_payload["sub"]
                request.state.device_id = device_id
                return await call_next(request)

            if not is_public:
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

        # Public endpoints pass through without auth
        if is_public:
            return await call_next(request)

        # No valid authentication provided for protected endpoint
        origin = request.headers.get("origin", "unknown")
        logger.warning("Unauthorized request to %s from: %s", request.url.path, origin)
        return JSONResponse(
            content={"error": "Authentication required. Provide a Bearer token."},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


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
app.include_router(account_router)
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
app.include_router(calendar_router)
app.include_router(github_router)
app.include_router(auto_start_router)
app.include_router(planning_router)
app.include_router(coach_router)
app.include_router(signals_router)
app.include_router(biometrics_router)
app.include_router(fitbit_router)
app.include_router(oura_router)

# Idempotency runs INSIDE authentication (it needs request.state.user_id), so
# it is added to the stack first — add_middleware wraps from inside out.
app.add_middleware(IdempotencyMiddleware)

# Add authentication middleware
app.add_middleware(AuthenticationMiddleware)


@app.get("/health")
async def health_check():
    """Health check endpoint for Docker and monitoring."""
    return {"status": "healthy", "service": "beats-api"}


@app.get("/talk/ding")
async def ding_get():
    """Test endpoint."""
    return {"message": "dong"}


@app.post("/talk/ding")
async def ding_post():
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
