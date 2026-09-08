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
