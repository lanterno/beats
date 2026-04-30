"""Unified error envelope for the Beats API.

All HTTP errors emit a body of the shape::

    {
        "detail": "<human-readable message>",
        "code": "<MACHINE_READABLE_CODE>",
        "fields": [...],  # only on 422 validation failures
    }

The ``detail`` key keeps the historical FastAPI shape so existing clients
that read ``response.json().detail`` keep working. ``code`` is new and is
intended to be the canonical way new clients route errors. ``fields``,
when present, lists per-field validation problems with normalized paths.
"""

from typing import Any

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

# Default machine-readable code for each common status. Routers may override
# by raising ``HTTPException(detail={"code": "PROJECT_NOT_ARCHIVED", "message": ...})``
# but the simple ``raise HTTPException(404, "Project not found")`` form
# auto-falls back to NOT_FOUND.
_DEFAULT_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    410: "GONE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    502: "UPSTREAM_ERROR",
    503: "SERVICE_UNAVAILABLE",
    504: "UPSTREAM_TIMEOUT",
}


def envelope(
    *,
    status_code: int,
    detail: str,
    code: str | None = None,
    fields: list[dict[str, Any]] | None = None,
) -> JSONResponse:
    """Build a normalized error response."""
    body: dict[str, Any] = {
        "detail": detail,
        "code": code or _DEFAULT_CODES.get(status_code, f"HTTP_{status_code}"),
    }
    if fields is not None:
        body["fields"] = fields
    return JSONResponse(status_code=status_code, content=body)


async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    """Wrap raises of ``HTTPException`` into the standard envelope.

    The ``detail`` argument is normally a string. If a router raises with a
    dict (e.g. ``{"code": "FOO", "message": "..."}``) we honor those keys so
    routers can opt into custom machine-readable codes without subclassing
    HTTPException.
    """
    raw = exc.detail
    if isinstance(raw, dict):
        code = raw.get("code")
        detail = raw.get("message") or raw.get("detail") or str(raw)
        fields = raw.get("fields")
    else:
        code = None
        detail = str(raw) if raw is not None else ""
        fields = None
    return envelope(
        status_code=exc.status_code,
        detail=detail,
        code=code,
        fields=fields,
    )


async def validation_exception_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Convert pydantic / FastAPI validation errors into the envelope.

    Each field reports a ``path`` (dot-joined location, with the ``body``
    prefix stripped so paths feel natural to consumers), the human message,
    and the validation type.
    """
    fields: list[dict[str, Any]] = []
    for err in exc.errors():
        loc = [p for p in err.get("loc", []) if p not in ("body", "query", "path")]
        fields.append(
            {
                "path": ".".join(str(p) for p in loc),
                "message": err.get("msg", ""),
                "type": err.get("type", ""),
            }
        )
    summary = (
        "Validation failed for one field"
        if len(fields) == 1
        else f"Validation failed for {len(fields)} fields"
    )
    return envelope(
        status_code=422,
        detail=summary,
        code="VALIDATION_ERROR",
        fields=fields,
    )
