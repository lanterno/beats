"""FastAPI dependency injection configuration."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from beats.domain.analytics import AnalyticsService
from beats.domain.calendar import CalendarService
from beats.domain.github import GitHubService
from beats.domain.intelligence import IntelligenceService
from beats.domain.services import BeatService, ProjectService, TimerService
from beats.infrastructure.database import Database
from beats.infrastructure.repositories import (
    AutoStartRuleRepository,
    BeatRepository,
    CalendarIntegrationRepository,
    DailyNoteRepository,
    InsightsRepository,
    IntentionRepository,
    MongoBeatRepository,
    MongoAutoStartRuleRepository,
    MongoCalendarIntegrationRepository,
    MongoDailyNoteRepository,
    MongoInsightsRepository,
    MongoIntentionRepository,
    MongoProjectRepository,
    MongoWebhookRepository,
    MongoWeeklyDigestRepository,
    ProjectRepository,
    WebhookRepository,
    WeeklyDigestRepository,
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
    cal_repo: Annotated[CalendarIntegrationRepository, Depends(get_calendar_integration_repository)],
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


def get_github_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> GitHubService:
    """Get the GitHub service."""
    return GitHubService(settings=settings)


GitHubServiceDep = Annotated[GitHubService, Depends(get_github_service)]


def get_auto_start_rule_repository(user_id: CurrentUserId) -> AutoStartRuleRepository:
    """Get the auto-start rule repository scoped to the current user."""
    db = Database.get_db()
    return MongoAutoStartRuleRepository(db.auto_start_rules, user_id=user_id)


AutoStartRuleRepoDep = Annotated[AutoStartRuleRepository, Depends(get_auto_start_rule_repository)]
