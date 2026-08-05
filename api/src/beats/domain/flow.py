"""Pure aggregation helpers for the ambient daemon's flow-window signals.

Mirrors the reduction behind `GET /api/signals/flow-windows/summary` so the
coach can render a "you flowed best on X" headline without an HTTP round-trip.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from beats.domain.models import FlowWindow


def _repo_basename(repo: str) -> str:
    """Last path/owner component — "acme/widgets" and "/home/me/beats" → name."""
    return repo.rstrip("/").split("/")[-1]


def _top_key(windows: Sequence[FlowWindow], key_of: Callable[[FlowWindow], str]) -> str | None:
    """Most-frequent non-empty key, tie-broken by higher average flow score.

    Same rule as `_top_bucket` in the signals router and `beatsd top`.
    """
    counts: dict[str, int] = {}
    sums: dict[str, float] = {}
    for w in windows:
        k = key_of(w)
        if not k:
            continue
        counts[k] = counts.get(k, 0) + 1
        sums[k] = sums.get(k, 0.0) + w.flow_score
    if not counts:
        return None
    return max(counts, key=lambda k: (counts[k], sums[k] / counts[k]))


@dataclass(frozen=True, slots=True)
class FlowSummary:
    """Coach-renderable headline for a slice of flow windows."""

    count: int
    avg_score: float
    peak_score: float
    top_repo: str | None
    top_language: str | None


def summarize_flow(windows: Sequence[FlowWindow]) -> FlowSummary | None:
    """Reduce flow windows to a summary, or None for an empty slice.

    Drift events (the daemon posts these as flow_score=0) are excluded so the
    average reflects genuine focused time rather than distraction markers.
    """
    real = [w for w in windows if w.flow_score > 0]
    if not real:
        return None
    total = sum(w.flow_score for w in real)
    top_repo = _top_key(real, lambda w: w.editor_repo or "")
    return FlowSummary(
        count=len(real),
        avg_score=total / len(real),
        peak_score=max(w.flow_score for w in real),
        top_repo=_repo_basename(top_repo) if top_repo else None,
        top_language=_top_key(real, lambda w: (w.editor_language or "").lower()),
    )
