"""
Handles user's yes/no reply to a safety gate confirmation request.

Dispatched to when confirmation_type in ("delete_safety", "update_safety").
Executes the pending operation via MCP on "yes", cancels on "no".
"""

import re
import logging
from langchain_core.messages import AIMessage, HumanMessage
from ..state import FlowState
from ..mcp_client import call_calendar_tool

logger = logging.getLogger(__name__)

_AFFIRMATIVES = {"yes", "y", "confirm", "ok", "okay", "sure", "do it", "proceed", "yep", "yeah"}
_NEGATIVES = {"no", "n", "cancel", "stop", "abort", "nope", "nah", "nevermind", "never mind"}


def _parse_user_intent(text: str) -> str:
    """Returns 'confirm', 'cancel', or 'unclear'."""
    cleaned = text.strip().lower()
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    if cleaned in _AFFIRMATIVES:
        return "confirm"
    if cleaned in _NEGATIVES:
        return "cancel"
    # partial match
    for word in cleaned.split():
        if word in _AFFIRMATIVES:
            return "confirm"
        if word in _NEGATIVES:
            return "cancel"
    return "unclear"


async def safety_confirmation_handler(state: FlowState) -> FlowState:
    confirmation_type = state.get("confirmation_type")
    confirmation_data = state.get("confirmation_data") or {}
    user_id = state.get("user_id")

    # Find the user's latest reply
    if confirmation_type == "delete_safety":
        messages = state.get("delete_messages") or state.get("router_messages") or []
    else:
        messages = state.get("update_messages") or state.get("router_messages") or []

    user_reply = ""
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            user_reply = msg.content
            break
    if not user_reply:
        user_reply = state.get("input_text", "")

    intent = _parse_user_intent(user_reply)

    # --- Reset confirmation state regardless of outcome ---
    state["awaiting_confirmation"] = False
    state["confirmation_type"] = None
    state["confirmation_data"] = None

    if intent == "cancel" or intent == "unclear":
        cancel_text = (
            "Operation cancelled. Nothing was changed."
            if intent == "cancel"
            else "I wasn't sure if you wanted to proceed, so I've cancelled the operation. "
                 "Please try again and reply yes or no."
        )
        state["is_success"] = True
        if confirmation_type == "delete_safety":
            return {**state, "delete_messages": [AIMessage(content=cancel_text)]}
        return {**state, "update_messages": [AIMessage(content=cancel_text)]}

    # ---- Execute the confirmed operation ----
    try:
        if confirmation_type == "delete_safety":
            events_to_delete = confirmation_data.get("events_to_delete", [])
            deleted_titles = []
            for ev in events_to_delete:
                await call_calendar_tool("delete_event", {
                    "event_id": ev["id"],
                    "user_id": user_id,
                })
                deleted_titles.append(ev["title"])

            if deleted_titles:
                summary = ", ".join(f'"{t}"' for t in deleted_titles[:5])
                if len(deleted_titles) > 5:
                    summary += f" and {len(deleted_titles) - 5} more"
                msg = f"Deleted: {summary}."
            else:
                msg = "No events were deleted."

            state["is_success"] = True
            return {**state, "delete_messages": [AIMessage(content=msg)]}

        elif confirmation_type == "update_safety":
            events_to_update = confirmation_data.get("events_to_update", [])
            update_arguments = confirmation_data.get("update_arguments", {})
            updated_titles = []
            for ev in events_to_update:
                await call_calendar_tool("update_event", {
                    "event_id": ev["id"],
                    "user_id": user_id,
                    **update_arguments,
                })
                updated_titles.append(ev["title"])

            if updated_titles:
                summary = ", ".join(f'"{t}"' for t in updated_titles[:5])
                if len(updated_titles) > 5:
                    summary += f" and {len(updated_titles) - 5} more"
                msg = f"Updated: {summary}."
            else:
                msg = "No events were updated."

            state["is_success"] = True
            return {**state, "update_messages": [AIMessage(content=msg)]}

    except Exception as e:
        logger.error("safety_confirmation_handler error: %s", e, exc_info=True)
        error_msg = "Something went wrong while executing the operation. Please try again."
        state["is_success"] = False
        if confirmation_type == "delete_safety":
            return {**state, "delete_messages": [AIMessage(content=error_msg)]}
        return {**state, "update_messages": [AIMessage(content=error_msg)]}

    state["is_success"] = True
    return state
