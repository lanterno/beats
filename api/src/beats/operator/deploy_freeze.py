"""The deploy freeze (docs/backoffice.md § Deploy freeze): during an incident,
stop a merge from shipping on top of it.

The flag is one object, `freeze`, in a small private bucket of its own —
**never the Terraform state bucket**, which holds `JWT_SECRET` and on which
the operator must never hold a grant. The operator writes it through
`deploy.freeze` and `deploy.unfreeze` (the runner, like every mutation); the
API's build reads it in `decide` (`api/scripts/deploy_lock.sh`) and, while it
is in force, skips the apply and goes red.

The object is lines of `key=value`, so the build reads it with `grep`:
`until` (ISO), `until_epoch` (what the build compares), `set_by`, `set_at`
and `reason`. An expired flag reads as no freeze, so nothing clears it.

The bucket is named by `OPERATOR_FREEZE_BUCKET`, set by Terraform; unset,
the commands answer 409 `FREEZE_UNAVAILABLE` and the page says so.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

import httpx

from beats.domain.exceptions import DomainException
from beats.operator.health import METADATA, TIMEOUT_SECONDS

STORAGE = "https://storage.googleapis.com"
OBJECT = "freeze"


@dataclass(frozen=True)
class Freeze:
    until: datetime
    reason: str
    set_by: str
    set_at: datetime

    def in_force(self, now: datetime) -> bool:
        return self.until > now


class FreezeUnavailable(DomainException):
    status_code = 409
    code = "FREEZE_UNAVAILABLE"
    message = "No freeze bucket is configured for this deployment"


class DeployFreeze(Protocol):
    async def get(self) -> Freeze | None: ...
    async def set(self, freeze: Freeze) -> None: ...
    async def clear(self) -> None: ...


def render(freeze: Freeze) -> str:
    """The flag as the build reads it. The reason is the operator's own
    words and goes on one line: a newline in it could forge a key."""
    reason = " ".join(freeze.reason.split())
    return (
        f"until={freeze.until.isoformat()}\n"
        f"until_epoch={int(freeze.until.timestamp())}\n"
        f"set_by={freeze.set_by}\n"
        f"set_at={freeze.set_at.isoformat()}\n"
        f"reason={reason}\n"
    )


def parse(text: str) -> Freeze | None:
    """The flag back, or None for anything the build would not take as a
    freeze either."""
    values = dict(line.split("=", 1) for line in text.splitlines() if "=" in line)
    try:
        return Freeze(
            until=datetime.fromtimestamp(int(values["until_epoch"]), UTC),
            reason=values.get("reason", ""),
            set_by=values.get("set_by", ""),
            set_at=datetime.fromisoformat(values["set_at"]),
        )
    except KeyError, ValueError:
        return None


class GcsDeployFreeze:
    """The flag in Cloud Storage, over the JSON API with a metadata-server
    token: no client library, the image being the API's too."""

    def __init__(self, bucket: str, *, transport: httpx.AsyncBaseTransport | None = None):
        self._bucket = bucket
        self._transport = transport

    async def _token(self, client: httpx.AsyncClient) -> dict[str, str]:
        resp = await client.get(
            f"{METADATA}/instance/service-accounts/default/token",
            headers={"Metadata-Flavor": "Google"},
        )
        resp.raise_for_status()
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=self._transport)

    async def get(self) -> Freeze | None:
        async with self._client() as client:
            resp = await client.get(
                f"{STORAGE}/storage/v1/b/{self._bucket}/o/{OBJECT}",
                params={"alt": "media"},
                headers=await self._token(client),
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return parse(resp.text)

    async def set(self, freeze: Freeze) -> None:
        async with self._client() as client:
            resp = await client.post(
                f"{STORAGE}/upload/storage/v1/b/{self._bucket}/o",
                params={"uploadType": "media", "name": OBJECT},
                content=render(freeze).encode(),
                headers={**await self._token(client), "Content-Type": "text/plain"},
            )
            resp.raise_for_status()

    async def clear(self) -> None:
        async with self._client() as client:
            resp = await client.delete(
                f"{STORAGE}/storage/v1/b/{self._bucket}/o/{OBJECT}",
                headers=await self._token(client),
            )
            if resp.status_code != 404:
                resp.raise_for_status()
