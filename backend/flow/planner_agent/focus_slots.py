"""
Focus Slot Management

Converts recurring focus slot templates (e.g., "study every weekday afternoon")
into concrete events via the optimizer, then creates them via MCP.

Focus slots are the building block for "plan my week"-style requests.
"""
from dataclasses import dataclass, field
from typing import Optional
from .optimizer import optimize_templates
from ..mcp_client import call_calendar_tool


@dataclass
class FocusSlot:
    """A recurring time block reserved for a specific activity."""
    title: str
    duration_minutes: int
    preferred_time: str          # "morning", "afternoon", "evening", "any"
    days: list[str]              # ["weekdays"], ["monday","wednesday","friday"], etc.
    category: str = "personal"
    priority: str = "optional"
    flexibility: str = "movable"
    location: Optional[str] = None


async def materialize_focus_slots(
    user_id: int,
    focus_slots: list[FocusSlot],
    date_range_start: str,
    date_range_end: str,
) -> list[dict]:
    """
    Place focus slots in the calendar and create them via MCP.

    Steps:
    1. Fetch existing events in the date range.
    2. Use optimizer to find free slots for each focus slot template.
    3. Create each placed event via MCP.

    Returns a list of created event dicts.
    """
    # Fetch existing events
    try:
        existing = await call_calendar_tool("list_events", {
            "user_id": user_id,
            "start_date": date_range_start,
            "end_date": date_range_end,
        }) or []
    except Exception:
        existing = []

    # Convert FocusSlot dataclasses to optimizer template dicts
    templates = [
        {
            "title":        fs.title,
            "duration":     fs.duration_minutes,
            "preferred_time": fs.preferred_time,
            "days":         fs.days,
            "category":     fs.category,
            "priority":     fs.priority,
            "flexibility":  fs.flexibility,
            "location":     fs.location,
        }
        for fs in focus_slots
    ]

    placed = optimize_templates(templates, existing, date_range_start, date_range_end)

    created: list[dict] = []
    for ev in placed:
        try:
            result = await call_calendar_tool("create_event", {
                "user_id":     user_id,
                "title":       ev["title"],
                "start_date":  ev["startDate"],
                "duration":    ev["duration"],
                "location":    ev.get("location"),
                "priority":    ev.get("priority", "optional"),
                "flexibility": ev.get("flexibility", "movable"),
                "category":    ev.get("category", "personal"),
            })
            if result:
                created.append(result)
        except Exception:
            continue

    return created
