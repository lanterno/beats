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
    finally:
        client.close()

    token = SessionManager(secret).create_session_token(user_id, EMAIL)
    print(json.dumps({"token": token, "userId": user_id, "email": EMAIL}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
