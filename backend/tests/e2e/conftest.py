"""
E2E test fixtures — full running backend with real DB, Redis, and OpenAI API.

Run with:
    pytest -m e2e
"""

import os
import uuid
import pytest
import pytest_asyncio
from datetime import datetime, timezone
from httpx import AsyncClient, ASGITransport

pytestmark = pytest.mark.e2e

# ── Shared test credentials ───────────────────────────────────────────────────

TEST_EMAIL = f"e2e-{uuid.uuid4().hex[:8]}@example.com"
TEST_PASSWORD = "e2epassword123"
TEST_NAME = "E2E Test User"


@pytest_asyncio.fixture(scope="session")
async def client():
    """
    httpx.AsyncClient connected to the real FastAPI app.

    Requires: DATABASE_URL, SECRET_KEY, OPENAI_API_KEY, REDIS_URL set in the
    environment (or a .env.development file).
    """
    from main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(scope="session")
async def registered_user(client):
    """Register the shared E2E user once per session; return tokens."""
    resp = await client.post(
        "/auth/register",
        json={"name": TEST_NAME, "email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert resp.status_code == 200, f"Register failed: {resp.text}"
    data = resp.json()
    return {
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD,
        "access_token": data["access_token"],
        "refresh_token": data["refresh_token"],
    }


@pytest_asyncio.fixture(scope="session")
async def auth_headers(registered_user):
    """Bearer token headers for the E2E test user."""
    return {"Authorization": f"Bearer {registered_user['access_token']}"}


@pytest_asyncio.fixture
def today_str():
    """ISO date string for 'today' in the E2E context (2026-03-20)."""
    return "2026-03-20T10:00:00"


@pytest_asyncio.fixture
def assistant_payload(today_str):
    """Factory to build /assistant/ request body."""
    def _make(text: str):
        return {
            "text": text,
            "current_datetime": today_str,
            "weekday": "Friday",
            "days_in_month": 31,
        }
    return _make
