"""
Slot finder utility: finds available calendar slots for rescheduling.

Given a user_id, desired duration, and a preferred datetime, scans business
hours (8 AM – 10 PM) in 30-minute increments over a search window and returns
up to `max_slots` free slots sorted by proximity to the preferred time.
"""
from datetime import datetime, timedelta
from typing import Optional
from ..mcp_client import call_calendar_tool

BUSINESS_START_HOUR = 8   # 8 AM
BUSINESS_END_HOUR = 22    # 10 PM
SLOT_GRANULARITY_MINUTES = 30
DEFAULT_SEARCH_DAYS = 7
DEFAULT_MAX_SLOTS = 5


async def find_available_slots(
    user_id: int,
    duration_minutes: int,
    preferred_time: datetime,
    exclude_event_id: Optional[str] = None,
    search_days: int = DEFAULT_SEARCH_DAYS,
    max_slots: int = DEFAULT_MAX_SLOTS,
) -> list[dict]:
    """
    Find available time slots for an event.

    Returns a list of dicts: [{"start": ISO str, "end": ISO str}, ...]
    sorted by proximity to preferred_time.
    """
    # Search window: start at beginning of preferred_time's day
    search_start = preferred_time.replace(hour=0, minute=0, second=0, microsecond=0)
    search_end = search_start + timedelta(days=search_days)

    # Fetch existing events in range
    try:
        events = await call_calendar_tool("list_events", {
            "user_id": user_id,
            "start_date": search_start.isoformat(),
            "end_date": search_end.isoformat(),
        }) or []
    except Exception:
        events = []

    # Build list of (busy_start, busy_end) intervals, excluding the event being rescheduled
    busy_intervals: list[tuple[datetime, datetime]] = []
    for ev in events:
        if exclude_event_id and ev.get("id") == exclude_event_id:
            continue
        try:
            s = datetime.fromisoformat(ev["startDate"])
            e = datetime.fromisoformat(ev["endDate"])
            busy_intervals.append((s, e))
        except (KeyError, ValueError):
            continue

    duration = timedelta(minutes=duration_minutes)
    available_slots: list[dict] = []

    # Scan each day in the search window
    current_day = search_start
    while current_day < search_end and len(available_slots) < max_slots * 3:
        day_start = current_day.replace(hour=BUSINESS_START_HOUR, minute=0, second=0, microsecond=0)
        day_end = current_day.replace(hour=BUSINESS_END_HOUR, minute=0, second=0, microsecond=0)

        candidate = day_start
        while candidate + duration <= day_end:
            candidate_end = candidate + duration

            # Check if this slot overlaps any busy interval
            conflict = any(
                candidate < busy_end and candidate_end > busy_start
                for busy_start, busy_end in busy_intervals
            )

            if not conflict:
                available_slots.append({
                    "start": candidate.isoformat(),
                    "end": candidate_end.isoformat(),
                })

            candidate += timedelta(minutes=SLOT_GRANULARITY_MINUTES)

        current_day += timedelta(days=1)

    # Sort by proximity to preferred_time and return top max_slots
    available_slots.sort(key=lambda s: abs(
        (datetime.fromisoformat(s["start"]) - preferred_time).total_seconds()
    ))

    return available_slots[:max_slots]
