"""
Risk classification for destructive operations (delete / update).

Risk levels
-----------
HIGH   – confirmation required before execution
MEDIUM – proceed but surface a warning in the response message
LOW    – proceed silently
"""

from enum import Enum
from typing import Optional
from models import Event


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


def assess_delete_risk(events: list[Event]) -> tuple[RiskLevel, str]:
    """
    Always HIGH when deleting ≥1 event so users cannot accidentally wipe data.
    Returns (level, human-readable reason).
    """
    if not events:
        return RiskLevel.LOW, "No events to delete."

    mandatory_titles = [
        e.title for e in events
        if getattr(e, "priority", None) == "mandatory"
           or getattr(e, "flexibility", None) == "fixed"
    ]

    if mandatory_titles:
        reason = (
            f"This will permanently delete {len(events)} event(s), "
            f"including mandatory/fixed event(s): {', '.join(mandatory_titles[:3])}."
        )
    else:
        reason = f"This will permanently delete {len(events)} event(s)."

    return RiskLevel.HIGH, reason


def assess_update_risk(events: list[Event], update_args: Optional[dict] = None) -> tuple[RiskLevel, str]:
    """
    HIGH when updating mandatory/fixed events or when updating many events at once (≥3).
    MEDIUM when updating optional events.
    """
    if not events:
        return RiskLevel.LOW, "No events to update."

    mandatory_titles = [
        e.title for e in events
        if getattr(e, "priority", None) == "mandatory"
           or getattr(e, "flexibility", None) == "fixed"
    ]

    if mandatory_titles:
        reason = (
            f"This will update mandatory/fixed event(s): {', '.join(mandatory_titles[:3])}."
        )
        return RiskLevel.HIGH, reason

    if len(events) >= 3:
        reason = f"This will update {len(events)} events at once."
        return RiskLevel.HIGH, reason

    return RiskLevel.MEDIUM, f"Updating {len(events)} event(s)."


def detect_ambiguity(events: list[Event], max_unambiguous: int = 5) -> Optional[str]:
    """
    Returns a warning string when the matched event list is suspiciously large
    (user may have been too vague).  Returns None when unambiguous.
    """
    if len(events) > max_unambiguous:
        return (
            f"Your request matched {len(events)} events — did you mean a specific one? "
            "Please clarify which event(s) you want to affect."
        )
    return None
