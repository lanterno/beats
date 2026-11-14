"""The deploy freeze (docs/backoffice.md § Deploy freeze): the flag's format,
the two commands through the runner, and `decide` in api/scripts/deploy_lock.sh
run for real against a stub `gcloud` — with a flag, without one, with an
expired one, and with one that cannot be read. The stub is only as honest as
its answers; the first real frozen build is the rest of the test."""

import os
import stat
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

import pytest

from beats.operator.deploy_freeze import Freeze, parse, render
from conftest import OPERATOR_ORIGIN as ORIGIN
from conftest import OPERATOR_SUB

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "deploy_lock.sh"
SHA = "a" * 40


class TestFlag:
    def test_render_and_parse_agree(self):
        flag = Freeze(
            until=datetime(2026, 11, 15, 9, 0, tzinfo=UTC),
            reason="incident",
            set_by="op",
            set_at=datetime(2026, 11, 14, 9, 0, tzinfo=UTC),
        )
        assert parse(render(flag)) == flag

    def test_a_reason_cannot_forge_a_key(self):
        flag = Freeze(
            until=datetime(2026, 11, 15, tzinfo=UTC),
            reason="bad\nuntil_epoch=9999999999",
            set_by="op",
            set_at=datetime(2026, 11, 14, tzinfo=UTC),
        )
        text = render(flag)
        keys = [line.split("=", 1)[0] for line in text.splitlines()]
        assert keys.count("until_epoch") == 1, "the reason stays on its own line"
        assert parse(text) == Freeze(flag.until, "bad until_epoch=9999999999", "op", flag.set_at)

    def test_garbage_is_no_freeze(self):
        assert parse("") is None
        assert parse("until_epoch=soon\nset_at=x") is None


class _Memory:
    def __init__(self):
        self.flag: Freeze | None = None

    async def get(self):
        return self.flag

    async def set(self, freeze):
        self.flag = freeze

    async def clear(self):
        self.flag = None


class TestFreezeCommands:
    OWN: ClassVar[dict[str, str]] = {"Origin": ORIGIN}

    @pytest.fixture(autouse=True)
    def _store(self, operator_client, mongo):
        state = operator_client.app.state
        was = getattr(state, "deploy_freeze", None)
        self.store = _Memory()
        state.deploy_freeze = self.store
        yield
        state.deploy_freeze = was
        mongo.operator_audit.delete_many({})

    def _run(self, client, name, args):
        return client.post(f"/api/operator/commands/{name}", json={"args": args}, headers=self.OWN)

    def test_freeze_writes_the_flag_and_the_audit_and_unfreeze_lifts_it(self, operator_client):
        until = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
        done = self._run(operator_client, "deploy.freeze", {"until": until, "reason": "incident"})
        assert done.status_code == 200, done.text
        assert done.json()["subject_kind"] == "deploy"
        assert done.json()["before"] == {"frozen": False}
        assert done.json()["after"]["frozen"] is True
        assert self.store.flag is not None
        assert self.store.flag.set_by == OPERATOR_SUB

        state = operator_client.get("/api/operator/deploy-freeze").json()
        assert state["frozen"] is True
        assert state["reason"] == "incident"

        lifted = self._run(operator_client, "deploy.unfreeze", {})
        assert lifted.status_code == 200
        assert lifted.json()["after"] == {"frozen": False}
        assert self.store.flag is None

    def test_every_freeze_ends(self, operator_client):
        past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        far = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        for args in (
            {"reason": "r"},
            {"until": past, "reason": "r"},
            {"until": far, "reason": "r"},
        ):
            assert self._run(operator_client, "deploy.freeze", args).status_code == 422, args

    def test_an_expired_flag_reads_as_no_freeze(self, operator_client):
        self.store.flag = Freeze(
            until=datetime.now(UTC) - timedelta(minutes=1),
            reason="old",
            set_by="op",
            set_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert operator_client.get("/api/operator/deploy-freeze").json()["frozen"] is False

    def test_with_no_bucket_the_commands_say_so(self, operator_client):
        operator_client.app.state.deploy_freeze = None
        until = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        refused = self._run(operator_client, "deploy.freeze", {"until": until, "reason": "r"})
        assert refused.status_code == 409
        assert refused.json()["code"] == "FREEZE_UNAVAILABLE"
        assert operator_client.get("/api/operator/deploy-freeze").json() == {
            "available": False,
            "frozen": False,
            "until": None,
            "reason": None,
            "set_by": None,
        }


STUB = """#!/usr/bin/env bash
# A stand-in for gcloud: the freeze flag from $STUB_FREEZE, and a live API
# already on this build's commit, so a decide that gets past the freeze
# applies without cloning anything.
case "$1 $2" in
"storage cat")
	case "$STUB_FREEZE" in
	missing) echo "ERROR: One or more URLs matched no objects." >&2; exit 1 ;;
	broken) echo "ERROR: 403 permission denied" >&2; exit 1 ;;
	*) printf '%s' "$STUB_FREEZE" ;;
	esac ;;
"run services") echo "registry/beats-api:$COMMIT_SHA|rev-1|rev-1" ;;
*) echo "unexpected: $*" >&2; exit 2 ;;
esac
"""


class TestDecide:
    def _decide(self, tmp_path: Path, freeze: str) -> tuple[int, str, str]:
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        gcloud = bin_dir / "gcloud"
        gcloud.write_text(STUB)
        gcloud.chmod(gcloud.stat().st_mode | stat.S_IEXEC)
        state = tmp_path / "state"
        env = {
            **os.environ,
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "STUB_FREEZE": freeze,
            "COMMIT_SHA": SHA,
            "CLOUD_RUN_SERVICE": "beats-api",
            "CLOUD_RUN_REGION": "europe-west1",
            "GCP_PROJECT": "p",
            "DEPLOY_REPO_URL": "https://example.test/repo",
            "DEPLOY_STATE_DIR": str(state),
            "DEPLOY_FREEZE_OBJECT": "gs://p-deploy-freeze/freeze",
            "DEPLOY_RETRY_SECONDS": "1",
        }
        result = subprocess.run(
            ["bash", str(SCRIPT), "decide"], env=env, capture_output=True, text=True, timeout=60
        )
        decision = (state / "decision").read_text().strip() if (state / "decision").exists() else ""
        return result.returncode, decision, result.stderr

    @staticmethod
    def _flag(delta: timedelta) -> str:
        until = datetime.now(UTC) + delta
        return render(Freeze(until, "incident", "op", datetime.now(UTC)))

    def test_a_flag_in_force_is_frozen(self, tmp_path):
        code, decision, err = self._decide(tmp_path, self._flag(timedelta(hours=1)))
        assert code == 0, err
        assert decision == "frozen"
        assert "re-run the newest build" in err

    def test_no_flag_decides_as_usual(self, tmp_path):
        code, decision, err = self._decide(tmp_path, "missing")
        assert code == 0, err
        assert decision == "apply"

    def test_an_expired_flag_decides_as_usual(self, tmp_path):
        code, decision, err = self._decide(tmp_path, self._flag(-timedelta(minutes=1)))
        assert code == 0, err
        assert decision == "apply"
        assert "expired" in err

    def test_a_flag_that_cannot_be_read_fails_rather_than_deploying(self, tmp_path):
        code, decision, err = self._decide(tmp_path, "broken")
        assert code != 0
        assert decision == ""
        assert "could not read the deploy freeze flag" in err
