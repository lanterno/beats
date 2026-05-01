"""Device API router — endpoints for ESP32 wall clock and daemon pairing."""

import base64
import hashlib
import os
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel

from beats.api.dependencies import (
    BeatServiceDep,
    CurrentUserId,
    DeviceRegistrationRepoDep,
    PairingCodeRepoDep,
    ProjectServiceDep,
    TimerServiceDep,
)
from beats.api.routers.auth import get_session_manager, limiter
from beats.domain.models import DeviceRegistration, PairingCode

router = APIRouter(prefix="/api/device", tags=["device"])

# Same palette as the frontend (ui/client/entities/project/model/colors.ts)
PROJECT_COLORS = [
    "#5B9CF6",  # Blue
    "#34D399",  # Green
    "#FBBF24",  # Amber
    "#F87171",  # Red
    "#A78BFA",  # Purple
    "#F472B6",  # Pink
    "#22D3EE",  # Cyan
    "#FB923C",  # Orange
    "#818CF8",  # Indigo
    "#A3E635",  # Lime
]


def assign_color(project_id: str) -> str:
    """Replicate frontend color assignment."""
    h = sum(ord(c) for c in project_id)
    return PROJECT_COLORS[h % len(PROJECT_COLORS)]


def hex_to_rgb(hex_color: str) -> list[int]:
    """Convert hex color to [r, g, b]."""
    h = hex_color.lstrip("#")
    return [int(h[i : i + 2], 16) for i in (0, 2, 4)]


# Schemas


# Theme accent colors — mirrors ui/client/shared/lib/useTheme.ts
THEME_ACCENTS = {
    "ember": "#d4952a",
    "midnight": "#6699cc",
    "forest": "#66b366",
    "mono": "#999999",
    "sunset": "#e06040",
}


class DeviceStatusResponse(BaseModel):
    clocked_in: bool
    project_name: str | None = None
    project_id: str | None = None
    project_color_rgb: list[int] = [0, 0, 0]
    elapsed_minutes: int = 0
    daily_total_minutes: int = 0
    energy_level: int = 0  # 0-7 for energy meter LEDs
    theme_accent_rgb: list[int] = [212, 149, 42]  # Default ember


class DeviceFavoriteProject(BaseModel):
    id: str
    name: str
    color_rgb: list[int]


class DeviceHeartbeatRequest(BaseModel):
    battery_voltage: float | None = None
    wifi_rssi: int | None = None
    uptime_seconds: int | None = None


class DeviceHeartbeatResponse(BaseModel):
    battery_voltage: float | None = None
    wifi_rssi: int | None = None
    uptime_seconds: int | None = None
    last_seen: datetime | None = None


# In-memory heartbeat storage (single device)
_last_heartbeat: dict | None = None


@router.get("/status", response_model=DeviceStatusResponse)
async def get_device_status(
    timer_service: TimerServiceDep,
    beat_service: BeatServiceDep,
    theme: str = Query(default="ember"),
) -> DeviceStatusResponse:
    """Get timer state optimized for ESP32 wall clock firmware."""
    theme_hex = THEME_ACCENTS.get(theme, THEME_ACCENTS["ember"])
    theme_rgb = hex_to_rgb(theme_hex)

    active_beat = await timer_service.beat_repo.get_active()

    if not active_beat:
        # Calculate daily total even when not clocked in
        daily_minutes = await _get_daily_total_minutes(beat_service)
        energy = min(int(daily_minutes / 60), 7)
        return DeviceStatusResponse(
            clocked_in=False,
            daily_total_minutes=daily_minutes,
            energy_level=energy,
            theme_accent_rgb=theme_rgb,
        )

    # Timer is running
    project = await timer_service.project_repo.get_by_id(active_beat.project_id)
    elapsed = active_beat.duration
    elapsed_minutes = int(elapsed.total_seconds() / 60)
    daily_minutes = await _get_daily_total_minutes(beat_service)
    energy = min(int(daily_minutes / 60), 7)
    color_hex = project.color or assign_color(project.id or "")

    return DeviceStatusResponse(
        clocked_in=True,
        project_name=project.name,
        project_id=project.id,
        project_color_rgb=hex_to_rgb(color_hex),
        elapsed_minutes=elapsed_minutes,
        daily_total_minutes=daily_minutes,
        energy_level=energy,
        theme_accent_rgb=theme_rgb,
    )


@router.get("/favorites", response_model=list[DeviceFavoriteProject])
async def get_favorites(
    project_service: ProjectServiceDep,
) -> list[DeviceFavoriteProject]:
    """Get favorite (non-archived) projects for multi-project switching."""
    projects = await project_service.project_repo.list(archived=False)
    return [
        DeviceFavoriteProject(
            id=p.id or "",
            name=p.name,
            color_rgb=hex_to_rgb(p.color or assign_color(p.id or "")),
        )
        for p in projects[:9]  # Max 9 for firmware UI
    ]


@router.post("/heartbeat", response_model=DeviceHeartbeatResponse)
async def post_heartbeat(body: DeviceHeartbeatRequest) -> DeviceHeartbeatResponse:
    """Receive a heartbeat from the wall clock device."""
    global _last_heartbeat
    _last_heartbeat = {
        "battery_voltage": body.battery_voltage,
        "wifi_rssi": body.wifi_rssi,
        "uptime_seconds": body.uptime_seconds,
        "last_seen": datetime.now(UTC),
    }
    return DeviceHeartbeatResponse(**_last_heartbeat)


@router.get("/heartbeat", response_model=DeviceHeartbeatResponse | None)
async def get_heartbeat() -> DeviceHeartbeatResponse | None:
    """Get the last heartbeat from the wall clock device."""
    if not _last_heartbeat:
        return None
    return DeviceHeartbeatResponse(**_last_heartbeat)


# --- Pairing schemas ---


class PairCodeResponse(BaseModel):
    code: str
    expires_in_seconds: int = 300


class PairExchangeRequest(BaseModel):
    code: str
    device_name: str | None = None


class PairExchangeResponse(BaseModel):
    device_token: str
    device_id: str


class DeviceRegistrationResponse(BaseModel):
    id: str
    device_id: str
    device_name: str | None
    created_at: datetime
    last_seen: datetime | None


def _generate_pair_code() -> tuple[str, str]:
    """Generate a 6-char base-32 pairing code and its SHA-256 hash."""
    raw = base64.b32encode(os.urandom(4))[:6].decode()
    code_hash = hashlib.sha256(raw.encode()).hexdigest()
    return raw, code_hash


@router.post("/pair/code", response_model=PairCodeResponse)
async def generate_pair_code(
    user_id: CurrentUserId,
    pairing_repo: PairingCodeRepoDep,
) -> PairCodeResponse:
    """Generate a short-lived pairing code for daemon authentication."""
    raw_code, code_hash = _generate_pair_code()
    pairing_code = PairingCode(user_id=user_id, code_hash=code_hash)
    await pairing_repo.create(pairing_code)
    return PairCodeResponse(code=raw_code)


@router.post("/pair/exchange", response_model=PairExchangeResponse)
@limiter.limit("10/minute")
async def exchange_pair_code(
    request: Request,
    body: PairExchangeRequest,
    pairing_repo: PairingCodeRepoDep,
    device_repo: DeviceRegistrationRepoDep,
) -> PairExchangeResponse:
    """Exchange a pairing code for a long-lived device token (public endpoint).

    Rate-limited because the endpoint is unauthenticated and the pairing
    code is only ~30 bits of entropy (6 base32 chars). Without a limit,
    a peer on the same NAT could grind through the keyspace.
    """
    code_hash = hashlib.sha256(body.code.encode()).hexdigest()
    pairing_code = await pairing_repo.find_by_hash(code_hash)
    if not pairing_code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid or expired pairing code",
        )

    # One-time use: delete immediately
    await pairing_repo.delete(pairing_code.id)  # type: ignore[arg-type]

    # Create device registration
    device_id = str(uuid.uuid4())
    registration = DeviceRegistration(
        user_id=pairing_code.user_id,
        device_id=device_id,
        device_name=body.device_name,
    )
    await device_repo.create(registration)

    # Issue device token
    session_manager = get_session_manager()
    device_token = session_manager.create_device_token(pairing_code.user_id, device_id)

    return PairExchangeResponse(device_token=device_token, device_id=device_id)


@router.get("/registrations", response_model=list[DeviceRegistrationResponse])
async def list_registrations(
    user_id: CurrentUserId,
    device_repo: DeviceRegistrationRepoDep,
) -> list[DeviceRegistrationResponse]:
    """List all active (non-revoked) device registrations for the current user."""
    registrations = await device_repo.list_by_user(user_id)
    return [
        DeviceRegistrationResponse(
            id=r.id or "",
            device_id=r.device_id,
            device_name=r.device_name,
            created_at=r.created_at,
            last_seen=r.last_seen,
        )
        for r in registrations
    ]


@router.delete("/registrations/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_registration(
    device_id: str,
    user_id: CurrentUserId,
    device_repo: DeviceRegistrationRepoDep,
) -> None:
    """Revoke a device registration, invalidating its device token."""
    revoked = await device_repo.revoke(device_id, user_id)
    if not revoked:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Device registration not found",
        )


async def _get_daily_total_minutes(beat_service: BeatServiceDep) -> int:
    """Calculate total tracked minutes for today."""
    today = date.today()
    beats = await beat_service.beat_repo.list(date_filter=today)
    total_seconds = sum(b.duration.total_seconds() for b in beats if not b.is_active)
    return int(total_seconds / 60)
