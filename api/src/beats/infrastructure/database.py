"""Database connection management using the PyMongo async MongoDB driver."""

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from beats.settings import settings


async def ensure_indexes(db: AsyncDatabase) -> None:
    """Create every index the application relies on.

    Takes the database explicitly rather than reading the ``Database``
    singleton so the test suite can build the same index set once per
    run without standing up a second connection manager.
    """
    await db.users.create_index("email", unique=True)
    # One identity at a provider maps to exactly one beats account. Partial,
    # because a multikey index gives every user without identities the same
    # missing key, and a plain unique index would allow only one of them.
    await db.users.create_index(
        [("identities.issuer", 1), ("identities.subject", 1)],
        unique=True,
        partialFilterExpression={"identities.subject": {"$type": "string"}},
    )
    # Sign-ins in progress: single-use, gone ten minutes after they start.
    await db.sso_flows.create_index("expires_at", expireAfterSeconds=0)
    await db.credentials.create_index("credential_id", unique=True)
    await db.credentials.create_index("user_id")
    await db.pairing_codes.create_index("expires_at", expireAfterSeconds=0)
    await db.pairing_codes.create_index("code_hash", unique=True)
    await db.device_registrations.create_index("device_id", unique=True)
    await db.device_registrations.create_index("user_id")
    await db.flow_windows.create_index([("user_id", 1), ("window_start", -1)])
    await db.signal_summaries.create_index(
        [("user_id", 1), ("device_id", 1), ("hour", 1)], unique=True
    )
    await db.biometric_days.create_index([("user_id", 1), ("date", 1), ("source", 1)], unique=True)
    await db.fitbit_integrations.create_index("user_id", unique=True)
    await db.oura_integrations.create_index("user_id", unique=True)
    # One absence per day per project: a second one replaces the first.
    await db.absences.create_index([("user_id", 1), ("project_id", 1), ("date", 1)], unique=True)
    # One balance adjustment per day per project, the same way.
    await db.balance_adjustments.create_index(
        [("user_id", 1), ("project_id", 1), ("date", 1)], unique=True
    )
    # A user's sessions by project and start: the billing month's range read
    # over its projects, and every per-project read before it.
    await db.timeLogs.create_index([("user_id", 1), ("project_id", 1), ("start", 1)])
    # The project list, as `MongoProjectRepository.list` asks for it. Until
    # organisations this was the one collection read by `user_id` without an
    # index — a scan at one person's scale, and wrong once the read became
    # "mine, plus every organisation project I am assigned to" across every
    # tenant (the roadmap's stage 2 note; measured in test_organisations).
    await db.projects.create_index([("user_id", 1), ("archived", 1)])
    await db.clients.create_index("user_id")
    # One billing per project: a second write replaces the first. By client
    # too, for the reads that ask what is billed to one.
    await db.project_billing.create_index([("user_id", 1), ("project_id", 1)], unique=True)
    await db.project_billing.create_index([("user_id", 1), ("client_id", 1)])
    # One billable override per beat, the same way.
    await db.billable_overrides.create_index([("user_id", 1), ("beat_id", 1)], unique=True)
    # One billing budget per scope — a client, or a billed project — the same
    # way. Every other read lists the whole collection, a small set.
    await db.billing_budgets.create_index(
        [("user_id", 1), ("scope", 1), ("scope_id", 1)], unique=True
    )
    # A report link is found by its token alone: the public read has no
    # session, so this is the one index that is not led by user_id. Unique,
    # because the token is the whole of a link's identity to its reader.
    await db.report_links.create_index("token", unique=True)
    # The owner's list, per client.
    await db.report_links.create_index([("user_id", 1), ("client_id", 1)])


class Database:
    """Async MongoDB connection manager.

    Manages the lifecycle of the PyMongo async client connection.
    Should be connected during app startup and disconnected on shutdown.
    """

    client: AsyncMongoClient | None = None
    db: AsyncDatabase | None = None

    @classmethod
    async def connect(cls, dsn: str | None = None, db_name: str | None = None) -> None:
        """Establish connection to MongoDB.

        Args:
            dsn: MongoDB connection string. Defaults to settings.db_dsn.
            db_name: Database name. Defaults to settings.db_name.
        """
        dsn = dsn or settings.db_dsn
        db_name = db_name or settings.db_name
        cls.client = AsyncMongoClient(dsn)
        cls.db = cls.client[db_name]
        await ensure_indexes(cls.db)

    @classmethod
    async def disconnect(cls) -> None:
        """Close the MongoDB connection."""
        if cls.client:
            await cls.client.close()
            cls.client = None
            cls.db = None

    @classmethod
    def get_db(cls) -> AsyncDatabase:
        """Get the database instance.

        Raises:
            RuntimeError: If database is not connected.
        """
        if cls.db is None:
            raise RuntimeError("Database not connected. Call Database.connect() first.")
        return cls.db
