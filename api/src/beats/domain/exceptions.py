"""Domain exceptions - unified exception hierarchy for business rule violations."""

from datetime import date

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _spoken(day: date) -> str:
    """A date the way a message says it, "Mar 2, 2026" — spelled out here
    rather than with `%b`, which follows the process locale."""
    return f"{_MONTHS[day.month - 1]} {day.day}, {day.year}"


class DomainException(Exception):
    """Base exception for all domain-level errors.

    Subclasses should define status_code and message as class attributes.
    These are used by the API layer to generate appropriate HTTP responses.
    `code` is the machine-readable name in the error envelope; left None, the
    envelope falls back to the status default (BAD_REQUEST, NOT_FOUND, ...).
    Set it where a client has to tell this failure from the others behind the
    same status.
    """

    status_code: int = 400
    message: str = "A domain error occurred"
    code: str | None = None

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
        beat: dict | None = None,
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


class UnknownHolidayRegion(DomainException):
    """Raised when a contract names a holiday region the calendar library does not know."""

    message = "Unknown holiday region"
    code = "UNKNOWN_HOLIDAY_REGION"

    def __init__(self, country: str, subdivision: str | None):
        where = country if subdivision is None else f"{country} / {subdivision}"
        super().__init__(f"Unknown holiday region: {where}")


class NotADayJob(DomainException):
    """Raised when a contract, its week, or an absence is asked of a project
    that is not a day job. A conflict with the project's kind, not a bad
    request: the same call is valid once the kind is changed."""

    status_code = 409
    message = "Only a day-job project has a contract"
    code = "NOT_A_DAY_JOB"


class NoContract(DomainException):
    """Raised when a day job's week, or a balance adjustment, is asked for
    before it has a contract."""

    status_code = 409
    message = "This day job has no contract yet"
    code = "NO_CONTRACT"


class VacationOpeningOutsideContract(DomainException):
    """Raised when a contract write leaves the vacation count's opening date
    outside the contract's dates — before the first term, or after
    `ended_on`. A stored entitlement is kept when a write leaves it out, so
    this is how a term removed, a term inserted earlier, or an end moved
    surfaces, rather than the count being silently reinterpreted."""

    status_code = 409
    message = "The vacation count starts outside the contract's dates"
    code = "VACATION_OPENING_OUTSIDE_CONTRACT"

    def __init__(self, opening_on: date):
        super().__init__(
            f"The vacation count starts on {_spoken(opening_on)}, outside the contract's "
            "dates; change it in the project settings first"
        )


class NoVacationEntitlement(DomainException):
    """Raised when a day job's vacation year is asked for and its contract
    tracks no vacation entitlement."""

    status_code = 409
    message = "This contract has no vacation entitlement"
    code = "NO_VACATION_ENTITLEMENT"


class VacationYearOutOfRange(DomainException):
    """Raised when a vacation year is asked for outside the years counted:
    before the opening's, or after the year the contract ends."""

    status_code = 409
    message = "Vacation is not counted in that year"
    code = "VACATION_YEAR_OUT_OF_RANGE"

    def __init__(self, first: int, last: int | None):
        if last is None:
            span = f"from {first} on"
        elif last == first:
            span = f"in {first} only"
        else:
            span = f"from {first} through {last}"
        super().__init__(f"Vacation is counted {span}")


class AbsenceNotFound(DomainException):
    """Raised when an absence cannot be found by ID."""

    status_code = 404
    message = "Absence not found"

    def __init__(self, absence_id: str | None = None):
        if absence_id:
            super().__init__(f"Absence not found: {absence_id}")
        else:
            super().__init__()


class AdjustmentOutsideBalance(DomainException):
    """Raised when a balance adjustment is dated where there is no balance to
    adjust: before the contract's first day, or after today in the caller's
    timezone."""

    status_code = 409
    message = "A balance adjustment must be dated from the contract's first day through today"
    code = "ADJUSTMENT_OUTSIDE_BALANCE"


class AdjustmentBeforeStart(DomainException):
    """Raised when a contract write moves the first day later past a balance
    adjustment: the adjustment would silently stop counting."""

    status_code = 409
    message = "Move or remove the balance adjustments dated before the contract's first day"
    code = "ADJUSTMENT_BEFORE_START"


class AdjustmentNotFound(DomainException):
    """Raised when a balance adjustment cannot be found by ID on the project."""

    status_code = 404
    message = "Balance adjustment not found"

    def __init__(self, adjustment_id: str | None = None):
        if adjustment_id:
            super().__init__(f"Balance adjustment not found: {adjustment_id}")
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


# General data exceptions
class NoObjectMatched(DomainException):
    """Raised when a query returns no results."""

    status_code = 404
    message = "No matching record found"
