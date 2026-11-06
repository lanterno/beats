"""Goals, work contracts, absences, the ledger and vacation
(docs/work-contracts.md).

Split out of `models.py` at the ceiling in roadmaps/file-sizes.md and
re-exported from it, so every import site still names `beats.domain.models`.
The goal models come along because a contract term governs the goal.
"""

from datetime import date as date_type
from enum import StrEnum
from itertools import pairwise
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)


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
