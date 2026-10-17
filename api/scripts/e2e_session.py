#!/usr/bin/env python3
"""Seed a user and print a session token, for the Playwright suite.

The E2E specs exercise pages behind `ProtectedRoute`, which needs a session
token in localStorage. Sessions are normally obtained through a WebAuthn
passkey ceremony that a headless browser cannot perform, so the suite has to be
handed one — which is what this prints.

It talks to the same database and signs with the same secret as the running
API, so the token it mints is an ordinary session, not a bypass. Nothing in the
application changes to accommodate it.

Prints JSON: {"token": ..., "userId": ..., "email": ...}
"""

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from bson import ObjectId
from pymongo import MongoClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from beats.auth.session import SessionManager
from beats.domain.models import (
    BillingTerm,
    Client,
    FlowWindow,
    ProjectBilling,
    RateTerm,
)
from beats.infrastructure.repositories import serialize_to_document

EMAIL = "e2e@example.test"


def _seed_content(db, user_id: str) -> None:
    """Give the suite something to look at.

    Several assertions are about UI that only exists once there is data — the
    tag filter on Insights renders only when a tag exists at all — so an empty
    database makes those tests silently vacuous rather than passing honestly.
    """
    if db.projects.find_one({"user_id": user_id}):
        return

    project_id = ObjectId()
    db.projects.insert_one(
        {
            "_id": project_id,
            "user_id": user_id,
            "name": "E2E Project",
            "description": "Seeded for the end-to-end suite",
            "color": "#d4952a",
            "archived": False,
            "weekly_goal": 5.0,
            "goal_type": "target",
            "goal_overrides": [],
            "autostart_repos": [],
        }
    )

    now = datetime.now(UTC)
    db.timeLogs.insert_many(
        [
            {
                "user_id": user_id,
                "project_id": str(project_id),
                "start": now - timedelta(days=day, hours=2),
                "end": now - timedelta(days=day, hours=1),
                "note": "seeded session",
                "tags": ["e2e"],
            }
            for day in range(3)
        ]
    )


def _seed_flow(db, user_id: str) -> None:
    """A week of the daemon's flow windows, for the flow charts on Insights.

    Those cards render nothing without windows, and their bars are what the
    suite measures: jsdom has no layout, so only a browser can see a bar
    collapse to no height. A window an hour through a working day, at scores
    that rise and fall, gives every day and eight hours a bar of its own
    height, and the 56 windows clear Flow by weekday's floor of 50. Written
    through the model and the repository's serialiser, so the stored shape is
    the API's.
    """
    if db.flow_windows.find_one({"user_id": user_id}):
        return
    project = db.projects.find_one({"user_id": user_id})
    project_id = str(project["_id"]) if project else None
    morning = datetime.now(UTC).replace(hour=9, minute=0, second=0, microsecond=0)
    scores = (0.35, 0.5, 0.65, 0.8, 0.7, 0.55, 0.45, 0.3)
    docs = []
    # The seven days before today: today's working hours may not have
    # happened yet, and a window after now is outside every range read.
    for day in range(1, 8):
        for hour, score in enumerate(scores):
            start = morning - timedelta(days=day) + timedelta(hours=hour)
            window = FlowWindow(
                window_start=start,
                window_end=start + timedelta(minutes=1),
                flow_score=min(score + day * 0.02, 1.0),
                dominant_bundle_id="com.microsoft.VSCode",
                dominant_category="coding",
                active_project_id=project_id,
            )
            doc = serialize_to_document(window.model_dump(mode="json", exclude_none=True))
            docs.append({**doc, "user_id": user_id})
    db.flow_windows.insert_many(docs)


def _seed_billing(db, user_id: str) -> None:
    """A client billed for a freelance project, for the Clients page and the
    project page's billing panel.

    The client panel's lines table and amount, and the billing panel, exist
    only once a project is billed and has hours in the month on screen: a
    client at 85.00 EUR an hour from 1 January, a freelance project billable
    at that rate from the same day, and two finished sessions in the last
    three hours, so this month's report has a line and a non-zero amount
    (unless the month began less than three hours ago). The client and the
    billing are written through their models and the repository's
    serialiser, so the stored shape is the API's.
    """
    if db.clients.find_one({"user_id": user_id}):
        return
    now = datetime.now(UTC)
    new_year = now.date().replace(month=1, day=1)

    client_id = ObjectId()
    client = Client(
        id=str(client_id),
        name="E2E Client",
        currency="EUR",
        rates=[RateTerm(effective_from=new_year, rate_minor=8500)],
    )
    db.clients.insert_one(
        {
            **serialize_to_document(client.model_dump(mode="json", exclude_none=True)),
            "user_id": user_id,
        }
    )

    project_id = ObjectId()
    db.projects.insert_one(
        {
            "_id": project_id,
            "user_id": user_id,
            "name": "E2E Client Work",
            "description": "Seeded for the end-to-end suite: a billed freelance project",
            "color": "#3d8bd4",
            "archived": False,
            "kind": "freelance",
            "goal_overrides": [],
            "autostart_repos": [],
        }
    )
    billing = ProjectBilling(
        project_id=str(project_id),
        client_id=str(client_id),
        terms=[BillingTerm(effective_from=new_year, billable=True)],
    )
    db.project_billing.insert_one(
        {
            **serialize_to_document(billing.model_dump(mode="json", exclude_none=True)),
            "user_id": user_id,
        }
    )

    db.timeLogs.insert_many(
        [
            {
                "user_id": user_id,
                "project_id": str(project_id),
                "start": now - timedelta(minutes=start),
                "end": now - timedelta(minutes=start - length),
                "tags": [],
            }
            for start, length in ((180, 60), (90, 75))
        ]
    )


def main() -> int:
    dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "beats")
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        print("JWT_SECRET must be set to the same value the API is running with", file=sys.stderr)
        return 2

    client = MongoClient(dsn)
    try:
        users = client[db_name].users
        existing = users.find_one({"email": EMAIL})
        if existing:
            user_id = str(existing["_id"])
        else:
            user_id = str(ObjectId())
            users.insert_one(
                {
                    "_id": ObjectId(user_id),
                    "email": EMAIL,
                    "display_name": "E2E",
                    "created_at": datetime.now(UTC),
                }
            )
        _seed_content(client[db_name], user_id)
        _seed_flow(client[db_name], user_id)
        _seed_billing(client[db_name], user_id)
    finally:
        client.close()

    token = SessionManager(secret).create_session_token(user_id, EMAIL)
    print(json.dumps({"token": token, "userId": user_id, "email": EMAIL}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
