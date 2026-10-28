"""The compliance warnings on their interesting inputs (#350).

`compliance_warnings` is pure arithmetic over the record's rows, so the
boundaries are tested here with synthetic records: exactly at a threshold is
lawful, the law binds per person across projects, and the first day read has
no rest to judge. The CSV's shape and the HTTP contract stay in
`src/test_organisations.py`.
"""

from datetime import UTC, date, datetime, timedelta
from typing import NamedTuple

from beats.domain.employment import MAX_DAILY_HOURS, compliance_warnings
from beats.domain.models import MemberTotals, OrgProject
from beats.domain.organisations import MemberRecord, ProjectRecord, RecordEntry


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 3, day, hour, minute, tzinfo=UTC)


def _entry(day: int, start_hour: float, hours: float, eid: str = "e") -> RecordEntry:
    start = datetime(2026, 3, day, int(start_hour), int((start_hour % 1) * 60), tzinfo=UTC)
    return RecordEntry(
        id=eid,
        day=date(2026, 3, day),
        start=start,
        end=start + timedelta(hours=hours),
        hours=hours,
        note=None,
    )


def _member(user_id: str, entries: list[RecordEntry]) -> MemberRecord:
    return MemberRecord(
        user_id=user_id,
        name=user_id,
        shared_from=_at(1, 0),
        active=True,
        hours=sum(e.hours for e in entries),
        entries=entries,
        absences=[],
        has_contract=False,
        balance=None,
        totals=MemberTotals(),
    )


class _Record(NamedTuple):
    projects: list[ProjectRecord]


def _record(*projects: tuple[str, list[MemberRecord]]) -> _Record:
    return _Record(
        projects=[
            ProjectRecord(project=OrgProject(id=name, name=name), members=members)
            for name, members in projects
        ]
    )


class TestDailyMaximum:
    def test_exactly_ten_hours_is_lawful(self):
        record = _record(("P", [_member("u1", [_entry(3, 8, MAX_DAILY_HOURS)])]))
        assert compliance_warnings(record) == {}

    def test_over_ten_hours_warns_with_the_day_total(self):
        record = _record(("P", [_member("u1", [_entry(3, 7, 10.5)])]))
        warnings = compliance_warnings(record)
        assert warnings == {("u1", date(2026, 3, 3)): ["day over 10 h (10.50 h)"]}

    def test_the_day_is_the_person_not_the_project(self):
        # Six lawful hours on each project are one twelve-hour day.
        record = _record(
            ("A", [_member("u1", [_entry(3, 6, 6, "a")])]),
            ("B", [_member("u1", [_entry(3, 13, 6, "b")])]),
        )
        warnings = compliance_warnings(record)
        assert warnings == {("u1", date(2026, 3, 3)): ["day over 10 h (12.00 h)"]}

    def test_two_members_are_judged_apart(self):
        record = _record(
            ("P", [_member("u1", [_entry(3, 6, 6)]), _member("u2", [_entry(3, 6, 11)])])
        )
        assert set(compliance_warnings(record)) == {("u2", date(2026, 3, 3))}


class TestRestPeriod:
    def test_exactly_eleven_hours_rest_is_lawful(self):
        # Ends 18:00, resumes 05:00 next day: exactly the 11 hours owed.
        record = _record(
            ("P", [_member("u1", [_entry(3, 10, 8), _entry(4, 5, 4)])]),
        )
        assert compliance_warnings(record) == {}

    def test_short_rest_warns_on_the_later_day(self):
        # Ends 22:00 on the 3rd, starts 06:00 on the 4th: 8 hours' rest.
        record = _record(("P", [_member("u1", [_entry(3, 14, 8), _entry(4, 6, 2)])]))
        warnings = compliance_warnings(record)
        assert warnings == {("u1", date(2026, 3, 4)): ["rest under 11 h (8.00 h after 2026-03-03)"]}

    def test_the_night_between_two_projects_is_one_rest(self):
        # Evening on project A, early morning on project B.
        record = _record(
            ("A", [_member("u1", [_entry(3, 16, 6, "a")])]),  # ends 22:00
            ("B", [_member("u1", [_entry(4, 6, 2, "b")])]),  # starts 06:00
        )
        warnings = compliance_warnings(record)
        assert warnings == {("u1", date(2026, 3, 4)): ["rest under 11 h (8.00 h after 2026-03-03)"]}

    def test_the_first_day_read_has_no_rest_to_judge(self):
        record = _record(("P", [_member("u1", [_entry(1, 0, 2)])]))
        assert compliance_warnings(record) == {}

    def test_rest_is_against_the_nearest_earlier_working_day(self):
        # A free day between: Friday 18:00 to Sunday 06:00 is 36 hours.
        record = _record(("P", [_member("u1", [_entry(6, 10, 8), _entry(8, 6, 2)])]))
        assert compliance_warnings(record) == {}

    def test_a_day_can_carry_both_warnings(self):
        record = _record(("P", [_member("u1", [_entry(3, 12, 10), _entry(4, 6, 10.5)])]))
        warnings = compliance_warnings(record)
        assert warnings[("u1", date(2026, 3, 4))] == [
            "day over 10 h (10.50 h)",
            "rest under 11 h (8.00 h after 2026-03-03)",
        ]
