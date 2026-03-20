"""Unit tests for EventService — adapter is mocked."""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException

from services.event_service import EventService
from models import Event, EventCreate, EventUpdate
from exceptions import EventNotFoundError, EventPermissionError

NOW = datetime(2026, 3, 20, 14, 0, 0, tzinfo=timezone.utc)
END = NOW + timedelta(hours=1)
USER_ID = 1
OTHER_USER_ID = 99
EVENT_UUID = "aaaa-bbbb-cccc-dddd"


def make_service():
    adapter = AsyncMock()
    service = EventService(adapter)
    return service, adapter


def make_event(user_id=USER_ID):
    return Event(
        id=EVENT_UUID, title="Meeting",
        startDate=NOW, endDate=END,
        user_id=user_id, priority="optional",
        flexibility="movable", category="work",
    )


def make_valid_token(user_id=USER_ID):
    from utils.jwt import create_access_token
    return create_access_token({"user_id": user_id})


# ── create_event ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_event_calls_adapter():
    service, adapter = make_service()
    adapter.create_event = AsyncMock(return_value=make_event())
    token = make_valid_token()
    result = await service.create_event(token, EventCreate(title="x", startDate=NOW))
    adapter.create_event.assert_awaited_once()
    assert result is not None


# ── get_event ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_event_owned_by_user():
    service, adapter = make_service()
    adapter.get_event_by_event_id = AsyncMock(return_value=make_event(USER_ID))
    token = make_valid_token(USER_ID)
    result = await service.get_event(token, EVENT_UUID)
    assert result.id == EVENT_UUID


@pytest.mark.asyncio
async def test_get_event_not_owned_raises_403():
    service, adapter = make_service()
    adapter.get_event_by_event_id = AsyncMock(return_value=make_event(OTHER_USER_ID))
    token = make_valid_token(USER_ID)
    with pytest.raises(HTTPException) as exc:
        await service.get_event(token, EVENT_UUID)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_event_not_found_raises_404():
    service, adapter = make_service()
    adapter.get_event_by_event_id = AsyncMock(side_effect=EventNotFoundError("not found"))
    token = make_valid_token()
    with pytest.raises(HTTPException) as exc:
        await service.get_event(token, "bad-uuid")
    assert exc.value.status_code == 404


# ── get_user_events ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_user_events_pagination():
    service, adapter = make_service()
    events = [make_event() for _ in range(3)]
    adapter.get_events_by_user_id = AsyncMock(return_value=events)
    token = make_valid_token()
    result = await service.get_user_events(token, limit=10, offset=0)
    adapter.get_events_by_user_id.assert_awaited_once_with(USER_ID, limit=10, offset=0)
    assert len(result) == 3


# ── update_event ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_event_success():
    service, adapter = make_service()
    adapter.update_event = AsyncMock(return_value=make_event())
    token = make_valid_token()
    result = await service.update_event(token, EVENT_UUID, EventUpdate(title="New"))
    assert result is not None


@pytest.mark.asyncio
async def test_update_event_not_found_raises_404():
    service, adapter = make_service()
    adapter.update_event = AsyncMock(side_effect=EventNotFoundError("not found"))
    token = make_valid_token()
    with pytest.raises(HTTPException) as exc:
        await service.update_event(token, "bad", EventUpdate(title="x"))
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_event_permission_denied_raises_403():
    service, adapter = make_service()
    adapter.update_event = AsyncMock(side_effect=EventPermissionError("denied"))
    token = make_valid_token()
    with pytest.raises(HTTPException) as exc:
        await service.update_event(token, EVENT_UUID, EventUpdate(title="x"))
    assert exc.value.status_code == 403


# ── delete_event ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_event_success():
    service, adapter = make_service()
    adapter.delete_event = AsyncMock(return_value=True)
    token = make_valid_token()
    result = await service.delete_event(token, EVENT_UUID)
    assert result == {"message": "Event deleted successfully"}


@pytest.mark.asyncio
async def test_delete_event_not_found_raises_404():
    service, adapter = make_service()
    adapter.delete_event = AsyncMock(return_value=False)
    token = make_valid_token()
    with pytest.raises(HTTPException) as exc:
        await service.delete_event(token, "bad-uuid")
    assert exc.value.status_code == 404


# ── delete_multiple_events ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_multiple_events_success():
    service, adapter = make_service()
    adapter.delete_multiple_events = AsyncMock(return_value=True)
    token = make_valid_token()
    result = await service.delete_multiple_events(token, ["id1", "id2"])
    assert "2" in result["message"]


@pytest.mark.asyncio
async def test_delete_multiple_events_empty_list():
    service, adapter = make_service()
    token = make_valid_token()
    with pytest.raises(HTTPException) as exc:
        await service.delete_multiple_events(token, [])
    assert exc.value.status_code == 400
