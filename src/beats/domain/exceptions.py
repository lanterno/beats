"""Domain exceptions - unified exception hierarchy for business rule violations."""


class DomainException(Exception):
    """Base exception for all domain-level errors.

    Subclasses should define status_code and message as class attributes.
    These are used by the API layer to generate appropriate HTTP responses.
    """

    status_code: int = 400
    message: str = "A domain error occurred"

    def __init__(self, message: str | None = None):
        self.message = message or self.__class__.message
        super().__init__(self.message)


# Timer-related exceptions
class NoActiveTimer(DomainException):
    """Raised when attempting to stop a timer but none is running."""

    message = "No timer is currently running"


class TimerAlreadyRunning(DomainException):
    """Raised when attempting to start a timer while one is already active."""

    message = "A timer is already running"

    def __init__(
        self,
        project_name: str | None = None,
        beat: "dict | None" = None,
    ):
        msg = (
            f"'{project_name}' already has a beat in progress"
            if project_name
            else self.__class__.message
        )
        super().__init__(msg)
        self.detail = {}
        if beat is not None:
            self.detail["beat"] = beat
        if project_name is not None:
            self.detail["project_name"] = project_name


class InvalidEndTime(DomainException):
    """Raised when the end time is before the start time."""

    message = "End time must be after start time"


# Project-related exceptions
class ProjectNotFound(DomainException):
    """Raised when a project cannot be found by ID."""

    status_code = 404
    message = "Project not found"

    def __init__(self, project_id: str | None = None):
        if project_id:
            super().__init__(f"Project not found: {project_id}")
        else:
            super().__init__()


# Beat-related exceptions
class BeatNotFound(DomainException):
    """Raised when a beat cannot be found by ID."""

    status_code = 404
    message = "Beat not found"

    def __init__(self, beat_id: str | None = None):
        if beat_id:
            super().__init__(f"Beat not found: {beat_id}")
        else:
            super().__init__()


class CannotStopInactiveBeat(DomainException):
    """Raised when attempting to stop a beat that is already stopped."""

    message = "Cannot stop a beat that is not active"


# General data exceptions
class NoObjectMatched(DomainException):
    """Raised when a query returns no results."""

    status_code = 404
    message = "No matching record found"
