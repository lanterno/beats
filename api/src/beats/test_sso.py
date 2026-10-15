"""Unit tests for single sign-on — the OpenID Connect client and account mapping.

No database and no network: the provider is `fake_idp.FakeIdP` behind
`httpx.MockTransport`, signing real RS256 tokens, and the user store is a small
in-memory fake. The checks on the ID token are the security boundary of the
whole feature, so each one has a test that fails it on purpose.
"""

import time

import httpx
import pytest

from beats.auth.oidc import OIDCIdentity, OIDCRejected, OIDCUnavailable, new_pkce_pair
from beats.auth.sso_accounts import (
    SSOAccountService,
    SSOAlreadyLinked,
    SSOLastCredential,
    SSONotLinked,
    SSOProviderLinked,
    SSOSignupClosed,
    sso_email_for,
)
from beats.domain.models import LinkedIdentity, User
from beats.settings import OIDCProviderSettings
from fake_idp import CLIENT_ID, ISSUER, REDIRECT_URI, FakeIdP


@pytest.fixture
def idp() -> FakeIdP:
    return FakeIdP()


async def sign_in(idp: FakeIdP, provider=None, **claims) -> OIDCIdentity:
    """The whole round trip: authorization URL, the provider's code, redemption."""
    provider = provider or idp.provider()
    verifier, challenge = new_pkce_pair()
    url = await provider.authorization_url(
        redirect_uri=REDIRECT_URI, state="st", nonce="n-1", code_challenge=challenge
    )
    code = idp.issue_code(url, **claims)
    return await provider.redeem(
        code=code, code_verifier=verifier, redirect_uri=REDIRECT_URI, nonce="n-1"
    )


async def redeem_token(idp: FakeIdP, id_token: str, nonce: str = "n-1") -> OIDCIdentity:
    """Redeem a code whose token response carries exactly `id_token`."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/token":
            return httpx.Response(200, json={"id_token": id_token})
        return idp.handle(request)

    provider = idp.provider()
    provider._transport = httpx.MockTransport(handler)
    return await provider.redeem(
        code="c", code_verifier="v", redirect_uri=REDIRECT_URI, nonce=nonce
    )


class TestRoundTrip:
    async def test_signs_in_with_the_providers_subject(self, idp):
        identity = await sign_in(idp, sub="abc", name="Ada", email="ada@example.com")
        assert identity == OIDCIdentity(
            provider="test", issuer=ISSUER, subject="abc", name="Ada", email="ada@example.com"
        )

    async def test_the_authorization_url_carries_pkce_and_the_nonce(self, idp):
        url = await idp.provider().authorization_url(
            redirect_uri=REDIRECT_URI, state="st", nonce="nn", code_challenge="cc"
        )
        query = httpx.URL(url).params
        assert url.startswith(f"{ISSUER}/authorize?")
        assert query["code_challenge_method"] == "S256"
        assert (query["state"], query["nonce"], query["code_challenge"]) == ("st", "nn", "cc")
        assert query["scope"] == "openid email profile"

    async def test_a_used_code_is_refused(self, idp):
        provider = idp.provider()
        verifier, challenge = new_pkce_pair()
        url = await provider.authorization_url(
            redirect_uri=REDIRECT_URI, state="s", nonce="n-1", code_challenge=challenge
        )
        code = idp.issue_code(url)
        args = {
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": REDIRECT_URI,
            "nonce": "n-1",
        }
        await provider.redeem(**args)
        with pytest.raises(OIDCRejected):
            await provider.redeem(**args)

    async def test_the_wrong_verifier_is_refused(self, idp):
        provider = idp.provider()
        _, challenge = new_pkce_pair()
        url = await provider.authorization_url(
            redirect_uri=REDIRECT_URI, state="s", nonce="n-1", code_challenge=challenge
        )
        code = idp.issue_code(url)
        with pytest.raises(OIDCRejected):
            await provider.redeem(
                code=code, code_verifier="not-it", redirect_uri=REDIRECT_URI, nonce="n-1"
            )

    async def test_client_secret_post_when_basic_is_not_offered(self, idp):
        idp.auth_methods = ["client_secret_post"]
        await sign_in(idp)
        request = idp.token_requests[-1]
        assert "authorization" not in request.headers
        assert b"client_secret=s3cret" in request.content

    async def test_a_public_client_sends_no_secret(self, idp):
        await sign_in(idp, provider=idp.provider(client_secret=""))
        request = idp.token_requests[-1]
        assert "authorization" not in request.headers
        assert b"client_secret" not in request.content


class TestIdTokenChecks:
    async def test_another_audience_is_refused(self, idp):
        with pytest.raises(OIDCRejected):
            await redeem_token(idp, idp.id_token(sub="x", nonce="n-1", aud="someone-else"))

    async def test_several_audiences_need_azp_naming_us(self, idp):
        aud = [CLIENT_ID, "other"]
        with pytest.raises(OIDCRejected):
            await redeem_token(idp, idp.id_token(sub="x", nonce="n-1", aud=aud))
        ok = await redeem_token(idp, idp.id_token(sub="x", nonce="n-1", aud=aud, azp=CLIENT_ID))
        assert ok.subject == "x"

    async def test_another_issuer_is_refused(self, idp):
        with pytest.raises(OIDCRejected):
            await redeem_token(idp, idp.id_token(sub="x", nonce="n-1", iss="https://evil.test"))

    async def test_an_expired_token_is_refused(self, idp):
        past = int(time.time()) - 3600
        with pytest.raises(OIDCRejected):
            await redeem_token(idp, idp.id_token(sub="x", nonce="n-1", iat=past, exp=past + 60))

    async def test_another_sign_ins_nonce_is_refused(self, idp):
        with pytest.raises(OIDCRejected):
            await redeem_token(idp, idp.id_token(sub="x", nonce="replayed"))

    async def test_a_token_without_a_nonce_is_refused(self, idp):
        with pytest.raises(OIDCRejected):
            await redeem_token(idp, idp.id_token(sub="x"))

    async def test_a_symmetric_algorithm_is_refused(self, idp):
        # Signed with the client secret: anyone holding it could mint one.
        import jwt

        now = int(time.time())
        forged = jwt.encode(
            {
                "iss": ISSUER,
                "aud": CLIENT_ID,
                "sub": "x",
                "nonce": "n-1",
                "iat": now,
                "exp": now + 60,
            },
            "s3cret-but-padded-to-32-bytes-for-hs256",
            algorithm="HS256",
            headers={"kid": "k1"},
        )
        with pytest.raises(OIDCRejected):
            await redeem_token(idp, forged)

    async def test_an_unsigned_token_is_refused(self, idp):
        import base64
        import json

        def part(obj: dict) -> str:
            return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()

        unsigned = f"{part({'alg': 'none'})}.{part({'iss': ISSUER, 'sub': 'x', 'nonce': 'n-1'})}."
        with pytest.raises(OIDCRejected):
            await redeem_token(idp, unsigned)

    async def test_a_token_signed_by_another_key_is_refused(self, idp):
        from cryptography.hazmat.primitives.asymmetric import rsa

        idp.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with pytest.raises(OIDCRejected):
            await redeem_token(idp, idp.id_token(sub="x", nonce="n-1"))


class TestKeys:
    async def test_a_rotated_key_is_fetched_once_more(self, idp):
        provider = idp.provider()
        await sign_in(idp, provider=provider)
        assert idp.jwks_fetches == 1

        # The provider rotates: tokens now name a key we haven't cached.
        from fake_idp import _jwk

        idp.kid = "k2"
        idp.jwks = [_jwk(idp.key, "k2")]
        original = idp.id_token
        idp.id_token = lambda **c: original(kid="k2", **c)
        identity = await sign_in(idp, provider=provider)
        assert identity.subject == "idp-user-1"
        assert idp.jwks_fetches == 2

    async def test_an_unknown_key_after_refetching_is_refused(self, idp):
        with pytest.raises(OIDCRejected):
            await redeem_token(idp, idp.id_token(kid="nope", sub="x", nonce="n-1"))

    async def test_no_kid_is_fine_with_a_single_published_key(self, idp):
        identity = await redeem_token(idp, idp.id_token(kid=None, sub="x", nonce="n-1"))
        assert identity.subject == "x"


class TestProviderTrouble:
    async def test_discovery_naming_another_issuer_is_unavailable(self, idp):
        idp.discovery_issuer = "https://elsewhere.test"
        with pytest.raises(OIDCUnavailable):
            await sign_in(idp)

    async def test_a_provider_that_is_down_is_unavailable(self, idp):
        def down(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        provider = idp.provider()
        provider._transport = httpx.MockTransport(down)
        with pytest.raises(OIDCUnavailable):
            await provider.authorization_url(
                redirect_uri=REDIRECT_URI, state="s", nonce="n", code_challenge="c"
            )

    async def test_a_token_endpoint_error_is_unavailable_not_rejected(self, idp):
        idp.token_status = 502
        with pytest.raises(OIDCUnavailable):
            await sign_in(idp)


class TestProviderSettings:
    def test_issuer_must_be_https_except_on_localhost(self):
        base = {"id": "x", "name": "X", "client_id": "c"}
        with pytest.raises(ValueError, match="https"):
            OIDCProviderSettings(**base, issuer="http://idp.example.com")
        assert OIDCProviderSettings(**base, issuer="http://localhost:9000/").issuer == (
            "http://localhost:9000"
        )

    def test_scopes_must_include_openid(self):
        with pytest.raises(ValueError, match="openid"):
            OIDCProviderSettings(
                id="x", name="X", client_id="c", issuer=ISSUER, scopes="email profile"
            )


# Account mapping


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

    async def get_by_identity(self, issuer: str, subject: str) -> User | None:
        return next(
            (
                u
                for u in self._users.values()
                if any(i.issuer == issuer and i.subject == subject for i in u.identities)
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


def identity(
    subject: str = "sub-1",
    provider: str = "test",
    name: str | None = "Ada",
    email: str | None = "ada@example.com",
) -> OIDCIdentity:
    return OIDCIdentity(provider=provider, issuer=ISSUER, subject=subject, name=name, email=email)


def linked(subject: str = "sub-1", provider: str = "test") -> LinkedIdentity:
    return LinkedIdentity(provider=provider, issuer=ISSUER, subject=subject)


class TestSignIn:
    async def test_a_linked_identity_signs_into_its_account(self):
        repo = FakeUserRepo([User(email="a@x.com", identities=[linked()])])
        user, created = await SSOAccountService(repo).sign_in(identity(), allow_signup=False)
        assert (user.email, created) == ("a@x.com", False)

    async def test_an_unknown_identity_is_refused_when_signup_is_off(self):
        with pytest.raises(SSOSignupClosed):
            await SSOAccountService(FakeUserRepo()).sign_in(identity(), allow_signup=False)

    async def test_the_same_email_does_not_reach_an_existing_account(self):
        # Matching on the address is the account-takeover bug; it must not happen.
        repo = FakeUserRepo([User(email="ada@example.com")])
        with pytest.raises(SSOSignupClosed):
            await SSOAccountService(repo).sign_in(identity(), allow_signup=False)

    async def test_signup_creates_an_account_on_an_unregisterable_address(self):
        repo = FakeUserRepo()
        user, created = await SSOAccountService(repo).sign_in(identity(), allow_signup=True)
        assert created
        assert user.sso_provisioned
        assert user.email.endswith("@sso.invalid")
        assert user.display_name == "Ada"
        assert [(i.provider, i.subject) for i in user.identities] == [("test", "sub-1")]

    async def test_the_address_is_per_issuer_and_subject(self):
        a = sso_email_for(identity("one"))
        assert a == sso_email_for(identity("one"))
        assert a != sso_email_for(identity("two"))
        other_issuer = OIDCIdentity("test", "https://other.test", "one", None, None)
        assert a != sso_email_for(other_issuer)

    async def test_signing_in_refreshes_what_the_provider_owns(self):
        repo = FakeUserRepo()
        accounts = SSOAccountService(repo)
        user, _ = await accounts.sign_in(identity(), allow_signup=True)
        renamed = identity(name="Ada L.", email="ada@new.example.com", provider="renamed")
        user, _ = await accounts.sign_in(renamed, allow_signup=True)
        assert user.display_name == "Ada L."
        assert (user.identities[0].provider, user.identities[0].email) == (
            "renamed",
            "ada@new.example.com",
        )

    async def test_the_provider_does_not_rename_an_account_it_did_not_create(self):
        repo = FakeUserRepo([User(email="a@x.com", display_name="Mine", identities=[linked()])])
        user, _ = await SSOAccountService(repo).sign_in(identity(name="Theirs"), allow_signup=True)
        assert user.display_name == "Mine"


class TestLink:
    async def test_links_a_new_identity(self):
        repo = FakeUserRepo([User(email="a@x.com")])
        user = await SSOAccountService(repo).link("u1", identity())
        assert [i.subject for i in user.identities] == ["sub-1"]

    async def test_an_identity_on_another_account_is_refused(self):
        repo = FakeUserRepo([User(email="a@x.com", identities=[linked()]), User(email="b@x.com")])
        with pytest.raises(SSOAlreadyLinked):
            await SSOAccountService(repo).link("u2", identity())

    async def test_a_second_identity_at_the_same_provider_is_refused(self):
        repo = FakeUserRepo([User(email="a@x.com", identities=[linked("first")])])
        with pytest.raises(SSOProviderLinked):
            await SSOAccountService(repo).link("u1", identity("second"))

    async def test_identities_at_two_providers_sit_side_by_side(self):
        repo = FakeUserRepo([User(email="a@x.com", identities=[linked(provider="google")])])
        user = await SSOAccountService(repo).link("u1", identity("sub-2", provider="work"))
        assert sorted(i.provider for i in user.identities) == ["google", "work"]


class TestUnlink:
    async def test_refused_when_nothing_else_would_sign_in(self):
        repo = FakeUserRepo([User(email="a@x.com", identities=[linked()])])
        with pytest.raises(SSOLastCredential):
            await SSOAccountService(repo).unlink("u1", "test", passkey_count=0)

    async def test_another_identity_is_enough_to_keep_a_way_in(self):
        repo = FakeUserRepo(
            [User(email="a@x.com", identities=[linked(), linked("s2", provider="work")])]
        )
        user = await SSOAccountService(repo).unlink("u1", "test", passkey_count=0)
        assert [i.provider for i in user.identities] == ["work"]

    async def test_a_passkey_is_enough_to_keep_a_way_in(self):
        repo = FakeUserRepo([User(email="a@x.com", identities=[linked()])])
        user = await SSOAccountService(repo).unlink("u1", "test", passkey_count=1)
        assert user.identities == []

    async def test_nothing_to_unlink(self):
        repo = FakeUserRepo([User(email="a@x.com")])
        with pytest.raises(SSONotLinked):
            await SSOAccountService(repo).unlink("u1", "test", passkey_count=1)
