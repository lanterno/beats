"""Build a SQLite snapshot of a user's Beats data.

Kept framework-agnostic: the caller passes plain dicts (already serialized via
`model_dump(mode="json")`) and receives bytes. Schema is intentionally flat —
one table per collection, JSON columns for nested structures — so the export
is self-describing and easy to open with `sqlite3` on the command line.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    name TEXT,
    description TEXT,
    estimation TEXT,
    color TEXT,
    archived INTEGER,
    weekly_goal REAL,
    goal_type TEXT,
    github_repo TEXT,
    data JSON
);

CREATE TABLE IF NOT EXISTS beats (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    project_id TEXT,
    start TEXT,
    "end" TEXT,
    note TEXT,
    tags JSON,
    data JSON
);

CREATE TABLE IF NOT EXISTS intentions (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    project_id TEXT,
    date TEXT,
    planned_minutes INTEGER,
    completed INTEGER,
    data JSON
);

CREATE TABLE IF NOT EXISTS daily_notes (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    date TEXT,
    note TEXT,
    mood INTEGER,
    data JSON
);

CREATE INDEX IF NOT EXISTS idx_beats_start ON beats(start);
CREATE INDEX IF NOT EXISTS idx_beats_project ON beats(project_id);
CREATE INDEX IF NOT EXISTS idx_intentions_date ON intentions(date);
"""


@dataclass
class ExportPayload:
    """User-scoped data to serialize. All lists hold JSON-serializable dicts."""

    projects: list[dict[str, Any]]
    beats: list[dict[str, Any]]
    intentions: list[dict[str, Any]]
    daily_notes: list[dict[str, Any]]


def build_sqlite_bytes(payload: ExportPayload) -> bytes:
    """Return a SQLite database file's bytes for the given payload.

    Uses a NamedTemporaryFile rather than :memory: so the built-in
    `sqlite3.connect(":memory:")` limitation on dumping doesn't bite us.
    """
    with tempfile.NamedTemporaryFile(suffix=".sqlite") as tmp:
        db_path = Path(tmp.name)
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(SCHEMA)
            for table, columns, extract in _INSERT_PLANS:
                rows = getattr(payload, table)
                _insert_rows(conn, table, columns, extract, rows)
            conn.commit()
        finally:
            conn.close()
        return db_path.read_bytes()


def build_manifest(payload: ExportPayload, sqlite_bytes: bytes, version: str) -> dict[str, Any]:
    """Return a deterministic manifest describing the export."""
    return {
        "version": version,
        "counts": {
            "projects": len(payload.projects),
            "beats": len(payload.beats),
            "intentions": len(payload.intentions),
            "daily_notes": len(payload.daily_notes),
        },
        "sqlite_sha256": hashlib.sha256(sqlite_bytes).hexdigest(),
    }


def canonical_manifest_bytes(manifest: dict[str, Any]) -> bytes:
    """Canonical JSON bytes for signing — sorted keys, no whitespace variations."""
    return json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")


# Per-table configs: (table_name, column_names, value_extractor).
# The `data` column is appended automatically as the full JSON-serialized row,
# so every extractor only needs to return the typed columns.
_RowExtractor = Callable[[dict[str, Any]], Sequence[Any]]


_INSERT_PLANS: list[tuple[str, tuple[str, ...], _RowExtractor]] = [
    (
        "projects",
        (
            "id",
            "user_id",
            "name",
            "description",
            "estimation",
            "color",
            "archived",
            "weekly_goal",
            "goal_type",
            "github_repo",
        ),
        lambda r: (
            r.get("id"),
            r.get("user_id"),
            r.get("name"),
            r.get("description"),
            r.get("estimation"),
            r.get("color"),
            1 if r.get("archived") else 0,
            r.get("weekly_goal"),
            r.get("goal_type"),
            r.get("github_repo"),
        ),
    ),
    (
        "beats",
        ("id", "user_id", "project_id", "start", "end", "note", "tags"),
        lambda r: (
            r.get("id"),
            r.get("user_id"),
            r.get("project_id"),
            r.get("start"),
            r.get("end"),
            r.get("note"),
            json.dumps(r.get("tags") or []),
        ),
    ),
    (
        "intentions",
        ("id", "user_id", "project_id", "date", "planned_minutes", "completed"),
        lambda r: (
            r.get("id"),
            r.get("user_id"),
            r.get("project_id"),
            r.get("date"),
            r.get("planned_minutes"),
            1 if r.get("completed") else 0,
        ),
    ),
    (
        "daily_notes",
        ("id", "user_id", "date", "note", "mood"),
        lambda r: (
            r.get("id"),
            r.get("user_id"),
            r.get("date"),
            r.get("note"),
            r.get("mood"),
        ),
    ),
]


def _insert_rows(
    conn: sqlite3.Connection,
    table: str,
    columns: tuple[str, ...],
    extract: _RowExtractor,
    rows: list[dict[str, Any]],
) -> None:
    """Generic bulk-insert: typed columns + a trailing `data` JSON blob."""
    col_list = ", ".join(f'"{c}"' for c in columns)
    placeholders = ", ".join("?" * (len(columns) + 1))
    sql = f"INSERT OR REPLACE INTO {table} ({col_list}, data) VALUES ({placeholders})"
    conn.executemany(
        sql,
        [(*extract(r), json.dumps(r, default=str)) for r in rows],
    )
