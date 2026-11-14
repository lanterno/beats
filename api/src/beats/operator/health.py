"""Live health from Cloud Monitoring (docs/backoffice.md § The pages, Today
and Capacity).

A narrow port (`MonitoringSource`) so the route and the pages never see
Google, and one implementation (`GoogleMonitoring`) over plain `httpx` and a
metadata-server token, the way `operator/iap.py` makes its outbound call: no
Google client library, because the image is shared with the public API.

**Nothing to configure.** The project id and the token come from the
metadata server the service already runs on; the API's service name and its
instance ceiling are set by Terraform beside the operator's other values
(both have defaults). Off Google Cloud there is no metadata server, the first
read fails, and the page says "unavailable" with the console link — never an
invented number.

**Cached in the process** (`HealthCache`): the operator runs one instance, so
a local cache is the whole cache. A failed read answers the last figures and
how old they are; a failure is cached too, so a local run does not wait on an
unreachable metadata server on every request. Nothing is stored: no time
series, no table, no query box.

The filters below are the ones the `api` dashboard in
`terraform/monitoring.tf` draws, and change with it.
"""

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

import httpx

METADATA = "http://metadata.google.internal/computeMetadata/v1"
MONITORING = "https://monitoring.googleapis.com/v3"
CACHE_SECONDS = 60.0
TIMEOUT_SECONDS = 3.0

# Decided 2026-11-14 (docs/backoffice.md § The pages): 99.5% a month.
AVAILABILITY_TARGET = 0.995


@dataclass(frozen=True)
class RouteFigure:
    route: str
    value: float


@dataclass(frozen=True)
class HealthFigures:
    """What Monitoring answered. A figure Google had no points for is None,
    never zero: an empty series is "no data", not "no errors"."""

    availability: float | None  # share of uptime probes passing, last 24 h
    error_share: float | None  # 5xx / all requests, last hour
    p95_latency_ms: float | None  # last hour
    instances: float | None  # most recent 5-minute maximum
    refused_writes: list[RouteFigure] = field(default_factory=list)  # last 24 h


@dataclass(frozen=True)
class HealthReport:
    state: Literal["live", "stale", "unavailable"]
    as_of: datetime | None
    age_seconds: float | None
    figures: HealthFigures | None
    max_instances: int | None
    availability_target: float = AVAILABILITY_TARGET


class MonitoringSource(Protocol):
    async def read(self) -> HealthFigures: ...


# ── parsing Monitoring's answers ─────────────────────────────────────


def _point_value(point: dict[str, Any]) -> float | None:
    value = point.get("value") or {}
    for key in ("doubleValue", "int64Value"):
        if key in value:
            try:
                return float(value[key])
            except TypeError, ValueError:
                return None
    return None


def latest_value(body: dict[str, Any]) -> float | None:
    """The newest point across the answer's series, or None when Google
    returned no series, or series with no points. Points come newest first."""
    best: tuple[str, float] | None = None
    for series in body.get("timeSeries") or []:
        for point in series.get("points") or []:
            value = _point_value(point)
            end = (point.get("interval") or {}).get("endTime", "")
            if value is not None and (best is None or end > best[0]):
                best = (end, value)
    return best[1] if best else None


def total_value(body: dict[str, Any]) -> float | None:
    """Every point of every series added up — for counts aligned into one
    window. None when there was nothing to add, so a quiet hour reads as no
    data rather than as zero requests."""
    values = [
        v
        for series in body.get("timeSeries") or []
        for point in series.get("points") or []
        if (v := _point_value(point)) is not None
    ]
    return sum(values) if values else None


def by_label(body: dict[str, Any], label: str) -> list[RouteFigure]:
    """One figure per value of a metric label, largest first."""
    out: dict[str, float] = {}
    for series in body.get("timeSeries") or []:
        name = ((series.get("metric") or {}).get("labels") or {}).get(label)
        if not name:
            continue
        for point in series.get("points") or []:
            value = _point_value(point)
            if value is not None:
                out[name] = out.get(name, 0.0) + value
    return [RouteFigure(k, v) for k, v in sorted(out.items(), key=lambda kv: -kv[1])]


def share(part: float | None, whole: float | None) -> float | None:
    """A ratio that knows the difference between no errors and no data."""
    if whole is None or whole == 0:
        return None
    return (part or 0.0) / whole


# ── Google ───────────────────────────────────────────────────────────


class GoogleMonitoring:
    def __init__(
        self,
        api_service_name: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._service = api_service_name
        self._transport = transport
        self._project: str | None = None

    async def _metadata(self, client: httpx.AsyncClient, path: str) -> httpx.Response:
        resp = await client.get(f"{METADATA}/{path}", headers={"Metadata-Flavor": "Google"})
        resp.raise_for_status()
        return resp

    async def _series(
        self,
        client: httpx.AsyncClient,
        token: str,
        metric_filter: str,
        *,
        window: timedelta,
        aligner: str,
        reducer: str,
        period: timedelta | None = None,
        group_by: str | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(UTC)
        params: dict[str, str] = {
            "filter": metric_filter,
            "interval.startTime": (now - window).isoformat().replace("+00:00", "Z"),
            "interval.endTime": now.isoformat().replace("+00:00", "Z"),
            "aggregation.alignmentPeriod": f"{int((period or window).total_seconds())}s",
            "aggregation.perSeriesAligner": aligner,
            "aggregation.crossSeriesReducer": reducer,
        }
        if group_by:
            params["aggregation.groupByFields"] = group_by
        resp = await client.get(
            f"{MONITORING}/projects/{self._project}/timeSeries",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json()

    async def read(self) -> HealthFigures:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, transport=self._transport) as client:
            if self._project is None:
                self._project = (await self._metadata(client, "project/project-id")).text
            token = (
                await self._metadata(client, "instance/service-accounts/default/token")
            ).json()["access_token"]

            api = (
                f'resource.type="cloud_run_revision" '
                f'AND resource.label.service_name="{self._service}"'
            )
            requests = f'{api} AND metric.type="run.googleapis.com/request_count"'
            hour, day = timedelta(hours=1), timedelta(days=1)

            uptime = await self._series(
                client,
                token,
                'resource.type="uptime_url" '
                'AND metric.type="monitoring.googleapis.com/uptime_check/check_passed"',
                window=day,
                aligner="ALIGN_FRACTION_TRUE",
                reducer="REDUCE_MEAN",
            )
            errors = await self._series(
                client,
                token,
                f'{requests} AND metric.label.response_code_class="5xx"',
                window=hour,
                aligner="ALIGN_SUM",
                reducer="REDUCE_SUM",
            )
            total = await self._series(
                client, token, requests, window=hour, aligner="ALIGN_SUM", reducer="REDUCE_SUM"
            )
            latency = await self._series(
                client,
                token,
                f'{api} AND metric.type="run.googleapis.com/request_latencies"',
                window=hour,
                aligner="ALIGN_DELTA",
                reducer="REDUCE_PERCENTILE_95",
            )
            instances = await self._series(
                client,
                token,
                f'{api} AND metric.type="run.googleapis.com/container/instance_count"',
                window=timedelta(minutes=15),
                period=timedelta(minutes=5),
                aligner="ALIGN_MAX",
                reducer="REDUCE_SUM",
            )
            refused = await self._series(
                client,
                token,
                'resource.type="cloud_run_revision" AND metric.type='
                f'"logging.googleapis.com/user/{self._service}/write_limit_refusals"',
                window=day,
                aligner="ALIGN_SUM",
                reducer="REDUCE_SUM",
                group_by="metric.label.route",
            )

        return HealthFigures(
            availability=latest_value(uptime),
            error_share=share(total_value(errors), total_value(total)),
            p95_latency_ms=latest_value(latency),
            instances=latest_value(instances),
            refused_writes=by_label(refused, "route"),
        )


# ── the cache ────────────────────────────────────────────────────────


class HealthCache:
    """The last answer, and when. Live inside the bound; past it, read
    again; if that fails, the last figures marked stale, or unavailable
    when there never were any."""

    def __init__(self, *, seconds: float = CACHE_SECONDS):
        self._seconds = seconds
        self._figures: HealthFigures | None = None
        self._as_of: datetime | None = None
        self._read_at = 0.0  # monotonic, of the last attempt, success or not
        self._failed = False

    async def report(self, source: MonitoringSource, max_instances: int | None) -> HealthReport:
        if self._read_at == 0.0 or time.monotonic() - self._read_at >= self._seconds:
            self._read_at = time.monotonic()
            try:
                self._figures = await source.read()
                self._as_of = datetime.now(UTC)
                self._failed = False
            except Exception:  # noqa: BLE001 — a Google failure is a state, not a crash
                self._failed = True
        if self._figures is None or self._as_of is None:
            return HealthReport("unavailable", None, None, None, max_instances)
        age = (datetime.now(UTC) - self._as_of).total_seconds()
        state = "stale" if self._failed else "live"
        return HealthReport(state, self._as_of, age, self._figures, max_instances)
