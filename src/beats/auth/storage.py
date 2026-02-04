"""File-based credential storage for WebAuthn credentials."""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class StoredCredential(BaseModel):
    """A stored WebAuthn credential."""

    credential_id: str  # Base64URL encoded
    public_key: str  # Base64URL encoded
    sign_count: int
    created_at: str
    device_name: str | None = None


class CredentialData(BaseModel):
    """Root structure for credentials.json."""

    user_id: str = "owner"
    credentials: list[StoredCredential] = []


class CredentialStorage:
    """File-based storage for WebAuthn credentials."""

    def __init__(self, file_path: Path | str):
        self.file_path = Path(file_path)
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        """Create the credentials file if it doesn't exist."""
        if not self.file_path.exists():
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self._save(CredentialData())
            logger.info(f"Created credentials file at {self.file_path}")

    def _load(self) -> CredentialData:
        """Load credentials from file."""
        try:
            with open(self.file_path) as f:
                data = json.load(f)
            return CredentialData.model_validate(data)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning(f"Failed to load credentials: {e}, returning empty data")
            return CredentialData()

    def _save(self, data: CredentialData) -> None:
        """Save credentials to file."""
        with open(self.file_path, "w") as f:
            json.dump(data.model_dump(), f, indent=2)

    def is_registered(self) -> bool:
        """Check if any credentials are registered."""
        data = self._load()
        return len(data.credentials) > 0

    def get_credentials(self) -> list[StoredCredential]:
        """Get all stored credentials."""
        data = self._load()
        return data.credentials

    def get_credential_by_id(self, credential_id: str) -> StoredCredential | None:
        """Get a credential by its ID."""
        data = self._load()
        for cred in data.credentials:
            if cred.credential_id == credential_id:
                return cred
        return None

    def save_credential(
        self,
        credential_id: str,
        public_key: str,
        sign_count: int,
        device_name: str | None = None,
    ) -> StoredCredential:
        """Save a new credential."""
        data = self._load()

        credential = StoredCredential(
            credential_id=credential_id,
            public_key=public_key,
            sign_count=sign_count,
            created_at=datetime.now().isoformat(),
            device_name=device_name,
        )

        data.credentials.append(credential)
        self._save(data)
        logger.info(f"Saved new credential: {credential_id[:20]}...")
        return credential

    def update_sign_count(self, credential_id: str, new_sign_count: int) -> bool:
        """Update the sign count for a credential (replay attack prevention)."""
        data = self._load()
        for cred in data.credentials:
            if cred.credential_id == credential_id:
                cred.sign_count = new_sign_count
                self._save(data)
                logger.debug(f"Updated sign count for {credential_id[:20]}... to {new_sign_count}")
                return True
        return False

    def delete_credential(self, credential_id: str) -> bool:
        """Delete a credential by its ID."""
        data = self._load()
        original_len = len(data.credentials)
        data.credentials = [c for c in data.credentials if c.credential_id != credential_id]
        if len(data.credentials) < original_len:
            self._save(data)
            logger.info(f"Deleted credential: {credential_id[:20]}...")
            return True
        return False

    def get_credential_ids(self) -> list[str]:
        """Get all credential IDs (for excludeCredentials during registration)."""
        return [c.credential_id for c in self.get_credentials()]

    def to_dict(self) -> dict[str, Any]:
        """Export credentials data as dict (for API responses)."""
        data = self._load()
        return data.model_dump()
