"""Domain layer - core business logic with no external dependencies."""

from .exceptions import (
    BeatNotFound,
    CannotStopInactiveBeat,
    DomainException,
    InvalidEndTime,
    NoActiveTimer,
    NoObjectMatched,
    ProjectNotFound,
    TimerAlreadyRunning,
)
from .models import Beat, Project

__all__ = [
    # Models
    "Beat",
    "Project",
    # Exceptions
    "DomainException",
    "BeatNotFound",
    "CannotStopInactiveBeat",
    "InvalidEndTime",
    "NoActiveTimer",
    "NoObjectMatched",
    "ProjectNotFound",
    "TimerAlreadyRunning",
]
