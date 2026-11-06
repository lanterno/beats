"""The operator deployment's contract (docs/backoffice.md).

The wall test matters most: a sentinel is planted in every stored thing the
right-hand column of § *The line* names — a session's note and its day, a
project's and a team's name, a tag, an absence note, a client's name and
rate, a webhook URL's path, a coach message and a memory, an integration's
token, a biometric value, an organisation audit entry's reason — and every
operator response is searched for it. That is how "never user content" stops
being a sentence in a roadmap and becomes something CI refuses.

The isolation pins run in fresh interpreters: `operator_server` imports
without `beats.settings` ever loading (the operator deployment never holds
JWT_SECRET), and `server` imports no operator router.
"""

import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

import httpx
import jwt
import jwt.algorithms
import pytest
from bson import ObjectId

# OperatorSettings is built when operator_server imports, so its environment
# is set here, before the import below. pytest_configure (conftest.py) has
# already started the Mongo container and set DB_DSN/DB_NAME.
OPERATOR_SUB = "test-operator"
VIEWER_SUB = "test-viewer"
ORIGIN = "http://backoffice.test"
os.environ["BEATS_OPERATOR_ENV_FILE"] = ".env.operator.does-not-exist"
os.environ["BACKOFFICE_DEV_OPERATOR"] = OPERATOR_SUB
os.environ["OPERATOR_ALLOWLIST"] = (
    f'[{{"sub": "{OPERATOR_SUB}", "email": "op@example.test", "role": "operator"}},'
    f' {{"sub": "{VIEWER_SUB}", "email": "viewer@example.test", "role": "viewer"}}]'
)
os.environ["OPERATOR_ORIGIN"] = ORIGIN
os.environ["OPERATOR_DB_DSN"] = os.environ.get("DB_DSN", "mongodb://localhost:27017")
os.environ["OPERATOR_DB_NAME"] = os.environ.get("DB_NAME", "beats_test")

from operator_server import app as operator_app  # noqa: E402

SENTINEL = "walltest-sentinel-7f3a9"
# A number no count or size in a small test database can coincide with.
RATE_SENTINEL = 86423911
BIOMETRIC_SENTINEL = 77311733
# A session planted years before the run, so no account's own dates match.
OLD_DAY = "1999-04-12"


@pytest.fixture(scope="class")
def operator_client():
    from starlette.testclient import TestClient

    with TestClient(operator_app) as client:
        yield client


def _env_for_subprocess() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent)
    return env


class TestIsolation:
    """The two invariants that make one codebase safe to deploy twice."""

    def test_operator_server_never_loads_the_api_settings(self):
        """Run in a fresh interpreter: this test process imported
        beats.settings long ago, so asserting on its own sys.modules would
        prove nothing. Unsetting JWT_SECRET would prove nothing either —
        .env.test holds one."""
        code = (
            "import sys; import operator_server; "
            "assert 'beats.settings' not in sys.modules, 'operator root loaded the API settings'; "
            "assert 'beats.auth' not in sys.modules, 'operator root loaded beats.auth'"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=_env_for_subprocess(),
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent),
        )
        assert result.returncode == 0, result.stderr

    def test_the_public_app_imports_no_operator_route(self):
        """Not reachable by construction — this pins it for the day somebody
        adds the import."""
        code = (
            "import sys; import server; "
            "assert 'beats.api.routers.operator' not in sys.modules, "
            "'server.py imports the operator router'; "
            "assert 'beats.operator' not in sys.modules, 'server.py imports beats.operator'"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            env=_env_for_subprocess(),
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parent),
        )
        assert result.returncode == 0, result.stderr


class TestOperatorAuth:
    """The allowlist and the cross-site line."""

    def test_me_names_the_operator(self, operator_client):
        resp = operator_client.get("/api/operator/me")
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"sub": OPERATOR_SUB, "email": "op@example.test", "role": "operator"}

    def test_a_write_without_this_apps_origin_is_refused(self, operator_client):
        """IAP's cookie rides any request the browser makes, so a POST is
        taken only from this app's own pages — the account lookup included,
        though it reads. The typed confirmation is no defence
        here; a forging page sends it as easily as the operator types it."""
        body = {"email": "a@example.test"}
        no_origin = operator_client.post("/api/operator/accounts/lookup", json=body)
        assert no_origin.status_code == 403
        assert no_origin.json()["code"] == "OPERATOR_BAD_ORIGIN"

        foreign = operator_client.post(
            "/api/operator/accounts/lookup", json=body, headers={"Origin": "https://evil.test"}
        )
        assert foreign.status_code == 403

        cross_site = operator_client.post(
            "/api/operator/accounts/lookup",
            json=body,
            headers={"Origin": ORIGIN, "Sec-Fetch-Site": "cross-site"},
        )
        assert cross_site.status_code == 403

        own = operator_client.post(
            "/api/operator/accounts/lookup",
            json=body,
            headers={"Origin": ORIGIN, "Sec-Fetch-Site": "same-origin"},
        )
        assert own.status_code == 200, own.text

    def test_reads_need_no_origin(self, operator_client):
        assert operator_client.get("/api/operator/attention").status_code == 200


@pytest.fixture(scope="class")
def planted(mongo, operator_client):
    user_id = str(ObjectId())
    org_id = str(ObjectId())
    now = datetime.now(UTC)
    mongo.users.insert_one(
        {
            "_id": ObjectId(user_id),
            "email": "wall@example.test",
            "display_name": f"Name {SENTINEL}",
            "created_at": now.isoformat(),
            "identities": [{"provider": "idp", "issuer": "https://idp.test", "subject": "s-1"}],
        }
    )
    mongo.projects.insert_one(
        {"user_id": user_id, "name": f"Project {SENTINEL}", "archived": False}
    )
    mongo.projects.insert_one({"organisation_id": org_id, "name": f"Org project {SENTINEL}"})
    mongo.timeLogs.insert_one(
        {
            "user_id": user_id,
            "project_id": str(ObjectId()),
            "start": datetime.fromisoformat(f"{OLD_DAY}T09:00:00+00:00"),
            "end": datetime.fromisoformat(f"{OLD_DAY}T10:00:00+00:00"),
            "note": f"note {SENTINEL}",
            "tags": [f"tag-{SENTINEL}"],
        }
    )
    mongo.absences.insert_one(
        {
            "user_id": user_id,
            "project_id": str(ObjectId()),
            "date": OLD_DAY,
            "type": "vacation",
            "note": f"absence {SENTINEL}",
        }
    )
    mongo.clients.insert_one(
        {
            "user_id": user_id,
            "name": f"Client {SENTINEL}",
            "currency": "EUR",
            "rates": [{"effective_from": "2026-01-01", "rate_minor": RATE_SENTINEL}],
        }
    )
    mongo.webhooks.insert_one(
        {
            "user_id": user_id,
            "url": f"https://hooks.example.test/{SENTINEL}",
            "events": ["timer.start"],
            "active": True,
        }
    )
    mongo.coach_memory.insert_one({"user_id": user_id, "content": f"memory {SENTINEL}"})
    mongo.coach_conversations.insert_one(
        {"user_id": user_id, "messages": [{"role": "user", "content": f"chat {SENTINEL}"}]}
    )
    mongo.github_integrations.insert_one(
        {"user_id": user_id, "access_token": f"token-{SENTINEL}", "github_username": SENTINEL}
    )
    mongo.biometric_days.insert_one(
        {
            "user_id": user_id,
            "date": OLD_DAY,
            "source": "fitbit",
            "resting_heart_rate": BIOMETRIC_SENTINEL,
        }
    )
    mongo.flow_windows.insert_one(
        {
            "user_id": user_id,
            "window_start": now.isoformat(),
            "window_end": now.isoformat(),
            "flow_score": 0.5,
            "editor_repo": f"/home/x/{SENTINEL}",
            "dominant_bundle_id": f"com.{SENTINEL}",
        }
    )
    mongo.report_links.insert_one(
        {"user_id": user_id, "client_id": str(ObjectId()), "token": f"tok-{SENTINEL}"}
    )
    mongo.organisations.insert_one(
        {
            "_id": ObjectId(org_id),
            "name": "Wall Org",
            "created_by": user_id,
            "created_at": now.isoformat(),
        }
    )
    mongo.org_members.insert_one(
        {
            "organisation_id": org_id,
            "user_id": user_id,
            "role": "owner",
            "name": "Wall Owner",
            "email": "wall@example.test",
            "joined_at": now.isoformat(),
            "left_at": None,
        }
    )
    mongo.org_teams.insert_one(
        {"organisation_id": org_id, "name": f"Team {SENTINEL}", "member_ids": [user_id]}
    )
    mongo.org_audit.insert_one(
        {
            "organisation_id": org_id,
            "at": now.isoformat(),
            "actor_user_id": user_id,
            "event": "timesheet.reopened",
            "details": {"reason": f"reopened because {SENTINEL}"},
        }
    )
    mongo.llm_usage.insert_one(
        {
            "user_id": user_id,
            "model": "claude-sonnet-5-5",
            "input_tokens": 10,
            "output_tokens": 10,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "cost_usd": 0.01,
            "purpose": "chat",
            "ts": now,
        }
    )
    return {"user_id": user_id, "org_id": org_id}


class TestOperatorWall:
    """Plant the whole right-hand column, then read every page.

    The database user reads every collection; the wall is in the code and in
    this test, not the grant. The likeliest leaks sit beside reads the
    control plane does make: a webhook's URL read for its domain, an
    integration's document read for whether it exists, an audit event read
    without its details.
    """

    def _every_page(self, operator_client, planted) -> list[tuple[str, str]]:
        own = {"Origin": ORIGIN}
        pages = [
            ("GET", "/api/operator/me", None),
            ("GET", "/api/operator/attention", None),
            ("POST", "/api/operator/accounts/lookup", {"email": "wall@example.test"}),
            ("GET", f"/api/operator/accounts/{planted['user_id']}", None),
            ("GET", "/api/operator/organisations", None),
            ("GET", f"/api/operator/organisations/{planted['org_id']}", None),
            ("GET", f"/api/operator/organisations/{planted['org_id']}/audit", None),
            ("GET", "/api/operator/abuse", None),
            ("GET", "/api/operator/capacity", None),
            ("GET", "/api/operator/audit", None),
            ("GET", "/api/operator/jobs", None),
        ]
        bodies = []
        for method, path, body in pages:
            if method == "GET":
                resp = operator_client.get(path)
            else:
                resp = operator_client.post(path, json=body, headers=own)
            assert resp.status_code == 200, f"{path}: {resp.status_code} {resp.text}"
            bodies.append((path, resp.text))
        return bodies

    def test_no_byte_of_user_content_in_any_operator_response(self, operator_client, planted):
        for path, body in self._every_page(operator_client, planted):
            assert SENTINEL not in body, f"user content leaked on {path}"
            assert str(RATE_SENTINEL) not in body, f"a rate leaked on {path}"
            assert str(BIOMETRIC_SENTINEL) not in body, f"a biometric value leaked on {path}"
            # A session's time belongs to the person; the day last seen is a
            # field of its own, so a planted session decades back must not
            # surface its day anywhere.
            assert OLD_DAY not in body, f"a session's day leaked on {path}"

    def test_what_the_pages_do_show(self, operator_client, planted):
        """The wall has two sides: the left-hand column must actually be
        there, or the wall could pass by showing nothing at all."""
        account = operator_client.get(f"/api/operator/accounts/{planted['user_id']}").json()
        assert account["email"] == "wall@example.test"
        assert account["projects"] == 2 or account["projects"] == 1  # own; the org's is its own
        assert account["sessions"] == 1
        assert account["biometric_rows"] == 1
        assert account["storage_bytes"] > 0
        assert account["sso_providers"] == ["idp"]
        assert "github" in account["integrations"]
        assert account["organisations"][0]["organisation_name"] == "Wall Org"

        abuse = operator_client.get("/api/operator/abuse").json()
        assert {"domain": "hooks.example.test", "value": 1} in [
            dict(d) for d in abuse["webhook_domains"]
        ]

        audit = operator_client.get(f"/api/operator/organisations/{planted['org_id']}/audit").json()
        assert audit[0]["event"] == "timesheet.reopened"
        assert "details" not in audit[0]

    def test_the_lookup_is_case_insensitive_and_exact(self, operator_client, planted):
        own = {"Origin": ORIGIN}
        upper = operator_client.post(
            "/api/operator/accounts/lookup", json={"email": "WALL@EXAMPLE.TEST"}, headers=own
        )
        assert [m["id"] for m in upper.json()] == [planted["user_id"]]
        prefix = operator_client.post(
            "/api/operator/accounts/lookup", json={"email": "wall@"}, headers=own
        )
        assert prefix.json() == []


# ── the IAP verifier ─────────────────────────────────────────────────


AUDIENCE = "/projects/123/locations/europe-west1/services/beats-operator"


def _es256_keypair():
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    jwk = jwt.algorithms.ECAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk["kid"] = "kid-1"
    return key, jwk


def _verifier(jwk, audience=AUDIENCE):
    from beats.operator.iap import IAPVerifier

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"keys": [jwk]})

    return IAPVerifier(audience, transport=httpx.MockTransport(handler))


def _assertion(key, *, kid="kid-1", alg="ES256", **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": "https://cloud.google.com/iap",
        "aud": AUDIENCE,
        "sub": "accounts.google.com:111",
        "email": "op@example.test",
        "iat": now,
        "exp": now + 600,
        **overrides,
    }
    return jwt.encode(claims, key, algorithm=alg, headers={"kid": kid})


class TestIAPVerifier:
    """Each check Google's signed-headers guide requires has a test that
    fails it on purpose — the verifier is the whole production wall."""

    async def test_a_good_assertion_yields_its_claims(self):
        key, jwk = _es256_keypair()
        claims = await _verifier(jwk).verify(_assertion(key))
        assert claims["sub"] == "accounts.google.com:111"

    async def test_wrong_audience_is_rejected(self):
        from beats.operator.iap import IAPRejected

        key, jwk = _es256_keypair()
        with pytest.raises(IAPRejected):
            await _verifier(jwk).verify(_assertion(key, aud="/projects/999/other"))

    async def test_wrong_issuer_is_rejected(self):
        from beats.operator.iap import IAPRejected

        key, jwk = _es256_keypair()
        with pytest.raises(IAPRejected):
            await _verifier(jwk).verify(_assertion(key, iss="https://evil.test"))

    async def test_an_expired_assertion_is_rejected(self):
        from beats.operator.iap import IAPRejected

        key, jwk = _es256_keypair()
        now = int(time.time())
        with pytest.raises(IAPRejected):
            await _verifier(jwk).verify(_assertion(key, iat=now - 7200, exp=now - 3600))

    async def test_an_unknown_key_is_rejected(self):
        from beats.operator.iap import IAPRejected

        key, jwk = _es256_keypair()
        with pytest.raises(IAPRejected):
            await _verifier(jwk).verify(_assertion(key, kid="kid-unknown"))

    async def test_a_non_es256_algorithm_is_rejected_before_any_key_is_read(self):
        """`alg` is attacker-controlled; pinning ES256 before key lookup is
        what forecloses algorithm-confusion."""
        from beats.operator.iap import IAPRejected

        _key, jwk = _es256_keypair()
        hs = jwt.encode(
            {"iss": "https://cloud.google.com/iap", "aud": AUDIENCE, "sub": "x"},
            "a-shared-secret-of-at-least-32-bytes!!",
            algorithm="HS256",
            headers={"kid": "kid-1"},
        )
        with pytest.raises(IAPRejected):
            await _verifier(jwk).verify(hs)

    async def test_an_unreachable_key_set_is_unavailable_not_rejected(self):
        """Nothing is known about the caller either way — a 503, never a
        401 that reads as 'you are not allowed'."""
        from beats.operator.iap import IAPUnavailable, IAPVerifier

        key, _ = _es256_keypair()

        def down(request: httpx.Request) -> httpx.Response:
            return httpx.Response(502)

        verifier = IAPVerifier(AUDIENCE, transport=httpx.MockTransport(down))
        with pytest.raises(IAPUnavailable):
            await verifier.verify(_assertion(key))


class TestOperatorCommands:
    """POST /commands/{name}: the one path a mutation takes. The runner's
    gates (confirmation, role, unknown command), the delegation to the
    services that own each rule, and the audit that cannot be forgotten."""

    OWN: ClassVar[dict[str, str]] = {"Origin": ORIGIN}

    @pytest.fixture(autouse=True)
    def _clean(self, mongo):
        yield
        mongo.operator_audit.delete_many({})
        mongo.account_limits.delete_many({})

    def _user(self, mongo, email="cmd@example.test") -> str:
        user_id = str(ObjectId())
        mongo.users.insert_one(
            {"_id": ObjectId(user_id), "email": email, "created_at": datetime.now(UTC)}
        )
        return user_id

    def _run(self, operator_client, name, args, confirmation=None):
        return operator_client.post(
            f"/api/operator/commands/{name}",
            json={"args": args, "confirmation": confirmation},
            headers=self.OWN,
        )

    def test_suspend_needs_the_accounts_email_typed_back(self, operator_client, mongo):
        user_id = self._user(mongo)
        wrong = self._run(
            operator_client,
            "account.suspend",
            {"user_id": user_id, "reason": "scraping"},
            confirmation="someone-else@example.test",
        )
        assert wrong.status_code == 409
        assert wrong.json()["code"] == "CONFIRMATION_MISMATCH"
        assert mongo.users.find_one({"_id": ObjectId(user_id)}).get("suspended_at") is None

        right = self._run(
            operator_client,
            "account.suspend",
            {"user_id": user_id, "reason": "scraping"},
            confirmation="cmd@example.test",
        )
        assert right.status_code == 200, right.text
        assert mongo.users.find_one({"_id": ObjectId(user_id)})["suspended_at"] is not None

        # The audit cannot be forgotten: the runner is the only path, and the
        # entry carries before and after, the subject as subject_id (never
        # user_id, which erasure's sweep would take), and no address.
        entry = right.json()
        assert entry["command"] == "account.suspend"
        assert entry["subject_id"] == user_id
        assert entry["before"]["suspended"] is False
        assert entry["after"]["suspended"] is True
        stored = mongo.operator_audit.find_one({"subject_id": user_id})
        assert stored is not None
        assert "user_id" not in stored
        assert "cmd@example.test" not in str(stored)

    def test_unsuspend_set_limits_and_revoke_delegate(
        self, operator_client, mongo, auth_info, client
    ):
        user_id = self._user(mongo, "acts@example.test")
        self._run(
            operator_client,
            "account.suspend",
            {"user_id": user_id, "reason": "r"},
            confirmation="acts@example.test",
        )
        assert (
            self._run(operator_client, "account.unsuspend", {"user_id": user_id}).status_code == 200
        )
        assert mongo.users.find_one({"_id": ObjectId(user_id)})["suspended_at"] is None

        limits = self._run(
            operator_client,
            "account.set_limits",
            {"user_id": user_id, "writes_per_minute_beats": 5, "webhooks_disabled": True},
        )
        assert limits.status_code == 200, limits.text
        doc = mongo.account_limits.find_one({"user_id": user_id})
        assert doc["writes_per_minute_beats"] == 5
        assert doc["webhooks_disabled"] is True
        assert doc["set_by"] == OPERATOR_SUB
        assert (
            self._run(operator_client, "account.clear_limits", {"user_id": user_id}).status_code
            == 200
        )
        assert mongo.account_limits.find_one({"user_id": user_id}) is None

        # device.revoke: the narrow answer to one broken daemon.
        code = client.post("/api/device/pair/code", headers=auth_info["headers"]).json()["code"]
        device_id = client.post("/api/device/pair/exchange", json={"code": code}).json()[
            "device_id"
        ]
        revoked = self._run(
            operator_client,
            "device.revoke",
            {"user_id": auth_info["user_id"], "device_id": device_id},
        )
        assert revoked.status_code == 200, revoked.text
        assert mongo.device_registrations.find_one({"device_id": device_id})["revoked"] is True

    def test_sign_out_everywhere_sets_the_cut(self, operator_client, mongo):
        user_id = self._user(mongo, "cut@example.test")
        resp = self._run(operator_client, "account.sign_out_everywhere", {"user_id": user_id})
        assert resp.status_code == 200
        assert mongo.users.find_one({"_id": ObjectId(user_id)})["sessions_valid_after"]

    def test_suspend_refuses_the_erasure_kind(self, operator_client, mongo):
        """An erasure-kind suspension minted here would falsely promise a
        deletion date with no job behind it; that kind belongs to the
        erasure's own queueing."""
        user_id = self._user(mongo, "no-fake-erasure@example.test")
        resp = self._run(
            operator_client,
            "account.suspend",
            {"user_id": user_id, "kind": "erasure", "reason": "r"},
            confirmation="no-fake-erasure@example.test",
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "INVALID_COMMAND_ARGS"

    def test_an_unknown_command_is_404_and_bad_args_422(self, operator_client):
        assert self._run(operator_client, "account.explode", {"user_id": "x"}).status_code == 404
        bad = self._run(operator_client, "account.suspend", {"user_id": ""})
        assert bad.status_code == 422
        assert bad.json()["code"] == "INVALID_COMMAND_ARGS"

    async def test_a_viewer_runs_no_command(self):
        """The role gate is the runner's, so it holds for every command at
        once — pinned at the runner, since the dev stand-in fixes one
        identity per process."""
        from typing import cast

        from beats.operator.commands import CommandContext
        from beats.operator.runner import ViewerCannotAct, run_command
        from beats.operator.settings import OperatorIdentity

        # None stands in for everything after the role gate, which refuses
        # before any of it is touched.
        absent = cast("Any", None)
        ctx = CommandContext(
            operator=OperatorIdentity(sub=VIEWER_SUB, email="v@example.test", role="viewer"),
            db=absent,
            accounts=absent,
            organisations=absent,
            devices=absent,
        )
        with pytest.raises(ViewerCannotAct):
            await run_command(ctx, "account.unsuspend", {"user_id": "u"}, None)


class TestOperatorOrganisationActs:
    """The operator acts only for an organisation with no owner, and only
    when asked — and each act lands in the organisation's own audit log
    under actor_kind operator, with no operator id in it."""

    OWN: ClassVar[dict[str, str]] = {"Origin": ORIGIN}

    def _org(self, mongo, *, name="Orphaned Org", owner=False, closes_on=None) -> dict:
        org_id = str(ObjectId())
        mongo.organisations.insert_one(
            {
                "_id": ObjectId(org_id),
                "name": name,
                "created_by": "nobody",
                "created_at": datetime.now(UTC).isoformat(),
                "timezone": "UTC",
                "closes_on": closes_on,
            }
        )
        member_id = str(ObjectId())
        mongo.users.insert_one({"_id": ObjectId(member_id), "email": f"m-{member_id}@x.test"})
        mongo.org_members.insert_one(
            {
                "organisation_id": org_id,
                "user_id": member_id,
                "role": "owner" if owner else "admin",
                "name": "M",
                "email": f"m-{member_id}@x.test",
                "joined_at": datetime.now(UTC).isoformat(),
                "left_at": None,
            }
        )
        return {"org_id": org_id, "member_id": member_id}

    def _run(self, operator_client, name, args, confirmation=None):
        return operator_client.post(
            f"/api/operator/commands/{name}",
            json={"args": args, "confirmation": confirmation},
            headers=self.OWN,
        )

    def test_nothing_while_an_owner_exists(self, operator_client, mongo):
        planted = self._org(mongo, name="Owned Org", owner=True)
        resp = self._run(
            operator_client,
            "organisation.grant_owner",
            {"organisation_id": planted["org_id"], "user_id": planted["member_id"]},
            confirmation="Owned Org",
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "ORGANISATION_HAS_OWNER"

    def test_grant_owner_to_the_requester_with_the_organisations_name_typed(
        self, operator_client, mongo
    ):
        planted = self._org(mongo)
        args = {"organisation_id": planted["org_id"], "user_id": planted["member_id"]}

        unconfirmed = self._run(operator_client, "organisation.grant_owner", args)
        assert unconfirmed.status_code == 409
        assert unconfirmed.json()["code"] == "CONFIRMATION_MISMATCH"

        granted = self._run(
            operator_client, "organisation.grant_owner", args, confirmation="Orphaned Org"
        )
        assert granted.status_code == 200, granted.text
        member = mongo.org_members.find_one({"user_id": planted["member_id"]})
        assert member["role"] == "owner"

        # In the organisation's own log, as the operator and as nobody:
        # actor_kind says whose act it was, and no operator id is in it.
        row = mongo.org_audit.find_one(
            {"organisation_id": planted["org_id"], "event": "member.role_changed"}
        )
        assert row["actor_kind"] == "operator"
        assert row.get("actor_user_id") is None
        assert OPERATOR_SUB not in str(row)

    def test_the_requester_must_hold_the_highest_active_role(self, operator_client, mongo):
        planted = self._org(mongo)  # the candidate is an admin
        lower_id = str(ObjectId())
        mongo.org_members.insert_one(
            {
                "organisation_id": planted["org_id"],
                "user_id": lower_id,
                "role": "member",
                "name": "L",
                "email": "l@x.test",
                "joined_at": datetime.now(UTC).isoformat(),
                "left_at": None,
            }
        )
        refused = self._run(
            operator_client,
            "organisation.grant_owner",
            {"organisation_id": planted["org_id"], "user_id": lower_id},
            confirmation="Orphaned Org",
        )
        assert refused.status_code == 409
        assert refused.json()["code"] == "REQUESTER_NOT_HIGHEST"

    def test_a_closing_notice_may_always_move_later(self, operator_client, mongo):
        """Amends decision 29: a notice with five days left can be extended
        by a week, while a fresh short notice is still refused."""
        soon = (datetime.now(UTC).date() + timedelta(days=5)).isoformat()
        planted = self._org(mongo, name="Closing Org", closes_on=soon)

        later = (datetime.now(UTC).date() + timedelta(days=12)).isoformat()
        moved = self._run(
            operator_client,
            "organisation.begin_closing",
            {"organisation_id": planted["org_id"], "closes_on": later},
            confirmation="Closing Org",
        )
        assert moved.status_code == 200, moved.text
        assert (
            mongo.organisations.find_one({"_id": ObjectId(planted["org_id"])})["closes_on"] == later
        )

        earlier = (datetime.now(UTC).date() + timedelta(days=3)).isoformat()
        refused = self._run(
            operator_client,
            "organisation.begin_closing",
            {"organisation_id": planted["org_id"], "closes_on": earlier},
            confirmation="Closing Org",
        )
        assert refused.status_code == 409
        assert refused.json()["code"] == "CLOSE_NOTICE_TOO_SHORT"

        cancelled = self._run(
            operator_client,
            "organisation.cancel_closing",
            {"organisation_id": planted["org_id"]},
        )
        assert cancelled.status_code == 200
        assert (
            mongo.organisations.find_one({"_id": ObjectId(planted["org_id"])}).get("closes_on")
            is None
        )


def _run_jobs() -> int:
    """Drain the queue the way the Cloud Run Job does: a fresh client on a
    fresh loop, because the job runner is its own process in production."""
    import asyncio

    from pymongo import AsyncMongoClient

    from beats.operator.jobs import run_due_jobs

    async def go() -> int:
        client = AsyncMongoClient(os.environ.get("DB_DSN", "mongodb://localhost:27017"))
        try:
            return await run_due_jobs(client[os.environ.get("DB_NAME", "beats_test")])
        finally:
            await client.close()

    return asyncio.run(go())


class TestOperatorJobs:
    """The window, the queue, and the sweep that must not eat its own record."""

    OWN: ClassVar[dict[str, str]] = {"Origin": ORIGIN}

    @pytest.fixture(autouse=True)
    def _clean(self, mongo):
        mongo.operator_jobs.delete_many({})
        mongo.operator_audit.delete_many({})
        yield
        mongo.operator_jobs.delete_many({})
        mongo.operator_audit.delete_many({})

    def _user(self, mongo, email: str) -> str:
        user_id = str(ObjectId())
        mongo.users.insert_one(
            {"_id": ObjectId(user_id), "email": email, "created_at": datetime.now(UTC)}
        )
        return user_id

    def _run(self, operator_client, name, args, confirmation=None):
        return operator_client.post(
            f"/api/operator/commands/{name}",
            json={"args": args, "confirmation": confirmation},
            headers=self.OWN,
        )

    def _due_now(self, mongo, job_id: str):
        mongo.operator_jobs.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {"run_after": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()}},
        )

    def test_an_erasure_waits_out_its_window_suspended(self, operator_client, mongo):
        user_id = self._user(mongo, "erase-me@example.test")
        resp = self._run(
            operator_client,
            "account.erase",
            {"user_id": user_id},
            confirmation="erase-me@example.test",
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["queued"] is True
        job = body["job"]
        assert job["state"] == "queued"
        assert job["subject_id"] == user_id
        assert "user_id" not in job

        # Queueing suspended the account with the erasure's own wording — the
        # refusal names the day the window ends, inside the week there is to
        # stop it. Nothing is deleted yet.
        user = mongo.users.find_one({"_id": ObjectId(user_id)})
        assert user["suspended_kind"] == "erasure"
        run_after = datetime.fromisoformat(job["run_after"])
        assert run_after - datetime.now(UTC) > timedelta(days=6)

        # Second thoughts: job.cancel lifts that suspension — it was the
        # erasure's.
        cancelled = self._run(operator_client, "job.cancel", {"job_id": job["id"]})
        assert cancelled.status_code == 200, cancelled.text
        assert mongo.operator_jobs.find_one({"_id": ObjectId(job["id"])})["state"] == "cancelled"
        assert mongo.users.find_one({"_id": ObjectId(user_id)}).get("suspended_at") is None

    def test_cancelling_an_erasure_never_lifts_an_abuse_suspension(self, operator_client, mongo):
        user_id = self._user(mongo, "abusive@example.test")
        # Suspended for abuse first; the erasure queued on top keeps its own
        # wording, but cancelling it must not open the abuse door.
        self._run(
            operator_client,
            "account.suspend",
            {"user_id": user_id, "reason": "scraping"},
            confirmation="abusive@example.test",
        )
        job = self._run(
            operator_client,
            "account.erase",
            {"user_id": user_id},
            confirmation="abusive@example.test",
        ).json()["job"]
        # Put the abuse suspension back the way the operator would after a
        # mistaken queue-on-top: the kind decides what cancel may lift.
        mongo.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"suspended_kind": "abuse"}})

        self._run(operator_client, "job.cancel", {"job_id": job["id"]})

        assert mongo.users.find_one({"_id": ObjectId(user_id)})["suspended_at"] is not None

    def test_the_job_runs_the_erasure_and_the_sweep_spares_its_own_record(
        self, operator_client, mongo
    ):
        user_id = self._user(mongo, "gone@example.test")
        mongo.projects.insert_one({"user_id": user_id, "name": "P"})
        mongo.account_limits.insert_one({"user_id": user_id, "webhooks_disabled": True})

        job = self._run(
            operator_client,
            "account.erase",
            {"user_id": user_id},
            confirmation="gone@example.test",
        ).json()["job"]
        self._due_now(mongo, job["id"])

        assert _run_jobs() == 1

        # The account and everything keyed on it went — account_limits keyed
        # on user_id deliberately, so the sweep takes it — while the job's
        # own entry and the audit of the act survive: their subject is
        # subject_id, which the sweep never matches.
        assert mongo.users.find_one({"_id": ObjectId(user_id)}) is None
        assert mongo.projects.find_one({"user_id": user_id}) is None
        assert mongo.account_limits.find_one({"user_id": user_id}) is None
        job_row = mongo.operator_jobs.find_one({"_id": ObjectId(job["id"])})
        assert job_row["state"] == "done"
        audit = mongo.operator_audit.find_one({"subject_id": user_id})
        assert audit is not None
        assert audit["command"] == "account.erase"
        assert audit["operator_sub"] == OPERATOR_SUB
        assert "gone@example.test" not in str(audit)

    def test_a_deletion_queued_then_outranked_by_a_new_owner_fails_its_job(
        self, operator_client, mongo
    ):
        """A command's rules are checked when it runs, not when it was
        queued; and after three attempts the entry is failed, for the alert
        to see."""
        org_id = str(ObjectId())
        yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
        mongo.organisations.insert_one(
            {
                "_id": ObjectId(org_id),
                "name": "Doomed Org",
                "created_by": "x",
                "created_at": datetime.now(UTC).isoformat(),
                "timezone": "UTC",
                "closes_on": yesterday,
            }
        )
        job = self._run(
            operator_client,
            "organisation.delete",
            {"organisation_id": org_id},
            confirmation="Doomed Org",
        ).json()["job"]

        # An owner appears while the job waits.
        mongo.org_members.insert_one(
            {
                "organisation_id": org_id,
                "user_id": str(ObjectId()),
                "role": "owner",
                "name": "O",
                "email": "o@x.test",
                "joined_at": datetime.now(UTC).isoformat(),
                "left_at": None,
            }
        )

        self._due_now(mongo, job["id"])
        # One drain retries a due, failing entry up to its attempt cap —
        # three claims — and then marks it failed, for the alert to see.
        assert _run_jobs() == 3
        row = mongo.operator_jobs.find_one({"_id": ObjectId(job["id"])})
        assert row["state"] == "failed"
        assert row["attempts"] == 3
        assert "owner" in row["error"].lower()
        assert mongo.organisations.find_one({"_id": ObjectId(org_id)}) is not None

    def test_an_ownerless_organisations_deletion_runs_once_due(self, operator_client, mongo):
        org_id = str(ObjectId())
        yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
        mongo.organisations.insert_one(
            {
                "_id": ObjectId(org_id),
                "name": "Ends Now",
                "created_by": "x",
                "created_at": datetime.now(UTC).isoformat(),
                "timezone": "UTC",
                "closes_on": yesterday,
            }
        )
        job = self._run(
            operator_client,
            "organisation.delete",
            {"organisation_id": org_id},
            confirmation="Ends Now",
        ).json()["job"]
        self._due_now(mongo, job["id"])

        assert _run_jobs() == 1

        assert mongo.organisations.find_one({"_id": ObjectId(org_id)}) is None
        assert mongo.operator_jobs.find_one({"_id": ObjectId(job["id"])})["state"] == "done"

    def test_the_purge_trims_the_operator_audit_at_four_years(self, mongo):
        import asyncio

        from pymongo import AsyncMongoClient

        from beats.infrastructure.retention import purge_expired_records

        old = (datetime.now(UTC) - timedelta(days=5 * 365)).isoformat()
        fresh = datetime.now(UTC).isoformat()
        mongo.operator_audit.insert_many(
            [
                {"at": old, "command": "account.suspend", "subject_id": "s1"},
                {"at": fresh, "command": "account.suspend", "subject_id": "s2"},
            ]
        )

        async def go():
            client = AsyncMongoClient(os.environ.get("DB_DSN", "mongodb://localhost:27017"))
            try:
                await purge_expired_records(
                    client[os.environ.get("DB_NAME", "beats_test")], apply=True
                )
            finally:
                await client.close()

        asyncio.run(go())

        remaining = list(mongo.operator_audit.find({}))
        assert [r["subject_id"] for r in remaining] == ["s2"]

    def test_one_queued_erasure_per_account_and_no_unsuspend_around_it(
        self, operator_client, mongo
    ):
        """The window must stay visible and cancellable as one thing: a
        second queued erasure would let a cancel lift the suspension while
        the other ran on schedule, and an unsuspend around a queued erasure
        would leave the account working normally — showing none of the
        warning — and still erased in seven days. job.cancel is the one way
        out, and it lifts the suspension itself."""
        user_id = self._user(mongo, "once@example.test")
        first = self._run(
            operator_client, "account.erase", {"user_id": user_id}, "once@example.test"
        )
        assert first.status_code == 200, first.text

        again = self._run(
            operator_client, "account.erase", {"user_id": user_id}, "once@example.test"
        )
        assert again.status_code == 409
        assert again.json()["code"] == "JOB_ALREADY_QUEUED"

        unsuspend = self._run(operator_client, "account.unsuspend", {"user_id": user_id})
        assert unsuspend.status_code == 409
        assert unsuspend.json()["code"] == "ERASURE_QUEUED"

        job_id = first.json()["job"]["id"]
        assert self._run(operator_client, "job.cancel", {"job_id": job_id}).status_code == 200
        assert mongo.users.find_one({"_id": ObjectId(user_id)}).get("suspended_at") is None

    def test_a_mistyped_subject_is_refused_at_queue_time_not_waived(self, operator_client, mongo):
        """A subject that doesn't resolve must never read as 'no confirmation
        required': the typed confirmation exists precisely for the mistyped
        id."""
        resp = self._run(operator_client, "account.erase", {"user_id": str(ObjectId())})
        assert resp.status_code == 404
        assert resp.json()["code"] == "ACCOUNT_NOT_FOUND"
        assert mongo.operator_jobs.count_documents({}) == 0

    def test_a_failed_queue_side_effect_leaves_no_job_standing(self, operator_client, mongo):
        """If queueing's suspension fails, the job is cancelled and the error
        surfaces: a job with no suspension would wait out an invisible window
        while the operator, who saw an error, believes nothing was queued.
        Driven at the runner with the real context, its suspend replaced by
        the transient failure a Mongo hiccup would be."""
        import asyncio

        from pymongo import AsyncMongoClient

        from beats.operator.context import build_command_context
        from beats.operator.runner import run_command
        from beats.operator.settings import OperatorIdentity

        user_id = self._user(mongo, "half@example.test")

        async def queue_with_failing_suspend() -> bool:
            client = AsyncMongoClient(os.environ.get("DB_DSN", "mongodb://localhost:27017"))
            try:
                db = client[os.environ.get("DB_NAME", "beats_test")]
                ctx = build_command_context(
                    db,
                    OperatorIdentity(sub=OPERATOR_SUB, email="op@example.test", role="operator"),
                )

                async def failing_suspend(*args, **kwargs):
                    raise RuntimeError("transient write failure")

                # ty flags replacing a bound method; a cast keeps the patch
                # explicit without widening the service's own type.
                from typing import cast

                cast("Any", ctx.accounts).suspend = failing_suspend
                try:
                    await run_command(
                        ctx, "account.erase", {"user_id": user_id}, "half@example.test"
                    )
                except RuntimeError:
                    return True
                return False
            finally:
                await client.close()

        assert asyncio.run(queue_with_failing_suspend()) is True
        job = mongo.operator_jobs.find_one({"subject_id": user_id})
        assert job is not None
        assert job["state"] == "cancelled"
