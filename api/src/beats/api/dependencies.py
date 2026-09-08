"""FastAPI dependency injection configuration."""

from collections.abc import Callable
from functools import lru_cache
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, HTTPException, Query, Request, status

from beats.domain.analytics import AnalyticsService
from beats.domain.calendar import CalendarService
from beats.domain.fitbit import FitbitService
from beats.domain.github import GitHubService
from beats.domain.intelligence import IntelligenceService
from beats.domain.oura import OuraService
from beats.domain.services import BeatService, ProjectService, TimerService
from beats.infrastructure.database import Database
from beats.infrastructure.repositories import (
    BeatRepository,
    BiometricDayRepository,
    CalendarIntegrationRepository,
    DeviceRegistrationRepository,
    FitbitIntegrationRepository,
    FlowWindowRepository,
    GitHubIntegrationRepository,
    InsightsRepository,
    MongoBeatRepository,
    MongoBiometricDayRepository,
    MongoCalendarIntegrationRepository,
    MongoDeviceRegistrationRepository,
    MongoFitbitIntegrationRepository,
    MongoFlowWindowRepository,
    MongoGitHubIntegrationRepository,
    MongoInsightsRepository,
    MongoOuraIntegrationRepository,
    MongoPairingCodeRepository,
    MongoPendingSuggestionRepository,
    MongoProjectRepository,
    MongoSignalSummaryRepository,
    MongoWebhookRepository,
    MongoWeeklyDigestRepository,
    MongoWeeklyPlanRepository,
    OuraIntegrationRepository,
    PairingCodeRepository,
    PendingSuggestionRepository,
    ProjectRepository,
    SignalSummaryRepository,
    WebhookRepository,
    WeeklyDigestRepository,
    WeeklyPlanRepository,
)
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
    try:
        return ZoneInfo(tz)
    except ZoneInfoNotFoundError, ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "INVALID_TIMEZONE", "message": f"Unknown timezone: {tz}"},
        ) from None


TimezoneDep = Annotated[ZoneInfo, Depends(get_timezone)]


get_beat_repository = _user_scoped(MongoBeatRepository, "timeLogs")


get_project_repository = _user_scoped(MongoProjectRepository, "projects")


get_flow_window_repository = _user_scoped(MongoFlowWindowRepository, "flow_windows")


def get_timer_service(
    beat_repo: Annotated[BeatRepository, Depends(get_beat_repository)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    flow_repo: Annotated[FlowWindowRepository, Depends(get_flow_window_repository)],
) -> TimerService:
    """Get the timer service with injected repositories."""
    return TimerService(beat_repo=beat_repo, project_repo=project_repo, flow_repo=flow_repo)


def get_beat_service(
    beat_repo: Annotated[BeatRepository, Depends(get_beat_repository)],
    flow_repo: Annotated[FlowWindowRepository, Depends(get_flow_window_repository)],
) -> BeatService:
    """Get the beat service with injected repository."""
    return BeatService(beat_repo=beat_repo, flow_repo=flow_repo)


def get_project_service(
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    beat_repo: Annotated[BeatRepository, Depends(get_beat_repository)],
) -> ProjectService:
    """Get the project service with injected repositories."""
    return ProjectService(project_repo=project_repo, beat_repo=beat_repo)


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
) -> IntelligenceService:
    """Get the intelligence service with injected repositories."""
    return IntelligenceService(
        beat_repo=beat_repo,
        project_repo=project_repo,
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
TimerServiceDep = Annotated[TimerService, Depends(get_timer_service)]
BeatServiceDep = Annotated[BeatService, Depends(get_beat_service)]
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
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
