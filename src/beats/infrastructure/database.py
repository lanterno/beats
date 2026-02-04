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

    @classmethod
    async def disconnect(cls) -> None:
        """Close the MongoDB connection."""
        if cls.client:
            cls.client.close()
            cls.client = None
            cls.db = None

    @classmethod
    def get_db(cls) -> AsyncIOMotorDatabase:
        """Get the database instance.

        Raises:
            RuntimeError: If database is not connected.
        """
        if cls.db is None:
            raise RuntimeError("Database not connected. Call Database.connect() first.")
        return cls.db
