"""Brief generation and the briefs read back, the feedback lines, the
formatters, and the contract section as the project page reads it.

Split out of `test_coach.py` at the ceiling in roadmaps/file-sizes.md;
the shared fakes and factories are `coach_fakes.py`'s.
"""

import re
from datetime import UTC, date, datetime, timedelta

import pytest

from beats.coach import brief as brief_module
from beats.coach.contract_section import contract_section, describe_balance
from beats.coach.feedback import brief_feedback_lines
from beats.coach.gateway import (
    GatewayResponse,
)
from beats.coach.repos import (
    DAILY_BRIEFS_COLLECTION,
    fmt_contract_goal,
    fmt_hours,
    fmt_minutes,
)
from beats.coach_fakes import (
    CONTRACT_NOW,
    CONTRACT_TODAY,
    ZURICH,
    _fake_gateway_response,
    _FakeAbsenceStoreForCoach,
    _FakeAdjustmentStoreForCoach,
    _FakeBeatRepoForTools,
    _FakeProjectRepoForTools,
    _text_block,
    _to_fixed_1,
)
from beats.infrastructure.database import Database
from beats.settings import settings


class TestFmtMinutes:
    """fmt_minutes formats a minute count as 'Nh Mm' or 'Mm'.

    Used in the coach's session tables and the day/user context builders.
    Locks in the boundary cases — these are the inputs that matter for
    the coach's per-project hour summaries (a 60-minute session formatting
    as '60m' instead of '1h 0m' would surprise readers, and a fractional
    input formatting as '0h 0m' instead of '0m' would clutter the output).
    """

    def test_zero_minutes(self):
        assert fmt_minutes(0) == "0m"

    def test_under_one_hour(self):
        assert fmt_minutes(15) == "15m"
        assert fmt_minutes(45) == "45m"
        # Boundary — one minute under the hour.
        assert fmt_minutes(59) == "59m"

    def test_exactly_one_hour(self):
        # 60 → "1h 0m", not "60m" — the hour boundary kicks in at >= 60
        # because divmod(60, 60) == (1, 0) and the h>0 branch fires.
        assert fmt_minutes(60) == "1h 0m"

    def test_one_hour_with_remainder(self):
        assert fmt_minutes(61) == "1h 1m"
        assert fmt_minutes(75) == "1h 15m"
        assert fmt_minutes(90) == "1h 30m"

    def test_multiple_hours(self):
        assert fmt_minutes(120) == "2h 0m"
        assert fmt_minutes(125) == "2h 5m"
        assert fmt_minutes(480) == "8h 0m"

    def test_large_value(self):
        # 24h+ — the coach occasionally summarizes across multi-day
        # windows. No special handling for "1d", just keeps counting hours.
        assert fmt_minutes(1500) == "25h 0m"
        assert fmt_minutes(1543) == "25h 43m"

    def test_fractional_input_truncates(self):
        # int() truncates toward zero (per the implementation's
        # divmod(int(minutes), 60)). A 30.7-minute session reads as
        # "30m", not "31m" — pin so a future change to round() is
        # a deliberate decision, not an accident.
        assert fmt_minutes(30.7) == "30m"
        assert fmt_minutes(59.9) == "59m"
        # 60.5 → int → 60 → "1h 0m" (the hour kicks in only AT 60
        # post-truncation, not before).
        assert fmt_minutes(60.5) == "1h 0m"


class TestBriefFeedbackLines:
    """The context section that tells the coach which briefs helped."""

    def test_no_rated_brief_adds_nothing(self):
        assert brief_feedback_lines([{"date": "2026-10-14", "body": "x"}]) == []

    def test_names_each_day_its_rating_and_how_it_opened(self):
        lines = brief_feedback_lines(
            [
                {
                    "date": "2026-10-14",
                    "feedback": "helpful",
                    "body": "**Protect** the morning. Then lunch.",
                },
                {
                    "date": "2026-10-13",
                    "feedback": "not_useful",
                    "body": "## Plan\nYou could work.",
                },
                {"date": "2026-10-12", "feedback": "meh", "body": "ignored"},
            ]
        )
        assert "1 of the last 2 rated briefs helpful" in lines[2]
        assert lines[3] == '  2026-10-14: helpful — opened with "Protect the morning."'
        assert lines[4].startswith("  2026-10-13: not useful — opened with")
        assert len(lines) == 5

    def test_a_long_opening_is_cut(self):
        lines = brief_feedback_lines([{"date": "d", "feedback": "helpful", "body": "word " * 60}])
        assert lines[-1].endswith('…"')


class TestGenerateBrief:
    """generate_brief composes context + calls the gateway + persists.
    Mocks build_coach_messages (the heavy upstream) and complete()
    (the LLM call). Pins what gets stored in daily_briefs and what
    the gateway is called with."""

    @pytest.fixture(autouse=True)
    async def _setup(self):
        await Database.connect(settings.db_dsn, settings.db_name)
        await Database.get_db()[DAILY_BRIEFS_COLLECTION].delete_many({})
        yield
        await Database.disconnect()

    @pytest.fixture
    def patched_gateway(self, monkeypatch):
        """Replace build_coach_messages and complete with deterministic
        fakes; capture the args the gateway was called with so tests
        can assert on prompt shape."""
        captured: dict = {}

        async def fake_build(user_id, prompt, target_date=None, tz=None):
            captured["build_args"] = {
                "user_id": user_id,
                "prompt": prompt,
                "target_date": target_date,
            }
            return ("system text", [{"role": "user", "content": prompt}], None)

        async def fake_complete(**kwargs):
            captured["complete_kwargs"] = kwargs
            return _fake_gateway_response()

        monkeypatch.setattr(brief_module, "build_coach_messages", fake_build)
        monkeypatch.setattr(brief_module, "complete", fake_complete)
        return captured

    async def test_persists_brief_with_full_shape(self, patched_gateway):
        from datetime import date as date_type

        target = date_type(2026, 5, 1)
        doc = await brief_module.generate_brief("user-1", target_date=target)

        # Returned doc has all the fields the API exposes.
        assert doc["user_id"] == "user-1"
        assert doc["date"] == "2026-05-01"
        assert doc["body"] == "Good morning. Two intentions today."
        assert doc["model"] == "claude-opus-4-7"
        assert doc["cost_usd"] == 0.012
        assert doc["input_tokens"] == 1234
        assert doc["output_tokens"] == 89
        assert doc["cache_read"] == 800
        assert "created_at" in doc

        # Persisted to Mongo with the same shape.
        stored = await Database.get_db()[DAILY_BRIEFS_COLLECTION].find_one(
            {"user_id": "user-1", "date": "2026-05-01"}
        )
        assert stored is not None
        assert stored["body"] == "Good morning. Two intentions today."

    async def test_defaults_to_today_when_target_date_omitted(self, patched_gateway):
        await brief_module.generate_brief("user-1")
        today = datetime.now(UTC).date().isoformat()
        # build_coach_messages received today via target_date.
        assert patched_gateway["build_args"]["target_date"].isoformat() == today
        # And the persisted row's date is today.
        stored = await Database.get_db()[DAILY_BRIEFS_COLLECTION].find_one(
            {"user_id": "user-1", "date": today}
        )
        assert stored is not None

    async def test_passes_purpose_brief_to_gateway(self, patched_gateway):
        """Locks the purpose tag so per-purpose usage breakdowns
        keep separating brief from chat. Renaming this would skew
        the cost dashboard."""
        await brief_module.generate_brief("user-1")
        assert patched_gateway["complete_kwargs"]["purpose"] == "brief"

    async def test_passes_user_id_to_gateway(self, patched_gateway):
        """Without this, UsageTracker would count the brief against
        the wrong user."""
        await brief_module.generate_brief("user-99")
        assert patched_gateway["complete_kwargs"]["user_id"] == "user-99"

    async def test_concatenates_multiple_text_blocks(self, monkeypatch):
        """The LLM can return multiple TextBlocks (one per output
        chunk). brief.py concatenates and strips. Pin so a refactor
        that grabs only `content[0].text` doesn't truncate briefs."""

        async def fake_build(user_id, prompt, target_date=None, tz=None):
            return ("sys", [], None)

        async def fake_complete(**_kwargs):
            return GatewayResponse(
                content=[
                    _text_block("First sentence. "),
                    _text_block("Second sentence."),
                ],
                model="claude-opus-4-7",
                input_tokens=10,
                output_tokens=20,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
                cost_usd=0.001,
                stop_reason="end_turn",
            )

        monkeypatch.setattr(brief_module, "build_coach_messages", fake_build)
        monkeypatch.setattr(brief_module, "complete", fake_complete)

        doc = await brief_module.generate_brief("user-1")
        assert doc["body"] == "First sentence. Second sentence."

    async def test_upserts_on_user_and_date(self, patched_gateway):
        """Generating a brief twice for the same date overwrites
        rather than duplicating. Locks the upsert filter — without
        it, get_brief() would non-deterministically return one of
        many rows."""
        from datetime import date as date_type

        target = date_type(2026, 5, 1)
        await brief_module.generate_brief("user-1", target_date=target)
        await brief_module.generate_brief("user-1", target_date=target)

        count = await Database.get_db()[DAILY_BRIEFS_COLLECTION].count_documents(
            {"user_id": "user-1", "date": "2026-05-01"}
        )
        assert count == 1


class TestGetAndListBriefs:
    """The read paths used by /api/coach/brief/today and
    /api/coach/brief/history. Pin: empty result for fresh users,
    descending-by-date for list, _id projection so the API doesn't
    leak ObjectIds."""

    @pytest.fixture(autouse=True)
    async def _setup(self):
        await Database.connect(settings.db_dsn, settings.db_name)
        await Database.get_db()[DAILY_BRIEFS_COLLECTION].delete_many({})
        yield
        await Database.disconnect()

    async def _seed_brief(self, user_id: str, date_str: str, body: str = "x") -> None:
        await Database.get_db()[DAILY_BRIEFS_COLLECTION].insert_one(
            {"user_id": user_id, "date": date_str, "body": body, "model": "x"}
        )

    async def test_get_brief_returns_none_when_missing(self):
        from datetime import date as date_type

        result = await brief_module.get_brief("user-1", target_date=date_type(2026, 5, 1))
        assert result is None

    async def test_get_brief_returns_doc_without_objectid(self):
        from datetime import date as date_type

        await self._seed_brief("user-1", "2026-05-01", "today's brief")
        result = await brief_module.get_brief("user-1", target_date=date_type(2026, 5, 1))
        assert result is not None
        assert result["body"] == "today's brief"
        # ObjectId stripped via the {"_id": 0} projection — important
        # because API responses don't serialize ObjectIds.
        assert "_id" not in result

    async def test_list_briefs_empty_for_fresh_user(self):
        result = await brief_module.list_briefs("user-1")
        assert result == []

    async def test_list_briefs_descending_by_date(self):
        await self._seed_brief("user-1", "2026-04-29", "older")
        await self._seed_brief("user-1", "2026-05-01", "newer")
        await self._seed_brief("user-1", "2026-04-30", "middle")

        result = await brief_module.list_briefs("user-1")
        # Newest first — important because the UI's "history" list
        # renders top-down.
        assert [b["date"] for b in result] == ["2026-05-01", "2026-04-30", "2026-04-29"]

    async def test_list_briefs_respects_limit(self):
        for d in ["2026-04-25", "2026-04-26", "2026-04-27", "2026-04-28", "2026-04-29"]:
            await self._seed_brief("user-1", d)

        result = await brief_module.list_briefs("user-1", limit=3)
        assert len(result) == 3
        # Most recent 3 (sort then truncate, not vice versa).
        assert [b["date"] for b in result] == ["2026-04-29", "2026-04-28", "2026-04-27"]

    async def test_list_briefs_isolates_users(self):
        await self._seed_brief("user-a", "2026-05-01", "A's brief")
        await self._seed_brief("user-b", "2026-05-01", "B's brief")

        a_briefs = await brief_module.list_briefs("user-a")
        assert len(a_briefs) == 1
        assert a_briefs[0]["body"] == "A's brief"


# Every case below prices against Sonnet 4.6 ($3 / $15 / $3.75 / $0.30 per
# Mtok) so the arithmetic stays readable; TestModelPricing covers the fact


class TestDescribeBalance:
    """`describe_balance` is the API's twin of the SPA's `describeBalance`
    (ui/client/entities/project/model/contract.ts): the same inputs, the same
    words, as `contract.test.ts` pins them there."""

    @pytest.mark.parametrize(
        ("hours", "words"),
        [
            (4.5, "+4.5 h over"),
            (6.2, "+6.2 h over"),
            (-2, "−2.0 h owed"),
            (-0.04, "even"),
            (0, "even"),
            (0.04, "even"),
            (0.05, "+0.1 h over"),
            # A tie: toFixed rounds away from zero where Python's round()
            # would go to the even digit and say 0.2.
            (0.25, "+0.3 h over"),
            (-0.25, "−0.3 h owed"),
        ],
    )
    def test_matches_the_spa(self, hours, words):
        assert describe_balance(hours) == words


class TestPartTimePercentReadsAsThePage:
    """A part-time term's percentage, in the goal line, get_projects and the
    contract week's label, is the one the page prints with `toPercent`
    (`Math.round(fraction * 10000) / 100`), not a whole percent."""

    @staticmethod
    def _part_time(fraction: float):
        from beats.domain.models import ContractTerm, ScheduleType

        return ContractTerm(
            effective_from=date(2026, 1, 5),
            schedule_type=ScheduleType.PART_TIME,
            full_time_hours=40,
            percentage=fraction,
        )

    @pytest.mark.parametrize(
        ("fraction", "shown"),
        # What node prints for `String(toPercent(fraction))`. The first four
        # were "88%", "62%", "38%" and "12%" — a tie went to the even digit.
        [
            (0.875, "87.5"),
            (0.625, "62.5"),
            (0.375, "37.5"),
            (0.125, "12.5"),
            (0.6875, "68.75"),
            (0.8, "80"),
            (0.29, "29"),
            (0.335, "33.5"),
            (0.0725, "7.25"),
            (0.995, "99.5"),
        ],
    )
    def test_matches_the_spa(self, fraction, shown):
        assert fmt_contract_goal(self._part_time(fraction)) == f"contract, {shown}%"

    def test_every_half_percent_the_form_offers_reads_as_typed(self):
        """The form steps by half a percent and stores `fromPercent`'s
        `Math.round(percent * 100) / 10000`; the page shows each back as
        typed, and so must the coach. A part-time term is under 100%."""
        mismatches = []
        for halves in range(1, 200):
            typed = halves / 2
            stored = round(typed * 100) / 10000
            said = fmt_contract_goal(self._part_time(stored))
            if said != f"contract, {typed:g}%":
                mismatches.append((typed, said))
        assert mismatches == []

    async def test_the_contract_week_is_labelled_with_it(self):
        from beats.domain.contract_service import ContractService
        from beats.domain.models import Contract, Project, ProjectKind

        job = Project(
            id="job",
            name="Acme",
            kind=ProjectKind.DAY_JOB,
            contract=Contract(terms=[self._part_time(0.875)]),
        )
        service = ContractService(
            project_repo=_FakeProjectRepoForTools([job]),
            beat_repo=_FakeBeatRepoForTools([]),
            absence_repo=_FakeAbsenceStoreForCoach([]),
            adjustment_repo=_FakeAdjustmentStoreForCoach([]),
            now=lambda tz: CONTRACT_NOW.astimezone(tz),
        )
        week = await service.week_for(job, [], None, ZURICH)
        lines = contract_section([job], {"job": week}, CONTRACT_TODAY)
        assert lines[1].startswith("  Acme (contract, 87.5%): this week expects")


class TestPartTimeHoursReadAsThePage:
    """`fmt_hours` prints a term's weekly hours as the page does with
    `termHoursPerWeek` and `formatHours` (`Math.round(hours * 100) / 100`),
    not as the raw product of full-time hours and percentage."""

    @pytest.mark.parametrize(
        ("full_time", "fraction", "shown"),
        # What node prints for `formatHours(termHoursPerWeek(term))`. The
        # first three were "28.875", "31.24875" and "13.332".
        [
            (42, 0.6875, "28.88"),
            (37.5, 0.8333, "31.25"),
            (40, 0.3333, "13.33"),
            (42, 0.8, "33.6"),
            (40, 0.5, "20"),
        ],
    )
    def test_matches_the_spa(self, full_time, fraction, shown):
        assert fmt_hours(full_time * fraction) == shown


class TestContractSectionReadsAsThePage:
    """Every whole-second duration worked, against two weeks: the coach's
    expected, worked and to go are the page's Expected, Worked and
    Remaining at the tenth the page shows, from the same week the page
    reads (`ContractService.week_for`). The page rounds each on its own, so
    its figures need not add up, and the coach must not either."""

    _LINE = re.compile(
        r"this week expects (?P<expected>\d+\.\d) h after holidays and days off"
        r" — (?P<worked>\d+\.\d) h worked,"
        r" (?:(?P<to_go>\d+\.\d) h to go|week met|week done, (?P<over>\d+\.\d) h over)$"
    )

    @staticmethod
    def _job(term):
        from beats.domain.models import Contract, Project, ProjectKind

        return Project(
            id="job", name="Acme", kind=ProjectKind.DAY_JOB, contract=Contract(terms=[term])
        )

    @pytest.mark.parametrize(
        ("week", "seconds"),
        [
            # 40 h, nine hours of it to the second: 8.545 h among them.
            ("custom_40", range(9 * 3600 + 1)),
            # 80 % of 42 h less Friday's half day: 30.24 h, an hour of it.
            ("part_time_half_day", range(3600 + 1)),
        ],
    )
    async def test_every_figure_is_the_pages_tenth(self, week, seconds):
        from beats.domain.contract_service import ContractService
        from beats.domain.models import Absence, AbsenceType, Beat, ContractTerm, ScheduleType

        starts = date(2026, 5, 18)
        term, absences = {
            "custom_40": (
                ContractTerm(
                    effective_from=starts, schedule_type=ScheduleType.CUSTOM, weekly_hours=40
                ),
                [],
            ),
            "part_time_half_day": (
                ContractTerm(
                    effective_from=starts,
                    schedule_type=ScheduleType.PART_TIME,
                    full_time_hours=42,
                    percentage=0.8,
                ),
                [
                    Absence(
                        project_id="job",
                        date=date(2026, 5, 29),
                        half_day=True,
                        type=AbsenceType.VACATION,
                    )
                ],
            ),
        }[week]
        job = self._job(term)
        service = ContractService(
            project_repo=_FakeProjectRepoForTools([job]),
            beat_repo=_FakeBeatRepoForTools([]),
            absence_repo=_FakeAbsenceStoreForCoach(absences),
            adjustment_repo=_FakeAdjustmentStoreForCoach([]),
            now=lambda tz: CONTRACT_NOW.astimezone(tz),
        )
        started = datetime(2026, 5, 26, 7, tzinfo=UTC)

        mismatches = []
        for second in seconds:
            beat = Beat(
                id="b", project_id="job", start=started, end=started + timedelta(seconds=second)
            )
            page = await service.week_for(job, [beat], None, ZURICH)
            lines = contract_section([job], {"job": page}, CONTRACT_TODAY)
            match = self._LINE.search(lines[1])
            assert match is not None, lines[1]
            assert page.expected is not None
            assert page.remaining is not None
            said = (match["expected"], match["worked"], match["to_go"] or "0.0")
            shown = (
                _to_fixed_1(page.expected),
                _to_fixed_1(page.worked),
                _to_fixed_1(max(page.remaining, 0.0)),
            )
            if said != shown:
                mismatches.append((second, said, shown))
            if match["over"] is not None:
                # The page's "The week is done — 0.4 h over."
                assert match["over"] == _to_fixed_1(-page.remaining), second

        assert mismatches == []

    @pytest.mark.parametrize(
        ("hours", "shown"),
        # What node prints for `hours.toFixed(1)`: 8.545 and 31.455 are just
        # under and over their ties in binary, 0.25 and 16.25 exact ties.
        [
            (8.545, "8.5"),
            (31.455, "31.5"),
            (31.45, "31.4"),
            (0.25, "0.3"),
            (16.25, "16.3"),
            (0.15, "0.1"),
            (2.675, "2.7"),
            (1.005, "1.0"),
            (0.0, "0.0"),
            (40.0, "40.0"),
        ],
    )
    def test_the_reference_is_javascripts_to_fixed(self, hours, shown):
        assert _to_fixed_1(hours) == shown
