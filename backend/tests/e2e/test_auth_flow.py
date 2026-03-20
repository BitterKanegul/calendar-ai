"""
E2E tests — Authentication flow: register → login → refresh → /events/ guard.

Requires: pytest -m e2e
"""

import uuid
import pytest

pytestmark = pytest.mark.e2e


async def test_register_login_refresh(client):
    """
    Full auth flow:
    1. POST /auth/register → 200, returns access_token + refresh_token
    2. POST /auth/login with same creds → 200
    3. POST /auth/refresh → returns new access_token
    """
    email = f"flow-{uuid.uuid4().hex[:8]}@example.com"
    password = "flowpass123"

    # 1. Register
    resp = await client.post(
        "/auth/register",
        json={"name": "Flow User", "email": email, "password": password},
    )
    assert resp.status_code == 200
    reg_data = resp.json()
    assert "access_token" in reg_data
    assert "refresh_token" in reg_data

    # 2. Login
    resp = await client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200
    login_data = resp.json()
    assert "access_token" in login_data
    refresh_token = login_data.get("refresh_token", reg_data["refresh_token"])

    # 3. Refresh
    resp = await client.post(
        "/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert resp.status_code == 200
    refresh_data = resp.json()
    assert "access_token" in refresh_data
    # New token must differ from the old one
    assert refresh_data["access_token"] != login_data["access_token"]


async def test_login_wrong_password(client):
    """POST /auth/login with bad password → 401."""
    email = f"bad-{uuid.uuid4().hex[:8]}@example.com"

    # Register first
    await client.post(
        "/auth/register",
        json={"name": "Bad Pass", "email": email, "password": "rightpassword"},
    )

    resp = await client.post(
        "/auth/login",
        json={"email": email, "password": "wrongpassword"},
    )
    assert resp.status_code == 401


async def test_protected_endpoint_without_token(client):
    """GET /events/ without Authorization header → 401 or 403."""
    resp = await client.get("/events/")
    assert resp.status_code in (401, 403)
