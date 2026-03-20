"""
Schedule Optimizer

Deterministic algorithm for placing new events into a calendar around existing ones.
Used by plan_executor for `create_optimized` tasks — the LLM specifies *what* to
create and rough timing preferences; this module finds the actual free slots.

Algorithm:
  For each requested (day, template) pair:
  1. Collect busy intervals for that day (with a buffer around each).
  2. Scan the preferred time window in 30-minute increments.
  3. Return the first conflict-free slot.
  4. Add the newly placed event to the busy list so subsequent placements don't overlap.
"""
from datetime import datetime, timedelta, date
from typing import Optional

PREFERRED_TIME_WINDOWS: dict[str, tuple[int, int]] = {
    "morning":   (8, 12),
    "afternoon": (12, 18),
    "evening":   (18, 22),
    "any":       (8, 22),
}

SLOT_GRANULARITY_MINUTES = 30
DEFAULT_BUFFER_MINUTES = 15

WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _weekday_index(name: str) -> int:
    """Return 0-based weekday index (Monday=0)."""
    return WEEKDAY_NAMES.index(name.lower())


def _expand_days(days_spec: list[str]) -> set[int]:
    """Convert a days spec like ["weekdays"] or ["monday","friday"] to a set of weekday indices."""
    result: set[int] = set()
    for d in days_spec:
        d = d.lower()
        if d == "weekdays":
            result.update(range(5))
        elif d == "weekend":
            result.update([5, 6])
        elif d == "all":
            result.update(range(7))
        elif d in WEEKDAY_NAMES:
            result.add(_weekday_index(d))
    return result


def _busy_intervals_for_day(
    events: list[dict],
    target_date: date,
    buffer_minutes: int,
) -> list[tuple[datetime, datetime]]:
    """Extract (buffered) busy intervals from events list for a specific date."""
    buffer = timedelta(minutes=buffer_minutes)
    intervals: list[tuple[datetime, datetime]] = []
    for ev in events:
        try:
            start = datetime.fromisoformat(ev.get("startDate", ""))
            end = datetime.fromisoformat(ev.get("endDate", ""))
        except (ValueError, TypeError):
            continue
        if start.date() == target_date:
            intervals.append((start - buffer, end + buffer))
    return sorted(intervals)


def place_event_template(
    template: dict,
    existing_events: list[dict],
    target_date: date,
    buffer_minutes: int = DEFAULT_BUFFER_MINUTES,
) -> Optional[dict]:
    """
    Find the best free slot for a single event template on target_date.

    Returns a concrete event dict with startDate/endDate, or None if no slot found.
    """
    preferred = template.get("preferred_time", "any")
    start_hour, end_hour = PREFERRED_TIME_WINDOWS.get(preferred, (8, 22))
    duration = timedelta(minutes=template.get("duration", 60))

    busy = _busy_intervals_for_day(existing_events, target_date, buffer_minutes)

    # Use a timezone-naive datetime anchored to target_date
    window_start = datetime(target_date.year, target_date.month, target_date.day, start_hour, 0, 0)
    window_end   = datetime(target_date.year, target_date.month, target_date.day, end_hour,   0, 0)

    candidate = window_start
    while candidate + duration <= window_end:
        candidate_end = candidate + duration
        conflict = any(
            candidate < busy_end and candidate_end > busy_start
            for busy_start, busy_end in busy
        )
        if not conflict:
            return {
                "title":       template.get("title", "Event"),
                "startDate":   candidate.isoformat(),
                "endDate":     candidate_end.isoformat(),
                "duration":    template.get("duration", 60),
                "location":    template.get("location"),
                "priority":    template.get("priority", "optional"),
                "flexibility": template.get("flexibility", "movable"),
                "category":    template.get("category", "personal"),
            }
        candidate += timedelta(minutes=SLOT_GRANULARITY_MINUTES)

    return None


def optimize_templates(
    templates: list[dict],
    existing_events: list[dict],
    date_range_start: str,
    date_range_end: str,
    buffer_minutes: int = DEFAULT_BUFFER_MINUTES,
) -> list[dict]:
    """
    Place all event templates in the best available slots within the date range.

    Each template should have:
      - title, duration, preferred_time, days (list), category, priority, flexibility

    Returns a list of concrete event dicts (startDate/endDate filled in).
    Mutates the working event list so later templates don't overlap earlier ones.
    """
    try:
        range_start = datetime.fromisoformat(date_range_start).date()
        range_end   = datetime.fromisoformat(date_range_end).date()
    except (ValueError, TypeError):
        return []

    # Work on a copy so we can append placed events without mutating caller's list
    working_events = list(existing_events)
    placed: list[dict] = []

    # Build sorted list of days in range
    days_in_range: list[date] = []
    current = range_start
    while current <= range_end:
        days_in_range.append(current)
        current += timedelta(days=1)

    for template in templates:
        days_spec = template.get("days", ["all"])
        allowed_weekdays = _expand_days(days_spec) if days_spec else set(range(7))

        for day in days_in_range:
            if day.weekday() not in allowed_weekdays:
                continue

            result = place_event_template(template, working_events, day, buffer_minutes)
            if result:
                placed.append(result)
                # Add to working events so the next template won't collide
                working_events.append({
                    "startDate": result["startDate"],
                    "endDate":   result["endDate"],
                })

    return placed
