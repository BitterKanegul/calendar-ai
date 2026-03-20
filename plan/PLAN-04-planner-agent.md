# PLAN-04: Planner Agent (Router Agent Upgrade)

## Goal

Upgrade the current router agent from a simple intent classifier into a full Planner Agent that can decompose complex multi-step requests, optimize schedules, manage focus slots, trigger the email RAG pipeline proactively, and provide rich conversational summaries.

---

## Current State

- **`flow/router_agent/router_agent.py`**: Calls the LLM with the router prompt, parses the response as JSON to get a `route` field, returns one of: `create`, `update`, `delete`, `list`, or falls through to `router_message_handler`
- **`flow/router_agent/prompt.py`**: `ROUTER_AGENT_PROMPT` instructs the LLM to classify intent into 4 CRUD categories or return a general message
- **`flow/builder.py`**: Router has 5 conditional edges — one per CRUD type + message handler
- The router handles exactly ONE operation per user message. No decomposition, no multi-step planning.

---

## Target Architecture

The Planner Agent operates in two modes:

1. **Simple mode** (backwards-compatible): Single CRUD operation — classify and route, same as today
2. **Planning mode**: Complex request → decompose into sub-tasks → execute sequentially/in-parallel → summarize results

```
User: "Plan my week — add study sessions around my classes,
       make sure gym stays flexible, and check if I have any
       meetings I'm missing from email"

Planner decomposes into:
  1. LIST events for the week (get current schedule)
  2. SEARCH emails for meeting-related content (RAG pipeline)
  3. CREATE study sessions in free slots (avoid class times)
  4. UPDATE gym events to flexibility=movable
  5. CREATE any events found in emails (with confirmation)

Returns: consolidated summary of all changes
```

---

## Implementation Steps

### Step 1: Redesign the Planner Agent prompt

**File: `backend/flow/router_agent/prompt.py`** (rename conceptually to planner)

The new prompt needs two capabilities:

**Capability 1: Intent classification (existing, enhanced)**
```
Classify the user's request:
- "create" — user wants to create one or more events
- "list" — user wants to view events
- "update" — user wants to modify events
- "delete" — user wants to remove events
- "confirm" — user is responding to a pending confirmation
- "plan" — user's request requires multiple operations (NEW)
- "message" — general conversation, not a calendar operation
```

**Capability 2: Task decomposition (new)**
When the route is "plan", the LLM also outputs a task list:
```json
{
  "route": "plan",
  "tasks": [
    {"step": 1, "operation": "list", "description": "Get all events for next week", "params": {"start_date": "...", "end_date": "..."}},
    {"step": 2, "operation": "create", "description": "Add study sessions in free slots", "depends_on": [1]},
    {"step": 3, "operation": "update", "description": "Set gym to flexible", "depends_on": [1]}
  ]
}
```

### Step 2: Create the plan executor

**New file: `backend/flow/planner_agent/plan_executor.py`**

```python
async def plan_executor(state: FlowState) -> dict:
    """
    Execute a multi-step plan by invoking sub-flows sequentially.

    For each task in the plan:
    1. Construct appropriate input for the target agent
    2. Invoke the agent (reuse existing create/list/update/delete agents)
    3. Collect results
    4. Pass results to dependent tasks
    5. After all tasks complete, generate a summary
    """
```

**Key design: Reuse existing agents as functions, not as graph nodes.**

The plan executor calls agent functions directly rather than re-traversing the graph:
```python
from flow.create_agent.create_agent import create_agent
from flow.list_agent.list_agent import list_event_by_date_range

# For each task in plan:
if task["operation"] == "list":
    result = await list_event_by_date_range(state)
elif task["operation"] == "create":
    result = await create_agent(state)
# etc.
```

This avoids the complexity of nested graph invocations while reusing all existing logic.

### Step 3: Add schedule optimization logic

**New file: `backend/flow/planner_agent/optimizer.py`**

```python
async def optimize_schedule(
    existing_events: list[dict],
    new_events: list[dict],
    preferences: dict
) -> list[dict]:
    """
    Place new events optimally around existing ones.

    Optimization criteria (in priority order):
    1. No conflicts with mandatory/fixed events
    2. Respect user time preferences (morning/afternoon/evening)
    3. Maintain buffer time between events (default: 15 min)
    4. Balance workload across days
    5. Proximity to user's preferred time

    Returns: new_events with optimized start/end times
    """
```

**Algorithm:**

1. Build a timeline for the target date range (list of occupied/free intervals)
2. For each new event, score all valid placements using the criteria above
3. Use a greedy approach: place highest-priority events first, then fill remaining
4. For "focus slots" (recurring blocks for study/deep work), find consistent daily slots if possible

This is deterministic Python code, not LLM-based. The LLM handles understanding what the user wants; the optimizer handles placing events.

### Step 4: Add focus slot management

**New file: `backend/flow/planner_agent/focus_slots.py`**

```python
class FocusSlot:
    """A recurring block of time reserved for a specific activity."""
    activity: str          # "study", "deep work", etc.
    duration_minutes: int
    preferred_time: str    # "morning", "afternoon", "evening"
    days: list[str]        # ["monday", "tuesday", ...] or ["weekdays"]
    flexibility: str       # "movable" (can be relocated if conflicts arise)

async def manage_focus_slots(
    user_id: int,
    focus_slots: list[FocusSlot],
    existing_events: list[dict]
) -> list[dict]:
    """
    Find optimal placements for focus slots around existing schedule.
    Tries to maintain consistency (same time each day if possible).
    """
```

Focus slots are conceptually "event templates" that the planner materializes into real events. When a new mandatory event conflicts with a focus slot, the planner automatically relocates the focus slot.

### Step 5: Update FlowState for planning

**File: `backend/flow/state.py`**

Add fields:
```python
class FlowState(TypedDict):
    # ... existing fields ...
    plan_tasks: list            # Decomposed task list
    plan_results: list          # Results from each completed task
    plan_summary: str           # Natural language summary of all changes
    is_planning_mode: bool      # Whether we're in multi-step mode
```

### Step 6: Update the flow graph

**File: `backend/flow/builder.py`**

Add the plan executor as a new node with a new conditional edge from the router:

```python
graph.add_node("plan_executor", plan_executor)

# Updated routing:
def route_action(state):
    route = state.get("route")
    if route == "plan":
        return "plan_executor"
    elif route == "confirm":
        return "confirmation_handler"
    # ... existing routes ...

graph.add_conditional_edges("router_agent", route_action, {
    "create": "create_agent",
    "list": "list_date_range_agent",
    "update": "update_date_range_agent",
    "delete": "delete_date_range_agent",
    "plan": "plan_executor",           # NEW
    "confirm": "confirmation_handler",  # NEW (from PLAN-03)
    "message": "router_message_handler",
})

graph.add_edge("plan_executor", END)
```

### Step 7: Generate conversational summaries

**New file: `backend/flow/planner_agent/summarizer.py`**

After multi-step execution, generate a clear summary:

```python
SUMMARY_PROMPT = """You are summarizing calendar changes made during a planning session.

Changes made:
{changes}

Generate a clear, friendly summary. Example format:
"Here's what I did for your week:
- Added 3 study sessions (Mon/Wed/Fri, 2-4 PM)
- Moved your gym session from 2 PM to 4 PM on Tuesday to avoid the team meeting
- Your Thursday looks packed — I left a 30-min buffer between your 1 PM and 3 PM meetings

Your updated schedule has 12 events across 5 days, with 2 hours of study time."
"""
```

This runs as the final step of the plan executor, using the LLM for natural language generation only.

### Step 8: Update the router agent prompt for planning detection

**File: `backend/flow/router_agent/prompt.py`**

Add examples of planning requests the LLM should recognize:

```
Route to "plan" when the user's request involves:
- Multiple operations ("add X and also delete Y")
- Schedule optimization ("plan my week", "organize my schedule")
- Conditional operations ("add study time around my classes")
- References to preferences ("avoid mornings", "keep evenings free")
- Requests that require seeing existing events first ("fit in a gym session somewhere")
```

### Step 9: Proactive email awareness (integration point)

When the plan executor detects certain triggers in the user's message, it adds an email retrieval task:

```python
# In plan_executor.py
email_triggers = ["email", "inbox", "missing", "forgot", "check if"]
if any(trigger in user_message.lower() for trigger in email_triggers):
    tasks.append({
        "step": 0,  # Run first
        "operation": "email_retrieval",
        "description": "Check emails for scheduling-relevant content"
    })
```

This is a stub until PLAN-05 (Email RAG Pipeline) is implemented. For now, skip the task gracefully if the email pipeline isn't available.

### Step 10: Update assistant_service response handling

**File: `backend/services/assistant_service.py`**

Add handling for the `plan` response type:

```python
if state.get("is_planning_mode"):
    return {
        "type": "plan_summary",
        "message": state["plan_summary"],
        "changes": state["plan_results"],
        "events_created": [...],
        "events_updated": [...],
        "events_deleted": [...]
    }
```

### Step 11: Update mobile app for plan summaries

**File: `mobile/src/screens/HomeScreen.tsx`**

Add handler for `"plan_summary"` response type. Display:
- The natural language summary as a message bubble
- A collapsible list of individual changes (created/updated/deleted events)
- A "View in Calendar" button to switch to the calendar view for the affected date range

---

## Testing Strategy

### Unit Tests

1. **Optimizer**: Given a set of existing events and new events to place, verify optimal placement respects all criteria
2. **Focus slots**: Verify slots are placed consistently across days; verify relocation when conflicts arise
3. **Task decomposition**: Feed complex requests to the planner prompt, verify the output task list is correct

### Integration Tests

4. **Simple request regression**: "Create a meeting tomorrow at 3pm" should still route to `create_agent` directly (not planning mode)
5. **Multi-step plan**: "Add a 1-hour study session every weekday next week, but not before 10am" — verify it lists events, finds slots, creates events
6. **Plan with conflicts**: Create a plan where some new events conflict — verify conflict resolution is invoked for each

### Manual Tests

7. Send increasingly complex requests and verify the planner decomposes them correctly
8. Verify the summary message is clear and accurate
9. Verify focus slot management across a full week

---

## Files Modified/Created (Summary)

| File | Change |
|------|--------|
| `flow/router_agent/prompt.py` | Enhanced with planning detection + task decomposition |
| `flow/router_agent/router_agent.py` | Parse plan tasks from LLM output |
| `flow/planner_agent/` | **New** directory |
| `flow/planner_agent/plan_executor.py` | **New** multi-step executor |
| `flow/planner_agent/optimizer.py` | **New** schedule optimization |
| `flow/planner_agent/focus_slots.py` | **New** focus slot management |
| `flow/planner_agent/summarizer.py` | **New** change summarizer |
| `flow/state.py` | Add planning state fields |
| `flow/builder.py` | Add plan_executor node + routes |
| `services/assistant_service.py` | Handle plan_summary response |
| `mobile/src/screens/HomeScreen.tsx` | Render plan summaries |

---

## Dependencies

- **PLAN-01** (Event Model): priority/flexibility needed for optimization
- **PLAN-03** (Conflict Resolution): plan executor calls conflict resolution for each conflicting event
- **PLAN-05** (Email RAG): proactive email awareness is a stub until the pipeline exists
