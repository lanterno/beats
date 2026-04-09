"""FastAPI dependency injection configuration."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

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


# Type aliases for cleaner dependency injection in routes
TimerServiceDep = Annotated[TimerService, Depends(get_timer_service)]
BeatServiceDep = Annotated[BeatService, Depends(get_beat_service)]
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
AnalyticsServiceDep = Annotated[AnalyticsService, Depends(get_analytics_service)]
IntentionRepoDep = Annotated[IntentionRepository, Depends(get_intention_repository)]
DailyNoteRepoDep = Annotated[DailyNoteRepository, Depends(get_daily_note_repository)]
WebhookRepoDep = Annotated[WebhookRepository, Depends(get_webhook_repository)]
