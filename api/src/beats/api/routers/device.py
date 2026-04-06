"""Device API router — endpoints optimized for ESP32 wall clock firmware."""

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from beats.api.dependencies import BeatServiceDep, ProjectServiceDep, TimerServiceDep

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


class DeviceStatusResponse(BaseModel):
    clocked_in: bool
    project_name: str | None = None
    project_id: str | None = None
    project_color_rgb: list[int] = [0, 0, 0]
    elapsed_minutes: int = 0
    daily_total_minutes: int = 0
    energy_level: int = 0  # 0-7 for energy meter LEDs


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
) -> DeviceStatusResponse:
    """Get timer state optimized for ESP32 wall clock firmware."""
    active_beat = await timer_service.beat_repo.get_active()

    if not active_beat:
        # Calculate daily total even when not clocked in
        daily_minutes = await _get_daily_total_minutes(beat_service)
        energy = min(int(daily_minutes / 60), 7)
        return DeviceStatusResponse(
            clocked_in=False,
            daily_total_minutes=daily_minutes,
            energy_level=energy,
        )

    # Timer is running
    project = await timer_service.project_repo.get_by_id(active_beat.project_id)
    elapsed = active_beat.duration
    elapsed_minutes = int(elapsed.total_seconds() / 60)
    daily_minutes = await _get_daily_total_minutes(beat_service)
    energy = min(int(daily_minutes / 60), 7)
    color_hex = assign_color(project.id or "")

    return DeviceStatusResponse(
        clocked_in=True,
        project_name=project.name,
        project_id=project.id,
        project_color_rgb=hex_to_rgb(color_hex),
        elapsed_minutes=elapsed_minutes,
        daily_total_minutes=daily_minutes,
        energy_level=energy,
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
            color_rgb=hex_to_rgb(assign_color(p.id or "")),
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


async def _get_daily_total_minutes(beat_service: BeatServiceDep) -> int:
    """Calculate total tracked minutes for today."""
    from datetime import date

    today = date.today()
    beats = await beat_service.beat_repo.list(date_filter=today)
    total_seconds = sum(
        b.duration.total_seconds() for b in beats if not b.is_active
    )
    return int(total_seconds / 60)
