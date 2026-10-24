"""FastAPI application entry point with DDD architecture."""

import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware

from beats.api.errors import envelope as error_envelope
from beats.api.errors import http_exception_handler, validation_exception_handler
from beats.api.middleware import IdempotencyMiddleware, ensure_mutation_log_indexes
from beats.api.routers.absences import router as absences_router
from beats.api.routers.account import router as account_router
from beats.api.routers.adjustments import router as adjustments_router
from beats.api.routers.analytics import router as analytics_router
from beats.api.routers.auth import get_session_manager, limiter
from beats.api.routers.auth import router as auth_router
from beats.api.routers.beats import router as beats_router
from beats.api.routers.billing import router as billing_router
from beats.api.routers.biometrics import router as biometrics_router
from beats.api.routers.calendar import router as calendar_router
from beats.api.routers.clients import router as clients_router
from beats.api.routers.coach import router as coach_router
from beats.api.routers.device import router as device_router
from beats.api.routers.export import router as export_router
from beats.api.routers.fitbit import router as fitbit_router
from beats.api.routers.github import router as github_router
from beats.api.routers.intelligence import router as intelligence_router
from beats.api.routers.meta import router as meta_router
from beats.api.routers.oura import router as oura_router
from beats.api.routers.planning import router as planning_router
from beats.api.routers.projects import router as projects_router
from beats.api.routers.reports import router as reports_router
from beats.api.routers.signals import router as signals_router
from beats.api.routers.sso import router as sso_router
from beats.api.routers.timer import router as timer_router
from beats.api.routers.webhooks import router as webhooks_router
from beats.auth import device_access
from beats.domain.exceptions import DomainException
from beats.infrastructure.database import Database
from beats.infrastructure.migrations import (
    clear_personal_goal_on_day_jobs,
    migrate_project_kinds,
)
from beats.infrastructure.plan_migration import move_sunday_plans_to_monday
from beats.infrastructure.repositories import MongoDeviceRegistrationRepository

logger = logging.getLogger(__name__)

# uvicorn's default logging config covers only its own loggers and leaves the
# root logger without a handler, so without this the app's INFO lines — the
# startup migrations' audit trail among them — reach nothing and are dropped
# (Python's last-resort handler passes WARNING and up). The root handler sits
# at WARNING to keep third-party INFO chatter (httpx logs every request) out;
# the app's own loggers are opened at INFO. `basicConfig` does nothing when
# a handler is already installed — pytest's capture, a `--log-config` — so
# those keep their setup.
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
for _app_logger in ("beats", __name__):
    logging.getLogger(_app_logger).setLevel(logging.INFO)

try:
    API_VERSION = package_version("beats")
except PackageNotFoundError:  # running from a source tree without an install
    API_VERSION = "0.0.0+unknown"

# Paths that never require authentication.
#
# /api/reports is the only one that serves a user's data. A report link's
# token is the whole of its authorisation, and the route serves exactly one
# shape, assembled from one client's inputs (docs/billing.md, phase 1c).
# Nothing else belongs here on those terms.
PUBLIC_PREFIXES = (
    "/api/auth",
    "/health",
    "/api/device/pair/exchange",
    "/api/reports",
)

# Paths that device tokens (daemon) are allowed to access.
#
# Money lives under /api/clients and /api/billing on purpose — clients and
# their rates, project billing, billable marks, and billing budgets with what
# they have spent. Never add them here, and never put billing under
# /api/projects or /api/beats, which are prefix matches (docs/billing.md).
DEVICE_ALLOWED_PREFIXES = (
    # Wall-clock firmware reads /status on a 10s poll for the timer
    # state + today_minutes + theme. Without this prefix, the
    # device-token middleware 403s every poll and the wall-clock
    # never sees real data — only the test_device_status_shape_…
    # coverage caught the absence.
    "/api/device/status",
    "/api/device/heartbeat",
    "/api/device/favorites",
    "/api/device/weekly",
    "/api/signals",
    "/api/biometrics/daily",
    "/api/timer",
    "/api/projects",
    # Companion's "How did it go?" prompt updates the just-stopped beat with
    # an optional note + tags via PUT /api/beats/.
    "/api/beats",
    "/api/coach/brief",
    # Companion timer screen renders today/week totals + streak from the heatmap.
    # Other /api/analytics/* endpoints remain off-limits.
    "/api/analytics/heatmap",
    # Companion's post-stop "How did it go?" sheet uses the user's prior tags
    # as one-tap chips alongside the freeform input.
    "/api/analytics/tags",
    # The Mac app's Body screen reads the week's biometrics (GET /api/biometrics/),
    # not just the daily push above, and its Settings show and change the Fitbit
    # and Oura connections.
    "/api/biometrics",
    "/api/fitbit",
    "/api/oura",
    # Its Today screen lays the day's calendar beside the day's sessions.
    "/api/calendar/events",
    # Its Coach screen chats. Every message spends the user's coach budget,
    # which /api/coach/chat enforces on its own (BUDGET_EXCEEDED).
    "/api/coach/chat",
)

# Paths a device token may only read (GET, HEAD). The rest of each prefix
# changes or deletes data a paired device has no reason to touch.
DEVICE_READ_ONLY_PREFIXES = (
    # The Mac app's Coach shows what the coach remembers. Deleting the memory
    # (DELETE /memory) and rewriting it (POST /memory/rewrite, which also
    # spends budget) stay with a signed-in browser.
    "/api/coach/memory",
)


def device_may_reach(method: str, path: str) -> bool:
    """Whether a device token may make this request at all."""
    if any(path.startswith(p) for p in DEVICE_ALLOWED_PREFIXES):
        return True
    return method in ("GET", "HEAD") and any(path.startswith(p) for p in DEVICE_READ_ONLY_PREFIXES)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Application lifespan manager for startup/shutdown events."""
    # Startup: Connect to database
    logger.info("Connecting to database...")
    await Database.connect()
    logger.info("Database connected.")
    # A project without `kind` predates contracts; stamp it once, here, so
    # the terms derived from its overrides are stored and then owned by the
    # user rather than recomputed on every read. Then — in this order, since
    # the contract is derived from the goal — drop the personal goal on the
    # day jobs whose contract every reader now takes instead.
    await migrate_project_kinds(Database.get_db())
    await clear_personal_goal_on_day_jobs(Database.get_db())
    # The Plan page stored a week under its Monday's UTC date, a Sunday east of
    # Greenwich; it now uses the local date, so those plans move to the Monday.
    await move_sunday_plans_to_monday(Database.get_db())
    await ensure_mutation_log_indexes()
    yield
    # Shutdown: Disconnect from database
    logger.info("Disconnecting from database...")
    await Database.disconnect()
    logger.info("Database disconnected.")


app = FastAPI(
    title="Beats API",
    description="A time tracking application",
    version=API_VERSION,
    lifespan=lifespan,
)

# A single-origin deployment (the SPA and this API behind one host) needs
# nothing here. These are for the two cases that are genuinely cross-origin:
# local development against a separately served UI, and the Cloud Run / Firebase
# deployment behind lifepete.com, which is split across two origins by design.
# That deployment is still live — dropping its origins here breaks its SPA
# without breaking anything a test or a local run would notice.
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

                # Verify device is not revoked. Cached briefly: the wall clock
                # polls every 10s, and re-reading the flag each time was a Mongo
                # round-trip per poll. Revoking clears the entry, so this only
                # delays a revocation made directly in the database.
                allowed = device_access.get(device_id)
                if allowed is None:
                    db = Database.get_db()
                    repo = MongoDeviceRegistrationRepository(db.device_registrations)
                    reg = await repo.get_by_device_id(device_id)
                    allowed = reg is not None and not reg.revoked
                    device_access.remember(device_id, allowed=allowed)
                if not allowed:
                    return error_envelope(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Device token has been revoked",
                        code="DEVICE_REVOKED",
                    )

                # Check path allowlist
                if not device_may_reach(request.method, request.url.path):
                    return error_envelope(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Device token not authorized for this endpoint",
                        code="DEVICE_PATH_FORBIDDEN",
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
                return error_envelope(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired session token",
                    code="INVALID_TOKEN",
                )

        # Public endpoints pass through without auth
        if is_public:
            return await call_next(request)

        # No valid authentication provided for protected endpoint
        origin = request.headers.get("origin", "unknown")
        logger.warning("Unauthorized request to %s from: %s", request.url.path, origin)
        return error_envelope(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide a Bearer token.",
            code="MISSING_TOKEN",
        )


# Rate limiting
app.state.limiter = limiter
# Registered through the decorator rather than add_exception_handler: Starlette
# types a handler as taking any Exception, and these take the one they are for.
app.exception_handler(RateLimitExceeded)(_rate_limit_exceeded_handler)


# Unified error envelope: every HTTP error and validation failure flows
# through the handlers in beats.api.errors so clients see a consistent
# {detail, code, fields?} shape.
app.exception_handler(HTTPException)(http_exception_handler)
app.exception_handler(RequestValidationError)(validation_exception_handler)


@app.exception_handler(DomainException)
async def domain_exception_handler(request: Request, exc: DomainException):
    """Handle all domain exceptions with the standard error envelope."""
    return error_envelope(
        status_code=exc.status_code,
        detail=exc.message,
        code=getattr(exc, "code", None),
        fields=getattr(exc, "fields", None),
    )


# Include routers
app.include_router(auth_router)
app.include_router(sso_router)
app.include_router(account_router)
app.include_router(projects_router)
app.include_router(absences_router)
app.include_router(adjustments_router)
app.include_router(meta_router)
app.include_router(clients_router)
app.include_router(billing_router)
app.include_router(reports_router)
app.include_router(beats_router)
app.include_router(timer_router)
app.include_router(analytics_router)
app.include_router(device_router)
app.include_router(export_router)
app.include_router(intelligence_router)
app.include_router(webhooks_router)
app.include_router(calendar_router)
app.include_router(github_router)
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


# CORS middleware - should be last (wraps all other middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
