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
  commit's subject never changes. A commit GitHub does not know is cached as
  unknown, so it is asked about once.

The API's own commit is the operator's image tag, which Terraform gives both
services in one apply: "as deployed", since a revision that failed to become
ready leaves the API on the previous one. A tag that is not a sha (a hand
`terraform apply` leaves `container_image_tag` at its default, `latest`)
reads as unknown and is never sent to GitHub. Nothing here moves traffic, and
nothing reads the API's Cloud Run service, whose spec carries its secrets.

**Read at once.** The three sources are asked side by side, and the subjects
the builds bring with them likewise, over one long-lived client, so a page's
first fill waits for the slowest answer rather than the sum of them. A
subject that fails leaves the others to answer; GitHub saying it is rate
limited quiets every subject until the time it names, since the address is
Cloud Run's, shared, and the unauthenticated limit is 60 an hour.

**Little to configure.** The project and token come from the metadata server;
the web origin and the API's commit are set by Terraform; the repository has
a default. Off Google Cloud the builds answer "unavailable" and the rest still
answers what it can.
"""

import asyncio
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


class GitHubRateLimited(Exception):
    """GitHub said to stop asking until `until` (epoch seconds)."""

    def __init__(self, until: float):
        super().__init__(f"GitHub is rate limiting until {until:.0f}")
        self.until = until


def quiet_until(headers: httpx.Headers, now: float) -> float | None:
    """When GitHub's answer says asking may start again, or None when it is
    not a rate limit: `retry-after` for its secondary limits, the reset of
    an exhausted primary limit otherwise."""
    retry = headers.get("retry-after", "")
    if retry.isdigit():
        return now + int(retry)
    reset = headers.get("x-ratelimit-reset", "")
    if headers.get("x-ratelimit-remaining") == "0" and reset.isdigit():
        return float(reset)
    return None


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


def commit_or_none(value: str | None) -> str | None:
    """A commit sha, or None for anything else — `latest`, a branch, an
    empty setting. Nothing that is not a sha is shown as a commit, linked
    to one, or asked of GitHub."""
    return value if value and _SHA.match(value) else None


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
        self._http: httpx.AsyncClient | None = None

    def _client(self) -> httpx.AsyncClient:
        """One client for every call this source makes, opened on first use
        and kept: its connections are reused across the sources, the
        subjects and the minutes between refreshes."""
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=self._transport)
        return self._http

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()

    async def builds(self) -> list[Build]:
        client = self._client()
        meta = {"Metadata-Flavor": "Google"}
        token_url = f"{METADATA}/instance/service-accounts/default/token"
        if self._project is None:
            project, token = await asyncio.gather(
                client.get(f"{METADATA}/project/project-id", headers=meta),
                client.get(token_url, headers=meta),
            )
            project.raise_for_status()
            self._project = project.text
        else:
            token = await client.get(token_url, headers=meta)
        token.raise_for_status()
        resp = await client.get(
            f"{CLOUD_BUILD}/projects/{self._project}/locations/global/builds",
            params={"pageSize": str(BUILDS_SHOWN * 2)},
            headers={"Authorization": f"Bearer {token.json()['access_token']}"},
        )
        resp.raise_for_status()
        return parse_builds(resp.json())

    async def web_commit(self) -> str | None:
        if not self._web_origin:
            raise LookupError("no web origin configured")
        resp = await self._client().get(f"{self._web_origin}/version.json")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        try:
            return parse_version(resp.json())
        except ValueError:
            return None

    async def subject(self, sha: str) -> str | None:
        resp = await self._client().get(
            f"{GITHUB}/repos/{self._repository}/commits/{sha}",
            headers={"Accept": "application/vnd.github+json"},
        )
        # GitHub answers 404 for a repository it cannot find and 422 ("No
        # commit found for SHA") for a ref the repository does not have:
        # both mean there is no subject to show, now or later.
        if resp.status_code in (404, 422):
            return None
        if resp.status_code in (403, 429):
            until = quiet_until(resp.headers, time.time())
            if until is not None:
                raise GitHubRateLimited(until)
        resp.raise_for_status()
        message = ((resp.json().get("commit") or {}).get("message")) or ""
        return message.splitlines()[0] if message else None


class ReleasesCache:
    """Each source's last answer, re-read after the bound; a source that
    fails keeps its last answer and is named in `unavailable`. Subjects are
    kept for good, since a commit's subject never changes; one that fails
    is asked again at the next refresh, and holds up none of the others."""

    def __init__(self, *, seconds: float = CACHE_SECONDS):
        self._seconds = seconds
        self._read_at = 0.0
        self._builds: list[Build] = []
        self._web: str | None = None
        self._subjects: dict[str, str | None] = {}
        self._unavailable: list[str] = []
        # Epoch seconds before which GitHub is not asked (GitHubRateLimited).
        self._github_quiet_until = 0.0

    async def report(
        self, source: ReleaseSource, *, api_commit: str | None, repository: str
    ) -> ReleasesReport:
        api_commit = commit_or_none(api_commit)
        if self._read_at == 0.0 or time.monotonic() - self._read_at >= self._seconds:
            self._read_at = time.monotonic()
            unavailable: list[str] = []
            builds, web = await asyncio.gather(
                source.builds(), source.web_commit(), return_exceptions=True
            )
            # One source failing is a state: it keeps its last answer.
            if isinstance(builds, BaseException):
                unavailable.append("builds")
            else:
                self._builds = builds
            if isinstance(web, BaseException):
                unavailable.append("web")
            else:
                self._web = web
            wanted = {b.sha for b in self._builds[:BUILDS_SHOWN]} | {self._web, api_commit}
            todo = sorted(s for s in wanted if s and s not in self._subjects)
            if todo and time.time() < self._github_quiet_until:
                unavailable.append("subjects")
            elif todo:
                answers = await asyncio.gather(
                    *(source.subject(sha) for sha in todo), return_exceptions=True
                )
                for sha, answer in zip(todo, answers, strict=True):
                    if isinstance(answer, GitHubRateLimited):
                        self._github_quiet_until = max(self._github_quiet_until, answer.until)
                    if isinstance(answer, BaseException):
                        if "subjects" not in unavailable:
                            unavailable.append("subjects")
                    else:
                        self._subjects[sha] = answer
            self._unavailable = unavailable
        return assemble(
            self._builds,
            api_commit=api_commit,
            web_commit=self._web,
            subjects=self._subjects,
            repository=repository,
            unavailable=self._unavailable,
        )
