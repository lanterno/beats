"""Oura API router — personal access token connection and status."""

from fastapi import APIRouter
from pydantic import BaseModel

from beats.api.dependencies import OuraServiceDep

router = APIRouter(prefix="/api/oura", tags=["oura"])


class OuraConnectRequest(BaseModel):
    access_token: str


@router.post("/connect")
async def connect(body: OuraConnectRequest, service: OuraServiceDep) -> dict:
    """Connect Oura by validating a personal access token."""
    integration = await service.connect(body.access_token)
    return {
        "connected": True,
        "oura_user_id": integration.oura_user_id,
    }


@router.delete("/disconnect")
async def disconnect(service: OuraServiceDep) -> dict[str, bool]:
    """Remove the Oura integration."""
    deleted = await service.disconnect()
    return {"disconnected": deleted}


@router.get("/status")
async def get_status(service: OuraServiceDep) -> dict:
    """Check if Oura is connected."""
    integration = await service.repo.get()
    if integration and integration.enabled:
        return {
            "connected": True,
            "oura_user_id": integration.oura_user_id,
        }
    return {"connected": False, "oura_user_id": None}
