"""Authentication module for WebAuthn/Passkey authentication."""

from beats.auth.session import SessionManager
from beats.auth.storage import CredentialStorage
from beats.auth.webauthn import WebAuthnManager

__all__ = ["CredentialStorage", "SessionManager", "WebAuthnManager"]
