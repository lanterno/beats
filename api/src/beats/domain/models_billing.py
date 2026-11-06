"""Billing: clients, rates, project billing, budgets and report links
(docs/billing.md).

Split out of `models.py` at the ceiling in roadmaps/file-sizes.md and
re-exported from it, so every import site still names `beats.domain.models`.
"""

from datetime import UTC, datetime
from datetime import date as date_type
from decimal import Decimal
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
)

from beats.domain.utils import TzNormalizedModel

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
