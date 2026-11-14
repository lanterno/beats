"""Telling customers what is happening (docs/status-page.md): the file's
shape, a publish that leaves the old file intact when the write fails, the
generation conflict, the commands' audit rows, and the read-back."""

from datetime import UTC, datetime
from typing import ClassVar

import httpx
import pytest

from beats.operator.status_page import (
    POSTS_KEPT,
    GcsStatusStore,
    MemoryStatusStore,
    StatusConflict,
    next_doc,
    parse,
    publish,
)
from conftest import OPERATOR_ORIGIN as ORIGIN

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


class TestDocument:
    def test_a_post_goes_on_top_and_only_the_last_are_kept(self):
        doc = None
        for i in range(POSTS_KEPT + 3):
            doc = next_doc(doc, state="degraded", message=f"post {i}", affected=["api"], now=NOW)
        assert doc is not None
        assert len(doc.posts) == POSTS_KEPT
        assert doc.posts[0].message == f"post {POSTS_KEPT + 2}"
        assert doc.state == "degraded"

    def test_render_and_parse_agree_and_garbage_is_none(self):
        doc = next_doc(
            None, state="outage", message="Sign-in is down.", affected=["sign-in"], now=NOW
        )
        assert parse(doc.to_json()) == doc
        assert parse("<!doctype html>") is None
        assert parse('{"state": "outage"}') is None


class _FailingWrite(MemoryStatusStore):
    async def write(self, doc, *, if_generation_match):
        raise httpx.ConnectError("bucket away")


class TestPublish:
    async def test_a_failed_write_leaves_the_old_file_intact(self):
        store = _FailingWrite()
        await MemoryStatusStore.write(
            store,
            next_doc(None, state="degraded", message="slow", affected=[], now=NOW),
            if_generation_match=0,
        )
        before = store.doc
        with pytest.raises(httpx.ConnectError):
            await publish(store, state="outage", message="down", affected=["api"], now=NOW)
        assert store.doc == before

    async def test_two_writers_cannot_silently_lose_one(self):
        store = MemoryStatusStore()
        first, generation = await store.read()
        assert first is None
        await publish(store, state="degraded", message="A", affected=[], now=NOW)
        # A second writer that read before the first published must not win.
        with pytest.raises(StatusConflict):
            await store.write(
                next_doc(None, state="outage", message="B", affected=[], now=NOW),
                if_generation_match=generation,
            )
        assert store.doc is not None
        assert store.doc.message == "A"


class TestGcs:
    async def test_a_412_is_the_conflict_and_the_write_sets_the_cache_header(self):
        seen: dict[str, str] = {}

        def answer(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "token" in url:
                return httpx.Response(200, json={"access_token": "t"})
            if request.method == "POST":
                seen["params"] = str(request.url.params)
                seen["body"] = request.content.decode()
                return httpx.Response(412)
            return httpx.Response(404)

        store = GcsStatusStore("b", transport=httpx.MockTransport(answer))
        doc, generation = await store.read()
        assert (doc, generation) == (None, 0)
        with pytest.raises(StatusConflict):
            await store.write(
                next_doc(None, state="degraded", message="m", affected=[], now=NOW),
                if_generation_match=0,
            )
        assert "ifGenerationMatch=0" in seen["params"]
        assert '"cacheControl": "public, max-age=30"' in seen["body"]


class TestStatusCommands:
    OWN: ClassVar[dict[str, str]] = {"Origin": ORIGIN}

    @pytest.fixture(autouse=True)
    def _store(self, operator_client, mongo):
        state = operator_client.app.state
        was = getattr(state, "status_store", None)
        self.store = MemoryStatusStore()
        state.status_store = self.store
        yield
        state.status_store = was
        mongo.operator_audit.delete_many({})

    def _run(self, client, name, args):
        return client.post(f"/api/operator/commands/{name}", json={"args": args}, headers=self.OWN)

    def test_publish_writes_the_file_and_the_audit_and_clear_posts_the_recovery(
        self, operator_client
    ):
        done = self._run(
            operator_client,
            "status.publish",
            {"state": "degraded", "message": "The coach is slow.", "affected": ["coach"]},
        )
        assert done.status_code == 200, done.text
        assert done.json()["subject_kind"] == "status"
        assert done.json()["before"]["published"] is False
        assert done.json()["after"]["state"] == "degraded"
        assert self.store.doc is not None
        assert self.store.doc.affected == ["coach"]

        read = operator_client.get("/api/operator/status").json()
        assert read == {**read, "available": True, "state": "degraded", "published": True}

        cleared = self._run(operator_client, "status.clear", {})
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["after"]["state"] == "operational"
        assert [p.state for p in self.store.doc.posts] == ["operational", "degraded"]

    def test_the_states_and_parts_are_fixed_lists_and_the_message_is_bounded(self, operator_client):
        for args in (
            {"state": "on fire", "message": "m"},
            {"state": "outage", "message": ""},
            {"state": "outage", "message": "x" * 281},
            {"state": "outage", "message": "m", "affected": ["the database host"]},
        ):
            assert self._run(operator_client, "status.publish", args).status_code == 422, args

    def test_with_no_bucket_the_commands_say_so(self, operator_client):
        operator_client.app.state.status_store = None
        refused = self._run(operator_client, "status.publish", {"state": "outage", "message": "m"})
        assert refused.status_code == 409
        assert refused.json()["code"] == "STATUS_UNAVAILABLE"
        assert operator_client.get("/api/operator/status").json()["available"] is False
