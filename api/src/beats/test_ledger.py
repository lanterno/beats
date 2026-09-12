"""Tests for the ledger assembly, on fixed dates.

One fixture carries most of them: a day job whose contract went from 60 % to
80 % of 42 h on a Monday, took a full week off, and is read on a Thursday ten
weeks in — so one call shows a week before the first term, six under the old
rate, one under the new, the vacation week, and the open one. The figures are
worked out by hand below and asserted as such; the row-to-row invariant is
then checked for every pair, which is what a reader of the ledger does by eye.
"""

from datetime import date, timedelta
from itertools import pairwise

import pytest

from beats.domain.ledger import assemble_ledger
from beats.domain.models import (
    Absence,
    AbsenceType,
    Contract,
    ContractTerm,
    GoalOverride,
    GoalType,
    LedgerNote,
    LedgerNoteKind,
    Project,
    ProjectKind,
    ScheduleType,
)

TODAY = date(2026, 3, 5)  # a Thursday
MONDAY = date(2026, 3, 2)  # its week
FIRST_TERM = date(2026, 1, 5)  # 60 % of 42 h = 25.2 h/week, 5.04 h/day
SECOND_TERM = date(2026, 2, 16)  # 80 % of 42 h = 33.6 h/week, 6.72 h/day
VACATION = date(2026, 2, 23)  # Mon–Fri off
OPENING = 2.0


def _monday(weeks_back: int) -> date:
    return MONDAY - timedelta(weeks=weeks_back)


def _term(effective_from: date, percentage: float) -> ContractTerm:
    return ContractTerm(
        effective_from=effective_from,
        schedule_type=ScheduleType.PART_TIME,
        full_time_hours=42,
        percentage=percentage,
    )


def _contract(*terms: ContractTerm, **fields) -> Contract:
    return Contract(
        terms=list(terms) or [_term(FIRST_TERM, 0.6), _term(SECOND_TERM, 0.8)],
        opening_balance_hours=OPENING,
        **fields,
    )


def _day_job(contract: Contract | None, **fields) -> Project:
    return Project(id="p1", name="Job", kind=ProjectKind.DAY_JOB, contract=contract, **fields)


def _worked() -> dict[date, float]:
    """6 h every weekday from the first term through Wednesday 4 March, bar
    the vacation week — and 3 h on that Wednesday, the last day worked."""
    hours: dict[date, float] = {}
    day = FIRST_TERM
    while day < TODAY:
        if day.weekday() < 5 and not VACATION <= day < VACATION + timedelta(days=5):
            hours[day] = 6.0
        day += timedelta(days=1)
    hours[TODAY - timedelta(days=1)] = 3.0
    return hours


def _vacation() -> list[Absence]:
    return [
        Absence(project_id="p1", date=VACATION + timedelta(days=n), type=AbsenceType.VACATION)
        for n in range(5)
    ]


def _ledger(
    project: Project | None = None,
    *,
    absences=None,
    holidays=None,
    worked=None,
    today: date = TODAY,
    weeks: int = 10,
):
    if project is None:
        project = _day_job(_contract())
    contract = project.contract if project.kind is ProjectKind.DAY_JOB else None
    return assemble_ledger(
        project,
        contract,
        _vacation() if absences is None else absences,
        holidays or {},
        _worked() if worked is None else worked,
        today,
        weeks,
    )


class TestLedgerWeeks:
    def test_weeks_are_newest_first_ending_with_the_current_one(self):
        ledger = _ledger()
        assert [w.week_of for w in ledger.weeks] == [_monday(n) for n in range(10)]
        assert _ledger(weeks=1).weeks[0].week_of == MONDAY
        assert len(_ledger(weeks=1).weeks) == 1

    def test_term_change_moves_the_expectation_and_the_goal_together(self):
        by_monday = {w.week_of: w for w in _ledger().weeks}
        old, new = by_monday[_monday(3)], by_monday[SECOND_TERM]
        assert (old.contract_expected, old.effective_goal) == (25.2, 25.2)
        assert (new.contract_expected, new.effective_goal) == (33.6, 33.6)
        assert new.effective_goal_type is GoalType.TARGET
        assert new.effective_goal_overridden is False

    def test_closing_balances_by_hand(self):
        # Opening 2 h; six weeks at +4.8 (30 worked against 25.2), one at −3.6
        # (30 against 33.6), the vacation week carried, the open week not
        # closed, and nothing before the first term.
        closing = [w.balance_end for w in _ledger().weeks]
        assert closing == [None, 27.2, 27.2, 30.8, 26.0, 21.2, 16.4, 11.6, 6.8, None]

    def test_full_vacation_week_expects_nothing_and_carries_the_balance(self):
        vacation, before = _ledger().weeks[1:3]
        assert vacation.week_of == VACATION
        assert vacation.contract_expected == 0  # owed nothing, as distinct from None
        assert vacation.worked == 0
        assert vacation.balance_end == before.balance_end

    def test_week_before_the_first_term_has_the_personal_goal_and_no_contract_figures(self):
        earliest = _ledger(_day_job(_contract(), weekly_goal=5)).weeks[-1]
        assert earliest.week_of < FIRST_TERM
        assert (earliest.contract_expected, earliest.balance_end) == (None, None)
        assert earliest.effective_goal == 5
        assert earliest.worked == 0

    def test_current_week_is_open(self):
        current = _ledger().weeks[0]
        assert current.week_of == MONDAY
        assert current.balance_end is None
        assert current.contract_expected == 33.6
        assert current.days == [6, 6, 3, 0, 0, 0, 0]
        assert current.worked == 15

    def test_each_closing_balance_moves_by_that_weeks_difference(self):
        # The row-to-row proof: balance(this week) − balance(the week before)
        # is worked − expected, to the cent, on every pair that has both.
        weeks = _ledger().weeks
        pairs = [
            (a, b)
            for a, b in pairwise(weeks)
            if a.balance_end is not None and b.balance_end is not None
        ]
        assert len(pairs) == 7
        for week, before in pairs:
            assert week.contract_expected is not None
            assert week.balance_end - before.balance_end == pytest.approx(
                week.worked - week.contract_expected, abs=0.01
            )

    def test_a_term_starting_mid_week_closes_its_first_partial_week(self):
        # First term from Wednesday 7 January. The week has an expectation
        # (three days at 5.04) and so a closing balance; both count from the
        # Wednesday, while `worked` shows every hour logged — Monday's and
        # Tuesday's 6 h are shown and charged nothing. The week before has
        # neither figure, and the next moves by its own worked − expected.
        wednesday = FIRST_TERM + timedelta(days=2)
        ledger = _ledger(_day_job(_contract(_term(wednesday, 0.6), _term(SECOND_TERM, 0.8))))
        by_monday = {w.week_of: w for w in ledger.weeks}
        first = by_monday[FIRST_TERM]
        assert ledger.since == wednesday
        assert first.contract_expected == pytest.approx(15.12)
        assert first.worked == 30
        assert first.balance_end == pytest.approx(OPENING + 18 - 15.12)
        before = by_monday[FIRST_TERM - timedelta(weeks=1)]
        assert (before.contract_expected, before.balance_end) == (None, None)
        second = by_monday[FIRST_TERM + timedelta(weeks=1)]
        assert second.balance_end == pytest.approx(first.balance_end + 30 - 25.2)

    def test_a_term_starting_on_saturday_leaves_its_week_before_the_contract(self):
        # The same rule for both figures: no weekday owes, so no expectation
        # and no closing balance — but the Saturday's hours count, and move
        # the next week's close.
        saturday = FIRST_TERM + timedelta(days=5)
        worked = {**_worked(), saturday: 2.0}
        ledger = _ledger(
            _day_job(_contract(_term(saturday, 0.6), _term(SECOND_TERM, 0.8))), worked=worked
        )
        by_monday = {w.week_of: w for w in ledger.weeks}
        first = by_monday[FIRST_TERM]
        assert (first.contract_expected, first.balance_end, first.worked) == (None, None, 32)
        assert by_monday[FIRST_TERM + timedelta(weeks=1)].balance_end == pytest.approx(
            OPENING + 2 + 30 - 25.2
        )

    def test_sunday_hours_close_with_their_own_week(self):
        # 3 h on Sunday 22 February and nothing else: the week ending that
        # Sunday moves by 3 − 33.6, the one after by −33.6 alone. The close
        # is through Sunday, not Saturday, and not into Monday.
        sunday = SECOND_TERM + timedelta(days=6)
        ledger = _ledger(absences=[], worked={sunday: 3.0})
        by_monday = {w.week_of: w for w in ledger.weeks}
        week, before, after = (
            by_monday[SECOND_TERM],
            by_monday[SECOND_TERM - timedelta(weeks=1)],
            by_monday[SECOND_TERM + timedelta(weeks=1)],
        )
        assert (week.worked, week.days[6]) == (3, 3)
        assert week.balance_end - before.balance_end == pytest.approx(3 - 33.6)
        assert after.balance_end - week.balance_end == pytest.approx(-33.6)


class TestLedgerTotals:
    def test_totals_are_the_balance_as_of_today_with_its_terms(self):
        ledger = _ledger()
        assert ledger.since == FIRST_TERM
        assert ledger.totals is not None
        # Through Wednesday: six weeks at 25.2, one at 33.6, none on vacation,
        # three days at 6.72. Worked: 7 × 30 h + 15 h this week.
        assert ledger.totals.expected == pytest.approx(204.96)
        assert ledger.totals.worked == 225
        assert ledger.totals.balance == pytest.approx(22.04)
        # And the last closed week plus this week's days lands on it.
        assert ledger.weeks[1].balance_end + 15 - 3 * 6.72 == pytest.approx(22.04)

    def test_opening_plus_worked_minus_expected_is_the_balance_to_the_cent(self):
        # Odd fractions, so each rounded term differs from its raw value:
        # 7 h 47 m and 5 h 23 m against 6.72 h days.
        worked = {_monday(1): 7 + 47 / 60, _monday(1) + timedelta(days=1): 5 + 23 / 60}
        totals = _ledger(absences=[], worked=worked).totals
        assert totals is not None
        assert OPENING + totals.worked - totals.expected == pytest.approx(totals.balance, abs=0.01)


class TestLedgerEndedOn:
    def test_weeks_after_the_end_repeat_the_final_balance(self):
        # Ended on Wednesday 18 February, read three weeks later. The week it
        # ended in owes Monday to Wednesday (20.16) and counts the hours
        # through Wednesday (18), though `worked` shows all 30 logged; it
        # closes at 30.8 + 18 − 20.16. The weeks after owe nothing (0, not
        # None: the term still governs) and their hours no longer count, so
        # every later row shows the same final figure — and so does today's.
        ended = _contract(ended_on=SECOND_TERM + timedelta(days=2))
        ledger = _ledger(_day_job(ended), absences=[], today=TODAY + timedelta(weeks=1), weeks=4)
        by_monday = {w.week_of: w for w in ledger.weeks}
        final = pytest.approx(28.64)
        last = by_monday[SECOND_TERM]
        assert (last.contract_expected, last.worked) == (pytest.approx(20.16), 30)
        assert last.balance_end == final
        after = by_monday[SECOND_TERM + timedelta(weeks=1)]
        assert (after.contract_expected, after.worked, after.balance_end) == (0, 0, final)
        worked_after = by_monday[MONDAY]
        assert (worked_after.worked, worked_after.balance_end) == (15, final)
        assert ledger.totals is not None
        assert (ledger.totals.worked, ledger.totals.expected, ledger.totals.balance) == (
            198,
            pytest.approx(171.36),
            final,
        )


class TestLedgerUngoverned:
    def test_objective_term_has_the_personal_goal_and_no_balance(self):
        objective = Contract(
            terms=[ContractTerm(effective_from=FIRST_TERM, schedule_type=ScheduleType.OBJECTIVE)]
        )
        ledger = _ledger(_day_job(objective, weekly_goal=5), absences=[])
        assert ledger.since == FIRST_TERM
        assert ledger.totals is None
        assert all((w.contract_expected, w.balance_end) == (None, None) for w in ledger.weeks)
        assert all(w.effective_goal == 5 for w in ledger.weeks)
        assert ledger.weeks[0].worked == 15

    @pytest.mark.parametrize(
        "project",
        [
            Project(
                id="p1",
                name="Side",
                weekly_goal=5,
                goal_overrides=[GoalOverride(week_of=VACATION, weekly_goal=None)],
            ),
            Project(
                id="p1",
                name="Job, no contract yet",
                kind=ProjectKind.DAY_JOB,
                weekly_goal=5,
                goal_overrides=[GoalOverride(week_of=VACATION, weekly_goal=None)],
            ),
        ],
        ids=["side project", "day job without a contract"],
    )
    def test_without_a_contract_only_the_goal_and_the_hours_remain(self, project):
        ledger = _ledger(project, absences=[])
        assert (ledger.since, ledger.totals) == (None, None)
        assert all((w.contract_expected, w.balance_end) == (None, None) for w in ledger.weeks)
        current, overridden = ledger.weeks[:2]
        assert (current.effective_goal, current.effective_goal_overridden) == (5, False)
        assert (overridden.effective_goal, overridden.effective_goal_overridden) == (None, True)
        assert current.worked == 15
        assert all(w.notes == [] for w in ledger.weeks)


class TestLedgerNotes:
    def test_notes_are_the_weekdays_absences_and_holidays_of_their_week(self):
        monday, tuesday = SECOND_TERM, SECOND_TERM + timedelta(days=1)
        saturday, sunday = SECOND_TERM + timedelta(days=5), SECOND_TERM + timedelta(days=6)
        ledger = _ledger(
            holidays={monday: "Fasnacht", saturday: "A Saturday holiday"},
            absences=[
                Absence(project_id="p1", date=tuesday, type=AbsenceType.SICK, half_day=True),
                Absence(project_id="p1", date=sunday, type=AbsenceType.VACATION),
            ],
        )
        by_monday = {w.week_of: w for w in ledger.weeks}
        week = by_monday[SECOND_TERM]
        assert week.notes == [
            LedgerNote(date=monday, kind=LedgerNoteKind.HOLIDAY, name="Fasnacht"),
            LedgerNote(date=tuesday, kind=LedgerNoteKind.SICK, half_day=True),
        ]
        # A day off and a half day, off 33.6.
        assert week.contract_expected == pytest.approx(33.6 - 6.72 - 3.36)
        # The weekend's two changed nothing and are not noted; the neighbours
        # carry nothing of this week's.
        assert by_monday[SECOND_TERM + timedelta(weeks=1)].notes == []
        assert by_monday[SECOND_TERM - timedelta(weeks=1)].notes == []
