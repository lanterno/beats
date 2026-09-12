"""Pytest configuration — provides the MongoDB the integration tests run against.

By default a testcontainer is started for the session. Set ``BEATS_TEST_ENV=1``
to point the suite at an already-running MongoDB via ``DB_DSN``/``DB_NAME``
instead — that is what CI does with a service container, and what to use
locally when Docker-in-Docker or container limits get in the way.
"""

import asyncio
import os
from datetime import UTC, datetime

import pytest
from bson import ObjectId

# mongod opens a handful of descriptors per collection and index. The suite
# clears and refills every collection once per test class, and the container
# default (1024) is low enough that WiredTiger hits EMFILE partway through a
# full run, panics, and takes the database down with it.
_MONGO_NOFILE = 64000

_mongo_container = None


def _dsn() -> str:
    return os.environ.get("DB_DSN", "mongodb://localhost:27017")


def _db_name() -> str:
    return os.environ.get("DB_NAME", "beats_test")


def pytest_configure(config):
    """Start the MongoDB testcontainer before any test module is imported.

    Also selects the committed .env.test over a developer's local .env, and sets
    DB_DSN/DB_NAME so pydantic-settings picks them up when Settings() is first
    instantiated.
    """
    global _mongo_container

    # Must happen before any test module imports beats.settings, which builds
    # Settings() at import time. .env.test is committed; a developer's .env is
    # not, so this is also what makes a fresh clone runnable.
    os.environ.setdefault("BEATS_ENV_FILE", ".env.test")

    if os.getenv("BEATS_TEST_ENV") == "1":
        return

    from docker.types import Ulimit
    from testcontainers.mongodb import MongoDbContainer

    _mongo_container = (
        MongoDbContainer("mongo:8")
        .with_kwargs(ulimits=[Ulimit(name="nofile", soft=_MONGO_NOFILE, hard=_MONGO_NOFILE)])
        .start()
    )
    os.environ["DB_DSN"] = _mongo_container.get_connection_url()
    os.environ["DB_NAME"] = "beats_test"


def pytest_unconfigure(config):
    """Stop the MongoDB testcontainer."""
    global _mongo_container
    if _mongo_container is not None:
        _mongo_container.stop()
        _mongo_container = None


@pytest.fixture(scope="session")
def mongo():
    """One synchronous MongoClient for the whole run.

    Session-scoped because the fixtures below run per test class; opening a
    client per class churns connections for no benefit.
    """
    from pymongo import MongoClient

    client = MongoClient(_dsn())
    try:
        yield client[_db_name()]
    finally:
        client.close()


@pytest.fixture(scope="session", autouse=True)
def _indexes():
    """Build the production index set once, from the production definition.

    Indexes survive the per-class cleanup below, so this runs once rather than
    once per class — and calls ``ensure_indexes`` directly so the suite can
    never drift from what the app actually creates at startup.
    """
    from pymongo import AsyncMongoClient

    from beats.infrastructure.database import ensure_indexes

    async def build() -> None:
        client = AsyncMongoClient(_dsn())
        try:
            await ensure_indexes(client[_db_name()])
        finally:
            await client.close()

    asyncio.run(build())


@pytest.fixture(autouse=True)
def _clear_device_cache():
    """Device revocation verdicts are cached process-wide for 30s.

    Without this, a device paired in one test could still read as allowed in
    the next after the collections were emptied underneath it.
    """
    from beats.auth import device_access

    device_access.clear()
    yield
    device_access.clear()


@pytest.fixture(scope="class", autouse=True)
def clean_db(mongo, _indexes):
    """Empty every collection before each test class.

    Deletes documents rather than dropping collections: a drop takes the
    collection's indexes with it, which would mean rebuilding the whole index
    set for all 30-odd test classes and destroying TTL indexes the app creates
    once at startup.
    """
    for name in mongo.list_collection_names():
        mongo[name].delete_many({})
    return


@pytest.fixture(scope="session")
def test_client():
    """Provide a TestClient that properly triggers the FastAPI lifespan."""
    from starlette.testclient import TestClient

    from server import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def client(test_client):
    """The TestClient, as an ordinary fixture parameter.

    Tests used to reach a module-level `client` that an autouse fixture
    assigned through `global`. Typed `TestClient | None`, that one global was
    the source of 508 of the project's 717 type diagnostics — which is why
    `error-on-warning` had to be off, which meant no type regression could
    fail CI.
    """
    return test_client


@pytest.fixture
def auth_headers(auth_info) -> dict[str, str]:
    """Bearer header for the per-class test user."""
    return auth_info["headers"]


@pytest.fixture(scope="class", autouse=True)
def auth_info(mongo, clean_db):
    """Create a test user and JWT token after each cleanup."""
    from beats.auth.session import SessionManager
    from beats.settings import settings

    user_id = str(ObjectId())
    mongo.users.insert_one(
        {
            "_id": ObjectId(user_id),
            "email": "test@example.com",
            "display_name": "Test User",
            "created_at": datetime.now(UTC),
        }
    )

    sm = SessionManager(settings.jwt_secret)
    token = sm.create_session_token(user_id, "test@example.com")

    return {"user_id": user_id, "headers": {"Authorization": f"Bearer {token}"}}


@pytest.fixture
def other_auth_headers(mongo) -> dict[str, str]:
    """Bearer header for a second user, for the isolation tests: someone else's
    data must read as not found, never as forbidden."""
    from beats.auth.session import SessionManager
    from beats.settings import settings

    user_id = str(ObjectId())
    email = f"other-{user_id}@example.com"
    mongo.users.insert_one({"_id": ObjectId(user_id), "email": email, "display_name": None})
    token = SessionManager(settings.jwt_secret).create_session_token(user_id, email)
    return {"Authorization": f"Bearer {token}"}
