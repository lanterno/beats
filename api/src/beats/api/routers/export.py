"""Export API router — CSV and JSON data export/import."""

import csv
import io
import json
from datetime import UTC, datetime

from fastapi import APIRouter, Query, UploadFile
from fastapi.responses import StreamingResponse

from beats.api.dependencies import (
    BeatServiceDep,
    ProjectServiceDep,
)

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
):
    """Export everything as JSON for backup."""
    beats = await beat_service.beat_repo.list()
    projects = await project_service.project_repo.list()
    data = {
        "exported_at": datetime.now(UTC).isoformat(),
        "version": "1.0",
        "projects": [p.model_dump(mode="json") for p in projects],
        "beats": [b.model_dump(mode="json") for b in beats],
    }

    output = json.dumps(data, indent=2, default=str)
    filename = f"beats_backup_{datetime.now(UTC).strftime('%Y%m%d')}.json"
    return StreamingResponse(
        iter([output]),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
async def import_full_json(
    file: UploadFile,
    beat_service: BeatServiceDep,
    project_service: ProjectServiceDep,
):
    """Import a full JSON backup. Upserts by ID — safe to re-import."""
    content = await file.read()
    data = json.loads(content)

    counts = {"projects": 0, "beats": 0}

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

    return {"status": "ok", "imported": counts}
