"""Domain layer - core business logic with no external dependencies."""

from .exceptions import (
    BeatNotFound,
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
    "BeatNotFound",
    # Exceptions
    "DomainException",
    "InvalidEndTime",
    "NoActiveTimer",
    "NoObjectMatched",
    "Project",
    "ProjectNotFound",
    "TimerAlreadyRunning",
]
