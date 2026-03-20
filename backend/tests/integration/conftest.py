"""
Integration test fixtures — require real PostgreSQL + Redis.

Run with:
    pytest -m integration
"""

import os
import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

# ── Test database URL ─────────────────────────────────────────────────────────
# Override with TEST_DATABASE_URL env var; falls back to a local test DB.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:password@localhost:5432/calendar_ai_test",
)

NOW = datetime(2026, 3, 20, 10, 0, 0, tzinfo=timezone.utc)
TOMORROW = NOW + timedelta(days=1)


# ── Engine + schema ───────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def test_engine():
    """Create async engine pointing at the test database; build schema once."""
    from database.models.base import Base
    # Import models so they register with Base.metadata
    from database.models.event import EventModel  # noqa: F401
    from database.models.user import UserModel  # noqa: F401

    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(test_engine):
    """Real AsyncSession; rolls back + truncates tables after each test."""
    factory = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
        await session.rollback()
        # Truncate all data so tests are isolated
        async with test_engine.begin() as conn:
            await conn.execute(text("TRUNCATE TABLE events, users RESTART IDENTITY CASCADE"))


# ── Test user ─────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_user(async_session):
    """Create and return a real User row in the test database."""
    import uuid
    from adapter.user_adapter import UserAdapter
    from models import UserCreate
    from utils.password import hash_password

    user_data = UserCreate(
        user_id=str(uuid.uuid4()),
        name="Integration User",
        email="integration@example.com",
        password=hash_password("secret123"),
    )
    adapter = UserAdapter(async_session)
    user = await adapter.create_user(user_data)
    return user


# ── Test events ───────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_events(async_session, test_user):
    """Create 5 real Event rows belonging to test_user."""
    from adapter.event_adapter import EventAdapter
    from models import EventCreate

    adapter = EventAdapter(async_session)
    events = []
    priorities = ["optional", "mandatory", "optional", "mandatory", "optional"]
    for i in range(5):
        ec = EventCreate(
            title=f"Integration Event {i}",
            startDate=TOMORROW.replace(hour=8 + i * 2),
            duration=60,
            location=f"Room {i}",
        )
        event = await adapter.create_event(test_user.id, ec)
        events.append(event)
    return events
