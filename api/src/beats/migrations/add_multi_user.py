"""Migration: Add multi-user support.

Creates the owner user, migrates file-based credentials to MongoDB,
and adds user_id to all existing documents.

Run standalone:
    cd api && uv run python -m beats.migrations.add_multi_user
"""

import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient

from beats.settings import settings

logger = logging.getLogger(__name__)

MIGRATION_NAME = "add_multi_user"

DATA_COLLECTIONS = ["timeLogs", "projects", "intentions", "daily_notes", "webhooks"]


async def run_migration(dsn: str | None = None, db_name: str | None = None) -> None:
    """Run the multi-user migration.

    Args:
        dsn: MongoDB connection string. Defaults to settings.
        db_name: Database name. Defaults to settings.
    """
    dsn = dsn or settings.db_dsn
    db_name = db_name or settings.db_name

    client = AsyncIOMotorClient(dsn)
    db = client[db_name]

    try:
        # Check if already migrated
        existing = await db["_migrations"].find_one({"name": MIGRATION_NAME})
        if existing:
            logger.info("Migration '%s' already completed, skipping.", MIGRATION_NAME)
            return

        # Prompt for owner email (interactive mode only)
        owner_email = _get_owner_email()

        logger.info("Starting multi-user migration...")
        logger.info("Owner email: %s", owner_email)

        # 1. Create owner user
        user_doc = {
            "email": owner_email,
            "display_name": "Beats Owner",
            "created_at": datetime.now(UTC).isoformat(),
        }
        result = await db.users.insert_one(user_doc)
        owner_id = str(result.inserted_id)
        logger.info("Created owner user: %s", owner_id)

        # 2. Create unique index on users.email
        await db.users.create_index("email", unique=True)

        # 3. Migrate file-based credentials to MongoDB
        credentials_path = settings.credentials_path
        await _migrate_credentials(db, credentials_path, owner_id)

        # 4. Add user_id to all existing documents
        for collection_name in DATA_COLLECTIONS:
            collection = db[collection_name]
            result = await collection.update_many(
                {"user_id": {"$exists": False}},
                {"$set": {"user_id": owner_id}},
            )
            logger.info(
                "Updated %d documents in '%s' with user_id",
                result.modified_count,
                collection_name,
            )

        # 5. Create indexes
        for collection_name in DATA_COLLECTIONS:
            await db[collection_name].create_index("user_id")
        await db.credentials.create_index("credential_id", unique=True)
        await db.credentials.create_index("user_id")
        logger.info("Created indexes")

        # 6. Record migration as complete
        await db["_migrations"].insert_one({
            "name": MIGRATION_NAME,
            "completed_at": datetime.now(UTC).isoformat(),
            "owner_id": owner_id,
        })
        logger.info("Migration '%s' completed successfully.", MIGRATION_NAME)

    finally:
        client.close()


async def _migrate_credentials(db, credentials_path: Path, owner_id: str) -> None:
    """Migrate file-based credentials to MongoDB credentials collection."""
    if not credentials_path.exists():
        logger.info("No credentials file at %s, skipping.", credentials_path)
        return

    try:
        with open(credentials_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        logger.warning("Could not read credentials file, skipping credential migration.")
        return

    creds = data.get("credentials", [])
    if not creds:
        logger.info("No credentials to migrate.")
        return

    for cred in creds:
        await db.credentials.insert_one({
            "user_id": owner_id,
            "credential_id": cred["credential_id"],
            "public_key": cred["public_key"],
            "sign_count": cred["sign_count"],
            "created_at": cred.get("created_at", datetime.now(UTC).isoformat()),
            "device_name": cred.get("device_name"),
        })

    logger.info("Migrated %d credentials to MongoDB.", len(creds))


def _get_owner_email() -> str:
    """Get the owner email interactively or from environment."""
    # Allow non-interactive usage via env var
    import os

    env_email = os.environ.get("OWNER_EMAIL")
    if env_email:
        return env_email

    # Interactive prompt
    if not sys.stdin.isatty():
        return "owner@beats.local"

    print("\n=== Beats Multi-User Migration ===")
    print("This will create the first user account and assign all existing data to it.\n")
    while True:
        email = input("Enter owner email: ").strip()
        if "@" in email and "." in email:
            return email
        print("Please enter a valid email address.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    asyncio.run(run_migration())
