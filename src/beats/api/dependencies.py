"""FastAPI dependency injection configuration."""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from beats.domain.services import BeatService, ProjectService, TimerService
from beats.infrastructure.database import Database
from beats.infrastructure.repositories import (
    BeatRepository,
    MongoBeatRepository,
    MongoProjectRepository,
    ProjectRepository,
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


# Type aliases for cleaner dependency injection in routes
SettingsDep = Annotated[Settings, Depends(get_settings)]
TimerServiceDep = Annotated[TimerService, Depends(get_timer_service)]
BeatServiceDep = Annotated[BeatService, Depends(get_beat_service)]
ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
