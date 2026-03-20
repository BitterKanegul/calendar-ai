"""Unit tests for the conflict resolution slot finder algorithm."""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from flow.conflict_resolution_agent.slot_finder import find_available_slots

BASE_DATE = datetime(2026, 3, 20, tzinfo=timezone.utc)
USER_ID = 1


def make_event_dict(hour_start, hour_end, title="Busy"):
    start = BASE_DATE.replace(hour=hour_start, minute=0)
    end = BASE_DATE.replace(hour=hour_end, minute=0)
    return {
        "title": title,
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "user_id": USER_ID,
        "id": f"evt-{hour_start}",
        "priority": "optional",
        "flexibility": "movable",
        "category": "work",
    }


@pytest.mark.asyncio
async def test_empty_calendar_returns_slots():
    with patch("flow.conflict_resolution_agent.slot_finder.call_calendar_tool", new=AsyncMock(return_value=[])):
        slots = await find_available_slots(USER_ID, duration_minutes=60, preferred_time=BASE_DATE.replace(hour=9, minute=0))
    assert len(slots) > 0
    assert "start" in slots[0]
    assert "end" in slots[0]


@pytest.mark.asyncio
async def test_busy_block_is_skipped():
    """If 9:00–10:00 is busy, no slot starting at 9:00 should be returned."""
    busy = [make_event_dict(9, 10)]
    with patch("flow.conflict_resolution_agent.slot_finder.call_calendar_tool", new=AsyncMock(return_value=busy)):
        slots = await find_available_slots(USER_ID, duration_minutes=60, preferred_time=BASE_DATE.replace(hour=9, minute=0))
    starts = [s["start"] for s in slots]
    assert not any("T09:00" in s for s in starts)


@pytest.mark.asyncio
async def test_respects_business_hours():
    """All returned slots should be within 8 AM–10 PM."""
    with patch("flow.conflict_resolution_agent.slot_finder.call_calendar_tool", new=AsyncMock(return_value=[])):
        slots = await find_available_slots(USER_ID, duration_minutes=60, preferred_time=BASE_DATE.replace(hour=9, minute=0))
    for slot in slots:
        start_hour = datetime.fromisoformat(slot["start"]).hour
        end_hour = datetime.fromisoformat(slot["end"]).hour
        assert 8 <= start_hour < 22
        assert end_hour <= 22


@pytest.mark.asyncio
async def test_max_slots_limit():
    with patch("flow.conflict_resolution_agent.slot_finder.call_calendar_tool", new=AsyncMock(return_value=[])):
        slots = await find_available_slots(USER_ID, duration_minutes=30, preferred_time=BASE_DATE.replace(hour=9, minute=0), max_slots=3)
    assert len(slots) <= 3


@pytest.mark.asyncio
async def test_fully_packed_day_returns_no_slots_that_day():
    """Create busy blocks every hour 8AM–10PM — no slots should be returned for that day."""
    busy = [make_event_dict(h, h + 1) for h in range(8, 22)]
    with patch("flow.conflict_resolution_agent.slot_finder.call_calendar_tool", new=AsyncMock(return_value=busy)):
        slots = await find_available_slots(USER_ID, duration_minutes=60, preferred_time=BASE_DATE.replace(hour=9, minute=0))
    # None of the returned slots should fall on the packed day (2026-03-20)
    packed_date = BASE_DATE.date()
    for slot in slots:
        slot_date = datetime.fromisoformat(slot["start"]).date()
        assert slot_date != packed_date, f"Unexpected slot on packed day: {slot}"
