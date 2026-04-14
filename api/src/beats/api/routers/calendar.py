"""Calendar API router — Google Calendar OAuth and event fetching."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Query

from beats.api.dependencies import CalendarServiceDep

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


@router.get("/auth-url")
async def get_auth_url(service: CalendarServiceDep):
    """Get the Google OAuth consent URL to start the connection flow."""
    return {"url": service.get_auth_url()}


@router.post("/connect")
async def connect_calendar(code: str, service: CalendarServiceDep):
    """Exchange an OAuth authorization code for tokens and store the integration."""
    integration = await service.exchange_code(code)
    return {"connected": True, "provider": integration.provider}


@router.get("/events")
async def get_calendar_events(
    service: CalendarServiceDep,
    start: str = Query(
        default_factory=lambda: datetime.now(UTC).replace(hour=0, minute=0, second=0).isoformat()
    ),
    end: str = Query(
        default_factory=lambda: (
            datetime.now(UTC).replace(hour=0, minute=0, second=0) + timedelta(days=1)
        ).isoformat()
    ),
):
    """Fetch calendar events in a time range."""
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    events = await service.fetch_events(start_dt, end_dt)
    return events


@router.delete("/disconnect")
async def disconnect_calendar(service: CalendarServiceDep):
    """Remove the Google Calendar integration."""
    deleted = await service.disconnect()
    return {"disconnected": deleted}


@router.get("/status")
async def calendar_status(service: CalendarServiceDep):
    """Check if a calendar integration is connected."""
    integration = await service.repo.get()
    return {
        "connected": integration is not None and integration.enabled,
        "provider": integration.provider if integration else None,
    }
