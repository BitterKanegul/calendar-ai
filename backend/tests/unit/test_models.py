"""Tests for Pydantic model validation."""
import pytest
from datetime import datetime, timezone
from pydantic import ValidationError

from models import (
    EventCreate, EventUpdate, Event, EventBase,
    UserCreate, UserRegister, UserUpdate,
    ProcessInput, SuccessfulListResponse, SuccessfulCreateResponse,
    ConfirmationRequiredResponse, PlanChange, ExtractedEmailEvent,
)
from database.models.event import EventPriority, EventFlexibility, EventCategory

NOW = datetime(2026, 3, 20, 14, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 3, 20, 15, 0, 0, tzinfo=timezone.utc)


# ── EventCreate ───────────────────────────────────────────────────────────────

def test_event_create_valid():
    e = EventCreate(title="Meeting", startDate=NOW, duration=60)
    assert e.title == "Meeting"
    assert e.duration == 60

def test_event_create_missing_title():
    with pytest.raises(ValidationError):
        EventCreate(startDate=NOW)

def test_event_create_missing_start_date():
    with pytest.raises(ValidationError):
        EventCreate(title="Meeting")

def test_event_create_invalid_priority():
    with pytest.raises(ValidationError):
        EventCreate(title="x", startDate=NOW, priority="super_urgent")

def test_event_create_default_enums():
    e = EventCreate(title="x", startDate=NOW)
    assert e.priority == EventPriority.OPTIONAL
    assert e.flexibility == EventFlexibility.MOVABLE
    assert e.category == EventCategory.PERSONAL

def test_event_create_with_location():
    e = EventCreate(title="x", startDate=NOW, location="Room A")
    assert e.location == "Room A"


# ── EventUpdate ───────────────────────────────────────────────────────────────

def test_event_update_all_optional():
    e = EventUpdate()
    assert e.title is None
    assert e.startDate is None
    assert e.duration is None

def test_event_update_partial():
    e = EventUpdate(title="New Title", duration=30)
    assert e.title == "New Title"
    assert e.duration == 30
    assert e.startDate is None


# ── UserCreate / UserRegister ─────────────────────────────────────────────────

def test_user_create_valid():
    u = UserCreate(user_id="uuid", name="Alice", email="alice@example.com", password="secret123")
    assert u.name == "Alice"

def test_user_create_short_password():
    with pytest.raises(ValidationError):
        UserCreate(user_id="uuid", name="Bob", email="bob@example.com", password="abc")

def test_user_create_invalid_email():
    with pytest.raises(ValidationError):
        UserCreate(user_id="uuid", name="Bob", email="not-an-email", password="secret123")

def test_user_register_valid():
    u = UserRegister(name="Alice", email="alice@example.com", password="secret123")
    assert u.email == "alice@example.com"


# ── ProcessInput ──────────────────────────────────────────────────────────────

def test_process_input_valid():
    p = ProcessInput(
        text="Schedule a meeting",
        current_datetime="2026-03-20T09:00:00",
        weekday="Friday",
        days_in_month=31,
    )
    assert p.text == "Schedule a meeting"


# ── Response models ───────────────────────────────────────────────────────────

def test_successful_list_response_shape():
    from models import Event
    e = Event(
        id="evt-1", title="Meet", startDate=NOW, endDate=END,
        user_id=1, priority="optional", flexibility="movable", category="work"
    )
    resp = SuccessfulListResponse(message="Here are your events", events=[e])
    assert resp.type == "list"
    assert len(resp.events) == 1

def test_confirmation_required_response():
    resp = ConfirmationRequiredResponse(
        message="Are you sure?",
        confirmation_type="delete_safety",
        events=[],
    )
    assert resp.type == "confirmation_required"
    assert resp.confirmation_type == "delete_safety"

def test_plan_change_optional_fields():
    pc = PlanChange(action="created")
    assert pc.event_title is None
    assert pc.event_start is None
    assert pc.detail is None

def test_extracted_email_event():
    e = ExtractedEmailEvent(title="Conference", confidence="high")
    assert e.confidence == "high"
    assert e.start_date is None
