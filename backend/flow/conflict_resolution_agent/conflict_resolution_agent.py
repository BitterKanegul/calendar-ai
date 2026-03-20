"""
Conflict Resolution Agent

Runs after check_event_conflict when conflicts are detected.
Determines the resolution strategy (suggest_alternatives, reschedule_existing,
or user_choice), finds available alternative slots, calls the LLM for a
natural-language explanation, and sets awaiting_confirmation=True so the
next user message routes to confirmation_handler.
"""
from datetime import datetime, timedelta
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.prompts import PromptTemplate

from ..state import FlowState
from ..mcp_client import call_calendar_tool
from ..llm import model
from .slot_finder import find_available_slots
from .prompt import CONFLICT_RESOLUTION_PROMPT


def _classify_resolution(
    new_priority: str,
    new_flexibility: str,
    existing_priority: str,
    existing_flexibility: str,
) -> str:
    """Determine resolution strategy from event metadata."""
    # If existing event is fixed, we can't move it → suggest new slot for the new event
    if existing_flexibility == "fixed":
        return "suggest_alternatives"
    # If new event is mandatory and existing is optional → move existing out of the way
    if new_priority == "mandatory" and existing_priority == "optional":
        return "reschedule_existing"
    # If new event is optional and existing is mandatory → suggest new slot for new event
    if new_priority == "optional" and existing_priority == "mandatory":
        return "suggest_alternatives"
    # Both mandatory or both optional → let user decide
    return "user_choice"


def _format_dt(iso_str: str) -> str:
    try:
        return datetime.fromisoformat(iso_str).strftime("%a %b %d at %I:%M %p")
    except Exception:
        return iso_str


async def conflict_resolution_agent(state: FlowState) -> FlowState:
    """
    Build a resolution_plan and prompt the user with numbered options.
    Sets awaiting_confirmation=True on the state.
    """
    create_event_data = state.get("create_event_data") or []
    user_id = state["user_id"]

    # Find the first new event that has a conflict (re-query per event for accuracy)
    conflicting_new_event = None
    conflict_event_dict = None
    new_event_index = 0

    for idx, event_data in enumerate(create_event_data):
        args = event_data.get("arguments", {})
        start_iso = args.get("startDate")
        duration = args.get("duration", 0) or 0
        if not start_iso:
            continue
        try:
            start = datetime.fromisoformat(start_iso)
            end = start + timedelta(minutes=duration)
        except ValueError:
            continue

        try:
            conflict = await call_calendar_tool("check_conflicts", {
                "user_id": user_id,
                "start_date": start.isoformat(),
                "end_date": end.isoformat(),
            })
        except Exception:
            conflict = None

        if conflict:
            conflicting_new_event = event_data
            conflict_event_dict = conflict
            new_event_index = idx
            break

    if not conflicting_new_event or not conflict_event_dict:
        # No conflict found on re-check — proceed to create normally
        state["resolution_plan"] = None
        state["awaiting_confirmation"] = False
        state["create_messages"].append(AIMessage(content="Do you want to create the following events?"))
        state["is_success"] = True
        return state

    new_args = conflicting_new_event.get("arguments", {})
    new_priority = new_args.get("priority", "optional")
    new_flexibility = new_args.get("flexibility", "movable")
    new_duration = new_args.get("duration", 0) or 0
    new_start_iso = new_args.get("startDate")

    existing_priority = conflict_event_dict.get("priority", "optional")
    existing_flexibility = conflict_event_dict.get("flexibility", "movable")
    existing_id = conflict_event_dict.get("id")

    resolution_type = _classify_resolution(
        new_priority, new_flexibility, existing_priority, existing_flexibility
    )

    # Find alternative slots
    try:
        new_start_dt = datetime.fromisoformat(new_start_iso)
    except (ValueError, TypeError):
        new_start_dt = datetime.now()

    options: list[dict] = []
    option_num = 1

    if resolution_type in ("suggest_alternatives", "user_choice"):
        # Find new slots for the NEW event
        slots = await find_available_slots(
            user_id=user_id,
            duration_minutes=new_duration,
            preferred_time=new_start_dt,
            exclude_event_id=existing_id,
        )
        for slot in slots:
            new_event_args = dict(new_args)
            new_event_args["startDate"] = slot["start"]
            options.append({
                "option_num": option_num,
                "description": f"Create '{new_args.get('title', 'new event')}' at {_format_dt(slot['start'])} instead",
                "action": "create_new_at_slot",
                "new_event_args": new_event_args,
            })
            option_num += 1

    if resolution_type in ("reschedule_existing", "user_choice"):
        # Find new slots for the EXISTING event (move it out of the way)
        existing_start_iso = conflict_event_dict.get("startDate", new_start_iso)
        existing_duration = conflict_event_dict.get("duration", 60) or 60
        try:
            existing_start_dt = datetime.fromisoformat(existing_start_iso)
        except (ValueError, TypeError):
            existing_start_dt = new_start_dt

        slots = await find_available_slots(
            user_id=user_id,
            duration_minutes=existing_duration,
            preferred_time=existing_start_dt,
            exclude_event_id=existing_id,
        )
        for slot in slots:
            existing_new_end = datetime.fromisoformat(slot["end"])
            options.append({
                "option_num": option_num,
                "description": (
                    f"Move '{conflict_event_dict.get('title', 'existing event')}' "
                    f"to {_format_dt(slot['start'])} and create new event as planned"
                ),
                "action": "reschedule_existing_and_create",
                "new_event_args": new_args,
                "existing_event_id": existing_id,
                "existing_new_start": slot["start"],
                "existing_new_end": slot["end"],
            })
            option_num += 1

    # Always offer a cancel option
    options.append({
        "option_num": option_num,
        "description": "Cancel — don't create the new event",
        "action": "cancel",
    })

    # Non-conflicting events to always create alongside the chosen option
    non_conflicting = [
        ev for i, ev in enumerate(create_event_data) if i != new_event_index
    ]

    resolution_plan = {
        "resolution_type": resolution_type,
        "new_event_index": new_event_index,
        "conflict_event_id": existing_id,
        "options": options,
        "non_conflicting_events": non_conflicting,
    }

    # Generate LLM explanation
    options_text = "\n".join(
        f"Option {opt['option_num']}: {opt['description']}" for opt in options
    )
    template = PromptTemplate.from_template(CONFLICT_RESOLUTION_PROMPT)
    prompt_text = template.format(
        new_event_title=new_args.get("title", "new event"),
        new_event_start=_format_dt(new_start_iso or ""),
        new_event_duration=new_duration,
        conflict_title=conflict_event_dict.get("title", "existing event"),
        conflict_start=_format_dt(conflict_event_dict.get("startDate", "")),
        resolution_type=resolution_type.replace("_", " "),
        options_text=options_text,
    )

    try:
        response = await model.ainvoke([SystemMessage(content=prompt_text)])
        explanation = response.content
    except Exception:
        explanation = (
            f"'{new_args.get('title')}' conflicts with '{conflict_event_dict.get('title')}'. "
            f"Please choose an option:\n{options_text}"
        )

    state["resolution_plan"] = resolution_plan
    state["resolution_type"] = resolution_type
    state["awaiting_confirmation"] = True
    state["is_success"] = True
    state["create_messages"].append(AIMessage(content=explanation))

    return state


def conflict_action(state: FlowState) -> str:
    """Route after check_event_conflict."""
    if state.get("create_conflict_events"):
        return "conflict_resolution_agent"
    return "__end__"
