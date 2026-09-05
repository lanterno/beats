"""Unit tests for home.space SSO — verification and account mapping.

Pure Python, no database and no network: the issuer is scripted with
`httpx.MockTransport` and the user store is a small in-memory fake, in the
style of `test_domain.py`.

An Ed25519 keypair is generated per test module and used to mint tokens in
exactly the format `auth/src/crypto.rs::create_session_token` produces —
`{"alg":"EdDSA","typ":"JWT"}` with no `kid`, and a payload of
`{sub, name, roles, exp, iss}`. If the issuer's token shape ever changes,
these tests are what notices.
"""

import base64
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from beats.auth.sso import (
    HomeIdentity,
    HomeSSOVerifier,
    SSORejected,
    SSOUnavailable,
)
from beats.auth.sso_accounts import (
    SSOAccountService,
    SSOAlreadyLinked,
    SSOLastCredential,
    SSOLinkConflict,
    SSONotLinked,
    SSOProvisionForbidden,
    sso_email_for,
)
from beats.domain.models import User

ISSUER = "did:web:auth.home.space"
BASE = "http://issuer.test"
DID = "did:key:z6MkuDeviceKeyExample"


# ============================================================================
# Token minting — mirrors the Rust issuer byte for byte
# ============================================================================


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@pytest.fixture(scope="module")
def issuer_key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def mint(
    key: Ed25519PrivateKey,
    *,
    sub: str = DID,
    name: str = "Primary Laptop",
    roles: list[str] | None = None,
    iss: str = ISSUER,
    ttl_hours: int = 24,
) -> str:
    """Mint a `Home-Session` token the way the Rust issuer does."""
    header = _b64(json.dumps({"alg": "EdDSA", "typ": "JWT"}).encode())
    exp = int((datetime.now(UTC) + timedelta(hours=ttl_hours)).timestamp())
    payload = _b64(
        json.dumps(
            {"sub": sub, "name": name, "roles": roles or ["owner"], "exp": exp, "iss": iss}
        ).encode()
    )
    signing_input = f"{header}.{payload}"
    sig = key.sign(signing_input.encode())
    return f"{signing_input}.{_b64(sig)}"


def jwks_for(key: Ed25519PrivateKey) -> dict:
    """The JWKS the issuer publishes for a key — OKP/Ed25519, kid `key-1`."""
    from cryptography.hazmat.primitives import serialization

    raw = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    return {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "x": _b64(raw),
                "kid": "key-1",
                "use": "sig",
                "alg": "EdDSA",
            }
        ]
    }


def verifier_with(handler, **kwargs) -> HomeSSOVerifier:
    return HomeSSOVerifier(
        auth_base_url=BASE,
        issuer=ISSUER,
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


# ============================================================================
# Issuer introspection — the authoritative path
# ============================================================================


class TestIssuerIntrospection:
    async def test_verifies_via_issuer_when_reachable(self, issuer_key):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/session/verify"
            assert request.headers["Authorization"].startswith("Bearer ")
            return httpx.Response(
                200,
                json={
                    "authenticated": True,
                    "did": DID,
                    "holder_name": "Primary Laptop",
                    "roles": ["owner", "admin"],
                },
            )

        identity = await verifier_with(handler).verify(mint(issuer_key))

        assert identity.did == DID
        assert identity.holder_name == "Primary Laptop"
        assert identity.roles == ["owner", "admin"]
        # The point of the issuer path: revocation was actually checked.
        assert identity.verified_by == "issuer"

    async def test_revoked_device_is_rejected_not_retried_offline(self, issuer_key):
        """A 401 from the issuer must be final.

        This is the whole reason the two paths are ordered rather than
        raced: the token is still cryptographically perfect after the
        device is revoked, so an offline fallback here would wave through
        exactly the device that was just revoked.
        """
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            if request.url.path == "/api/session/verify":
                return httpx.Response(401)
            return httpx.Response(200, json=jwks_for(issuer_key))

        with pytest.raises(SSORejected):
            await verifier_with(handler).verify(mint(issuer_key))

        # Never went looking for a key to second-guess the answer with.
        assert calls == ["/api/session/verify"]

    async def test_unauthenticated_body_is_rejected(self, issuer_key):
        def handler(_request):
            return httpx.Response(200, json={"authenticated": False})

        with pytest.raises(SSORejected):
            await verifier_with(handler).verify(mint(issuer_key))

    async def test_empty_token_rejected_without_a_request(self, issuer_key):
        def handler(_request):
            raise AssertionError("should not reach the issuer")

        with pytest.raises(SSORejected):
            await verifier_with(handler).verify("")


# ============================================================================
# Offline fallback — issuer down
# ============================================================================


class TestOfflineFallback:
    async def test_falls_back_to_signature_when_issuer_unreachable(self, issuer_key):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/session/verify":
                raise httpx.ConnectError("connection refused")
            return httpx.Response(200, json=jwks_for(issuer_key))

        identity = await verifier_with(handler).verify(
            mint(issuer_key, roles=["owner"], name="Phone")
        )

        assert identity.did == DID
        assert identity.holder_name == "Phone"
        # Flagged honestly: revocation was NOT checked on this path.
        assert identity.verified_by == "offline"

    async def test_issuer_5xx_falls_back_rather_than_rejecting(self, issuer_key):
        """A broken issuer is an outage, not a verdict on the token."""

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/session/verify":
                return httpx.Response(502)
            return httpx.Response(200, json=jwks_for(issuer_key))

        identity = await verifier_with(handler).verify(mint(issuer_key))
        assert identity.verified_by == "offline"

    async def test_token_signed_by_a_different_key_is_rejected(self, issuer_key):
        impostor = Ed25519PrivateKey.generate()

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/session/verify":
                raise httpx.ConnectError("down")
            return httpx.Response(200, json=jwks_for(issuer_key))

        with pytest.raises(SSORejected):
            await verifier_with(handler).verify(mint(impostor))

    async def test_expired_token_is_rejected_offline(self, issuer_key):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/session/verify":
                raise httpx.ConnectError("down")
            return httpx.Response(200, json=jwks_for(issuer_key))

        with pytest.raises(SSORejected):
            await verifier_with(handler).verify(mint(issuer_key, ttl_hours=-1))

    async def test_token_from_another_issuer_is_rejected(self, issuer_key):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/session/verify":
                raise httpx.ConnectError("down")
            return httpx.Response(200, json=jwks_for(issuer_key))

        with pytest.raises(SSORejected):
            await verifier_with(handler).verify(mint(issuer_key, iss="did:web:evil.example"))

    async def test_unavailable_when_issuer_down_and_no_cached_keys(self, issuer_key):
        """Neither a yes nor a no — the caller must be able to tell."""

        def handler(_request):
            raise httpx.ConnectError("down")

        with pytest.raises(SSOUnavailable):
            await verifier_with(handler).verify(mint(issuer_key))

    async def test_cached_jwks_survives_the_issuer_going_away(self, issuer_key):
        """The cache is the fallback, so an outage must not empty it."""
        state = {"up": True}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/session/verify":
                raise httpx.ConnectError("verify is always down in this test")
            if not state["up"]:
                raise httpx.ConnectError("jwks down too")
            return httpx.Response(200, json=jwks_for(issuer_key))

        # ttl 0 forces a refetch attempt on every call, so the second verify
        # genuinely exercises "refresh failed, use what we have".
        verifier = verifier_with(handler, jwks_ttl_seconds=0)

        first = await verifier.verify(mint(issuer_key))
        assert first.verified_by == "offline"

        state["up"] = False
        second = await verifier.verify(mint(issuer_key))
        assert second.verified_by == "offline"


# ============================================================================
# Role gate
# ============================================================================


class TestRoleGate:
    @pytest.mark.parametrize(
        ("roles", "allowed"),
        [
            (["owner"], True),
            (["admin"], True),
            (["owner", "guest"], True),
            (["family"], False),
            (["guest"], False),
            ([], False),
        ],
    )
    def test_provision_roles(self, roles, allowed):
        identity = HomeIdentity(
            did=DID, holder_name="x", roles=roles, issuer=ISSUER, verified_by="issuer"
        )
        assert identity.has_any_role(frozenset({"owner", "admin"})) is allowed

    def test_empty_gate_means_no_gate(self):
        identity = HomeIdentity(
            did=DID, holder_name="x", roles=["guest"], issuer=ISSUER, verified_by="issuer"
        )
        assert identity.has_any_role(frozenset()) is True

    def test_role_matching_is_case_insensitive(self):
        identity = HomeIdentity(
            did=DID, holder_name="x", roles=["Owner"], issuer=ISSUER, verified_by="issuer"
        )
        assert identity.has_any_role(frozenset({"owner"})) is True


# ============================================================================
# Account mapping
# ============================================================================


class FakeUserRepo:
    """In-memory UserRepository, enough for the linking rules."""

    def __init__(self, users: list[User] | None = None):
        self._users: dict[str, User] = {}
        self._next = 1
        for u in users or []:
            self._insert(u)

    def _insert(self, user: User) -> User:
        if not user.id:
            user.id = f"u{self._next}"
            self._next += 1
        self._users[user.id] = user
        return user

    async def get_by_id(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        return next((u for u in self._users.values() if u.email == email), None)

    async def get_by_sso_subject(self, issuer: str, subject: str) -> User | None:
        return next(
            (
                u
                for u in self._users.values()
                if u.sso_issuer == issuer and u.sso_subject == subject
            ),
            None,
        )

    async def create(self, user: User) -> User:
        if await self.get_by_email(user.email):
            raise ValueError("duplicate email")
        return self._insert(user)

    async def update(self, user: User) -> User:
        self._users[user.id or ""] = user
        return user

    async def count(self) -> int:
        return len(self._users)


def identity(did: str = DID, name: str = "Primary Laptop", roles: list[str] | None = None):
    return HomeIdentity(
        did=did,
        holder_name=name,
        roles=roles or ["owner"],
        issuer=ISSUER,
        verified_by="issuer",
    )


OWNER_ONLY = frozenset({"owner", "admin"})


class TestSignIn:
    async def test_provisions_a_new_account_for_an_owner(self):
        repo = FakeUserRepo()
        service = SSOAccountService(repo, OWNER_ONLY)

        user, created = await service.sign_in(identity())

        assert created is True
        assert user.sso_subject == DID
        assert user.sso_provisioned is True
        assert user.display_name == "Primary Laptop"
        assert await repo.count() == 1

    async def test_refuses_to_provision_for_a_guest(self):
        repo = FakeUserRepo()
        service = SSOAccountService(repo, OWNER_ONLY)

        with pytest.raises(SSOProvisionForbidden):
            await service.sign_in(identity(roles=["guest"]))

        assert await repo.count() == 0

    async def test_signs_into_an_existing_link_without_creating(self):
        existing = User(
            id="u9",
            email="ahmed@example.com",
            display_name="Ahmed",
            sso_issuer=ISSUER,
            sso_subject=DID,
        )
        repo = FakeUserRepo([existing])
        service = SSOAccountService(repo, OWNER_ONLY)

        user, created = await service.sign_in(identity())

        assert created is False
        assert user.id == "u9"
        assert await repo.count() == 1

    async def test_a_guest_may_sign_into_an_account_already_linked(self):
        """The role gate is on provisioning only, not on signing in."""
        repo = FakeUserRepo(
            [User(id="u9", email="g@example.com", sso_issuer=ISSUER, sso_subject=DID)]
        )
        service = SSOAccountService(repo, OWNER_ONLY)

        user, created = await service.sign_in(identity(roles=["guest"]))

        assert created is False
        assert user.id == "u9"

    async def test_provisioned_email_is_deterministic_and_unregisterable(self):
        email = sso_email_for(identity())
        assert email == sso_email_for(identity())
        # RFC 2606 reserved — cannot be registered through beats' own signup,
        # so it can never collide with a real user's address.
        assert email.endswith(".invalid")
        assert "z6MkuDeviceKeyExample" in email

    async def test_roles_and_holder_name_refresh_on_each_sign_in(self):
        repo = FakeUserRepo(
            [
                User(
                    id="u9",
                    email="a@example.com",
                    sso_issuer=ISSUER,
                    sso_subject=DID,
                    sso_holder_name="Old Name",
                    sso_roles=["guest"],
                )
            ]
        )
        service = SSOAccountService(repo, OWNER_ONLY)

        user, _ = await service.sign_in(identity(name="Renamed Laptop", roles=["owner"]))

        assert user.sso_holder_name == "Renamed Laptop"
        assert user.sso_roles == ["owner"]

    async def test_refresh_does_not_overwrite_a_linked_users_own_display_name(self):
        """The issuer owns the device label, not the person's chosen name."""
        repo = FakeUserRepo(
            [
                User(
                    id="u9",
                    email="a@example.com",
                    display_name="Ahmed",
                    sso_issuer=ISSUER,
                    sso_subject=DID,
                    sso_holder_name="Old Laptop",
                    sso_provisioned=False,
                )
            ]
        )
        service = SSOAccountService(repo, OWNER_ONLY)

        user, _ = await service.sign_in(identity(name="New Laptop"))

        assert user.display_name == "Ahmed"
        assert user.sso_holder_name == "New Laptop"


class TestLink:
    async def test_links_an_identity_to_an_authenticated_account(self):
        repo = FakeUserRepo([User(id="u1", email="ahmed@example.com", display_name="Ahmed")])
        service = SSOAccountService(repo, OWNER_ONLY)

        user = await service.link("u1", identity())

        assert user.sso_subject == DID
        assert user.sso_provisioned is False  # linked, not created by SSO
        assert user.email == "ahmed@example.com"
        assert user.sso_linked_at is not None

    async def test_a_guest_may_link_even_though_it_cannot_provision(self):
        repo = FakeUserRepo([User(id="u1", email="g@example.com")])
        service = SSOAccountService(repo, OWNER_ONLY)

        user = await service.link("u1", identity(roles=["guest"]))

        assert user.sso_subject == DID

    async def test_refuses_when_the_identity_belongs_to_someone_else(self):
        repo = FakeUserRepo(
            [
                User(id="u1", email="a@example.com"),
                User(id="u2", email="b@example.com", sso_issuer=ISSUER, sso_subject=DID),
            ]
        )
        service = SSOAccountService(repo, OWNER_ONLY)

        with pytest.raises(SSOAlreadyLinked):
            await service.link("u1", identity())

    async def test_refuses_a_second_identity_on_one_account(self):
        repo = FakeUserRepo(
            [
                User(
                    id="u1",
                    email="a@example.com",
                    sso_issuer=ISSUER,
                    sso_subject="did:key:z6MkuSomethingElse",
                )
            ]
        )
        service = SSOAccountService(repo, OWNER_ONLY)

        with pytest.raises(SSOLinkConflict):
            await service.link("u1", identity())

    async def test_relinking_the_same_identity_is_idempotent(self):
        repo = FakeUserRepo(
            [User(id="u1", email="a@example.com", sso_issuer=ISSUER, sso_subject=DID)]
        )
        service = SSOAccountService(repo, OWNER_ONLY)

        user = await service.link("u1", identity())
        assert user.sso_subject == DID


class TestUnlink:
    async def test_unlinks_when_a_passkey_remains(self):
        repo = FakeUserRepo(
            [User(id="u1", email="a@example.com", sso_issuer=ISSUER, sso_subject=DID)]
        )
        service = SSOAccountService(repo, OWNER_ONLY)

        user = await service.unlink("u1", passkey_count=1)

        assert user.sso_subject is None
        assert user.sso_issuer is None
        assert user.sso_roles == []

    async def test_refuses_to_remove_the_only_way_in(self):
        repo = FakeUserRepo(
            [
                User(
                    id="u1",
                    email="a@example.com",
                    sso_issuer=ISSUER,
                    sso_subject=DID,
                    sso_provisioned=True,
                )
            ]
        )
        service = SSOAccountService(repo, OWNER_ONLY)

        with pytest.raises(SSOLastCredential):
            await service.unlink("u1", passkey_count=0)

    async def test_unlinking_an_unlinked_account_is_an_error(self):
        repo = FakeUserRepo([User(id="u1", email="a@example.com")])
        service = SSOAccountService(repo, OWNER_ONLY)

        with pytest.raises(SSONotLinked):
            await service.unlink("u1", passkey_count=2)

    async def test_unlinked_identity_can_then_be_claimed_by_another_account(self):
        repo = FakeUserRepo(
            [
                User(id="u1", email="a@example.com", sso_issuer=ISSUER, sso_subject=DID),
                User(id="u2", email="b@example.com"),
            ]
        )
        service = SSOAccountService(repo, OWNER_ONLY)

        await service.unlink("u1", passkey_count=1)
        user = await service.link("u2", identity())

        assert user.id == "u2"
        assert user.sso_subject == DID
