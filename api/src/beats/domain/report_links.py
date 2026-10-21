"""Report links: the token, the rules that read a clock, the public shapes and
the arithmetic of a client's report (docs/billing.md, phase 1c).

Pure, beside `domain/billing.py` and made of it. Nothing here reads a clock:
the day a rule is checked on arrives as `today`, in the link's time zone.

    the token     `lpr_` + 256 random bits, url-safe; stored only as its
                  HMAC-SHA256 under `REPORT_LINK_KEY`
    the months    `assemble_client` over each of `month_slices(first, last)`,
                  so a whole month in a link is that month on the Clients
                  page, line for line. Never one range: a line is rounded
                  once per month, as the invoice rounds it
    hours only    the same lines, priced, then merged per project per month:
                  the invoice's hours, and no day a rate changed on
    a day row     one project's billable entries that started on one local
                  day, summed exactly and rounded once: for display, as an
                  entry's hours are

What a report shows has a class per shape, each `extra="forbid"`, and
`public_report` fills every field by name. A field added to `ClientBilling`
later has nowhere to cross to, and an hours-only report has no field a
money figure could travel in: not `exclude_none`, which would make an
unpriced line's null rate look like a hidden one.
"""

import hashlib
import hmac
import re
import secrets
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import NamedTuple
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from beats.domain.billing import (
    BillingEntry,
    BillingLine,
    ClientBilling,
    assemble_client,
    hours_of,
    microseconds_of,
    month_slices,
)
from beats.domain.currencies import minor_units
from beats.domain.exceptions import RangeNotOver, ReportLinkExpiryOutOfRange
from beats.domain.models import (
    REPORT_LINK_MAX_LIFETIME_DAYS,
    Beat,
    Client,
    Project,
    ProjectBilling,
    ReportLink,
    ReportScope,
)
from beats.domain.timesheet import month_end
from beats.domain.utils import local_date

_ZERO_HOURS = Decimal("0.00")

TOKEN_PREFIX = "lpr_"
# A body's `token` longer than this is a 422 before anything else is read.
TOKEN_MAX_LENGTH = 64
TOKEN_SHAPE = re.compile(r"^lpr_[A-Za-z0-9_-]{43}$")


def new_token(key: bytes) -> tuple[str, str]:
    """A new link's token and its hash. The token is shown once, by the
    create, and stored nowhere."""
    token = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return token, token_hash(token, key)


def token_hash(token: str, key: bytes) -> str:
    """What is stored, and looked up, for `token`. Keyed, so that rotating
    `REPORT_LINK_KEY` ends every link at once, and a database restored
    from before a link was turned off cannot bring it back (DATA.md). A salt
    or a slow hash would add nothing against 256 random bits, and would make
    the public route a CPU sink."""
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


def key_id(key: bytes) -> str:
    """Which key a link was made under, stored beside its token's hash. Once
    `REPORT_LINK_KEY` is rotated no token's hash matches any more, and a
    link whose `key_id` is not the running key's is listed as ended rather
    than as one that still works. An HMAC of a fixed message: it names the
    key and gives nothing of it away."""
    return hmac.new(key, b"report link key id", hashlib.sha256).hexdigest()


def well_formed(token: str) -> bool:
    """Whether `token` could be one this module made: anything else is
    answered as a dead link without a read."""
    return TOKEN_SHAPE.fullmatch(token) is not None


def is_live(link: ReportLink, today: date) -> bool:
    """A link works through its `expires_on`, `today` read in its zone."""
    return today <= link.expires_on


def check_range_over(last: date, today: date) -> None:
    """A report covers finished days: its last is yesterday at the latest."""
    if last >= today:
        raise RangeNotOver()


def check_expiry(expires_on: date, today: date) -> None:
    """A new link works from today for at most a year and a day."""
    if not today <= expires_on <= today + timedelta(days=REPORT_LINK_MAX_LIFETIME_DAYS):
        raise ReportLinkExpiryOutOfRange()


# What a report shows. Siblings, never subclasses of one another: a field
# typed with a base class serialises a subclass's instance as the base,
# dropping the fields it adds. Hours are floats here only, as in every
# response; the domain works them in Decimal.


class _Shape(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReportShows(_Shape):
    """What the link was made to show, so the page knows its shape."""

    amounts: bool
    notes: bool


class ReportMoney(_Shape):
    currency: str
    minor_units: int
    amount_minor: int  # Σ priced line amounts
    unpriced_hours: float  # the part of the billable hours with no rate


class PricedLine(_Shape):
    """A run of days of one project at one rate, as the invoice has it."""

    project_name: str
    first: date
    last: date
    hours: float
    rate_minor: int | None  # None: no rate set, as on /api/billing/month
    amount_minor: int | None


class HoursLine(_Shape):
    """One project's hours in a month: its priced lines merged."""

    project_name: str
    hours: float


class ReportDay(_Shape):
    day: date
    project_name: str
    hours: float


class NotedReportDay(_Shape):
    day: date
    project_name: str
    hours: float
    notes: list[str]  # its entries' notes, in start order


class PricedMonth(_Shape):
    month: str  # "YYYY-MM"
    first: date  # the month's days in the link
    last: date
    whole_month: bool  # the 1st through the month's last day
    billable_hours: float
    amount_minor: int
    unpriced_hours: float
    lines: list[PricedLine]
    days: list[ReportDay] | list[NotedReportDay]


class HoursMonth(_Shape):
    month: str
    first: date
    last: date
    whole_month: bool
    billable_hours: float
    lines: list[HoursLine]
    days: list[ReportDay] | list[NotedReportDay]


class PricedReport(_Shape):
    client_name: str
    first: date
    last: date
    shows: ReportShows
    billable_hours: float
    money: ReportMoney
    months: list[PricedMonth]


class HoursReport(_Shape):
    client_name: str
    first: date
    last: date
    shows: ReportShows
    billable_hours: float
    months: list[HoursMonth]


PublicReport = PricedReport | HoursReport


class ReportMonth(NamedTuple):
    """One calendar month's days in a link, and the client's figures for
    them."""

    first: date
    last: date
    whole_month: bool  # `first` is a 1st and `last` that month's last day
    billing: ClientBilling


def report_months(
    client: Client,
    billings: Iterable[ProjectBilling],
    projects: Mapping[str, Project],
    beats: Iterable[Beat],
    overrides: Mapping[str, bool],
    first: date,
    last: date,
    tz: ZoneInfo,
) -> list[ReportMonth]:
    """The client's figures for the days `first` through `last` in `tz`, one
    `assemble_client` per calendar month, as `scope_spend` sums a budget. A
    partial month at either end is rounded on its own days: no invoice in
    the app has it, and `whole_month` says so."""
    billings = list(billings)
    # Each month is given only its own beats; `assemble_client` checks the
    # local day again, so the bucketing rule stays in one place.
    beats_of: dict[date, list[Beat]] = defaultdict(list)
    for beat in beats:
        beats_of[local_date(beat.start, tz).replace(day=1)].append(beat)
    return [
        ReportMonth(
            first=slice_first,
            last=slice_last,
            whole_month=slice_first.day == 1 and slice_last == month_end(slice_first),
            billing=assemble_client(
                client,
                billings,
                projects,
                beats_of.get(slice_first.replace(day=1), []),
                overrides,
                slice_first,
                slice_last,
                tz,
            ),
        )
        for slice_first, slice_last in month_slices(first, last)
    ]


def merge_hours(lines: Sequence[BillingLine]) -> list[tuple[str, Decimal]]:
    """An hours-only month's rows: one per project, the sum of its rounded
    line hours, by name. So its hours are the invoice's to the hundredth,
    and nothing tells when a rate changed, when one was first set, or that
    a project's own rate equals the client's: each of those splits a line."""
    names: dict[str, str] = {}
    hours: dict[str, Decimal] = defaultdict(lambda: _ZERO_HOURS)
    for line in lines:
        names[line.project_id] = line.project_name
        hours[line.project_id] += line.hours
    return [
        (names[project_id], hours[project_id])
        for project_id in sorted(
            names, key=lambda project_id: (names[project_id].casefold(), project_id)
        )
    ]


class DayRow(NamedTuple):
    day: date
    project_id: str
    hours: Decimal  # for display: the lines are the figures
    notes: tuple[str, ...]  # empty without notes


def day_rows(entries: Sequence[BillingEntry], notes: Mapping[str, str] | None) -> list[DayRow]:
    """Per local day and project, its billable entries summed exactly and
    rounded once: no clock times and no count of sessions. With `notes` (by
    beat id), each row carries its entries' stripped, non-empty notes in
    start order. By day, then project id."""
    worked: dict[tuple[date, str], int] = defaultdict(int)
    noted: dict[tuple[date, str], list[BillingEntry]] = defaultdict(list)
    for entry in entries:
        if not entry.billable:
            continue
        key = (entry.day, entry.project_id)
        worked[key] += microseconds_of(entry.start, entry.end)
        noted[key].append(entry)
    rows: list[DayRow] = []
    for day, project_id in sorted(worked):
        texts: tuple[str, ...] = ()
        if notes is not None:
            ordered = sorted(noted[day, project_id], key=lambda entry: entry.start)
            stripped = (
                notes.get(entry.beat_id, "").strip()
                for entry in ordered
                if entry.beat_id is not None
            )
            texts = tuple(text for text in stripped if text)
        rows.append(DayRow(day, project_id, hours_of(worked[day, project_id]), texts))
    return rows


def _days(
    rows: list[DayRow], names: Mapping[str, str], noted: bool
) -> list[ReportDay] | list[NotedReportDay]:
    rows = sorted(rows, key=lambda row: (row.day, names[row.project_id].casefold(), row.project_id))
    if noted:
        return [
            NotedReportDay(
                day=row.day,
                project_name=names[row.project_id],
                hours=float(row.hours),
                notes=list(row.notes),
            )
            for row in rows
        ]
    return [
        ReportDay(day=row.day, project_name=names[row.project_id], hours=float(row.hours))
        for row in rows
    ]


def _month(first: date) -> str:
    return f"{first.year:04d}-{first.month:02d}"


def public_report(
    link: ReportScope,
    client: Client,
    project_names: Mapping[str, str],
    months: Sequence[ReportMonth],
    notes: Mapping[str, str] | None,
) -> PricedReport | HoursReport:
    """What the link shows, built field by field from `months`, the class of
    each part picked by the link's `show_amounts` and `show_notes`. Never a
    `model_dump()` of a domain object. Every total is a sum of the months',
    which are sums of their lines."""
    shows = ReportShows(amounts=link.show_amounts, notes=link.show_notes)
    day_notes = (notes or {}) if link.show_notes else None
    billable_hours = sum((month.billing.billable_hours for month in months), _ZERO_HOURS)
    if not link.show_amounts:
        return HoursReport(
            client_name=client.name,
            first=link.first,
            last=link.last,
            shows=shows,
            billable_hours=float(billable_hours),
            months=[
                HoursMonth(
                    month=_month(month.first),
                    first=month.first,
                    last=month.last,
                    whole_month=month.whole_month,
                    billable_hours=float(month.billing.billable_hours),
                    lines=[
                        HoursLine(project_name=name, hours=float(hours))
                        for name, hours in merge_hours(month.billing.lines)
                    ],
                    days=_days(
                        day_rows(month.billing.entries, day_notes), project_names, link.show_notes
                    ),
                )
                for month in months
            ],
        )
    return PricedReport(
        client_name=client.name,
        first=link.first,
        last=link.last,
        shows=shows,
        billable_hours=float(billable_hours),
        money=ReportMoney(
            currency=client.currency,
            minor_units=minor_units(client.currency),
            amount_minor=sum(month.billing.amount_minor for month in months),
            unpriced_hours=float(
                sum((month.billing.unpriced_hours for month in months), _ZERO_HOURS)
            ),
        ),
        months=[
            PricedMonth(
                month=_month(month.first),
                first=month.first,
                last=month.last,
                whole_month=month.whole_month,
                billable_hours=float(month.billing.billable_hours),
                amount_minor=month.billing.amount_minor,
                unpriced_hours=float(month.billing.unpriced_hours),
                lines=[
                    PricedLine(
                        project_name=line.project_name,
                        first=line.first,
                        last=line.last,
                        hours=float(line.hours),
                        rate_minor=line.rate_minor,
                        amount_minor=line.amount_minor,
                    )
                    for line in month.billing.lines
                ],
                days=_days(
                    day_rows(month.billing.entries, day_notes), project_names, link.show_notes
                ),
            )
            for month in months
        ],
    )
