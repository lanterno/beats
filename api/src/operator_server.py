"""The operator deployment's entry point — the second composition root.

`uvicorn operator_server:app` beside `uvicorn server:app`, composing the same
`beats` library (docs/backoffice.md § Architecture): same image,
the Cloud Run service's command picks the module. What that buys over a mode
switch is isolation by construction:

- **The public app cannot serve an operator route**, because it does not
  import one — and this app imports none of the public routers, nothing in
  `beats.auth`, and never `beats.settings`, so **it never holds JWT_SECRET**
  (a test imports this module in a fresh interpreter and finds
  `beats.settings` out of `sys.modules`).
- **The lifespan is honest**: it connects its own client into `app.state`
  and stops. No migrations, no index building — the public API is the one
  deployment that builds indexes — and nothing that needs a write grant on
  collections the operator's narrow database user must not touch.
- **`request.state.user_id` is never set here.** The middleware sets
  `request.state.operator` instead, so a user-scoped dependency imported by
  mistake fails loudly on a missing attribute rather than quietly scoping to
  the operator.

In front of the service is Google IAP; this app verifies the signed
assertion itself (`beats/operator/iap.py`) and matches its `sub` against the
allowlist in `OperatorSettings` — IAP's IAM binding says who reaches the
app, the allowlist says what they may do, so an IAM grant made by mistake
reaches a 403. The browser's credential is IAP's cookie, which another
site's page can make the browser send: every command is a POST whose
`Origin` must be this app's own (and whose `Sec-Fetch-Site`, where the
browser sends one, must be `same-origin`), the account lookup included.
"""

import logging
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, Response
from pymongo import AsyncMongoClient
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.staticfiles import StaticFiles

from beats.api.errors import envelope as error_envelope
from beats.api.errors import http_exception_handler, validation_exception_handler
from beats.api.routers.operator import router as operator_router
from beats.domain.exceptions import DomainException
from beats.operator.health import GoogleMonitoring, HealthCache
from beats.operator.iap import IAPRejected, IAPUnavailable, IAPVerifier
from beats.operator.settings import OperatorSettings

logger = logging.getLogger(__name__)

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
for _app_logger in ("beats", __name__):
    logging.getLogger(_app_logger).setLevel(logging.INFO)

settings = OperatorSettings()

# The built back office (backoffice/dist, copied here by its build). Locally
# Vite serves the UI, so the app runs without it only under the dev stand-in;
# a deployment missing it is a broken image and must not start.
STATIC_DIR = Path(__file__).resolve().parent / "beats" / "operator" / "static"

_verifier = IAPVerifier(settings.iap_audience) if settings.iap_audience else None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    """Connects, and stops. Deliberately not `Database`, which keeps its
    client on the class: two apps in one process (the test suite) would
    share one, and this app's disconnect would set it to None under the
    public app's event loop."""
    if not settings.dev_operator and not (STATIC_DIR / "index.html").exists():
        raise RuntimeError(
            "beats/operator/static/index.html is missing: the image was built without "
            "the back office. Set BACKOFFICE_DEV_OPERATOR only for local development."
        )
    logger.info("Connecting to database...")
    client: AsyncMongoClient = AsyncMongoClient(settings.db_dsn)
    app.state.operator_db = client[settings.db_name]
    app.state.operator_settings = settings
    app.state.health_source = GoogleMonitoring(settings.api_service_name)
    app.state.health_cache = HealthCache()
    logger.info("Database connected.")
    yield
    logger.info("Disconnecting from database...")
    await client.close()


app = FastAPI(
    title="Beats operator API",
    description="The control plane: operational metadata, never user content",
    lifespan=lifespan,
    # The spec is served to the operator alone, but there is no reason to
    # serve it at all: backoffice/ reads the dumped copy.
    openapi_url=None,
    docs_url=None,
    redoc_url=None,
)


class OperatorAuthMiddleware(BaseHTTPMiddleware):
    """Resolves the IAP assertion — and no other credential — into
    `request.state.operator`, and holds the cross-site line on writes."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Who: IAP's signed assertion, or the local stand-in. No bearer
        # token, no cookie of our own, nothing else.
        if settings.dev_operator:
            sub = settings.dev_operator
        else:
            assertion = request.headers.get("x-goog-iap-jwt-assertion", "")
            if not assertion or _verifier is None:
                return error_envelope(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="No IAP assertion on this request",
                    code="NO_IAP_ASSERTION",
                )
            try:
                claims = await _verifier.verify(assertion)
            except IAPRejected as e:
                logger.warning("IAP assertion rejected: %s", e)
                return error_envelope(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="The IAP assertion was rejected",
                    code="IAP_REJECTED",
                )
            except IAPUnavailable as e:
                logger.warning("IAP keys unavailable: %s", e)
                return error_envelope(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="IAP's key set cannot be fetched right now",
                    code="IAP_UNAVAILABLE",
                )
            sub = str(claims.get("sub", ""))

        identity = settings.identity_for(sub)
        if identity is None:
            # Reached the app (IAP let them through) but not on the
            # allowlist: an IAM grant made by mistake ends here.
            return error_envelope(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This identity is not on the operator allowlist",
                code="OPERATOR_NOT_ALLOWED",
            )

        # The browser's credential is IAP's cookie, which a request another
        # site's page starts would carry too. JSON from another origin needs
        # a preflight nothing here grants, and every write — the account
        # lookup included, which reads — must come from this app's own pages.
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            fetch_site = request.headers.get("sec-fetch-site")
            if origin != settings.origin or (
                fetch_site is not None and fetch_site != "same-origin"
            ):
                return error_envelope(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cross-origin writes are refused",
                    code="OPERATOR_BAD_ORIGIN",
                )

        request.state.operator = identity
        return await call_next(request)


app.exception_handler(HTTPException)(http_exception_handler)
app.exception_handler(RequestValidationError)(validation_exception_handler)


@app.exception_handler(DomainException)
async def domain_exception_handler(request: Request, exc: DomainException):
    """The services the commands delegate to raise the same domain errors
    they raise for members (ORGANISATION_HAS_OWNER, ACCOUNT_NOT_FOUND, …);
    the envelope is the shared one."""
    return error_envelope(
        status_code=exc.status_code,
        detail=exc.message,
        code=getattr(exc, "code", None),
        fields=getattr(exc, "fields", None),
    )


app.include_router(operator_router)
app.add_middleware(OperatorAuthMiddleware)

# The UI: the built SPA's assets, and index.html for any path outside
# /api/operator — the SPA's own routes. Served by this app so the browser has
# one origin and one IAP session (docs/backoffice.md § Deployment).
if (STATIC_DIR / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str, request: Request) -> FileResponse:
        file = STATIC_DIR / path
        if path and file.is_file() and file.resolve().is_relative_to(STATIC_DIR):
            return FileResponse(file)
        return FileResponse(STATIC_DIR / "index.html")
