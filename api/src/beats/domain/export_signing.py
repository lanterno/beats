"""Ed25519 sign/verify primitives for signed exports.

Pure helpers — no I/O. The user-scoped key material is persisted by
`infrastructure.export_key_repo`. We wrap the `cryptography` library so the
router never touches raw private keys directly.

Security note: these signatures prove that an export came from a given Beats
account at a given time. They do NOT encrypt content — anyone with the export
bundle can read it. This is intentional; signing gives tamper-evidence for
restores without the operational burden of client-side decryption.
"""

from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519


class SignatureMismatch(Exception):
    """Raised when a manifest signature does not verify against a public key."""


def generate_keypair() -> tuple[bytes, bytes]:
    """Return `(private_bytes, public_bytes)` as raw 32-byte Ed25519 keys."""
    priv = ed25519.Ed25519PrivateKey.generate()
    private_bytes = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return private_bytes, public_bytes


def sign(private_bytes: bytes, payload: bytes) -> bytes:
    """Sign `payload` with a raw 32-byte private key. Returns a 64-byte signature."""
    key = ed25519.Ed25519PrivateKey.from_private_bytes(private_bytes)
    return key.sign(payload)


def verify(public_bytes: bytes, payload: bytes, signature: bytes) -> None:
    """Verify `signature` over `payload`. Raises `SignatureMismatch` on failure."""
    try:
        key = ed25519.Ed25519PublicKey.from_public_bytes(public_bytes)
        key.verify(signature, payload)
    except InvalidSignature as exc:
        raise SignatureMismatch("export signature does not verify") from exc
    except Exception as exc:  # noqa: BLE001
        raise SignatureMismatch(f"export signature malformed: {exc}") from exc
