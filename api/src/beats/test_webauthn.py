"""`WebAuthnManager` — registration and authentication orchestration,
the second passkey on a signed-in account, and the Mongo credential
storage; plus the two settings validators the auth layer depends on
(`JWT_SECRET`'s length and `FORWARDED_ALLOW_IPS`).

Split from the session half at the ceiling in roadmaps/file-sizes.md.
"""

from __future__ import annotations

import pytest

from beats.auth.storage import StoredCredential
from beats.auth_fakes import (
    _FakeCredentialStorage,
    _FakeUserRepo,
    _sm,
    _user,
    _wam,
)
from beats.settings import settings


class TestWebAuthnRegistrationOptions:
    """get_registration_options builds the dict the browser hands
    to navigator.credentials.create. Two side effects: the
    challenge is stored on SessionManager AND the
    pending-registration user_id is recorded — so verify_*
    can find both."""

    async def test_returns_options_dict_with_required_keys(self):
        wam = _wam()
        out = await wam.get_registration_options(_user())
        for key in (
            "rp",
            "user",
            "challenge",
            "pubKeyCredParams",
            "authenticatorSelection",
            "attestation",
            "excludeCredentials",
        ):
            assert key in out, f"missing key {key!r}"
        assert out["rp"]["id"] == "beats.test"
        assert out["rp"]["name"] == "Beats"
        assert out["user"]["name"] == "ahmed@example.com"
        assert out["user"]["displayName"] == "Ahmed"
        assert "id" in out["user"]
        # authenticatorSelection: residentKey REQUIRED, userVerification PREFERRED
        assert out["authenticatorSelection"]["residentKey"] == "required"
        assert out["authenticatorSelection"]["userVerification"] == "preferred"

    async def test_stores_challenge_and_pending_registration(self):
        """Side effect: SessionManager has a "registration" challenge
        AND the pending-registration map points to the user. Pin
        both so verify_registration can find them."""
        sm = _sm()
        wam = _wam(session=sm)
        await wam.get_registration_options(_user(id_="user-42"))
        assert sm.get_current_challenge("registration") is not None
        assert sm.get_pending_registration_user_id("registration") == "user-42"

    async def test_excludes_existing_credentials(self):
        """A user with an existing credential gets it surfaced in
        excludeCredentials so the browser refuses to register the
        same authenticator twice. Pin so a second registration
        attempt with the same hardware shows a useful error rather
        than silently overwriting."""
        storage = _FakeCredentialStorage()
        await storage.save_credential(
            user_id="user-1",
            credential_id="AQIDBA",  # valid base64url, decodes to 4 bytes
            public_key="AQID",
            sign_count=0,
        )
        wam = _wam(storage=storage)
        out = await wam.get_registration_options(_user())
        ids = [c["id"] for c in out["excludeCredentials"]]
        assert "AQIDBA" in ids

    async def test_user_without_display_name_falls_back_to_email(self):
        """display_name=None → user.displayName is the email. Pin
        so the browser's native picker shows a non-empty label."""
        wam = _wam()
        out = await wam.get_registration_options(_user(display_name=None))
        assert out["user"]["displayName"] == "ahmed@example.com"


class TestWebAuthnRegistrationVerificationGuards:
    """verify_registration's crypto path needs a real authenticator
    signature, so cover the PRE-checks (business logic) here. The
    crypto path is exercised by HTTP integration tests in test_api."""

    async def test_max_credentials_per_user_blocks_new_registration(self):
        """A user at MAX_CREDENTIALS_PER_USER (10) → ValueError
        BEFORE the crypto path runs. Pin so a malicious or buggy
        client can't register unbounded keys."""
        from beats.auth.webauthn import MAX_CREDENTIALS_PER_USER

        storage = _FakeCredentialStorage()
        for i in range(MAX_CREDENTIALS_PER_USER):
            await storage.save_credential(
                user_id="user-1",
                credential_id=f"cred-{i}",
                public_key=f"pk-{i}",
                sign_count=0,
            )
        wam = _wam(storage=storage)
        with pytest.raises(ValueError, match="Maximum"):
            await wam.verify_registration(credential={}, user=_user())

    async def test_no_pending_challenge_raises(self):
        """verify_registration without a prior get_registration_options
        call → ValueError. Pin so an attacker who skips the challenge
        step gets rejected at the service layer."""
        wam = _wam()
        with pytest.raises(ValueError, match="No pending registration"):
            await wam.verify_registration(credential={}, user=_user())

    async def test_happy_path_persists_credential_and_returns_token(self, monkeypatch):
        """Mock py_webauthn's verify_registration_response to return
        a fake success object — exercises the try-block (lines
        148-173): save_credential is called with the verified
        material AND a session token is returned in the response.

        Pin so a refactor of the storage interaction (e.g. forgets
        to base64-encode credential_id) or the token-issue path
        gets caught."""
        from beats.auth import webauthn as webauthn_module

        class _FakeVerification:
            credential_id = b"\x01\x02\x03\x04"
            credential_public_key = b"\x05\x06\x07\x08"
            sign_count = 0

        def fake_verify(*, credential, **_kwargs):
            return _FakeVerification()

        monkeypatch.setattr(webauthn_module, "verify_registration_response", fake_verify)

        storage = _FakeCredentialStorage()
        sm = _sm()
        # Seed the pending registration challenge so the pre-check passes
        sm.store_challenge(b"X" * 32, "registration")
        wam = _wam(storage=storage, session=sm)

        result = await wam.verify_registration(
            credential={"id": "fake"},
            user=_user(),
            device_name="iPhone",
        )

        # Response shape pinned: verified + token
        assert result["verified"] is True
        assert isinstance(result["token"], str)
        assert result["token"]

        # Credential persisted via save_credential
        creds = await storage.get_credentials("user-1")
        assert len(creds) == 1
        # base64url(b"\x01\x02\x03\x04") == "AQIDBA"
        assert creds[0].credential_id == "AQIDBA"
        assert creds[0].device_name == "iPhone"
        # Token validates against the SessionManager
        payload = sm.validate_session_token(result["token"])
        assert payload is not None
        assert payload["sub"] == "user-1"

    async def test_crypto_failure_wraps_to_value_error(self, monkeypatch):
        """When verify_registration_response raises (signature
        mismatch, malformed origin, etc.), the broad except wraps
        it as ValueError("Registration verification failed: ...").
        Pin the wrapper so the API router's `except ValueError` →
        400 path stays reachable from the real py_webauthn library."""
        from beats.auth import webauthn as webauthn_module

        def fake_verify_raises(*, credential, **_kwargs):
            raise RuntimeError("origin mismatch")

        monkeypatch.setattr(webauthn_module, "verify_registration_response", fake_verify_raises)

        sm = _sm()
        sm.store_challenge(b"X" * 32, "registration")
        wam = _wam(session=sm)

        with pytest.raises(ValueError, match="Registration verification failed"):
            await wam.verify_registration(credential={"id": "fake"}, user=_user())


class TestAddingASecondPasskey:
    """The ceremony behind a session (#376). Two things separate it from
    signing up: the challenge is in its own slot, so one ceremony cannot be
    finished with the other's challenge, and no second session token is
    issued — the caller already holds one."""

    @staticmethod
    def _fake_verification(monkeypatch, credential_id=b"\x01\x02\x03\x04"):
        from beats.auth import webauthn as webauthn_module

        class _FakeVerification:
            credential_public_key = b"\x05\x06\x07\x08"
            sign_count = 0

            def __init__(self) -> None:
                self.credential_id = credential_id

        monkeypatch.setattr(
            webauthn_module, "verify_registration_response", lambda **_kw: _FakeVerification()
        )

    async def test_the_two_ceremonies_do_not_share_a_challenge(self):
        """A sign-up challenge must not finish an add, nor the reverse —
        otherwise the challenge slot is a single global one and whichever
        ceremony ran last decides what the other verifies against."""
        sm = _sm()
        wam = _wam(session=sm)
        await wam.get_registration_options(_user(), challenge_type="add-credential")

        assert sm.get_stored_challenge("registration") is None
        assert sm.get_stored_challenge("add-credential") is not None

        with pytest.raises(ValueError, match="No pending registration"):
            await wam.verify_registration(credential={}, user=_user())

    async def test_adding_stores_the_passkey_and_issues_no_token(self, monkeypatch):
        self._fake_verification(monkeypatch)
        storage = _FakeCredentialStorage()
        sm = _sm()
        sm.store_challenge(b"X" * 32, "add-credential")
        wam = _wam(storage=storage, session=sm)

        result = await wam.verify_registration(
            credential={"id": "fake"},
            user=_user(),
            device_name="Work laptop",
            challenge_type="add-credential",
            issue_token=False,
        )

        assert result == {"verified": True}
        creds = await storage.get_credentials("user-1")
        assert [c.device_name for c in creds] == ["Work laptop"]

    async def test_an_account_can_hold_two(self, monkeypatch):
        """The whole point: before this, an account held exactly one, so a
        second device was impossible and losing the one locked it out."""
        storage = _FakeCredentialStorage()
        sm = _sm()
        wam = _wam(storage=storage, session=sm)

        for name, cred_id in (("Phone", b"\x01"), ("Laptop", b"\x02")):
            self._fake_verification(monkeypatch, credential_id=cred_id)
            sm.store_challenge(cred_id * 32, "add-credential")
            await wam.verify_registration(
                credential={"id": name},
                user=_user(),
                device_name=name,
                challenge_type="add-credential",
                issue_token=False,
            )

        creds = await storage.get_credentials("user-1")
        assert sorted(c.device_name for c in creds) == ["Laptop", "Phone"]

    async def test_the_second_ceremony_excludes_the_first_passkey(self):
        """excludeCredentials is what stops the same authenticator being
        enrolled twice — the browser refuses rather than making a duplicate."""
        storage = _FakeCredentialStorage()
        await storage.save_credential(
            user_id="user-1", credential_id="AQIDBA", public_key="pk", sign_count=0
        )
        wam = _wam(storage=storage)

        options = await wam.get_registration_options(_user(), challenge_type="add-credential")

        assert [c["id"] for c in options["excludeCredentials"]] == ["AQIDBA"]


class TestWebAuthnAuthenticationOptions:
    """get_authentication_options uses an empty allowCredentials list
    so the browser triggers its native picker for discoverable
    credentials. Pin the empty-list invariant — exposing registered
    credential IDs to unauthenticated callers leaks user existence."""

    async def test_returns_options_with_empty_allow_credentials(self):
        wam = _wam()
        out = await wam.get_authentication_options()
        assert out["rpId"] == "beats.test"
        assert out["allowCredentials"] == []
        assert "challenge" in out
        assert out["userVerification"] == "preferred"

    async def test_stores_authentication_challenge(self):
        sm = _sm()
        wam = _wam(session=sm)
        await wam.get_authentication_options()
        assert sm.get_current_challenge("authentication") is not None
        # Pin: it's NOT also a registration challenge
        assert sm.get_current_challenge("registration") is None


class TestWebAuthnAuthenticationVerificationGuards:
    """Pin the pre-checks of verify_authentication without needing
    a real authenticator signature."""

    async def test_no_pending_challenge_raises(self):
        wam = _wam()
        with pytest.raises(ValueError, match="No pending authentication"):
            await wam.verify_authentication(credential={"id": "any"})

    async def test_unknown_credential_raises(self):
        """Credential ID not in storage → ValueError "Credential
        not found". Pin so an attacker can't probe for valid
        credential IDs by checking which error fires."""
        sm = _sm()
        sm.store_challenge(b"X" * 32, challenge_type="authentication")
        wam = _wam(session=sm)
        with pytest.raises(ValueError, match="Credential not found"):
            await wam.verify_authentication(credential={"id": "ghost"})

    async def test_credential_without_user_raises(self):
        """A credential that exists but isn't mapped to a user
        (orphaned data) → ValueError "No user found". Pin so a
        partial DB state doesn't auth the wrong user."""
        storage = _FakeCredentialStorage()
        # Insert orphaned credential directly — empty user_id
        storage._creds.append(
            (
                "",
                StoredCredential(
                    credential_id="orphan",
                    public_key="pk",
                    sign_count=0,
                    created_at="2026-04-01T00:00:00",
                ),
            )
        )
        sm = _sm()
        sm.store_challenge(b"X" * 32, challenge_type="authentication")
        wam = _wam(storage=storage, session=sm)
        with pytest.raises(ValueError, match="No user"):
            await wam.verify_authentication(credential={"id": "orphan"})

    async def test_happy_path_updates_sign_count_and_returns_token(self, monkeypatch):
        """Mock verify_authentication_response to return a fake
        success object → exercises the try-block (lines 229-252):
        update_sign_count is called with the new value AND a
        session token is issued for the credential's owner.

        Pin the sign_count-update side effect — without it, the
        WebAuthn replay-attack prevention is silently broken."""
        from beats.auth import webauthn as webauthn_module
        from beats.domain.models import User

        class _FakeAuth:
            new_sign_count = 42

        def fake_verify(*, credential, **_kwargs):
            return _FakeAuth()

        monkeypatch.setattr(webauthn_module, "verify_authentication_response", fake_verify)

        storage = _FakeCredentialStorage()
        # Seed a credential — credential_id="cred-1", base64url-decodable
        # public_key = "pk" (also valid base64url for 1 byte)
        storage._creds.append(
            (
                "user-99",
                StoredCredential(
                    credential_id="cred-1",
                    public_key="pk",
                    sign_count=10,
                    created_at="2026-04-01T00:00:00",
                ),
            )
        )

        sm = _sm()
        sm.store_challenge(b"X" * 32, challenge_type="authentication")

        user = User(id="user-99", email="ahmed@example.com")
        wam = _wam(storage=storage, session=sm, user_repo=_FakeUserRepo([user]))

        result = await wam.verify_authentication(credential={"id": "cred-1"})

        # Response shape pinned
        assert result["verified"] is True
        assert result["user_id"] == "user-99"
        assert isinstance(result["token"], str)
        assert result["token"]

        # sign_count was advanced from 10 → 42
        cred = await storage.get_credential_by_id("cred-1")
        assert cred is not None
        assert cred.sign_count == 42

        # Token validates with the user's identity
        payload = sm.validate_session_token(result["token"])
        assert payload is not None
        assert payload["sub"] == "user-99"
        assert payload["email"] == "ahmed@example.com"

    async def test_crypto_failure_wraps_to_value_error(self, monkeypatch):
        """When verify_authentication_response raises (signature
        mismatch, sign-count rollback, etc.), the broad except
        wraps it as ValueError("Authentication verification
        failed: ..."). Pin so the router's `except ValueError`
        → 401 path stays reachable from the real py_webauthn
        library."""
        from beats.auth import webauthn as webauthn_module

        def fake_verify_raises(*, credential, **_kwargs):
            raise RuntimeError("sign-count rollback detected")

        monkeypatch.setattr(webauthn_module, "verify_authentication_response", fake_verify_raises)

        storage = _FakeCredentialStorage()
        storage._creds.append(
            (
                "user-99",
                StoredCredential(
                    credential_id="cred-X",
                    public_key="pk",
                    sign_count=0,
                    created_at="2026-04-01T00:00:00",
                ),
            )
        )
        sm = _sm()
        sm.store_challenge(b"X" * 32, challenge_type="authentication")
        wam = _wam(storage=storage, session=sm)

        with pytest.raises(ValueError, match="Authentication verification failed"):
            await wam.verify_authentication(credential={"id": "cred-X"})


class TestWebAuthnIsRegistered:
    """is_registered passes through to storage."""

    async def test_no_credentials_returns_false(self):
        wam = _wam()
        assert await wam.is_registered() is False

    async def test_with_credentials_returns_true(self):
        storage = _FakeCredentialStorage()
        await storage.save_credential(
            user_id="user-1",
            credential_id="cred-1",
            public_key="pk",
            sign_count=0,
        )
        wam = _wam(storage=storage)
        assert await wam.is_registered() is True


class TestWebAuthnGetCredentialsInfo:
    """get_credentials_info shapes stored credentials into the
    UI-facing dict {id, device_name, created_at}."""

    async def test_empty_returns_empty_list(self):
        wam = _wam()
        assert await wam.get_credentials_info("user-1") == []

    async def test_returns_credentials_with_expected_shape(self):
        storage = _FakeCredentialStorage()
        await storage.save_credential(
            user_id="user-1",
            credential_id="cred-1",
            public_key="pk-1",
            sign_count=0,
            device_name="iPhone",
        )
        wam = _wam(storage=storage)
        out = await wam.get_credentials_info("user-1")
        assert len(out) == 1
        entry = out[0]
        assert set(entry.keys()) == {"id", "device_name", "created_at"}
        assert entry["id"] == "cred-1"
        assert entry["device_name"] == "iPhone"


class TestWebAuthnDeleteCredential:
    """delete_credential refuses to delete a user's only credential.
    Pin so a user who hits "remove" on their last passkey doesn't
    lock themselves out — the API surface forces them to register
    a new one first."""

    async def test_cannot_delete_last_credential(self):
        storage = _FakeCredentialStorage()
        await storage.save_credential(
            user_id="user-1",
            credential_id="only-one",
            public_key="pk",
            sign_count=0,
        )
        wam = _wam(storage=storage)
        with pytest.raises(ValueError, match="only passkey"):
            await wam.delete_credential("only-one", "user-1")
        # Confirm the credential is still there
        assert await storage.count_credentials("user-1") == 1

    async def test_can_delete_when_multiple_exist(self):
        storage = _FakeCredentialStorage()
        await storage.save_credential(
            user_id="user-1",
            credential_id="cred-1",
            public_key="pk-1",
            sign_count=0,
        )
        await storage.save_credential(
            user_id="user-1",
            credential_id="cred-2",
            public_key="pk-2",
            sign_count=0,
        )
        wam = _wam(storage=storage)
        assert await wam.delete_credential("cred-1", "user-1") is True
        assert await storage.count_credentials("user-1") == 1

    async def test_delete_scoped_to_owning_user(self):
        """User A cannot delete User B's credential — pin the
        scoping so a compromised account can't strip another
        user's passkeys."""
        storage = _FakeCredentialStorage()
        # B has 2, A has 2 (so the last-one guard doesn't fire on A)
        for uid, cid in [
            ("user-B", "b1"),
            ("user-B", "b2"),
            ("user-A", "a1"),
            ("user-A", "a2"),
        ]:
            await storage.save_credential(
                user_id=uid, credential_id=cid, public_key="pk", sign_count=0
            )
        wam = _wam(storage=storage)
        # User A tries to delete User B's credential
        result = await wam.delete_credential("b1", "user-A")
        assert result is False
        # B's credentials are intact
        assert await storage.count_credentials("user-B") == 2


# Settings — JWT_SECRET length validator


class TestJwtSecretValidator:
    """JWT_SECRET must be at least 32 bytes (RFC 7518 §3.2 for
    HS256). The validator is the only thing standing between a
    deploy with a too-short shared secret and an attacker who
    can mint session tokens.

    Why this matters: pyjwt logs `InsecureKeyLengthWarning` on
    short keys but still signs with them. A self-host that
    forgot to set JWT_SECRET (and got the dev fallback) or
    typed a 16-character password would have been silently
    insecure. Pin so the validator fires before the app starts."""

    def test_short_secret_rejected_at_construction(self, monkeypatch):
        """An 11-byte secret (the previous .env.test value) is
        now rejected by Settings(). Pin so a regression in the
        validator surfaces immediately rather than after a
        Settings refactor."""
        from pydantic import ValidationError

        from beats.settings import Settings

        monkeypatch.setenv("JWT_SECRET", "test-secret")  # 11 bytes
        with pytest.raises(ValidationError) as exc:
            Settings()
        # Error message tells the operator how to generate a key
        msg = str(exc.value)
        assert "32 bytes" in msg
        assert "openssl rand" in msg
        # …and not what the key was. Settings() is built at import, so this
        # text is the whole of what a Cloud Run revision that fails to start
        # leaves in the logs, where it is kept 30 days (#376).
        assert "test-secret" not in msg
        assert "input_value" not in msg

    def test_a_missing_setting_does_not_print_the_ones_that_were_read(self, monkeypatch):
        """pydantic's `input_value=` for a missing field is a shortened copy
        of the whole mapping it read — the start of DB_DSN, the tail of
        JWT_SECRET. The field's name is what an operator needs; the values
        are secrets."""
        from pydantic import ValidationError

        from beats.settings import Settings

        monkeypatch.setenv("DB_DSN", "mongodb://dummyuser:dummypassword@localhost:27017")
        monkeypatch.setenv("JWT_SECRET", "s" * 40)
        monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)

        # _env_file=None so .env.test's value for it doesn't fill the gap.
        with pytest.raises(ValidationError) as exc:
            Settings(_env_file=None)

        msg = str(exc.value)
        assert "FORWARDED_ALLOW_IPS" in msg
        assert "dummypassword" not in msg
        assert "s" * 40 not in msg
        assert "input_value" not in msg

    def test_exact_32_byte_secret_accepted(self, monkeypatch):
        """The 32-byte boundary case is accepted (>=, not >).
        Pin so a `openssl rand -base64 24` (which yields a
        32-byte base64 string) is exactly at the threshold."""
        from beats.settings import Settings

        secret = "x" * 32
        monkeypatch.setenv("JWT_SECRET", secret)
        s = Settings()
        assert s.jwt_secret == secret

    def test_long_secret_accepted(self, monkeypatch):
        """A typical openssl-generated 48-byte secret passes."""
        from beats.settings import Settings

        secret = "W2wIN5fOg1WaO7KSekBWsTnqFp4MnRVXIDEkOhWp9vRqEQ7+y/lqBvBe7yVe7Ev1"
        monkeypatch.setenv("JWT_SECRET", secret)
        s = Settings()
        assert s.jwt_secret == secret

    def test_byte_length_not_character_length(self, monkeypatch):
        """The validator counts UTF-8 BYTES, not Python str
        characters. A 32-character string with multi-byte
        runes encodes to >32 bytes and passes; a 31-character
        ASCII string fails. Pin so a refactor to len(v) instead
        of len(v.encode('utf-8')) is caught."""
        from pydantic import ValidationError

        from beats.settings import Settings

        # 31 ASCII chars = 31 bytes → should fail
        short_ascii = "x" * 31
        monkeypatch.setenv("JWT_SECRET", short_ascii)
        with pytest.raises(ValidationError):
            Settings()

        # 11 chars × 3 bytes (em dashes are 3 bytes in UTF-8) = 33 bytes
        # → should pass even though the str is short
        multibyte = "—" * 11  # 11 em dashes = 33 bytes
        monkeypatch.setenv("JWT_SECRET", multibyte)
        s = Settings()
        assert s.jwt_secret == multibyte


class TestForwardedAllowIps:
    """FORWARDED_ALLOW_IPS names the proxies whose X-Forwarded-For the rate
    limits believe. Both ways it can be wrong are quiet — trust too little and
    every visitor shares the proxy's bucket, trust everything and a client
    picks its own — so it has no default, and an entry uvicorn would read as a
    name no address matches is refused rather than trusting nothing."""

    @pytest.mark.parametrize(
        "value",
        [
            "*",
            "0.0.0.0/0",
            "::/0",
            "169.254.169.126/16",  # host bits set: a typo for /32 or for .0.0/16
            "cloud-run",
            "169.254.0.0/16,",
            "",
        ],
    )
    def test_refused(self, monkeypatch, value):
        from pydantic import ValidationError

        from beats.settings import Settings

        monkeypatch.setenv("FORWARDED_ALLOW_IPS", value)
        with pytest.raises(ValidationError, match="FORWARDED_ALLOW_IPS"):
            Settings()

    def test_addresses_and_networks_are_read_as_one_list(self, monkeypatch):
        from beats.settings import Settings

        monkeypatch.setenv("FORWARDED_ALLOW_IPS", " 169.254.0.0/16 , 172.30.208.10,::1")
        assert Settings().forwarded_allow_ips == "169.254.0.0/16,172.30.208.10,::1"

    def test_required(self, monkeypatch):
        from pydantic import ValidationError

        from beats.settings import Settings

        monkeypatch.delenv("FORWARDED_ALLOW_IPS", raising=False)
        monkeypatch.setenv("JWT_SECRET", "x" * 32)
        with pytest.raises(ValidationError, match="FORWARDED_ALLOW_IPS"):
            Settings(_env_file=None)


# MongoCredentialStorage — real-Mongo CRUD coverage


class TestMongoCredentialStorage:
    """Direct CRUD tests for the Mongo-backed credential store. The
    earlier WebAuthn tests use _FakeCredentialStorage; this class
    pins the actual MongoCredentialStorage implementation against
    a real test Mongo (via testcontainers in conftest).

    Why bother when the in-memory fake has the same surface: the
    real implementation handles dict→StoredCredential conversion,
    Mongo's $set update semantics, and the count_documents query
    shape. A regression in any of those three would silently break
    auth across the deploy without any test failure (the
    in-memory fake has different code paths)."""

    @pytest.fixture(autouse=True)
    async def _setup(self):
        from beats.infrastructure.database import Database

        await Database.connect(settings.db_dsn, settings.db_name)
        db = Database.get_db()
        await db.credentials.delete_many({})
        yield
        await Database.disconnect()

    def _store(self):
        from beats.auth.storage import MongoCredentialStorage
        from beats.infrastructure.database import Database

        return MongoCredentialStorage(Database.get_db().credentials)

    async def test_save_and_get_round_trip(self):
        """save_credential persists; get_credentials returns it
        with the matching shape. Pin the dict→StoredCredential
        conversion."""
        store = self._store()
        await store.save_credential(
            user_id="user-A",
            credential_id="cred-1",
            public_key="pk-1",
            sign_count=0,
            device_name="iPhone",
        )
        creds = await store.get_credentials(user_id="user-A")
        assert len(creds) == 1
        assert creds[0].credential_id == "cred-1"
        assert creds[0].public_key == "pk-1"
        assert creds[0].sign_count == 0
        assert creds[0].device_name == "iPhone"
        assert creds[0].created_at  # non-empty ISO timestamp

    async def test_is_registered_scoped_to_user(self):
        """is_registered with a user_id only sees that user's
        credentials. Pin so a regression doesn't accidentally
        do a global count and report cross-user state."""
        store = self._store()
        # User A has a credential, User B does not
        await store.save_credential(
            user_id="user-A",
            credential_id="cred-A",
            public_key="pk",
            sign_count=0,
        )
        assert await store.is_registered("user-A") is True
        assert await store.is_registered("user-B") is False
        # Global is_registered (no user) sees A's credential
        assert await store.is_registered() is True

    async def test_get_credentials_filters_by_user(self):
        """A and B have credentials; get_credentials(user_id="A")
        returns only A's. Pin the user-scoping — the Settings →
        Passkeys panel binds to this."""
        store = self._store()
        await store.save_credential(
            user_id="user-A", credential_id="a1", public_key="pk", sign_count=0
        )
        await store.save_credential(
            user_id="user-B", credential_id="b1", public_key="pk", sign_count=0
        )
        a_creds = await store.get_credentials(user_id="user-A")
        b_creds = await store.get_credentials(user_id="user-B")
        assert {c.credential_id for c in a_creds} == {"a1"}
        assert {c.credential_id for c in b_creds} == {"b1"}

    async def test_get_credential_by_id_user_agnostic(self):
        """get_credential_by_id is the login path — by design it
        does NOT filter by user (the user is unknown until the
        credential matches). Pin so a regression doesn't add a
        spurious user_id filter that would break login."""
        store = self._store()
        await store.save_credential(
            user_id="user-A", credential_id="lookup-me", public_key="pk", sign_count=5
        )
        cred = await store.get_credential_by_id("lookup-me")
        assert cred is not None
        assert cred.credential_id == "lookup-me"
        assert cred.sign_count == 5

    async def test_get_credential_by_id_returns_none_for_missing(self):
        """Unknown credential_id → None (not raise). Pin so the
        login service's "Credential not found" ValueError fires
        instead of an unhandled exception."""
        store = self._store()
        result = await store.get_credential_by_id("ghost")
        assert result is None

    async def test_get_user_id_for_credential_round_trip(self):
        """get_user_id_for_credential returns the owning user_id
        — used during login to resolve credential → user. Pin
        the user_id is correct."""
        store = self._store()
        await store.save_credential(
            user_id="user-42", credential_id="cred-42", public_key="pk", sign_count=0
        )
        owner = await store.get_user_id_for_credential("cred-42")
        assert owner == "user-42"
        # Unknown id → None
        assert await store.get_user_id_for_credential("ghost") is None

    async def test_update_sign_count_persists(self):
        """update_sign_count overwrites the sign_count field —
        the WebAuthn replay-attack prevention mechanism. Pin
        that the new value is read back AND that the function
        returns True on success."""
        store = self._store()
        await store.save_credential(
            user_id="user-A", credential_id="cred-A", public_key="pk", sign_count=10
        )
        result = await store.update_sign_count("cred-A", 42)
        assert result is True
        # Confirm persisted
        cred = await store.get_credential_by_id("cred-A")
        assert cred is not None
        assert cred.sign_count == 42

    async def test_update_sign_count_returns_false_for_unknown_credential(self):
        """update_sign_count for a missing credential_id → False
        (not raise, not silently succeed). Pin so a stale
        credential reference doesn't quietly succeed and let
        an attacker-controlled sign_count slip through."""
        store = self._store()
        result = await store.update_sign_count("nonexistent", 99)
        assert result is False

    async def test_delete_credential_scoped_to_user(self):
        """delete_credential requires BOTH credential_id AND
        user_id to match. Pin so User A can't delete User B's
        credential (mirrors the WebAuthnManager test, but here
        verifies the actual Mongo query rather than the
        in-memory fake)."""
        store = self._store()
        await store.save_credential(
            user_id="user-A", credential_id="a1", public_key="pk", sign_count=0
        )
        await store.save_credential(
            user_id="user-B", credential_id="b1", public_key="pk", sign_count=0
        )
        # User A tries to delete User B's credential → False
        result = await store.delete_credential("b1", "user-A")
        assert result is False
        # B's credential is intact
        assert await store.get_credential_by_id("b1") is not None
        # A deleting their own credential succeeds
        result = await store.delete_credential("a1", "user-A")
        assert result is True
        assert await store.get_credential_by_id("a1") is None

    async def test_count_credentials_per_user(self):
        """count_credentials returns the count for one user only.
        Pin the user-scoping — the WebAuthnManager.delete-
        credential guard ("can't delete your only passkey") relies
        on this returning the per-user count, not the global one."""
        store = self._store()
        await store.save_credential(
            user_id="user-A", credential_id="a1", public_key="pk", sign_count=0
        )
        await store.save_credential(
            user_id="user-A", credential_id="a2", public_key="pk", sign_count=0
        )
        await store.save_credential(
            user_id="user-B", credential_id="b1", public_key="pk", sign_count=0
        )
        assert await store.count_credentials("user-A") == 2
        assert await store.count_credentials("user-B") == 1
        assert await store.count_credentials("user-C") == 0

    async def test_get_credential_ids_returns_id_list(self):
        """get_credential_ids is a thin wrapper over get_credentials
        that flattens to a list of strings. Used by
        get_registration_options to build excludeCredentials. Pin
        so the dict→[str] mapping doesn't drift."""
        store = self._store()
        await store.save_credential(
            user_id="user-A", credential_id="a1", public_key="pk", sign_count=0
        )
        await store.save_credential(
            user_id="user-A", credential_id="a2", public_key="pk", sign_count=0
        )
        ids = await store.get_credential_ids(user_id="user-A")
        assert set(ids) == {"a1", "a2"}
