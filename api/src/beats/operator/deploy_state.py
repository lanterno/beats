"""The API's deploy state (docs/backoffice.md § The pages, Today): which
revision serves, the commit it runs, and whether the newest revision became
ready.

Read from Cloud Run's v1 API, the reads `decide` makes in
`api/scripts/deploy_lock.sh`, with the operator's `roles/run.viewer` on the
API's service alone (terraform/operator.tf). Reading a revision's spec is safe
since 2026-11-15: the API's secrets moved into Secret Manager, so a spec names
them and holds none, and the revisions from before were deleted
(terraform/README.md § The API's Secrets).

- **The newest revision serving**: its commit is the tag on the service's own
  image, `<registry>/beats-api:<sha>`, as Terraform deploys it.
- **The newest one failed, or is still starting**: traffic stays on the older
  one, whose revision pins its image by digest, and the registry's tags on
  that digest name its commit (`roles/artifactregistry.reader`, which the
  operator holds for its own image). A digest carrying no commit tag, or more
  than one, is an unknown commit, never a guess.

Cached a minute, like health: a Google failure answers the last state and its
age, and with no region configured, or off Google Cloud before any answer,
"unavailable". Nothing here moves traffic.
"""

import asyncio
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol
from urllib.parse import quote

import httpx

from beats.operator.health import CACHE_SECONDS, METADATA, TIMEOUT_SECONDS

ARTIFACT_REGISTRY = "https://artifactregistry.googleapis.com/v1"
# What Terraform tags an image with (`container_image_tag`): a full commit.
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
# `<location>-docker.pkg.dev/<project>/<repository>/<package>@sha256:<hex>`
_DIGEST_REF = re.compile(
    r"^(?P<location>[a-z0-9-]+)-docker\.pkg\.dev/(?P<project>[^/]+)/(?P<repository>[^/]+)/"
    r"(?P<package>[^@]+)@(?P<digest>sha256:[0-9a-f]{64})$"
)

# The newest revision: serving, still starting, or failed to become ready.
Newest = Literal["serving", "starting", "failed"]


@dataclass(frozen=True)
class ServiceView:
    """The service's answer, reduced to what the state is made of."""

    newest: str | None
    serving: str | None
    newest_commit: str | None
    # The service's `Ready` condition: "True", "False", "Unknown", or "".
    ready: str
    ready_since: datetime | None
    # Cloud Run's own words for a condition that is not "True", if any.
    message: str | None


@dataclass(frozen=True)
class DeployState:
    serving_revision: str | None
    serving_commit: str | None
    serving_since: datetime | None
    newest_revision: str | None
    newest_commit: str | None
    newest: Newest | None
    # Why the newest is not serving, in Cloud Run's words, when it says.
    problem: str | None


@dataclass(frozen=True)
class DeployStateReport:
    state: Literal["live", "stale", "unavailable"]
    as_of: datetime | None
    deploy: DeployState | None


class CloudRunSource(Protocol):
    async def service(self) -> dict[str, Any]: ...
    async def revision(self, name: str) -> dict[str, Any]: ...
    async def tags(self, digest_ref: str) -> list[str]: ...


def _when(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def image_commit(image: object) -> str | None:
    """The commit an image reference is tagged with, or None: a digest, a
    `latest`, anything but a full commit after the last ':'."""
    if not isinstance(image, str) or "@" in image or ":" not in image.rsplit("/", 1)[-1]:
        return None
    tag = image.rsplit(":", 1)[-1]
    return tag if _COMMIT.match(tag) else None


def commit_of_tags(tags: list[str]) -> str | None:
    """The one commit among a digest's tags; None for none, or for several,
    which would leave the commit a guess."""
    commits = {t for t in tags if _COMMIT.match(t)}
    return commits.pop() if len(commits) == 1 else None


def parse_service(body: dict[str, Any]) -> ServiceView:
    status = body.get("status") or {}
    conditions = {c.get("type"): c for c in status.get("conditions") or [] if isinstance(c, dict)}
    ready = conditions.get("Ready") or {}
    # A failure is told on `Ready` and on `ConfigurationsReady`; whichever
    # carries words, `Ready` first.
    message = next(
        (
            c.get("message")
            for c in (ready, conditions.get("ConfigurationsReady") or {})
            if c.get("status") != "True" and c.get("message")
        ),
        None,
    )
    containers = (((body.get("spec") or {}).get("template") or {}).get("spec") or {}).get(
        "containers"
    ) or [{}]
    return ServiceView(
        newest=status.get("latestCreatedRevisionName") or None,
        serving=status.get("latestReadyRevisionName") or None,
        newest_commit=image_commit(containers[0].get("image")),
        ready=str(ready.get("status") or ""),
        ready_since=_when(ready.get("lastTransitionTime")),
        message=message,
    )


def newest_state(view: ServiceView) -> Newest | None:
    """Serving when the newest revision is the ready one. Otherwise failed
    when the service says it is not ready, and starting while it does not
    know yet, or still reads ready from the revision before."""
    if view.newest is None:
        return None
    if view.newest == view.serving:
        return "serving"
    return "failed" if view.ready == "False" else "starting"


async def read_deploy_state(source: CloudRunSource) -> DeployState:
    """The service, then the serving revision only when it is not the
    newest: its image is pinned by digest, and the registry names the
    commit. A failure of either read is the whole read's."""
    view = parse_service(await source.service())
    newest = newest_state(view)
    serving_commit = view.newest_commit if newest == "serving" else None
    since = view.ready_since if newest == "serving" else None
    if view.serving is not None and newest != "serving":
        revision = await source.revision(view.serving)
        since = _when((revision.get("metadata") or {}).get("creationTimestamp"))
        digest = (revision.get("status") or {}).get("imageDigest")
        if isinstance(digest, str) and _DIGEST_REF.match(digest):
            serving_commit = commit_of_tags(await source.tags(digest))
    return DeployState(
        serving_revision=view.serving,
        serving_commit=serving_commit,
        serving_since=since,
        newest_revision=view.newest,
        newest_commit=view.newest_commit,
        newest=newest,
        problem=view.message if newest != "serving" else None,
    )


class LiveCloudRun:
    """Cloud Run's v1 API and Artifact Registry's, with a metadata-server
    token: no client library, the image being the API's too."""

    def __init__(
        self, *, service: str, region: str, transport: httpx.AsyncBaseTransport | None = None
    ):
        self._service = service
        self._region = region
        self._transport = transport
        self._project: str | None = None

    async def _get(self, url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        meta = {"Metadata-Flavor": "Google"}
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=self._transport) as client:
            token_url = f"{METADATA}/instance/service-accounts/default/token"
            if self._project is None:
                project, token = await asyncio.gather(
                    client.get(f"{METADATA}/project/project-id", headers=meta),
                    client.get(token_url, headers=meta),
                )
                project.raise_for_status()
                self._project = project.text.strip()
            else:
                token = await client.get(token_url, headers=meta)
            token.raise_for_status()
            resp = await client.get(
                url.format(project=self._project),
                params=params,
                headers={"Authorization": f"Bearer {token.json()['access_token']}"},
            )
            resp.raise_for_status()
            return resp.json()

    def _namespace(self) -> str:
        return (
            f"https://{self._region}-run.googleapis.com/apis/serving.knative.dev/v1"
            "/namespaces/{project}"
        )

    async def service(self) -> dict[str, Any]:
        return await self._get(f"{self._namespace()}/services/{quote(self._service)}")

    async def revision(self, name: str) -> dict[str, Any]:
        return await self._get(f"{self._namespace()}/revisions/{quote(name)}")

    async def tags(self, digest_ref: str) -> list[str]:
        m = _DIGEST_REF.match(digest_ref)
        if m is None:
            return []
        package = (
            f"projects/{m['project']}/locations/{m['location']}/repositories/{m['repository']}"
            f"/packages/{quote(m['package'], safe='')}"
        )
        body = await self._get(
            f"{ARTIFACT_REGISTRY}/{package}/tags",
            params={"filter": f'version="{package}/versions/{m["digest"]}"'},
        )
        return [str(t.get("name", "")).rsplit("/", 1)[-1] for t in body.get("tags") or []]


class DeployStateCache:
    """The last answer, and when. Read again past the bound; if that fails,
    the last state marked stale, or unavailable when there never was one."""

    def __init__(self, *, seconds: float = CACHE_SECONDS):
        self._seconds = seconds
        self._deploy: DeployState | None = None
        self._as_of: datetime | None = None
        self._read_at = 0.0  # monotonic, of the last attempt, success or not
        self._failed = False

    async def report(self, source: CloudRunSource | None) -> DeployStateReport:
        if source is None:
            return DeployStateReport("unavailable", None, None)
        if self._read_at == 0.0 or time.monotonic() - self._read_at >= self._seconds:
            self._read_at = time.monotonic()
            try:
                self._deploy = await read_deploy_state(source)
                self._as_of = datetime.now(UTC)
                self._failed = False
            except Exception:  # noqa: BLE001 — a Google failure is a state, not a crash
                self._failed = True
        if self._deploy is None:
            return DeployStateReport("unavailable", None, None)
        return DeployStateReport("stale" if self._failed else "live", self._as_of, self._deploy)
