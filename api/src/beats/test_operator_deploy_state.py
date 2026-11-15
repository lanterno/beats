"""The API's deploy state (docs/backoffice.md § The pages, Today): which
revision serves and its commit when the newest failed or is still starting,
and the cache that keeps the last answer. The route is test_operator.py's,
over a fake of the port."""

import asyncio
from typing import Any

from beats.operator.deploy_state import (
    DeployStateCache,
    commit_of_tags,
    image_commit,
    read_deploy_state,
)

A = "a" * 40
B = "b" * 40
REGISTRY = "europe-west1-docker.pkg.dev/p-1/docker/beats-api"
DIGEST = f"{REGISTRY}@sha256:{'d' * 64}"


def service(
    *, newest: str, serving: str | None, ready: str, image: str, message: str | None = None
) -> dict[str, Any]:
    """Cloud Run's v1 service, as much of it as the state is made of."""
    return {
        "spec": {"template": {"spec": {"containers": [{"image": image}]}}},
        "status": {
            "latestCreatedRevisionName": newest,
            **({"latestReadyRevisionName": serving} if serving else {}),
            "conditions": [
                {
                    "type": "Ready",
                    "status": ready,
                    "lastTransitionTime": "2026-11-15T06:02:56Z",
                    **({"message": message} if message else {}),
                },
                {"type": "ConfigurationsReady", "status": ready},
            ],
        },
    }


class _CloudRun:
    def __init__(self, body: dict[str, Any], *, tags: list[str] | None = None):
        self.body = body
        self.tag_list = tags if tags is not None else [B, "latest"]
        self.revisions_read: list[str] = []
        self.fail = False

    async def service(self) -> dict[str, Any]:
        if self.fail:
            raise RuntimeError("Cloud Run is away")
        return self.body

    async def revision(self, name: str) -> dict[str, Any]:
        self.revisions_read.append(name)
        return {
            "metadata": {"creationTimestamp": "2026-11-14T09:00:00Z"},
            "status": {"imageDigest": DIGEST},
        }

    async def tags(self, digest_ref: str) -> list[str]:
        assert digest_ref == DIGEST
        return self.tag_list


class _SlowCloudRun(_CloudRun):
    """A service read that waits to be released, so a second caller arrives
    while it is in flight."""

    def __init__(self, body: dict[str, Any]):
        super().__init__(body)
        self.released = asyncio.Event()
        self.reads = 0

    async def service(self) -> dict[str, Any]:
        self.reads += 1
        await self.released.wait()
        return await super().service()


class TestReadingTheState:
    async def test_the_newest_revision_serving_is_read_off_the_service_alone(self):
        source = _CloudRun(service(newest="r-2", serving="r-2", ready="True", image=f"x:{A}"))
        state = await read_deploy_state(source)
        assert (state.newest, state.serving_revision, state.serving_commit) == ("serving", "r-2", A)
        assert state.problem is None
        assert source.revisions_read == []

    async def test_a_newest_revision_that_failed_leaves_the_older_one_and_its_commit_live(self):
        """The case the console link stood in for: the spec names the new
        commit, but traffic stays on the revision before, whose commit the
        registry's tag on its digest names, never the spec's."""
        source = _CloudRun(
            service(
                newest="r-3",
                serving="r-2",
                ready="False",
                image=f"x:{A}",
                message="Revision 'r-3' is not ready and cannot serve traffic.",
            )
        )
        state = await read_deploy_state(source)
        assert state.newest == "failed"
        assert (state.newest_revision, state.newest_commit) == ("r-3", A)
        assert (state.serving_revision, state.serving_commit) == ("r-2", B)
        assert state.problem == "Revision 'r-3' is not ready and cannot serve traffic."
        assert source.revisions_read == ["r-2"]

    async def test_a_newest_revision_still_starting_is_neither_serving_nor_failed(self):
        source = _CloudRun(service(newest="r-3", serving="r-2", ready="Unknown", image=f"x:{A}"))
        state = await read_deploy_state(source)
        assert (state.newest, state.serving_commit) == ("starting", B)

    async def test_no_revision_ever_ready_serves_nothing(self):
        source = _CloudRun(service(newest="r-1", serving=None, ready="False", image=f"x:{A}"))
        state = await read_deploy_state(source)
        assert state.newest == "failed"
        assert (state.serving_revision, state.serving_commit) == (None, None)
        assert source.revisions_read == []

    async def test_a_digest_carrying_two_commits_is_an_unknown_commit(self):
        source = _CloudRun(
            service(newest="r-3", serving="r-2", ready="False", image=f"x:{A}"), tags=[A, B]
        )
        assert (await read_deploy_state(source)).serving_commit is None


class TestCommits:
    def test_an_image_names_a_commit_only_by_a_full_sha_tag(self):
        assert image_commit(f"{REGISTRY}:{A}") == A
        assert image_commit(f"{REGISTRY}:latest") is None
        assert image_commit(DIGEST) is None
        # A registry's port is not a tag.
        assert image_commit("localhost:5000/beats-api") is None

    def test_a_digest_names_its_commit_only_when_it_carries_exactly_one(self):
        assert commit_of_tags([A, "latest"]) == A
        assert commit_of_tags(["latest"]) is None
        assert commit_of_tags([A, B]) is None


class TestCache:
    async def test_a_failure_after_an_answer_keeps_it_marked_stale(self):
        source = _CloudRun(service(newest="r-2", serving="r-2", ready="True", image=f"x:{A}"))
        cache = DeployStateCache(seconds=0)
        assert (await cache.report(source)).state == "live"
        source.fail = True
        report = await cache.report(source)
        assert report.state == "stale"
        assert report.deploy is not None
        assert report.deploy.serving_commit == A

    async def test_a_caller_during_the_first_read_waits_for_it(self):
        """Today asks /deploy-state and /releases at once; on a cold cache the
        second answered "unavailable" while the first read was in flight, and
        the page said the API's commit was unknown."""
        source = _SlowCloudRun(service(newest="r-2", serving="r-2", ready="True", image=f"x:{A}"))
        cache = DeployStateCache()
        first = asyncio.create_task(cache.report(source))
        second = asyncio.create_task(cache.report(source))
        await asyncio.sleep(0)
        source.released.set()
        reports = await asyncio.gather(first, second)
        assert [r.state for r in reports] == ["live", "live"]
        assert source.reads == 1

    async def test_no_answer_yet_and_no_source_are_both_unavailable(self):
        source = _CloudRun({})
        source.fail = True
        assert (await DeployStateCache(seconds=0).report(source)).state == "unavailable"
        assert (await DeployStateCache().report(None)).state == "unavailable"
