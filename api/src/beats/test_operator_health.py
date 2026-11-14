"""Live health (docs/backoffice.md § The pages, Today): parsing Monitoring's
answers at their awkward shapes, and the cache's three states. The route is
test_operator.py's, over a fake of the port — never a stubbed Google in a
live page."""

import httpx
import pytest

from beats.operator.health import (
    GoogleMonitoring,
    HealthCache,
    HealthFigures,
    by_label,
    latest_value,
    share,
    total_value,
)


def _point(value, end="2026-11-14T10:00:00Z", kind="doubleValue"):
    return {"interval": {"endTime": end}, "value": {kind: value}}


class TestParsing:
    def test_an_empty_answer_is_no_data_not_zero(self):
        assert latest_value({}) is None
        assert latest_value({"timeSeries": []}) is None
        assert total_value({"timeSeries": [{"points": []}]}) is None

    def test_a_single_point(self):
        assert latest_value({"timeSeries": [{"points": [_point(0.98)]}]}) == 0.98

    def test_the_newest_point_wins_across_a_gap_and_two_series(self):
        body = {
            "timeSeries": [
                {"points": [_point(3, "2026-11-14T10:05:00Z"), _point(9, "2026-11-14T09:00:00Z")]},
                {"points": [_point(4, "2026-11-14T10:10:00Z")]},
            ]
        }
        assert latest_value(body) == 4

    def test_counts_arrive_as_strings_and_add_up(self):
        body = {
            "timeSeries": [
                {"points": [_point("12", kind="int64Value"), _point("3", kind="int64Value")]}
            ]
        }
        assert total_value(body) == 15

    def test_a_share_tells_no_errors_from_no_data(self):
        assert share(None, 200) == 0.0
        assert share(4, 200) == 0.02
        assert share(4, None) is None
        assert share(0, 0) is None

    def test_by_label_sums_per_route_largest_first(self):
        body = {
            "timeSeries": [
                {
                    "metric": {"labels": {"route": "/api/beats/"}},
                    "points": [_point("2", kind="int64Value")],
                },
                {
                    "metric": {"labels": {"route": "/api/signals/"}},
                    "points": [_point("7", kind="int64Value")],
                },
                {"metric": {"labels": {}}, "points": [_point("100", kind="int64Value")]},
            ]
        }
        assert [(r.route, r.value) for r in by_label(body, "route")] == [
            ("/api/signals/", 7),
            ("/api/beats/", 2),
        ]


FIGURES = HealthFigures(availability=0.999, error_share=0.01, p95_latency_ms=420.0, instances=1)


class _Source:
    def __init__(self):
        self.fail = False
        self.reads = 0

    async def read(self):
        self.reads += 1
        if self.fail:
            raise httpx.ConnectError("google is away")
        return FIGURES


class TestCache:
    async def test_never_read_and_failing_is_unavailable(self):
        source = _Source()
        source.fail = True
        report = await HealthCache().report(source, 2)
        assert report.state == "unavailable"
        assert report.figures is None

    async def test_a_failure_after_a_success_answers_the_last_figures_as_stale(self):
        source, cache = _Source(), HealthCache(seconds=0)
        assert (await cache.report(source, 2)).state == "live"
        source.fail = True
        stale = await cache.report(source, 2)
        assert stale.state == "stale"
        assert stale.figures == FIGURES
        assert stale.age_seconds is not None

    async def test_inside_the_bound_google_is_not_asked_again(self):
        source, cache = _Source(), HealthCache(seconds=60)
        await cache.report(source, 2)
        await cache.report(source, 2)
        assert source.reads == 1

    async def test_a_failure_is_cached_too(self):
        """Off Google Cloud the metadata server never answers; a page must
        not wait on it for every request."""
        source, cache = _Source(), HealthCache(seconds=60)
        source.fail = True
        await cache.report(source, None)
        await cache.report(source, None)
        assert source.reads == 1


class TestGoogle:
    async def test_no_metadata_server_is_a_failure_the_cache_turns_into_unavailable(self):
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no metadata server here")

        source = GoogleMonitoring("beats-api", transport=httpx.MockTransport(refuse))
        with pytest.raises(httpx.ConnectError):
            await source.read()
        assert (await HealthCache().report(source, None)).state == "unavailable"

    async def test_figures_are_read_off_the_answers(self):
        def answer(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if "project-id" in url:
                return httpx.Response(200, text="proj-1")
            if "token" in url:
                return httpx.Response(200, json={"access_token": "t"})
            f = request.url.params["filter"]
            assert "/projects/proj-1/" in url
            if "uptime_check" in f:
                return httpx.Response(200, json={"timeSeries": [{"points": [_point(0.997)]}]})
            if 'response_code_class="5xx"' in f:
                return httpx.Response(
                    200, json={"timeSeries": [{"points": [_point("5", kind="int64Value")]}]}
                )
            if "request_count" in f:
                return httpx.Response(
                    200, json={"timeSeries": [{"points": [_point("500", kind="int64Value")]}]}
                )
            return httpx.Response(200, json={})

        figures = await GoogleMonitoring("beats-api", transport=httpx.MockTransport(answer)).read()
        assert figures.availability == 0.997
        assert figures.error_share == 0.01
        assert figures.p95_latency_ms is None, "no points is no data"
        assert figures.refused_writes == []
