"""Projects API router - thin controller for project operations."""

import csv
import http
import io
import re
from datetime import date, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response
from pydantic import BeforeValidator, WithJsonSchema

from beats.api.dependencies import (
    BeatRepoDep,
    ContractServiceDep,
    GitHubServiceDep,
    MondayDate,
    ProjectServiceDep,
    TimerServiceDep,
    TimezoneDep,
    WebhookRepoDep,
)
from beats.api.routers.webhooks import dispatch_webhook_event
from beats.api.schemas import (
    CreateProjectRequest,
    DurationResponse,
    GoalOverrideRequest,
    MonthlyTotalsResponse,
    ProjectResponse,
    ProjectsListItemResponse,
    RecordTimeRequest,
    UpdateProjectRequest,
)
from beats.domain.holidays import Holiday
from beats.domain.models import (
    Contract,
    ContractWeek,
    GoalOverride,
    Ledger,
    Project,
    ProjectKind,
    VacationYear,
)
from beats.domain.services import keep_unsent_contract_fields
from beats.domain.timesheet import Timesheet

router = APIRouter(
    prefix="/api/projects",
    tags=["Projects"],
    responses={404: {"description": "Not found"}},
)


@router.get("/", response_model=list[ProjectsListItemResponse])
async def list_projects(
    service: ProjectServiceDep,
    contract_service: ContractServiceDep,
    # The grouped read below is wider than what ProjectService itself needs, so
    # it comes from the repository directly rather than reaching through the
    # service for a method the service does not use.
    beat_repo: BeatRepoDep,
    tz: TimezoneDep,
    archived: bool = False,
    include: str | None = Query(
        default=None,
        description=(
            "Comma-separated aggregations to populate per project. Supported: "
            "'totals' (total_minutes, a running timer counted up to now), "
            "'this_week' (weekly_minutes + effective_goal "
            "trio, and on a day job the contract's expected / worked / remaining / "
            "balance), "
            "'last_tracked' (last_tracked_at). Omitted ⇒ slim response."
        ),
    ),
):
    """List projects, optionally augmented with aggregation fields.

    Without `include` the response is slim: the fields of ProjectResponse
    plus null aggregation slots, and no beats are read. The daemon and the
    companion list projects this way.

    P3.0 of the project-management revamp. First cut loops per-project
    server-side; if profiling shows it's needed, a follow-up (P3.0b)
    moves to a Mongo $facet pipeline for true batched aggregation.
    """
    projects = await service.list_projects(archived=archived)
    include_set = {token.strip() for token in (include or "").split(",") if token.strip()}
    want_totals = "totals" in include_set
    want_week = "this_week" in include_set
    want_last = "last_tracked" in include_set

    # FF.15: One Mongo find for ALL displayed projects' beats; per-project
    # aggregation is pure Python over the in-memory bucket. The previous
    # FF.9 shape parallelized the 3 aggregations per project but each was
    # still its own list_by_project query — N projects × 3 = 3N round
    # trips. The route now issues 1 round-trip total when aggregations
    # are requested.
    #
    # When archived=False (the only case the /projects index page hits),
    # the pid list excludes archived projects so we never load their
    # beats. When archived=True the caller explicitly opted in.
    #
    # Skipping the slim path entirely when nothing's requested keeps a
    # users-with-zero-beats cold load from issuing a no-op find.
    if not (want_totals or want_week or want_last):
        return [p.model_dump(mode="json") for p in projects]

    project_ids = [p.id for p in projects if p.id]
    beats_by_pid = await beat_repo.list_grouped_by_project_ids(project_ids)

    # The contract weeks reuse the beats already loaded above; what they add
    # is one absence read and one holiday calendar per day job with a
    # contract — a few projects at most — and nothing for the others.
    contract_weeks = (
        await contract_service.weeks_for(projects, beats_by_pid, tz) if want_week else {}
    )

    def aggregate_one(p: Project) -> dict:
        item = p.model_dump(mode="json")
        if not p.id:
            return item
        beats = beats_by_pid.get(p.id, [])
        if want_totals:
            totals = service._monthly_totals_from_beats(beats, tz)
            item["total_minutes"] = totals.get("total_minutes", 0)
        if want_week:
            item.update(service._this_week_from_beats(beats, p))
            contract_week = contract_weeks.get(p.id)
            if contract_week is not None:
                item["contract_expected"] = contract_week.expected
                item["contract_worked"] = contract_week.worked
                item["contract_remaining"] = contract_week.remaining
                item["balance"] = contract_week.balance
        if want_last:
            last = service._last_tracked_from_beats(beats)
            item["last_tracked_at"] = last.isoformat() if last else None
        return item

    # Pure-Python aggregation now — no need for asyncio.gather. Order is
    # preserved by the list comprehension matching `projects`.
    return [aggregate_one(p) for p in projects]


@router.post("/", status_code=http.HTTPStatus.CREATED, response_model=ProjectResponse)
async def create_project(request: CreateProjectRequest, service: ProjectServiceDep):
    """Create a new project."""
    project = Project(
        name=request.name,
        description=request.description,
        color=request.color,
        weekly_goal=request.weekly_goal,
        goal_type=request.goal_type,
        github_repo=request.github_repo,
        category=request.category,
        autostart_repos=request.autostart_repos,
        kind=request.kind,
        contract=request.contract,
    )
    created = await service.create_project(project)
    return created.model_dump()


@router.put("/", response_model=ProjectResponse)
async def update_project(request: UpdateProjectRequest, service: ProjectServiceDep):
    """Update an existing project. A field the request leaves out keeps its
    stored value; one it sends replaces it, `null` clearing a nullable one."""
    # Omitted is not cleared: a client sends the fields it edits, and the
    # rest must survive. The project page's colour picker sends id, name,
    # colour and a few fields it happens to know; while absence read as a
    # reset, every colour change wiped the GitHub repo, the category and the
    # autostart repos (AHM-89). So every field is taken from the request only
    # when it was sent (model_fields_set), and goal_overrides, which no
    # request carries, always from the stored project.
    # `kind` has no empty state, so null reads as left out. `contract: null`
    # clears; left out, the contract is kept — unless the edit moves the
    # project away from day_job, in which case it goes with the kind: a
    # contract lives only on a day job, and the service refuses one sent with
    # any other kind (409 NOT_A_DAY_JOB). Inside a sent contract the same
    # rule holds for the holiday lists and the vacation entitlement: one left
    # out is kept, so an older client's term edit does not delete them.
    existing = await service.project_repo.get_by_id(request.id)
    sent = request.model_fields_set

    def sent_or_stored(field: str) -> Any:
        return getattr(request if field in sent else existing, field)

    kind = request.kind if request.kind is not None else existing.kind
    if "contract" in sent:
        contract = request.contract
        if contract is not None:
            contract = keep_unsent_contract_fields(contract, existing.contract)
    else:
        contract = existing.contract if kind is ProjectKind.DAY_JOB else None
    project = Project(
        id=request.id,
        name=request.name,
        description=sent_or_stored("description"),
        color=sent_or_stored("color"),
        archived=sent_or_stored("archived"),
        weekly_goal=sent_or_stored("weekly_goal"),
        goal_type=sent_or_stored("goal_type"),
        goal_overrides=existing.goal_overrides,
        kind=kind,
        contract=contract,
        github_repo=sent_or_stored("github_repo"),
        category=sent_or_stored("category"),
        autostart_repos=sent_or_stored("autostart_repos"),
    )
    updated = await service.update_project(project, previous_contract=existing.contract)
    return updated.model_dump()


@router.put("/{project_id}/goal-overrides")
async def update_goal_overrides(
    project_id: str,
    overrides: list[GoalOverrideRequest],
    service: ProjectServiceDep,
):
    """Replace goal overrides for a project."""
    project = await service.project_repo.get_by_id(project_id)
    project.goal_overrides = [
        GoalOverride(
            week_of=o.week_of,
            effective_from=o.effective_from,
            weekly_goal=o.weekly_goal,
            goal_type=o.goal_type,
        )
        for o in overrides
    ]
    # The contract is the one just read and goes back unchanged, so nothing
    # about its balance adjustments is reconciled.
    updated = await service.update_project(project, previous_contract=project.contract)
    return updated.model_dump()


@router.put("/{project_id}/contract", response_model=ProjectResponse)
async def replace_contract(project_id: str, contract: Contract, service: ProjectServiceDep):
    """Replace a day job's whole contract: terms, holiday region, company
    holidays and the region holidays not given, opening balance, end date
    and vacation entitlement, in one shape, like goal-overrides. A holiday
    list or a `vacation` the body leaves out is kept; `[]` or `null` clears
    it. Leaves `kind` alone; on a project that is not a day job it is a 409
    (NOT_A_DAY_JOB), and a region the calendar does not know is a 400
    (UNKNOWN_HOLIDAY_REGION). Moving the first term later past a balance
    adjustment is a 409 (ADJUSTMENT_BEFORE_START), and leaving the vacation
    count's opening outside the contract's dates a 409
    (VACATION_OPENING_OUTSIDE_CONTRACT)."""
    updated = await service.replace_contract(project_id, contract)
    return updated.model_dump()


# Validated as a query parameter so a Tuesday is a 422 naming `week_of` in
# `fields`, the same envelope a bad body gets.
WeekOfQuery = Annotated[
    MondayDate,
    Query(description="Monday of the week wanted. Defaults to the current week in `tz`."),
]


@router.get("/{project_id}/contract/week", response_model=ContractWeek)
async def get_contract_week(
    project_id: str,
    service: ContractServiceDep,
    tz: TimezoneDep,
    week_of: WeekOfQuery = None,
):
    """One week of a day job against its contract — expected, worked,
    remaining, the running balance as of today, and the seven days with
    their holiday and absence. Worked hours are bucketed by the local day
    each beat started on, in `tz`; a running timer counts up to now.
    409 on a project that is not a day job (NOT_A_DAY_JOB) or has no
    contract yet (NO_CONTRACT)."""
    return await service.week(project_id, week_of, tz)


@router.get("/{project_id}/ledger", response_model=Ledger)
async def get_ledger(
    project_id: str,
    service: ContractServiceDep,
    tz: TimezoneDep,
    weeks: int = Query(
        default=8, ge=1, le=104, description="How many weeks back, ending with the current one."
    ),
):
    """The last `weeks` weeks of any project, newest first, ending with the
    current week in `tz` — worked hours by day, the goal in force, and on a
    day job the contract's adjusted expectation, the balance at each week's
    close and its absences and holidays — plus the balance as of today with
    the terms that make it. Worked hours are bucketed by the local day each
    beat started on, in `tz`, and a running timer counts up to now, exactly
    as `/contract/week`. A project the contract does not govern carries its
    goal and its hours and nulls for the rest."""
    return await service.ledger(project_id, weeks, tz)


_MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


def _first_of_month(value: object) -> date:
    """'YYYY-MM' to the 1st of that month. Anything else — '2026-9', a full
    date, '0000-01', which `date` refuses — is a ValueError, which a query
    parameter turns into a 422 naming `month`."""
    if not isinstance(value, str) or _MONTH.fullmatch(value) is None:
        msg = "month must be YYYY-MM"
        raise ValueError(msg)
    return date(int(value[:4]), int(value[5:]), 1)


# The schema is the string a client sends, not the `date` it becomes. Left to
# pydantic it would come from `date` and say `format: date`: a full date, which
# `_first_of_month` refuses with a 422.
MonthQuery = Annotated[
    date,
    BeforeValidator(_first_of_month),
    Query(description="The month wanted, as YYYY-MM."),
    WithJsonSchema({"type": "string", "pattern": f"^{_MONTH.pattern}$", "examples": ["2026-09"]}),
]

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_TIMESHEET_COLUMNS = [
    "date",
    "weekday",
    "expected",
    "worked",
    "difference",
    "holiday",
    "absence",
    "half_day",
    "adjustment",
    "adjusted",
    "balance",
]


def _hours(value: float | None) -> str:
    """Two fixed decimals, a blank for None. Adding 0.0 turns a rounded −0.0
    into 0.00: a day worked exactly to contract would print −0.00."""
    return "" if value is None else f"{value + 0.0:.2f}"


def _timesheet_csv(sheet: Timesheet) -> str:
    """The sheet as RFC 4180 CSV: comma-separated, dot decimals, CRLF line
    ends, a header and no other metadata. A "brought forward" row first and a
    "total" row last, its holiday and absence cells holding the month's
    counts. Nothing in it is text the user typed: a holiday is the library's
    name or "company holiday", an absence its type."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(_TIMESHEET_COLUMNS)
    writer.writerow(["brought forward", *[""] * 9, _hours(sheet.brought_forward)])
    for day in sheet.days:
        writer.writerow(
            [
                day.date.isoformat(),
                _WEEKDAYS[day.date.weekday()],
                _hours(day.expected),
                _hours(day.worked),
                _hours(day.difference),
                day.holiday or "",
                day.absence.value if day.absence is not None else "",
                ("yes" if day.half_day else "no") if day.absence is not None else "",
                day.adjustment.value if day.adjustment is not None else "",
                _hours(day.adjusted),
                _hours(day.balance_end),
            ]
        )
    writer.writerow(
        [
            "total",
            "",
            _hours(sheet.expected),
            _hours(sheet.worked),
            _hours(sheet.difference),
            str(sheet.holidays),
            f"{sheet.absence_days:g}",
            "",
            "",
            _hours(sheet.adjusted),
            _hours(sheet.carried_forward),
        ]
    )
    return out.getvalue()


@router.get(
    "/{project_id}/timesheet.csv",
    response_class=Response,
    responses={
        200: {
            "description": "The month as CSV, one row per finished day.",
            "content": {"text/csv": {}},
        }
    },
)
async def get_timesheet_csv(
    project_id: str, month: MonthQuery, service: ContractServiceDep, tz: TimezoneDep
) -> Response:
    """A day job's month as a timesheet, for the employer: one row per
    finished day of the month inside the contract — through yesterday in
    `tz`, from the first term, through `ended_on` — with the hours expected,
    worked and their difference, the weekday holiday's name and absence
    type, the balance adjustment and what it moved, and the balance at the
    day's close; a "brought forward" row first and a "total" row last. A
    figure the contract has no expectation for is blank. Worked hours are
    bucketed by the local day each beat started on, in `tz`, and a running
    timer counts up to now, as on `/ledger`. The file is sent as an
    attachment without a filename; the caller names it.
    409 on a project that is not a day job (NOT_A_DAY_JOB), without a
    contract (NO_CONTRACT), or for a month with no finished day inside the
    contract (OUTSIDE_CONTRACT)."""
    sheet = await service.timesheet(project_id, month, tz)
    return Response(
        content=_timesheet_csv(sheet),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment"},
    )


@router.get("/{project_id}/holidays", response_model=list[Holiday])
async def get_holidays(
    project_id: str,
    service: ContractServiceDep,
    tz: TimezoneDep,
    year: int | None = Query(
        default=None, ge=1, le=9999, description="Defaults to the current year in `tz`."
    ),
    include: Literal["not_given"] | None = Query(
        default=None,
        description=(
            "'not_given' also lists the region holidays the employer does not give, "
            "with `given: false`."
        ),
    ),
):
    """The contract's holidays for a year, by date, for the calendar and the
    absence booking: the region's public holidays the employer gives
    (`source: region`) and the employer's own (`source: company`), all with
    `given: true`. With `include=not_given`, the region holidays on the
    contract's `holidays_not_given` too, with `given: false` — a date a
    company day covers is then listed twice, the region's row first. Empty
    when the day job has no contract; only the company days when it names no
    region.
    409 on a project that is not a day job."""
    return await service.holidays(project_id, year, tz, include_not_given=include == "not_given")


@router.get("/{project_id}/vacation", response_model=VacationYear)
async def get_vacation(
    project_id: str,
    service: ContractServiceDep,
    tz: TimezoneDep,
    year: int | None = Query(
        default=None, ge=1, le=9999, description="Defaults to the current year in `tz`."
    ),
):
    """One calendar year of a day job's vacation entitlement, in days: what
    the year gives (`accrued`, pro-rated in the year the contract ends; null
    in the opening year, whose figure is the opening's), what the year
    before carried in, what is available, what is booked (the `vacation`
    days, past and planned, on weekdays inside the contract's dates that are
    not its holidays) and what remains. Every figure is a whole or half day.
    409 on a project that is not a day job (NOT_A_DAY_JOB), without a
    contract (NO_CONTRACT) or an entitlement (NO_VACATION_ENTITLEMENT), and
    for a year before the opening's or after the contract's end
    (VACATION_YEAR_OUT_OF_RANGE)."""
    return await service.vacation(project_id, year, tz)


@router.get("/{project_id}/git-activity")
async def get_git_activity(
    project_id: str,
    service: ProjectServiceDep,
    github_service: GitHubServiceDep,
    start: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end: date = Query(default_factory=date.today),
):
    """Get GitHub commit counts correlated with a project's tracked time."""
    project = await service.project_repo.get_by_id(project_id)
    if not project.github_repo:
        return []
    return await github_service.fetch_commit_counts(project.github_repo, start, end)


@router.get("/{project_id}/daily-average")
async def get_daily_average(project_id: str, service: ProjectServiceDep):
    """Get the average daily session time for a project over the last 30 days."""
    return await service.get_daily_average(project_id)


@router.post("/{project_id}/archive")
async def archive_project(project_id: str, service: ProjectServiceDep):
    """Archive a project."""
    await service.archive_project(project_id)
    return {"status": "success"}


@router.post("/{project_id}/unarchive")
async def unarchive_project(project_id: str, service: ProjectServiceDep):
    """Restore an archived project (symmetric to /archive)."""
    await service.unarchive_project(project_id)
    return {"status": "success"}


@router.get("/{project_id}/today/")
async def today_time_for_project(project_id: str, service: ProjectServiceDep) -> DurationResponse:
    """Get total time spent on project today."""
    duration = await service.get_today_time(project_id)
    return DurationResponse(duration=str(duration))


@router.get("/{project_id}/total/")
async def total_work_time_per_month_on_project(
    project_id: str, service: ProjectServiceDep, tz: TimezoneDep
) -> MonthlyTotalsResponse:
    """A project's hours per month, keyed 'YYYY-MM', and the minutes of them
    all. Hours are bucketed by the local month of the day each beat started
    on, in `tz`, and a running timer counts up to now, as on `/ledger`."""
    result = await service.get_monthly_totals(project_id, tz)
    return MonthlyTotalsResponse(**result)


@router.get("/{project_id}/summary/")
async def get_project_summary(project_id: str, service: ProjectServiceDep):
    """Get daily summary for a project."""
    return await service.get_daily_summary(project_id)


@router.post("/{project_id}/start")
async def start_project_timer(
    project_id: str,
    time_validator: RecordTimeRequest,
    service: TimerServiceDep,
    webhook_repo: WebhookRepoDep,
):
    """Start a timer for a project."""
    beat = await service.start_timer(project_id, time_validator.time)
    project = await service.project_repo.get_by_id(project_id)
    await dispatch_webhook_event(
        "timer.start",
        {"project_id": project_id, "project_name": project.name, "beat_id": beat.id},
        webhook_repo,
    )
    return beat.model_dump()


@router.post("/stop")
async def end_project_timer(
    time_validator: RecordTimeRequest,
    service: TimerServiceDep,
    webhook_repo: WebhookRepoDep,
):
    """Stop the currently running timer."""
    beat = await service.stop_timer(time_validator.time)
    await dispatch_webhook_event(
        "timer.stop",
        {
            "project_id": beat.project_id,
            "beat_id": beat.id,
            "duration_minutes": int(beat.duration.total_seconds() / 60),
        },
        webhook_repo,
    )
    return beat.model_dump()
