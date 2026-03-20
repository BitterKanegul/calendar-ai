"""
List Event Tool for LangChain agents.

This tool allows LLM agents to list calendar events within a date range
with proper filtering and authorization.
"""

import logging
from typing import Optional
from datetime import datetime
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from adapter.event_adapter import EventAdapter
from database import get_async_db_context_manager
from models import Event

logger = logging.getLogger(__name__)


class ListEventInput(BaseModel):
    """Input schema for the list_event tool."""
    
    startDate: datetime = Field(..., description="Start date of the range to list events (ISO 8601 format: YYYY-MM-DDTHH:MM:SS±HH:MM)")
    endDate: Optional[datetime] = Field(
        None,
        description="End date of the range to list events. If not provided, lists all events from startDate onwards"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "startDate": "2025-03-20T00:00:00-05:00",
                "endDate": "2025-03-27T23:59:59-05:00"
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


async def list_event_impl(
    startDate: datetime,
    endDate: Optional[datetime],
    user_id: int
) -> dict:
    """
    List calendar events within a date range.
    
    Args:
        startDate: Start date of the range to list events
        endDate: End date of the range (optional, if None lists all events from startDate onwards)
        user_id: User ID to filter events (required, injected from state)
    
    Returns:
        Dictionary with list of events and metadata
    
    Raises:
        Exception: If event listing fails
    """
    logger.info(f"Listing events for user {user_id} from {startDate} to {endDate or 'end'}")
    
    try:
        # Use adapter to list events
        async with get_async_db_context_manager() as db:
            adapter = EventAdapter(db)
            events = await adapter.get_events_by_date_range(
                user_id=user_id,
                start_date=startDate,
                end_date=endDate
            )
            
            logger.info(f"Found {len(events)} events for user {user_id}")
            
            return {
                "events": [_event_to_dict(event) for event in events],
                "count": len(events),
                "startDate": startDate.isoformat(),
                "endDate": endDate.isoformat() if endDate else None,
                "success": True
            }
    except Exception as e:
        logger.error(f"Error listing events: {e}", exc_info=True)
        raise Exception(f"Failed to list events: {str(e)}")


def list_event_tool_factory(user_id: int) -> StructuredTool:
    """
    Factory function to create a list_event tool bound to a specific user_id.
    
    Args:
        user_id: The user ID to inject into the tool
    
    Returns:
        A StructuredTool instance configured for the user
    """
    async def list_event_with_user_id(
        startDate: datetime,
        endDate: Optional[datetime] = None
    ) -> dict:
        """List events with user_id injected."""
        return await list_event_impl(
            startDate=startDate,
            endDate=endDate,
            user_id=user_id
        )
    
    return StructuredTool.from_function(
        func=list_event_with_user_id,
        name="list_event",
        description="""List calendar events within a date range.
        
        Use this tool when the user wants to view, see, or list their events.
        Returns all events that start on or after startDate.
        If endDate is provided, only returns events that end on or before endDate.
        If endDate is not provided, returns all events from startDate onwards.
        """,
        args_schema=ListEventInput,
    )


