"""The startup migrations: the one that gives every project a `kind`, and the one
that then clears the personal goal where the contract has replaced it.

Documents are seeded raw through the synchronous test client and read back
raw, because what is under test is the on-disk shape: which fields each pass
sets or unsets and which it leaves exactly as they were. Two tests read the
result back through `MongoProjectRepository`, since the migration writes the
contract by hand and the repository must agree with it.
"""

import os
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from bson import ObjectId
from pymongo import AsyncMongoClient

from beats.domain.contracts import term_on
from beats.domain.models import ProjectKind
from beats.infrastructure.migrations import (
    clear_personal_goal_on_day_jobs,
    migrate_project_kinds,
)
from beats.infrastructure.repositories import MongoProjectRepository

USER = "user-1"


@pytest.fixture
async def db():
    client = AsyncMongoClient(os.environ.get("DB_DSN", "mongodb://localhost:27017"))
    try:
        yield client[os.environ.get("DB_NAME", "beats_test")]
    finally:
        await client.close()


@pytest.fixture(autouse=True)
def _fresh(mongo):
    """Each test seeds its own projects; the report's counts must be about them alone."""
    mongo.projects.delete_many({})
    mongo.beats.delete_many({})


def _seed_project(mongo, **fields: Any) -> ObjectId:
    doc: dict[str, Any] = {"name": "job", "user_id": USER, "archived": False, **fields}
    return mongo.projects.insert_one(doc).inserted_id


def _created(day: date) -> ObjectId:
    """An id whose creation date is `day` — the base date of a project never worked on."""
    return ObjectId.from_datetime(datetime(day.year, day.month, day.day, 12, tzinfo=UTC))


def _seed_beat(mongo, project_id: ObjectId, start: Any, end: Any) -> None:
    mongo.beats.insert_one(
        {"user_id": USER, "project_id": str(project_id), "start": start, "end": end, "tags": []}
    )


def _terms(doc: dict[str, Any]) -> list[tuple[str, float]]:
    return [(t["effective_from"], t["weekly_hours"]) for t in doc["contract"]["terms"]]


class TestMigrateProjectKinds:
    async def test_target_with_dated_overrides_becomes_terms_in_order(self, db, mongo):
        overrides = [
            {"effective_from": "2026-06-01", "note": "sabbatical"},
            {"effective_from": "2026-03-02", "weekly_goal": 30, "goal_type": "cap"},
        ]
        pid = _seed_project(
            mongo, weekly_goal=20, goal_type="target", goal_overrides=overrides, color="#123456"
        )
        _seed_beat(
            mongo,
            pid,
            datetime(2026, 1, 13, 9, tzinfo=UTC),
            datetime(2026, 1, 13, 10, tzinfo=UTC),
        )

        report = await migrate_project_kinds(db)

        assert (report.day_job, report.side_project, report.skipped) == (1, 0, 0)
        doc = mongo.projects.find_one({"_id": pid})
        assert doc["kind"] == "day_job"
        assert _terms(doc) == [("2026-01-13", 20.0), ("2026-03-02", 30.0), ("2026-06-01", 0.0)]
        # The personal goal is left as it was: clearing it is the second pass's.
        assert doc["weekly_goal"] == 20
        assert doc["goal_overrides"] == overrides
        assert doc["color"] == "#123456"

        project = await MongoProjectRepository(db.projects, USER).get_by_id(str(pid))
        assert project.kind is ProjectKind.DAY_JOB
        assert project.contract is not None
        assert project.contract.starts_on == date(2026, 1, 13)
        assert [t.note for t in project.contract.terms] == [None, None, "sabbatical"]

    @pytest.mark.parametrize(
        "fields",
        [{}, {"weekly_goal": 0, "goal_type": "target"}, {"weekly_goal": -5, "goal_type": "target"}],
        ids=["absent", "zero", "negative"],
    )
    async def test_no_goal_or_a_goal_of_nothing_is_a_side_project(self, db, mongo, fields):
        pid = _seed_project(mongo, **fields)

        report = await migrate_project_kinds(db)

        assert (report.day_job, report.side_project) == (0, 1)
        doc = mongo.projects.find_one({"_id": pid})
        assert doc["kind"] == "side_project"
        assert "contract" not in doc

    async def test_cap_stays_a_side_project_and_keeps_its_goal(self, db, mongo):
        pid = _seed_project(mongo, weekly_goal=10, goal_type="cap")

        report = await migrate_project_kinds(db)

        assert (report.day_job, report.side_project) == (0, 1)
        doc = mongo.projects.find_one({"_id": pid})
        assert doc["kind"] == "side_project"
        assert doc["weekly_goal"] == 10
        assert "contract" not in doc

    async def test_week_of_override_gives_one_term_and_stays_in_place(self, db, mongo):
        overrides = [{"week_of": "2026-04-06", "weekly_goal": 10}]
        pid = _seed_project(
            mongo,
            _id=_created(date(2026, 1, 5)),
            weekly_goal=20,
            goal_type="target",
            goal_overrides=overrides,
        )

        report = await migrate_project_kinds(db)

        doc = mongo.projects.find_one({"_id": pid})
        assert doc["kind"] == "day_job"
        assert _terms(doc) == [("2026-01-05", 20.0)]
        assert doc["goal_overrides"] == overrides
        # The week is in the log, so the user can be told it no longer applies.
        assert "2026-04-06" in report.lines[0]

    async def test_rerun_changes_nothing(self, db, mongo):
        _seed_project(mongo, weekly_goal=20, goal_type="target")
        _seed_project(mongo, weekly_goal=10, goal_type="cap")
        _seed_project(mongo)
        await migrate_project_kinds(db)
        before = list(mongo.projects.find().sort("_id"))

        report = await migrate_project_kinds(db)

        assert (report.migrated, report.skipped) == (0, 0)
        assert list(mongo.projects.find().sort("_id")) == before

    async def test_overrides_before_the_first_beat_the_latest_is_the_base_term(self, db, mongo):
        """Two terms on one day, or out of order, is what `Contract` rejects; an
        override already in force on the base date *is* the base term, and
        when two were, the latest — which is what `effective_goal` resolved to."""
        pid = _seed_project(
            mongo,
            weekly_goal=20,
            goal_type="target",
            goal_overrides=[
                {"effective_from": "2025-12-01", "weekly_goal": 35},
                {"effective_from": "2025-11-03", "weekly_goal": 30},
            ],
        )
        _seed_beat(
            mongo,
            pid,
            datetime(2026, 3, 10, 9, tzinfo=UTC),
            datetime(2026, 3, 10, 10, tzinfo=UTC),
        )

        await migrate_project_kinds(db)

        assert _terms(mongo.projects.find_one({"_id": pid})) == [("2026-03-10", 35.0)]

    async def test_a_term_restating_the_hours_before_it_is_dropped(self, db, mongo):
        pid = _seed_project(
            mongo,
            _id=_created(date(2026, 1, 5)),
            weekly_goal=20,
            goal_type="target",
            goal_overrides=[
                {"effective_from": "2026-03-02", "weekly_goal": 30},
                {"effective_from": "2026-04-06", "weekly_goal": 30},
                {"effective_from": "2026-05-04", "weekly_goal": 20},
            ],
        )

        await migrate_project_kinds(db)

        assert _terms(mongo.projects.find_one({"_id": pid})) == [
            ("2026-01-05", 20.0),
            ("2026-03-02", 30.0),
            ("2026-05-04", 20.0),
        ]

    async def test_the_contract_says_what_the_goal_said_every_week(self, db, mongo):
        """Decision 10, Monday by Monday: from the first beat on, `term_on` must
        give what `effective_goal` gave — through overrides before the first
        beat, two on one day, one restating the hours, and one to no goal."""
        overrides = [
            {"effective_from": "2025-12-01", "weekly_goal": 35},
            {"effective_from": "2025-11-03", "weekly_goal": 30},
            {"effective_from": "2026-03-02", "weekly_goal": 25},
            {"effective_from": "2026-03-02", "weekly_goal": 15},
            {"effective_from": "2026-04-06", "weekly_goal": 25},
            {"effective_from": "2026-06-01", "weekly_goal": None},
        ]
        pid = _seed_project(mongo, weekly_goal=20, goal_type="target", goal_overrides=overrides)
        _seed_beat(
            mongo,
            pid,
            datetime(2026, 1, 13, 9, tzinfo=UTC),
            datetime(2026, 1, 13, 10, tzinfo=UTC),
        )
        repo = MongoProjectRepository(db.projects, USER)
        before = await repo.get_by_id(str(pid))

        await migrate_project_kinds(db)

        contract = (await repo.get_by_id(str(pid))).contract
        assert contract is not None
        mondays = [date(2026, 1, 19) + timedelta(weeks=n) for n in range(26)]
        for monday in mondays:
            term = term_on(contract, monday)
            assert term is not None, monday
            assert term.hours_per_week == (before.effective_goal(monday)[0] or 0), monday

    async def test_base_term_starts_on_the_first_beat_or_the_documents_creation(self, db, mongo):
        worked = _seed_project(mongo, weekly_goal=20, goal_type="target")
        _seed_beat(
            mongo,
            worked,
            datetime(2026, 1, 13, 9, tzinfo=UTC),
            datetime(2026, 1, 13, 10, tzinfo=UTC),
        )
        # A restored backup: the import path stores the JSON's strings as they
        # are, and BSON sorts a string before every date — so this later beat
        # is the one a `$min` would pick.
        _seed_beat(mongo, worked, "2026-01-14T09:00:00+00:00", "2026-01-14T10:00:00+00:00")
        untouched = _seed_project(
            mongo, _id=_created(date(2025, 5, 6)), weekly_goal=20, goal_type="target"
        )

        await migrate_project_kinds(db)

        assert _terms(mongo.projects.find_one({"_id": worked})) == [("2026-01-13", 20.0)]
        assert _terms(mongo.projects.find_one({"_id": untouched})) == [("2025-05-06", 20.0)]

    async def test_a_beat_still_running_counts_as_the_earliest(self, db, mongo):
        pid = _seed_project(
            mongo, _id=_created(date(2026, 1, 1)), weekly_goal=20, goal_type="target"
        )
        _seed_beat(mongo, pid, datetime(2026, 2, 2, 9, tzinfo=UTC), None)
        _seed_beat(
            mongo,
            pid,
            datetime(2026, 2, 9, 9, tzinfo=UTC),
            datetime(2026, 2, 9, 10, tzinfo=UTC),
        )

        await migrate_project_kinds(db)

        assert _terms(mongo.projects.find_one({"_id": pid})) == [("2026-02-02", 20.0)]

    async def test_document_with_a_kind_is_left_alone(self, db, mongo):
        pid = _seed_project(mongo, kind="side_project", weekly_goal=20, goal_type="target")

        report = await migrate_project_kinds(db)

        assert (report.migrated, report.skipped) == (0, 0)
        doc = mongo.projects.find_one({"_id": pid})
        assert doc["kind"] == "side_project"
        assert doc["weekly_goal"] == 20
        assert "contract" not in doc

    @pytest.mark.parametrize(
        "fields",
        [
            {"weekly_goal": "20", "goal_type": "target"},
            {"weekly_goal": 20, "goal_type": "target", "goal_overrides": [None]},
        ],
        ids=["goal-not-a-number", "override-not-an-object"],
    )
    async def test_a_document_the_pass_cannot_read_is_skipped_and_the_rest_migrated(
        self, db, mongo, fields
    ):
        """The pass runs in `lifespan`: one document it cannot read must be logged and
        left without a kind, and must stop neither the other projects nor the boot."""
        bad = _seed_project(mongo, **fields)
        good = _seed_project(mongo, weekly_goal=20, goal_type="target")

        report = await migrate_project_kinds(db)

        assert (report.day_job, report.skipped) == (1, 1)
        assert "kind" not in mongo.projects.find_one({"_id": bad})
        assert mongo.projects.find_one({"_id": good})["kind"] == "day_job"


TODAY = date(2026, 9, 12)


def _contract(*terms: dict[str, Any]) -> dict[str, Any]:
    return {"terms": list(terms)}


def _custom(effective_from: str, weekly_hours: float) -> dict[str, Any]:
    return {
        "effective_from": effective_from,
        "schedule_type": "custom",
        "weekly_hours": weekly_hours,
    }


class TestClearPersonalGoalOnDayJobs:
    async def test_clears_where_the_contract_sets_the_goal_and_nowhere_else(self, db, mongo):
        overrides = [{"week_of": "2026-04-06", "weekly_goal": 10, "note": "conference"}]
        governed = _seed_project(
            mongo,
            kind="day_job",
            weekly_goal=20,
            goal_overrides=overrides,
            contract=_contract(_custom("2026-01-05", 20), _custom("2026-06-01", 30)),
        )
        objective = _seed_project(
            mongo,
            kind="day_job",
            weekly_goal=20,
            contract=_contract({"effective_from": "2026-01-05", "schedule_type": "objective"}),
        )
        not_started = _seed_project(
            mongo, kind="day_job", weekly_goal=20, contract=_contract(_custom("2026-10-05", 40))
        )
        no_contract = _seed_project(mongo, kind="day_job", weekly_goal=20)
        side = _seed_project(mongo, kind="side_project", weekly_goal=20, goal_type="target")

        report = await clear_personal_goal_on_day_jobs(db, today=TODAY)

        assert (report.cleared, report.skipped) == (1, 0)
        doc = mongo.projects.find_one({"_id": governed})
        assert "weekly_goal" not in doc
        # The overrides are the user's notes on weeks; the panel still lists them.
        assert doc["goal_overrides"] == overrides
        assert doc["contract"]["terms"][1]["weekly_hours"] == 30
        for untouched in (objective, not_started, no_contract, side):
            assert mongo.projects.find_one({"_id": untouched})["weekly_goal"] == 20

    async def test_rerun_is_a_no_op(self, db, mongo):
        _seed_project(
            mongo, kind="day_job", weekly_goal=20, contract=_contract(_custom("2026-01-05", 20))
        )
        _seed_project(mongo, kind="day_job", weekly_goal=20)
        await clear_personal_goal_on_day_jobs(db, today=TODAY)
        before = list(mongo.projects.find().sort("_id"))

        report = await clear_personal_goal_on_day_jobs(db, today=TODAY)

        assert (report.cleared, report.skipped) == (0, 0)
        assert list(mongo.projects.find().sort("_id")) == before

    async def test_a_contract_the_pass_cannot_read_is_skipped_and_the_rest_cleared(self, db, mongo):
        bad = _seed_project(mongo, kind="day_job", weekly_goal=20, contract={"terms": []})
        good = _seed_project(
            mongo, kind="day_job", weekly_goal=20, contract=_contract(_custom("2026-01-05", 20))
        )

        report = await clear_personal_goal_on_day_jobs(db, today=TODAY)

        assert (report.cleared, report.skipped) == (1, 1)
        assert mongo.projects.find_one({"_id": bad})["weekly_goal"] == 20
        assert "weekly_goal" not in mongo.projects.find_one({"_id": good})

    async def test_both_passes_in_one_boot_leave_a_contract_and_no_goal(self, db, mongo):
        """The order `lifespan` runs them in: a target goal becomes the contract,
        and the same boot then drops the goal the contract was derived from."""
        pid = _seed_project(
            mongo, _id=_created(date(2026, 1, 5)), weekly_goal=20, goal_type="target"
        )

        await migrate_project_kinds(db)
        await clear_personal_goal_on_day_jobs(db, today=TODAY)

        doc = mongo.projects.find_one({"_id": pid})
        assert doc["kind"] == "day_job"
        assert _terms(doc) == [("2026-01-05", 20.0)]
        assert "weekly_goal" not in doc
        project = await MongoProjectRepository(db.projects, USER).get_by_id(str(pid))
        assert project.effective_goal(date(2026, 9, 7)) == (20.0, project.goal_type)
