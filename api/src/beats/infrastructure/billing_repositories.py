"""Persistence for the billing collections (docs/billing.md).

Split out of `repositories.py` at the size ceiling (CLAUDE.md § Conventions).
Billing is never a field of `Project` or `Beat`: clients, project billing,
billable overrides, billing budgets and report links are their own
collections, and so their own repositories.
"""

import builtins
from collections.abc import Iterable
from typing import NamedTuple, Protocol

from bson import ObjectId
from bson.errors import InvalidId
from pymongo import ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection

from beats.domain.exceptions import (
    ClientNotFound,
)
from beats.domain.models import (
    BillableOverride,
    BillingBudget,
    BillingBudgetScope,
    Client,
    ProjectBilling,
    ReportLink,
)
from beats.infrastructure.repositories import (
    MongoStore,
    serialize_from_document,
)


class ClientRepository(Protocol):
    async def get_by_id(self, client_id: str) -> Client: ...
    async def list(self, archived: bool = False) -> builtins.list[Client]: ...
    async def list_all(self) -> builtins.list[Client]: ...
    async def create(self, client: Client) -> Client: ...
    async def update(self, client: Client) -> Client: ...
    async def delete(self, client_id: str) -> bool: ...
    async def restore(self, client: Client) -> None: ...
    async def ids_held_elsewhere(self, ids: Iterable[str]) -> set[str]: ...


class MongoClientRepository(MongoStore[Client], ClientRepository):
    model = Client

    async def get_by_id(self, client_id: str) -> Client:
        # A malformed id is "no such client", like an unknown one: every route
        # under /api/clients/{id} takes it from the path and answers 404.
        try:
            oid = ObjectId(client_id)
        except InvalidId:
            raise ClientNotFound(client_id) from None
        client = await self._find_one({"_id": oid})
        if client is None:
            raise ClientNotFound(client_id)
        return client

    async def list(self, archived: bool = False) -> builtins.list[Client]:
        return await self._find_many({"archived": archived})

    async def list_all(self) -> builtins.list[Client]:
        # Archived too, for a report — an archived client keeps the months it
        # has hours in — and for the full export.
        return await self._find_many()

    async def create(self, client: Client) -> Client:
        return await self._insert(client)

    async def update(self, client: Client) -> Client:
        return await self._replace(client.id, client)

    async def delete(self, client_id: str) -> bool:
        try:
            oid = ObjectId(client_id)
        except InvalidId:
            return False
        return await self._delete_one({"_id": oid})

    async def restore(self, client: Client) -> None:
        """Write a client read from a backup, keeping its id, as
        `MongoBeatRepository.restore` writes a beat: a replace that inserts
        when there is none, scoped to this user."""
        if client.id is None:
            await self._insert(client)
            return
        await self.collection.replace_one(
            self._q({"_id": ObjectId(client.id)}), self._dump(client), upsert=True
        )

    async def ids_held_elsewhere(self, ids: Iterable[str]) -> set[str]:
        return await self._ids_held_elsewhere(ids)


class ProjectBillingRepository(Protocol):
    async def get(self, project_id: str) -> ProjectBilling | None: ...
    async def exists(self, project_id: str) -> bool: ...
    async def list_all(self) -> list[ProjectBilling]: ...
    async def list_by_client(self, client_id: str) -> list[ProjectBilling]: ...
    async def upsert(self, billing: ProjectBilling) -> ProjectBilling: ...
    async def delete(self, project_id: str) -> bool: ...


class MongoProjectBillingRepository(MongoStore[ProjectBilling], ProjectBillingRepository):
    model = ProjectBilling

    async def get(self, project_id: str) -> ProjectBilling | None:
        return await self._find_one({"project_id": project_id})

    async def exists(self, project_id: str) -> bool:
        doc = await self.collection.find_one(self._q({"project_id": project_id}), {"_id": 1})
        return doc is not None

    async def list_all(self) -> list[ProjectBilling]:
        return await self._find_many()

    async def list_by_client(self, client_id: str) -> list[ProjectBilling]:
        return await self._find_many({"client_id": client_id})

    async def upsert(self, billing: ProjectBilling) -> ProjectBilling:
        # A replace, as an absence's: the document IS the billing, so a term
        # left out of the new list must not survive in the old one. The
        # (user, project) unique index makes this filter its identity.
        data = self._dump(billing)
        data.pop("_id", None)
        result = await self.collection.find_one_and_replace(
            self._q({"project_id": data["project_id"]}),
            data,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise RuntimeError("upsert of ProjectBilling returned no document")
        return self._load(result)

    async def delete(self, project_id: str) -> bool:
        return await self._delete_one({"project_id": project_id})


class BillingBudgetRepository(Protocol):
    async def list_all(self) -> list[BillingBudget]: ...
    async def get(self, scope: BillingBudgetScope, scope_id: str) -> BillingBudget | None: ...
    async def upsert(self, budget: BillingBudget) -> BillingBudget: ...
    async def delete(self, scope: BillingBudgetScope, scope_id: str) -> bool: ...


class MongoBillingBudgetRepository(MongoStore[BillingBudget], BillingBudgetRepository):
    model = BillingBudget

    async def list_all(self) -> list[BillingBudget]:
        return await self._find_many()

    async def get(self, scope: BillingBudgetScope, scope_id: str) -> BillingBudget | None:
        return await self._find_one({"scope": scope.value, "scope_id": scope_id})

    async def upsert(self, budget: BillingBudget) -> BillingBudget:
        # A replace, as a project's billing: the document IS the budget, so a
        # limit in the unit it no longer has must not survive. The (user,
        # scope, scope id) unique index makes this filter its identity.
        data = self._dump(budget)
        data.pop("_id", None)
        result = await self.collection.find_one_and_replace(
            self._q({"scope": data["scope"], "scope_id": data["scope_id"]}),
            data,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise RuntimeError("upsert of BillingBudget returned no document")
        return self._load(result)

    async def delete(self, scope: BillingBudgetScope, scope_id: str) -> bool:
        return await self._delete_one({"scope": scope.value, "scope_id": scope_id})


class BillableOverrideRepository(Protocol):
    async def list_all(self) -> list[BillableOverride]: ...
    async def list_for(self, beat_ids: Iterable[str]) -> list[BillableOverride]: ...
    async def upsert(self, override: BillableOverride) -> BillableOverride: ...
    async def delete(self, beat_id: str) -> bool: ...


class MongoBillableOverrideRepository(MongoStore[BillableOverride], BillableOverrideRepository):
    model = BillableOverride

    async def list_all(self) -> list[BillableOverride]:
        return await self._find_many()

    async def list_for(self, beat_ids: Iterable[str]) -> list[BillableOverride]:
        ids = list(beat_ids)
        if not ids:
            return []
        return await self._find_many({"beat_id": {"$in": ids}})

    async def upsert(self, override: BillableOverride) -> BillableOverride:
        # A replace keyed on the beat, which the (user, beat) unique index
        # makes the document's identity.
        data = self._dump(override)
        data.pop("_id", None)
        result = await self.collection.find_one_and_replace(
            self._q({"beat_id": data["beat_id"]}),
            data,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            raise RuntimeError("upsert of BillableOverride returned no document")
        return self._load(result)

    async def delete(self, beat_id: str) -> bool:
        return await self._delete_one({"beat_id": beat_id})


class ReportLinkRepository(Protocol):
    async def list_for_client(self, client_id: str) -> list[ReportLink]: ...
    async def create(self, link: ReportLink) -> ReportLink: ...
    async def delete(self, client_id: str, link_id: str) -> bool: ...
    async def delete_for_client(self, client_id: str) -> int: ...


class MongoReportLinkRepository(MongoStore[ReportLink], ReportLinkRepository):
    """The owner's side of report links: list, mint and revoke. User-scoped
    like every other billing collection. The public read goes through
    `MongoReportLinkLookup`, which is not."""

    model = ReportLink

    async def list_for_client(self, client_id: str) -> list[ReportLink]:
        return await self._find_many({"client_id": client_id}, sort=("created_at", -1))

    async def create(self, link: ReportLink) -> ReportLink:
        return await self._insert(link)

    async def delete(self, client_id: str, link_id: str) -> bool:
        # Keyed on the client as well as the id, so a link cannot be revoked
        # through the wrong client's path. A malformed id is "no such link",
        # as an unknown one is: the route answers 204 either way, since with
        # no link there is nothing left to clear.
        try:
            oid = ObjectId(link_id)
        except InvalidId:
            return False
        return await self._delete_one({"_id": oid, "client_id": client_id})

    async def delete_for_client(self, client_id: str) -> int:
        """Every link on one client, for when the client is deleted: a link
        whose client has gone would serve nothing, and must not linger as a
        live URL."""
        result = await self.collection.delete_many(self._q({"client_id": client_id}))
        return result.deleted_count


class OwnedReportLink(NamedTuple):
    """A resolved token: the link, and the account whose hours it serves.

    The owner is carried beside the link rather than on it because
    `user_id` is a column of every document and a field of no model — the
    scoping lives in `MongoStore`, not in the domain.
    """

    link: ReportLink
    user_id: str


class ReportLinkLookup(Protocol):
    async def find_by_token(self, token: str) -> OwnedReportLink | None: ...


class MongoReportLinkLookup(ReportLinkLookup):
    """Not user-scoped: the public report endpoint has no session, and the
    owner is not known until the token resolves. This is the only read in the
    system whose `user_id` comes from a stored record rather than a token —
    see the call site in `api/routers/reports.py`.
    """

    def __init__(self, collection: AsyncCollection):
        self.collection = collection

    async def find_by_token(self, token: str) -> OwnedReportLink | None:
        # An exact match on the unique-indexed token. No regex, no prefix: the
        # token is the whole secret and nothing about it is guessed at here.
        doc = await self.collection.find_one({"token": token})
        if not doc:
            return None
        owner = doc.get("user_id")
        if not isinstance(owner, str):
            # A link with no owner can serve nothing, and guessing one would
            # be the worst possible guess. Treat it as no link at all.
            return None
        return OwnedReportLink(ReportLink(**serialize_from_document(doc)), owner)
