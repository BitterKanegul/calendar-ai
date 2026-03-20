"""Tests for delete/update risk assessment and ambiguity detection."""
import pytest
from datetime import datetime, timezone

from flow.safety.risk_assessment import (
    RiskLevel,
    assess_delete_risk,
    assess_update_risk,
    detect_ambiguity,
)
from models import Event

NOW = datetime(2026, 3, 20, 14, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 3, 20, 15, 0, 0, tzinfo=timezone.utc)


def make_event(title="Meeting", priority="optional", flexibility="movable", idx=0):
    return Event(
        id=f"evt-{idx}",
        title=title,
        startDate=NOW,
        endDate=END,
        user_id=1,
        priority=priority,
        flexibility=flexibility,
        category="work",
    )


# ── Delete risk ───────────────────────────────────────────────────────────────

def test_delete_risk_empty_list():
    level, reason = assess_delete_risk([])
    assert level == RiskLevel.LOW

def test_delete_risk_one_event_is_high():
    level, reason = assess_delete_risk([make_event()])
    assert level == RiskLevel.HIGH

def test_delete_risk_mandatory_event_mentions_title():
    ev = make_event(title="Board Meeting", priority="mandatory")
    level, reason = assess_delete_risk([ev])
    assert level == RiskLevel.HIGH
    assert "Board Meeting" in reason

def test_delete_risk_multiple_events():
    events = [make_event(idx=i) for i in range(3)]
    level, reason = assess_delete_risk(events)
    assert level == RiskLevel.HIGH
    assert "3" in reason


# ── Update risk ───────────────────────────────────────────────────────────────

def test_update_risk_optional_events_medium():
    events = [make_event(priority="optional"), make_event(priority="optional", idx=1)]
    level, reason = assess_update_risk(events)
    assert level == RiskLevel.MEDIUM

def test_update_risk_mandatory_event_high():
    ev = make_event(priority="mandatory")
    level, reason = assess_update_risk([ev])
    assert level == RiskLevel.HIGH
    assert "mandatory" in reason.lower() or "Meeting" in reason

def test_update_risk_fixed_flexibility_high():
    ev = make_event(flexibility="fixed")
    level, reason = assess_update_risk([ev])
    assert level == RiskLevel.HIGH

def test_update_risk_three_events_high():
    events = [make_event(idx=i) for i in range(3)]
    level, reason = assess_update_risk(events)
    assert level == RiskLevel.HIGH


# ── Ambiguity ─────────────────────────────────────────────────────────────────

def test_ambiguity_below_threshold_none():
    events = [make_event(idx=i) for i in range(3)]
    assert detect_ambiguity(events) is None

def test_ambiguity_above_threshold_warning():
    events = [make_event(idx=i) for i in range(6)]
    warning = detect_ambiguity(events)
    assert warning is not None
    assert "6" in warning
