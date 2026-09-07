"""Focus quality — how good each of a day's sessions was."""

from collections import defaultdict
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from beats.domain.models import Beat
from beats.domain.ports import RangeBeatReader
from beats.domain.utils import local_dt

from ._support import UTC_TZ, _beats_in_local_range


async def compute_focus_scores(
    beat_repo: RangeBeatReader, target_date: date, tz: ZoneInfo = UTC_TZ
) -> list[dict]:
    """Compute focus quality scores for all sessions on a given local date."""
    beats = await _beats_in_local_range(beat_repo, target_date, target_date, tz)
    if not beats:
        return []

    # Compute user's peak hours from recent data
    recent_start = target_date - timedelta(days=30)
    recent_beats = await beat_repo.list_completed_in_range(recent_start, target_date)
    peak_block = find_peak_block(recent_beats, tz)

    sorted_beats = sorted(beats, key=lambda b: b.start)
    results = []
    for i, b in enumerate(sorted_beats):
        score = focus_score_for_beat(b, sorted_beats, i, peak_block, tz)
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
