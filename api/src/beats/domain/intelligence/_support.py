"""Small helpers the intelligence modules share.

The local-date pair is the important one: beats carry UTC timestamps, so a
query for a date range has to be widened and then narrowed in local time, or
the sessions nearest each boundary go missing from the day they belong to.
"""

from datetime import date, timedelta
from zoneinfo import ZoneInfo

from beats.domain.models import Beat
from beats.domain.ports import RangeBeatReader
from beats.domain.utils import local_date

UTC_TZ = ZoneInfo("UTC")


async def _beats_covering(repo: RangeBeatReader, start: date, end: date) -> list[Beat]:
    """Completed beats for [start, end], widened by a day at each end.

    Beats are stored with UTC timestamps. A session at 23:30 local on the 3rd
    is stored under the 4th, so a query for exactly [start, end] loses the
    sessions nearest each boundary. Callers that bucket by local date
    themselves want those edge sessions present and do the narrowing after.
    """
    return await repo.list_completed_in_range(start - timedelta(days=1), end + timedelta(days=1))


async def _beats_in_local_range(
    repo: RangeBeatReader, start: date, end: date, tz: ZoneInfo
) -> list[Beat]:
    """Completed beats whose *local* date falls within [start, end]."""
    beats = await _beats_covering(repo, start, end)
    return [b for b in beats if start <= local_date(b.start, tz) <= end]


def _monday_of(d: date) -> date:
    """Get the Monday of the week containing the given date."""
    return d - timedelta(days=d.weekday())


def _format_hours(minutes: float) -> str:
    h = minutes / 60
    if h >= 1:
        return f"{h:.1f}h"
    return f"{int(minutes)}m"


def _rescale_score(consistency: float, goals: float, quality: float) -> int:
    """Combine the three 0-25 components into a 0-100 productivity score.

    Each component maxes at 25 (sum ≤ 75); the ``* 4 / 3`` stretches that to
    0-100, clamped. Single source of truth for the live score, its weekly
    history, and the digest (which passes a neutral goals=13)."""
    return min(100, round((consistency + goals + quality) * 4 / 3))
