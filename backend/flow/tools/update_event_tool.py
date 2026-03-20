"""
Update Event Tool for LangChain agents.

This tool allows LLM agents to update calendar events with proper validation
and authorization checks.
"""

import logging
from typing import Optional
from datetime import datetime
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from adapter.event_adapter import EventAdapter
from database import get_async_db_context_manager
from models import EventUpdate, Event
from exceptions import EventNotFoundError, EventPermissionError

logger = logging.getLogger(__name__)


class UpdateEventInput(BaseModel):
    """Input schema for the update_event tool."""
    
    event_id: str = Field(..., description="The UUID of the event to update")
    title: Optional[str] = Field(None, description="New title for the event")
    startDate: Optional[datetime] = Field(
        None,
        description="New start date/time for the event (ISO 8601 format: YYYY-MM-DDTHH:MM:SS±HH:MM)"
    )
    duration: Optional[int] = Field(
        None,
        description="New duration in minutes. If provided along with startDate, endDate will be calculated. If only duration is provided, it will be added to the existing startDate."
    )
    location: Optional[str] = Field(None, description="New location for the event")

    class Config:
        json_schema_extra = {
            "example": {
                "event_id": "123e4567-e89b-12d3-a456-426614174000",
                "title": "Updated Meeting Title",
                "startDate": "2025-03-20T15:00:00-05:00",
                "duration": 60,
                "location": "New Location"
            }
        }


def _event_to_dict(event: Event) -> dict:
    """Convert Event model to dictionary."""
    return {
        "event_id": event.id,
        "title": event.title,
        "startDate": event.startDate.isoformat() if event.startDate else None,
        "endDate": event.endDate.isoformat() if event.endDate else None,
        "location": event.location,
        "user_id": event.user_id,
        "duration": event.duration
    }


async def update_event_impl(
    event_id: str,
    user_id: int,
    title: Optional[str] = None,
    startDate: Optional[datetime] = None,
    duration: Optional[int] = None,
    location: Optional[str] = None
) -> dict:
    """
    Update a calendar event.
    
    Args:
        event_id: The UUID of the event to update
        user_id: User ID to verify ownership (required, injected from state)
        title: New title for the event (optional)
        startDate: New start date/time (optional)
        duration: New duration in minutes (optional)
        location: New location (optional)
    
    Returns:
        Dictionary with updated event details
    
    Raises:
        ValueError: If no update fields are provided
        EventNotFoundError: If event is not found
        EventPermissionError: If user doesn't own the event
        Exception: If event update fails
    """
    # Check if at least one field is being updated
    if all(field is None for field in [title, startDate, duration, location]):
        raise ValueError("At least one field (title, startDate, duration, or location) must be provided for update")
    
    logger.info(f"Updating event {event_id} for user {user_id}")
    
    try:
        # Create EventUpdate model
        event_update = EventUpdate(
            title=title,
            startDate=startDate,
            duration=duration,
            location=location
        )
        
        # Use adapter to update event
        async with get_async_db_context_manager() as db:
            adapter = EventAdapter(db)
            updated_event = await adapter.update_event(event_id, user_id, event_update)
            
            logger.info(f"Successfully updated event {event_id} for user {user_id}")
            
            return {
                "event": _event_to_dict(updated_event),
                "success": True,
                "message": f"Event {event_id} updated successfully"
            }
    except EventNotFoundError as e:
        logger.warning(f"Event not found: {event_id}")
        return {
            "event_id": event_id,
            "success": False,
            "message": f"Event {event_id} not found"
        }
    except EventPermissionError as e:
        logger.warning(f"Permission denied for event {event_id}: {e}")
        return {
            "event_id": event_id,
            "success": False,
            "message": f"You are not authorized to update event {event_id}"
        }
    except Exception as e:
        logger.error(f"Error updating event {event_id}: {e}", exc_info=True)
        raise Exception(f"Failed to update event: {str(e)}")


def update_event_tool_factory(user_id: int) -> StructuredTool:
    """
    Factory function to create an update_event tool bound to a specific user_id.
    
    Args:
        user_id: The user ID to inject into the tool
    
    Returns:
        A StructuredTool instance configured for the user
    """
    async def update_event_with_user_id(
        event_id: str,
        title: Optional[str] = None,
        startDate: Optional[datetime] = None,
        duration: Optional[int] = None,
        location: Optional[str] = None
    ) -> dict:
        """Update event with user_id injected."""
        return await update_event_impl(
            event_id=event_id,
            user_id=user_id,
            title=title,
            startDate=startDate,
            duration=duration,
            location=location
        )
    
    return StructuredTool.from_function(
        func=update_event_with_user_id,
        name="update_event",
        description="""Update an existing calendar event.
        
        Use this tool when the user wants to modify, change, or update an event.
        Provide the event_id of the event to update, and at least one field to change:
        - title: Change the event title
        - startDate: Change when the event starts
        - duration: Change how long the event lasts (in minutes)
        - location: Change where the event takes place
        
        You can update multiple fields at once. If duration is provided with startDate,
        the endDate will be calculated automatically. If only duration is provided,
        it will be added to the existing startDate.
        """,
        args_schema=UpdateEventInput,
    )


# Note: Use update_event_tool_factory(user_id) to create a tool instance bound to a user_id.
# The factory pattern ensures user_id is properly injected and not exposed to the LLM.
