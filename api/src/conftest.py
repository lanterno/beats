"""Pytest configuration — spins up a MongoDB testcontainer for integration tests."""

import os
from datetime import UTC, datetime

import pytest
from bson import ObjectId

_mongo_container = None


def pytest_configure(config):
    """Start MongoDB testcontainer before any test modules are imported.

    Sets DB_DSN and DB_NAME env vars so pydantic-settings picks them up
    when Settings() is first instantiated. Skipped when running inside
    Docker Compose (BEATS_TEST_ENV=1).
    """
    global _mongo_container

    if os.getenv("BEATS_TEST_ENV") == "1":
        return

    from testcontainers.mongodb import MongoDbContainer

    _mongo_container = MongoDbContainer("mongo:8").start()
    os.environ["DB_DSN"] = _mongo_container.get_connection_url()
    os.environ["DB_NAME"] = "beats_test"


def pytest_unconfigure(config):
    """Stop the MongoDB testcontainer."""
    global _mongo_container
    if _mongo_container is not None:
        _mongo_container.stop()
        _mongo_container = None


@pytest.fixture(scope="session")
def test_client():
    """Provide a TestClient that properly triggers the FastAPI lifespan."""
    from starlette.testclient import TestClient

    from server import app

    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="class", autouse=True)
def clean_db():
    """Drop all test collections before each test class."""
    from pymongo import MongoClient

    dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "beats_test")
    sync_client = MongoClient(dsn)
    db = sync_client[db_name]
    for name in db.list_collection_names():
        db[name].drop()
    sync_client.close()
    yield


@pytest.fixture(scope="class", autouse=True)
def auth_info(clean_db):
    """Create a test user and JWT token after each collection drop."""
    from pymongo import MongoClient

    from beats.auth.session import SessionManager
    from beats.settings import settings

    dsn = os.environ.get("DB_DSN", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "beats_test")
    sync_client = MongoClient(dsn)
    db = sync_client[db_name]

    user_id = str(ObjectId())
    db.users.insert_one({
        "_id": ObjectId(user_id),
        "email": "test@example.com",
        "display_name": "Test User",
        "created_at": datetime.now(UTC),
    })

    sm = SessionManager(settings.jwt_secret)
    token = sm.create_session_token(user_id, "test@example.com")
    sync_client.close()

    yield {"user_id": user_id, "headers": {"Authorization": f"Bearer {token}"}}
