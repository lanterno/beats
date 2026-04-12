"""Credential storage for WebAuthn credentials (MongoDB)."""

import logging
from datetime import datetime
from typing import Any

from motor.motor_asyncio import AsyncIOMotorCollection
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class StoredCredential(BaseModel):
    """A stored WebAuthn credential."""

    credential_id: str  # Base64URL encoded
    public_key: str  # Base64URL encoded
    sign_count: int
    created_at: str
    device_name: str | None = None


class MongoCredentialStorage:
    """MongoDB-backed storage for WebAuthn credentials (multi-user)."""

    def __init__(self, collection: AsyncIOMotorCollection):
        self.collection = collection

    async def is_registered(self, user_id: str | None = None) -> bool:
        """Check if any credentials are registered, optionally for a specific user."""
        query: dict[str, Any] = {}
        if user_id:
            query["user_id"] = user_id
        return await self.collection.count_documents(query) > 0

    async def get_credentials(self, user_id: str | None = None) -> list[StoredCredential]:
        """Get stored credentials, optionally filtered by user."""
        query: dict[str, Any] = {}
        if user_id:
            query["user_id"] = user_id
        cursor = self.collection.find(query)
        docs = await cursor.to_list(length=None)
        return [
            StoredCredential(
                credential_id=doc["credential_id"],
                public_key=doc["public_key"],
                sign_count=doc["sign_count"],
                created_at=doc["created_at"],
                device_name=doc.get("device_name"),
            )
            for doc in docs
        ]

    async def get_credential_by_id(self, credential_id: str) -> StoredCredential | None:
        """Get a credential by its ID (user-agnostic for login)."""
        doc = await self.collection.find_one({"credential_id": credential_id})
        if not doc:
            return None
        return StoredCredential(
            credential_id=doc["credential_id"],
            public_key=doc["public_key"],
            sign_count=doc["sign_count"],
            created_at=doc["created_at"],
            device_name=doc.get("device_name"),
        )

    async def get_user_id_for_credential(self, credential_id: str) -> str | None:
        """Get the user_id that owns a credential."""
        doc = await self.collection.find_one({"credential_id": credential_id})
        if not doc:
            return None
        return doc["user_id"]

    async def save_credential(
        self,
        user_id: str,
        credential_id: str,
        public_key: str,
        sign_count: int,
        device_name: str | None = None,
    ) -> StoredCredential:
        """Save a new credential for a user."""
        credential = StoredCredential(
            credential_id=credential_id,
            public_key=public_key,
            sign_count=sign_count,
            created_at=datetime.now().isoformat(),
            device_name=device_name,
        )
        await self.collection.insert_one(
            {
                "user_id": user_id,
                "credential_id": credential_id,
                "public_key": public_key,
                "sign_count": sign_count,
                "created_at": credential.created_at,
                "device_name": device_name,
            }
        )
        logger.info(f"Saved new credential for user {user_id}: {credential_id[:20]}...")
        return credential

    async def update_sign_count(self, credential_id: str, new_sign_count: int) -> bool:
        """Update the sign count for a credential (replay attack prevention)."""
        result = await self.collection.update_one(
            {"credential_id": credential_id},
            {"$set": {"sign_count": new_sign_count}},
        )
        if result.modified_count > 0:
            logger.debug(f"Updated sign count for {credential_id[:20]}... to {new_sign_count}")
            return True
        return False

    async def delete_credential(self, credential_id: str, user_id: str) -> bool:
        """Delete a credential by its ID, scoped to the owning user."""
        result = await self.collection.delete_one(
            {"credential_id": credential_id, "user_id": user_id}
        )
        if result.deleted_count > 0:
            logger.info(f"Deleted credential: {credential_id[:20]}...")
            return True
        return False

    async def count_credentials(self, user_id: str) -> int:
        """Count the number of credentials for a user."""
        return await self.collection.count_documents({"user_id": user_id})

    async def get_credential_ids(self, user_id: str | None = None) -> list[str]:
        """Get all credential IDs, optionally filtered by user."""
        creds = await self.get_credentials(user_id)
        return [c.credential_id for c in creds]
