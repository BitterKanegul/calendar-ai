"""
Root conftest.py — shared fixtures for all test tiers.

No external services required here; everything is mocked.
"""

# ── Set required env vars BEFORE any source imports ──────────────────────────
# config.py instantiates Settings() at module level and requires these two
# fields.  Setting defaults here ensures unit tests never need a .env file.
import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost:5432/calendar_ai_test")
os.environ.setdefault("SECRET_KEY", "unit-test-secret-key-not-used-in-production")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")
# ─────────────────────────────────────────────────────────────────────────────

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# ── Shared sample data ────────────────────────────────────────────────────────

USER_ID = 1
USER_UUID = "11111111-1111-1111-1111-111111111111"
EVENT_UUID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"

NOW = datetime(2026, 3, 20, 10, 0, 0, tzinfo=timezone.utc)
TOMORROW = NOW + timedelta(days=1)


@pytest.fixture
def sample_user_dict():
    return {
        "id": USER_ID,
        "user_id": USER_UUID,
        "name": "Test User",
        "email": "test@example.com",
        "password": "hashed_password",
        "created_at": NOW.isoformat(),
    }


@pytest.fixture
def sample_event_dict():
    return {
        "id": EVENT_UUID,
        "title": "Team Meeting",
        "startDate": TOMORROW.replace(hour=14, minute=0),
        "endDate": TOMORROW.replace(hour=15, minute=0),
        "duration": 60,
        "location": "Conference Room A",
        "user_id": USER_ID,
        "priority": "optional",
        "flexibility": "movable",
        "category": "work",
    }


@pytest.fixture
def sample_event(sample_event_dict):
    from models import Event
    return Event(**sample_event_dict)


@pytest.fixture
def sample_events(sample_event_dict):
    from models import Event
    events = []
    for i in range(5):
        d = sample_event_dict.copy()
        d["id"] = f"event-uuid-{i}"
        d["title"] = f"Event {i}"
        d["startDate"] = TOMORROW.replace(hour=8 + i * 2)
        d["endDate"] = TOMORROW.replace(hour=9 + i * 2)
        d["duration"] = 60
        events.append(Event(**d))
    return events


@pytest.fixture
def sample_event_create():
    from models import EventCreate
    return EventCreate(
        title="Team Meeting",
        startDate=TOMORROW.replace(hour=14, minute=0),
        duration=60,
        location="Conference Room A",
    )


@pytest.fixture
def auth_token():
    """Valid JWT access token for USER_ID=1."""
    from utils.jwt import create_access_token
    return create_access_token({"user_id": USER_ID})


@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


# ── Mock DB session ───────────────────────────────────────────────────────────

@pytest.fixture
def mock_session():
    """AsyncMock of SQLAlchemy AsyncSession."""
    session = AsyncMock()
    session.add = MagicMock()
    session.add_all = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    return session


# ── Mock LLM ─────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_llm_response():
    """Factory: returns a mock AIMessage with the given content."""
    def _make(content: str):
        msg = MagicMock()
        msg.content = content
        return msg
    return _make


@pytest.fixture
def patch_llm(mock_llm_response):
    """Patches flow.llm.model.ainvoke to return a controllable AIMessage."""
    with patch("flow.llm.model.ainvoke") as mock_invoke:
        mock_invoke.return_value = mock_llm_response('{"route": "message"}')
        yield mock_invoke
