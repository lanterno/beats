"""Release history (docs/backoffice.md § The pages, Releases): merging the
sources, one failing while the others answer, and a web version.json that is
missing. The route is test_operator.py's, over a fake of the port."""

import httpx

from beats.operator.releases import (
    Build,
    LiveReleases,
    ReleasesCache,
    assemble,
    parse_builds,
    parse_version,
)

A = "a" * 40
B = "b" * 40
C = "c" * 40


class TestParsing:
    def test_builds_come_newest_first_and_a_build_with_no_commit_is_left_out(self):
        body = {
            "builds": [
                {
                    "substitutions": {"COMMIT_SHA": A},
                    "status": "SUCCESS",
                    "createTime": "2026-11-13T10:00:00Z",
                },
                {
                    "source": {"repoSource": {"commitSha": B}},
                    "status": "FAILURE",
                    "createTime": "2026-11-14T10:00:00Z",
                },
                {"status": "SUCCESS", "createTime": "2026-11-14T11:00:00Z"},
                {
                    "substitutions": {"COMMIT_SHA": "not-a-sha"},
                    "createTime": "2026-11-14T12:00:00Z",
                },
            ]
        }
        assert [(b.sha, b.status) for b in parse_builds(body)] == [(B, "FAILURE"), (A, "SUCCESS")]

    def test_an_empty_answer_is_no_builds(self):
        assert parse_builds({}) == []

    def test_a_version_file_with_no_sha_is_unknown(self):
        assert parse_version({"sha": A}) == A
        assert parse_version({"sha": "main"}) is None
        assert parse_version("<!doctype html>") is None
        assert parse_version({}) is None


class TestAssemble:
    def test_the_live_build_is_the_one_the_api_was_deployed_with(self):
        builds = [Build(B, "SUCCESS", None, None, None), Build(A, "SUCCESS", None, None, None)]
        report = assemble(
            builds,
            api_commit=A,
            web_commit=C,
            subjects={A: "api: one", C: "ui: two"},
            repository="o/r",
            unavailable=[],
        )
        assert [(r.sha, r.live, r.subject) for r in report.builds] == [
            (B, False, None),
            (A, True, "api: one"),
        ]
        assert report.web_subject == "ui: two"

    def test_an_unknown_api_commit_marks_nothing_live(self):
        report = assemble(
            [Build(A, "SUCCESS", None, None, None)],
            api_commit=None,
            web_commit=None,
            subjects={},
            repository="o/r",
            unavailable=[],
        )
        assert report.builds[0].live is False


class _Source:
    def __init__(self):
        self.fail: set[str] = set()
        self.subject_calls = 0

    async def builds(self):
        if "builds" in self.fail:
            raise httpx.ConnectError("no metadata server")
        return [Build(A, "SUCCESS", None, None, None)]

    async def web_commit(self):
        if "web" in self.fail:
            raise httpx.ConnectError("away")
        return C

    async def subject(self, sha):
        self.subject_calls += 1
        if "subjects" in self.fail:
            raise httpx.ConnectError("rate limited")
        return f"subject of {sha[:1]}"


class TestCache:
    async def test_one_source_failing_leaves_the_others_answering(self):
        source = _Source()
        source.fail = {"builds"}
        report = await ReleasesCache(seconds=0).report(source, api_commit=A, repository="o/r")
        assert report.unavailable == ["builds"]
        assert report.builds == []
        assert report.web_commit == C
        assert report.web_subject == "subject of c"

    async def test_a_failure_after_a_success_keeps_the_last_builds(self):
        source, cache = _Source(), ReleasesCache(seconds=0)
        await cache.report(source, api_commit=A, repository="o/r")
        source.fail = {"builds", "web"}
        report = await cache.report(source, api_commit=A, repository="o/r")
        assert [r.sha for r in report.builds] == [A]
        assert report.web_commit == C
        assert sorted(report.unavailable) == ["builds", "web"]

    async def test_a_subject_is_asked_for_once(self):
        source, cache = _Source(), ReleasesCache(seconds=0)
        await cache.report(source, api_commit=A, repository="o/r")
        calls = source.subject_calls
        await cache.report(source, api_commit=A, repository="o/r")
        assert source.subject_calls == calls


class TestLive:
    async def test_a_missing_version_file_is_unknown_not_a_failure(self):
        def answer(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        source = LiveReleases(
            web_origin="https://web.example.test",
            repository="o/r",
            transport=httpx.MockTransport(answer),
        )
        assert await source.web_commit() is None

    async def test_the_spas_index_served_for_version_json_is_unknown(self):
        def answer(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text="<!doctype html><html></html>")

        source = LiveReleases(
            web_origin="https://web.example.test",
            repository="o/r",
            transport=httpx.MockTransport(answer),
        )
        assert await source.web_commit() is None

    async def test_no_web_origin_is_a_source_that_did_not_answer(self):
        report = await ReleasesCache().report(
            LiveReleases(
                web_origin="",
                repository="o/r",
                transport=httpx.MockTransport(lambda r: httpx.Response(503)),
            ),
            api_commit=None,
            repository="o/r",
        )
        assert "web" in report.unavailable
        assert "builds" in report.unavailable

    async def test_a_subject_is_the_first_line_of_the_message(self):
        def answer(request: httpx.Request) -> httpx.Response:
            assert request.url.path == f"/repos/o/r/commits/{A}"
            return httpx.Response(200, json={"commit": {"message": "api: a thing\n\nbody"}})

        source = LiveReleases(
            web_origin="", repository="o/r", transport=httpx.MockTransport(answer)
        )
        assert await source.subject(A) == "api: a thing"
