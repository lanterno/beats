"""Billing and public-report schemas (docs/billing.md).

Split out of `schemas.py` at the size ceiling (CLAUDE.md § Conventions) and
re-exported from it, so every router still imports `beats.api.schemas`.
"""

from datetime import date as date_type
from datetime import datetime

from pydantic import BaseModel, Field

from beats.domain.billing import RateSource
from beats.domain.billing_budgets import BillingBudgetState
from beats.domain.models import (
    BillingBudgetFields,
    BillingBudgetPeriod,
    BillingBudgetScope,
    BillingBudgetUnit,
    BillingTerm,
    ClientFields,
    ProjectBillingFields,
    RateTerm,
    ReportLinkFields,
)


class ClientWriteRequest(ClientFields):
    """Request body for adding a client: the domain's fields, every key
    required, null where it may be. Its rates are `rate_minor` per hour in
    the currency's minor units, strictly ascending by `effective_from`."""


class ClientUpdateRequest(ClientFields):
    """Request body for replacing a client: the same keys, and
    `rewrite_past`, required, saying the caller has confirmed a change to
    figures before the current month."""

    rewrite_past: bool = Field(strict=True)


class ClientResponse(BaseModel):
    """A client as stored, with its currency's minor units from the API's
    table, and whether its currency is locked: something is priced in it,
    or a money billing budget is in it, so it can no longer change."""

    id: str
    name: str
    contact_name: str | None = None
    contact_email: str | None = None
    currency: str
    minor_units: int
    rates: list[RateTerm]
    archived: bool
    created_at: datetime
    currency_locked: bool


class ProjectBillingRequest(ProjectBillingFields):
    """Request body for billing a project: its client and the whole list of
    terms, and `rewrite_past`, all required."""

    rewrite_past: bool = Field(strict=True)


class ProjectBillingResponse(BaseModel):
    """A project's billing, with its client's currency and minor units, the
    currency every `rate_minor` in it is in."""

    project_id: str
    client_id: str
    currency: str
    minor_units: int
    terms: list[BillingTerm]


class BillableOverrideRequest(BaseModel):
    """Request body for marking one entry billable or not."""

    billable: bool = Field(strict=True)


class BillableOverrideResponse(BaseModel):
    """One entry's billable mark, against its project's term."""

    beat_id: str
    billable: bool


class BillingLineResponse(BaseModel):
    """A run of consecutive days of one project at one rate from one source.
    `rate_minor`, `source` and `amount_minor` are all null on an unpriced
    run. `hours` are to the hundredth, and `amount_minor` is `hours` times
    `rate_minor`, to a whole minor unit, half-up."""

    project_id: str
    project_name: str
    rate_minor: int | None
    source: RateSource | None
    first: date_type
    last: date_type
    hours: float
    amount_minor: int | None


class BillingEntryResponse(BaseModel):
    """A finished entry of a billed project, billable or not. `day` is the
    local day it started on, which decides its month and its rate. `hours`
    is for display; the lines are the figures."""

    beat_id: str
    project_id: str
    day: date_type
    start: datetime
    end: datetime
    hours: float
    billable: bool
    overridden: bool
    rate_minor: int | None


class ClientBillingResponse(BaseModel):
    """One client's figures for the month, in its one currency. The hours and
    the amount are sums of the lines; `unpriced_hours` is the part of
    `billable_hours` with no rate. `running`: a billable timer is running,
    and counts once it stops."""

    client_id: str
    name: str
    archived: bool
    currency: str
    minor_units: int
    running: bool
    billable_hours: float
    non_billable_hours: float
    unpriced_hours: float
    amount_minor: int
    lines: list[BillingLineResponse]
    entries: list[BillingEntryResponse]


class CurrencyTotalResponse(BaseModel):
    """Every listed client in one currency, summed: no figure holds two."""

    currency: str
    minor_units: int
    billable_hours: float
    unpriced_hours: float
    amount_minor: int


class UnattachedHoursResponse(BaseModel):
    """A freelance project with finished hours in the month and no client:
    hours in no figure of the report."""

    project_id: str
    name: str
    hours: float


class BillingMonthResponse(BaseModel):
    """What is billable in a month, per client and per currency: the whole
    month once it has ended, `first` through today while it runs."""

    month: str  # YYYY-MM
    first: date_type
    last: date_type
    totals: list[CurrencyTotalResponse]
    clients: list[ClientBillingResponse]
    unattached: list[UnattachedHoursResponse]


class ReportLinkRequest(ReportLinkFields):
    """Request body for minting a report link: the range, the timezone its
    days are bucketed in, and the two flags, every key required. The range
    runs forward and covers at most 366 days."""


class ReportLinkResponse(BaseModel):
    """A report link as its owner sees it, token included: the owner has to
    be able to re-copy the link they sent a client last month."""

    id: str
    client_id: str
    token: str
    first: date_type
    last: date_type
    tz: str
    show_amounts: bool
    show_entries: bool
    created_at: datetime


# ---------------------------------------------------------------------- #
# The public report (phase 1c)
#
# These three are what a reader with no session sees, and they are written
# out field by field on purpose: they do not inherit from
# `ClientBillingResponse`, `BillingLineResponse` or `BillingEntryResponse`,
# so a field added to the private month report later cannot reach a client's
# eyes by inheritance. Deliberately absent, though the assembler has them:
# `client_id`, `project_id` and `beat_id` (a client has no use for the
# owner's internal ids), `source` and `overridden` (how a figure was arrived
# at), `non_billable_hours` (hours the client is not billed for) and
# `running` (a report says nothing about now). See docs/billing.md, 1c
# decisions 4, 5 and 7.
# ---------------------------------------------------------------------- #


class ReportLineResponse(BaseModel):
    """A run of consecutive days of one project at one rate. `rate_minor` and
    `amount_minor` are null on an unpriced run, and on every line when the
    link does not show amounts."""

    project_name: str
    first: date_type
    last: date_type
    hours: float
    rate_minor: int | None
    amount_minor: int | None


class ReportEntryResponse(BaseModel):
    """One billable entry: the local day it started on, when it ran, and how
    long. Empty on a link that does not show entries."""

    day: date_type
    start: datetime
    end: datetime
    hours: float


class ReportResponse(BaseModel):
    """What `GET /api/reports/{token}` answers: one client's billable work
    over the link's frozen range.

    With `show_amounts` false, `currency`, `minor_units`, `unpriced_hours`,
    `amount_minor` and every line's rate and amount are null, and the hours
    still add up — a proof of time with the price left out.
    """

    client_name: str
    first: date_type
    last: date_type
    show_amounts: bool
    show_entries: bool
    currency: str | None
    minor_units: int | None
    billable_hours: float
    unpriced_hours: float | None
    amount_minor: int | None
    lines: list[ReportLineResponse]
    entries: list[ReportEntryResponse]


class BillingBudgetRequest(BillingBudgetFields):
    """Request body for a billing budget: the domain's fields, every key
    required, null where it may be. Exactly the limit of its `unit` is set
    (`limit_hours` to the hundredth, or `limit_minor` in the client's
    currency), and `starts_on` only on a total."""


class BillingBudgetResponse(BaseModel):
    """A billing budget as stored, with its client and that client's
    currency and minor units, the currency a `limit_minor` is in."""

    scope: BillingBudgetScope
    scope_id: str
    client_id: str
    currency: str
    minor_units: int
    unit: BillingBudgetUnit
    period: BillingBudgetPeriod
    limit_hours: float | None
    limit_minor: int | None
    starts_on: date_type | None
    warn_at_percent: int


class BillingBudgetRunningResponse(BaseModel):
    """A running timer that counts on a billing budget, and the instants,
    in UTC, at which it alone would cross the warning and the limit: null
    once crossed, and both null when it has no rate under a money budget or
    another timer counts too."""

    project_id: str
    since: datetime
    priced: bool
    near_at: datetime | None
    over_at: datetime | None


class BillingBudgetStatusResponse(BaseModel):
    """A billing budget read as of today: the current month, or a total from
    `starts_on`, through `through`. The three figures are there whatever the
    unit; only the unit's own `remaining_…` is set, negative when over. No
    figure counts a running timer: `running` answers it. An upcoming total
    has no figures, no projection and no running timer. `active` is false
    while its client or its project is archived: it is read, but never
    alerts."""

    scope: BillingBudgetScope
    scope_id: str
    client_id: str
    name: str
    active: bool
    currency: str
    minor_units: int
    unit: BillingBudgetUnit
    period: BillingBudgetPeriod
    limit_hours: float | None
    limit_minor: int | None
    starts_on: date_type | None
    warn_at_percent: int
    upcoming: bool
    first: date_type
    last: date_type | None
    through: date_type | None
    billable_hours: float
    unpriced_hours: float
    amount_minor: int
    remaining_hours: float | None
    remaining_minor: int | None
    percent_used: int
    state: BillingBudgetState
    runs_out_on: date_type | None
    running: BillingBudgetRunningResponse | None
