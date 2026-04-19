"""Fitbit API router — OAuth flow and status."""

from fastapi import APIRouter

from beats.api.dependencies import FitbitServiceDep

router = APIRouter(prefix="/api/fitbit", tags=["fitbit"])


@router.get("/auth-url")
async def get_auth_url(service: FitbitServiceDep) -> dict[str, str]:
    """Get the Fitbit OAuth consent URL."""
    return {"url": service.get_auth_url()}


@router.post("/connect")
async def connect(code: str, service: FitbitServiceDep) -> dict:
    """Exchange an OAuth code for Fitbit tokens."""
    integration = await service.exchange_code(code)
    return {
        "connected": True,
        "fitbit_user_id": integration.fitbit_user_id,
    }


@router.delete("/disconnect")
async def disconnect(service: FitbitServiceDep) -> dict[str, bool]:
    """Remove the Fitbit integration."""
    deleted = await service.disconnect()
    return {"disconnected": deleted}


@router.get("/status")
async def get_status(service: FitbitServiceDep) -> dict:
    """Check if Fitbit is connected."""
    integration = await service.repo.get()
    if integration and integration.enabled:
        return {
            "connected": True,
            "fitbit_user_id": integration.fitbit_user_id,
        }
    return {"connected": False, "fitbit_user_id": None}
