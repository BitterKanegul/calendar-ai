"""
Confirmation Handler

Processes the user's choice from a conflict resolution prompt.
Parses their message to extract an option number, then executes
the corresponding action via MCP tools.
"""
import re
from datetime import datetime, timedelta
from langchain_core.messages import AIMessage
from ..state import FlowState
from ..mcp_client import call_calendar_tool
from ..llm import model
from langchain_core.messages import SystemMessage

# Word → number mapping for natural language parsing
_WORD_NUMBERS = {
    "one": 1, "first": 1,
    "two": 2, "second": 2,
    "three": 3, "third": 3,
    "four": 4, "fourth": 4,
    "five": 5, "fifth": 5,
    "six": 6, "sixth": 6,
    "seven": 7, "seventh": 7,
}

_AFFIRMATIVES = {"yes", "ok", "okay", "sure", "go ahead", "confirm", "do it", "proceed", "yep", "yeah"}


def _parse_option(text: str, num_options: int) -> int | None:
    """
    Try to extract an option number from user text.
    Returns 1-based option index or None if unclear.
    """
    text_lower = text.lower().strip()

    # 1. Explicit digit
    match = re.search(r'\b([1-9])\b', text_lower)
    if match:
        n = int(match.group(1))
        if 1 <= n <= num_options:
            return n

    # 2. Word numbers
    for word, num in _WORD_NUMBERS.items():
        if re.search(r'\b' + word + r'\b', text_lower) and 1 <= num <= num_options:
            return num

    # 3. Affirmatives → pick option 1 if only one non-cancel option
    if any(aff in text_lower for aff in _AFFIRMATIVES):
        if num_options == 2:  # only option 1 + cancel
            return 1

    return None


async def _llm_parse_option(user_text: str, options: list[dict]) -> int | None:
    """Fall back to LLM to interpret the user's choice."""
    options_text = "\n".join(
        f"Option {opt['option_num']}: {opt['description']}" for opt in options
    )
    prompt = (
        f"The user was shown these options:\n{options_text}\n\n"
        f"The user replied: \"{user_text}\"\n\n"
        f"Which option number did the user choose? Reply with only the number (e.g. '2'). "
        f"If unclear, reply with '0'."
    )
    try:
        response = await model.ainvoke([SystemMessage(content=prompt)])
        num = int(response.content.strip())
        if 1 <= num <= len(options):
            return num
    except Exception:
        pass
    return None


async def confirmation_handler(state: FlowState) -> FlowState:
    """
    Parse the user's confirmation/choice and execute the resolution plan.
    """
    resolution_plan = state.get("resolution_plan")
    user_text = state.get("input_text", "")
    user_id = state["user_id"]

    if not resolution_plan:
        state["create_messages"].append(
            AIMessage(content="Sorry, I lost track of the previous context. Please try again.")
        )
        state["awaiting_confirmation"] = False
        return state

    options: list[dict] = resolution_plan.get("options", [])
    non_conflicting: list[dict] = resolution_plan.get("non_conflicting_events", [])

    # Parse choice
    chosen_num = _parse_option(user_text, len(options))
    if chosen_num is None:
        chosen_num = await _llm_parse_option(user_text, options)

    if chosen_num is None:
        # Still unclear — re-prompt
        options_text = "\n".join(
            f"Option {opt['option_num']}: {opt['description']}" for opt in options
        )
        state["create_messages"].append(
            AIMessage(content=f"I didn't quite understand. Please reply with the option number:\n{options_text}")
        )
        return state

    chosen = next((opt for opt in options if opt["option_num"] == chosen_num), None)
    if not chosen:
        state["create_messages"].append(AIMessage(content="Invalid option. Please try again."))
        return state

    action = chosen.get("action")

    # === Execute the chosen action ===
    created_events = []
    errors = []

    if action == "cancel":
        state["awaiting_confirmation"] = False
        state["resolution_plan"] = None
        state["resolution_type"] = None
        state["create_messages"].append(AIMessage(content="No problem, I've cancelled the new event."))
        state["is_success"] = True
        return state

    if action == "create_new_at_slot":
        # Create the new event at the alternative slot
        ev_args = chosen.get("new_event_args", {})
        try:
            result = await call_calendar_tool("create_event", {
                "user_id": user_id,
                "title": ev_args.get("title"),
                "start_date": ev_args.get("startDate"),
                "duration": ev_args.get("duration", 60),
                "location": ev_args.get("location"),
                "priority": ev_args.get("priority", "optional"),
                "flexibility": ev_args.get("flexibility", "movable"),
                "category": ev_args.get("category", "personal"),
            })
            if result:
                created_events.append(result)
        except Exception as e:
            errors.append(str(e))

    elif action == "reschedule_existing_and_create":
        # Move the existing event
        existing_id = chosen.get("existing_event_id")
        new_start = chosen.get("existing_new_start")
        new_end = chosen.get("existing_new_end")

        try:
            # Calculate new duration from new_start/new_end
            new_duration = None
            if new_start and new_end:
                s = datetime.fromisoformat(new_start)
                e = datetime.fromisoformat(new_end)
                new_duration = int((e - s).total_seconds() / 60)

            await call_calendar_tool("update_event", {
                "event_id": existing_id,
                "user_id": user_id,
                "start_date": new_start,
                "duration": new_duration,
            })
        except Exception as e:
            errors.append(f"Could not reschedule existing event: {e}")

        # Create the new event at original planned time
        ev_args = chosen.get("new_event_args", {})
        try:
            result = await call_calendar_tool("create_event", {
                "user_id": user_id,
                "title": ev_args.get("title"),
                "start_date": ev_args.get("startDate"),
                "duration": ev_args.get("duration", 60),
                "location": ev_args.get("location"),
                "priority": ev_args.get("priority", "optional"),
                "flexibility": ev_args.get("flexibility", "movable"),
                "category": ev_args.get("category", "personal"),
            })
            if result:
                created_events.append(result)
        except Exception as e:
            errors.append(str(e))

    # Create non-conflicting events
    for ev_data in non_conflicting:
        ev_args = ev_data.get("arguments", {})
        try:
            result = await call_calendar_tool("create_event", {
                "user_id": user_id,
                "title": ev_args.get("title"),
                "start_date": ev_args.get("startDate"),
                "duration": ev_args.get("duration", 60),
                "location": ev_args.get("location"),
                "priority": ev_args.get("priority", "optional"),
                "flexibility": ev_args.get("flexibility", "movable"),
                "category": ev_args.get("category", "personal"),
            })
            if result:
                created_events.append(result)
        except Exception as e:
            errors.append(str(e))

    # Reset confirmation state; mark route as "confirmation" so assistant_service
    # returns a plain text response (events were already created via MCP)
    state["awaiting_confirmation"] = False
    state["resolution_plan"] = None
    state["resolution_type"] = None
    state["route"] = {"route": "confirmation"}

    if errors and not created_events:
        state["create_messages"].append(
            AIMessage(content="An error occurred while creating your events. Please try again.")
        )
    elif errors:
        state["create_messages"].append(
            AIMessage(content=f"Some events were created, but there were errors: {'; '.join(errors)}")
        )
        state["is_success"] = True
    else:
        state["create_messages"].append(AIMessage(content="Done! Your events have been updated."))
        state["is_success"] = True

    return state
