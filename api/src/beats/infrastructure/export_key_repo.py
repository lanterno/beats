"""Persist per-user Ed25519 keypairs used for signing exports.

Storage model: one document per user, lazily created on first export. The
private key is stored as raw 32 bytes — this is the v1 posture. A follow-up
will wrap it with server-side KMS (the v1 plan acknowledges this trade-off).
"""

from __future__ import annotations

from datetime import UTC, datetime

from bson.binary import Binary
from motor.motor_asyncio import AsyncIOMotorDatabase

from beats.domain.export_signing import generate_keypair

COLLECTION = "export_keys"


class ExportKeyRepository:
    def __init__(self, db: AsyncIOMotorDatabase, user_id: str) -> None:
        self._col = db[COLLECTION]
        self._user_id = user_id

    async def get_or_create(self) -> tuple[bytes, bytes]:
        """Return the user's `(private, public)` keypair, generating once."""
        doc = await self._col.find_one({"user_id": self._user_id})
        if doc is not None:
            return bytes(doc["private_key"]), bytes(doc["public_key"])

        private_bytes, public_bytes = generate_keypair()
        await self._col.insert_one(
            {
                "user_id": self._user_id,
                "private_key": Binary(private_bytes),
                "public_key": Binary(public_bytes),
                "created_at": datetime.now(UTC),
            },
        )
        return private_bytes, public_bytes

    async def get_public(self) -> bytes | None:
        doc = await self._col.find_one({"user_id": self._user_id})
        if doc is None:
            return None
        return bytes(doc["public_key"])
