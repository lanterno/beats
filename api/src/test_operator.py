"""The operator deployment's contract (docs/backoffice.md): the isolation
pins, the auth and Origin lines, the wall, and the IAP verifier. The commands
and the job queue are test_operator_commands.py; the operator env and the
`operator_client` fixture are conftest.py's, set before any module import.

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
from typing import ClassVar

import httpx
import jwt
import jwt.algorithms
import pytest
from bson import ObjectId

from beats.operator.reads import (
    ABSENCE_REQUEST_ATTENTION_DAYS,
    ACCOUNT_COACH_SPEND_DAYS,
    SUPERSEDED_ATTENTION_DAYS,
    queue_due,
)
from conftest import OPERATOR_ORIGIN as ORIGIN
from conftest import OPERATOR_SUB

SENTINEL = "walltest-sentinel-7f3a9"
# A number no count or size in a small test database can coincide with.
RATE_SENTINEL = 86423911
BIOMETRIC_SENTINEL = 77311733
# A session planted years before the run, so no account's own dates match.
OLD_DAY = "1999-04-12"


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
            ("GET", "/api/operator/queue", None),
            ("GET", "/api/operator/controls", None),
            ("GET", "/api/operator/access", None),
            ("GET", "/api/operator/erasure-requests", None),
            ("POST", "/api/operator/accounts/lookup", {"email": "wall@example.test"}),
            ("GET", f"/api/operator/accounts/{planted['user_id']}", None),
            ("GET", f"/api/operator/accounts/{planted['user_id']}/coach", None),
            ("GET", f"/api/operator/accounts/{planted['user_id']}/audit", None),
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

    def test_a_visitors_address_is_in_no_response_and_no_document(
        self, operator_client, planted, mongo, test_client
    ):
        """The sign-up network signal keeps a counter per hashed network and
        nothing else: the address, whole or cut to its /24, reaches no
        operator page and no stored row."""
        # The public API's client, seen as arriving from an address: the
        # same client, since a fresh TestClient runs on a loop of its own.
        transport = test_client._transport
        was = transport.client
        transport.client = ("203.0.113.77", 443)
        try:
            started = test_client.post(
                "/api/auth/register/start",
                json={"email": "wall-visitor@example.test", "display_name": "V"},
            )
        finally:
            transport.client = was
        assert started.status_code == 200, started.text
        try:
            for path, body in self._every_page(operator_client, planted):
                assert "203.0.113" not in body, f"an address leaked on {path}"
            for row in mongo.signup_network_counts.find({}):
                assert "203.0.113" not in str(row)
        finally:
            mongo.signup_network_counts.delete_many({})
            mongo.users.delete_many({"email": "wall-visitor@example.test"})

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


class TestOneAccountsReads:
    """The two reads behind the account page (roadmaps/backoffice.md, stage
    1): what the back office has done to this account, and where its coach
    money went. Both answer about one account and must not widen into a way
    to read the platform."""

    OWN: ClassVar[dict[str, str]] = {"Origin": ORIGIN}

    @pytest.fixture(autouse=True)
    def _clean(self, mongo):
        yield
        mongo.operator_audit.delete_many({})
        mongo.llm_usage.delete_many({})

    def _audit(self, mongo, subject_id: str, command: str, at: datetime):
        mongo.operator_audit.insert_one(
            {
                "at": at.isoformat(),
                "command": command,
                "operator_sub": "test-operator",
                "operator_email": "op@example.test",
                "subject_kind": "account",
                "subject_id": subject_id,
                "before": {},
                "after": {},
            }
        )

    def test_the_audit_answers_one_subject_newest_first(self, operator_client, mongo):
        now = datetime.now(UTC)
        mine, theirs = str(ObjectId()), str(ObjectId())
        self._audit(mongo, mine, "account.suspend", now - timedelta(days=2))
        self._audit(mongo, mine, "account.unsuspend", now - timedelta(hours=1))
        self._audit(mongo, theirs, "device.revoke", now)

        rows = operator_client.get(f"/api/operator/accounts/{mine}/audit").json()
        assert [r["command"] for r in rows] == ["account.unsuspend", "account.suspend"]
        assert {r["subject_id"] for r in rows} == {mine}

    def test_the_audit_matches_a_whole_subject_and_not_a_prefix(self, operator_client, mongo):
        """A prefix match would turn the account page into a way to sweep
        the audit for ids nobody typed."""
        subject = str(ObjectId())
        self._audit(mongo, subject, "account.suspend", datetime.now(UTC))
        assert operator_client.get(f"/api/operator/accounts/{subject[:12]}/audit").json() == []

    def test_an_account_nothing_was_done_to_reads_empty(self, operator_client, mongo):
        self._audit(mongo, str(ObjectId()), "account.suspend", datetime.now(UTC))
        assert operator_client.get(f"/api/operator/accounts/{ObjectId()}/audit").json() == []

    def _usage(self, mongo, user_id: str, ts: datetime, cost: float):
        mongo.llm_usage.insert_one({"user_id": user_id, "ts": ts, "cost_usd": cost})

    @staticmethod
    def _midday() -> datetime:
        """Noon UTC today, to hang the calls off.

        Two calls an hour either side of `now` are the same day only if the
        suite is not running near midnight; grouping is by UTC day, so the
        fixture has to be anchored inside one rather than measured back from
        the clock.
        """
        return datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)

    def test_coach_spend_is_summed_a_day_oldest_first(self, operator_client, mongo):
        midday = self._midday()
        mine = str(ObjectId())
        self._usage(mongo, mine, midday - timedelta(days=2), 1.5)
        self._usage(mongo, mine, midday - timedelta(days=2, hours=1), 0.25)
        self._usage(mongo, mine, midday, 4.0)

        rows = operator_client.get(f"/api/operator/accounts/{mine}/coach").json()
        assert [r["value"] for r in rows] == [1.75, 4.0]
        assert rows[0]["day"] < rows[1]["day"]

    def test_coach_spend_is_one_accounts_only(self, operator_client, mongo):
        midday = self._midday()
        mine, theirs = str(ObjectId()), str(ObjectId())
        self._usage(mongo, mine, midday, 2.0)
        self._usage(mongo, theirs, midday, 99.0)
        rows = operator_client.get(f"/api/operator/accounts/{mine}/coach").json()
        assert [r["value"] for r in rows] == [2.0]

    def test_coach_spend_stops_at_the_window(self, operator_client, mongo):
        """Older calls are the platform's history, on Capacity. This read is
        the shape of a month that is running away."""
        midday = self._midday()
        mine = str(ObjectId())
        self._usage(mongo, mine, midday - timedelta(days=ACCOUNT_COACH_SPEND_DAYS + 1), 50.0)
        self._usage(mongo, mine, midday, 1.0)
        rows = operator_client.get(f"/api/operator/accounts/{mine}/coach").json()
        assert [r["value"] for r in rows] == [1.0]

    def test_an_id_that_is_not_an_id_reads_empty_rather_than_erroring(self, operator_client, mongo):
        """A mistyped id reaches these the same way it reaches the account
        itself, and neither should answer 500."""
        assert operator_client.get("/api/operator/accounts/not-an-id/coach").json() == []
        assert operator_client.get("/api/operator/accounts/not-an-id/audit").json() == []


class TestQueueDue:
    """The queue's due dates, at the boundaries Attention counts by."""

    NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)

    def test_a_superseded_approval_is_due_when_attention_starts_counting_it(self):
        since = self.NOW - timedelta(days=SUPERSEDED_ATTENTION_DAYS)
        assert queue_due("approvals_superseded", since, self.NOW) == self.NOW
        later = since + timedelta(seconds=1)
        assert queue_due("approvals_superseded", later, self.NOW) > self.NOW

    def test_an_absence_request_is_due_after_its_own_window(self):
        since = self.NOW - timedelta(days=ABSENCE_REQUEST_ATTENTION_DAYS)
        assert queue_due("absence_requests_pending", since, self.NOW) == self.NOW

    def test_a_queued_job_is_due_when_its_window_ends(self):
        run_after = self.NOW + timedelta(days=7)
        assert queue_due("job_queued", run_after, self.NOW) == run_after

    def test_a_condition_with_no_date_is_due_now(self):
        assert queue_due("organisation_without_owner", None, self.NOW) == self.NOW
        assert queue_due("approvals_superseded", None, self.NOW) == self.NOW


class TestQueueRead:
    """The rows behind the Attention counts, over HTTP."""

    @pytest.fixture(autouse=True)
    def _clean(self, mongo):
        yield
        for name in ("operator_jobs", "org_timesheets", "org_absence_requests", "organisations"):
            mongo[name].delete_many({})

    def test_rows_are_soonest_due_first_and_grouped_per_organisation(self, operator_client, mongo):
        now = datetime.now(UTC)
        org = str(ObjectId())
        mongo.org_absence_requests.insert_many(
            [
                {
                    "organisation_id": org,
                    "user_id": SENTINEL,
                    "status": "pending",
                    "requested_at": (now - timedelta(days=d)).isoformat(),
                }
                for d in (20, 2)
            ]
        )
        mongo.org_absence_requests.insert_one(
            {"organisation_id": org, "status": "approved", "requested_at": now.isoformat()}
        )
        failed = mongo.operator_jobs.insert_one(
            {"state": "failed", "finished_at": now.isoformat(), "command": "x"}
        ).inserted_id
        mongo.operator_jobs.insert_one(
            {"state": "done", "finished_at": now.isoformat(), "command": "x"}
        )

        rows = operator_client.get("/api/operator/queue").json()
        assert [(r["kind"], r["subject_id"], r["count"]) for r in rows] == [
            ("absence_requests_pending", org, 2),
            ("job_failed", str(failed), 1),
        ]
        assert SENTINEL not in str(rows), "no member is named"

    def test_an_empty_platform_has_an_empty_queue(self, operator_client):
        assert operator_client.get("/api/operator/queue").json() == []


class TestOperatorHealthRoute:
    """GET /api/operator/health over a fake of the port: the three states,
    and that it is the operator's alone like every other read."""

    @pytest.fixture(autouse=True)
    def _fake(self, operator_client):
        from beats.operator.health import HealthCache, HealthFigures

        class _Fake:
            fail = False

            async def read(self):
                if self.fail:
                    raise RuntimeError("away")
                return HealthFigures(
                    availability=0.999, error_share=0.0, p95_latency_ms=300.0, instances=1
                )

        state = operator_client.app.state
        was = (state.health_source, state.health_cache)
        self.fake = _Fake()
        state.health_source, state.health_cache = self.fake, HealthCache(seconds=0)
        yield
        state.health_source, state.health_cache = was

    def test_live_figures_with_the_ceiling_and_the_target(self, operator_client):
        body = operator_client.get("/api/operator/health").json()
        assert body["state"] == "live"
        assert body["figures"]["availability"] == 0.999
        assert body["availability_target"] == 0.995

    def test_a_failure_after_a_read_is_stale(self, operator_client):
        operator_client.get("/api/operator/health")
        self.fake.fail = True
        body = operator_client.get("/api/operator/health").json()
        assert body["state"] == "stale"
        assert body["figures"] is not None

    def test_never_read_is_unavailable(self, operator_client):
        self.fake.fail = True
        body = operator_client.get("/api/operator/health").json()
        assert body == {**body, "state": "unavailable", "figures": None}
