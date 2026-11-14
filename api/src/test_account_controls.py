"""Account controls over HTTP (docs/account-controls.md): suspension on both
credential branches and at the doors, sign-out everywhere, the two last-seen
stamps, and the per-account limits. Split out of test_api.py, whose harness
(and billing helpers, for the report-link door) these classes share; the SSO
door's suspension test stays with TestSSOAPI's harness there.
"""

import logging
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest

from api_helpers import _billed_march, _mint_link, _read_report


class TestAccountSuspensionAPI:
    """Suspension, sign-out everywhere and the day last seen
    (docs/account-controls.md): the middleware on both credential
    branches, the public doors, and the once-a-day stamps. State is written
    the way the account service stores it; enforcement is read through the
    cached lookup, which the per-test fixture clears."""

    def _suspend(self, mongo, user_id: str, kind: str = "abuse", at: datetime | None = None):
        from bson import ObjectId

        mongo.users.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "suspended_at": (at or datetime.now(UTC)).isoformat(),
                    "suspended_kind": kind,
                    "suspended_by": "test",
                    "suspended_reason": "testing",
                }
            },
        )
        # Enforcement is cached; a suspension written by another process is
        # seen within the TTL. The tests don't wait for it.
        from beats.auth import account_access

        account_access.clear()

    def _unsuspend(self, mongo, user_id: str):
        from bson import ObjectId

        from beats.auth import account_access

        mongo.users.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "suspended_at": None,
                    "suspended_kind": None,
                    "suspended_by": None,
                    "suspended_reason": None,
                }
            },
        )
        account_access.clear()

    def _device_headers(self, client, auth_info) -> dict:
        code = client.post("/api/device/pair/code", headers=auth_info["headers"]).json()["code"]
        resp = client.post("/api/device/pair/exchange", json={"code": code})
        assert resp.status_code == 200, resp.text
        return {"Authorization": f"Bearer {resp.json()['device_token']}"}

    @pytest.fixture(autouse=True)
    def _lift(self, mongo, auth_info):
        """Every test leaves the class user acting again — unsuspended, and
        with no sign-out cut, which would refuse the class token whenever a
        second ticked between its minting and the cut."""
        yield
        from bson import ObjectId

        mongo.users.update_one(
            {"_id": ObjectId(auth_info["user_id"])}, {"$unset": {"sessions_valid_after": ""}}
        )
        self._unsuspend(mongo, auth_info["user_id"])

    def test_a_suspended_session_is_refused_everywhere_with_the_address(
        self, client, auth_headers, auth_info, mongo
    ):
        from beats.brand import CONTACT_EMAIL

        self._suspend(mongo, auth_info["user_id"])

        for path in ("/api/projects/", "/api/account/me"):
            resp = client.get(path, headers=auth_headers)
            assert resp.status_code == 403, resp.text
            assert resp.json()["code"] == "ACCOUNT_SUSPENDED"
            assert CONTACT_EMAIL in resp.json()["detail"]
        # Refresh is behind the middleware too: a suspended session cannot
        # keep itself alive, and is not silently signed out either.
        refresh = client.post("/api/account/refresh", headers=auth_headers)
        assert refresh.status_code == 403
        assert refresh.json()["code"] == "ACCOUNT_SUSPENDED"

    def test_an_erasure_suspension_names_the_day_the_window_ends(
        self, client, auth_headers, auth_info, mongo
    ):
        queued = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
        self._suspend(mongo, auth_info["user_id"], kind="erasure", at=queued)

        resp = client.get("/api/projects/", headers=auth_headers)

        assert resp.status_code == 403
        assert "2026-11-11" in resp.json()["detail"]
        assert "deleted" in resp.json()["detail"]

    def test_lifting_a_suspension_lets_the_account_act_again(
        self, client, auth_headers, auth_info, mongo
    ):
        self._suspend(mongo, auth_info["user_id"])
        assert client.get("/api/projects/", headers=auth_headers).status_code == 403

        self._unsuspend(mongo, auth_info["user_id"])
        assert client.get("/api/projects/", headers=auth_headers).status_code == 200

    def test_a_suspended_accounts_device_token_is_refused(self, client, auth_info, mongo):
        """A device token has no expiry, so suspension must hold on the
        device branch: an account whose daemon still writes flow windows has
        not been suspended."""
        device = self._device_headers(client, auth_info)
        assert client.get("/api/timer/status", headers=device).status_code == 200

        self._suspend(mongo, auth_info["user_id"])

        resp = client.get("/api/timer/status", headers=device)
        assert resp.status_code == 403, resp.text
        assert resp.json()["code"] == "ACCOUNT_SUSPENDED"

    def test_a_pairing_code_made_before_the_suspension_mints_nothing(
        self, client, auth_headers, auth_info, mongo
    ):
        """Otherwise the code would mint a device token that starts working
        the moment the suspension lifts."""
        code = client.post("/api/device/pair/code", headers=auth_headers).json()["code"]
        self._suspend(mongo, auth_info["user_id"])

        resp = client.post("/api/device/pair/exchange", json={"code": code})

        assert resp.status_code == 403, resp.text
        assert resp.json()["code"] == "ACCOUNT_SUSPENDED"

    def test_a_suspended_owners_report_link_is_the_one_404(
        self, client, auth_headers, auth_info, mongo
    ):
        """Suspension is for abuse, and a public link serving the account's
        data is the account acting. The same 404 as every other way a token
        fails, per that route's one-404 rule."""
        billed = _billed_march(client, auth_headers)
        link = _mint_link(client, auth_headers, billed["client"]["id"])
        assert _read_report(client, link["token"]).status_code == 200

        self._suspend(mongo, auth_info["user_id"])

        resp = _read_report(client, link["token"])
        assert resp.status_code == 404
        assert resp.json()["code"] == "REPORT_NOT_FOUND"

    def test_sign_out_everywhere_ends_older_sessions_and_only_those(self, client, auth_info, mongo):
        """A session whose sign-in is older than the account's cut is
        refused — through refreshes, which copy auth_time — while a sign-in
        after the cut works. Devices are a different row: the paired daemon
        stays."""
        from bson import ObjectId

        from beats.auth import account_access
        from beats.auth.session import SessionManager
        from beats.settings import settings

        device = self._device_headers(client, auth_info)
        sm = SessionManager(settings.jwt_secret)
        now = int(time.time())
        old = sm.create_session_token(
            auth_info["user_id"], "test@example.com", auth_time=now - 3600
        )
        new = sm.create_session_token(auth_info["user_id"], "test@example.com", auth_time=now + 60)

        mongo.users.update_one(
            {"_id": ObjectId(auth_info["user_id"])},
            {"$set": {"sessions_valid_after": datetime.now(UTC).isoformat()}},
        )
        account_access.clear()

        resp = client.get("/api/projects/", headers={"Authorization": f"Bearer {old}"})
        assert resp.status_code == 401
        assert resp.json()["code"] == "INVALID_TOKEN"
        assert (
            client.get("/api/projects/", headers={"Authorization": f"Bearer {new}"}).status_code
            == 200
        )
        assert client.get("/api/timer/status", headers=device).status_code == 200

    def test_the_day_last_seen_is_stamped_as_a_date(self, client, auth_headers, auth_info, mongo):
        """A UTC date, not a time: a session's times are the account's own
        business, and a day is all "is this account in use?" needs. The
        device's registration gets a datetime of its own."""
        from bson import ObjectId

        assert client.get("/api/projects/", headers=auth_headers).status_code == 200
        doc = mongo.users.find_one({"_id": ObjectId(auth_info["user_id"])})
        assert doc["last_seen_on"] == datetime.now(UTC).date().isoformat()

        device = self._device_headers(client, auth_info)
        assert client.get("/api/timer/status", headers=device).status_code == 200
        reg = mongo.device_registrations.find_one({"user_id": auth_info["user_id"]})
        assert isinstance(reg["last_seen"], datetime)


class TestAccountLimitsAPI:
    """Per-account limits (docs/account-controls.md § Per-account limits): the write
    ceilings off account_limits and the global settings, the coach budget
    override, and webhooks_disabled. Off (None) means uncounted — the whole
    rest of the suite runs that way — so these turn a ceiling on and pin
    what it refuses."""

    def _set_limits(self, mongo, user_id: str, **fields):
        from beats.auth import account_access

        mongo.account_limits.update_one({"user_id": user_id}, {"$set": fields}, upsert=True)
        account_access.clear()

    @pytest.fixture(autouse=True)
    def _clean_limits(self, mongo):
        yield
        mongo.account_limits.delete_many({})

    def _post_beat(self, client, headers, project_id: str):
        start = datetime.now(UTC) - timedelta(hours=2)
        return client.post(
            "/api/beats/",
            json={
                "project_id": project_id,
                "start": start.isoformat(),
                "end": (start + timedelta(minutes=5)).isoformat(),
            },
            headers=headers,
        )

    def _project(self, client, headers) -> str:
        resp = client.post("/api/projects/", json={"name": "Limits"}, headers=headers)
        assert resp.status_code in (200, 201), resp.text
        return resp.json()["id"]

    def test_an_accounts_own_ceiling_caps_its_beat_writes_and_nobody_elses(
        self, client, auth_headers, auth_info, mongo, other_auth_headers
    ):
        project = self._project(client, auth_headers)
        other_project = self._project(client, other_auth_headers)
        self._set_limits(mongo, auth_info["user_id"], writes_per_minute_beats=2)

        assert self._post_beat(client, auth_headers, project).status_code == 201
        assert self._post_beat(client, auth_headers, project).status_code == 201
        refused = self._post_beat(client, auth_headers, project)
        assert refused.status_code == 429, refused.text
        assert refused.json()["code"] == "RATE_LIMITED"

        # The other account has no ceiling and no global default is set, so
        # it is not even counted.
        assert self._post_beat(client, other_auth_headers, other_project).status_code == 201

    def test_the_three_beat_writes_share_one_bucket(self, client, auth_headers, auth_info, mongo):
        """POST, PUT and DELETE spend the same budget: a client cannot get
        three ceilings by mixing verbs."""
        project = self._project(client, auth_headers)
        self._set_limits(mongo, auth_info["user_id"], writes_per_minute_beats=2)

        created = self._post_beat(client, auth_headers, project)
        assert created.status_code == 201
        beat_id = created.json()["id"]
        assert client.delete(f"/api/beats/{beat_id}", headers=auth_headers).status_code == 200
        assert self._post_beat(client, auth_headers, project).status_code == 429

    def test_an_override_wins_over_the_global_default(
        self, client, auth_headers, auth_info, mongo, monkeypatch
    ):
        """The operator can raise one account above the platform default,
        not only cap it."""
        from beats.settings import settings

        monkeypatch.setattr(settings, "writes_per_minute_beats", 1)
        project = self._project(client, auth_headers)
        self._set_limits(mongo, auth_info["user_id"], writes_per_minute_beats=3)

        for _ in range(3):
            assert self._post_beat(client, auth_headers, project).status_code == 201
        assert self._post_beat(client, auth_headers, project).status_code == 429

    def test_the_global_signals_default_counts_once_set(self, client, auth_info, monkeypatch):
        from beats.settings import settings

        monkeypatch.setattr(settings, "writes_per_minute_signals", 1)
        code = client.post("/api/device/pair/code", headers=auth_info["headers"]).json()["code"]
        device = {
            "Authorization": "Bearer "
            + client.post("/api/device/pair/exchange", json={"code": code}).json()["device_token"]
        }
        now = datetime.now(UTC)
        body = {
            "window_start": (now - timedelta(minutes=1)).isoformat(),
            "window_end": now.isoformat(),
            "flow_score": 0.5,
            "cadence_score": 0.5,
            "coherence_score": 0.5,
            "category_fit_score": 0.0,
            "idle_fraction": 0.0,
            "dominant_bundle_id": "com.example",
            "dominant_category": "coding",
        }

        assert (
            client.post("/api/signals/flow-windows", json=body, headers=device).status_code == 201
        )
        refused = client.post("/api/signals/flow-windows", json=body, headers=device)
        assert refused.status_code == 429
        assert refused.json()["code"] == "RATE_LIMITED"

    def test_a_refused_write_is_logged_and_an_auth_door_is_not(
        self, client, auth_headers, auth_info, mongo, caplog
    ):
        """`WRITE_LIMIT_REFUSED` is the only record of a refusal — nothing is
        stored — so the control plane's reading of it (docs/backoffice.md
        § *Abuse*) is exactly as good as this line. The address-keyed doors
        must stay out of it: scanners exhaust them all day, and a metric that
        counted those would say nothing about any account.
        """
        project = self._project(client, auth_headers)
        self._set_limits(mongo, auth_info["user_id"], writes_per_minute_beats=1)

        with caplog.at_level(logging.WARNING, logger="beats.api.errors"):
            assert self._post_beat(client, auth_headers, project).status_code == 201
            assert self._post_beat(client, auth_headers, project).status_code == 429
        refusals = [
            r.getMessage() for r in caplog.records if "WRITE_LIMIT_REFUSED" in r.getMessage()
        ]
        assert len(refusals) == 1, refusals
        assert "route=/api/beats/" in refusals[0]
        assert f"account={auth_info['user_id']}" in refusals[0]

        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="beats.api.errors"):
            for _ in range(11):
                client.get("/api/auth/login/options")
        assert not [r for r in caplog.records if "WRITE_LIMIT_REFUSED" in r.getMessage()]

    def test_the_coach_budget_reads_the_accounts_ceiling_before_the_global(
        self, client, auth_headers, auth_info, mongo
    ):
        """The same figure draws the SPA's usage bar and refuses the chat,
        so GET /api/coach/usage is where the override must show."""
        from beats.settings import settings

        base = client.get("/api/coach/usage", headers=auth_headers)
        assert base.status_code == 200
        assert base.json()["budget_usd"] == settings.coach_monthly_budget_usd

        self._set_limits(mongo, auth_info["user_id"], coach_monthly_budget_usd=0.5)

        capped = client.get("/api/coach/usage", headers=auth_headers)
        assert capped.json()["budget_usd"] == 0.5

    def test_webhooks_disabled_refuses_create_and_silences_dispatch(
        self, client, auth_headers, auth_info, mongo
    ):
        import asyncio

        from beats.api.routers.webhooks import dispatch_webhook_event
        from beats.auth import account_access

        self._set_limits(mongo, auth_info["user_id"], webhooks_disabled=True)

        resp = client.post(
            "/api/webhooks/", json={"url": "https://example.test/hook"}, headers=auth_headers
        )
        assert resp.status_code == 403, resp.text
        assert resp.json()["code"] == "WEBHOOKS_DISABLED"

        # Dispatch never even asks for the account's webhooks: one that was
        # registered before the switch falls silent too. The verdict is
        # pre-warmed in the cache, so no event loop or database is touched.
        class _Repo:
            asked = False

            async def list_by_event(self, event):
                self.asked = True
                return []

            # The rest of WebhookRepository, which dispatch never calls.
            async def list_all(self):
                return []

            async def create(self, webhook):
                raise NotImplementedError

            async def delete(self, webhook_id):
                raise NotImplementedError

            async def update(self, webhook):
                raise NotImplementedError

        account_access.remember(
            "u-disabled", account_access.AccountAccess(exists=True, webhooks_disabled=True)
        )
        account_access.remember("u-enabled", account_access.AccountAccess(exists=True))
        silenced, heard = _Repo(), _Repo()
        asyncio.run(dispatch_webhook_event("timer.start", {}, silenced, "u-disabled"))
        asyncio.run(dispatch_webhook_event("timer.start", {}, heard, "u-enabled"))
        assert not silenced.asked
        assert heard.asked


class TestPlatformControlsAPI:
    """The operator's platform-wide controls as the public API enforces them
    (docs/backoffice.md § Controls): each paused route refuses with 409 and
    its own code, works again once the pause has expired, existing people
    still sign in, and the three ceilings are read in order — the account's
    override, then the control, then the setting."""

    def _control(self, mongo, name: str, *, until=None, value=None):
        from beats import platform_controls

        mongo.platform_controls.update_one(
            {"name": name},
            {"$set": {"name": name, "until": until, "value": value, "reason": "test"}},
            upsert=True,
        )
        platform_controls.clear()

    @pytest.fixture(autouse=True)
    def _clean(self, mongo):
        from beats import platform_controls

        platform_controls.clear()
        yield
        mongo.platform_controls.delete_many({})
        mongo.account_limits.delete_many({})
        platform_controls.clear()

    @staticmethod
    def _soon() -> str:
        return (datetime.now(UTC) + timedelta(hours=1)).isoformat()

    @staticmethod
    def _passed() -> str:
        return (datetime.now(UTC) - timedelta(seconds=1)).isoformat()

    def _import(self, client, headers):
        return client.post(
            "/api/export/import",
            files={"file": ("backup.json", b'{"version": "1.0"}', "application/json")},
            headers=headers,
        )

    def test_imports_refuse_while_paused_and_work_after_expiry(self, client, auth_headers, mongo):
        self._control(mongo, "imports", until=self._soon())
        refused = self._import(client, auth_headers)
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "IMPORTS_PAUSED"
        assert "test" not in refused.json()["detail"], "the operator's reason stays theirs"

        self._control(mongo, "imports", until=self._passed())
        assert self._import(client, auth_headers).status_code != 409

    def test_the_coach_refuses_while_paused(self, client, auth_headers, mongo):
        self._control(mongo, "coach", until=self._soon())
        refused = client.post("/api/coach/memory/rewrite", headers=auth_headers)
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "COACH_PAUSED"

    def test_signups_refuse_while_paused_and_sign_in_still_works(self, client, mongo):
        self._control(mongo, "signups", until=self._soon())
        start = client.post(
            "/api/auth/register/start", json={"email": "new@example.test", "display_name": "N"}
        )
        assert start.status_code == 409, start.text
        assert start.json()["code"] == "SIGNUPS_PAUSED"
        assert mongo.users.count_documents({"email": "new@example.test"}) == 0, "no row left"
        verify = client.post("/api/auth/register/verify", json={"credential": {}})
        assert verify.status_code == 409
        # Never a sign-in.
        assert client.get("/api/auth/login/options").status_code == 200

    def test_slowed_signups_refuse_once_the_hour_holds_the_ceiling(self, client, mongo):
        from datetime import datetime as dt

        self._control(mongo, "signups", until=self._soon(), value=2)
        recent = dt.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        mongo.users.insert_many(
            [{"email": f"wave{i}@example.test", "created_at": recent} for i in range(2)]
        )
        start = client.post(
            "/api/auth/register/start", json={"email": "late@example.test", "display_name": "L"}
        )
        assert start.status_code == 409
        assert start.json()["code"] == "SIGNUPS_PAUSED"

        from beats import platform_controls

        self._control(mongo, "signups", until=self._soon(), value=5)
        platform_controls._signups_counted_at = 0.0
        assert (
            client.post(
                "/api/auth/register/start", json={"email": "room@example.test", "display_name": "R"}
            ).status_code
            == 200
        )

    def _post_beat(self, client, headers, project_id: str):
        start = datetime.now(UTC) - timedelta(hours=2)
        return client.post(
            "/api/beats/",
            json={
                "project_id": project_id,
                "start": start.isoformat(),
                "end": (start + timedelta(minutes=5)).isoformat(),
            },
            headers=headers,
        )

    def test_the_control_caps_writes_beneath_the_accounts_own_override(
        self, client, auth_headers, auth_info, mongo
    ):
        from beats.auth import account_access

        project = client.post("/api/projects/", json={"name": "Ctl"}, headers=auth_headers).json()[
            "id"
        ]
        self._control(mongo, "writes_per_minute_beats", value=1)
        assert self._post_beat(client, auth_headers, project).status_code == 201
        assert self._post_beat(client, auth_headers, project).status_code == 429

        # The account's own override wins over the control.
        mongo.account_limits.update_one(
            {"user_id": auth_info["user_id"]},
            {"$set": {"writes_per_minute_beats": 10}},
            upsert=True,
        )
        account_access.clear()
        assert self._post_beat(client, auth_headers, project).status_code == 201

    def test_paused_webhooks_drop_with_a_line_per_event(self, auth_info, caplog):
        """No outbox holds a delivery, so a pause drops it — and logs it, so
        the loss can be counted. Pre-warmed like the per-account switch's
        test, so no event loop reaches the database."""
        import asyncio
        import time

        from beats import platform_controls
        from beats.api.routers.webhooks import dispatch_webhook_event
        from beats.auth import account_access

        class _Repo:
            asked = False

            async def list_by_event(self, event):
                self.asked = True
                return []

        platform_controls._state = platform_controls.controls_from_docs(
            [{"name": "webhooks", "until": self._soon()}], datetime.now(UTC)
        )
        platform_controls._expires_at = time.monotonic() + 60
        account_access.remember("u-open", account_access.AccountAccess(exists=True))
        repo = _Repo()
        with caplog.at_level(logging.WARNING, logger="beats.api.routers.webhooks"):
            asyncio.run(dispatch_webhook_event("timer.start", {}, repo, "u-open"))  # ty: ignore[invalid-argument-type]
        assert not repo.asked
        assert any("WEBHOOKS_PAUSED_DROPPED event=timer.start" in r.message for r in caplog.records)


class TestSignupNetworks:
    """The sign-up network signal over HTTP (docs/backoffice.md § The pages,
    Trust and safety): a start from an address is one counter row holding a
    key and never the address; abandoned starts are not completions; the
    largest group shows only at the minimum size; a network-scoped
    slow-down refuses that network and nobody else, and expires with the
    day's key."""

    VISITOR = "203.0.113.7"

    @pytest.fixture(autouse=True)
    def _clean(self, mongo):
        from beats import platform_controls

        platform_controls.clear()
        yield
        mongo.signup_network_counts.delete_many({})
        mongo.platform_controls.delete_many({})
        mongo.users.delete_many({"email": {"$regex": "^wave"}})
        platform_controls.clear()

    @staticmethod
    @contextmanager
    def _from(client, address: str):
        """The class's TestClient, seen as arriving from `address`. The same
        client, not a second one: a fresh TestClient runs on an event loop of
        its own, which the session's Mongo client refuses."""
        transport = client._transport
        was = transport.client
        transport.client = (address, 443)
        try:
            yield client
        finally:
            transport.client = was

    @staticmethod
    def _key(address: str) -> str:
        from beats.auth.signup_networks import key_for

        key = key_for(address)
        assert key is not None
        return key

    def _start(self, client, email: str):
        return client.post("/api/auth/register/start", json={"email": email, "display_name": "W"})

    def test_a_start_is_one_counter_row_with_a_key_and_no_address(self, client, mongo):
        with self._from(client, self.VISITOR) as visitor:
            assert self._start(visitor, "wave-a@example.test").status_code == 200
        with self._from(client, "203.0.113.9") as neighbour:
            assert self._start(neighbour, "wave-b@example.test").status_code == 200
        rows = list(mongo.signup_network_counts.find({}))
        assert len(rows) == 1, "two addresses in one /24 are one network"
        row = rows[0]
        assert row["key"] == self._key(self.VISITOR)
        assert row["started"] == 2
        assert row.get("completed", 0) == 0, "an abandoned start is not a completion"
        assert "203.0.113" not in str(row)
        assert row["expires_at"] is not None

    def test_a_visitor_with_no_address_is_not_counted(self, client, mongo):
        # The default test client has a name for a host, not an address.
        assert self._start(client, "wave-c@example.test").status_code == 200
        assert mongo.signup_network_counts.count_documents({}) == 0

    def test_the_largest_group_shows_at_the_minimum_and_not_below(self, operator_client, mongo):
        from datetime import datetime as dt

        from beats.operator.reads import SIGNUP_NETWORK_MIN_GROUP
        from beats.platform_controls import hour_key

        key = self._key(self.VISITOR)
        mongo.signup_network_counts.insert_one(
            {
                "hour": hour_key(dt.now(UTC)),
                "key": key,
                "started": 9,
                "completed": SIGNUP_NETWORK_MIN_GROUP - 1,
                "expires_at": dt.now(UTC) + timedelta(hours=1),
            }
        )
        wave = operator_client.get("/api/operator/abuse").json()["signup_wave"]
        assert wave["largest_group"] is None
        assert wave["largest_key"] is None
        assert wave["groups"] == 1

        mongo.signup_network_counts.update_one({"key": key}, {"$inc": {"completed": 1}})
        wave = operator_client.get("/api/operator/abuse").json()["signup_wave"]
        assert wave["largest_group"] == SIGNUP_NETWORK_MIN_GROUP
        assert wave["largest_key"] == key
        assert self.VISITOR not in str(wave)
        assert "203.0.113" not in str(wave)

    def test_a_slowed_network_is_refused_and_nobody_else(self, client, mongo):
        from beats import platform_controls

        key = self._key(self.VISITOR)
        until = (datetime.now(UTC) + timedelta(minutes=30)).isoformat()
        mongo.platform_controls.insert_one(
            {"name": "signups", "until": until, "value": 1, "network": key, "reason": "wave"}
        )
        platform_controls.clear()

        with self._from(client, self.VISITOR) as same:
            assert self._start(same, "wave-d@example.test").status_code == 200
            refused = self._start(same, "wave-e@example.test")
            assert refused.status_code == 409, refused.text
            assert refused.json()["code"] == "SIGNUPS_PAUSED"
            # Never a sign-in.
            assert same.get("/api/auth/login/options").status_code == 200
        with self._from(client, "198.51.100.4") as other:
            assert self._start(other, "wave-f@example.test").status_code == 200
