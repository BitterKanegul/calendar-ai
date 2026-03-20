# PLAN-08 — Testing Strategy

## Overview

Three tiers, running from fast/cheap to slow/expensive:

| Tier | Count | DB | Redis | OpenAI | Runtime |
|------|-------|----|-------|--------|---------|
| **Unit tests** | ~80 | No (mocked) | No (mocked) | No (mocked) | < 10 s |
| **Integration tests** | ~15 | Yes (test DB) | Yes (Docker) | No (mocked) | < 30 s |
| **End-to-end tests** | ~8 | Yes | Yes | Yes (live) | < 3 min |

All tests use **pytest + pytest-asyncio**. Run the full suite with:

```bash
cd backend
pytest                              # unit only (default)
pytest -m integration               # integration only
pytest -m e2e                       # end-to-end only
pytest -m "not e2e"                 # everything except e2e
pytest --tb=short -q                # CI-friendly output
```

---

## Directory Structure

```
backend/tests/
├── conftest.py                     # shared fixtures: mock DB session, mock LLM, test user/events
├── pytest.ini                      # markers, asyncio mode
│
├── unit/
│   ├── test_models.py              # Pydantic validation (14 tests)
│   ├── test_jwt.py                 # token create/verify/expire (8 tests)
│   ├── test_password.py            # hash + verify (4 tests)
│   ├── test_event_adapter.py       # all CRUD, mock AsyncSession (12 tests)
│   ├── test_user_adapter.py        # all CRUD, mock AsyncSession (8 tests)
│   ├── test_event_service.py       # business logic, mock adapter (10 tests)
│   ├── test_user_service.py        # auth flows, mock adapter + JWT (8 tests)
│   ├── test_risk_assessment.py     # delete/update risk + ambiguity (8 tests)
│   ├── test_slot_finder.py         # available-slot algorithm (6 tests)
│   ├── test_compaction.py          # threshold logic, message trimming (5 tests)
│   ├── test_slot_metrics.py        # eval slot F1 computation (4 tests)
│   └── test_intent_metrics.py      # eval accuracy/confusion matrix (4 tests)
│
├── integration/
│   ├── conftest.py                 # real test DB + Redis fixtures
│   ├── test_db_event_lifecycle.py  # create→read→update→delete via adapter (5 tests)
│   ├── test_db_user_lifecycle.py   # register→read→update→delete via adapter (4 tests)
│   ├── test_redis_checkpointer.py  # aput/aget field filtering (3 tests)
│   └── test_router_agent.py        # router_agent with mock LLM, real state (3 tests)
│
└── e2e/
    ├── conftest.py                 # TestClient, seeded user + events
    ├── test_auth_flow.py           # register → login → refresh → me (3 tests)
    └── test_calendar_flow.py       # create → list → update → delete via /assistant/ (5 tests)
```

---

## Tier 1 — Unit Tests (no external dependencies)

### 1.1 Pydantic Models (`test_models.py`, ~14 tests)

Test all validation rules on the Pydantic schemas.

| Test | What it checks |
|------|---------------|
| `test_event_create_valid` | Valid EventCreate is accepted |
| `test_event_create_missing_title` | Raises ValidationError when title is missing |
| `test_event_create_missing_start_date` | Raises ValidationError |
| `test_event_create_invalid_priority_enum` | Rejects unknown priority value |
| `test_event_create_default_enums` | priority=optional, flexibility=movable, category=personal |
| `test_event_update_all_optional` | EventUpdate with no fields is valid |
| `test_user_create_short_password` | Password < 6 chars raises ValidationError |
| `test_user_create_invalid_email` | Invalid email raises ValidationError |
| `test_user_create_valid` | Happy path |
| `test_process_input_valid` | ProcessInput accepts well-formed input |
| `test_successful_list_response_shape` | SuccessfulListResponse serialises correctly |
| `test_confirmation_required_response` | ConfirmationRequiredResponse includes confirmation_type |
| `test_plan_change_optional_fields` | PlanChange allows None for event_title/event_start |
| `test_extracted_email_event` | ExtractedEmailEvent serialises confidence tiers |

### 1.2 JWT (`test_jwt.py`, ~8 tests)

```
test_create_access_token_returns_string
test_create_refresh_token_returns_string
test_verify_valid_access_token
test_verify_expired_access_token              # patch time
test_verify_refresh_token_rejects_access      # wrong type
test_verify_access_token_rejects_refresh      # wrong type
test_get_user_id_from_token
test_verify_token_invalid_signature           # tampered token
```

### 1.3 Password (`test_password.py`, ~4 tests)

```
test_hash_returns_bytes_string
test_verify_correct_password
test_verify_wrong_password
test_hash_is_nondeterministic                 # two hashes of same input differ
```

### 1.4 Event Adapter (`test_event_adapter.py`, ~12 tests)

Mock `AsyncSession` with `MagicMock`/`AsyncMock`. Patch `get_async_db` to return the mock.

```
test_create_event_success                     # mock session.add + commit
test_create_event_integrity_error             # duplicate → raises
test_get_event_by_event_id_found
test_get_event_by_event_id_not_found          # returns None
test_get_events_by_user_id
test_get_events_by_date_range
test_update_event_success
test_update_event_not_found
test_delete_event_success
test_delete_event_not_found
test_check_event_conflict_found
test_check_event_conflict_no_conflict
```

### 1.5 User Adapter (`test_user_adapter.py`, ~8 tests)

Same mocking pattern as event adapter.

```
test_create_user_success
test_create_user_duplicate_email
test_get_user_by_id_found
test_get_user_by_id_not_found
test_get_user_by_email_found
test_get_user_by_email_not_found
test_update_user_success
test_delete_user_success
```

### 1.6 Event Service (`test_event_service.py`, ~10 tests)

Mock `EventAdapter` entirely.

```
test_create_event_calls_adapter
test_create_events_bulk
test_get_event_owned_by_user
test_get_event_not_owned_raises_403
test_get_event_not_found_raises_404
test_get_user_events_pagination
test_get_events_by_date_range
test_update_event_success
test_delete_event_success
test_delete_multiple_events
```

### 1.7 User Service (`test_user_service.py`, ~8 tests)

Mock `UserAdapter` + `jwt` + `password` utils.

```
test_register_creates_user_and_tokens
test_register_duplicate_email
test_login_success
test_login_wrong_password
test_login_email_not_found
test_refresh_token_success
test_refresh_token_expired
test_change_password_success
```

### 1.8 Risk Assessment (`test_risk_assessment.py`, ~8 tests)

Pure functions — no mocks needed, just construct `Event` objects.

```
test_delete_risk_empty_list_returns_low
test_delete_risk_one_event_returns_high
test_delete_risk_mandatory_event_mentions_title
test_update_risk_optional_events_returns_medium
test_update_risk_mandatory_event_returns_high
test_update_risk_three_plus_events_returns_high
test_ambiguity_below_threshold_returns_none
test_ambiguity_above_threshold_returns_warning
```

### 1.9 Slot Finder (`test_slot_finder.py`, ~6 tests)

Mock `call_calendar_tool("list_events", ...)` to return known events. Test the time-scanning algorithm.

```
test_empty_calendar_returns_preferred_time
test_one_busy_block_skips_it
test_fully_packed_day_returns_empty
test_respects_business_hours_8am_10pm
test_sorts_by_proximity_to_preferred
test_max_slots_limit
```

### 1.10 Memory Compaction (`test_compaction.py`, ~5 tests)

Mock `model.ainvoke` for the LLM summary call.

```
test_below_threshold_returns_unchanged
test_at_threshold_returns_unchanged
test_above_threshold_compacts
test_compacted_result_has_system_message_first
test_keeps_last_n_messages_verbatim
```

### 1.11 Eval Metrics (`test_slot_metrics.py` + `test_intent_metrics.py`, ~8 tests)

Pure functions, no mocks.

```
# slot_metrics
test_slot_f1_perfect_match
test_slot_f1_partial_match
test_slot_f1_string_substring_matching
test_slot_f1_numeric_tolerance

# intent_metrics
test_intent_accuracy_perfect
test_intent_accuracy_half
test_per_class_f1_calculation
test_confusion_matrix_shape
```

---

## Tier 2 — Integration Tests (real DB + Redis, mock LLM)

### 2.1 Fixtures (`integration/conftest.py`)

```python
# 1. Spin up a test PostgreSQL database (calendar_ai_test)
#    - Create tables via init_db()
#    - Truncate all tables between tests

# 2. Spin up Redis on the default port (reuse Docker Compose Redis)
#    - Flush the test keys between tests (FLUSHDB on a test-specific DB index)

# 3. Provide:
#    - async_session fixture → real AsyncSession
#    - test_user fixture → created User with known credentials
#    - test_events fixture → 5 events with various priorities/times
```

### 2.2 DB Event Lifecycle (`test_db_event_lifecycle.py`, 5 tests)

```
test_create_and_read_event            # adapter.create_event → adapter.get_event
test_update_event_fields              # change title + location, verify persistence
test_delete_event_removes_it          # delete → get returns None
test_date_range_query                 # create 3 events, query range returns 2
test_conflict_detection               # overlapping time → check_event_conflict returns event
```

### 2.3 DB User Lifecycle (`test_db_user_lifecycle.py`, 4 tests)

```
test_create_and_read_user
test_duplicate_email_raises
test_update_user_email
test_delete_user_cascades_events      # deleting user removes their events
```

### 2.4 Redis Checkpointer (`test_redis_checkpointer.py`, 3 tests)

```
test_aput_filters_non_message_fields  # only message arrays + confirmation state saved
test_roundtrip_messages               # aput → aget preserves router_messages
test_confirmation_state_persisted     # awaiting_confirmation + confirmation_type survive
```

### 2.5 Router Agent with Real State (`test_router_agent.py`, 3 tests)

Mock `model.ainvoke` to return canned JSON. Verify state mutation.

```
test_router_classifies_create         # mock response: {"route":"create","arguments":{...}}
test_router_classifies_list
test_router_skips_llm_when_awaiting_confirmation
```

---

## Tier 3 — End-to-End Tests (live API + live LLM)

Use `httpx.AsyncClient` with the real FastAPI app. Require a running PostgreSQL, Redis, and a valid `OPENAI_API_KEY`.

### 3.1 Auth Flow (`test_auth_flow.py`, 3 tests)

```
test_register_login_refresh
  1. POST /auth/register → 200, has access_token + refresh_token
  2. POST /auth/login with same creds → 200
  3. POST /auth/refresh with refresh_token → new access_token

test_login_wrong_password
  POST /auth/login with bad password → 401

test_protected_endpoint_without_token
  GET /events/ without Authorization header → 401 or 403
```

### 3.2 Calendar Flow via `/assistant/` (`test_calendar_flow.py`, 5 tests)

Each test sends natural language to `POST /assistant/` and validates the response shape.

```
test_create_event_via_assistant
  Input: "Schedule a meeting tomorrow at 2pm for 1 hour"
  Assert: response.type == "create", response.events is non-empty,
          events[0].title contains "meeting"

test_list_events_via_assistant
  Prereq: create event above
  Input: "What's on my calendar tomorrow?"
  Assert: response.type == "list", response.events includes the meeting

test_update_event_via_assistant
  Input: "Move the meeting to 4pm"
  Assert: response.type in ("update", "confirmation_required")
  If confirmation_required: send "yes", verify follow-up succeeds

test_delete_event_via_assistant
  Input: "Cancel the meeting tomorrow"
  Assert: response.type == "confirmation_required" (safety gate)
  Send "yes" → response confirms deletion

test_general_message_via_assistant
  Input: "Hello, how are you?"
  Assert: response has a message field, no events/actions
```

---

## Infrastructure & Configuration

### `pytest.ini` (or `pyproject.toml` section)

```ini
[pytest]
asyncio_mode = auto
markers =
    integration: requires real DB + Redis
    e2e: requires running backend + OpenAI API
testpaths = tests
filterwarnings =
    ignore::DeprecationWarning
```

### `conftest.py` (root)

```python
# Shared fixtures available to all tiers:
#
# mock_async_session   — AsyncMock of sqlalchemy AsyncSession
# mock_llm             — patches flow.llm.model.ainvoke with configurable responses
# sample_user          — User(id=1, user_id="test-uuid", name="Test", ...)
# sample_event         — Event(id="evt-uuid", title="Test Event", ...)
# sample_events        — list of 5 events with varied priorities/times
# auth_token           — valid JWT for sample_user
# auth_headers         — {"Authorization": "Bearer <token>"}
```

### Dependencies to install

```bash
pip install pytest pytest-asyncio httpx aiosqlite
```

Add to `requirements.txt` under a `# Testing` comment (or a separate `requirements-test.txt`).

---

## Execution Order

**Phase 1 — Scaffolding (do first)**
1. Create `tests/` directory structure
2. Write `conftest.py` with shared fixtures (mock session, mock LLM, sample data)
3. Write `pytest.ini`

**Phase 2 — Unit tests (bulk of the work)**
4. `test_models.py` — fastest to write, validates all Pydantic schemas
5. `test_jwt.py` + `test_password.py` — pure utility functions
6. `test_risk_assessment.py` — pure functions, no setup
7. `test_intent_metrics.py` + `test_slot_metrics.py` — eval module validation
8. `test_event_adapter.py` + `test_user_adapter.py` — mock DB session
9. `test_event_service.py` + `test_user_service.py` — mock adapters
10. `test_slot_finder.py` — mock MCP, test algorithm
11. `test_compaction.py` — mock LLM, test threshold logic

**Phase 3 — Integration tests**
12. `integration/conftest.py` — real DB + Redis fixtures
13. `test_db_event_lifecycle.py` + `test_db_user_lifecycle.py`
14. `test_redis_checkpointer.py`
15. `test_router_agent.py`

**Phase 4 — End-to-end tests**
16. `e2e/conftest.py` — TestClient + seeded data
17. `test_auth_flow.py`
18. `test_calendar_flow.py`

---

## Estimated Counts

| Category | Tests | Coverage target |
|----------|-------|----------------|
| Pydantic models | 14 | All models + response types |
| Utilities (JWT, password) | 12 | All functions + error paths |
| Risk assessment + slot finder | 14 | All pure logic |
| Eval metrics | 8 | F1, accuracy, confusion matrix |
| Adapters | 20 | All CRUD + error paths |
| Services | 18 | All methods + auth checks |
| Compaction | 5 | Threshold + trim logic |
| Integration (DB) | 9 | Lifecycle + cascade + conflicts |
| Integration (Redis + router) | 6 | Checkpointing + routing |
| E2E | 8 | Auth flow + full assistant flow |
| **Total** | **~114** | |
