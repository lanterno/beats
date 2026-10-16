"""Focus quality — how good each of a day's sessions was."""

from collections import defaultdict
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from beats.domain.models import Beat
from beats.domain.ports import RangeBeatReader
from beats.domain.utils import local_date, local_dt

from ._support import UTC_TZ, _beats_covering

# A session's peak hours come from the local days up to and including it.
PEAK_WINDOW_DAYS = 30

# The first day `compute_focus_scores` can score: its peak window, and the day
# `_beats_covering` widens a read by, have to fit inside the calendar.
EARLIEST_SCORABLE_DAY = date.min + timedelta(days=PEAK_WINDOW_DAYS + 1)


async def compute_focus_scores(
    beat_repo: RangeBeatReader, start: date, end: date, tz: ZoneInfo = UTC_TZ
) -> list[dict]:
    """Focus quality scores for every session whose local date is in [start, end].

    Each day is scored exactly as a request for that day alone would score it,
    so a session's mark is the same on the Today feed and on the project page:
    its own peak block, from the 30 local days up to and including it, and
    fragmentation that only counts neighbours on the same local day.

    The window is read in local dates, so a session just after local midnight
    30 days back counts wherever UTC filed it, and sorted by start, so a tie
    between two blocks breaks the same way on every run. Rows come out by day,
    then by start.
    """
    window = sorted(
        await _beats_covering(beat_repo, start - timedelta(days=PEAK_WINDOW_DAYS), end),
        key=lambda b: b.start,
    )
    dated = [(local_date(b.start, tz), b) for b in window]
    by_day: dict[date, list[Beat]] = defaultdict(list)
    for d, b in dated:
        if start <= d <= end:
            by_day[d].append(b)

    results = []
    for d in sorted(by_day):
        since = d - timedelta(days=PEAK_WINDOW_DAYS)
        peak_block = find_peak_block([b for bd, b in dated if since <= bd <= d], tz)
        day_beats = by_day[d]
        for i, b in enumerate(day_beats):
            score = focus_score_for_beat(b, day_beats, i, peak_block, tz)
            results.append(
                {
                    "beat_id": b.id,
                    "score": score["score"],
                    "components": score["components"],
                }
            )
    return results


def find_peak_block(beats: list[Beat], tz: ZoneInfo = UTC_TZ) -> int:
    """Find the 2-hour block with the most total minutes."""
    blocks: dict[int, float] = defaultdict(float)
    for b in beats:
        block = local_dt(b.start, tz).hour // 2
        blocks[block] += b.duration.total_seconds() / 60
    if not blocks:
        return 4  # default: 8-10 AM
    return max(blocks, key=lambda b: blocks[b])


def focus_score_for_beat(
    beat: Beat, day_beats: list[Beat], index: int, peak_block: int, tz: ZoneInfo = UTC_TZ
) -> dict:
    """Compute focus score for a single beat."""
    dur_min = beat.duration.total_seconds() / 60

    # Length component (0-40)
    if dur_min < 10:
        length = 5
    elif dur_min < 25:
        length = 15
    elif dur_min < 45:
        length = 25
    elif dur_min < 90:
        length = 35
    else:
        length = 40

    # Peak hours component (0-30)
    beat_block = local_dt(beat.start, tz).hour // 2
    if beat_block == peak_block:
        peak = 30
    elif abs(beat_block - peak_block) == 1:
        peak = 20
    else:
        peak = 10

    # Fragmentation penalty (start at 30, subtract for close gaps)
    frag = 30
    if index > 0:
        prev = day_beats[index - 1]
        if prev.end:
            gap = (beat.start - prev.end).total_seconds() / 60
            if 0 < gap < 5:
                frag -= 15
    if index < len(day_beats) - 1:
        nxt = day_beats[index + 1]
        if beat.end:
            gap = (nxt.start - beat.end).total_seconds() / 60
            if 0 < gap < 5:
                frag -= 15

    total = max(0, min(100, length + peak + frag))
    return {
        "score": total,
        "components": {"length": length, "peak_hours": peak, "fragmentation": frag},
    }
