"""Domain models - pure business entities with no external dependencies."""

from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from decimal import Decimal
from enum import StrEnum
from itertools import pairwise
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    computed_field,
    field_validator,
    model_validator,
)

from beats.domain.utils import TzNormalizedModel, normalize_tz


class LinkedIdentity(BaseModel):
    """An identity at an OpenID Connect provider that signs into this account.

    Keyed on (issuer, subject), never on a name or an email: `subject` is the
    provider's `sub`, stable and never reassigned within its issuer, while a
    name or an address can change hands. `name` and `email` are refreshed on
    each sign-in and are shown, not matched.
    """

    # The configured provider's id it arrived through (`OIDC_PROVIDERS`).
    provider: str
    issuer: str
    subject: str
    name: str | None = None
    email: str | None = None
    linked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class User(TzNormalizedModel):
    """A registered user of the Beats system.

    A user may hold two independent ways in: passkeys registered against
    beats itself (`credentials` collection), and identities at OpenID
    Connect providers (`identities`, at most one per provider). Neither
    implies the other, and either alone is enough to sign in.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    email: str
    display_name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    identities: list[LinkedIdentity] = Field(default_factory=list)

    # True when the account was created BY a sign-in through a provider
    # rather than linked to one afterwards. Such an account has no passkey
    # until its owner registers one, and keeps a provider-chosen display name
    # in step with the provider until then.
    sso_provisioned: bool = False

    def identity_for(self, provider: str) -> LinkedIdentity | None:
        return next((i for i in self.identities if i.provider == provider), None)


class GoalType(StrEnum):
    """Type of weekly goal: target to reach or cap to stay under."""

    TARGET = "target"
    CAP = "cap"


class GoalOverride(BaseModel):
    """A per-week or date-range override of a project's weekly goal.

    Exactly one of week_of or effective_from must be set:
    - week_of: one-off override for a single week (identified by its Monday)
    - effective_from: permanent override from a date forward (must be a Monday)

    weekly_goal=None means "no goal applies for this window" (e.g. a holiday
    week, or the user giving up on a target from a given Monday forward).
    """

    week_of: date_type | None = None
    effective_from: date_type | None = None
    weekly_goal: float | None = None
    goal_type: GoalType | None = None  # None = inherit project default
    note: str | None = None

    @model_validator(mode="after")
    def validate_override_type(self) -> GoalOverride:
        has_week = self.week_of is not None
        has_from = self.effective_from is not None
        if has_week == has_from:
            msg = "Exactly one of week_of or effective_from must be set"
            raise ValueError(msg)
        if self.week_of is not None and self.week_of.weekday() != 0:
            msg = "week_of must be a Monday"
            raise ValueError(msg)
        if self.effective_from is not None and self.effective_from.weekday() != 0:
            msg = "effective_from must be a Monday"
            raise ValueError(msg)
        if self.weekly_goal is not None and self.weekly_goal <= 0:
            msg = "weekly_goal must be positive"
            raise ValueError(msg)
        return self


class ProjectKind(StrEnum):
    """What a project is to the person tracking it. A contract is read only on a day job."""

    DAY_JOB = "day_job"
    FREELANCE = "freelance"
    SIDE_PROJECT = "side_project"


class ScheduleType(StrEnum):
    """How a contract term states the hours it owes."""

    FULL_TIME = "full_time"  # percentage fixed at 1.0
    PART_TIME = "part_time"  # percentage < 1.0
    CUSTOM = "custom"  # weekly_hours given directly
    OBJECTIVE = "objective"  # no expectation, no balance


# A week owes hours_per_week; a day off owes a fifth of it less. There is no
# working pattern (decision 3): we never ask which weekdays are worked.
WORKDAYS_PER_WEEK = 5


class ContractTerm(BaseModel):
    """One stretch of a contract, from `effective_from` until the next term takes over.

    A time-based term (full_time / part_time) owes `full_time_hours × percentage`
    a week — a percentage needs its basis, since 80% of 42 is not 80% of 40. A
    custom term states `weekly_hours` outright. An objective term owes nothing
    and carries no numbers at all. Hence the rules:

    - `percentage` lies in (0, 1]; a full_time term is 1 — filled in when
      omitted, rejected when it says otherwise — and a part_time term is
      less than 1, or it would be full-time under another name.
    - `weekly_hours` is required for custom and must be left out for the
      time-based types, where it is derived (`hours_per_week`).
    - `full_time_hours` and `percentage` belong to the time-based types only.

    `effective_from` may be any day of the week: a contract that changes on a
    Wednesday charges Monday and Tuesday at the old rate.
    """

    effective_from: date_type
    schedule_type: ScheduleType
    # Finite only: a NaN here would ride through hours_per_day into every
    # expectation and the balance, and compare as neither over nor under.
    full_time_hours: float | None = Field(default=None, allow_inf_nan=False)
    percentage: float | None = Field(default=None, allow_inf_nan=False)
    weekly_hours: float | None = Field(default=None, allow_inf_nan=False)
    note: str | None = None

    @model_validator(mode="after")
    def validate_hours_for_schedule(self) -> ContractTerm:
        if self.full_time_hours is not None and self.full_time_hours <= 0:
            msg = "full_time_hours must be positive"
            raise ValueError(msg)
        if self.percentage is not None and not 0 < self.percentage <= 1:
            msg = "percentage must be in (0, 1]"
            raise ValueError(msg)
        if self.weekly_hours is not None and self.weekly_hours < 0:
            msg = "weekly_hours must not be negative"
            raise ValueError(msg)

        schedule = self.schedule_type
        if schedule is ScheduleType.OBJECTIVE:
            if (self.full_time_hours, self.percentage, self.weekly_hours) != (None, None, None):
                msg = "an objective term carries no hours"
                raise ValueError(msg)
        elif schedule is ScheduleType.CUSTOM:
            if self.weekly_hours is None:
                msg = "a custom term requires weekly_hours"
                raise ValueError(msg)
            if self.full_time_hours is not None or self.percentage is not None:
                msg = "a custom term states weekly_hours directly, not a basis and percentage"
                raise ValueError(msg)
        else:
            if self.full_time_hours is None:
                msg = f"a {schedule} term requires full_time_hours"
                raise ValueError(msg)
            if self.weekly_hours is not None:
                msg = f"weekly_hours is derived for a {schedule} term"
                raise ValueError(msg)
            if schedule is ScheduleType.FULL_TIME:
                if self.percentage is None:
                    self.percentage = 1.0
                elif self.percentage != 1:
                    msg = "a full_time term is 100%; use part_time for less"
                    raise ValueError(msg)
            elif self.percentage is None:
                msg = "a part_time term requires percentage"
                raise ValueError(msg)
            elif self.percentage == 1:
                msg = "a part_time term is less than 100%; use full_time for a full week"
                raise ValueError(msg)
        return self

    @property
    def hours_per_week(self) -> float | None:
        """Hours the week owes under this term; None for an objective term."""
        if self.schedule_type is ScheduleType.CUSTOM:
            return self.weekly_hours
        if self.full_time_hours is None or self.percentage is None:
            return None  # objective; the validator leaves no other way here
        return self.full_time_hours * self.percentage

    @property
    def hours_per_day(self) -> float | None:
        """What one weekday owes, and what a day off costs."""
        weekly = self.hours_per_week
        return None if weekly is None else weekly / WORKDAYS_PER_WEEK

    @property
    def is_time_based(self) -> bool:
        """Whether the term owes hours at all — false only for an objective term."""
        return self.hours_per_week is not None


class CompanyHoliday(BaseModel):
    """A day off the employer gives that the region's calendar does not —
    Christmas Eve, a bridge day, a company day. A whole day, on one date."""

    date: date_type
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class CarryOver(StrEnum):
    """What becomes of the vacation days left at the end of a year."""

    ALL = "all"  # every unused day carries into the next year
    CAPPED = "capped"  # up to `carry_over_max_days` carry
    NONE = "none"  # unused days lapse on 31 December


# Far beyond any real figure, and a bound on what a typo can do to a chain of years.
_VACATION_DAYS_BOUND = 366


class VacationEntitlement(BaseModel):
    """The vacation days a day job gives, counted the way the arithmetic
    counts a day off: for a five-day week (decision 3), so a week off is
    five days whatever the percentage, and a 4-day week with 20 days is
    entered as 25.

    Counting starts on `opening_on`, with `opening_days` left for the rest
    of that calendar year (carry-over included, negative when overdrawn) —
    the figure off the contract or an HR statement. Nothing before it is
    reconstructed: a contract the migration started at the first beat,
    years back, must not be credited years of leave nobody recorded.

    Every figure is a whole or half day. The rules are field constraints,
    so a 422 names the leaf. The one rule tying the entitlement to the rest
    of the contract — `opening_on` inside its dates — is checked where a
    contract is written (`ProjectService`), for the reason the region is:
    this model is re-validated on every read, and a stored entitlement can
    be paired with new terms by the keep-unsent merge.
    """

    days_per_year: float = Field(
        strict=True, gt=0, le=_VACATION_DAYS_BOUND, multiple_of=0.5, allow_inf_nan=False
    )
    carry_over: CarryOver
    # Only with `capped`, and required there. Positive: a cap of 0 is `none`.
    # Defaulted, so a stored entitlement that carries everything (the cap
    # dropped by the store's exclude_none) reads back.
    carry_over_max_days: float | None = Field(
        default=None,
        strict=True,
        gt=0,
        le=_VACATION_DAYS_BOUND,
        multiple_of=0.5,
        allow_inf_nan=False,
        validate_default=True,
    )
    opening_on: date_type
    opening_days: float = Field(
        strict=True,
        ge=-_VACATION_DAYS_BOUND,
        le=_VACATION_DAYS_BOUND,
        multiple_of=0.5,
        allow_inf_nan=False,
    )

    @field_validator("carry_over_max_days")
    @classmethod
    def cap_only_when_capped(cls, cap: float | None, info: ValidationInfo) -> float | None:
        # A field validator rather than a model one, so the 422 names the
        # cap. `carry_over` is declared first and so is in `info.data` —
        # unless it failed, and then its own error is the answer.
        carry_over = info.data.get("carry_over")
        if carry_over is CarryOver.CAPPED and cap is None:
            msg = "say how many days carry over"
            raise ValueError(msg)
        if carry_over in (CarryOver.ALL, CarryOver.NONE) and cap is not None:
            msg = "only a capped carry-over takes a number of days"
            raise ValueError(msg)
        return cap


# Far beyond any real balance, and small enough that a sum of many records
# stays finite: a balance that overflowed would serialize as null. It bounds
# the two figures a client types into the balance: the opening and an
# adjustment's hours. Both models are re-validated on every read, the
# opening with every project of its user, so a stored figure past the bound
# is a 500 there: it is never narrowed without first finding the stored
# figures past the new one.
_BALANCE_HOURS_BOUND = 10_000


class Contract(BaseModel):
    """A day job's terms as they changed over time, plus what frames them.

    `terms` is the history — part-time, then 80%, then full-time — kept in
    order of `effective_from` with no two starting on the same day, because
    the day decides which term applies. The region names the employer's
    public holidays: `holiday_subdivision` only means something inside a
    `holiday_country`. Both must be codes the holidays library knows, but
    that is checked where a contract is written (`ProjectService`), not
    here: this model is re-validated on every read, and the set of codes the
    library knows moves with its version — a code it stops recognising must
    make one contract un-editable, not every project of the user unreadable.
    `opening_balance_hours` is what was banked (or owed) before Beats started
    counting; `ended_on` freezes the balance from that day on.

    Where the employer's days off differ from the region's, two lists say
    how: `company_holidays` adds days, `holidays_not_given` takes region
    holidays away (`domain/holidays.contract_calendar` combines the three).
    A removal that matches no region holiday — or is kept while there is no
    region — does nothing; a company day on a removed date wins. Each list's
    only rule is its own (no date twice), and no rule may ever tie either
    list to another field or to the other list: an incoming contract that
    leaves a list out keeps the stored one (`keep_unsent_contract_fields`),
    merged without re-validating, which is safe only while every rule on
    these lists is per-list. A cross-field rule would need that merge to
    re-validate and answer a 422 — otherwise a merged contract could fail
    the next read, and every project of the user with it.

    `vacation` is the leave the job gives (`VacationEntitlement`), None when
    nothing is tracked. It is kept when left out the same way, and so has no
    rule here tying it to the terms or `ended_on`: that its opening falls
    inside the contract's dates is checked after the merge, on the write.
    """

    terms: list[ContractTerm]
    holiday_country: str | None = None  # ISO 3166-1 alpha-2, e.g. "CH"
    holiday_subdivision: str | None = None  # ISO 3166-2 part, e.g. "ZH"
    opening_balance_hours: float = Field(
        default=0,
        allow_inf_nan=False,
        ge=-_BALANCE_HOURS_BOUND,
        le=_BALANCE_HOURS_BOUND,
    )
    ended_on: date_type | None = None
    company_holidays: list[CompanyHoliday] = Field(default_factory=list, max_length=400)
    holidays_not_given: list[date_type] = Field(default_factory=list, max_length=400)
    vacation: VacationEntitlement | None = None

    @field_validator("company_holidays")
    @classmethod
    def one_company_holiday_a_day(cls, days: list[CompanyHoliday]) -> list[CompanyHoliday]:
        if len({day.date for day in days}) != len(days):
            msg = "two company holidays on one date"
            raise ValueError(msg)
        return days

    @field_validator("holidays_not_given")
    @classmethod
    def no_date_given_twice(cls, days: list[date_type]) -> list[date_type]:
        if len(set(days)) != len(days):
            msg = "a date is listed twice"
            raise ValueError(msg)
        return days

    @model_validator(mode="after")
    def validate_terms(self) -> Contract:
        if not self.terms:
            msg = "a contract needs at least one term"
            raise ValueError(msg)
        for earlier, later in pairwise(self.terms):
            if later.effective_from <= earlier.effective_from:
                msg = "terms must be in ascending order of effective_from, with no two on one day"
                raise ValueError(msg)
        if self.ended_on is not None and self.ended_on < self.terms[0].effective_from:
            msg = "ended_on is before the first term starts"
            raise ValueError(msg)
        if self.holiday_subdivision is not None and self.holiday_country is None:
            msg = "holiday_subdivision needs a holiday_country"
            raise ValueError(msg)
        return self

    @property
    def starts_on(self) -> date_type:
        """The first day anything is expected: the first term's `effective_from`."""
        return self.terms[0].effective_from

    def term_on(self, day: date_type) -> ContractTerm | None:
        """The term in force on `day`: the latest whose `effective_from` is not after it.

        None before the first term. `ended_on` is not consulted — a term is
        still the term that applied, it just stops owing anything.
        """
        current: ContractTerm | None = None
        for term in self.terms:  # the validator keeps these ascending
            if term.effective_from > day:
                break
            current = term
        return current


class AbsenceType(StrEnum):
    """Why a day was not worked. The expectation treats all three the same: a
    day off is a day off. Only the vacation count reads the type, and counts
    `vacation` alone against the entitlement (`domain/vacation.py`)."""

    VACATION = "vacation"
    SICK = "sick"
    OTHER = "other"


class Absence(BaseModel):
    """A day, or half of one, the contract does not expect work on.

    One per (project, date): a second absence on the same day replaces the
    first rather than stacking. Weekends and holidays already cost nothing,
    so an absence recorded on one changes nothing.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    project_id: str
    date: date_type
    half_day: bool = False
    type: AbsenceType
    note: str | None = None
    # As on `Beat`: set when recorded on an organisation's project, and what
    # the organisation's read of absences asks for. The note is never read
    # through it — an absence crosses as its date, type and half-day alone.
    organisation_id: str | None = None


class AdjustmentKind(StrEnum):
    """How a balance adjustment moves the balance at the start of its day."""

    DELTA = "delta"  # by `hours`, signed: a payout is negative, a credit positive
    RESET = "reset"  # to `hours`
    CAP = "cap"  # down to `hours` if above it; a balance under the cap is untouched


class BalanceAdjustmentFields(BaseModel):
    """A dated change to a day job's balance, as a client sends it — the
    request body of `POST /{id}/adjustments`, so its validators are the 422.

    A reset or a cap stores its target, not the hours it moved: what it
    moves is worked out each time the balance is read, against the balance
    that morning, so a session recorded later from before the reset leaves
    everything after it unchanged.
    """

    date: date_type
    kind: AdjustmentKind
    # Strict, so `true` is a 422 and not a 1 h payout: lax mode reads a bool
    # (and a numeric string) as a number. An int still reads as hours.
    hours: float = Field(
        strict=True,
        allow_inf_nan=False,
        ge=-_BALANCE_HOURS_BOUND,
        le=_BALANCE_HOURS_BOUND,
    )
    note: str | None = None

    @field_validator("hours")
    @classmethod
    def hours_mean_something_for_the_kind(cls, hours: float, info: ValidationInfo) -> float:
        # A field validator rather than a model one, so the 422 names `hours`.
        # `kind` is declared first and so is already in `info.data` — unless
        # it failed, and then its own error is the answer.
        kind = info.data.get("kind")
        if kind is AdjustmentKind.DELTA and hours == 0:
            msg = "a delta of 0 h moves nothing"
            raise ValueError(msg)
        if kind is AdjustmentKind.CAP and hours < 0:
            msg = "a cap must not be negative"
            raise ValueError(msg)
        return hours


class BalanceAdjustment(BalanceAdjustmentFields):
    """A balance adjustment on record: one per (project, date), so a second
    posted for a day replaces the first, as an absence does. It counts from
    the contract's first day on, whatever `ended_on` says — a payout after
    the end settles the frozen balance — and is deleted with the contract."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    project_id: str


class DayAbsence(BaseModel):
    """An absence as one day of the week report shows it — the record without
    its keys, which the day already supplies."""

    type: AbsenceType
    half_day: bool
    note: str | None = None


class ContractDay(BaseModel):
    """One day of a contract week: what it owed, what was worked, and why it
    owed less if it did."""

    date: date_type
    expected: float
    worked: float
    holiday: str | None = None  # the holiday's name
    absence: DayAbsence | None = None


class ContractWeek(BaseModel):
    """A day job's week against its contract, plus the running balance.

    Typed because it crosses the wire (see `ProjectBreakdownEntry`).
    `expected` and `remaining` are None when the contract owes nothing by
    nature that week — no weekday has a time-based term in force — as
    distinct from 0, which is a week the contract owed nothing by
    circumstance (every weekday a holiday, or after `ended_on`). `balance`
    is None on the same rule for today. `remaining` goes negative once the
    week is over its expectation. `worked` is every hour on the project that
    week; `remaining` subtracts only the hours the balance counts — inside
    the contract's dates, under a term that owes hours — so the two differ
    on a week it starts or ends, or a term that owes nothing begins or ends.
    Each figure is rounded on its own, so `worked + remaining` can miss
    `expected` by a hundredth.
    """

    week_of: date_type
    expected: float | None
    worked: float
    remaining: float | None
    balance: float | None
    days: list[ContractDay]
    # The proof under the balance, so a reader can check the sum:
    # `balance_opening + balance_worked - balance_expected_through +
    # balance_adjusted` is `balance` within 0.025 (each of the four terms and
    # the balance is rounded on its own). Always on the wire, and null
    # exactly when `balance` is — required like it, so the generated type
    # does not say they may be absent: `balance_as_of` is the day the balance
    # is for, `balance_worked` the hours since the contract started (through
    # `ended_on` at most, under a term that owes hours),
    # `balance_expected_through` what was expected through the day before,
    # `balance_adjusted` what the balance adjustments dated through today
    # moved it by.
    balance_as_of: date_type | None
    balance_opening: float | None
    balance_worked: float | None
    balance_expected_through: float | None
    balance_adjusted: float | None


class LedgerNoteKind(StrEnum):
    """Why a weekday of a ledger week owed less: the three absence types, or a
    holiday of the contract (the region's or the company's)."""

    VACATION = "vacation"
    SICK = "sick"
    OTHER = "other"
    HOLIDAY = "holiday"


class LedgerNote(BaseModel):
    """One weekday of a ledger week that owed less than its term: an absence
    (with `half_day`) or a named holiday (with `name`)."""

    date: date_type
    kind: LedgerNoteKind
    half_day: bool | None = None
    name: str | None = None


class LedgerAdjustment(BaseModel):
    """A balance adjustment as its ledger week shows it: the record, and
    `applied`, the hours it actually moved the balance — `hours` for a
    delta, the target less that morning's balance for a reset, and for a cap
    the hours it took off (0 when the balance was under it)."""

    id: str
    date: date_type
    kind: AdjustmentKind
    hours: float
    note: str | None
    applied: float


class LedgerWeek(BaseModel):
    """One week of the ledger. See `domain/ledger.py` for what each figure is
    and when it is None."""

    week_of: date_type
    worked: float
    days: list[float]  # Mon..Sun, hours
    effective_goal: float | None
    effective_goal_type: GoalType
    effective_goal_overridden: bool
    contract_expected: float | None
    balance_end: float | None
    balance_moved: float | None
    notes: list[LedgerNote]
    adjustments: list[LedgerAdjustment]


class LedgerTotals(BaseModel):
    """The balance as of today and the three terms that move it, since the
    contract started — the standing's "worked since · expected through ·
    adjusted" lines and the ledger's foot. The opening balance is the
    contract's own. `worked` is the hours the balance counts: through
    `ended_on`, under a term that owes hours. Hours worked under an
    objective or 0-hour term are in the weeks' `worked` and not here."""

    expected: float
    worked: float
    adjusted: float
    balance: float


class Ledger(BaseModel):
    """`GET /{id}/ledger`: N weeks newest first, and the totals as of today.
    Typed because it crosses the wire, as `ContractWeek` is."""

    weeks: list[LedgerWeek]
    since: date_type | None  # contract.starts_on, or None
    totals: LedgerTotals | None  # None when there is no balance today
    # The close on `ended_on`, before any adjustment after it — the final
    # balance a settlement then pays out. None without a contract, without
    # `ended_on`, until the day after it (on the last day its hours still
    # count), and when no balance is kept on that day (`week_expectation`'s
    # null rule for the term then).
    ended_balance: float | None


class VacationYear(BaseModel):
    """`GET /{id}/vacation`: one calendar year of a day job's vacation
    entitlement, in days, every figure a whole or half day. See
    `domain/vacation.py` for how each is worked out. Only what the client
    cannot derive: the days per year, the opening and the end date are on
    the contract it already holds."""

    year: int
    # The year's share of `days_per_year`, pro-rated only in the year of
    # `ended_on`; None in the opening year, whose figure is the opening's.
    accrued: float | None
    # What the year before left, after the carry-over rule; a deficit carries
    # whole. 0 in the opening year, whose opening already includes it.
    carried_in: float
    available: float  # (the opening, or accrued) + carried_in
    # The vacation days in the year that cost a day, past and planned.
    booked: float
    remaining: float  # available - booked; negative when overdrawn


# 1,000,000.00 an hour in a two-decimal currency. A month of every hour at it,
# 1e8 x 744, is about 7.4e10: far inside the 2**53 a JavaScript number holds.
RATE_MINOR_MAX = 100_000_000

_Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
# Shape only — one "@" with text either side. It is shown, never mailed.
_Email = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=254, pattern=r"^[^@\s]+@[^@\s]+$")
]


def _forward_one_a_day[T: RateTerm | BillingTerm](terms: list[T]) -> list[T]:
    """Refuse, never sort: a list out of order is a client bug, and sorting
    it would quietly pick which of two same-day terms wins."""
    for earlier, later in pairwise(terms):
        if later.effective_from <= earlier.effective_from:
            msg = "terms must be in ascending order of effective_from, with no two on one day"
            raise ValueError(msg)
    return terms


class RateTerm(BaseModel):
    """One stretch of a client's default rate, from `effective_from` until
    the next. Any day of the week: rates change on invoice dates, not
    Mondays. `rate_minor` is per hour, in the client's currency's minor
    units — cents for EUR, yen for JPY, fils for KWD."""

    effective_from: date_type
    # Strict, so `true` is a 422 and not a rate of 1: lax mode reads a bool,
    # a numeric string and 85.0 as an int.
    rate_minor: int = Field(strict=True, gt=0, le=RATE_MINOR_MAX)


class ClientFields(BaseModel):
    """A client as a write sends it — the body of `POST` and `PUT
    /api/clients`, so its validators are the 422. Every key is required,
    null where it may be: a write replaces the client whole, and a key an
    older client leaves out must be refused, not read as cleared."""

    name: _Name
    contact_name: _Name | None
    contact_email: _Email | None
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
    rates: list[RateTerm]

    @field_validator("rates")
    @classmethod
    def rates_run_forward(cls, rates: list[RateTerm]) -> list[RateTerm]:
        # A field validator rather than a model one, so the 422 names `rates`.
        return _forward_one_a_day(rates)


class Client(ClientFields, TzNormalizedModel):
    """Someone you bill: a record in your own account, not an account of
    theirs (docs/billing.md). One currency for everything billed to them, so
    a client's figures never need an exchange rate.

    `currency` is checked for shape only. That it is a code
    `domain/currencies.py` knows, and that it does not change once anything
    is priced in it, is checked where a client is written: this model is
    re-validated on every read, and a table edit must not make a stored
    client unreadable.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    # Defaulted here, unlike on a write: a None is not stored.
    contact_name: _Name | None = None
    contact_email: _Email | None = None
    rates: list[RateTerm] = Field(default_factory=list)
    archived: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BillingTerm(BaseModel):
    """From `effective_from` on, whether a project's hours are billable and,
    optionally, at a rate of its own; without one they take the client's
    rate in force each day. "Not billable from 1 November" is a term, so
    October's figures stay as they were."""

    effective_from: date_type
    billable: bool = Field(strict=True)
    rate_minor: int | None = Field(default=None, strict=True, gt=0, le=RATE_MINOR_MAX)

    @field_validator("rate_minor")
    @classmethod
    def a_rate_only_where_billable(cls, rate: int | None, info: ValidationInfo) -> int | None:
        # A field validator rather than a model one, so the 422 names the
        # rate. `billable` is declared first and so is in `info.data` —
        # unless it failed, and then its own error is the answer.
        if rate is not None and info.data.get("billable") is False:
            msg = "a term that is not billable takes no rate"
            raise ValueError(msg)
        return rate


class ProjectBillingFields(BaseModel):
    """A project's billing as a write sends it — the body of `PUT
    /api/billing/projects/{id}`, beside `rewrite_past` — so its validators
    are the 422."""

    client_id: str
    terms: list[BillingTerm]

    @field_validator("terms")
    @classmethod
    def terms_run_forward(cls, terms: list[BillingTerm]) -> list[BillingTerm]:
        # A field validator rather than a model one, so the 422 names `terms`.
        return _forward_one_a_day(terms)


class ProjectBilling(ProjectBillingFields):
    """A freelance project billed to one client, under dated terms. One per
    project, in its own collection: never a field of `Project`, which devices
    read and replace-style writes rebuild (docs/billing.md). The client link
    is not dated — a project is for one client, and moving it moves all of
    its hours."""

    project_id: str
    terms: list[BillingTerm] = Field(default_factory=list)


# A lifetime cap: 100,000 h is over eleven years of every hour.
BILLING_BUDGET_HOURS_MAX = Decimal("100000")
# 10,000,000,000.00 in a two-decimal currency: far inside the 2**53 a
# JavaScript number holds.
BILLING_BUDGET_MINOR_MAX = 1_000_000_000_000

# In hundredths, as every hour figure of billing is: 37.333 is refused, not
# rounded. A JSON number arrives here and is held exactly; `true` is refused.
_BillingBudgetHours = Annotated[Decimal, Field(gt=0, le=BILLING_BUDGET_HOURS_MAX, decimal_places=2)]
# Strict, as `RateTerm.rate_minor`: lax mode reads a bool as an int.
_BillingBudgetMinor = Annotated[int, Field(strict=True, gt=0, le=BILLING_BUDGET_MINOR_MAX)]


class BillingBudgetScope(StrEnum):
    """What a billing budget limits: every project billed to a client, or
    one billed project."""

    CLIENT = "client"
    PROJECT = "project"


class BillingBudgetUnit(StrEnum):
    HOURS = "hours"  # billable hours, priced or not
    MONEY = "money"  # the priced amount, in the client's currency


class BillingBudgetPeriod(StrEnum):
    MONTHLY = "monthly"  # the calendar month, every month
    TOTAL = "total"  # one cap from `starts_on` on, with no end


class BillingBudgetFields(BaseModel):
    """A billing budget as a write sends it — the body of `PUT
    /api/billing/budgets/…` — so its validators are the 422. Every key is
    required, null where it may be, as `ClientFields`: a key an older client
    leaves out must be refused, not read as cleared. Declared in this order
    so each validator finds `unit` and `period` in `info.data` — unless one
    of them failed, and then its own error is the answer."""

    unit: BillingBudgetUnit
    period: BillingBudgetPeriod
    limit_hours: _BillingBudgetHours | None
    # In the minor units of the scope's client's currency. No currency is
    # stored: a money budget locks its client's (docs/billing.md).
    limit_minor: _BillingBudgetMinor | None
    starts_on: date_type | None  # a total's first day; null on a monthly budget
    # The early warning. The second threshold is always 100 %.
    warn_at_percent: int = Field(strict=True, ge=1, le=99)

    # Field validators rather than model ones, so the 422 names the key.

    @field_validator("limit_hours")
    @classmethod
    def a_limit_in_hours_only_in_hours(
        cls, hours: Decimal | None, info: ValidationInfo
    ) -> Decimal | None:
        unit = info.data.get("unit")
        if unit is BillingBudgetUnit.HOURS and hours is None:
            msg = "a budget in hours takes limit_hours"
            raise ValueError(msg)
        if unit is BillingBudgetUnit.MONEY and hours is not None:
            msg = "a budget in money takes limit_minor, not limit_hours"
            raise ValueError(msg)
        return hours

    @field_validator("limit_minor")
    @classmethod
    def a_limit_in_money_only_in_money(cls, minor: int | None, info: ValidationInfo) -> int | None:
        unit = info.data.get("unit")
        if unit is BillingBudgetUnit.MONEY and minor is None:
            msg = "a budget in money takes limit_minor"
            raise ValueError(msg)
        if unit is BillingBudgetUnit.HOURS and minor is not None:
            msg = "a budget in hours takes limit_hours, not limit_minor"
            raise ValueError(msg)
        return minor

    @field_validator("starts_on")
    @classmethod
    def a_start_only_on_a_total(
        cls, day: date_type | None, info: ValidationInfo
    ) -> date_type | None:
        period = info.data.get("period")
        if period is BillingBudgetPeriod.TOTAL and day is None:
            msg = "a total budget takes the day it starts on"
            raise ValueError(msg)
        if period is BillingBudgetPeriod.MONTHLY and day is not None:
            msg = "a monthly budget is the calendar month and takes no starts_on"
            raise ValueError(msg)
        return day


class BillingBudget(BillingBudgetFields):
    """A limit on a client, or on one billed project, in hours or in money,
    monthly or in total (docs/billing.md, phase 1b). One per scope, in its
    own collection, addressed by its scope: it has no id. Only the limit is
    stored; what is spent and what is left are worked out on every read
    (`domain/billing_budgets.py`).

    That a project scope is billed, and the currency rules, are checked
    where a budget is written, as `Client`'s currency is: this model is
    re-validated on every read."""

    scope: BillingBudgetScope
    scope_id: str  # a client's id or a project's
    # Defaulted here, unlike on a write: a None is not stored. The default
    # is validated too, so a key left out meets the unit's and the period's
    # rules as a null does — a backup written by hand may leave one out.
    limit_hours: _BillingBudgetHours | None = Field(default=None, validate_default=True)
    limit_minor: _BillingBudgetMinor | None = Field(default=None, validate_default=True)
    starts_on: date_type | None = Field(default=None, validate_default=True)


class BillableOverride(BaseModel):
    """One entry marked billable or not, against its project's term. A fact
    about the entry: it survives a move to another project, and counts only
    while the entry's project is billed."""

    beat_id: str
    billable: bool = Field(strict=True)


# A report link backs an invoice period, and the assembler walks its range a
# day at a time, so a link cannot span more than a year and a day.
REPORT_RANGE_MAX_DAYS = 366


class ReportLinkFields(BaseModel):
    """A report link as a write sends it — the body of `POST
    /api/clients/{id}/links` — so its validators are the 422. Every key is
    required: a flag an older client leaves out must be refused, not read as
    off."""

    first: date_type
    last: date_type
    # IANA. That the zone is one `zoneinfo` knows is checked where a link is
    # written, as a client's currency is: this model is re-validated on every
    # read, and a zone leaving the tz database must not make a stored link
    # unreadable.
    tz: str = Field(min_length=1)
    # Strict, as `BillingTerm.billable`: lax mode reads 1 and "true" as True,
    # and showing a client money by accident is the one mistake to rule out.
    show_amounts: bool = Field(strict=True)
    show_entries: bool = Field(strict=True)

    @field_validator("last")
    @classmethod
    def range_runs_forward_and_is_bounded(cls, last: date_type, info: ValidationInfo) -> date_type:
        # A field validator rather than a model one, so the 422 names `last`.
        # `first` is declared first and so is in `info.data` — unless it
        # failed, and then its own error is the answer.
        first = info.data.get("first")
        if first is None:
            return last
        if last < first:
            msg = "last is before first"
            raise ValueError(msg)
        if (last - first).days + 1 > REPORT_RANGE_MAX_DAYS:
            msg = f"a report link covers at most {REPORT_RANGE_MAX_DAYS} days"
            raise ValueError(msg)
        return last


class ReportLink(ReportLinkFields, TzNormalizedModel):
    """A link a client opens with no login to read its own hours for a fixed
    range (docs/billing.md, phase 1c).

    It holds no figures: every number is worked out on each read by
    `assemble_client`, from this client's inputs only. The range and `tz` are
    frozen here so two reads agree — the days are bucketed in the owner's
    zone, not the reader's, because those are the days the owner invoiced on.

    `token` is stored as it is read, not hashed: whoever can read this
    collection can read the hours it serves out of the same database, and the
    owner has to be able to open the link they sent a client last month.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    client_id: str
    token: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Beat(TzNormalizedModel):
    """A time tracking entry (heartbeat) for a project.

    Represents a work session with a start time and optional end time.
    When end is None, the timer is considered active.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    project_id: str
    start: datetime = Field(default_factory=lambda: datetime.now(UTC))
    end: datetime | None = None
    note: str | None = None
    tags: list[str] = Field(default_factory=list)
    # Set when the beat was tracked on an organisation's project: this beat is
    # that organisation's working-time record, and the stamp is what says so
    # on the document itself, so the question is answered per row — by the
    # organisation's read, which asks for its own stamp and nothing else, and
    # by an account's erasure, which keeps the stamped rows and nothing else
    # (docs/organisations.md). Written by the services that write a beat
    # against its project, and by connecting a project over its shared
    # history; moving a beat to a personal project clears it.
    organisation_id: str | None = None

    @computed_field
    @property
    def is_active(self) -> bool:
        """Check if this beat represents an active timer."""
        return self.end is None

    @computed_field
    @property
    def duration(self) -> timedelta:
        """Calculate the duration of this beat.

        For active beats, calculates time elapsed since start.
        For completed beats, calculates time between start and end.
        """
        end = self.end or datetime.now(UTC)
        # Ensure both datetimes are timezone-aware before subtraction
        start = normalize_tz(self.start)
        end = normalize_tz(end)
        return end - start

    @computed_field
    @property
    def day(self) -> date_type:
        """The date this beat started on."""
        return self.start.date()


class ProjectOrganisation(BaseModel):
    """The organisation that owns a project, as its member sees it on the
    project: enough to mark it in a list, and the instant from which the
    member's hours on it are the organisation's (docs/organisations.md).
    `shared_from` is the member's own choice when they connected a project of
    theirs, and the moment of assignment otherwise."""

    id: str
    name: str
    logo_url: str | None = None
    shared_from: datetime


# On an organisation's project, which fields are whose. The organisation's
# fields live on the project document and only an organisation admin writes
# them; the personal fields live on the member's assignment, so two members
# of one project each keep their own goal, their own local repo paths and —
# until an employer owns it (stage 3) — their own contract. The repository
# merges the two on read and splits them on write; `ProjectService` refuses a
# member's write that changes an organisation field (409 ORGANISATION_PROJECT).
ORGANISATION_FIELDS = frozenset(
    {"name", "description", "color", "archived", "kind", "github_repo", "category"}
)
PERSONAL_FIELDS = frozenset(
    {"weekly_goal", "goal_type", "goal_overrides", "autostart_repos", "contract"}
)


class Project(BaseModel):
    """A project to track time against.

    Projects are named entities that can accumulate time through beats.
    They can be archived when no longer active.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    name: str
    description: str | None = None
    color: str | None = None  # User-chosen hex color, e.g. "#5B9CF6"
    archived: bool = False
    weekly_goal: float | None = None  # Weekly goal in hours
    goal_type: GoalType = GoalType.TARGET  # target or cap
    goal_overrides: list[GoalOverride] = Field(default_factory=list)
    github_repo: str | None = None  # GitHub repo in "owner/repo" format
    category: str | None = None  # Activity category: coding, design, writing, etc.
    autostart_repos: list[str] = Field(default_factory=list)  # Local repo paths for auto-timer
    kind: ProjectKind = ProjectKind.SIDE_PROJECT
    contract: Contract | None = None  # only meaningful when kind == day_job
    # Who owns the project when it is not the person reading it. Read-only:
    # set by the repository when it merges an organisation's project with the
    # reader's assignment to it, never by a request. On such a project the
    # organisation's fields (`ORGANISATION_FIELDS`) are the organisation's to
    # write and the personal ones (`PERSONAL_FIELDS`) stay the member's.
    organisation: ProjectOrganisation | None = None

    def goal_term(self, week_monday: date_type) -> ContractTerm | None:
        """The contract term that governs this week's goal, or None when the personal goal does.

        The contract sets the goal on a day job whose term in force on the
        week's Monday is time-based; that term's `hours_per_week` is what the
        week owes, nominally. A term of 0 hours — the migration's reading of
        an override that said "no goal from here", or a custom term typed as
        0 — governs too, so the personal goal does not resurface under it,
        and `effective_goal` reports it as no goal at all. Before the first
        term, under an objective term, on a day job without a contract, and
        on every other kind, the personal goal applies. A term changing
        mid-week takes over the following Monday: the week is one figure, and
        its Monday decides.

        `ended_on` is not consulted, as `Contract.term_on` does not: the last
        term stays the goal after the contract ends, and the UI hides the
        personal goal on the same rule, so no goal reappears that the form
        cannot show. Archiving is what takes a finished job out of the readers.
        """
        if self.kind is not ProjectKind.DAY_JOB or self.contract is None:
            return None
        term = self.contract.term_on(week_monday)
        return term if term is not None and term.is_time_based else None

    def goal_overridden(self, week_monday: date_type) -> bool:
        """Whether a goal override resolves for the week — what lets the UI
        tell "override says no goal" (None, overridden) from "no override and
        no project default" (None, not overridden).

        False on a week the contract governs: `effective_goal` does not read
        the overrides there, so none is in effect however many are stored.
        """
        if self.goal_term(week_monday) is not None:
            return False
        return any(
            o.week_of == week_monday
            or (o.effective_from is not None and o.effective_from <= week_monday)
            for o in self.goal_overrides
        )

    def effective_goal(self, week_monday: date_type) -> tuple[float | None, GoalType]:
        """Resolve the effective goal for a given week (identified by its Monday).

        A contract that governs the week (`goal_term`) is the goal — its plain
        weekly hours, not adjusted for holidays or absences (the week route
        reports the adjusted expectation), always a target, and the personal
        goal and its overrides are not read at all. A governing term of 0
        hours is no goal (None), as the "no goal" override it was migrated
        from was, not a goal of nothing. Otherwise the precedence is one-off
        week_of > latest effective_from <= week_monday > project default.
        """
        term = self.goal_term(week_monday)
        if term is not None:
            return term.hours_per_week or None, GoalType.TARGET

        # 1. One-off override
        for o in self.goal_overrides:
            if o.week_of == week_monday:
                return o.weekly_goal, o.goal_type or self.goal_type

        # 2. Permanent override — the latest one that has taken effect by then
        in_effect = [
            o
            for o in self.goal_overrides
            if o.effective_from is not None and o.effective_from <= week_monday
        ]
        if in_effect:
            best = max(in_effect, key=lambda o: o.effective_from)
            return best.weekly_goal, best.goal_type or self.goal_type

        # 3. Default
        return self.weekly_goal, self.goal_type


class ProjectBreakdownEntry(BaseModel):
    """One project's share of a week, as a digest reports it.

    Typed rather than a bare dict because it crosses the wire: it is what
    the UI's digest list renders, and an untyped `list[dict]` publishes an
    OpenAPI `array of object` with no properties, which leaves every client
    casting the rows back into a shape by hand.
    """

    project_id: str
    name: str
    hours: float


class WeeklyDigest(TzNormalizedModel):
    """A generated weekly summary with insights and productivity score."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    week_of: date_type  # Monday of the week
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    total_hours: float
    session_count: int
    active_days: int
    top_project_id: str | None = None
    top_project_name: str | None = None
    top_project_hours: float = 0
    vs_last_week_pct: float | None = None
    longest_day: str | None = None  # Day name, e.g. "Wednesday"
    longest_day_hours: float = 0
    best_streak: int = 0
    observation: str = ""
    project_breakdown: list[ProjectBreakdownEntry] = Field(default_factory=list)
    productivity_score: int = 0


class InsightCard(BaseModel):
    """A single detected pattern or insight."""

    id: str  # uuid for dismiss tracking
    type: str  # day_pattern, time_pattern, stale_project, session_trend, etc.
    title: str
    body: str
    data: dict = Field(default_factory=dict)
    priority: int = 3  # 1-5, higher = more important


class UserInsights(TzNormalizedModel):
    """Cached pattern detection results for a user."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    insights: list[InsightCard] = Field(default_factory=list)
    dismissed_ids: list[str] = Field(default_factory=list)


class WeeklyPlan(BaseModel):
    """A weekly time budget plan with per-project allocations."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    week_of: date_type  # Monday of the week
    budgets: list[dict] = Field(default_factory=list)  # [{project_id, planned_hours}]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PairingCode(BaseModel):
    """A short-lived pairing code for daemon-to-API authentication.

    The raw code is shown to the user once; only its SHA-256 hash is stored.
    Expires after 5 minutes via MongoDB TTL index on expires_at.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    user_id: str
    code_hash: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime = Field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=5))


class SSOFlow(BaseModel):
    """A sign-in through a provider, between leaving for it and coming back.

    Held server-side, so nothing the browser carries back can change what is
    checked: the nonce the ID token must repeat, the PKCE verifier that
    proves the code was asked for here, and — for a link — whose account the
    identity goes on. Keyed by a hash of the `state` sent through the
    provider, taken exactly once, and expired by a TTL index after ten minutes.
    """

    state_hash: str
    provider: str
    nonce: str
    code_verifier: str
    intent: Literal["sign_in", "link"]
    # Set for a link: the account that asked, which must also finish it.
    user_id: str | None = None
    expires_at: datetime = Field(default_factory=lambda: datetime.now(UTC) + timedelta(minutes=10))


class DeviceRegistration(BaseModel):
    """A registered daemon device paired to a user account.

    Created when a daemon exchanges a pairing code for a long-lived device token.
    The device token is a JWT with type="device" scoped to signal-writing endpoints.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    user_id: str
    device_id: str
    device_name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen: datetime | None = None
    revoked: bool = False


class GitHubIntegration(BaseModel):
    """A connected GitHub OAuth integration (per-user)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    access_token: str = ""
    github_username: str = ""
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CalendarIntegration(TzNormalizedModel):
    """A connected Google Calendar OAuth integration."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    provider: str = "google"
    access_token: str = ""
    refresh_token: str = ""
    token_expiry: datetime | None = None
    calendar_ids: list[str] = Field(default_factory=lambda: ["primary"])
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class FitbitIntegration(BaseModel):
    """A connected Fitbit OAuth integration (per-user)."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    access_token: str = ""
    refresh_token: str = ""
    token_expiry: datetime | None = None
    fitbit_user_id: str = ""
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OuraIntegration(BaseModel):
    """A connected Oura integration using a personal access token."""

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    access_token: str = ""
    oura_user_id: str = ""
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BiometricDay(TzNormalizedModel):
    """A single day of biometric data from any source.

    Keyed by (user_id, date, source) for upsert. Multiple sources per day
    are allowed (e.g. HealthKit + Oura). Priority: HealthKit > Oura > Fitbit.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    date: date_type = Field(default_factory=lambda: datetime.now(UTC).date())
    source: str = ""  # healthkit, health_connect, fitbit, oura
    sleep_minutes: int | None = None
    sleep_efficiency: float | None = None  # 0.0–1.0
    hrv_ms: float | None = None
    resting_hr_bpm: int | None = None
    steps: int | None = None
    readiness_score: int | None = None  # Oura 0–100
    workouts: list[dict] = Field(default_factory=list)  # [{kind, minutes, avg_hr}]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PendingSuggestion(TzNormalizedModel):
    """An auto-timer suggestion the API has surfaced but the user hasn't
    yet acted on.

    Created on the API side whenever the daemon's POST to
    `/api/signals/suggest-timer` returns `should_suggest=True`. The
    companion's notification poller pulls these via
    `GET /api/signals/pending-suggestions`, fires
    `notifyAutoTimerSuggestion`, and dedupes by id. There's no separate
    "ack" — staleness is handled by the read endpoint's `since` window.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    project_id: str
    project_name: str
    suggested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    # The categorical signal that triggered the suggestion. Stored for
    # debugging / future analytics — the companion notification body
    # doesn't reference it today.
    dominant_category: str = ""
    # When the match came from an editor-repo → autostart_repos hit
    # (rather than the looser category fallback), we keep the repo path
    # so a future "yes" tap can confirm "start tracking on this repo".
    editor_repo: str | None = None


class FlowWindow(TzNormalizedModel):
    """A computed flow-state window from the daemon's signal collector.

    Represents a 1-minute window of aggregated desktop activity. The daemon
    computes the flow score locally and sends only the aggregate to the API.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    device_id: str = ""
    window_start: datetime = Field(default_factory=lambda: datetime.now(UTC))
    window_end: datetime = Field(default_factory=lambda: datetime.now(UTC))
    flow_score: float = 0.0
    cadence_score: float = 0.0
    coherence_score: float = 0.0
    category_fit_score: float = 0.0
    idle_fraction: float = 0.0
    dominant_bundle_id: str = ""
    dominant_category: str = ""
    context_switches: int = 0
    active_project_id: str | None = None
    # Editor context — populated by the daemon from the most recent fresh
    # heartbeat received from an editor extension (today: VS Code via
    # `daemon/internal/editor/listener.go`). All three default to None when
    # no editor was active during the window.
    editor_repo: str | None = None
    editor_branch: str | None = None
    editor_language: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SignalSummary(TzNormalizedModel):
    """Hourly aggregation of signal categories for the privacy dashboard.

    Stores per-category sample counts without any raw signal data.
    Keyed by (user_id, device_id, hour) for upsert.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    device_id: str = ""
    hour: datetime = Field(default_factory=lambda: datetime.now(UTC))
    categories: dict[str, int] = Field(default_factory=dict)
    total_samples: int = 0
    idle_samples: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Webhook(TzNormalizedModel):
    """A registered webhook URL that receives timer events.

    Events: timer.start, timer.stop — both dispatched from the timer routes
    in `api/routers/projects.py`. `events` is not validated against that set,
    so a row can name an event nothing emits; it simply never fires.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str | None = None
    url: str
    events: list[str] = Field(default_factory=lambda: ["timer.start", "timer.stop"])
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# --- Organisations (docs/organisations.md) ---------------------------------


class OrgRole(StrEnum):
    """What a member may do in an organisation. Each role includes the ones
    below it: an owner is an admin, an admin is a member."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"

    @property
    def rank(self) -> int:
        return _ROLE_RANK[self]

    def at_least(self, other: OrgRole) -> bool:
        return self.rank >= other.rank


_ROLE_RANK = {OrgRole.MEMBER: 0, OrgRole.ADMIN: 1, OrgRole.OWNER: 2}


class WeekStart(StrEnum):
    """Which day an organisation's week begins on, for its own reports."""

    MONDAY = "monday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


_OrgName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class OrganisationFields(BaseModel):
    """What an organisation is set up with: the fields its admins write."""

    name: _OrgName
    logo_url: Annotated[str, StringConstraints(max_length=2000)] | None = None
    week_start: WeekStart = WeekStart.MONDAY
    # The region whose public holidays a contract under it defaults to; checked
    # against the calendar library at write time, as a contract's region is.
    holiday_country: str | None = None
    holiday_subdivision: str | None = None
    timezone: str = "UTC"


class Organisation(OrganisationFields, TzNormalizedModel):
    """A party that owns projects and reads the hours on them. Not a user,
    and not scoped by one: `user_id` is a column of no document here."""

    id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_by: str


class MembershipEnd(StrEnum):
    """Why a membership ended."""

    LEFT = "left"
    REMOVED = "removed"
    ERASED = "erased"  # the account was deleted; the record stays (decision 3)


class OrgMembership(TzNormalizedModel):
    """One person in one organisation, once: a membership that ends keeps its
    document, with `left_at`, and joining again reopens it.

    `name` and `email` are what the organisation knew the person by, taken
    from the account when they joined. They stay when the account is erased
    and `user_id` becomes a tombstone (`erased:<membership id>`, which no
    account ever has) — the one place a name outlives its account, as the
    employer's record (docs/organisations.md, decision 3).
    """

    id: str | None = None
    organisation_id: str
    user_id: str
    role: OrgRole
    name: str
    email: str
    joined_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    left_at: datetime | None = None
    left_reason: MembershipEnd | None = None

    @property
    def active(self) -> bool:
        return self.left_at is None


class OrgInvite(TzNormalizedModel):
    """A way in. With `email`, an invitation to one address, taken once; with
    none, a link anyone may use until it expires or is revoked, which with
    `requires_approval` makes a join request rather than a member. The
    token is the whole of what the joiner presents."""

    id: str | None = None
    organisation_id: str
    token: str
    email: str | None = None
    role: OrgRole = OrgRole.MEMBER
    requires_approval: bool = False
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    accepted_at: datetime | None = None
    accepted_by: str | None = None
    revoked_at: datetime | None = None

    def open_at(self, now: datetime) -> bool:
        """Still usable: not revoked, not expired, and — for an invitation to
        one address — not yet taken."""
        if self.revoked_at is not None or normalize_tz(self.expires_at) <= normalize_tz(now):
            return False
        return self.email is None or self.accepted_at is None


class JoinDecision(StrEnum):
    APPROVED = "approved"
    DECLINED = "declined"


class OrgJoinRequest(TzNormalizedModel):
    """Someone who used an invite link with an approval step, waiting."""

    id: str | None = None
    organisation_id: str
    user_id: str
    invite_id: str
    name: str
    email: str
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    decided_at: datetime | None = None
    decision: JoinDecision | None = None
    decided_by: str | None = None


class OrgAssignment(TzNormalizedModel):
    """One member on one of the organisation's projects, and the personal
    half of that project for them (`PERSONAL_FIELDS`).

    `shared_from` is the instant from which the member's hours on the
    project are the organisation's: the moment of assignment, or on a
    connected project the local midnight of the day the member chose. An
    assignment that ends keeps its document with `ended_at`; assigning
    again reopens it.
    """

    id: str | None = None
    organisation_id: str
    project_id: str
    user_id: str
    shared_from: datetime
    assigned_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    assigned_by: str | None = None
    ended_at: datetime | None = None
    weekly_goal: float | None = None
    goal_type: GoalType = GoalType.TARGET
    goal_overrides: list[GoalOverride] = Field(default_factory=list)
    autostart_repos: list[str] = Field(default_factory=list)
    contract: Contract | None = None

    @property
    def active(self) -> bool:
        return self.ended_at is None


class OrgAuditEvent(TzNormalizedModel):
    """One thing that happened in an organisation, written as it happens and
    read by nothing yet: membership, roles, projects, assignments, a
    connected project, an erased account. Kept from the start because it is
    cheap to write and impossible to backfill (the roadmap's stage 4 note)."""

    id: str | None = None
    organisation_id: str
    at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    actor_user_id: str | None
    event: str
    subject_user_id: str | None = None
    project_id: str | None = None
    details: dict[str, object] = Field(default_factory=dict)


class OrgProject(BaseModel):
    """An organisation's project as the organisation sees it: the document's
    fields (`ORGANISATION_FIELDS`) and nothing personal, since the personal
    half is each member's own."""

    id: str
    name: str
    description: str | None = None
    color: str | None = None
    archived: bool = False
    kind: ProjectKind = ProjectKind.SIDE_PROJECT
    github_repo: str | None = None
    category: str | None = None


class MemberTotals(TzNormalizedModel):
    """What one member's finished entries on one project add up to, all time.
    Mongo hands the instants back naive; this makes them UTC like every other."""

    entries: int = 0
    hours: float = 0.0
    first: datetime | None = None
    last: datetime | None = None
