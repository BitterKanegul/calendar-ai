# PLAN-01: Event Model Enhancements

## Goal

Add `priority`, `flexibility`, and `category` metadata fields to the event model across the entire stack. This is foundational — the Conflict Resolution Agent, Planner Agent, and schedule optimization all depend on these fields.

---

## Current State

- **`database/models/event.py`**: `EventModel` has columns: `id`, `event_id`, `title`, `startDate`, `endDate`, `location`, `user_id`, `created_at`
- **`models.py`**: Pydantic schemas `EventBase`, `EventCreate`, `EventUpdate`, `Event` have: `title`, `startDate`, `endDate`, `duration`, `location`
- **`mobile/src/models/event.tsx`**: TypeScript `Event` interface has: `id`, `title`, `startDate`, `endDate`, `duration`, `location`, `user_id`
- **Agent prompts** (e.g., `create_agent/prompt.py`): instruct the LLM to extract `title`, `duration`, `startDate`, `location` — no priority/flexibility/category

---

## Implementation Steps

### Step 1: Define enums and update SQLAlchemy model

**File: `backend/database/models/event.py`**

Add Python enums and new columns:

```python
import enum

class EventPriority(str, enum.Enum):
    MANDATORY = "mandatory"
    OPTIONAL = "optional"

class EventFlexibility(str, enum.Enum):
    FIXED = "fixed"
    MOVABLE = "movable"

class EventCategory(str, enum.Enum):
    WORK = "work"
    STUDY = "study"
    PERSONAL = "personal"
    LEISURE = "leisure"
```

Add to `EventModel`:
```python
priority = Column(SQLEnum(EventPriority), default=EventPriority.OPTIONAL, nullable=False)
flexibility = Column(SQLEnum(EventFlexibility), default=EventFlexibility.MOVABLE, nullable=False)
category = Column(SQLEnum(EventCategory), default=EventCategory.PERSONAL, nullable=False)
```

All three columns must have defaults so existing events (and simple create requests that don't specify them) remain valid.

### Step 2: Update Pydantic schemas

**File: `backend/models.py`**

Import the enums from `database/models/event.py` and add optional fields to:

- `EventBase`: add `priority: EventPriority = EventPriority.OPTIONAL`, `flexibility: EventFlexibility = EventFlexibility.MOVABLE`, `category: EventCategory = EventCategory.PERSONAL`
- `EventCreate`: inherits from `EventBase`, so it gets them automatically
- `EventUpdate`: add all three as `Optional` fields (only update if provided)
- `Event`: inherits from `EventBase`, so it gets them automatically

Also update the response models (`SuccessfulCreateResponse`, etc.) if they explicitly list fields.

### Step 3: Update the event adapter

**File: `backend/adapter/event_adapter.py`**

- `_convert_to_model()` and `_convert_to_db_model()`: include the three new fields in the conversion
- `create_event()` / `create_events()`: pass through new fields when constructing `EventModel`
- `update_event()`: include new fields in the update dict if provided

### Step 4: Update the event service

**File: `backend/services/event_service.py`**

- `create_event()`: pass through new fields to adapter
- `update_event()`: pass through new fields
- No changes needed for conflict detection logic yet (that's PLAN-03)

### Step 5: Update the create agent prompt

**File: `backend/flow/create_agent/prompt.py`**

Add instructions to the `CREATE_EVENT_AGENT_PROMPT` to extract:
- `priority`: "mandatory" or "optional" (default "optional"). Infer from context — meetings, exams, deadlines are mandatory; gym, study sessions are optional.
- `flexibility`: "fixed" or "movable" (default "movable"). Infer from context — doctor appointments are fixed; study blocks are movable.
- `category`: "work", "study", "personal", or "leisure" (default "personal"). Infer from keywords.

Update the JSON output schema in the prompt to include these fields.

### Step 6: Update the create agent logic

**File: `backend/flow/create_agent/create_agent.py`**

- When parsing the LLM's JSON response into event data, extract `priority`, `flexibility`, and `category` fields
- Pass them through to the event creation flow
- Use defaults if the LLM doesn't provide them

### Step 7: Update the update agent prompt and logic

**Files: `backend/flow/update_agent/update_data_range_agent_prompt.py`, `backend/flow/update_agent/update_agent.py`**

- Add `priority`, `flexibility`, `category` to the `update_arguments` schema in the prompt
- Parse and pass through in the update agent logic

### Step 8: Update list/filter agent prompts

**Files: `backend/flow/list_agent/list_filter_event_agent_prompt.py`, `backend/flow/delete_agent/delete_filter_event_agent_prompt.py`, `backend/flow/update_agent/update_filter_event_agent_prompt.py`**

- Include priority/flexibility/category in the event data shown to the filter LLM so users can say "delete all optional events" or "list my work events"

### Step 9: Update assistant_service response formatting

**File: `backend/services/assistant_service.py`**

- Include the new fields in the response data sent back to the mobile app

### Step 10: Update mobile TypeScript models

**File: `mobile/src/models/event.tsx`**

```typescript
export type EventPriority = 'mandatory' | 'optional';
export type EventFlexibility = 'fixed' | 'movable';
export type EventCategory = 'work' | 'study' | 'personal' | 'leisure';

export interface Event {
  // ... existing fields ...
  priority?: EventPriority;
  flexibility?: EventFlexibility;
  category?: EventCategory;
}
```

### Step 11: Update mobile UI components

**Files: `mobile/src/components/CreateComponent.tsx`, `UpdateComponent.tsx`, `ListComponent.tsx`, `DeleteComponent.tsx`**

- Display priority/category as chips or badges on event cards
- In `CreateComponent` and `UpdateComponent`: add pickers/dropdowns for the three fields (use `react-native-paper` `SegmentedButtons` or `Chip` components)
- In `ListComponent` and `DeleteComponent`: show the metadata as visual indicators (e.g., a red dot for mandatory, category icon)

### Step 12: Database migration

**File: `backend/database/migrate_add_event_metadata.py`** (new file)

Write a migration script (following the pattern of `migrate_to_start_end_dates.py`) that:
1. Adds the three columns with defaults to the existing `events` table
2. Backfills existing rows with defaults (`optional`, `movable`, `personal`)

---

## Testing Strategy

Since there are no existing tests, validate manually:

1. **Backend smoke test**: Start the server, create an event via `POST /events` with and without the new fields. Verify defaults are applied. Verify the response includes the new fields.
2. **Agent test**: Send natural language to `/assistant/` like "Schedule a mandatory team meeting tomorrow at 2pm" and verify the create agent extracts `priority: mandatory`.
3. **Update test**: Send "Change my gym session to optional" and verify the update flow handles it.
4. **List test**: Send "Show me my work events this week" and verify filtering works on category.
5. **Mobile test**: Verify event cards display the new metadata, and create/update modals allow setting them.
6. **Migration test**: Run migration on a database with existing events, verify all rows get defaults without errors.

---

## Files Modified (Summary)

| File | Change |
|------|--------|
| `database/models/event.py` | Add enums + 3 columns |
| `models.py` | Add fields to Pydantic schemas |
| `adapter/event_adapter.py` | Update conversions |
| `services/event_service.py` | Pass through new fields |
| `flow/create_agent/prompt.py` | Add extraction instructions |
| `flow/create_agent/create_agent.py` | Parse new fields |
| `flow/update_agent/update_data_range_agent_prompt.py` | Add to update schema |
| `flow/update_agent/update_agent.py` | Parse new fields |
| `flow/list_agent/list_filter_event_agent_prompt.py` | Include in filter context |
| `flow/delete_agent/delete_filter_event_agent_prompt.py` | Include in filter context |
| `flow/update_agent/update_filter_event_agent_prompt.py` | Include in filter context |
| `services/assistant_service.py` | Include in response |
| `mobile/src/models/event.tsx` | Add TypeScript types |
| `mobile/src/components/*.tsx` | Display and edit new fields |
| `database/migrate_add_event_metadata.py` | **New** migration script |
