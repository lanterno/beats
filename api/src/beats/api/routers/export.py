"""Export API router — CSV and JSON data export/import."""

import csv
import hashlib
import io
import json
import sqlite3
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse

from beats.api.dependencies import (
    BeatServiceDep,
    CurrentUserId,
    DailyNoteRepoDep,
    IntentionRepoDep,
    ProjectServiceDep,
)
from beats.domain.export_signing import SignatureMismatch, sign, verify
from beats.domain.export_sqlite import (
    ExportPayload,
    build_manifest,
    build_sqlite_bytes,
    canonical_manifest_bytes,
)
from beats.infrastructure.database import Database
from beats.infrastructure.export_key_repo import ExportKeyRepository

router = APIRouter(prefix="/api/export", tags=["export"])

_COMPUTED_FIELDS = ("is_active", "duration", "day")
EXPORT_VERSION = "sqlite-1"
ZIP_SQLITE_NAME = "data.sqlite"
ZIP_MANIFEST_NAME = "manifest.json"
ZIP_SIGNATURE_NAME = "manifest.sig"
ZIP_PUBKEY_NAME = "public_key.bin"


@router.get("/csv/sessions")
async def export_sessions_csv(
    beat_service: BeatServiceDep,
    project_service: ProjectServiceDep,
    project_id: str | None = Query(default=None),
):
    """Export sessions as CSV."""
    if project_id:
        beats = await beat_service.beat_repo.list_by_project(project_id)
    else:
        beats = await beat_service.beat_repo.list_all_completed()

    projects = await project_service.project_repo.list()
    project_map = {p.id: p.name for p in projects}

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "project", "start", "end", "duration_minutes", "note", "tags"])

    for beat in sorted(beats, key=lambda b: b.start):
        if beat.end is None:
            continue
        duration_min = int(beat.duration.total_seconds() / 60)
        writer.writerow(
            [
                beat.day.isoformat(),
                project_map.get(beat.project_id, "Unknown"),
                beat.start.isoformat(),
                beat.end.isoformat(),
                duration_min,
                beat.note or "",
                ";".join(beat.tags) if beat.tags else "",
            ]
        )

    output.seek(0)
    filename = f"beats_sessions_{datetime.now(UTC).strftime('%Y%m%d')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/full")
async def export_full_json(
    beat_service: BeatServiceDep,
    project_service: ProjectServiceDep,
    intention_repo: IntentionRepoDep,
    daily_note_repo: DailyNoteRepoDep,
):
    """Export everything as JSON for backup."""
    payload = await _gather_payload(beat_service, project_service, intention_repo, daily_note_repo)
    data = {
        "exported_at": datetime.now(UTC).isoformat(),
        "version": "1.0",
        "projects": payload.projects,
        "beats": payload.beats,
        "intentions": payload.intentions,
        "daily_notes": payload.daily_notes,
    }

    output = json.dumps(data, indent=2, default=str)
    filename = f"beats_backup_{datetime.now(UTC).strftime('%Y%m%d')}.json"
    return StreamingResponse(
        iter([output]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _gather_payload(
    beat_service: BeatServiceDep,
    project_service: ProjectServiceDep,
    intention_repo: IntentionRepoDep,
    daily_note_repo: DailyNoteRepoDep,
) -> ExportPayload:
    beats = await beat_service.beat_repo.list()
    projects = await project_service.project_repo.list()
    intentions = await intention_repo.list_all()
    notes = await daily_note_repo.list_all()
    return ExportPayload(
        projects=[p.model_dump(mode="json") for p in projects],
        beats=[b.model_dump(mode="json") for b in beats],
        intentions=[i.model_dump(mode="json") for i in intentions],
        daily_notes=[n.model_dump(mode="json") for n in notes],
    )


@router.get("/sqlite")
async def export_sqlite(
    user_id: CurrentUserId,
    beat_service: BeatServiceDep,
    project_service: ProjectServiceDep,
    intention_repo: IntentionRepoDep,
    daily_note_repo: DailyNoteRepoDep,
) -> Response:
    """Export a signed SQLite snapshot as a `.zip` bundle.

    Bundle contents:
        - data.sqlite       — normalized, queryable snapshot
        - manifest.json     — version, counts, sha256(data.sqlite)
        - manifest.sig      — Ed25519 signature over the canonical manifest
        - public_key.bin    — raw 32-byte Ed25519 public key for verification

    The private key lives only in Mongo and is never served — the public key
    ships with the bundle so a user can run the verify path entirely offline.
    """
    payload = await _gather_payload(beat_service, project_service, intention_repo, daily_note_repo)
    sqlite_bytes = build_sqlite_bytes(payload)
    manifest = build_manifest(payload, sqlite_bytes, EXPORT_VERSION)
    manifest_bytes = canonical_manifest_bytes(manifest)

    key_repo = ExportKeyRepository(Database.get_db(), user_id)
    private_bytes, public_bytes = await key_repo.get_or_create()
    signature = sign(private_bytes, manifest_bytes)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(ZIP_SQLITE_NAME, sqlite_bytes)
        zf.writestr(ZIP_MANIFEST_NAME, manifest_bytes)
        zf.writestr(ZIP_SIGNATURE_NAME, signature)
        zf.writestr(ZIP_PUBKEY_NAME, public_bytes)

    filename = f"beats_backup_{datetime.now(UTC).strftime('%Y%m%d')}.zip"
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/sqlite/import")
async def import_sqlite(
    user_id: CurrentUserId,
    file: UploadFile,
    beat_service: BeatServiceDep,
    project_service: ProjectServiceDep,
    intention_repo: IntentionRepoDep,
    daily_note_repo: DailyNoteRepoDep,
):
    """Import a previously signed SQLite bundle. The signature is verified
    against the signing user's stored public key before any mutation runs —
    a tampered bundle never reaches the writers.

    Cross-account restores are rejected: the bundle must be signed by THIS
    user. Sharing exports between accounts is out of scope for v1.
    """
    blob = await file.read()
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = set(zf.namelist())
            required = {ZIP_SQLITE_NAME, ZIP_MANIFEST_NAME, ZIP_SIGNATURE_NAME}
            if not required.issubset(names):
                missing = sorted(required - names)
                raise HTTPException(status_code=400, detail=f"missing entries: {missing}")
            sqlite_bytes = zf.read(ZIP_SQLITE_NAME)
            manifest_bytes = zf.read(ZIP_MANIFEST_NAME)
            signature = zf.read(ZIP_SIGNATURE_NAME)
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail=f"not a zip: {exc}") from exc

    # The authoritative public key is the one stored server-side for this
    # user — bundling a public key inside the zip is a convenience, not a
    # trust anchor. If the user has never exported before, there is nothing
    # to verify against, and the import is rejected.
    key_repo = ExportKeyRepository(Database.get_db(), user_id)
    public_bytes = await key_repo.get_public()
    if public_bytes is None:
        raise HTTPException(
            status_code=400,
            detail="no export key on file; generate one via GET /api/export/sqlite first",
        )

    try:
        verify(public_bytes, manifest_bytes, signature)
    except SignatureMismatch as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Verify the SQLite blob hasn't been swapped post-signing.
    manifest = json.loads(manifest_bytes)
    actual_sha = hashlib.sha256(sqlite_bytes).hexdigest()
    if manifest.get("sqlite_sha256") != actual_sha:
        raise HTTPException(status_code=400, detail="sqlite payload does not match manifest")

    # At this point the bundle is authentic. Read rows out of SQLite and
    # upsert through the same repos used by the JSON import path.
    counts = {"projects": 0, "beats": 0, "intentions": 0, "daily_notes": 0}
    with tempfile.NamedTemporaryFile(suffix=".sqlite") as tmp:
        Path(tmp.name).write_bytes(sqlite_bytes)
        conn = sqlite3.connect(tmp.name)
        conn.row_factory = sqlite3.Row
        try:
            for row in conn.execute("SELECT data FROM projects"):
                proj = json.loads(row["data"])
                for k in _COMPUTED_FIELDS:
                    proj.pop(k, None)
                await project_service.project_repo.upsert(proj)
                counts["projects"] += 1
            for row in conn.execute("SELECT data FROM beats"):
                beat = json.loads(row["data"])
                for k in _COMPUTED_FIELDS:
                    beat.pop(k, None)
                await beat_service.beat_repo.upsert(beat)
                counts["beats"] += 1
            for row in conn.execute("SELECT data FROM intentions"):
                await intention_repo.upsert(json.loads(row["data"]))
                counts["intentions"] += 1
            for row in conn.execute("SELECT data FROM daily_notes"):
                await daily_note_repo.upsert_raw(json.loads(row["data"]))
                counts["daily_notes"] += 1
        finally:
            conn.close()

    return {"status": "ok", "imported": counts, "version": manifest.get("version")}


@router.post("/import")
async def import_full_json(
    file: UploadFile,
    beat_service: BeatServiceDep,
    project_service: ProjectServiceDep,
    intention_repo: IntentionRepoDep,
    daily_note_repo: DailyNoteRepoDep,
):
    """Import a full JSON backup. Upserts by ID — safe to re-import."""
    content = await file.read()
    data = json.loads(content)

    counts = {"projects": 0, "beats": 0, "intentions": 0, "daily_notes": 0}

    for proj in data.get("projects", []):
        for k in _COMPUTED_FIELDS:
            proj.pop(k, None)
        await project_service.project_repo.upsert(proj)
        counts["projects"] += 1

    for beat in data.get("beats", []):
        for k in _COMPUTED_FIELDS:
            beat.pop(k, None)
        await beat_service.beat_repo.upsert(beat)
        counts["beats"] += 1

    for intention in data.get("intentions", []):
        await intention_repo.upsert(intention)
        counts["intentions"] += 1

    for note in data.get("daily_notes", []):
        await daily_note_repo.upsert_raw(note)
        counts["daily_notes"] += 1

    return {"status": "ok", "imported": counts}
