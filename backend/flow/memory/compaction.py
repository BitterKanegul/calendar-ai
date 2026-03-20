"""
Context compaction: summarises old messages when any array grows beyond COMPACTION_THRESHOLD.
The node runs between START and router_agent so every agent sees a trimmed history.
"""

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from ..llm import model
from ..state import FlowState

COMPACTION_THRESHOLD = 15   # compact when array length exceeds this
MESSAGES_TO_COMPACT = 10    # summarise this many oldest messages
MESSAGES_TO_KEEP = 5        # keep this many most-recent messages verbatim

SUMMARY_PROMPT = (
    "You are a conversation summariser. "
    "Summarise the following conversation history concisely in 2–4 sentences, "
    "preserving key facts: dates, event titles, decisions made, and unresolved questions. "
    "Reply with only the summary text.\n\n"
    "---\n{history}\n---"
)


def _messages_to_text(messages: list[BaseMessage]) -> str:
    lines = []
    for msg in messages:
        role = type(msg).__name__.replace("Message", "")
        lines.append(f"{role}: {msg.content}")
    return "\n".join(lines)


async def compact_if_needed(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Return a compacted copy if len > threshold, else return as-is."""
    if len(messages) <= COMPACTION_THRESHOLD:
        return messages

    to_compact = messages[:MESSAGES_TO_COMPACT]
    to_keep = messages[MESSAGES_TO_COMPACT:]

    history_text = _messages_to_text(to_compact)
    prompt = SUMMARY_PROMPT.format(history=history_text)

    try:
        summary_msg = await model.ainvoke([HumanMessage(content=prompt)])
        summary_content = f"[Earlier conversation summary] {summary_msg.content}"
    except Exception:
        # Fallback: just drop the oldest messages rather than error out
        summary_content = f"[Earlier conversation omitted — {len(to_compact)} messages]"

    return [SystemMessage(content=summary_content)] + to_keep


# Names of all message-array fields in FlowState that should be compacted.
_MESSAGE_FIELDS = [
    "router_messages",
    "create_messages",
    "delete_messages",
    "list_messages",
    "update_messages",
    "email_messages",
]


async def memory_compaction_node(state: FlowState) -> FlowState:
    """LangGraph node: compact all oversized message arrays before routing."""
    updates: dict = {}
    for field in _MESSAGE_FIELDS:
        messages = state.get(field) or []
        if len(messages) > COMPACTION_THRESHOLD:
            updates[field] = await compact_if_needed(messages)
    if updates:
        state.update(updates)
    return state
