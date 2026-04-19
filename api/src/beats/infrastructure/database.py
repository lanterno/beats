"""Database connection management using Motor async MongoDB driver."""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from beats.settings import settings


class Database:
    """Async MongoDB connection manager.

    Manages the lifecycle of the Motor async client connection.
    Should be connected during app startup and disconnected on shutdown.
    """

    client: AsyncIOMotorClient | None = None
    db: AsyncIOMotorDatabase | None = None

    @classmethod
    async def connect(cls, dsn: str | None = None, db_name: str | None = None) -> None:
        """Establish connection to MongoDB.

        Args:
            dsn: MongoDB connection string. Defaults to settings.db_dsn.
            db_name: Database name. Defaults to settings.db_name.
        """
        dsn = dsn or settings.db_dsn
        db_name = db_name or settings.db_name
        cls.client = AsyncIOMotorClient(dsn)
        cls.db = cls.client[db_name]
        await cls._ensure_indexes()

    @classmethod
    async def disconnect(cls) -> None:
        """Close the MongoDB connection."""
        if cls.client:
            cls.client.close()
            cls.client = None
            cls.db = None

    @classmethod
    async def _ensure_indexes(cls) -> None:
        """Create required indexes if they don't already exist."""
        if cls.db is None:
            return
        await cls.db.users.create_index("email", unique=True)
        await cls.db.credentials.create_index("credential_id", unique=True)
        await cls.db.credentials.create_index("user_id")
        # Device pairing indexes
        await cls.db.pairing_codes.create_index("expires_at", expireAfterSeconds=0)
        await cls.db.pairing_codes.create_index("code_hash", unique=True)
        await cls.db.device_registrations.create_index("device_id", unique=True)
        await cls.db.device_registrations.create_index("user_id")
        # Flow windows and signal summaries
        await cls.db.flow_windows.create_index([("user_id", 1), ("window_start", -1)])
        await cls.db.signal_summaries.create_index(
            [("user_id", 1), ("device_id", 1), ("hour", 1)], unique=True
        )
        # Biometrics
        await cls.db.biometric_days.create_index(
            [("user_id", 1), ("date", 1), ("source", 1)], unique=True
        )
        await cls.db.fitbit_integrations.create_index("user_id", unique=True)
        await cls.db.oura_integrations.create_index("user_id", unique=True)

    @classmethod
    def get_db(cls) -> AsyncIOMotorDatabase:
        """Get the database instance.

        Raises:
            RuntimeError: If database is not connected.
        """
        if cls.db is None:
            raise RuntimeError("Database not connected. Call Database.connect() first.")
        return cls.db
