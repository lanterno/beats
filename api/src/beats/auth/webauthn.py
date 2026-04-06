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
from beats.auth.storage import CredentialStorage

logger = logging.getLogger(__name__)


class WebAuthnManager:
    """Handles WebAuthn registration and authentication operations."""

    def __init__(
        self,
        rp_id: str,
        rp_name: str,
        origin: str,
        credential_storage: CredentialStorage,
        session_manager: SessionManager,
    ):
        self.rp_id = rp_id
        self.rp_name = rp_name
        self.origin = origin
        self.storage = credential_storage
        self.session = session_manager

        # Fixed user info for single-user system
        self.user_id = b"owner"
        self.user_name = "owner"
        self.user_display_name = "Beats Owner"

    def get_registration_options(self) -> dict[str, Any]:
        """Generate registration options for a new passkey.

        Returns a dict that can be JSON-serialized for the frontend.
        """
        # Get existing credential IDs to exclude (prevent re-registration)
        existing_credentials = [
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(cred_id))
            for cred_id in self.storage.get_credential_ids()
        ]

        options = generate_registration_options(
            rp_id=self.rp_id,
            rp_name=self.rp_name,
            user_id=self.user_id,
            user_name=self.user_name,
            user_display_name=self.user_display_name,
            exclude_credentials=existing_credentials,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.REQUIRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
        )

        # Store the challenge for later verification
        self.session.store_challenge(options.challenge, "registration")

        # Convert to dict for JSON response
        # The options object has a model_dump() or we can convert manually
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

    def verify_registration(
        self, credential: dict[str, Any], device_name: str | None = None
    ) -> dict[str, Any]:
        """Verify a registration response and store the credential.

        Args:
            credential: The credential response from the browser
            device_name: Optional friendly name for the device

        Returns:
            Dict with success status and session token
        """
        # Get the stored challenge
        expected_challenge = self.session.get_stored_challenge("registration")
        if expected_challenge is None:
            raise ValueError("No pending registration challenge found")

        try:
            # Pass the credential dict directly to verify_registration_response
            # The library handles parsing the camelCase keys and base64 decoding
            verification = verify_registration_response(
                credential=credential,
                expected_challenge=expected_challenge,
                expected_rp_id=self.rp_id,
                expected_origin=self.origin,
            )

            # Store the credential
            self.storage.save_credential(
                credential_id=bytes_to_base64url(verification.credential_id),
                public_key=bytes_to_base64url(verification.credential_public_key),
                sign_count=verification.sign_count,
                device_name=device_name,
            )

            # Create a session token
            token = self.session.create_session_token()

            logger.info("Successfully registered new passkey")
            return {
                "verified": True,
                "token": token,
            }

        except Exception as e:
            logger.error(f"Registration verification failed: {e}")
            raise ValueError(f"Registration verification failed: {e}") from e

    def get_authentication_options(self) -> dict[str, Any]:
        """Generate authentication options for login.

        Returns a dict that can be JSON-serialized for the frontend.
        """
        # Get all registered credentials
        credentials = self.storage.get_credentials()

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

        # Store the challenge for later verification
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

    def verify_authentication(self, credential: dict[str, Any]) -> dict[str, Any]:
        """Verify an authentication response.

        Args:
            credential: The credential response from the browser

        Returns:
            Dict with success status and session token
        """
        # Get the stored challenge
        expected_challenge = self.session.get_stored_challenge("authentication")
        if expected_challenge is None:
            raise ValueError("No pending authentication challenge found")

        # Find the credential in storage
        credential_id = credential["id"]
        stored_credential = self.storage.get_credential_by_id(credential_id)

        if stored_credential is None:
            raise ValueError("Credential not found")

        try:
            # Pass the credential dict directly to verify_authentication_response
            # The library handles parsing the camelCase keys and base64 decoding
            verification = verify_authentication_response(
                credential=credential,
                expected_challenge=expected_challenge,
                expected_rp_id=self.rp_id,
                expected_origin=self.origin,
                credential_public_key=base64url_to_bytes(stored_credential.public_key),
                credential_current_sign_count=stored_credential.sign_count,
            )

            # Update sign count for replay attack prevention
            self.storage.update_sign_count(credential_id, verification.new_sign_count)

            # Create a session token
            token = self.session.create_session_token()

            logger.info("Successfully authenticated with passkey")
            return {
                "verified": True,
                "token": token,
            }

        except Exception as e:
            logger.error(f"Authentication verification failed: {e}")
            raise ValueError(f"Authentication verification failed: {e}") from e

    def is_registered(self) -> bool:
        """Check if any passkeys are registered."""
        return self.storage.is_registered()

    def get_credentials_info(self) -> list[dict[str, Any]]:
        """Get info about registered credentials (for management UI)."""
        credentials = self.storage.get_credentials()
        return [
            {
                "id": cred.credential_id[:20] + "...",
                "device_name": cred.device_name,
                "created_at": cred.created_at,
            }
            for cred in credentials
        ]
