"""
Safety gate inserted after delete_filter_event_agent.

If the pending deletion is HIGH risk (always for any real delete), the node
sets awaiting_confirmation=True and asks the user to confirm before the
actual DB delete happens.
"""

from langchain_core.messages import AIMessage
from ..state import FlowState
from .risk_assessment import assess_delete_risk, detect_ambiguity, RiskLevel


async def delete_safety_gate(state: FlowState) -> FlowState:
    events = state.get("delete_final_filtered_events") or []

    # Nothing to delete — let it flow through without gating
    if not events:
        state["is_success"] = True
        return state

    ambiguity_warning = detect_ambiguity(events)
    risk_level, risk_reason = assess_delete_risk(events)

    if risk_level == RiskLevel.HIGH or ambiguity_warning:
        event_summaries = []
        for ev in events[:5]:
            start = getattr(ev, "startDate", None)
            start_str = start.strftime("%a %b %d %I:%M %p") if start else "unknown time"
            event_summaries.append(f'• "{ev.title}" on {start_str}')
        if len(events) > 5:
            event_summaries.append(f"  … and {len(events) - 5} more")

        lines = [risk_reason]
        if ambiguity_warning:
            lines.append(ambiguity_warning)
        lines.append("\nEvents to be deleted:")
        lines.extend(event_summaries)
        lines.append("\nReply **yes** to confirm or **no** to cancel.")

        confirmation_message = "\n".join(lines)

        state["awaiting_confirmation"] = True
        state["confirmation_type"] = "delete_safety"
        state["confirmation_data"] = {
            "events_to_delete": [
                {
                    "id": ev.id,
                    "title": ev.title,
                    "startDate": ev.startDate.isoformat() if ev.startDate else None,
                }
                for ev in events
            ],
            "risk_reason": risk_reason,
        }
        state["is_success"] = True
        return {
            **state,
            "delete_messages": [AIMessage(content=confirmation_message)],
        }

    # LOW / MEDIUM risk — proceed without gating (currently unreachable for delete,
    # but kept for future policy changes)
    state["is_success"] = True
    return state
