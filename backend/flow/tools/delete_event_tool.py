"""
Delete Event Tool for LangChain agents.

This tool allows LLM agents to delete calendar events with proper validation
and authorization checks.
"""

import logging
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from adapter.event_adapter import EventAdapter
from database import get_async_db_context_manager

logger = logging.getLogger(__name__)


class DeleteEventInput(BaseModel):
    """Input schema for the delete_event tool."""
    
    event_id: str = Field(..., description="The UUID of the event to delete")


async def delete_event_impl(
    event_id: str,
    user_id: int
) -> dict:
    """
    Delete a calendar event.
    
    Args:
        event_id: The UUID of the event to delete
        user_id: User ID to verify ownership (required, injected from state)
    
    Returns:
        Dictionary with deletion status and event_id
    
    Raises:
        Exception: If event deletion fails
    """
    logger.info(f"Deleting event {event_id} for user {user_id}")
    
    try:
        # Use adapter to delete event
        async with get_async_db_context_manager() as db:
            adapter = EventAdapter(db)
            deleted = await adapter.delete_event(event_id, user_id)
            
            if deleted:
                logger.info(f"Successfully deleted event {event_id} for user {user_id}")
                return {
                    "event_id": event_id,
                    "success": True,
                    "message": f"Event {event_id} deleted successfully"
                }
            else:
                logger.warning(f"Event {event_id} not found or not authorized for user {user_id}")
                return {
                    "event_id": event_id,
                    "success": False,
                    "message": f"Event {event_id} not found or you are not authorized to delete it"
                }
    except Exception as e:
        logger.error(f"Error deleting event {event_id}: {e}", exc_info=True)
        raise Exception(f"Failed to delete event: {str(e)}")


def delete_event_tool_factory(user_id: int) -> StructuredTool:
    """
    Factory function to create a delete_event tool bound to a specific user_id.
    
    Args:
        user_id: The user ID to inject into the tool
    
    Returns:
        A StructuredTool instance configured for the user
    """
    async def delete_event_with_user_id(
        event_id: str
    ) -> dict:
        """Delete event with user_id injected."""
        return await delete_event_impl(
            event_id=event_id,
            user_id=user_id
        )
    
    return StructuredTool.from_function(
        func=delete_event_with_user_id,
        name="delete_event",
        description="""Delete a calendar event by its event_id.
        
        Use this tool when the user wants to delete, remove, or cancel an event.
        The event_id is the UUID of the event to delete.
        Only events owned by the user can be deleted.
        """,
        args_schema=DeleteEventInput,
    )


# Note: Use delete_event_tool_factory(user_id) to create a tool instance bound to a user_id.
# The factory pattern ensures user_id is properly injected and not exposed to the LLM.
