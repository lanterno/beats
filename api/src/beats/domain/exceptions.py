"""Domain exceptions - unified exception hierarchy for business rule violations."""

from datetime import date

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def _spoken(day: date) -> str:
    """A date the way a message says it, "Mar 2, 2026" — spelled out here
    rather than with `%b`, which follows the process locale."""
    return f"{_MONTHS[day.month - 1]} {day.day}, {day.year}"


def _spoken_month(day: date) -> str:
    """The month of `day` the way a message says it, "March 2026"."""
    return f"{_MONTH_NAMES[day.month - 1]} {day.year}"


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


class MonthOutsideContract(DomainException):
    """Raised when a timesheet is asked for a month with no finished day
    inside the contract: wholly before its first term or after `ended_on`,
    still to come, or the current month on its first day."""

    status_code = 409
    message = "No finished day of that month falls in the contract"
    code = "OUTSIDE_CONTRACT"


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


class BackupOfAnotherAccount(DomainException):
    """Raised when a backup being imported holds a project, a session or a
    client whose id is another account's. A restore keeps ids, so writing it
    would collide with that account's record, or, unscoped, take it over."""

    status_code = 409
    message = "This backup holds projects, sessions or clients of another account"
    code = "BACKUP_OF_ANOTHER_ACCOUNT"

    def __init__(self, projects: int, beats: int, clients: int):
        super().__init__(
            f"This backup holds {projects} project(s), {beats} session(s) and {clients} "
            "client(s) of another account; import it into the account it was exported from"
        )


# Billing exceptions
class ClientNotFound(DomainException):
    """Raised when a client cannot be found by ID among the caller's own."""

    status_code = 404
    message = "Client not found"
    code = "CLIENT_NOT_FOUND"

    def __init__(self, client_id: str | None = None):
        if client_id:
            super().__init__(f"Client not found: {client_id}")
        else:
            super().__init__()


class UnknownCurrency(DomainException):
    """Raised when a client names a currency `domain/currencies.py` does not
    know: the table is the one source of a currency's minor units."""

    message = "Unknown currency"
    code = "UNKNOWN_CURRENCY"

    def __init__(self, currency: str):
        super().__init__(f"Unknown currency: {currency}")


class CurrencyInUse(DomainException):
    """Raised when a client's currency is changed once something is priced in
    it — a rate of the client's, or of any of its projects': every amount
    would silently be read in the new currency."""

    status_code = 409
    message = "This client's rates are in its currency; its currency can no longer change"
    code = "CURRENCY_IN_USE"


class CurrencyMismatch(DomainException):
    """Raised when a project is moved to a client in another currency while
    it carries a rate of its own, or billable terms before the current
    month: either would be re-denominated in the other currency."""

    status_code = 409
    message = (
        "This project is billed in its client's currency; stop billing it before "
        "moving it to a client in another currency"
    )
    code = "CURRENCY_MISMATCH"


class ClientHasProjects(DomainException):
    """Raised when a client is deleted while a project is billed to it.
    Archive is the way out: past reports keep the client's name and currency."""

    status_code = 409
    message = "Projects are billed to this client; archive it instead"
    code = "CLIENT_HAS_PROJECTS"


class NotFreelance(DomainException):
    """Raised when billing is asked of a project that is not freelance. A
    conflict with the project's kind, as `NotADayJob` is for a contract."""

    status_code = 409
    message = "Only a freelance project is billed"
    code = "NOT_FREELANCE"


class ProjectHasBilling(DomainException):
    """Raised when a billed project's kind is changed away from freelance: its
    billing would sit dormant on a project that cannot read it."""

    status_code = 409
    message = "Stop billing this project before changing its kind"
    code = "PROJECT_HAS_BILLING"


class RetroactiveChange(DomainException):
    """Raised when a write would change billable figures before the current
    month and the caller did not say `rewrite_past`. Those months may have
    been invoiced; the 409 names the first one touched."""

    status_code = 409
    message = "This changes billable figures in a month that has ended"
    code = "RETROACTIVE_CHANGE"

    def __init__(self, first_day: date):
        super().__init__(
            f"This changes billable figures from {_spoken_month(first_day)}, which may "
            "already have been invoiced. Confirm to apply it."
        )


class ProjectNotBilled(DomainException):
    """Raised when billing is stopped on a project that is not billed. A
    project of someone else's, or none at all, is not billed either."""

    status_code = 404
    message = "This project is not billed"


class MonthNotStarted(DomainException):
    """Raised when a billing month after the current one is asked for."""

    status_code = 409
    message = "That month has not started yet"
    code = "MONTH_NOT_STARTED"

    def __init__(self, month: date):
        super().__init__(f"{_spoken_month(month)} has not started yet")


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
