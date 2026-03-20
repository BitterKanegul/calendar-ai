# PLAN-03: Conflict Resolution Agent

## Goal

Upgrade the current binary conflict check into a full Conflict Resolution Agent that reasons about event priority and flexibility, suggests alternative time slots, handles bulk conflicts, and asks for user confirmation before making high-impact changes.

---

## Current State

- **`flow/create_agent/create_agent.py`** → `check_event_conflict()`:
  - Calls `EventAdapter().check_event_conflict(user_id, startDate, endDate)`
  - Returns a list of conflicting events in `state["conflict_events"]`
  - The flow ends here — conflicts are reported to the user but not resolved
  - No priority awareness, no alternative suggestions, no automatic rescheduling
- **`flow/builder.py`**: `check_event_conflict` is a terminal node (goes to END)
- **Conflict data** is returned to the mobile app, which displays it as a warning in `CreateComponent.tsx`

---

## Target Architecture

```
check_event_conflict (existing node, detects conflicts)
  │
  ├── No conflicts → create event → END
  │
  └── Conflicts detected → conflict_resolution_agent (NEW node)
        │
        ├── All conflicts are with optional/movable events
        │   → Propose rescheduling the conflicting events
        │   → Return resolution plan for user confirmation
        │
        ├── Conflict with mandatory/fixed event
        │   → Find alternative time slots for the NEW event
        │   → Return ranked alternatives for user confirmation
        │
        └── Bulk creation with mixed conflicts
            → Resolve each conflict individually
            → Return consolidated resolution plan
```

---

## Implementation Steps

### Step 1: Create the Conflict Resolution Agent

**New file: `backend/flow/conflict_resolution_agent/conflict_resolution_agent.py`**

```python
async def conflict_resolution_agent(state: FlowState) -> dict:
    """
    Analyze conflicts and propose resolutions based on priority/flexibility.

    Inputs from state:
      - create_event_data: the event(s) the user wants to create
      - conflict_events: the conflicting existing events
      - user_id: for querying available slots

    Outputs to state:
      - resolution_plan: structured resolution proposal
      - resolution_type: "reschedule_existing" | "suggest_alternatives" | "user_choice"
    """
```

**Resolution logic (implemented in Python, NOT delegated to the LLM):**

1. For each conflict pair (new event vs existing event):
   - If existing event is `optional` + `movable` and new event is `mandatory`:
     → Propose moving the existing event. Find free slots via `check_conflicts` MCP tool.
   - If existing event is `mandatory` or `fixed`:
     → Cannot move it. Find alternative slots for the new event.
   - If both are `optional` + `movable`:
     → Present both options to the user (move existing or reschedule new).

2. **Finding alternative slots**: Query the user's events for the target day, identify gaps that fit the event duration, rank by proximity to the originally requested time.

**New file: `backend/flow/conflict_resolution_agent/prompt.py`**

```python
CONFLICT_RESOLUTION_PROMPT = """You are a scheduling conflict resolution assistant.

Given:
- The event the user wants to create: {new_event}
- The conflicting existing events: {conflicts}
- Available alternative time slots: {alternatives}

Generate a clear, friendly explanation of the conflict and the proposed resolution.
Present options to the user in a numbered list.

Rules:
- Never silently overwrite mandatory/fixed events
- Explain WHY you're suggesting each alternative (closest to requested time, no conflicts, etc.)
- If multiple events conflict, summarize all conflicts together
- End with a question asking the user to choose an option or provide a different time
"""
```

The LLM is used only for **generating natural language explanations**, not for the resolution logic itself. This keeps conflict resolution deterministic and testable.

### Step 2: Add alternative slot finder

**New file: `backend/flow/conflict_resolution_agent/slot_finder.py`**

```python
async def find_available_slots(
    user_id: int,
    target_date: date,
    duration_minutes: int,
    preferred_time: time,
    exclude_event_ids: list[str] = None
) -> list[dict]:
    """
    Find available time slots on the target date.

    Returns slots sorted by proximity to preferred_time.
    Each slot: {"start": datetime, "end": datetime, "distance_minutes": int}
    """
    # 1. Get all events for target_date via MCP list_events tool
    # 2. Build a list of occupied intervals
    # 3. Compute free intervals within business hours (8am-10pm)
    # 4. Filter intervals that fit the requested duration
    # 5. Sort by |slot_midpoint - preferred_time|
    # 6. Return top 5 alternatives
```

### Step 3: Add resolution plan data structure

**File: `backend/flow/state.py`**

Add new state fields:

```python
class FlowState(TypedDict):
    # ... existing fields ...
    resolution_plan: list       # Proposed resolution actions
    resolution_type: str        # "reschedule_existing" | "suggest_alternatives" | "user_choice"
    awaiting_confirmation: bool # Whether the flow is paused waiting for user input
```

### Step 4: Update the flow graph

**File: `backend/flow/builder.py`**

Change the flow after `check_event_conflict`:

```python
# Before:
# check_event_conflict → END

# After:
graph.add_node("conflict_resolution_agent", conflict_resolution_agent)

graph.add_conditional_edges(
    "check_event_conflict",
    conflict_action,  # New routing function
    {
        "no_conflict": END,       # No conflicts → proceed (event already created)
        "has_conflict": "conflict_resolution_agent",
    }
)
graph.add_edge("conflict_resolution_agent", END)
```

### Step 5: Handle user confirmation flow

Conflict resolution often requires a round-trip with the user ("Do you want option A or B?"). Two approaches:

**Approach A (Recommended): Return resolution plan, handle confirmation in next turn**

1. Flow returns with `awaiting_confirmation: True` and a `resolution_plan`
2. Mobile app displays the options (see Step 7)
3. User selects an option → sent back to `/assistant/` as a new message
4. Router agent detects this is a confirmation response → routes to a `confirmation_handler` node
5. `confirmation_handler` executes the chosen resolution

**Implementation:**

**New node in `backend/flow/builder.py`:**
```python
graph.add_node("confirmation_handler", confirmation_handler)
```

**Router agent update (`flow/router_agent/prompt.py`):**
Add a new route category: `"confirm"` — triggered when the user's message is a response to a pending resolution (e.g., "option 1", "yes", "move the gym session").

**Redis checkpointer update (`flow/redis_checkpointer.py`):**
Add `resolution_plan` and `resolution_type` to the persisted fields so the context survives between turns.

### Step 6: Handle bulk conflict resolution

For bulk event creation (e.g., "Schedule a 1-hour study session every day next week"):

```python
async def resolve_bulk_conflicts(events: list, conflicts_by_event: dict) -> list:
    """
    Resolve conflicts for multiple events.

    Strategy:
    1. Process mandatory new events first (they take priority)
    2. For each event, try to resolve conflicts independently
    3. After resolving one, re-check remaining events (resolving one
       conflict may create or resolve another)
    4. Return consolidated resolution plan
    """
```

### Step 7: Update mobile app for conflict resolution UI

**File: `mobile/src/components/CreateComponent.tsx`**

Currently shows conflict events as a warning. Enhance to:

1. Display the resolution options as selectable cards
2. Each option shows: proposed new time, which events move, visual timeline preview
3. "Accept" button to confirm the selected option
4. "Custom time" option to let the user pick manually

**File: `mobile/src/components/ConflictResolutionComponent.tsx`** (new)

Dedicated component for conflict resolution:
```typescript
interface ResolutionOption {
  id: number;
  description: string;
  actions: Array<{
    type: 'move' | 'create' | 'skip';
    event_title: string;
    original_time: string;
    proposed_time: string;
  }>;
}

interface ConflictResolutionProps {
  newEvent: Event;
  conflicts: Event[];
  options: ResolutionOption[];
  onSelect: (optionId: number) => void;
}
```

### Step 8: Update assistant_service response format

**File: `backend/services/assistant_service.py`**

Add a new response type for conflict resolution:

```python
if state.get("awaiting_confirmation"):
    return {
        "type": "conflict_resolution",
        "message": state["resolution_plan"]["explanation"],
        "options": state["resolution_plan"]["options"],
        "original_event": state["create_event_data"],
        "conflicts": state["conflict_events"]
    }
```

**File: `mobile/src/screens/HomeScreen.tsx`**

Add handler for the `"conflict_resolution"` response type that renders the `ConflictResolutionComponent`.

---

## Testing Strategy

### Unit Tests

1. **Slot finder**: Given a set of existing events, verify `find_available_slots` returns correct free intervals sorted by proximity
2. **Resolution logic**: Test all priority/flexibility combinations:
   - mandatory vs optional → should propose moving optional
   - mandatory vs mandatory → should suggest alternatives for new event
   - optional vs optional → should offer both choices
3. **Bulk resolution**: Create 5 events with 2 conflicts, verify resolution is globally consistent

### Integration Tests

4. **End-to-end create with conflict**: Send "Schedule a meeting tomorrow at 2pm" when a mandatory event exists at 2pm. Verify the response includes alternatives.
5. **Confirmation round-trip**: After receiving alternatives, send "option 1" and verify the event is created at the alternative time.
6. **No-conflict path**: Verify that events without conflicts are still created normally (regression).

### Manual Mobile Tests

7. Verify conflict resolution UI displays options correctly
8. Verify selecting an option sends the right confirmation back
9. Verify the resolution is reflected in the calendar view

---

## Files Modified/Created (Summary)

| File | Change |
|------|--------|
| `flow/conflict_resolution_agent/` | **New** directory |
| `flow/conflict_resolution_agent/conflict_resolution_agent.py` | **New** resolution logic |
| `flow/conflict_resolution_agent/prompt.py` | **New** LLM prompt for explanations |
| `flow/conflict_resolution_agent/slot_finder.py` | **New** available slot finder |
| `flow/state.py` | Add resolution_plan, resolution_type, awaiting_confirmation |
| `flow/builder.py` | Add conflict_resolution_agent node, confirmation_handler node |
| `flow/router_agent/prompt.py` | Add "confirm" route |
| `flow/redis_checkpointer.py` | Persist resolution fields |
| `services/assistant_service.py` | Handle conflict_resolution response type |
| `mobile/src/components/ConflictResolutionComponent.tsx` | **New** UI component |
| `mobile/src/components/CreateComponent.tsx` | Integrate resolution UI |
| `mobile/src/screens/HomeScreen.tsx` | Handle conflict_resolution response type |

---

## Dependencies

- **PLAN-01** (Event Model Enhancements): priority and flexibility fields must exist for resolution logic
- **PLAN-02** (MCP Integration): slot finder should use MCP tools for consistency, but can fall back to direct adapter calls if MCP isn't ready yet
