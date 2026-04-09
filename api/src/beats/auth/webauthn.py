"""WebAuthn registration and authentication logic."""

import logging
from typing import Any

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from beats.auth.session import SessionManager
from beats.auth.storage import MongoCredentialStorage
from beats.domain.models import User

logger = logging.getLogger(__name__)


class WebAuthnManager:
    """Handles WebAuthn registration and authentication operations."""

    def __init__(
        self,
        rp_id: str,
        rp_name: str,
        origin: str,
        credential_storage: MongoCredentialStorage,
        session_manager: SessionManager,
    ):
        self.rp_id = rp_id
        self.rp_name = rp_name
        self.origin = origin
        self.storage = credential_storage
        self.session = session_manager

    async def get_registration_options(self, user: User) -> dict[str, Any]:
        """Generate registration options for a new passkey.

        Args:
            user: The user registering a passkey.

        Returns a dict that can be JSON-serialized for the frontend.
        """
        user_id = (user.id or "").encode()
        user_name = user.email
        user_display_name = user.display_name or user.email

        # Get existing credential IDs for this user to exclude
        existing_cred_ids = await self.storage.get_credential_ids(user_id=user.id)
        existing_credentials = [
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(cred_id))
            for cred_id in existing_cred_ids
        ]

        options = generate_registration_options(
            rp_id=self.rp_id,
            rp_name=self.rp_name,
            user_id=user_id,
            user_name=user_name,
            user_display_name=user_display_name,
            exclude_credentials=existing_credentials,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
        )

        # Store the challenge and pending registration user_id
        self.session.store_challenge(options.challenge, "registration")
        self.session.store_pending_registration(options.challenge, user.id or "")

        return {
            "rp": {"id": options.rp.id, "name": options.rp.name},
            "user": {
                "id": bytes_to_base64url(options.user.id),
                "name": options.user.name,
                "displayName": options.user.display_name,
            },
            "challenge": bytes_to_base64url(options.challenge),
            "pubKeyCredParams": [
                {"type": p.type, "alg": p.alg} for p in options.pub_key_cred_params
            ],
            "timeout": options.timeout,
            "excludeCredentials": [
                {
                    "type": c.type,
                    "id": bytes_to_base64url(c.id),
                }
                for c in (options.exclude_credentials or [])
            ],
            "authenticatorSelection": {
                "residentKey": options.authenticator_selection.resident_key.value
                if options.authenticator_selection
                else "preferred",
                "userVerification": options.authenticator_selection.user_verification.value
                if options.authenticator_selection
                else "preferred",
            },
            "attestation": options.attestation.value if options.attestation else "none",
        }

    async def verify_registration(
        self,
        credential: dict[str, Any],
        user: User,
        device_name: str | None = None,
    ) -> dict[str, Any]:
        """Verify a registration response and store the credential.

        Args:
            credential: The credential response from the browser
            user: The user who is registering
            device_name: Optional friendly name for the device

        Returns:
            Dict with success status and session token
        """
        expected_challenge = self.session.get_stored_challenge("registration")
        if expected_challenge is None:
            raise ValueError("No pending registration challenge found")

        try:
            verification = verify_registration_response(
                credential=credential,
                expected_challenge=expected_challenge,
                expected_rp_id=self.rp_id,
                expected_origin=self.origin,
            )

            await self.storage.save_credential(
                user_id=user.id or "",
                credential_id=bytes_to_base64url(verification.credential_id),
                public_key=bytes_to_base64url(verification.credential_public_key),
                sign_count=verification.sign_count,
                device_name=device_name,
            )

            token = self.session.create_session_token(
                user_id=user.id or "",
                email=user.email,
            )

            logger.info("Successfully registered new passkey for user %s", user.email)
            return {
                "verified": True,
                "token": token,
            }

        except Exception as e:
            logger.error(f"Registration verification failed: {e}")
            raise ValueError(f"Registration verification failed: {e}") from e

    async def get_authentication_options(self) -> dict[str, Any]:
        """Generate authentication options for login.

        Returns a dict that can be JSON-serialized for the frontend.
        """
        credentials = await self.storage.get_credentials()

        if not credentials:
            raise ValueError("No credentials registered. Please register first.")

        allow_credentials = [
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(cred.credential_id))
            for cred in credentials
        ]

        options = generate_authentication_options(
            rp_id=self.rp_id,
            allow_credentials=allow_credentials,
            user_verification=UserVerificationRequirement.PREFERRED,
        )

        self.session.store_challenge(options.challenge, "authentication")

        return {
            "challenge": bytes_to_base64url(options.challenge),
            "timeout": options.timeout,
            "rpId": options.rp_id,
            "allowCredentials": [
                {
                    "type": c.type,
                    "id": bytes_to_base64url(c.id),
                }
                for c in (options.allow_credentials or [])
            ],
            "userVerification": options.user_verification.value
            if options.user_verification
            else "preferred",
        }

    async def verify_authentication(self, credential: dict[str, Any]) -> dict[str, Any]:
        """Verify an authentication response.

        Args:
            credential: The credential response from the browser

        Returns:
            Dict with success status, session token, and user_id
        """
        expected_challenge = self.session.get_stored_challenge("authentication")
        if expected_challenge is None:
            raise ValueError("No pending authentication challenge found")

        credential_id = credential["id"]
        stored_credential = await self.storage.get_credential_by_id(credential_id)

        if stored_credential is None:
            raise ValueError("Credential not found")

        # Look up which user owns this credential
        user_id = await self.storage.get_user_id_for_credential(credential_id)
        if not user_id:
            raise ValueError("No user found for this credential")

        try:
            verification = verify_authentication_response(
                credential=credential,
                expected_challenge=expected_challenge,
                expected_rp_id=self.rp_id,
                expected_origin=self.origin,
                credential_public_key=base64url_to_bytes(stored_credential.public_key),
                credential_current_sign_count=stored_credential.sign_count,
            )

            await self.storage.update_sign_count(credential_id, verification.new_sign_count)

            token = self.session.create_session_token(user_id=user_id)

            logger.info("Successfully authenticated user %s with passkey", user_id)
            return {
                "verified": True,
                "token": token,
                "user_id": user_id,
            }

        except Exception as e:
            logger.error(f"Authentication verification failed: {e}")
            raise ValueError(f"Authentication verification failed: {e}") from e

    async def is_registered(self) -> bool:
        """Check if any passkeys are registered."""
        return await self.storage.is_registered()

    async def get_credentials_info(self, user_id: str) -> list[dict[str, Any]]:
        """Get info about registered credentials for a user."""
        credentials = await self.storage.get_credentials(user_id=user_id)
        return [
            {
                "id": cred.credential_id[:20] + "...",
                "device_name": cred.device_name,
                "created_at": cred.created_at,
            }
            for cred in credentials
        ]
