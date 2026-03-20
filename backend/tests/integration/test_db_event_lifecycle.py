"""
Integration tests — Event lifecycle via EventAdapter against a real PostgreSQL database.

Requires: pytest -m integration
"""

import pytest
from datetime import datetime, timedelta, timezone

pytestmark = pytest.mark.integration

NOW = datetime(2026, 3, 20, 10, 0, 0, tzinfo=timezone.utc)
TOMORROW = NOW + timedelta(days=1)


async def test_create_and_read_event(async_session, test_user):
    """create_event → get_event_by_event_id round-trip."""
    from adapter.event_adapter import EventAdapter
    from models import EventCreate

    adapter = EventAdapter(async_session)
    ec = EventCreate(
        title="Lifecycle Test",
        startDate=TOMORROW.replace(hour=9),
        duration=30,
        location="Lab",
    )
    created = await adapter.create_event(test_user.id, ec)

    assert created.id is not None
    assert created.title == "Lifecycle Test"

    fetched = await adapter.get_event_by_event_id(created.id)
    assert fetched.id == created.id
    assert fetched.title == "Lifecycle Test"
    assert fetched.location == "Lab"


async def test_update_event_fields(async_session, test_user):
    """Change title + location, verify persistence."""
    from adapter.event_adapter import EventAdapter
    from models import EventCreate, EventUpdate

    adapter = EventAdapter(async_session)
    ec = EventCreate(title="Old Title", startDate=TOMORROW.replace(hour=10), duration=45)
    event = await adapter.create_event(test_user.id, ec)

    updated = await adapter.update_event(
        event.id, test_user.id, EventUpdate(title="New Title", location="Board Room")
    )
    assert updated.title == "New Title"
    assert updated.location == "Board Room"

    # Verify persistence by re-fetching
    fetched = await adapter.get_event_by_event_id(event.id)
    assert fetched.title == "New Title"
    assert fetched.location == "Board Room"


async def test_delete_event_removes_it(async_session, test_user):
    """delete → get returns EventNotFoundError."""
    from adapter.event_adapter import EventAdapter
    from models import EventCreate
    from exceptions import EventNotFoundError

    adapter = EventAdapter(async_session)
    ec = EventCreate(title="To Be Deleted", startDate=TOMORROW.replace(hour=11), duration=30)
    event = await adapter.create_event(test_user.id, ec)

    deleted = await adapter.delete_event(event.id, test_user.id)
    assert deleted is True

    with pytest.raises(EventNotFoundError):
        await adapter.get_event_by_event_id(event.id)


async def test_date_range_query(async_session, test_user):
    """Create 3 events; date-range query returns only the 2 that overlap."""
    from adapter.event_adapter import EventAdapter
    from models import EventCreate

    adapter = EventAdapter(async_session)
    base = TOMORROW.replace(hour=8, minute=0, second=0, microsecond=0)

    for i in range(3):
        ec = EventCreate(
            title=f"Range Event {i}",
            startDate=base + timedelta(hours=i * 3),
            duration=60,
        )
        await adapter.create_event(test_user.id, ec)

    # Query range: 8am – 14pm; events at 8am and 11am qualify, 14am is at the boundary
    range_start = base  # 08:00
    range_end = base + timedelta(hours=5)  # 13:00
    results = await adapter.get_events_by_date_range(test_user.id, range_start, range_end)

    titles = [e.title for e in results]
    assert "Range Event 0" in titles  # 8am–9am ✓
    assert "Range Event 1" in titles  # 11am–12am ✓
    assert "Range Event 2" not in titles  # 14am–15am ✗


async def test_conflict_detection(async_session, test_user):
    """Overlapping time → check_event_conflict returns the conflicting event."""
    from adapter.event_adapter import EventAdapter
    from models import EventCreate

    adapter = EventAdapter(async_session)
    start = TOMORROW.replace(hour=14, minute=0, second=0, microsecond=0)
    end = start + timedelta(hours=1)

    ec = EventCreate(title="Existing Meeting", startDate=start, duration=60)
    existing = await adapter.create_event(test_user.id, ec)

    # A new event overlapping by 30 min
    overlap_start = start + timedelta(minutes=30)
    overlap_end = overlap_start + timedelta(hours=1)
    conflict = await adapter.check_event_conflict(test_user.id, overlap_start, overlap_end)

    assert conflict is not None
    assert conflict.id == existing.id
