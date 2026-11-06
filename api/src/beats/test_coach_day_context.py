"""The day context — the one read the brief and the chat share.

Split out of `test_coach.py` at the ceiling in roadmaps/file-sizes.md;
the shared fakes and factories are `coach_fakes.py`'s.
"""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from beats.coach import context as context_module
from beats.coach.contract_section import HEADER as CONTRACT_HEADER
from beats.coach.contract_section import describe_balance
from beats.coach_fakes import (
    CONTRACT_MONDAY,
    CONTRACT_NOW,
    CONTRACT_TODAY,
    ZURICH,
    _contract_job,
    _fake_coach_repos,
    _FakeAbsenceStoreForCoach,
    _FakeAdjustmentStoreForCoach,
    _FakeBeatRepoForTools,
    _FakeProjectRepoForTools,
    _project,
)
from beats.infrastructure.database import Database
from beats.settings import settings


class TestBuildDayContext:
    """build_day_context renders today's signals (beats, calendar,
    biometrics) into the small per-turn context block that's
    prepended to chat / brief prompts.

    Why test directly: existing tests stub this whole function out,
    leaving 130+ lines (38% of context.py) uncovered. A regression
    in any branch would silently degrade the LLM's per-turn input
    and the chat coach would drift further from the user's actual
    state without any test failure.

    Most assertions use `target_date` to avoid wall-clock dependency.
    Database is needed because the calendar + biometric blocks
    query Mongo directly; both are wrapped in try/except so a
    missing testcontainer would degrade gracefully — but we
    connect anyway to exercise the bio block on success."""

    @pytest.fixture(autouse=True)
    async def _setup(self):
        await Database.connect(settings.db_dsn, settings.db_name)
        # Clean any stale biometric / calendar docs from prior tests
        db = Database.get_db()
        await db.biometric_days.delete_many({})
        await db.calendar_integrations.delete_many({})
        yield
        await Database.disconnect()

    async def test_empty_data_renders_headers_with_empty_state(self):
        """No beats / calendar / biometrics → the section headers
        still render with documented empty-state lines. Pin so a
        coach turn on a first-day account doesn't crash on missing
        keys."""
        target = datetime.now(UTC).date()
        repos = _fake_coach_repos()
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        assert f"## Today: {target.isoformat()}" in out
        assert "### Yesterday's sessions" in out
        assert "No sessions yesterday." in out
        assert "### Today's sessions so far" in out
        assert "No sessions today." in out
        # Calendar + biometric sections are omitted when empty
        assert "### Calendar today" not in out
        assert "### Last night's biometrics" not in out

    async def test_today_beats_render_with_time_project_and_duration(self):
        """A beat that started today renders as
        `  HH:MM — ProjectName (Xm)` with a totals line.
        Pin the format so the coach's "today so far" prompt
        block is stable."""
        from beats.domain.models import Beat

        target = datetime.now(UTC).date()
        s = datetime.combine(target, datetime.min.time(), tzinfo=UTC).replace(hour=9)
        beat = Beat(
            id="b1",
            project_id="p1",
            start=s,
            end=s + timedelta(minutes=45),
        )
        repos = _fake_coach_repos(
            projects=[_project("p1", "Alpha")],
            beats=[beat],
        )
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        assert "09:00 — Alpha (45m)" in out
        # Totals line: 45/60 = 0.75h, rounded to 0.8h via :.1f
        assert "Total: 0.8h across 1 sessions" in out

    async def test_buckets_beats_by_local_timezone_not_utc(self):
        """A session whose UTC date differs from the user's local date is
        bucketed by the LOCAL calendar day (tz-aware), matching analytics.
        2026-01-01T23:30Z is 2026-01-02 08:30 in Tokyo, so for a Tokyo user
        whose 'today' is 2026-01-02 it's a TODAY session and renders at its
        LOCAL time; under UTC the same session is not today."""
        from datetime import date as date_type
        from zoneinfo import ZoneInfo

        from beats.domain.models import Beat

        s = datetime(2026, 1, 1, 23, 30, tzinfo=UTC)
        beat = Beat(id="b1", project_id="p1", start=s, end=s + timedelta(minutes=30))
        repos = _fake_coach_repos(projects=[_project("p1", "Alpha")], beats=[beat])

        tokyo = await context_module.build_day_context(
            "user-1", repos, target_date=date_type(2026, 1, 2), tz=ZoneInfo("Asia/Tokyo")
        )
        today_section = tokyo.split("### Today's sessions so far")[1]
        assert "08:30 — Alpha" in today_section  # local Tokyo wall-clock, under today

        utc = await context_module.build_day_context(
            "user-1", repos, target_date=date_type(2026, 1, 2), tz=ZoneInfo("UTC")
        )
        assert "No sessions today." in utc.split("### Today's sessions so far")[1]

    async def test_yesterday_beats_render_separately_from_today(self):
        """Yesterday's beats land under "### Yesterday's sessions"
        — pin so the coach can compare day-to-day rather than
        confuse them. A beat from yesterday must not appear in
        the today section."""
        from beats.domain.models import Beat

        target = datetime.now(UTC).date()
        yesterday = target - timedelta(days=1)
        s = datetime.combine(yesterday, datetime.min.time(), tzinfo=UTC).replace(hour=14)
        beat = Beat(
            id="b1",
            project_id="p1",
            start=s,
            end=s + timedelta(minutes=60),
        )
        repos = _fake_coach_repos(
            projects=[_project("p1", "Alpha")],
            beats=[beat],
        )
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        # Split on the today header to verify the beat is in
        # yesterday's section, not today's
        yesterday_block, _, today_block = out.partition("### Today's sessions so far")
        assert "14:00 — Alpha (1h 0m)" in yesterday_block
        assert "Alpha" not in today_block

    async def test_beat_with_note_renders_note_suffix(self):
        """A beat with .note set renders as `... [note: <note>]`.
        Pin so the LLM sees per-session annotations the user wrote."""
        from beats.domain.models import Beat

        target = datetime.now(UTC).date()
        s = datetime.combine(target, datetime.min.time(), tzinfo=UTC).replace(hour=10)
        beat = Beat(
            id="b1",
            project_id="p1",
            start=s,
            end=s + timedelta(minutes=30),
            note="deep work",
        )
        repos = _fake_coach_repos(
            projects=[_project("p1", "Alpha")],
            beats=[beat],
        )
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        assert "[note: deep work]" in out

    async def test_biometric_block_renders_when_doc_exists(self):
        """A biometric_days doc for yesterday → renders the
        sleep/HRV/HR/readiness block. Pin all four field
        formatters so a regression doesn't drop one. The block
        is hidden entirely if no fields are populated."""
        target = datetime.now(UTC).date()
        yesterday = target - timedelta(days=1)
        db = Database.get_db()
        await db.biometric_days.insert_one(
            {
                "user_id": "user-1",
                "date": yesterday.isoformat(),
                "sleep_minutes": 480,
                "sleep_efficiency": 0.92,
                "hrv_ms": 45,
                "resting_hr_bpm": 58,
                "readiness_score": 88,
                "created_at": datetime.now(UTC),
            }
        )
        repos = _fake_coach_repos()
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        assert "### Last night's biometrics" in out
        # 480 min / 60 = 8.0h
        assert "Sleep: 8.0h (efficiency 92%)" in out
        assert "HRV: 45ms" in out
        assert "Resting HR: 58 bpm" in out
        assert "Readiness: 88/100" in out

    async def test_biometric_block_omitted_when_no_fields_populated(self):
        """A biometric_days doc with all biometric fields None
        (e.g. a placeholder row) → block is omitted, NOT rendered
        with empty values. Pin so a coach turn doesn't include
        a half-empty biometric section."""
        target = datetime.now(UTC).date()
        yesterday = target - timedelta(days=1)
        db = Database.get_db()
        await db.biometric_days.insert_one(
            {
                "user_id": "user-1",
                "date": yesterday.isoformat(),
                "sleep_minutes": None,
                "hrv_ms": None,
                "resting_hr_bpm": None,
                "readiness_score": None,
                "created_at": datetime.now(UTC),
            }
        )
        repos = _fake_coach_repos()
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        assert "### Last night's biometrics" not in out

    async def test_biometric_block_partial_fields_only_renders_present(self):
        """Only sleep_minutes set → biometric block renders just
        the Sleep line. Pin so a partial day's data still surfaces
        what's available."""
        target = datetime.now(UTC).date()
        yesterday = target - timedelta(days=1)
        db = Database.get_db()
        await db.biometric_days.insert_one(
            {
                "user_id": "user-1",
                "date": yesterday.isoformat(),
                "sleep_minutes": 420,
                "sleep_efficiency": None,  # no efficiency suffix
                "created_at": datetime.now(UTC),
            }
        )
        repos = _fake_coach_repos()
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        assert "Sleep: 7.0h" in out
        # No efficiency suffix
        assert "(efficiency" not in out
        # Other lines absent
        assert "HRV:" not in out
        assert "Resting HR:" not in out
        assert "Readiness:" not in out

    async def test_unknown_project_resolves_to_question_mark(self):
        """Beat references a project_id not in the project list
        (project deleted between session and prompt build) →
        renders as "? (Xm)" rather than crashing on KeyError."""
        from beats.domain.models import Beat

        target = datetime.now(UTC).date()
        s = datetime.combine(target, datetime.min.time(), tzinfo=UTC).replace(hour=11)
        beat = Beat(
            id="b1",
            project_id="ghost",
            start=s,
            end=s + timedelta(minutes=30),
        )
        repos = _fake_coach_repos(projects=[], beats=[beat])
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        assert "11:00 — ? (30m)" in out

    async def test_calendar_block_renders_timed_and_all_day_events(self, monkeypatch):
        """When the user has a connected calendar_integrations doc,
        build_day_context fetches today's events and renders them
        under "### Calendar today". Two event shapes pinned:
          - timed event ("dateTime") → "  HH:MM–HH:MM <summary>"
          - all-day event (only "date") → "  all-day <summary>"

        The previous calendar block had two latent bugs (wrong
        constructor args + wrong method name) that the broad
        except hid — pin so a regression in the inline import
        chain or the events-shape parsing surfaces."""
        from beats.domain import calendar as calendar_module

        # Seed an enabled calendar integration so the cal_doc lookup
        # passes — we don't care about its fields beyond enabled=True
        # because we mock fetch_events to short-circuit the HTTP call
        db = Database.get_db()
        await db.calendar_integrations.insert_one(
            {
                "user_id": "user-1",
                "provider": "google",
                "access_token": "ya29",
                "refresh_token": "rt",
                "enabled": True,
                "calendar_ids": ["primary"],
            }
        )

        async def fake_fetch_events(self, start, end):
            return [
                {
                    "summary": "Standup",
                    "start": "2026-04-01T09:00:00Z",
                    "end": "2026-04-01T09:30:00Z",
                    "all_day": False,
                },
                {
                    "summary": "Holiday",
                    "start": "2026-04-01",
                    "end": "2026-04-02",
                    "all_day": True,
                },
            ]

        monkeypatch.setattr(calendar_module.CalendarService, "fetch_events", fake_fetch_events)

        target = date(2026, 4, 1)
        repos = _fake_coach_repos()
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        assert "### Calendar today" in out
        # Timed event: HH:MM–HH:MM extracted from RFC3339
        assert "  09:00–09:30 Standup" in out
        # All-day event: "  all-day <summary>"
        assert "  all-day Holiday" in out

    async def test_calendar_reads_the_users_day_on_the_users_clock(self, monkeypatch):
        """The window asked of the calendar is the user's local day, with its
        offset: Google refuses a naive timeMin with a 400, which fetch_events'
        per-calendar except turned into no calendar at all, and a naive
        midnight was UTC's day besides. An event Google writes in another zone reads on the
        user's clock."""
        from beats.domain import calendar as calendar_module

        db = Database.get_db()
        await db.calendar_integrations.insert_one(
            {
                "user_id": "user-1",
                "provider": "google",
                "access_token": "ya29",
                "refresh_token": "rt",
                "enabled": True,
                "calendar_ids": ["primary"],
            }
        )
        windows: list[tuple[datetime, datetime]] = []

        async def fake_fetch_events(self, start, end):
            windows.append((start, end))
            return [
                {
                    "summary": "Standup",
                    "start": "2026-04-01T07:00:00Z",
                    "end": "2026-04-01T07:30:00Z",
                    "all_day": False,
                },
            ]

        monkeypatch.setattr(calendar_module.CalendarService, "fetch_events", fake_fetch_events)

        tz = ZoneInfo("Europe/Zurich")
        repos = _fake_coach_repos()
        out = await context_module.build_day_context(
            "user-1", repos, target_date=date(2026, 4, 1), tz=tz
        )
        [(start, end)] = windows
        assert start.utcoffset() is not None
        assert end.utcoffset() is not None
        # Zürich's 1 April, CEST: 22:00 UTC the day before to 22:00 UTC.
        assert start == datetime(2026, 3, 31, 22, 0, tzinfo=UTC)
        assert end.astimezone(tz).date() == date(2026, 4, 1)
        assert datetime(2026, 4, 1, 21, 59, tzinfo=UTC) < end < datetime(2026, 4, 1, 22, tzinfo=UTC)
        assert "  09:00–09:30 Standup" in out

    async def test_calendar_block_omitted_when_fetch_raises(self, monkeypatch):
        """If CalendarService.fetch_events raises (revoked OAuth,
        network down, expired token), the broad except in
        build_day_context swallows it and the calendar block is
        silently omitted. Pin so the day-context generator stays
        best-effort — a flaky calendar must NOT break the coach
        prompt for unrelated features."""
        from beats.domain import calendar as calendar_module

        db = Database.get_db()
        await db.calendar_integrations.insert_one(
            {
                "user_id": "user-1",
                "provider": "google",
                "access_token": "ya29",
                "refresh_token": "rt",
                "enabled": True,
                "calendar_ids": ["primary"],
            }
        )

        async def fake_fetch_events(self, start, end):
            raise RuntimeError("calendar quota exhausted")

        monkeypatch.setattr(calendar_module.CalendarService, "fetch_events", fake_fetch_events)

        target = date(2026, 4, 1)
        repos = _fake_coach_repos()
        out = await context_module.build_day_context("user-1", repos, target_date=target)
        # Calendar header is omitted (fetch threw, except branch hit)
        assert "### Calendar today" not in out
        # The rest of the day context still renders
        assert "## Today: 2026-04-01" in out

    async def test_an_unreadable_event_time_skips_that_event_alone(self, monkeypatch):
        """AHM-85. A dateTime fromisoformat refuses lost the whole calendar
        block. Now that event is skipped, and the five that print are the
        first five readable ones, so the bad one takes no good one's place."""
        from beats.domain import calendar as calendar_module

        db = Database.get_db()
        await db.calendar_integrations.insert_one(
            {
                "user_id": "user-1",
                "provider": "google",
                "access_token": "ya29",
                "refresh_token": "rt",
                "enabled": True,
                "calendar_ids": ["primary"],
            }
        )

        def event(summary, hour):
            return {
                "summary": summary,
                "start": f"2026-04-01T{hour:02}:00:00Z",
                "end": f"2026-04-01T{hour:02}:30:00Z",
                "all_day": False,
            }

        async def fake_fetch_events(self, start, end):
            garbled = {**event("Garbled", 8), "start": "2026-04-01Tnine o'clock"}
            return [garbled, *(event(f"Meeting {n}", 9 + n) for n in range(5))]

        monkeypatch.setattr(calendar_module.CalendarService, "fetch_events", fake_fetch_events)

        repos = _fake_coach_repos()
        out = await context_module.build_day_context("user-1", repos, target_date=date(2026, 4, 1))

        assert "Garbled" not in out
        for n in range(5):
            assert f"  {9 + n:02}:00–{9 + n:02}:30 Meeting {n}" in out

    # The contract section. The clock is the contract service's (CONTRACT_NOW,
    # Thursday 28 May in Zürich), and every positive test passes that day as
    # `target_date` with the Zürich timezone.

    @staticmethod
    @staticmethod
    def _work(day: date, hours: float, *, at: int = 9):
        """A finished session on the job, starting at `at` o'clock in Zürich."""
        from datetime import time

        from beats.domain.models import Beat

        start = datetime.combine(day, time(at), tzinfo=ZURICH).astimezone(UTC)
        return Beat(
            id=f"w-{day}-{at}", project_id="job", start=start, end=start + timedelta(hours=hours)
        )

    @staticmethod
    def _off(day: date, *, half_day=False, type_="vacation", note=None):
        from beats.domain.models import Absence, AbsenceType

        return Absence(
            project_id="job", date=day, half_day=half_day, type=AbsenceType(type_), note=note
        )

    async def _day_context(self, *, target=CONTRACT_TODAY, **repos) -> str:
        return await context_module.build_day_context(
            "user-1", _fake_coach_repos(**repos), target_date=target, tz=ZURICH
        )

    def _week_beats(self):
        """38 h the week before (7.6 h a weekday, against 40), then 9 h on
        Tuesday, 8.5 h on Wednesday and 3 h this morning."""
        before = [self._work(date(2026, 5, 18) + timedelta(days=n), 7.6) for n in range(5)]
        return [
            *before,
            self._work(date(2026, 5, 26), 9),
            self._work(date(2026, 5, 27), 8.5),
            self._work(CONTRACT_TODAY, 3, at=8),
        ]

    async def test_contract_week_after_holiday_and_day_off(self):
        """40 h a week, Pentecost Monday off and Friday booked off: the week
        expects 24 h, not 40, and 20.5 h of it is worked. The balance is
        1.6 opening − 2 h last week + 4.5 h this week, and the project page's
        week route says the same."""
        from beats.domain.contract_service import ContractService

        job = _contract_job(opening=1.6)
        beats = self._week_beats()
        absences = [self._off(date(2026, 5, 29))]
        out = await self._day_context(projects=[job], beats=beats, absences=absences)

        section = out.split(CONTRACT_HEADER)[1]
        assert section.splitlines()[1:7] == [
            "  Acme (contract): this week expects 24.0 h after holidays and days off"
            " — 20.5 h worked, 3.5 h to go",
            "    Mon 2026-05-25: public holiday (Pentecost Monday)",
            "    Fri 2026-05-29: day off",
            "  Acme today: 8.0 h expected (charged to the balance tomorrow)",
            "  Acme running balance: +4.1 h over",
            "  Acme by Sunday: −3.9 h owed if you stop now,"
            " −0.4 h owed if the rest of the week is met",
        ]
        page = await ContractService(
            project_repo=_FakeProjectRepoForTools([job]),
            beat_repo=_FakeBeatRepoForTools(beats),
            absence_repo=_FakeAbsenceStoreForCoach(absences),
            adjustment_repo=_FakeAdjustmentStoreForCoach([]),
            now=lambda tz: CONTRACT_NOW.astimezone(tz),
        ).week("job", None, ZURICH)
        assert page.balance is not None
        assert f"running balance: {describe_balance(page.balance)}" in section

    async def test_contract_balance_counts_an_adjustment_as_the_page_does(self):
        """A 3 h payout last Monday takes the running balance from +4.1 h to
        +1.1 h, and both by-Sunday figures with it, exactly as the project
        page's week route reads it. The adjustment's kind and note are not
        sent: only the balance it moved."""
        from beats.domain.contract_service import ContractService
        from beats.domain.models import AdjustmentKind, BalanceAdjustment

        job = _contract_job(opening=1.6)
        beats = self._week_beats()
        absences = [self._off(date(2026, 5, 29))]
        payout = BalanceAdjustment(
            project_id="job",
            date=date(2026, 5, 18),
            kind=AdjustmentKind.DELTA,
            hours=-3,
            note="paid out in May's salary",
        )
        out = await self._day_context(
            projects=[job], beats=beats, absences=absences, adjustments=[payout]
        )

        section = out.split(CONTRACT_HEADER)[1]
        assert "  Acme running balance: +1.1 h over" in section.splitlines()
        assert (
            "  Acme by Sunday: −6.9 h owed if you stop now,"
            " −3.4 h owed if the rest of the week is met"
        ) in section.splitlines()
        page = await ContractService(
            project_repo=_FakeProjectRepoForTools([job]),
            beat_repo=_FakeBeatRepoForTools(beats),
            absence_repo=_FakeAbsenceStoreForCoach(absences),
            adjustment_repo=_FakeAdjustmentStoreForCoach([payout]),
            now=lambda tz: CONTRACT_NOW.astimezone(tz),
        ).week("job", None, ZURICH)
        assert page.balance is not None
        assert page.balance_adjusted == -3
        assert f"running balance: {describe_balance(page.balance)}" in section
        assert "paid out" not in out
        assert "delta" not in out.lower()

    async def test_contract_section_sends_no_absence_type_note_region_or_company_name(self):
        """What PRIVACY.md promises stays home: a sick day with a note reads
        "day off", a company holiday reads "company holiday" without the name
        the user typed, and neither the region's codes nor the opening
        balance as a figure of its own appear anywhere in the day context."""
        job = _contract_job(opening=1.6, company=[(date(2026, 5, 27), "Founders' picnic at Lake")])
        absences = [self._off(date(2026, 5, 29), type_="sick", note="flu")]
        out = await self._day_context(projects=[job], beats=self._week_beats(), absences=absences)

        assert "    Wed 2026-05-27: company holiday" in out
        assert "    Fri 2026-05-29: day off" in out
        for secret in ("Founders", "picnic", "sick", "flu", "CH", "ZH", "1.6"):
            assert secret not in out

    async def test_worked_and_to_go_are_the_pages_on_a_half_way_hundredth(self):
        """8 h 32 m 42 s is 8.545 h. The week route rounds worked to 8.54 and
        remaining to 31.45, each on its own, and the page shows them as 8.5
        and 31.4 h, which make 39.9 against 40.0. The coach says what the
        page says, not the 8.55 it read back off the other two, nor a 31.5
        that would add up."""
        from beats.domain.contract_service import ContractService

        job = _contract_job(region=None)
        beats = [self._work(date(2026, 5, 26), 30762 / 3600)]
        page = await ContractService(
            project_repo=_FakeProjectRepoForTools([job]),
            beat_repo=_FakeBeatRepoForTools(beats),
            absence_repo=_FakeAbsenceStoreForCoach([]),
            adjustment_repo=_FakeAdjustmentStoreForCoach([]),
            now=lambda tz: CONTRACT_NOW.astimezone(tz),
        ).week("job", None, ZURICH)
        out = await self._day_context(projects=[job], beats=beats)

        assert (page.expected, page.worked, page.remaining) == (40.0, 8.54, 31.45)
        assert (
            "this week expects 40.0 h after holidays and days off"
            " — 8.5 h worked, 31.4 h to go\n" in out
        )

    async def test_on_a_contracts_first_day_the_balance_is_the_opening_balance(self):
        """PRIVACY.md says the opening balance is not sent as a figure of its
        own but the running balance sums it: with nothing worked yet and
        nothing charged yet, the one is the other, and the end date this
        week is listed."""
        job = _contract_job(
            starts=CONTRACT_TODAY, region=None, opening=12.5, ended_on=date(2026, 5, 29)
        )
        out = await self._day_context(projects=[job])

        assert "  Acme running balance: +12.5 h over" in out.splitlines()
        assert "  Acme: contract ends 2026-05-29" in out.splitlines()

    async def test_by_sunday_charges_today_and_the_rest_of_the_week(self):
        """The bare balance counts this morning's 4 h but not today's 8 h, so
        it reads +4.0 (last week was met to the hour). Stopping now owes
        today and Friday: −12.0. Meeting the week works off exactly that."""
        job = _contract_job(region=None)
        beats = [
            *(self._work(date(2026, 5, 18) + timedelta(days=n), 8) for n in range(5)),
            *(self._work(CONTRACT_MONDAY + timedelta(days=n), 8) for n in range(3)),
            self._work(CONTRACT_TODAY, 4, at=7),
        ]
        out = await self._day_context(projects=[job], beats=beats)

        assert "  Acme running balance: +4.0 h over" in out
        assert (
            "  Acme by Sunday: −12.0 h owed if you stop now, even if the rest of the week is met"
            in out
        )

    @pytest.mark.parametrize(
        ("starts", "first_week"),
        [
            (CONTRACT_MONDAY, True),
            # Friday to Thursday is still the first seven days, across two
            # calendar weeks, as the page counts them; from Thursday it is not.
            (date(2026, 5, 22), True),
            (date(2026, 5, 21), False),
        ],
    )
    async def test_the_first_week_says_so_in_place_of_the_projection(self, starts, first_week):
        """The page shows "First week under the contract." and no by-Sunday
        projection for the first seven days from the contract's first term:
        the balance has not had a full week to settle. So does the coach."""
        job = _contract_job(starts=starts, region=None)
        out = await self._day_context(projects=[job], beats=[self._work(CONTRACT_TODAY, 4)])

        assert "  Acme running balance:" in out
        said = (
            "  Acme: first week under the contract — each day is charged as it closes,"
            " and the balance settles once a full week is in"
        )
        assert (said in out.splitlines()) is first_week
        assert ("Acme by Sunday:" in out) is not first_week

    @pytest.mark.parametrize(
        ("today_hours", "left"),
        [
            (7.0, "1.0 h to go"),
            (8.04, "week met"),  # −0.04 h left rounds to the 0.0 shown
            (8.4, "week done, 0.4 h over"),
        ],
    )
    async def test_what_is_left_is_judged_at_the_decimal_shown(self, today_hours, left):
        job = _contract_job(starts=CONTRACT_MONDAY, region=None)
        beats = [
            *(self._work(CONTRACT_MONDAY + timedelta(days=n), 8) for n in range(3)),
            self._work(CONTRACT_TODAY, today_hours, at=1),
        ]
        absences = [self._off(date(2026, 5, 29))]  # Mon–Thu expect 32 h
        out = await self._day_context(projects=[job], beats=beats, absences=absences)

        assert f" h worked, {left}\n" in out

    async def test_contract_starting_mid_week_counts_only_its_own_days(self):
        """Starting on Wednesday: worked is the page's, the whole week's 24 h,
        but the 10 h tracked Monday and Tuesday are not under the contract,
        so 10 h are still to go of its 24 h, and a note says why. The
        holiday before the start shortened nothing and is not listed."""
        job = _contract_job(starts=date(2026, 5, 27))
        beats = [
            self._work(date(2026, 5, 25), 5),
            self._work(date(2026, 5, 26), 5),
            self._work(date(2026, 5, 27), 8),
            self._work(CONTRACT_TODAY, 6, at=1),
        ]
        out = await self._day_context(projects=[job], beats=beats)

        assert (
            "this week expects 24.0 h after holidays and days off"
            " — 24.0 h worked, 10.0 h to go (the contract counts only its own days this week)"
            in out
        )
        assert "Pentecost" not in out

    async def test_week_is_labelled_by_mondays_term_as_the_goal_line_is(self):
        """80 % until Tuesday, full-time from Wednesday: the goal line names
        Monday's term, and so does the week's line, not today's."""
        from beats.domain.models import ContractTerm, ScheduleType

        job = _contract_job(region=None)
        assert job.contract is not None
        terms = [
            ContractTerm(
                effective_from=date(2026, 5, 18),
                schedule_type=ScheduleType.PART_TIME,
                full_time_hours=40,
                percentage=0.8,
            ),
            ContractTerm(
                effective_from=date(2026, 5, 27),
                schedule_type=ScheduleType.FULL_TIME,
                full_time_hours=40,
            ),
        ]
        job = job.model_copy(update={"contract": job.contract.model_copy(update={"terms": terms})})
        out = await self._day_context(projects=[job])

        assert "  Acme (contract, 80%): this week expects" in out
        assert "full-time" not in out

    async def test_quarter_hours_read_as_the_page_reads_them(self):
        """23.75 h worked of 40 leaves 16.25 h, and the page shows each at
        the tenth, ties away from zero: 23.8 and 16.3, which make 40.1. The
        coach says the same two figures."""
        job = _contract_job(starts=CONTRACT_MONDAY, region=None)
        beats = [
            self._work(CONTRACT_MONDAY, 7.75),
            *(self._work(CONTRACT_MONDAY + timedelta(days=n), 8) for n in (1, 2)),
        ]
        out = await self._day_context(projects=[job], beats=beats)

        assert (
            "this week expects 40.0 h after holidays and days off"
            " — 23.8 h worked, 16.3 h to go\n" in out
        )

    async def test_only_days_that_shortened_the_week_are_listed(self):
        """A company day on a Saturday owed nothing to begin with; a day off
        booked on the holiday is the holiday, once; a half day says so."""
        job = _contract_job(company=[(date(2026, 5, 30), "Summer party")])
        absences = [self._off(CONTRACT_MONDAY), self._off(date(2026, 5, 26), half_day=True)]
        out = await self._day_context(projects=[job], absences=absences)

        assert out.count("2026-05-25") == 1
        assert "    Mon 2026-05-25: public holiday (Pentecost Monday)" in out
        assert "    Tue 2026-05-26: half day off" in out
        assert "2026-05-30" not in out
        assert "company holiday" not in out

    async def test_contract_that_ended_yesterday_sends_only_its_final_balance(self):
        """Nothing worked from today on counts, so there is nothing "to go"
        and no Sunday to project to: the project page shows "Final balance"
        alone, and so does the section. −2 h the first week, +1 h on
        Tuesday and +0.5 h on Wednesday; this morning's 3 h do not count."""
        job = _contract_job(ended_on=date(2026, 5, 27))
        out = await self._day_context(projects=[job], beats=self._week_beats())

        assert out.split(CONTRACT_HEADER)[1].strip().splitlines() == [
            "Acme final balance: −0.5 h owed (contract ended 2026-05-27)"
        ]
        for live in ("to go", "running balance", "by Sunday", "today:", "contract ends"):
            assert live not in out

    async def test_contract_ending_today_is_still_live(self):
        """On the last day today's hours count and today's 8 h are charged
        tomorrow, so the bare +2.5 h is not where the contract closes: the
        projection is, and the section keeps it. Meeting the week closes at
        last week's −2 h."""
        job = _contract_job(ended_on=CONTRACT_TODAY)
        out = await self._day_context(projects=[job], beats=self._week_beats())

        assert "  Acme running balance: +2.5 h over" in out
        assert (
            "  Acme by Sunday: −5.5 h owed if you stop now, −2.0 h owed if the rest of the"
            " week is met" in out
        )
        assert "  Acme: contract ends 2026-05-28" in out
        assert "final balance" not in out

    @pytest.mark.parametrize(
        "case", ["objective", "side_project", "no_contract", "ended_last_week"]
    )
    async def test_no_section_without_a_live_contract_that_owes_hours(self, case):
        from beats.domain.models import Project, ProjectKind

        project = {
            "objective": lambda: _contract_job(objective=True),
            "side_project": lambda: _project("job", "Acme", weekly_goal=10),
            "no_contract": lambda: Project(id="job", name="Acme", kind=ProjectKind.DAY_JOB),
            "ended_last_week": lambda: _contract_job(ended_on=date(2026, 5, 22)),
        }[case]()
        out = await self._day_context(projects=[project], beats=self._week_beats())

        assert CONTRACT_HEADER not in out

    async def test_no_section_for_a_day_other_than_the_contract_clocks_today(self):
        """A backdated brief: the figures are today's, so none are sent."""
        out = await self._day_context(
            target=CONTRACT_TODAY - timedelta(days=1),
            projects=[_contract_job()],
            beats=self._week_beats(),
        )

        assert CONTRACT_HEADER not in out
        assert "## Today: 2026-05-27" in out

    async def test_failing_contract_read_leaves_the_rest_of_the_day(self):
        class _Broken:
            async def current_weeks(self, projects, tz, as_of):
                raise RuntimeError("mongo went away")

            async def expected_for_week(self, project, week_of):
                raise RuntimeError("mongo went away")

        out = await self._day_context(
            projects=[_contract_job()], beats=self._week_beats(), contracts=_Broken()
        )

        assert CONTRACT_HEADER not in out
        assert "08:00 — Acme (3h 0m)" in out
