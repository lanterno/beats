"""The database's pace (docs/backoffice.md § The pages, Capacity), on the
inputs that shape it: one day kept, a gap where the runner did not run, a
history longer than the pace's span, a database that shrank, and a
collection made or dropped inside the span. Where the sizes come from is
test_operator_capacity.py's."""

from datetime import date, timedelta

import pytest

from beats.operator.growth import DAYS_A_MONTH, database_growth, pace_window, with_growth
from beats.operator.reads import GROWTH_PACE_DAYS, CollectionSize, SizeDay

MB = 1024 * 1024
DAY = date(2026, 11, 14)


def _day(days_ago: int, mb: float) -> SizeDay:
    return SizeDay(day=DAY - timedelta(days=days_ago), storage_bytes=int(mb * MB))


class TestPace:
    def test_one_day_kept_is_where_it_stands_not_a_pace(self):
        assert database_growth([]) is None
        assert database_growth([_day(0, 10)]) is None

    def test_two_days_carry_one_days_change_to_a_month(self):
        growth = database_growth([_day(1, 10), _day(0, 11)])
        assert growth is not None
        assert (growth.since, growth.until) == (DAY - timedelta(days=1), DAY)
        assert growth.change_bytes == MB
        assert growth.bytes_a_month == DAYS_A_MONTH * MB

    def test_a_gap_is_counted_in_days_not_in_sizes_kept(self):
        """The runner missed four days: two sizes five days apart are five
        days' growth, not one's."""
        growth = database_growth([_day(5, 10), _day(0, 15)])
        assert growth is not None
        assert growth.bytes_a_month == pytest.approx(DAYS_A_MONTH * MB)

    def test_a_long_history_is_read_over_the_last_span_only(self):
        """A year ago the database was nearly empty; the pace is the last
        month's, not the year's average."""
        sizes = [_day(365, 1), _day(GROWTH_PACE_DAYS + 1, 100), _day(GROWTH_PACE_DAYS, 100)]
        sizes += [_day(0, 130)]
        growth = database_growth(sizes)
        assert growth is not None
        assert growth.since == DAY - timedelta(days=GROWTH_PACE_DAYS)
        assert growth.bytes_a_month == pytest.approx(30 * MB * DAYS_A_MONTH / GROWTH_PACE_DAYS)

    def test_with_nothing_kept_inside_the_span_the_day_before_the_newest_stands_in(self):
        """A runner off for two months and back today: the pace is read from
        the last size before the gap, over the whole gap."""
        sizes = [_day(80, 40), _day(60, 50), _day(0, 80)]
        window = pace_window(sizes)
        assert window is not None
        assert window[0].day == DAY - timedelta(days=60)
        growth = database_growth(sizes)
        assert growth is not None
        assert growth.bytes_a_month == pytest.approx(30 * MB * DAYS_A_MONTH / 60)

    def test_a_database_that_shrank_has_a_negative_pace(self):
        growth = database_growth([_day(10, 50), _day(0, 40)])
        assert growth is not None
        assert growth.change_bytes == -10 * MB
        assert growth.bytes_a_month < 0

    def test_the_order_and_a_repeated_day_do_not_matter(self):
        """The read hands them oldest first, but the arithmetic does not
        lean on it, and a day is one size."""
        growth = database_growth([_day(0, 11), _day(1, 10), _day(1, 10)])
        assert growth is not None
        assert growth.change_bytes == MB


class TestCollections:
    def _collection(self, name: str, mb: float) -> CollectionSize:
        return CollectionSize(name=name, documents=1, storage_bytes=int(mb * MB))

    def test_each_collection_moves_at_its_own_pace_and_share(self):
        growth = database_growth([_day(10, 30), _day(0, 36)])
        out = with_growth(
            [self._collection("beats", 22), self._collection("flow", 14)],
            growth,
            then={"beats": 20 * MB, "flow": 10 * MB},
            now={"beats": 22 * MB, "flow": 14 * MB},
        )
        beats, flow = out
        assert beats.growth_bytes_a_month == pytest.approx(2 * MB * DAYS_A_MONTH / 10)
        assert beats.growth_share_a_month == pytest.approx(0.1 * DAYS_A_MONTH / 10)
        assert flow.growth_bytes_a_month == pytest.approx(4 * MB * DAYS_A_MONTH / 10)
        assert flow.growth_share_a_month == pytest.approx(0.4 * DAYS_A_MONTH / 10)

    def test_a_collection_made_inside_the_span_has_no_pace(self):
        """Its whole size is not growth: it was not there to grow from."""
        growth = database_growth([_day(10, 30), _day(0, 36)])
        (made,) = with_growth(
            [self._collection("new_one", 6)], growth, then={}, now={"new_one": 6 * MB}
        )
        assert made.growth_bytes_a_month is None
        assert made.growth_share_a_month is None

    def test_a_collection_that_took_up_nothing_has_a_pace_but_no_share(self):
        growth = database_growth([_day(10, 30), _day(0, 36)])
        (empty,) = with_growth(
            [self._collection("was_empty", 1)], growth, then={"was_empty": 0}, now={"was_empty": MB}
        )
        assert empty.growth_bytes_a_month == pytest.approx(MB * DAYS_A_MONTH / 10)
        assert empty.growth_share_a_month is None

    def test_no_pace_leaves_every_collection_as_it_stands(self):
        collections = [self._collection("beats", 22)]
        assert with_growth(collections, None, then={}, now={}) == collections
