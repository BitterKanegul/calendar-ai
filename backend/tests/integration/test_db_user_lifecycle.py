"""
Integration tests — User lifecycle via UserAdapter against a real PostgreSQL database.

Requires: pytest -m integration
"""

import uuid
import pytest

pytestmark = pytest.mark.integration


async def test_create_and_read_user(async_session):
    """create_user → get_user_by_id round-trip."""
    from adapter.user_adapter import UserAdapter
    from models import UserCreate
    from utils.password import hash_password

    adapter = UserAdapter(async_session)
    user_data = UserCreate(
        user_id=str(uuid.uuid4()),
        name="Alice",
        email=f"alice-{uuid.uuid4().hex[:6]}@example.com",
        password=hash_password("password123"),
    )
    created = await adapter.create_user(user_data)

    assert created is not None
    assert created.name == "Alice"

    fetched = await adapter.get_user_by_id(created.id)
    assert fetched is not None
    assert fetched.email == user_data.email


async def test_duplicate_email_raises(async_session):
    """Creating two users with the same email raises HTTPException 400."""
    from fastapi import HTTPException
    from adapter.user_adapter import UserAdapter
    from models import UserCreate
    from utils.password import hash_password

    adapter = UserAdapter(async_session)
    shared_email = f"dup-{uuid.uuid4().hex[:6]}@example.com"

    user_data = UserCreate(
        user_id=str(uuid.uuid4()),
        name="Bob",
        email=shared_email,
        password=hash_password("password123"),
    )
    await adapter.create_user(user_data)

    duplicate = UserCreate(
        user_id=str(uuid.uuid4()),
        name="Bob2",
        email=shared_email,
        password=hash_password("password123"),
    )
    with pytest.raises(HTTPException) as exc_info:
        await adapter.create_user(duplicate)
    assert exc_info.value.status_code == 400


async def test_update_user_email(async_session):
    """Update a user's email and verify it persists."""
    from adapter.user_adapter import UserAdapter
    from models import UserCreate, UserUpdate
    from utils.password import hash_password

    adapter = UserAdapter(async_session)
    user_data = UserCreate(
        user_id=str(uuid.uuid4()),
        name="Charlie",
        email=f"charlie-{uuid.uuid4().hex[:6]}@example.com",
        password=hash_password("password123"),
    )
    user = await adapter.create_user(user_data)

    new_email = f"charlie-updated-{uuid.uuid4().hex[:6]}@example.com"
    updated = await adapter.update_user(user.id, UserUpdate(email=new_email))

    assert updated is not None
    assert updated.email == new_email


async def test_delete_user_cascades_events(async_session):
    """Deleting a user removes their events (ON DELETE CASCADE)."""
    from adapter.user_adapter import UserAdapter
    from adapter.event_adapter import EventAdapter
    from models import UserCreate, EventCreate
    from utils.password import hash_password
    from datetime import datetime, timedelta, timezone

    user_adapter = UserAdapter(async_session)
    event_adapter = EventAdapter(async_session)

    tomorrow = datetime(2026, 3, 21, 9, 0, 0, tzinfo=timezone.utc)

    user_data = UserCreate(
        user_id=str(uuid.uuid4()),
        name="Dave",
        email=f"dave-{uuid.uuid4().hex[:6]}@example.com",
        password=hash_password("password123"),
    )
    user = await user_adapter.create_user(user_data)

    ec = EventCreate(title="Dave's Meeting", startDate=tomorrow, duration=30)
    event = await event_adapter.create_event(user.id, ec)

    # Delete the user — should cascade to events
    deleted = await user_adapter.delete_user(user.id)
    assert deleted is True

    # Event should be gone too
    from exceptions import EventNotFoundError
    with pytest.raises(EventNotFoundError):
        await event_adapter.get_event_by_event_id(event.id)
