"""FastAPI dependency injection configuration."""

from collections.abc import Callable
from datetime import date, timedelta
from functools import lru_cache
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, HTTPException, Query, Request, status
from pydantic import AfterValidator

from beats.domain.analytics import AnalyticsService
from beats.domain.billing_service import BillingService
from beats.domain.calendar import CalendarService
from beats.domain.fitbit import FitbitService
from beats.domain.github import GitHubService
from beats.domain.intelligence import IntelligenceService
from beats.domain.organisations import OrganisationService
from beats.domain.oura import OuraService
from beats.domain.services import BeatService, ContractService, ProjectService, TimerService
from beats.infrastructure.database import Database
from beats.infrastructure.organisations import MongoOrganisationRecords, MongoOrganisationStore
from beats.infrastructure.repositories import (
    AbsenceRepository,
    AdjustmentRepository,
    BeatRepository,
    BillableOverrideRepository,
    BillingBudgetRepository,
    BiometricDayRepository,
    CalendarIntegrationRepository,
    ClientRepository,
    DeviceRegistrationRepository,
    FitbitIntegrationRepository,
    FlowWindowRepository,
    GitHubIntegrationRepository,
    InsightsRepository,
    MongoAbsenceRepository,
    MongoAdjustmentRepository,
    MongoBeatRepository,
    MongoBillableOverrideRepository,
    MongoBillingBudgetRepository,
    MongoBiometricDayRepository,
    MongoCalendarIntegrationRepository,
    MongoClientRepository,
    MongoDeviceRegistrationRepository,
    MongoFitbitIntegrationRepository,
    MongoFlowWindowRepository,
    MongoGitHubIntegrationRepository,
    MongoInsightsRepository,
    MongoOuraIntegrationRepository,
    MongoPairingCodeRepository,
    MongoPendingSuggestionRepository,
    MongoProjectBillingRepository,
    MongoProjectRepository,
    MongoReportLinkLookup,
    MongoReportLinkRepository,
    MongoSignalSummaryRepository,
    MongoUserRepository,
    MongoWebhookRepository,
    MongoWeeklyDigestRepository,
    MongoWeeklyPlanRepository,
    OuraIntegrationRepository,
    PairingCodeRepository,
    PendingSuggestionRepository,
    ProjectBillingRepository,
    ProjectRepository,
    ReportLinkLookup,
    ReportLinkRepository,
    SignalSummaryRepository,
    WebhookRepository,
    WeeklyDigestRepository,
    WeeklyPlanRepository,
)
from beats.infrastructure.repositories import project_repository_for as _project_repository_for
from beats.settings import Settings


@lru_cache
def get_settings() -> Settings:
    """Get application settings (cached)."""
    return Settings()


async def get_current_user_id(request: Request) -> str:
    """Extract the current user's ID from request state (set by middleware)."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user_id


CurrentUserId = Annotated[str, Depends(get_current_user_id)]


def _user_scoped[R](repo: Callable[..., R], collection: str) -> Callable[[str], R]:
    """Build a FastAPI dependency yielding `repo` bound to the caller's data.

    The `Annotated[...]` aliases at the bottom of this module are what routes
    actually depend on, and they still name the interface; these constructors
    only ever differed by class and collection name.
    """

    def dependency(user_id: CurrentUserId) -> R:
        return repo(getattr(Database.get_db(), collection), user_id=user_id)

    return dependency


def _unscoped[R](repo: Callable[..., R], collection: str) -> Callable[[], R]:
    """Same, for the two collections that are looked up across all users:
    pairing codes (redeemed by an unauthenticated device) and device
    registrations (resolved from a device token before its owner is known).
    """

    def dependency() -> R:
        return repo(getattr(Database.get_db(), collection))

    return dependency


def get_timezone(
    tz: Annotated[
        str | None,
        Query(description="IANA timezone name (e.g. America/New_York). Defaults to UTC."),
    ] = None,
) -> ZoneInfo:
    """Resolve the request's ``tz`` query param to a ``ZoneInfo``.

    Day/hour bucketing in analytics and intelligence is computed in the
    caller's local timezone. Absent or empty ``tz`` defaults to UTC, keeping
    behavior unchanged for clients that don't send one. An unrecognized IANA
    name returns HTTP 400 via the unified error envelope.
    """
    if not tz:
        return ZoneInfo("UTC")
    return _zone(tz)


def get_required_timezone(
    tz: Annotated[
        str,
        Query(
            min_length=1,
            description=(
                "IANA timezone name (e.g. America/New_York). Required: which day is "
                "today decides what the request may do."
            ),
        ),
    ],
) -> ZoneInfo:
    """``get_timezone`` without the UTC default, for a write whose rules
    depend on the caller's today: a missing ``tz`` is a 422 naming it,
    rather than a quiet answer for a day the caller is not in."""
    return _zone(tz)


def _zone(tz: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz)
    except ZoneInfoNotFoundError, ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_TIMEZONE", "message": f"Unknown timezone: {tz}"},
        ) from None


TimezoneDep = Annotated[ZoneInfo, Depends(get_timezone)]
RequiredTimezoneDep = Annotated[ZoneInfo, Depends(get_required_timezone)]


def monday_or_none(day: date | None) -> date | None:
    """Pass a Monday (or nothing) through; anything else is a ValueError, which
    a query parameter turns into a 422 naming the parameter in `fields`."""
    if day is None:
        return None
    if day.weekday() != 0:
        msg = "week_of must be a Monday"
        raise ValueError(msg)
    if day > date.max - timedelta(days=6):
        # Its seven days cannot even be enumerated; keep the answer a 422.
        msg = "week_of is past the end of the calendar"
        raise ValueError(msg)
    return day


# The type of an optional `week_of`. Each route wraps it in its own `Query`,
# since what an absent week means differs from route to route.
MondayDate = Annotated[date | None, AfterValidator(monday_or_none)]


get_beat_repository = _user_scoped(MongoBeatRepository, "timeLogs")


def get_project_repository(user_id: CurrentUserId) -> ProjectRepository:
    """The caller's projects: their own, and the organisation projects they
    are assigned to, merged with their assignment (docs/organisations.md).
    The one repository given more than its collection, because it is the one
    whose scope is wider than `user_id`."""
    return project_repository_for(user_id)


def project_repository_for(user_id: str) -> MongoProjectRepository:
    return _project_repository_for(Database.get_db(), user_id)


get_flow_window_repository = _user_scoped(MongoFlowWindowRepository, "flow_windows")


get_client_repository = _user_scoped(MongoClientRepository, "clients")


get_project_billing_repository = _user_scoped(MongoProjectBillingRepository, "project_billing")


get_billable_override_repository = _user_scoped(
    MongoBillableOverrideRepository, "billable_overrides"
)


get_billing_budget_repository = _user_scoped(MongoBillingBudgetRepository, "billing_budgets")


get_report_link_repository = _user_scoped(MongoReportLinkRepository, "report_links")


# Resolving a report link's token is the one read that crosses users: the
# public report endpoint has no session, so the owner is not known until the
# token resolves (`_unscoped`, as pairing codes and SSO flows are).
get_report_link_lookup = _unscoped(MongoReportLinkLookup, "report_links")


def get_timer_service(
    beat_repo: Annotated[BeatRepository, Depends(get_beat_repository)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    flow_repo: Annotated[FlowWindowRepository, Depends(get_flow_window_repository)],
) -> TimerService:
    """Get the timer service with injected repositories."""
    return TimerService(beat_repo=beat_repo, project_repo=project_repo, flow_repo=flow_repo)


def get_beat_service(
    beat_repo: Annotated[BeatRepository, Depends(get_beat_repository)],
    override_repo: Annotated[BillableOverrideRepository, Depends(get_billable_override_repository)],
    flow_repo: Annotated[FlowWindowRepository, Depends(get_flow_window_repository)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> BeatService:
    """Get the beat service with injected repositories. The billable
    overrides are there for the delete: a beat's override goes with it. The
    projects are there for the organisation stamp: a beat written against an
    organisation's project is that organisation's record."""
    return BeatService(
        beat_repo=beat_repo, overrides=override_repo, flow_repo=flow_repo, projects=project_repo
    )


get_absence_repository = _user_scoped(MongoAbsenceRepository, "absences")


get_adjustment_repository = _user_scoped(MongoAdjustmentRepository, "balance_adjustments")


def get_contract_service(
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    beat_repo: Annotated[BeatRepository, Depends(get_beat_repository)],
    absence_repo: Annotated[AbsenceRepository, Depends(get_absence_repository)],
    adjustment_repo: Annotated[AdjustmentRepository, Depends(get_adjustment_repository)],
) -> ContractService:
    """Get the contract service with injected repositories."""
    return ContractService(
        project_repo=project_repo,
        beat_repo=beat_repo,
        absence_repo=absence_repo,
        adjustment_repo=adjustment_repo,
    )


def get_project_service(
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    beat_repo: Annotated[BeatRepository, Depends(get_beat_repository)],
    adjustment_repo: Annotated[AdjustmentRepository, Depends(get_adjustment_repository)],
    billing_repo: Annotated[ProjectBillingRepository, Depends(get_project_billing_repository)],
) -> ProjectService:
    """Get the project service with injected repositories. The adjustments
    are there for the contract writes: the balance adjustments go with the
    contract, and a first day moved later past one is refused. The billing is
    there for the kind: a billed project stays freelance."""
    return ProjectService(
        project_repo=project_repo,
        beat_repo=beat_repo,
        adjustments=adjustment_repo,
        billing=billing_repo,
    )


def get_billing_service(
    client_repo: Annotated[ClientRepository, Depends(get_client_repository)],
    billing_repo: Annotated[ProjectBillingRepository, Depends(get_project_billing_repository)],
    override_repo: Annotated[BillableOverrideRepository, Depends(get_billable_override_repository)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    beat_repo: Annotated[BeatRepository, Depends(get_beat_repository)],
    billing_budget_repo: Annotated[BillingBudgetRepository, Depends(get_billing_budget_repository)],
    report_link_repo: Annotated[ReportLinkRepository, Depends(get_report_link_repository)],
) -> BillingService:
    """Get the billing service with injected repositories. It is the only
    service given the billing budgets and the report links: no device route
    and no coach port reaches them."""
    return BillingService(
        clients=client_repo,
        billings=billing_repo,
        overrides=override_repo,
        projects=project_repo,
        beats=beat_repo,
        budgets=billing_budget_repo,
        links=report_link_repo,
    )


def billing_service_for(user_id: str) -> BillingService:
    """A `BillingService` for an account named by something other than a
    session token.

    The one caller is the public report route. A report link carries the
    account whose hours it serves, so that account's repositories are built
    here rather than by `Depends`, which has no user to resolve. Every one of
    them is the same user-scoped repository a signed-in route is given, bound
    to the owner the token resolved to — so the public read is as scoped as
    any other, and the only question is whether the token was right.
    """
    db = Database.get_db()
    return BillingService(
        clients=MongoClientRepository(db.clients, user_id=user_id),
        billings=MongoProjectBillingRepository(db.project_billing, user_id=user_id),
        overrides=MongoBillableOverrideRepository(db.billable_overrides, user_id=user_id),
        projects=project_repository_for(user_id),
        beats=MongoBeatRepository(db.timeLogs, user_id=user_id),
        budgets=MongoBillingBudgetRepository(db.billing_budgets, user_id=user_id),
        links=MongoReportLinkRepository(db.report_links, user_id=user_id),
    )


def get_organisation_service(
    billing_repo: Annotated[ProjectBillingRepository, Depends(get_project_billing_repository)],
) -> OrganisationService:
    """The organisation service. Its store and its records reader are the
    two classes in the system not scoped by `user_id`
    (`infrastructure/organisations.py`); every read they make names an
    organisation the caller's membership was resolved against first. The
    caller's own billing is there for connecting a project: one billed to a
    client stays personal."""
    db = Database.get_db()
    return OrganisationService(
        store=MongoOrganisationStore(db),
        records=MongoOrganisationRecords(db),
        users=MongoUserRepository(db.users),
        billing=billing_repo,
    )


OrganisationServiceDep = Annotated[OrganisationService, Depends(get_organisation_service)]


def get_analytics_service(
    beat_repo: Annotated[BeatRepository, Depends(get_beat_repository)],
) -> AnalyticsService:
    """Get the analytics service with injected repository."""
    return AnalyticsService(beat_repo=beat_repo)


get_webhook_repository = _user_scoped(MongoWebhookRepository, "webhooks")


get_weekly_digest_repository = _user_scoped(MongoWeeklyDigestRepository, "weekly_digests")


get_insights_repository = _user_scoped(MongoInsightsRepository, "insights")


def get_intelligence_service(
    beat_repo: Annotated[BeatRepository, Depends(get_beat_repository)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    contract_service: Annotated[ContractService, Depends(get_contract_service)],
) -> IntelligenceService:
    """Get the intelligence service with injected repositories. The contract
    service is what makes the planning line and the pattern cards quote a
    governed day job's adjusted week, not its nominal term."""
    return IntelligenceService(
        beat_repo=beat_repo,
        project_repo=project_repo,
        contracts=contract_service,
    )


get_calendar_integration_repository = _user_scoped(
    MongoCalendarIntegrationRepository, "calendar_integrations"
)


def get_calendar_service(
    cal_repo: Annotated[
        CalendarIntegrationRepository, Depends(get_calendar_integration_repository)
    ],
    settings: Annotated[Settings, Depends(get_settings)],
) -> CalendarService:
    """Get the calendar service with injected repository."""
    return CalendarService(settings=settings, repo=cal_repo)


# Type aliases for cleaner dependency injection in routes
BeatRepoDep = Annotated[BeatRepository, Depends(get_beat_repository)]
ProjectRepoDep = Annotated[ProjectRepository, Depends(get_project_repository)]
TimerServiceDep = Annotated[TimerService, Depends(get_timer_service)]
BeatServiceDep = Annotated[BeatService, Depends(get_beat_service)]
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
ContractServiceDep = Annotated[ContractService, Depends(get_contract_service)]
AbsenceRepoDep = Annotated[AbsenceRepository, Depends(get_absence_repository)]
AdjustmentRepoDep = Annotated[AdjustmentRepository, Depends(get_adjustment_repository)]
ClientRepoDep = Annotated[ClientRepository, Depends(get_client_repository)]
ProjectBillingRepoDep = Annotated[ProjectBillingRepository, Depends(get_project_billing_repository)]
BillableOverrideRepoDep = Annotated[
    BillableOverrideRepository, Depends(get_billable_override_repository)
]
# For the backup's export alone; every other reader goes through BillingService.
BillingBudgetRepoDep = Annotated[BillingBudgetRepository, Depends(get_billing_budget_repository)]
BillingServiceDep = Annotated[BillingService, Depends(get_billing_service)]
# For the public report route alone, which resolves a token to its owner
# before it can build anything user-scoped.
ReportLinkLookupDep = Annotated[ReportLinkLookup, Depends(get_report_link_lookup)]
AnalyticsServiceDep = Annotated[AnalyticsService, Depends(get_analytics_service)]
WebhookRepoDep = Annotated[WebhookRepository, Depends(get_webhook_repository)]
WeeklyDigestRepoDep = Annotated[WeeklyDigestRepository, Depends(get_weekly_digest_repository)]
InsightsRepoDep = Annotated[InsightsRepository, Depends(get_insights_repository)]
IntelligenceServiceDep = Annotated[IntelligenceService, Depends(get_intelligence_service)]
CalendarServiceDep = Annotated[CalendarService, Depends(get_calendar_service)]


get_github_integration_repository = _user_scoped(
    MongoGitHubIntegrationRepository, "github_integrations"
)


def get_github_service(
    gh_repo: Annotated[GitHubIntegrationRepository, Depends(get_github_integration_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GitHubService:
    """Get the GitHub service with injected repository."""
    return GitHubService(settings=settings, repo=gh_repo)


GitHubServiceDep = Annotated[GitHubService, Depends(get_github_service)]


get_weekly_plan_repository = _user_scoped(MongoWeeklyPlanRepository, "weekly_plans")


WeeklyPlanRepoDep = Annotated[WeeklyPlanRepository, Depends(get_weekly_plan_repository)]


get_pairing_code_repository = _unscoped(MongoPairingCodeRepository, "pairing_codes")


get_device_registration_repository = _unscoped(
    MongoDeviceRegistrationRepository, "device_registrations"
)


PairingCodeRepoDep = Annotated[PairingCodeRepository, Depends(get_pairing_code_repository)]
DeviceRegistrationRepoDep = Annotated[
    DeviceRegistrationRepository, Depends(get_device_registration_repository)
]


get_signal_summary_repository = _user_scoped(MongoSignalSummaryRepository, "signal_summaries")


FlowWindowRepoDep = Annotated[FlowWindowRepository, Depends(get_flow_window_repository)]
SignalSummaryRepoDep = Annotated[SignalSummaryRepository, Depends(get_signal_summary_repository)]


def get_pending_suggestion_repository(
    user_id: CurrentUserId,
) -> PendingSuggestionRepository:
    """Get the pending-suggestion repository scoped to the current user."""
    db = Database.get_db()
    return MongoPendingSuggestionRepository(db.pending_suggestions, user_id=user_id)


PendingSuggestionRepoDep = Annotated[
    PendingSuggestionRepository, Depends(get_pending_suggestion_repository)
]


get_biometric_repository = _user_scoped(MongoBiometricDayRepository, "biometric_days")


get_fitbit_integration_repository = _user_scoped(
    MongoFitbitIntegrationRepository, "fitbit_integrations"
)


get_oura_integration_repository = _user_scoped(MongoOuraIntegrationRepository, "oura_integrations")


BiometricRepoDep = Annotated[BiometricDayRepository, Depends(get_biometric_repository)]
FitbitIntegrationRepoDep = Annotated[
    FitbitIntegrationRepository, Depends(get_fitbit_integration_repository)
]
OuraIntegrationRepoDep = Annotated[
    OuraIntegrationRepository, Depends(get_oura_integration_repository)
]


def get_fitbit_service(
    repo: Annotated[FitbitIntegrationRepository, Depends(get_fitbit_integration_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FitbitService:
    """Get the Fitbit service with injected repository and settings."""
    return FitbitService(settings=settings, repo=repo)


def get_oura_service(
    repo: Annotated[OuraIntegrationRepository, Depends(get_oura_integration_repository)],
) -> OuraService:
    """Get the Oura service with injected repository."""
    return OuraService(repo=repo)


FitbitServiceDep = Annotated[FitbitService, Depends(get_fitbit_service)]
OuraServiceDep = Annotated[OuraService, Depends(get_oura_service)]
