"""
Conflict Resolution Tools for LangChain agents.

These tools help detect conflicts and suggest alternative meeting times.
"""

import logging
from typing import Optional, List
from datetime import datetime, timedelta
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from adapter.event_adapter import EventAdapter
from database import get_async_db_context_manager
from models import Event

logger = logging.getLogger(__name__)


class CheckConflictInput(BaseModel):
    """Input schema for check_conflict tool."""
    startDate: datetime = Field(..., description="Start date/time to check for conflicts")
    endDate: datetime = Field(..., description="End date/time to check for conflicts")
    exclude_event_id: Optional[str] = Field(None, description="Event ID to exclude from conflict check (useful for updates)")


class FindFreeSlotsInput(BaseModel):
    """Input schema for find_free_slots tool."""
    startDate: datetime = Field(..., description="Start of date range to search for free slots")
    endDate: datetime = Field(..., description="End of date range to search for free slots")
    duration_minutes: int = Field(..., description="Required duration in minutes")
    preferred_times: Optional[List[str]] = Field(None, description="Preferred times in HH:MM format (e.g., ['09:00', '14:00'])")
    buffer_minutes: Optional[int] = Field(15, description="Buffer time in minutes between meetings")


class SuggestAlternativeTimesInput(BaseModel):
    """Input schema for suggest_alternative_times tool."""
    requested_startDate: datetime = Field(..., description="Original requested start time")
    requested_endDate: datetime = Field(..., description="Original requested end time")
    duration_minutes: int = Field(..., description="Required duration in minutes")
    search_window_days: Optional[int] = Field(7, description="Number of days forward to search")
    max_suggestions: Optional[int] = Field(3, description="Maximum number of suggestions to return")


def _event_to_dict(event: Event) -> dict:
    """Convert Event model to dictionary."""
    return {
        "event_id": event.id,
        "title": event.title,
        "startDate": event.startDate.isoformat() if event.startDate else None,
        "endDate": event.endDate.isoformat() if event.endDate else None,
        "location": event.location,
        "duration": event.duration
    }


def _calculate_conflict_type(requested_start: datetime, requested_end: datetime, 
                            existing_start: datetime, existing_end: datetime) -> str:
    """Determine the type of conflict."""
    if requested_start == existing_start and requested_end == existing_end:
        return "exact_match"
    elif (requested_start < existing_end and requested_end > existing_start):
        return "overlap"
    elif (requested_end == existing_start) or (requested_start == existing_end):
        return "adjacent"
    return "none"


async def check_conflict_impl(
    startDate: datetime,
    endDate: datetime,
    user_id: int,
    exclude_event_id: Optional[str] = None
) -> dict:
    """
    Check if a time slot conflicts with existing events.
    
    Returns all conflicting events, not just the first one.
    """
    logger.info(f"Checking conflicts for user {user_id} from {startDate} to {endDate}")
    
    try:
        async with get_async_db_context_manager() as db:
            adapter = EventAdapter(db)
            
            # Get all events in the date range
            events = await adapter.get_events_by_date_range(
                user_id=user_id,
                start_date=startDate - timedelta(days=1),  # Expand range slightly
                end_date=endDate + timedelta(days=1)
            )
            
            conflicting_events = []
            conflict_types = []
            
            for event in events:
                if exclude_event_id and event.id == exclude_event_id:
                    continue
                    
                conflict_type = _calculate_conflict_type(
                    startDate, endDate,
                    event.startDate, event.endDate
                )
                
                if conflict_type != "none":
                    conflicting_events.append(event)
                    conflict_types.append(conflict_type)
            
            return {
                "has_conflict": len(conflicting_events) > 0,
                "conflicting_events": [_event_to_dict(e) for e in conflicting_events],
                "conflict_count": len(conflicting_events),
                "conflict_types": conflict_types,
                "success": True
            }
    except Exception as e:
        logger.error(f"Error checking conflicts: {e}", exc_info=True)
        raise Exception(f"Failed to check conflicts: {str(e)}")


async def find_free_slots_impl(
    startDate: datetime,
    endDate: datetime,
    duration_minutes: int,
    user_id: int,
    preferred_times: Optional[List[str]] = None,
    buffer_minutes: int = 15
) -> dict:
    """
    Find available time slots in a date range.
    
    Considers buffer time between meetings and preferred times.
    """
    logger.info(f"Finding free slots for user {user_id}, duration: {duration_minutes} minutes")
    
    try:
        async with get_async_db_context_manager() as db:
            adapter = EventAdapter(db)
            
            # Get all events in the range
            events = await adapter.get_events_by_date_range(
                user_id=user_id,
                start_date=startDate,
                end_date=endDate
            )
            
            # Sort events by start time
            events.sort(key=lambda e: e.startDate)
            
            free_slots = []
            current_time = startDate
            
            # Default working hours: 9 AM - 5 PM
            working_start_hour = 9
            working_end_hour = 17
            
            for event in events:
                event_start = event.startDate
                event_end = event.endDate
                
                # Check if there's a free slot before this event
                if current_time < event_start:
                    slot_end = event_start - timedelta(minutes=buffer_minutes)
                    slot_duration = (slot_end - current_time).total_seconds() / 60
                    
                    if slot_duration >= duration_minutes:
                        # Check if within working hours
                        slot_hour = current_time.hour
                        if working_start_hour <= slot_hour < working_end_hour:
                            quality_score = _calculate_slot_quality(
                                current_time, preferred_times
                            )
                            free_slots.append({
                                "startDate": current_time.isoformat(),
                                "endDate": slot_end.isoformat(),
                                "duration_minutes": int(slot_duration),
                                "quality_score": quality_score
                            })
                
                # Move current_time to after this event (with buffer)
                current_time = max(current_time, event_end + timedelta(minutes=buffer_minutes))
            
            # Check for free slot after last event
            if current_time < endDate:
                slot_end = min(endDate, current_time + timedelta(minutes=duration_minutes))
                slot_duration = (slot_end - current_time).total_seconds() / 60
                
                if slot_duration >= duration_minutes:
                    slot_hour = current_time.hour
                    if working_start_hour <= slot_hour < working_end_hour:
                        quality_score = _calculate_slot_quality(
                            current_time, preferred_times
                        )
                        free_slots.append({
                            "startDate": current_time.isoformat(),
                            "endDate": slot_end.isoformat(),
                            "duration_minutes": int(slot_duration),
                            "quality_score": quality_score
                        })
            
            # Sort by quality score (best first)
            free_slots.sort(key=lambda x: x["quality_score"], reverse=True)
            
            return {
                "free_slots": free_slots,
                "count": len(free_slots),
                "success": True
            }
    except Exception as e:
        logger.error(f"Error finding free slots: {e}", exc_info=True)
        raise Exception(f"Failed to find free slots: {str(e)}")


def _calculate_slot_quality(slot_time: datetime, preferred_times: Optional[List[str]]) -> float:
    """Calculate quality score for a time slot (0-1)."""
    score = 0.5  # Base score
    
    # Prefer morning times (9-12)
    if 9 <= slot_time.hour < 12:
        score += 0.2
    
    # Prefer afternoon times (14-16)
    elif 14 <= slot_time.hour < 16:
        score += 0.2
    
    # Avoid lunch time (12-13)
    if 12 <= slot_time.hour < 13:
        score -= 0.3
    
    # Check preferred times
    if preferred_times:
        slot_time_str = slot_time.strftime("%H:%M")
        if slot_time_str in preferred_times:
            score += 0.3
    
    return min(1.0, max(0.0, score))


async def suggest_alternative_times_impl(
    requested_startDate: datetime,
    requested_endDate: datetime,
    duration_minutes: int,
    user_id: int,
    search_window_days: int = 7,
    max_suggestions: int = 3
) -> dict:
    """
    Suggest alternative times for a conflicting event.
    
    Searches forward from requested time and provides ranked suggestions.
    """
    logger.info(f"Suggesting alternatives for user {user_id}, duration: {duration_minutes} minutes")
    
    try:
        # Calculate search range
        search_start = requested_startDate
        search_end = requested_startDate + timedelta(days=search_window_days)
        
        # Find free slots
        free_slots_result = await find_free_slots_impl(
            startDate=search_start,
            endDate=search_end,
            duration_minutes=duration_minutes,
            user_id=user_id,
            buffer_minutes=15
        )
        
        free_slots = free_slots_result.get("free_slots", [])
        
        # Convert to suggestions format
        suggestions = []
        for slot in free_slots[:max_suggestions]:
            slot_start = datetime.fromisoformat(slot["startDate"])
            slot_end = slot_start + timedelta(minutes=duration_minutes)
            
            # Generate reason
            hours_diff = (slot_start - requested_startDate).total_seconds() / 3600
            if hours_diff < 1:
                reason = "Available within the next hour"
            elif hours_diff < 24:
                reason = f"Available {int(hours_diff)} hours later"
            else:
                days_diff = int(hours_diff / 24)
                reason = f"Available {days_diff} day(s) later"
            
            suggestions.append({
                "startDate": slot_start.isoformat(),
                "endDate": slot_end.isoformat(),
                "reason": reason,
                "confidence": slot["quality_score"]
            })
        
        # If no suggestions found, try next day same time
        if not suggestions:
            next_day = requested_startDate + timedelta(days=1)
            next_day_end = next_day + timedelta(minutes=duration_minutes)
            
            # Check if this time is free
            conflict_check = await check_conflict_impl(
                startDate=next_day,
                endDate=next_day_end,
                user_id=user_id
            )
            
            if not conflict_check["has_conflict"]:
                suggestions.append({
                    "startDate": next_day.isoformat(),
                    "endDate": next_day_end.isoformat(),
                    "reason": "Available tomorrow at the same time",
                    "confidence": 0.7
                })
        
        return {
            "suggestions": suggestions,
            "count": len(suggestions),
            "original_time": requested_startDate.isoformat(),
            "success": True
        }
    except Exception as e:
        logger.error(f"Error suggesting alternatives: {e}", exc_info=True)
        raise Exception(f"Failed to suggest alternatives: {str(e)}")


# Factory functions for tools
def check_conflict_tool_factory(user_id: int) -> StructuredTool:
    """Create check_conflict tool bound to user_id."""
    async def check_conflict_with_user_id(
        startDate: datetime,
        endDate: datetime,
        exclude_event_id: Optional[str] = None
    ) -> dict:
        return await check_conflict_impl(
            startDate=startDate,
            endDate=endDate,
            user_id=user_id,
            exclude_event_id=exclude_event_id
        )
    
    return StructuredTool.from_function(
        func=check_conflict_with_user_id,
        name="check_conflict",
        description="""Check if a time slot conflicts with existing events.
        
        Returns all conflicting events and conflict types (overlap, exact_match, adjacent).
        Use this to verify if a proposed time is available.
        """,
        args_schema=CheckConflictInput,
    )


def find_free_slots_tool_factory(user_id: int) -> StructuredTool:
    """Create find_free_slots tool bound to user_id."""
    async def find_free_slots_with_user_id(
        startDate: datetime,
        endDate: datetime,
        duration_minutes: int,
        preferred_times: Optional[List[str]] = None,
        buffer_minutes: int = 15
    ) -> dict:
        return await find_free_slots_impl(
            startDate=startDate,
            endDate=endDate,
            duration_minutes=duration_minutes,
            user_id=user_id,
            preferred_times=preferred_times,
            buffer_minutes=buffer_minutes
        )
    
    return StructuredTool.from_function(
        func=find_free_slots_with_user_id,
        name="find_free_slots",
        description="""Find available time slots in a date range.
        
        Considers buffer time between meetings and preferred times.
        Returns slots ranked by quality score.
        """,
        args_schema=FindFreeSlotsInput,
    )


def suggest_alternative_times_tool_factory(user_id: int) -> StructuredTool:
    """Create suggest_alternative_times tool bound to user_id."""
    async def suggest_alternatives_with_user_id(
        requested_startDate: datetime,
        requested_endDate: datetime,
        duration_minutes: int,
        search_window_days: int = 7,
        max_suggestions: int = 3
    ) -> dict:
        return await suggest_alternative_times_impl(
            requested_startDate=requested_startDate,
            requested_endDate=requested_endDate,
            duration_minutes=duration_minutes,
            user_id=user_id,
            search_window_days=search_window_days,
            max_suggestions=max_suggestions
        )
    
    return StructuredTool.from_function(
        func=suggest_alternatives_with_user_id,
        name="suggest_alternative_times",
        description="""Suggest alternative times for a conflicting event.
        
        Searches forward from the requested time and provides ranked suggestions
        with reasons and confidence scores. Use this when conflicts are detected.
        """,
        args_schema=SuggestAlternativeTimesInput,
    )
