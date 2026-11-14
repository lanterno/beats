"""Release history (docs/backoffice.md § The pages, Releases): when something
breaks, what shipped just before it.

Three sources, each read on its own so one failing leaves the others
answering, behind one narrow port (`ReleaseSource`):

- **API builds**, newest first, from Cloud Build's `builds.list`, with the
  operator's `roles/cloudbuild.builds.viewer`. A build viewer can read every
  step's arguments; `api/cloudbuild.yaml` holds no secret in them, and a step
  that gained one would hand it to the operator.
- **The web app's live commit**, from the `version.json` its build writes
  (`ui/vite.config.ts`), fetched from the web origin.
- **Commit subjects**, from GitHub's public API, cached per sha for good: a
  commit's subject never changes.

The API's own commit is the operator's image tag, which Terraform gives both
services in one apply: "as deployed", since a revision that failed to become
ready leaves the API on the previous one. Nothing here moves traffic, and
nothing reads the API's Cloud Run service, whose spec carries its secrets.

**Little to configure.** The project and token come from the metadata server;
the web origin and the API's commit are set by Terraform; the repository has
a default. Off Google Cloud the builds answer "unavailable" and the rest still
answers what it can.
"""

import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

import httpx

from beats.operator.health import METADATA, TIMEOUT_SECONDS

CLOUD_BUILD = "https://cloudbuild.googleapis.com/v1"
GITHUB = "https://api.github.com"
CACHE_SECONDS = 60.0
BUILDS_SHOWN = 10
_SHA = re.compile(r"^[0-9a-f]{7,40}$")


@dataclass(frozen=True)
class Build:
    sha: str
    status: str
    created_at: datetime | None
    finished_at: datetime | None
    log_url: str | None


@dataclass(frozen=True)
class ReleaseRow:
    sha: str
    subject: str | None
    status: str
    created_at: datetime | None
    finished_at: datetime | None
    log_url: str | None
    # The commit the API was last deployed with. "As deployed": a revision
    # that never became ready is not caught here.
    live: bool


@dataclass(frozen=True)
class ReleasesReport:
    builds: list[ReleaseRow]
    api_commit: str | None
    web_commit: str | None
    web_subject: str | None
    repository: str
    # Which sources did not answer this time: "builds", "web", "subjects".
    unavailable: list[str] = field(default_factory=list)


class ReleaseSource(Protocol):
    async def builds(self) -> list[Build]: ...
    async def web_commit(self) -> str | None: ...
    async def subject(self, sha: str) -> str | None: ...


def _when(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_builds(body: dict[str, Any]) -> list[Build]:
    """Cloud Build's answer as builds with a commit, newest first. A build
    started by hand with no commit is not a release, and is left out."""
    out = []
    for b in body.get("builds") or []:
        sha = (b.get("substitutions") or {}).get("COMMIT_SHA") or (
            (b.get("source") or {}).get("repoSource") or {}
        ).get("commitSha")
        if not isinstance(sha, str) or not _SHA.match(sha):
            continue
        out.append(
            Build(
                sha=sha,
                status=str(b.get("status", "STATUS_UNKNOWN")),
                created_at=_when(b.get("createTime")),
                finished_at=_when(b.get("finishTime")),
                log_url=b.get("logUrl"),
            )
        )
    out.sort(key=lambda b: b.created_at.isoformat() if b.created_at else "", reverse=True)
    return out


def parse_version(body: object) -> str | None:
    """`version.json`'s sha, or None for anything else — a missing file
    answers the SPA's index.html, which is not JSON with a sha."""
    if isinstance(body, dict):
        sha = body.get("sha")
        if isinstance(sha, str) and _SHA.match(sha):
            return sha
    return None


def assemble(
    builds: list[Build],
    *,
    api_commit: str | None,
    web_commit: str | None,
    subjects: dict[str, str | None],
    repository: str,
    unavailable: list[str],
) -> ReleasesReport:
    """The page's one answer from whatever the sources gave."""
    rows = [
        ReleaseRow(
            sha=b.sha,
            subject=subjects.get(b.sha),
            status=b.status,
            created_at=b.created_at,
            finished_at=b.finished_at,
            log_url=b.log_url,
            live=api_commit is not None and b.sha == api_commit,
        )
        for b in builds[:BUILDS_SHOWN]
    ]
    return ReleasesReport(
        builds=rows,
        api_commit=api_commit,
        web_commit=web_commit,
        web_subject=subjects.get(web_commit) if web_commit else None,
        repository=repository,
        unavailable=unavailable,
    )


class LiveReleases:
    def __init__(
        self,
        *,
        web_origin: str,
        repository: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._web_origin = web_origin.rstrip("/")
        self._repository = repository
        self._transport = transport
        self._project: str | None = None

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=self._transport)

    async def builds(self) -> list[Build]:
        async with self._client() as client:
            meta = {"Metadata-Flavor": "Google"}
            if self._project is None:
                resp = await client.get(f"{METADATA}/project/project-id", headers=meta)
                resp.raise_for_status()
                self._project = resp.text
            resp = await client.get(
                f"{METADATA}/instance/service-accounts/default/token", headers=meta
            )
            resp.raise_for_status()
            token = resp.json()["access_token"]
            resp = await client.get(
                f"{CLOUD_BUILD}/projects/{self._project}/locations/global/builds",
                params={"pageSize": str(BUILDS_SHOWN * 2)},
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            return parse_builds(resp.json())

    async def web_commit(self) -> str | None:
        if not self._web_origin:
            raise LookupError("no web origin configured")
        async with self._client() as client:
            resp = await client.get(f"{self._web_origin}/version.json")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            try:
                return parse_version(resp.json())
            except ValueError:
                return None

    async def subject(self, sha: str) -> str | None:
        async with self._client() as client:
            resp = await client.get(
                f"{GITHUB}/repos/{self._repository}/commits/{sha}",
                headers={"Accept": "application/vnd.github+json"},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            message = ((resp.json().get("commit") or {}).get("message")) or ""
            return message.splitlines()[0] if message else None


class ReleasesCache:
    """Each source's last answer, re-read after the bound; a source that
    fails keeps its last answer and is named in `unavailable`. Subjects are
    kept for good, since a commit's subject never changes."""

    def __init__(self, *, seconds: float = CACHE_SECONDS):
        self._seconds = seconds
        self._read_at = 0.0
        self._builds: list[Build] = []
        self._web: str | None = None
        self._subjects: dict[str, str | None] = {}
        self._unavailable: list[str] = []

    async def report(
        self, source: ReleaseSource, *, api_commit: str | None, repository: str
    ) -> ReleasesReport:
        if self._read_at == 0.0 or time.monotonic() - self._read_at >= self._seconds:
            self._read_at = time.monotonic()
            unavailable: list[str] = []
            try:
                self._builds = await source.builds()
            except Exception:  # noqa: BLE001 — one source failing is a state
                unavailable.append("builds")
            try:
                self._web = await source.web_commit()
            except Exception:  # noqa: BLE001
                unavailable.append("web")
            wanted = {b.sha for b in self._builds[:BUILDS_SHOWN]} | {self._web, api_commit}
            for sha in sorted(s for s in wanted if s and s not in self._subjects):
                try:
                    self._subjects[sha] = await source.subject(sha)
                except Exception:  # noqa: BLE001
                    if "subjects" not in unavailable:
                        unavailable.append("subjects")
                    break  # rate-limited or away: try the rest next time
            self._unavailable = unavailable
        return assemble(
            self._builds,
            api_commit=api_commit,
            web_commit=self._web,
            subjects=self._subjects,
            repository=repository,
            unavailable=self._unavailable,
        )
