"""Helpers the HTTP suites share — no tests of their own.

`test_api.py` grew past the size ceiling (CLAUDE.md § Conventions) and split by
router area; several of those files, and `test_account_controls.py`, build
the same fixtures (a day job with a contract, a billed freelance project, a
report link). They live here rather than in one of the suites, so no suite
imports another, and the module is not `test_`-prefixed so pytest does not
collect it.
"""

import time
from datetime import UTC, date, datetime, timedelta

# A Monday, in the past: fixed dates keep the week tests independent of when
# they run. The contract below starts well before it.
CONTRACT_START = "2026-01-05"
WEEK = "2026-03-02"
FULL_TIME = [
    {"effective_from": CONTRACT_START, "schedule_type": "full_time", "full_time_hours": 40}
]


def _create_project(client, headers, **fields) -> dict:
    resp = client.post(
        "/api/projects/", json={"name": f"p-{time.time()}", **fields}, headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _day_job(client, headers, terms=None, **contract) -> dict:
    return _create_project(
        client, headers, kind="day_job", contract={"terms": terms or FULL_TIME, **contract}
    )


# A Wednesday in WEEK for a company day, and a GB (England) bank holiday on a
# weekday after the contract starts, for a region holiday the employer keeps open.
COMPANY_DAY = {"date": "2026-03-04", "name": "Founders' Day"}
EASTER_MONDAY = "2026-04-06"
# An entitlement that starts counting on the Monday of WEEK, inside FULL_TIME.
VACATION = {
    "days_per_year": 25.0,
    "carry_over": "all",
    "carry_over_max_days": None,
    "opening_on": WEEK,
    "opening_days": 12.0,
}


def _put_contract(client, headers, project_id: str, **contract) -> dict:
    resp = client.put(
        f"/api/projects/{project_id}/contract",
        json={"terms": FULL_TIME, **contract},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["contract"]


def _log(client, headers, project_id: str, start: str, minutes: int) -> None:
    begun = datetime.fromisoformat(start)
    resp = client.post(
        "/api/beats/",
        json={
            "project_id": project_id,
            "start": begun.isoformat(),
            "end": (begun + timedelta(minutes=minutes)).isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


BILLED_MONTH = "2026-03"
KITE_RATE = [{"effective_from": "2026-01-01", "rate_minor": 8500}]


def _this_month() -> date:
    return datetime.now(UTC).date().replace(day=1)


def _last_month() -> date:
    return (_this_month() - timedelta(days=1)).replace(day=1)


def _client_body(**fields) -> dict:
    return {
        "name": "Studio Kite",
        "contact_name": None,
        "contact_email": None,
        "currency": "EUR",
        "rates": [],
        **fields,
    }


def _create_client(client, headers, **fields) -> dict:
    resp = client.post("/api/clients/", json=_client_body(**fields), headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _put_client(client, headers, client_id: str, *, rewrite_past: bool = False, **fields):
    return client.put(
        f"/api/clients/{client_id}",
        params={"tz": "UTC"},
        json={**_client_body(**fields), "rewrite_past": rewrite_past},
        headers=headers,
    )


def _freelance(client, headers, name: str = "Website") -> dict:
    return _create_project(client, headers, name=name, kind="freelance")


def _bill(client, headers, project_id: str, client_id: str, terms, *, rewrite_past=False):
    return client.put(
        f"/api/billing/projects/{project_id}",
        params={"tz": "UTC"},
        json={"client_id": client_id, "terms": terms, "rewrite_past": rewrite_past},
        headers=headers,
    )


def _billable_from(day: date | str, **term) -> list[dict]:
    return [{"effective_from": str(day), "billable": True, **term}]


def _beat(client, headers, project_id: str, start: str, minutes: int | None) -> dict:
    """A session from `start` (UTC), finished after `minutes`, or running."""
    begun = datetime.fromisoformat(start).replace(tzinfo=UTC)
    end = None if minutes is None else (begun + timedelta(minutes=minutes)).isoformat()
    resp = client.post(
        "/api/beats/",
        json={"project_id": project_id, "start": begun.isoformat(), "end": end},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _month(client, headers, month: str = BILLED_MONTH, tz: str = "UTC") -> dict:
    resp = client.get("/api/billing/month", params={"month": month, "tz": tz}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _entries(report: dict) -> dict[str, dict]:
    return {e["beat_id"]: e for c in report["clients"] for e in c["entries"]}


def _billing_budget_body(**fields) -> dict:
    return {
        "unit": "hours",
        "period": "monthly",
        "limit_hours": 40,
        "limit_minor": None,
        "starts_on": None,
        "warn_at_percent": 80,
        **fields,
    }


def _put_billing_budget(client, headers, scope: str, scope_id: str, **fields):
    return client.put(
        f"/api/billing/budgets/{scope}/{scope_id}",
        json=_billing_budget_body(**fields),
        headers=headers,
    )


def _billing_budgets(client, headers, tz: str = "UTC") -> list[dict]:
    resp = client.get("/api/billing/budgets", params={"tz": tz}, headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _link_body(**fields) -> dict:
    return {
        "first": "2026-03-01",
        "last": "2026-03-31",
        "tz": "UTC",
        "show_amounts": True,
        "show_entries": True,
        **fields,
    }


def _mint_link(client, headers, client_id: str, **fields) -> dict:
    resp = client.post(
        f"/api/clients/{client_id}/links", json=_link_body(**fields), headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _read_report(client, token: str):
    """The public read, deliberately with no Authorization header: that it
    works without one is half of what these tests are for. The token goes in
    a header, never the path — Cloud Run logs every request's URL (#376)."""
    return client.get("/api/reports", headers={"X-Report-Token": token})


def _billed_march(client, headers, *, name: str = "Studio Kite", project: str = "Website") -> dict:
    """A client with a rate, one billed project, and March hours on it:
    two finished billable sessions and one non-billable."""
    kite = _create_client(client, headers, name=name, rates=KITE_RATE)
    website = _freelance(client, headers, project)
    assert (
        _bill(client, headers, website["id"], kite["id"], _billable_from("2026-03-01")).status_code
        == 200
    )
    _beat(client, headers, website["id"], "2026-03-02T09:00:00", 120)
    _beat(client, headers, website["id"], "2026-03-03T09:00:00", 60)
    return {"client": kite, "project": website}


# What backup 1.2 added; a 1.1 file has none of them.
BILLING_BACKUP_KEYS = ("clients", "project_billing", "billable_overrides")
# A well-formed id no account holds.
NOWHERE = "0" * 24


def _without_ids(value):
    """A response with every `id` taken out: an absence or an adjustment is
    identified by its project and date, and one restored into an empty
    account gets a new id."""
    if isinstance(value, dict):
        return {k: _without_ids(v) for k, v in value.items() if k != "id"}
    if isinstance(value, list | tuple):
        return [_without_ids(v) for v in value]


def _pair_device(client, auth_headers):
    """Pair a device and return (device_token, device_headers)."""
    resp = client.post("/api/device/pair/code", headers=auth_headers)
    code = resp.json()["code"]
    resp = client.post("/api/device/pair/exchange", json={"code": code})
    data = resp.json()
    return data["device_token"], {"Authorization": f"Bearer {data['device_token']}"}
