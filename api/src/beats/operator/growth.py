"""The database's pace, read off the sizes the job runner keeps (docs/backoffice.md
§ The pages, Capacity).

Pure, so the arithmetic is tested without Mongo: `MongoDatabaseSizes`
(infrastructure/database_sizes.py) keeps one size a UTC day, and
`MongoOperatorReads.capacity` hands what it reads to these.

The pace is the plainest one that can be said in a sentence: what the
database moved between two days kept, over the days between them, carried to
a month. Two days because one size is where the database stands, not a pace;
the dates rather than the count of sizes because a runner that missed a week
has a gap, not a shorter month.
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace

from beats.operator.reads import GROWTH_PACE_DAYS, CollectionSize, DatabaseGrowth, SizeDay

# "A month" in the sentence and the chart: about, by design, so a round 30.
DAYS_A_MONTH = 30


def pace_window(sizes: Sequence[SizeDay]) -> tuple[SizeDay, SizeDay] | None:
    """The two days the pace is read between: the newest kept, and the oldest
    kept within `GROWTH_PACE_DAYS` before it — or, when nothing was kept in
    that span (a runner off for longer), the one kept just before the newest.
    None below two days."""
    ordered = sorted({s.day: s for s in sizes}.values(), key=lambda s: s.day)
    if len(ordered) < 2:
        return None
    last = ordered[-1]
    within = [s for s in ordered[:-1] if (last.day - s.day).days <= GROWTH_PACE_DAYS]
    return (within[0] if within else ordered[-2]), last


def database_growth(sizes: Sequence[SizeDay]) -> DatabaseGrowth | None:
    """The database's pace, or None below two days kept."""
    window = pace_window(sizes)
    if window is None:
        return None
    first, last = window
    days = (last.day - first.day).days
    change = last.storage_bytes - first.storage_bytes
    return DatabaseGrowth(
        since=first.day,
        until=last.day,
        change_bytes=change,
        bytes_a_month=change * DAYS_A_MONTH / days,
    )


def with_growth(
    collections: Sequence[CollectionSize],
    growth: DatabaseGrowth | None,
    then: Mapping[str, int],
    now: Mapping[str, int],
) -> list[CollectionSize]:
    """Each collection with its pace between the database's two days, from
    what each took up on them (`then` on `growth.since`, `now` on
    `growth.until`, by name). A collection kept on only one of the days —
    made or dropped between them — has none: its whole size is not growth."""
    if growth is None:
        return list(collections)
    days = (growth.until - growth.since).days
    out = []
    for c in collections:
        before, after = then.get(c.name), now.get(c.name)
        if before is None or after is None:
            out.append(c)
            continue
        bytes_a_month = (after - before) * DAYS_A_MONTH / days
        out.append(
            replace(
                c,
                growth_bytes_a_month=bytes_a_month,
                growth_share_a_month=bytes_a_month / before if before > 0 else None,
            )
        )
    return out
