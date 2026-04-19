"""FastAPI dependency injection configuration."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from beats.domain.analytics import AnalyticsService
from beats.domain.calendar import CalendarService
from beats.domain.fitbit import FitbitService
from beats.domain.github import GitHubService
from beats.domain.intelligence import IntelligenceService
from beats.domain.oura import OuraService
from beats.domain.services import BeatService, ProjectService, TimerService
from beats.infrastructure.database import Database
from beats.infrastructure.repositories import (
    AutoStartRuleRepository,
    BeatRepository,
    BiometricDayRepository,
    CalendarIntegrationRepository,
    DailyNoteRepository,
    DeviceRegistrationRepository,
    FitbitIntegrationRepository,
    FlowWindowRepository,
    GitHubIntegrationRepository,
    InsightsRepository,
    IntentionRepository,
    MongoAutoStartRuleRepository,
    MongoBeatRepository,
    MongoBiometricDayRepository,
    MongoCalendarIntegrationRepository,
    MongoDailyNoteRepository,
    MongoDeviceRegistrationRepository,
    MongoFitbitIntegrationRepository,
    MongoFlowWindowRepository,
    MongoGitHubIntegrationRepository,
    MongoInsightsRepository,
    MongoIntentionRepository,
    MongoOuraIntegrationRepository,
    MongoPairingCodeRepository,
    MongoProjectRepository,
    MongoRecurringIntentionRepository,
    MongoSignalSummaryRepository,
    MongoWebhookRepository,
    MongoWeeklyDigestRepository,
    MongoWeeklyPlanRepository,
    MongoWeeklyReviewRepository,
    OuraIntegrationRepository,
    PairingCodeRepository,
    ProjectRepository,
    RecurringIntentionRepository,
    SignalSummaryRepository,
    WebhookRepository,
    WeeklyDigestRepository,
    WeeklyPlanRepository,
    WeeklyReviewRepository,
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


def get_beat_repository(user_id: CurrentUserId) -> BeatRepository:
    """Get the beat repository instance scoped to the current user."""
    db = Database.get_db()
    return MongoBeatRepository(db.timeLogs, user_id=user_id)


def get_project_repository(user_id: CurrentUserId) -> ProjectRepository:
    """Get the project repository instance scoped to the current user."""
    db = Database.get_db()
    return MongoProjectRepository(db.projects, user_id=user_id)


def get_timer_service(
    beat_repo: Annotated[BeatRepository, Depends(get_beat_repository)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
) -> TimerService:
    """Get the timer service with injected repositories."""
    return TimerService(beat_repo=beat_repo, project_repo=project_repo)


def get_beat_service(
    beat_repo: Annotated[BeatRepository, Depends(get_beat_repository)],
) -> BeatService:
    """Get the beat service with injected repository."""
    return BeatService(beat_repo=beat_repo)


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


def get_intention_repository(user_id: CurrentUserId) -> IntentionRepository:
    """Get the intention repository instance scoped to the current user."""
    db = Database.get_db()
    return MongoIntentionRepository(db.intentions, user_id=user_id)


def get_daily_note_repository(user_id: CurrentUserId) -> DailyNoteRepository:
    """Get the daily note repository instance scoped to the current user."""
    db = Database.get_db()
    return MongoDailyNoteRepository(db.daily_notes, user_id=user_id)


def get_webhook_repository(user_id: CurrentUserId) -> WebhookRepository:
    """Get the webhook repository instance scoped to the current user."""
    db = Database.get_db()
    return MongoWebhookRepository(db.webhooks, user_id=user_id)


def get_weekly_digest_repository(user_id: CurrentUserId) -> WeeklyDigestRepository:
    """Get the weekly digest repository scoped to the current user."""
    db = Database.get_db()
    return MongoWeeklyDigestRepository(db.weekly_digests, user_id=user_id)


def get_insights_repository(user_id: CurrentUserId) -> InsightsRepository:
    """Get the insights repository scoped to the current user."""
    db = Database.get_db()
    return MongoInsightsRepository(db.insights, user_id=user_id)


def get_intelligence_service(
    beat_repo: Annotated[BeatRepository, Depends(get_beat_repository)],
    project_repo: Annotated[ProjectRepository, Depends(get_project_repository)],
    intention_repo: Annotated[IntentionRepository, Depends(get_intention_repository)],
    daily_note_repo: Annotated[DailyNoteRepository, Depends(get_daily_note_repository)],
) -> IntelligenceService:
    """Get the intelligence service with injected repositories."""
    return IntelligenceService(
        beat_repo=beat_repo,
        project_repo=project_repo,
        intention_repo=intention_repo,
        daily_note_repo=daily_note_repo,
    )


def get_calendar_integration_repository(user_id: CurrentUserId) -> CalendarIntegrationRepository:
    """Get the calendar integration repository scoped to the current user."""
    db = Database.get_db()
    return MongoCalendarIntegrationRepository(db.calendar_integrations, user_id=user_id)


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
IntentionRepoDep = Annotated[IntentionRepository, Depends(get_intention_repository)]
DailyNoteRepoDep = Annotated[DailyNoteRepository, Depends(get_daily_note_repository)]
WebhookRepoDep = Annotated[WebhookRepository, Depends(get_webhook_repository)]
WeeklyDigestRepoDep = Annotated[WeeklyDigestRepository, Depends(get_weekly_digest_repository)]
InsightsRepoDep = Annotated[InsightsRepository, Depends(get_insights_repository)]
IntelligenceServiceDep = Annotated[IntelligenceService, Depends(get_intelligence_service)]
CalendarServiceDep = Annotated[CalendarService, Depends(get_calendar_service)]


def get_github_integration_repository(user_id: CurrentUserId) -> GitHubIntegrationRepository:
    """Get the GitHub integration repository scoped to the current user."""
    db = Database.get_db()
    return MongoGitHubIntegrationRepository(db.github_integrations, user_id=user_id)


def get_github_service(
    gh_repo: Annotated[GitHubIntegrationRepository, Depends(get_github_integration_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GitHubService:
    """Get the GitHub service with injected repository."""
    return GitHubService(settings=settings, repo=gh_repo)


GitHubServiceDep = Annotated[GitHubService, Depends(get_github_service)]


def get_auto_start_rule_repository(user_id: CurrentUserId) -> AutoStartRuleRepository:
    """Get the auto-start rule repository scoped to the current user."""
    db = Database.get_db()
    return MongoAutoStartRuleRepository(db.auto_start_rules, user_id=user_id)


AutoStartRuleRepoDep = Annotated[AutoStartRuleRepository, Depends(get_auto_start_rule_repository)]


def get_weekly_plan_repository(user_id: CurrentUserId) -> WeeklyPlanRepository:
    """Get the weekly plan repository scoped to the current user."""
    db = Database.get_db()
    return MongoWeeklyPlanRepository(db.weekly_plans, user_id=user_id)


def get_recurring_intention_repository(user_id: CurrentUserId) -> RecurringIntentionRepository:
    """Get the recurring intention repository scoped to the current user."""
    db = Database.get_db()
    return MongoRecurringIntentionRepository(db.recurring_intentions, user_id=user_id)


def get_weekly_review_repository(user_id: CurrentUserId) -> WeeklyReviewRepository:
    """Get the weekly review repository scoped to the current user."""
    db = Database.get_db()
    return MongoWeeklyReviewRepository(db.weekly_reviews, user_id=user_id)


WeeklyPlanRepoDep = Annotated[WeeklyPlanRepository, Depends(get_weekly_plan_repository)]
RecurringIntentionRepoDep = Annotated[
    RecurringIntentionRepository, Depends(get_recurring_intention_repository)
]
WeeklyReviewRepoDep = Annotated[WeeklyReviewRepository, Depends(get_weekly_review_repository)]


def get_pairing_code_repository() -> PairingCodeRepository:
    """Get the pairing code repository (not user-scoped)."""
    db = Database.get_db()
    return MongoPairingCodeRepository(db.pairing_codes)


def get_device_registration_repository() -> DeviceRegistrationRepository:
    """Get the device registration repository (not user-scoped)."""
    db = Database.get_db()
    return MongoDeviceRegistrationRepository(db.device_registrations)


PairingCodeRepoDep = Annotated[PairingCodeRepository, Depends(get_pairing_code_repository)]
DeviceRegistrationRepoDep = Annotated[
    DeviceRegistrationRepository, Depends(get_device_registration_repository)
]


def get_flow_window_repository(user_id: CurrentUserId) -> FlowWindowRepository:
    """Get the flow window repository scoped to the current user."""
    db = Database.get_db()
    return MongoFlowWindowRepository(db.flow_windows, user_id=user_id)


def get_signal_summary_repository(user_id: CurrentUserId) -> SignalSummaryRepository:
    """Get the signal summary repository scoped to the current user."""
    db = Database.get_db()
    return MongoSignalSummaryRepository(db.signal_summaries, user_id=user_id)


FlowWindowRepoDep = Annotated[FlowWindowRepository, Depends(get_flow_window_repository)]
SignalSummaryRepoDep = Annotated[SignalSummaryRepository, Depends(get_signal_summary_repository)]


def get_biometric_repository(user_id: CurrentUserId) -> BiometricDayRepository:
    """Get the biometric day repository scoped to the current user."""
    db = Database.get_db()
    return MongoBiometricDayRepository(db.biometric_days, user_id=user_id)


def get_fitbit_integration_repository(user_id: CurrentUserId) -> FitbitIntegrationRepository:
    """Get the Fitbit integration repository scoped to the current user."""
    db = Database.get_db()
    return MongoFitbitIntegrationRepository(db.fitbit_integrations, user_id=user_id)


def get_oura_integration_repository(user_id: CurrentUserId) -> OuraIntegrationRepository:
    """Get the Oura integration repository scoped to the current user."""
    db = Database.get_db()
    return MongoOuraIntegrationRepository(db.oura_integrations, user_id=user_id)


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
