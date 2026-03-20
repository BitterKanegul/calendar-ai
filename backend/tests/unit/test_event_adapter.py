"""Unit tests for EventAdapter — all DB calls are mocked."""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from adapter.event_adapter import EventAdapter
from models import EventCreate, EventUpdate, Event
from exceptions import EventNotFoundError, DatabaseError, EventPermissionError
from database.models.event import EventModel
from sqlalchemy.exc import SQLAlchemyError

NOW = datetime(2026, 3, 20, 14, 0, 0, tzinfo=timezone.utc)
END = NOW + timedelta(hours=1)
USER_ID = 1
EVENT_UUID = "aaaa-bbbb-cccc-dddd"


def make_db_event(title="Meeting", event_id=EVENT_UUID, user_id=USER_ID):
    ev = MagicMock(spec=EventModel)
    ev.event_id = event_id
    ev.title = title
    ev.startDate = NOW
    ev.endDate = END
    ev.location = "Room A"
    ev.user_id = user_id
    ev.priority = "optional"
    ev.flexibility = "movable"
    ev.category = "work"
    return ev


def make_adapter(session):
    return EventAdapter(session)


# ── create_event ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_event_success(mock_session):
    db_ev = make_db_event()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    adapter = make_adapter(mock_session)
    event_data = EventCreate(title="Meeting", startDate=NOW, duration=60)

    # Patch _convert_to_db_model to return our mock
    with patch.object(adapter, "_convert_to_db_model", return_value=db_ev), \
         patch.object(adapter, "_convert_to_model", return_value=MagicMock(spec=Event)):
        result = await adapter.create_event(USER_ID, event_data)

    mock_session.add.assert_called_once_with(db_ev)
    mock_session.commit.assert_awaited_once()
    assert result is not None


@pytest.mark.asyncio
async def test_create_event_db_error(mock_session):
    mock_session.commit = AsyncMock(side_effect=SQLAlchemyError("DB error"))
    mock_session.rollback = AsyncMock()
    adapter = make_adapter(mock_session)
    db_ev = make_db_event()

    with patch.object(adapter, "_convert_to_db_model", return_value=db_ev):
        with pytest.raises(DatabaseError):
            await adapter.create_event(USER_ID, EventCreate(title="x", startDate=NOW))

    mock_session.rollback.assert_awaited_once()


# ── get_event_by_event_id ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_event_by_event_id_found(mock_session):
    db_ev = make_db_event()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = db_ev
    mock_session.execute = AsyncMock(return_value=result_mock)
    adapter = make_adapter(mock_session)

    with patch.object(adapter, "_convert_to_model", return_value=MagicMock(spec=Event)) as conv:
        event = await adapter.get_event_by_event_id(EVENT_UUID)
    conv.assert_called_once_with(db_ev)


@pytest.mark.asyncio
async def test_get_event_by_event_id_not_found(mock_session):
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=result_mock)
    adapter = make_adapter(mock_session)

    with pytest.raises(EventNotFoundError):
        await adapter.get_event_by_event_id("nonexistent-uuid")


# ── get_events_by_user_id ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_events_by_user_id(mock_session):
    db_events = [make_db_event(title=f"Event {i}", event_id=f"uuid-{i}") for i in range(3)]
    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = db_events
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute = AsyncMock(return_value=result_mock)
    adapter = make_adapter(mock_session)

    fake_event = MagicMock(spec=Event)
    with patch.object(adapter, "_convert_to_model", return_value=fake_event):
        events = await adapter.get_events_by_user_id(USER_ID)

    assert len(events) == 3


# ── get_events_by_date_range ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_events_by_date_range(mock_session):
    db_events = [make_db_event()]
    result_mock = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = db_events
    result_mock.scalars.return_value = scalars_mock
    mock_session.execute = AsyncMock(return_value=result_mock)
    adapter = make_adapter(mock_session)

    with patch.object(adapter, "_convert_to_model", return_value=MagicMock(spec=Event)):
        events = await adapter.get_events_by_date_range(USER_ID, NOW, END)

    assert len(events) == 1


# ── update_event ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_event_success(mock_session):
    db_ev = make_db_event()
    updated_ev = make_db_event(title="Updated Meeting")

    # First execute (SELECT) returns db_ev; second execute (UPDATE) returns updated_ev
    sel_result = MagicMock()
    sel_result.scalar_one_or_none.return_value = db_ev
    upd_result = MagicMock()
    upd_result.scalar_one_or_none.return_value = updated_ev
    mock_session.execute = AsyncMock(side_effect=[sel_result, upd_result])
    mock_session.commit = AsyncMock()
    adapter = make_adapter(mock_session)
    event_data = EventUpdate(title="Updated Meeting")

    fake_event = MagicMock(spec=Event)
    with patch.object(adapter, "_convert_to_model", return_value=fake_event):
        result = await adapter.update_event(EVENT_UUID, USER_ID, event_data)

    mock_session.commit.assert_awaited_once()
    assert result == fake_event


@pytest.mark.asyncio
async def test_update_event_not_found(mock_session):
    sel_result = MagicMock()
    sel_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=sel_result)
    adapter = make_adapter(mock_session)

    with pytest.raises(EventNotFoundError):
        await adapter.update_event("nonexistent", USER_ID, EventUpdate(title="x"))


@pytest.mark.asyncio
async def test_update_event_wrong_user(mock_session):
    db_ev = make_db_event(user_id=999)
    sel_result = MagicMock()
    sel_result.scalar_one_or_none.return_value = db_ev
    mock_session.execute = AsyncMock(return_value=sel_result)
    adapter = make_adapter(mock_session)

    with pytest.raises(EventPermissionError):
        await adapter.update_event(EVENT_UUID, USER_ID, EventUpdate(title="x"))


# ── delete_event ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_event_success(mock_session):
    del_result = MagicMock()
    del_result.rowcount = 1
    mock_session.execute = AsyncMock(return_value=del_result)
    mock_session.commit = AsyncMock()
    adapter = make_adapter(mock_session)

    result = await adapter.delete_event(EVENT_UUID, USER_ID)
    assert result is True


@pytest.mark.asyncio
async def test_delete_event_not_found(mock_session):
    del_result = MagicMock()
    del_result.rowcount = 0
    mock_session.execute = AsyncMock(return_value=del_result)
    mock_session.rollback = AsyncMock()
    adapter = make_adapter(mock_session)

    result = await adapter.delete_event("nonexistent", USER_ID)
    assert result is False


# ── check_event_conflict ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_conflict_found(mock_session):
    db_ev = make_db_event()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = db_ev
    mock_session.execute = AsyncMock(return_value=result_mock)
    adapter = make_adapter(mock_session)

    fake_event = MagicMock(spec=Event)
    with patch.object(adapter, "_convert_to_model", return_value=fake_event):
        conflict = await adapter.check_event_conflict(USER_ID, NOW, END)

    assert conflict == fake_event


@pytest.mark.asyncio
async def test_check_conflict_none(mock_session):
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=result_mock)
    adapter = make_adapter(mock_session)

    conflict = await adapter.check_event_conflict(USER_ID, NOW, END)
    assert conflict is None
