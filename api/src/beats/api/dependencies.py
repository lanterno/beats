"""FastAPI dependency injection configuration."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from beats.domain.analytics import AnalyticsService
from beats.domain.services import BeatService, ProjectService, TimerService
from beats.infrastructure.database import Database
from beats.infrastructure.repositories import (
    BeatRepository,
    DailyNoteRepository,
    IntentionRepository,
    MongoBeatRepository,
    MongoDailyNoteRepository,
    MongoIntentionRepository,
    MongoProjectRepository,
    MongoWebhookRepository,
    ProjectRepository,
    WebhookRepository,
)
from beats.settings import Settings


@lru_cache
def get_settings() -> Settings:
    """Get application settings (cached)."""
    return Settings()


def get_beat_repository() -> BeatRepository:
    """Get the beat repository instance."""
    db = Database.get_db()
    return MongoBeatRepository(db.timeLogs)


def get_project_repository() -> ProjectRepository:
    """Get the project repository instance."""
    db = Database.get_db()
    return MongoProjectRepository(db.projects)


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


def get_intention_repository() -> IntentionRepository:
    """Get the intention repository instance."""
    db = Database.get_db()
    return MongoIntentionRepository(db.intentions)


def get_daily_note_repository() -> DailyNoteRepository:
    """Get the daily note repository instance."""
    db = Database.get_db()
    return MongoDailyNoteRepository(db.daily_notes)


def get_webhook_repository() -> WebhookRepository:
    """Get the webhook repository instance."""
    db = Database.get_db()
    return MongoWebhookRepository(db.webhooks)


# Type aliases for cleaner dependency injection in routes
TimerServiceDep = Annotated[TimerService, Depends(get_timer_service)]
BeatServiceDep = Annotated[BeatService, Depends(get_beat_service)]
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
AnalyticsServiceDep = Annotated[AnalyticsService, Depends(get_analytics_service)]
IntentionRepoDep = Annotated[IntentionRepository, Depends(get_intention_repository)]
DailyNoteRepoDep = Annotated[DailyNoteRepository, Depends(get_daily_note_repository)]
WebhookRepoDep = Annotated[WebhookRepository, Depends(get_webhook_repository)]
