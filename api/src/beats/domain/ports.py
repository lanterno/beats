"""The persistence shapes the domain asks for, declared where they are used.

Two things follow from putting them here rather than importing repository
interfaces from `beats.infrastructure`. The dependency points inward — domain
code no longer reaches out to the layer that is supposed to implement it — and
each protocol lists only the methods its consumer actually calls, so a service
that reads completed beats cannot quietly start writing them.

That narrowness is also what lets the test suite's in-memory fakes stand in.
`AnalyticsService` needs two methods; asking for a whole `BeatRepository` meant
every fake either implemented twelve or lied about its type.

`MongoBeatRepository` and `MongoProjectRepository` satisfy these structurally —
there is nothing to register.
"""

import builtins
from datetime import date, datetime
from typing import Protocol

from beats.domain.models import Beat, FlowWindow, Project


class CompletedBeatReader(Protocol):
    """Read access to finished beats. Used by analytics and intelligence."""

    async def list_all_completed(self) -> list[Beat]: ...
    async def list_completed_in_range(self, start: date, end: date) -> list[Beat]: ...


class RangeBeatReader(Protocol):
    """Just the date-range read — all the intelligence services need."""

    async def list_completed_in_range(self, start: date, end: date) -> list[Beat]: ...


class ProjectLister(Protocol):
    """Read access to the project list."""

    # builtins.list because this class defines a method called `list`, which
    # would otherwise shadow the builtin in the annotation.
    async def list(self, archived: bool = False) -> builtins.list[Project]: ...


class FlowWindowReader(Protocol):
    """Flow windows over a time range."""

    async def list_by_range(self, start: datetime, end: datetime) -> list[FlowWindow]: ...


class TimerBeatStore(Protocol):
    """The four beat operations running a timer needs: open one, find the
    open one, find the last one, close it."""

    async def create(self, beat: Beat) -> Beat: ...
    async def get_active(self) -> Beat | None: ...
    async def get_last(self) -> Beat: ...
    async def update(self, beat: Beat) -> Beat: ...


class TimerProjectReader(Protocol):
    """What the timer asks about a project before starting against it."""

    async def exists(self, project_id: str) -> bool: ...
    async def get_by_id(self, project_id: str) -> Project: ...


class BeatStore(Protocol):
    """CRUD over beats — what `BeatService` needs, not the twelve methods
    the Mongo repository happens to offer."""

    async def get_by_id(self, beat_id: str) -> Beat: ...
    async def create(self, beat: Beat) -> Beat: ...
    async def update(self, beat: Beat) -> Beat: ...
    async def delete(self, beat_id: str) -> bool: ...
    # builtins.list because this class defines a method called `list`.
    async def list(
        self, project_id: str | None = None, date_filter: date | None = None
    ) -> builtins.list[Beat]: ...


class ProjectStore(Protocol):
    """CRUD over projects, plus the list read `ProjectLister` also offers."""

    async def get_by_id(self, project_id: str) -> Project: ...
    async def create(self, project: Project) -> Project: ...
    async def update(self, project: Project) -> Project: ...
    async def list(self, archived: bool = False) -> builtins.list[Project]: ...


class ProjectBeatReader(Protocol):
    """One project's beats. All `ProjectService` asks of beat storage."""

    async def list_by_project(self, project_id: str) -> list[Beat]: ...
