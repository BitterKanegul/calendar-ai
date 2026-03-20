"""
Safety gate inserted after update_filter_event_agent.

Asks for confirmation when the update targets mandatory/fixed events or
affects an unusually large number of events (≥3).
"""

from langchain_core.messages import AIMessage
from ..state import FlowState
from .risk_assessment import assess_update_risk, detect_ambiguity, RiskLevel


async def update_safety_gate(state: FlowState) -> FlowState:
    events = state.get("update_final_filtered_events") or []
    update_args = state.get("update_arguments") or {}

    # Nothing to update — pass through
    if not events:
        state["is_success"] = True
        return state

    ambiguity_warning = detect_ambiguity(events)
    risk_level, risk_reason = assess_update_risk(events, update_args)

    if risk_level == RiskLevel.HIGH or ambiguity_warning:
        event_summaries = []
        for ev in events[:5]:
            start = getattr(ev, "startDate", None)
            start_str = start.strftime("%a %b %d %I:%M %p") if start else "unknown time"
            event_summaries.append(f'• "{ev.title}" on {start_str}')
        if len(events) > 5:
            event_summaries.append(f"  … and {len(events) - 5} more")

        # Summarise what will change
        changes = []
        if update_args.get("title"):
            changes.append(f'title → "{update_args["title"]}"')
        if update_args.get("startDate"):
            changes.append(f'start → {update_args["startDate"]}')
        if update_args.get("duration"):
            changes.append(f'duration → {update_args["duration"]} min')
        if update_args.get("location"):
            changes.append(f'location → "{update_args["location"]}"')
        changes_str = ", ".join(changes) if changes else "various fields"

        lines = [risk_reason]
        if ambiguity_warning:
            lines.append(ambiguity_warning)
        lines.append(f"\nProposed changes: {changes_str}")
        lines.append("\nEvents to be updated:")
        lines.extend(event_summaries)
        lines.append("\nReply **yes** to confirm or **no** to cancel.")

        confirmation_message = "\n".join(lines)

        state["awaiting_confirmation"] = True
        state["confirmation_type"] = "update_safety"
        state["confirmation_data"] = {
            "events_to_update": [
                {
                    "id": ev.id,
                    "title": ev.title,
                    "startDate": ev.startDate.isoformat() if ev.startDate else None,
                }
                for ev in events
            ],
            "update_arguments": update_args,
            "risk_reason": risk_reason,
        }
        state["is_success"] = True
        return {
            **state,
            "update_messages": [AIMessage(content=confirmation_message)],
        }

    state["is_success"] = True
    return state
