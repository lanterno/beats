"""Timer API router - thin controller for timer status."""

from fastapi import APIRouter

from beats.api.dependencies import TimerServiceDep

router = APIRouter(
    prefix="/api/timer",
    tags=["Timer"],
)


@router.get("/status")
async def get_timer_status(service: TimerServiceDep):
    """Get the current timer status.

    Returns whether a timer is running, and if so, details about the active beat.
    """
    return await service.get_status()
