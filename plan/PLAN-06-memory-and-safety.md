# PLAN-06: Conversation Memory & Confirmation-First Safety

## Goal

Implement context compaction for long conversations and a confirmation-first safety policy that prevents destructive or ambiguous operations from executing without explicit user approval.

---

## Current State

### Memory
- **`flow/redis_checkpointer.py`**: `MessagesOnlyRedisSaver` persists 5 message arrays (router, create, delete, list, update) to Redis between turns
- Message arrays grow unbounded — long conversations will eventually exceed the LLM's context window
- No summarization or compaction of older messages

### Safety
- Events are created/deleted without confirmation (the mobile app shows events and the user clicks "Generate" or "Delete", but the AI flow itself doesn't gate operations)
- No ambiguity detection (e.g., "delete that meeting" when multiple meetings exist)
- No distinction between low-risk and high-risk operations

---

## Part A: Context Compaction

### Architecture

```
Messages:  [msg1, msg2, msg3, ..., msg18, msg19, msg20]
                                          ↑
                                   compaction threshold (15 messages)

After compaction:
  [summary_of_msg1_to_msg10, msg11, msg12, ..., msg19, msg20]
```

**Strategy**: When a message array exceeds a threshold, summarize the oldest N messages into a single summary message, then replace them. This preserves recent context while keeping token count bounded.

### Step 1: Build the compaction utility

**New file: `backend/flow/memory/compaction.py`**

```python
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

COMPACTION_PROMPT = """Summarize the following conversation history into a concise context summary.
Preserve:
- Key entities mentioned (event names, dates, people)
- Decisions made (events created, updated, deleted)
- Unresolved references (things the user mentioned but didn't act on)
- User preferences expressed (preferred times, categories, etc.)

Conversation:
{messages}

Return a concise summary paragraph (2-4 sentences max).
"""

COMPACTION_THRESHOLD = 15  # Messages before compaction triggers
MESSAGES_TO_COMPACT = 10   # How many old messages to summarize
MESSAGES_TO_KEEP = 5       # Recent messages to preserve verbatim

async def compact_messages(messages: list) -> list:
    """
    If messages exceed threshold, summarize oldest ones.

    Returns: compacted message list with a SystemMessage summary
    replacing the oldest messages.
    """
    if len(messages) <= COMPACTION_THRESHOLD:
        return messages  # No compaction needed

    to_compact = messages[:MESSAGES_TO_COMPACT]
    to_keep = messages[MESSAGES_TO_COMPACT:]

    # Generate summary
    formatted = "\n".join([
        f"{'User' if isinstance(m, HumanMessage) else 'Assistant'}: {m.content}"
        for m in to_compact
    ])

    summary_response = await llm.ainvoke([
        SystemMessage(content=COMPACTION_PROMPT.format(messages=formatted))
    ])

    summary_message = SystemMessage(
        content=f"[Conversation summary: {summary_response.content}]"
    )

    return [summary_message] + to_keep
```

### Step 2: Integrate compaction into the flow

**File: `backend/flow/builder.py`** or **`backend/services/assistant_service.py`**

Call compaction before invoking the flow:

```python
# In assistant_service.py, before flow.ainvoke():
from flow.memory.compaction import compact_messages

# Compact each message array in the state
for key in ["router_messages", "create_messages", "list_messages",
            "update_messages", "delete_messages"]:
    if key in initial_state and len(initial_state[key]) > COMPACTION_THRESHOLD:
        initial_state[key] = await compact_messages(initial_state[key])
```

### Step 3: Update the Redis checkpointer

**File: `backend/flow/redis_checkpointer.py`**

The checkpointer already persists message arrays. After compaction, it will naturally persist the compacted versions. No changes needed unless you want to:
- Store the full uncompacted history separately (for debugging)
- Add a TTL to old checkpoints to free Redis memory

Optional enhancement:
```python
# Add TTL to checkpoints older than 24 hours
async def put(self, config, checkpoint, metadata, new_versions):
    result = await super().put(config, checkpoint, metadata, new_versions)
    # Set TTL on the checkpoint key
    await self.conn.expire(checkpoint_key, 86400)  # 24 hours
    return result
```

---

## Part B: Confirmation-First Safety Policy

### Architecture

Operations are classified by risk level:

| Risk Level | Examples | Behavior |
|-----------|----------|----------|
| **Low** | List events, create optional event (no conflicts) | Execute immediately |
| **Medium** | Create event with conflict, update event time | Return preview, execute on user confirmation |
| **High** | Delete events, modify mandatory events, bulk operations | Require explicit confirmation with details |

### Step 4: Create the safety gate

**New file: `backend/flow/safety/confirmation_gate.py`**

```python
from enum import Enum

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

def assess_risk(operation: str, state: dict) -> RiskLevel:
    """
    Assess the risk level of an operation based on context.

    Rules:
    - DELETE anything → HIGH
    - Bulk operations (>3 events) → HIGH
    - UPDATE mandatory/fixed event → HIGH
    - CREATE with conflict → MEDIUM
    - UPDATE optional event → MEDIUM
    - CREATE without conflict → LOW
    - LIST → LOW
    """
    if operation == "delete":
        return RiskLevel.HIGH

    if operation == "create":
        event_count = len(state.get("create_event_data", []))
        has_conflict = bool(state.get("conflict_events"))
        if event_count > 3:
            return RiskLevel.HIGH
        if has_conflict:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW

    if operation == "update":
        # Check if targeting mandatory events
        events = state.get("update_filtered_events", [])
        if any(e.get("priority") == "mandatory" for e in events):
            return RiskLevel.HIGH
        return RiskLevel.MEDIUM

    return RiskLevel.LOW

def needs_confirmation(risk_level: RiskLevel) -> bool:
    """Returns True if the operation should pause for user confirmation."""
    return risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH)
```

### Step 5: Add ambiguity detection

**New file: `backend/flow/safety/ambiguity_detector.py`**

```python
async def detect_ambiguity(operation: str, state: dict) -> dict | None:
    """
    Check if the user's request is ambiguous.

    Returns None if unambiguous, or a dict describing the ambiguity:
    {"type": "multiple_matches", "candidates": [...], "message": "..."}
    """
    # Case 1: "Delete that meeting" but multiple meetings exist in context
    if operation == "delete":
        events = state.get("delete_date_range_filtered_events", [])
        if len(events) > 1:
            # Check if the filter agent couldn't narrow it down
            # (all events still match)
            return {
                "type": "multiple_matches",
                "candidates": events,
                "message": f"I found {len(events)} events that match. Which one(s) did you mean?"
            }

    # Case 2: "Update the meeting" with multiple candidates
    if operation == "update":
        events = state.get("update_filtered_events", [])
        if len(events) > 1:
            return {
                "type": "multiple_matches",
                "candidates": events,
                "message": f"I found {len(events)} events. Which one should I update?"
            }

    return None
```

### Step 6: Integrate safety gates into the flow

There are two approaches. **Recommended: Post-agent gate nodes.**

Add a safety gate node after each action agent but before the actual database operation:

**File: `backend/flow/builder.py`**

```python
# For delete flow:
# Before:  delete_filter_event_agent → END (with deletion happening in the node)
# After:   delete_filter_event_agent → delete_safety_gate → END

graph.add_node("delete_safety_gate", delete_safety_gate)
graph.add_conditional_edges("delete_safety_gate", safety_action, {
    "proceed": END,              # Low risk → execute
    "confirm": END,              # Medium/High risk → return confirmation request
    "ambiguous": END,            # Ambiguous → return clarification request
})
```

The gate node:
```python
async def delete_safety_gate(state: FlowState) -> dict:
    risk = assess_risk("delete", state)
    ambiguity = await detect_ambiguity("delete", state)

    if ambiguity:
        return {
            "awaiting_confirmation": True,
            "confirmation_type": "ambiguity",
            "confirmation_data": ambiguity
        }

    if needs_confirmation(risk):
        events = state.get("delete_date_range_filtered_events", [])
        return {
            "awaiting_confirmation": True,
            "confirmation_type": "delete_confirmation",
            "confirmation_data": {
                "events": events,
                "message": f"I'm about to delete {len(events)} event(s). Confirm?"
            }
        }

    # Low risk: proceed with deletion
    # (execute the actual delete operation here)
    return {"awaiting_confirmation": False}
```

### Step 7: Handle confirmation responses

**File: `backend/flow/router_agent/prompt.py`**

Add to the router prompt:
```
- "confirm" — user is responding to a pending confirmation
  (e.g., "yes", "go ahead", "delete #2", "option A")
```

**New file: `backend/flow/safety/confirmation_handler.py`**

```python
async def confirmation_handler(state: FlowState) -> dict:
    """
    Process user's confirmation response.

    Reads the pending operation from Redis checkpoint,
    matches the user's response to the expected confirmation type,
    and executes the confirmed operation.
    """
    user_response = state["router_messages"][-1].content.lower()
    pending = state.get("confirmation_data")

    if not pending:
        return {"router_messages": [AIMessage(
            content="I don't have a pending action to confirm."
        )]}

    confirmation_type = state.get("confirmation_type")

    if confirmation_type == "ambiguity":
        # Parse which candidate the user selected
        selected = parse_selection(user_response, pending["candidates"])
        if selected:
            # Execute the operation on the selected event(s)
            ...
        else:
            return {"router_messages": [AIMessage(
                content="I didn't understand your selection. Please specify which event."
            )]}

    elif confirmation_type == "delete_confirmation":
        if is_affirmative(user_response):
            # Execute the deletion
            ...
        else:
            return {"router_messages": [AIMessage(
                content="OK, I've cancelled the deletion."
            )]}
```

### Step 8: Update FlowState

**File: `backend/flow/state.py`**

```python
class FlowState(TypedDict):
    # ... existing fields ...
    awaiting_confirmation: bool
    confirmation_type: str       # "delete_confirmation", "ambiguity", etc.
    confirmation_data: dict      # Context for the pending confirmation
```

### Step 9: Update Redis checkpointer for confirmation state

**File: `backend/flow/redis_checkpointer.py`**

Add confirmation fields to the persisted set:
```python
MESSAGE_FIELDS = [
    "router_messages", "create_messages", "delete_messages",
    "list_messages", "update_messages",
    # Safety/confirmation state:
    "awaiting_confirmation", "confirmation_type", "confirmation_data"
]
```

### Step 10: Update mobile app for confirmation UI

**File: `mobile/src/screens/HomeScreen.tsx`**

When response type is `confirmation_required`:
- Display the confirmation message as an AI bubble
- For ambiguity: show numbered list of candidates, user taps to select
- For delete/update confirmation: show event details + "Confirm" / "Cancel" buttons
- User's selection is sent back to `/assistant/` as a normal text message

---

## Testing Strategy

### Context Compaction Tests

1. Build a conversation with 20+ messages, verify compaction triggers at threshold
2. Verify the summary preserves key entities (event names, dates)
3. Verify the LLM can still reference compacted context (e.g., "move that meeting we discussed earlier")
4. Verify Redis stores the compacted version (not the full history)

### Safety Gate Tests

5. **Low risk**: Create a single event with no conflict → should execute immediately
6. **Medium risk**: Create event with conflict → should return confirmation request
7. **High risk**: Delete 5 events → should require explicit confirmation
8. **Ambiguity**: "Delete the meeting" with 3 meetings → should ask which one
9. **Confirmation round-trip**: Trigger a confirmation, then respond "yes" → verify execution
10. **Cancellation**: Trigger a confirmation, then respond "no" → verify cancellation
11. **Mandatory protection**: Try to update a mandatory event → should require confirmation with warning

---

## Files Modified/Created (Summary)

| File | Change |
|------|--------|
| `flow/memory/` | **New** directory |
| `flow/memory/compaction.py` | **New** context compaction |
| `flow/safety/` | **New** directory |
| `flow/safety/confirmation_gate.py` | **New** risk assessment |
| `flow/safety/ambiguity_detector.py` | **New** ambiguity detection |
| `flow/safety/confirmation_handler.py` | **New** confirmation processing |
| `flow/state.py` | Add confirmation state fields |
| `flow/builder.py` | Add safety gate nodes + confirmation handler |
| `flow/router_agent/prompt.py` | Add "confirm" route |
| `flow/redis_checkpointer.py` | Persist confirmation state |
| `services/assistant_service.py` | Trigger compaction; handle confirmation responses |
| `mobile/src/screens/HomeScreen.tsx` | Confirmation UI |

---

## Dependencies

- **PLAN-01** (Event Model): priority field needed for mandatory event detection
- **PLAN-03** (Conflict Resolution): shares the confirmation flow pattern
