"""Startup migration: stamp `kind` on every project, and turn a target goal into a contract.

Runs once per boot from `lifespan`, over every user's projects at once — it is
a task of the deployment, not of a request, so it works on the raw collection
rather than through a user-scoped repository. A document without a `kind`
field is unmigrated; a migrated one has it, so the pass is idempotent by
construction and a second boot finds nothing to do.

That test only holds if nothing else writes `kind` first. Since the domain
model gained the field, the repository writes its default (`side_project`) on
every save, so a target project saved under a build that has the model but
not this pass would be skipped here with its goal intact and no contract.
The model and the migration therefore deploy together — never the model on
its own.

The rules are the roadmap's (docs/work-contracts-roadmap.md, Phase 2):

1. No `weekly_goal` → side_project.
2. `weekly_goal` with `goal_type == cap` → side_project, goal kept: a cap
   limits, it does not oblige.
3. `weekly_goal` with `goal_type == target` → day_job, with a contract whose
   base term is `custom` at those hours and whose later terms come from the
   `effective_from` overrides.

The pass is additive: it sets `kind` and, for a day job, `contract`, and
touches nothing else. `weekly_goal` and `goal_overrides` stay exactly as they
were. Until the week card and the API's goal readers take the contract, the
personal goal is still what the user sees, and it must keep saying what it
said the day before. Leaving it also makes the pass safe to roll back and
safe under a rollout: a build without the model that rewrites a migrated
document drops `kind` and `contract`, and the next boot on this build derives
the same contract from the same fields. Clearing `weekly_goal` on day jobs is
the step after the readers switch, as its own pass.

What the roadmap leaves open, decided here:

- **The base term's date.** `Project` has no `created_at`. The base term starts
  on the UTC date of the project's earliest beat, running or not — the day the
  timer first ran on it — or, for a project never worked on, on the UTC date
  its document was created, read from the ObjectId. UTC because there is no
  request timezone at startup; being a day out on the day a contract began
  costs at most one weekday's expectation, and the term's date is the user's
  to edit.
- **Imported beats.** `/api/export/import` writes beats as they arrive in the
  JSON, so a restored beat carries an ISO string for `start` where a tracked
  one carries a BSON date. BSON orders strings before dates, so `$min` or a
  sorted `find_one` would pick the wrong beat on a mixed collection; the
  minimum is taken here after parsing each value. Beats are scoped by
  `(user_id, project_id)`, as every repository query is.
- **Overrides on or before the base date.** An `effective_from` override dated
  on or before the base term replaces the base term's hours rather than adding
  a term: `Contract` rejects two terms on one day and any out-of-order list,
  and under `effective_goal` that override already was what applied from the
  base date on. The latest such override wins, as it did there. The project's
  own `weekly_goal` then appears in no term — it applied only to weeks before
  the first beat, when nothing was worked and nothing is charged.
- **Two overrides on one date.** `effective_goal` resolves them to the first in
  list order; so does this.
- **An override with `weekly_goal` unset** becomes a `custom` term of zero
  hours: nothing is expected from that date, which is what "no goal from here"
  meant. An override's `note` is carried onto its term.
- **An override typed `cap`** becomes a term at its hours all the same — a
  contract has no notion of a cap — and the project's log line names its date,
  because a limit the user set has become an obligation and they should hear
  about it.
- **A zero or negative `weekly_goal`** counts as no goal (rule 1): the week card
  had nothing to reach, and a day job owing zero hours is not what anyone
  meant by it.
- **`week_of` overrides** are one-week deviations, not contract changes. They
  stay on `goal_overrides` and keep applying to the personal goal for now; the
  contract does not know them. Their weeks are in the project's log line so
  the user can be told.
- **Coalescing.** A term restating the hours of the term before it is dropped;
  the history the user sees is of changes.
- **Pathological documents.** The contract is built through the pydantic model
  so its validator runs. If it refuses — or anything in the document is not
  the shape this code expects — the document is logged with its id and left
  exactly as it was, `kind` included, so the next boot tries again and the log
  keeps saying so. Whatever goes wrong in one project, startup goes on.
- **The log.** Ids only — no project name. A name is the user's content, and
  a skipped document is logged at ERROR on every boot until it is fixed.

Updates are a `$set` on the raw document, filtered on `kind` still being
absent. Nothing else in the document is rewritten, so a field this code does
not know about survives, and a request that stamps `kind` in the meantime is
not overwritten.
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from beats.domain.models import Contract, ContractTerm, GoalType, ProjectKind, ScheduleType
from beats.domain.utils import normalize_tz

logger = logging.getLogger(__name__)

# The BSON key for beats' owning project: the project's ObjectId as a string.
_BeatKey = tuple[Any, str]


@dataclass
class MigrationReport:
    """What one pass did: a count per outcome and a line per project it looked at."""

    side_project: int = 0
    day_job: int = 0
    skipped: int = 0
    lines: list[str] = field(default_factory=list)

    @property
    def migrated(self) -> int:
        return self.side_project + self.day_job


@dataclass(frozen=True)
class _Plan:
    kind: ProjectKind
    update: dict[str, Any]
    summary: str


@dataclass(frozen=True)
class _Derived:
    """A day job's terms, and what in `goal_overrides` the user should hear about."""

    terms: list[ContractTerm]
    week_of: list[date]  # one-week deviations, left on the personal goal
    caps: list[date]  # dated overrides typed cap, whose limit is now hours owed


async def migrate_project_kinds(db: AsyncDatabase) -> MigrationReport:
    """Give every project without a `kind` one, following the rules above."""
    report = MigrationReport()
    docs = await db.projects.find({"kind": {"$exists": False}}).to_list(length=None)
    if not docs:
        logger.debug("project kinds: nothing to migrate")
        return report

    first_beat_day = await _first_beat_days(db, docs)

    for doc in docs:
        project_id = doc["_id"]
        label = f"project {project_id} (user {doc.get('user_id')})"
        try:
            plan = _plan(doc, first_beat_day.get((doc.get("user_id"), str(project_id))))
        except Exception as exc:  # noqa: BLE001 — one document must not stop the boot
            # A ValidationError, an unreadable date or number, a field of the
            # wrong shape: left alone, no kind, so the next boot retries.
            report.skipped += 1
            report.lines.append(f"{label}: skipped — {exc}")
            logger.error("%s: not migrated, left without a kind: %s", label, exc)
            continue

        result = await db.projects.update_one(
            {"_id": project_id, "kind": {"$exists": False}}, plan.update
        )
        if result.modified_count == 0:
            # Something stamped a kind between the read and the write; it wins.
            report.lines.append(f"{label}: already had a kind by the time it was written")
            continue

        if plan.kind is ProjectKind.DAY_JOB:
            report.day_job += 1
        else:
            report.side_project += 1
        report.lines.append(f"{label}: {plan.summary}")
        logger.info("%s: %s", label, plan.summary)

    logger.info(
        "project kinds: %d migrated (%d side_project, %d day_job), %d skipped",
        report.migrated,
        report.side_project,
        report.day_job,
        report.skipped,
    )
    return report


def _plan(doc: dict[str, Any], first_beat_day: date | None) -> _Plan:
    goal = _project_goal(doc.get("weekly_goal"))
    if goal is None:
        return _Plan(
            ProjectKind.SIDE_PROJECT,
            {"$set": {"kind": ProjectKind.SIDE_PROJECT.value}},
            "side_project — no weekly goal",
        )
    if doc.get("goal_type") == GoalType.CAP:
        return _Plan(
            ProjectKind.SIDE_PROJECT,
            {"$set": {"kind": ProjectKind.SIDE_PROJECT.value}},
            f"side_project — {goal:g} h cap kept as the personal goal",
        )

    starts_on = first_beat_day if first_beat_day is not None else _created_on(doc["_id"])
    derived = _terms(doc.get("goal_overrides") or [], starts_on, goal)
    contract = Contract(terms=derived.terms)
    history = ", ".join(f"{t.effective_from} {t.weekly_hours:g} h" for t in derived.terms)
    summary = f"day_job — {len(derived.terms)} term(s): {history}"
    if derived.week_of:
        weeks = ", ".join(str(week) for week in derived.week_of)
        summary += f"; {len(derived.week_of)} week_of override(s) left in place: {weeks}"
    if derived.caps:
        days = ", ".join(str(day) for day in derived.caps)
        summary += f"; {len(derived.caps)} cap override(s) now hours owed: {days}"
    return _Plan(
        ProjectKind.DAY_JOB,
        {
            "$set": {
                "kind": ProjectKind.DAY_JOB.value,
                "contract": contract.model_dump(mode="json", exclude_none=True),
            }
        },
        summary,
    )


def _terms(overrides: Any, starts_on: date, base_hours: float) -> _Derived:
    """The base term plus one per dated override, in order, coalesced."""
    week_of: list[date] = []
    caps: list[date] = []
    dated: list[tuple[date, float, str | None]] = []
    for override in overrides:
        if not isinstance(override, dict):
            msg = f"goal_overrides entry is not an object: {override!r}"
            raise TypeError(msg)
        if override.get("effective_from") is not None:
            day = _as_date(override["effective_from"])
            hours = override.get("weekly_goal")
            note = override.get("note")
            dated.append(
                (
                    day,
                    0.0 if hours is None else float(hours),
                    note if isinstance(note, str) else None,
                )
            )
            if override.get("goal_type") == GoalType.CAP:
                caps.append(day)
        elif override.get("week_of") is not None:
            week_of.append(_as_date(override["week_of"]))

    # A stable sort keeps two overrides on one day in list order, and the
    # first of them is the one `effective_goal` resolved to.
    dated.sort(key=lambda step: step[0])
    steps: list[tuple[date, float, str | None]] = [(starts_on, base_hours, None)]
    seen: set[date] = set()
    for day, hours, note in dated:
        if day in seen:
            continue
        seen.add(day)
        if day <= starts_on:
            steps[0] = (starts_on, hours, note)  # already in force on the base date
        else:
            steps.append((day, hours, note))

    coalesced = [steps[0]]
    for step in steps[1:]:
        if step[1] != coalesced[-1][1]:
            coalesced.append(step)

    terms = [
        ContractTerm(
            effective_from=day, schedule_type=ScheduleType.CUSTOM, weekly_hours=hours, note=note
        )
        for day, hours, note in coalesced
    ]
    return _Derived(terms, sorted(week_of), sorted(caps))


async def _first_beat_days(db: AsyncDatabase, docs: list[dict[str, Any]]) -> dict[_BeatKey, date]:
    """UTC date of the earliest beat, running or not, per (user, project), for these projects."""
    cursor = db.beats.find(
        {"project_id": {"$in": [str(doc["_id"]) for doc in docs]}},
        projection={"user_id": 1, "project_id": 1, "start": 1},
    )
    earliest: dict[_BeatKey, date] = {}
    async for beat in cursor:
        try:
            day = _as_date(beat["start"])
        except (ValueError, TypeError, KeyError) as exc:
            logger.warning("beat %s has an unreadable start, ignored: %s", beat.get("_id"), exc)
            continue
        key: _BeatKey = (beat.get("user_id"), beat["project_id"])
        if key not in earliest or day < earliest[key]:
            earliest[key] = day
    return earliest


def _created_on(project_id: Any) -> date:
    if not isinstance(project_id, ObjectId):
        msg = f"_id is not an ObjectId, so the project has no creation date: {project_id!r}"
        raise TypeError(msg)
    return project_id.generation_time.date()  # aware, UTC


def _project_goal(value: Any) -> float | None:
    """The project-level weekly goal as hours, or None when there is none to speak of."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        msg = f"weekly_goal is not a number: {value!r}"
        raise TypeError(msg)
    return float(value) if value > 0 else None


def _as_date(value: Any) -> date:
    """A stored date as a UTC calendar date: BSON dates come back naive, imports as strings."""
    if isinstance(value, datetime):
        return normalize_tz(value).astimezone(UTC).date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return _as_date(datetime.fromisoformat(value))
    msg = f"not a date: {value!r}"
    raise TypeError(msg)
