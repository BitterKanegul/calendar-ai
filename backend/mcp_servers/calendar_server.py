"""
Calendar MCP Server

Wraps calendar operations and exposes them as standardized MCP tools.
Agents call these tools instead of importing EventAdapter directly,
enabling service portability (e.g. swapping to Google Calendar later
requires only changing this file).
"""
import logging
from datetime import datetime, timedelta

from fastmcp import FastMCP

from database import get_async_db_context_manager
from adapter.event_adapter import EventAdapter
from models import EventCreate, EventUpdate
from database.models.event import EventPriority, EventFlexibility, EventCategory

logger = logging.getLogger(__name__)

mcp = FastMCP("Calendar")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _event_to_dict(event) -> dict:
    """Serialize a Pydantic Event to a plain dict for MCP transport."""
    def _enum_val(v):
        return v.value if hasattr(v, "value") else str(v)

    return {
        "id": event.id,
        "title": event.title,
        "startDate": event.startDate.isoformat() if hasattr(event.startDate, "isoformat") else str(event.startDate),
        "endDate": event.endDate.isoformat() if hasattr(event.endDate, "isoformat") else str(event.endDate),
        "duration": event.duration,
        "location": event.location,
        "user_id": event.user_id,
        "priority": _enum_val(event.priority),
        "flexibility": _enum_val(event.flexibility),
        "category": _enum_val(event.category),
    }


# ---------------------------------------------------------------------------
# Read tools (used by current agents)
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_events(
    user_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """List calendar events for a user within an optional date range."""
    async with get_async_db_context_manager() as db:
        adapter = EventAdapter(db)
        events = await adapter.get_events_by_date_range(user_id, start_date, end_date)
        return [_event_to_dict(e) for e in events]


@mcp.tool()
async def check_conflicts(
    user_id: int,
    start_date: str,
    end_date: str,
    exclude_event_id: str | None = None,
) -> dict | None:
    """Check for a time conflict with existing events. Returns the conflicting event or null."""
    async with get_async_db_context_manager() as db:
        adapter = EventAdapter(db)
        conflict = await adapter.check_event_conflict(
            user_id,
            datetime.fromisoformat(start_date),
            datetime.fromisoformat(end_date),
            exclude_event_id,
        )
        return _event_to_dict(conflict) if conflict else None


# ---------------------------------------------------------------------------
# Write tools (used by the Planner Agent in PLAN-04)
# ---------------------------------------------------------------------------

@mcp.tool()
async def create_event(
    user_id: int,
    title: str,
    start_date: str,
    duration: int | None = None,
    location: str | None = None,
    priority: str = "optional",
    flexibility: str = "movable",
    category: str = "personal",
) -> dict:
    """Create a new calendar event."""
    event_data = EventCreate(
        title=title,
        startDate=datetime.fromisoformat(start_date),
        duration=duration,
        location=location,
        priority=EventPriority(priority),
        flexibility=EventFlexibility(flexibility),
        category=EventCategory(category),
    )
    async with get_async_db_context_manager() as db:
        adapter = EventAdapter(db)
        event = await adapter.create_event(user_id, event_data)
        return _event_to_dict(event)


@mcp.tool()
async def update_event(
    event_id: str,
    user_id: int,
    title: str | None = None,
    start_date: str | None = None,
    duration: int | None = None,
    location: str | None = None,
    priority: str | None = None,
    flexibility: str | None = None,
    category: str | None = None,
) -> dict:
    """Update an existing calendar event."""
    event_data = EventUpdate(
        title=title,
        startDate=datetime.fromisoformat(start_date) if start_date else None,
        duration=duration,
        location=location,
        priority=EventPriority(priority) if priority else None,
        flexibility=EventFlexibility(flexibility) if flexibility else None,
        category=EventCategory(category) if category else None,
    )
    async with get_async_db_context_manager() as db:
        adapter = EventAdapter(db)
        event = await adapter.update_event(event_id, user_id, event_data)
        return _event_to_dict(event)


@mcp.tool()
async def delete_event(event_id: str, user_id: int) -> bool:
    """Delete a calendar event."""
    async with get_async_db_context_manager() as db:
        adapter = EventAdapter(db)
        return await adapter.delete_event(event_id, user_id)
