"""Telling customers what is happening (docs/status-page.md).

One public JSON file, `status.json`, in a small Cloud Storage bucket of its
own: the current state, a short message, what is affected, and the last
posts. The page at `lifepete.com/status` and the SPA's banner read that file
and nothing else, so both still work when the API is down — the only time
they matter. Written whole each time, by `status.publish` and `status.clear`
through the runner, with `ifGenerationMatch` so two writes cannot silently
lose one, and with `Cache-Control: public, max-age=30`, because Cloud
Storage's default for a public object is an hour of caching and "we're back"
must not arrive an hour late.

**Nothing about a person in a post** — the file is public and keeps its
history — and no email, no push, no third-party status page.

The bucket is named by `OPERATOR_STATUS_BUCKET`, set by Terraform; unset, the
commands answer 409 `STATUS_UNAVAILABLE` and the back office says so.
"""

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal, Protocol, get_args

import httpx

from beats.domain.exceptions import DomainException
from beats.operator.health import METADATA, TIMEOUT_SECONDS

STORAGE = "https://storage.googleapis.com"
OBJECT = "status.json"
CACHE_CONTROL = "public, max-age=30"
POSTS_KEPT = 20
MESSAGE_MAX = 280

State = Literal["operational", "degraded", "outage", "maintenance"]
Part = Literal["web app", "api", "sign-in", "coach", "integrations", "phone apps"]
STATES: tuple[str, ...] = get_args(State)
PARTS: tuple[str, ...] = get_args(Part)


@dataclass(frozen=True)
class Post:
    at: str  # ISO, UTC
    state: str
    message: str
    affected: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StatusDoc:
    state: str
    message: str
    affected: list[str]
    updated_at: str
    posts: list[Post] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=1, ensure_ascii=False) + "\n"


OPERATIONAL = StatusDoc(
    state="operational", message="", affected=[], updated_at="1970-01-01T00:00:00+00:00"
)


def parse(text: str) -> StatusDoc | None:
    try:
        raw = json.loads(text)
        return StatusDoc(
            state=str(raw["state"]),
            message=str(raw.get("message", "")),
            affected=[str(a) for a in raw.get("affected", [])],
            updated_at=str(raw["updated_at"]),
            posts=[
                Post(
                    at=str(p["at"]),
                    state=str(p["state"]),
                    message=str(p.get("message", "")),
                    affected=[str(a) for a in p.get("affected", [])],
                )
                for p in raw.get("posts", [])
            ],
        )
    except ValueError, KeyError, TypeError, AttributeError:
        return None


def next_doc(
    current: StatusDoc | None, *, state: str, message: str, affected: list[str], now: datetime
) -> StatusDoc:
    """The file as it will be after a post: the new state on top, the post
    prepended, and only the last `POSTS_KEPT` kept."""
    at = now.isoformat()
    post = Post(at=at, state=state, message=message, affected=list(affected))
    posts = [post, *(current.posts if current else [])][:POSTS_KEPT]
    return StatusDoc(
        state=state, message=message, affected=list(affected), updated_at=at, posts=posts
    )


class StatusUnavailable(DomainException):
    status_code = 409
    code = "STATUS_UNAVAILABLE"
    message = "No status bucket is configured for this deployment"


class StatusConflict(DomainException):
    """Somebody else published between the read and the write. Read again
    and publish again: nothing was lost, nothing was overwritten."""

    status_code = 409
    code = "STATUS_CONFLICT"
    message = "The status file changed under you; read it again and publish again"


class StatusStore(Protocol):
    async def read(self) -> tuple[StatusDoc | None, int]:
        """The file and its generation; (None, 0) when there is none."""
        ...

    async def write(self, doc: StatusDoc, *, if_generation_match: int) -> None:
        """Raises StatusConflict when the generation moved."""
        ...


class GcsStatusStore:
    def __init__(self, bucket: str, *, transport: httpx.AsyncBaseTransport | None = None):
        self._bucket = bucket
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=self._transport)

    async def _token(self, client: httpx.AsyncClient) -> dict[str, str]:
        resp = await client.get(
            f"{METADATA}/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"},
        )
        resp.raise_for_status()
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    async def read(self) -> tuple[StatusDoc | None, int]:
        async with self._client() as client:
            headers = await self._token(client)
            meta = await client.get(
                f"{STORAGE}/storage/v1/b/{self._bucket}/o/{OBJECT}", headers=headers
            )
            if meta.status_code == 404:
                return None, 0
            meta.raise_for_status()
            generation = int(meta.json()["generation"])
            body = await client.get(
                f"{STORAGE}/storage/v1/b/{self._bucket}/o/{OBJECT}",
                params={"alt": "media", "generation": str(generation)},
                headers=headers,
            )
            body.raise_for_status()
            return parse(body.text), generation

    async def write(self, doc: StatusDoc, *, if_generation_match: int) -> None:
        boundary = "beats-status-boundary"
        metadata = json.dumps({"name": OBJECT, "cacheControl": CACHE_CONTROL})
        body = (
            f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{metadata}\r\n"
            f"--{boundary}\r\nContent-Type: application/json\r\n\r\n{doc.to_json()}\r\n"
            f"--{boundary}--"
        ).encode()
        async with self._client() as client:
            resp = await client.post(
                f"{STORAGE}/upload/storage/v1/b/{self._bucket}/o",
                params={"uploadType": "multipart", "ifGenerationMatch": str(if_generation_match)},
                content=body,
                headers={
                    **await self._token(client),
                    "Content-Type": f"multipart/related; boundary={boundary}",
                },
            )
            if resp.status_code == 412:
                raise StatusConflict()
            resp.raise_for_status()


class MemoryStatusStore:
    """For tests and local development: the file in memory, with a
    generation that moves on every write."""

    def __init__(self):
        self.doc: StatusDoc | None = None
        self.generation = 0
        self.writes = 0

    async def read(self) -> tuple[StatusDoc | None, int]:
        return self.doc, self.generation

    async def write(self, doc: StatusDoc, *, if_generation_match: int) -> None:
        if if_generation_match != self.generation:
            raise StatusConflict()
        self.doc = doc
        self.generation += 1
        self.writes += 1


async def publish(
    store: StatusStore, *, state: str, message: str, affected: list[str], now: datetime
) -> StatusDoc:
    current, generation = await store.read()
    doc = next_doc(current, state=state, message=message, affected=affected, now=now)
    await store.write(doc, if_generation_match=generation)
    return doc


def state_of(doc: StatusDoc | None) -> dict[str, Any]:
    """What `describe()` and the back office's panel read."""
    if doc is None:
        return {"state": "operational", "message": "", "affected": [], "published": False}
    return {
        "state": doc.state,
        "message": doc.message,
        "affected": doc.affected,
        "updated_at": doc.updated_at,
        "published": True,
    }


def now_utc() -> datetime:
    return datetime.now(UTC)
