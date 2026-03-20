# Implementation Progress

> Last updated: 2026-03-19

## Summary

| Plan | Title | Status | Progress |
|------|-------|--------|----------|
| PLAN-01 | Event Model Enhancements | ✅ Complete | 100% |
| PLAN-02 | MCP Integration Layer | ✅ Complete | 100% |
| PLAN-03 | Conflict Resolution Agent | ✅ Complete | 100% |
| PLAN-04 | Planner Agent (Router Upgrade) | ✅ Complete | 100% |
| PLAN-05 | Email RAG Pipeline | ✅ Complete | 100% |
| PLAN-06 | Conversation Memory & Safety | ✅ Complete | 100% |
| PLAN-07 | Evaluation Framework | ✅ Complete | 100% |

**Overall: 7 / 7 plans complete (100%)**

---

## PLAN-01 — Event Model Enhancements ✅

Added `priority`, `flexibility`, and `category` metadata fields throughout the full stack.

**Backend changes:**
- `database/models/event.py` — Added `EventPriority`, `EventFlexibility`, `EventCategory` SQLAlchemy enums and three new columns with `server_default`
- `models.py` — Added fields to `EventBase`, `EventCreate`, `EventUpdate`, `Event` Pydantic models
- `adapter/event_adapter.py` — Updated `_convert_to_model()`, `_convert_to_db_model()`, and `update_event()` to pass through new fields
- `database/migrate_add_event_metadata.py` — Migration script using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` with CHECK constraints
- `flow/create_agent/prompt.py` — Added inference heuristics and extraction rules for the three new fields
- `flow/update_agent/update_data_range_agent_prompt.py` — Added fields to `update_arguments` schema
- `flow/list_agent/list_filter_event_agent_prompt.py` — Added as filterable fields
- `flow/update_agent/update_filter_event_agent_prompt.py` — Added as filterable fields
- `flow/delete_agent/delete_filter_event_agent_prompt.py` — Added as filterable fields
- `flow/update_agent/update_agent.py` — Passes new fields when constructing `Event` objects from LLM output
- `services/assistant_service.py` — Passes new fields when building `EventCreate` from `create_event_data`

**Mobile changes:**
- `mobile/src/models/event.tsx` — Added `EventPriority`, `EventFlexibility`, `EventCategory` TypeScript types and optional fields to the `Event` interface

---

## PLAN-02 — MCP Integration Layer ✅

Introduced a FastMCP server and refactored all agents to communicate through it instead of importing `EventAdapter` directly.

**New files:**
- `backend/mcp_servers/__init__.py` — Package marker
- `backend/mcp_servers/calendar_server.py` — FastMCP server with 5 tools: `list_events`, `check_conflicts`, `create_event`, `update_event`, `delete_event`
- `backend/flow/mcp_client.py` — Shared async client utility (`call_calendar_tool`) used by all agents; uses in-process memory transport

**Refactored agents (removed direct adapter imports, now use MCP):**
- `flow/create_agent/create_agent.py` — `check_event_conflict` uses `call_calendar_tool("check_conflicts", ...)`
- `flow/list_agent/list_agent.py` — `list_event_by_date_range` uses `call_calendar_tool("list_events", ...)` + added `_dict_to_event()` helper
- `flow/delete_agent/delete_agent.py` — `delete_event_by_date_range` uses `call_calendar_tool("list_events", ...)` + added `_dict_to_event()` helper
- `flow/update_agent/update_agent.py` — `get_events_for_update` and conflict check use MCP tools + added `_dict_to_event()` helper

**Other:**
- `backend/requirements.txt` — Added `fastmcp>=2.3.0`

---

## PLAN-03 — Conflict Resolution Agent ✅

Added a multi-turn conflict resolution flow: when a new event conflicts with an existing one, the system classifies the conflict type, finds alternative time slots, presents numbered options to the user, and executes the chosen resolution via MCP.

**New files:**
- `flow/conflict_resolution_agent/__init__.py`
- `flow/conflict_resolution_agent/prompt.py` — `CONFLICT_RESOLUTION_PROMPT` for LLM explanation generation
- `flow/conflict_resolution_agent/slot_finder.py` — `find_available_slots()`: queries MCP for events, scans 8AM–10PM in 30-min increments, returns top 5 slots sorted by proximity to preferred time
- `flow/conflict_resolution_agent/conflict_resolution_agent.py` — Re-queries conflicts per new event, classifies resolution type (`suggest_alternatives` / `reschedule_existing` / `user_choice`), builds `resolution_plan`, calls LLM for explanation, sets `awaiting_confirmation=True`
- `flow/conflict_resolution_agent/confirmation_handler.py` — Parses user's choice (regex → word numbers → affirmatives → LLM fallback), executes via `create_event` / `update_event` MCP tools
- `mobile/src/components/ConflictResolutionComponent.tsx` — Numbered option card UI component

**Modified files:**
- `flow/state.py` — Added `resolution_plan: Optional[dict]`, `resolution_type: Optional[str]`, `awaiting_confirmation: bool`
- `flow/builder.py` — Added `conflict_resolution_agent` and `confirmation_handler` nodes; replaced `check_event_conflict → END` with conditional edge via `conflict_action`
- `flow/router_agent/router_agent.py` — Skips LLM when `awaiting_confirmation=True`; `route_action` shortcuts to `"confirmation_handler"` before normal routing
- `flow/redis_checkpointer.py` — Added `awaiting_confirmation`, `resolution_plan`, `resolution_type` to persisted fields set
- `models.py` — Added `ConflictResolutionOption` and `SuccessfulConflictResolutionResponse`
- `services/assistant_service.py` — Returns `SuccessfulConflictResolutionResponse` when `awaiting_confirmation=True`; handles `route == "confirmation"` for post-execution response
- `mobile/src/screens/HomeScreen.tsx` — Handles `conflict_resolution` response type, renders `ConflictResolutionComponent`, sends chosen option number back to assistant

**Resolution logic:**
| Condition | Strategy |
|-----------|----------|
| Existing event is `fixed` flexibility | `suggest_alternatives` — find new slot for new event |
| New is `mandatory`, existing is `optional` | `reschedule_existing` — move existing, create new as planned |
| New is `optional`, existing is `mandatory` | `suggest_alternatives` — find new slot for new event |
| Both same priority | `user_choice` — offer both sets of alternatives |

---

## PLAN-04 — Planner Agent ✅

Upgraded the router agent to detect complex multi-step requests and execute them via a new plan executor node, with a deterministic optimizer for slot placement and an LLM-generated summary.

**New files:**
- `flow/planner_agent/__init__.py`
- `flow/planner_agent/optimizer.py` — deterministic slot placement: scans preferred time windows (morning/afternoon/evening/any) in 30-min increments, buffers 15 min around existing events, supports weekday/weekend/all day specs
- `flow/planner_agent/focus_slots.py` — `FocusSlot` dataclass + `materialize_focus_slots()`: converts recurring templates into concrete events via optimizer + MCP
- `flow/planner_agent/summarizer.py` — LLM-based change summarizer using structured change log
- `flow/planner_agent/plan_executor.py` — orchestrates task execution; supports operations: `list`, `create`, `create_optimized`, `update_matching`, `delete_matching`, `email_retrieval` (stub); LLM-based event matching for update/delete; email trigger detection

**Modified files:**
- `flow/router_agent/prompt.py` — extended with `"plan"` route detection, task decomposition schema, and full param schemas for all 5 operation types
- `flow/router_agent/router_agent.py` — added `case "plan": return "plan_executor"` to `route_action`
- `flow/state.py` — added `plan_tasks`, `plan_results`, `plan_summary`, `is_planning_mode`
- `flow/builder.py` — added `plan_executor` node + `plan_executor → END` edge
- `models.py` — added `PlanChange` and `SuccessfulPlanResponse`
- `services/assistant_service.py` — returns `SuccessfulPlanResponse` when `is_planning_mode=True`
- `mobile/src/screens/HomeScreen.tsx` — handles `plan_summary` response type; renders inline change log with color-coded action labels (created=green, deleted=red, updated=blue)

---

## PLAN-05 — Email RAG Pipeline ✅

Full Gmail RAG pipeline: OAuth2 auth, MCP server, ChromaDB vector store with incremental indexing, LLM event extraction with confidence scoring, and a LangGraph node integrated into the main flow.

**New files:**
- `mcp_servers/email_auth.py` — OAuth2 helper: `get_gmail_credentials()` (loads/refreshes per-user JSON tokens), `get_auth_url()`, `exchange_code()`, `has_gmail_access()`
- `mcp_servers/email_server.py` — FastMCP server with `search_emails` (Gmail API query + metadata) and `get_email_content` (full body, HTML→text via BeautifulSoup)
- `flow/email_pipeline/__init__.py`
- `flow/email_pipeline/email_mcp_client.py` — `call_email_tool()` following the same pattern as `call_calendar_tool()`
- `flow/email_pipeline/embeddings.py` — `EmailVectorStore`: per-user ChromaDB collection; paragraph/sentence chunking (500 chars, 50-char overlap) with subject+sender prefix; `ingest_emails()`, `search()`, `get_indexed_email_ids()`
- `flow/email_pipeline/extractor.py` — LLM extraction with three confidence tiers: high (confirmations/invites), medium (requests/proposals), low (casual mentions)
- `flow/email_pipeline/index_manager.py` — `refresh_email_index()` (incremental, rate-limited via Redis timestamp), `full_reindex()` (first-time setup, last N days)
- `flow/email_pipeline/email_agent.py` — LangGraph node: generates search query via LLM → refreshes index → semantic search → extracts events → returns grouped proposals
- `controller/google_auth_controller.py` — 4 endpoints: `GET /auth/google/connect`, `GET /auth/google/callback`, `GET /auth/google/status`, `DELETE /auth/google/disconnect`
- `mobile/src/components/EmailExtractionComponent.tsx` — confidence-tiered card UI: high=green pre-selected, medium=yellow unchecked, low=grey text; "Add Selected" button

**Modified files:**
- `requirements.txt` — added `chromadb`, `sentence-transformers`, `google-api-python-client`, `google-auth-oauthlib`, `google-auth-httplib2`, `beautifulsoup4`
- `config.py` — added `GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI`, `CHROMA_PERSIST_DIR`, `GMAIL_CREDENTIALS_DIR`, `EMBEDDING_MODEL`, `EMAIL_INDEX_REFRESH_MINUTES`
- `flow/state.py` — added `email_messages`, `email_extracted_events`, `email_search_results`
- `flow/builder.py` — added `email_retrieval_agent` node + edge to END
- `flow/router_agent/prompt.py` — added `"email"` route classification
- `flow/router_agent/router_agent.py` — added `case "email": return "email_retrieval_agent"`
- `flow/redis_checkpointer.py` — added `email_messages` to persisted fields
- `flow/planner_agent/plan_executor.py` — `email_retrieval` task now uses real pipeline (with `has_gmail_access` guard)
- `models.py` — added `ExtractedEmailEvent` and `EmailExtractionResponse`
- `services/assistant_service.py` — returns `EmailExtractionResponse` when `email_extracted_events` is set
- `main.py` — registered `google_auth_router`
- `mobile/src/screens/HomeScreen.tsx` — handles `email_extraction` type; `handleAddEmailEvents` creates selected events via `addEvents`
- `.gitignore` — added `backend/data/chroma/` and `backend/data/gmail_credentials/`

**Setup required (dev):**
```
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/auth/google/callback
```
First-time: call `GET /auth/google/connect` (JWT required) → open URL in browser → grants access → callback saves tokens → all subsequent calls auto-refresh.

---

## PLAN-06 — Conversation Memory & Safety ✅

**Part A — Context Compaction:**
- `flow/memory/__init__.py` — package marker
- `flow/memory/compaction.py` — `compact_if_needed(messages)`: threshold=15, compact oldest 10 into LLM summary SystemMessage, keep 5; `memory_compaction_node` runs over all 6 message arrays
- `flow/builder.py` — `START → memory_compaction → router_agent` (replaces direct START → router_agent)

**Part B — Confirmation-First Safety:**
- `flow/safety/__init__.py` — package marker
- `flow/safety/risk_assessment.py` — `RiskLevel` enum; `assess_delete_risk()` (always HIGH for ≥1 event); `assess_update_risk()` (HIGH for mandatory/fixed or ≥3 events); `detect_ambiguity()` (warns if >5 matched events)
- `flow/safety/delete_safety_gate.py` — node after `delete_filter_event_agent`; HIGH risk sets `awaiting_confirmation=True`, `confirmation_type="delete_safety"`, appends confirmation message to `delete_messages`
- `flow/safety/update_safety_gate.py` — node after `update_filter_event_agent`; same pattern for `"update_safety"`
- `flow/safety/safety_confirmation_handler.py` — parses yes/no; executes `delete_event`/`update_event` via MCP on confirm; cancels cleanly on no/unclear
- `flow/state.py` — added `confirmation_type: Optional[str]`, `confirmation_data: Optional[dict]`
- `flow/builder.py` — added safety gate nodes + edges; added `safety_confirmation_handler` node
- `flow/router_agent/router_agent.py` — `route_action` checks `confirmation_type` to dispatch to `safety_confirmation_handler` vs `confirmation_handler`
- `flow/redis_checkpointer.py` — added `confirmation_type`, `confirmation_data` to persisted fields
- `models.py` — added `ConfirmationRequiredResponse`
- `services/assistant_service.py` — returns `ConfirmationRequiredResponse` when safety gate fires; returns text result after handler executes
- `mobile/src/components/SafetyConfirmationComponent.tsx` — delete=red theme, update=yellow theme; event list; Confirm/Cancel buttons
- `mobile/src/screens/HomeScreen.tsx` — handles `confirmation_required` responseType; `handleSafetyConfirm`/`handleSafetyCancel` send yes/no back to assistant

---

## PLAN-07 — Evaluation Framework ✅

**New files (all under `backend/eval/`):**

- `dataset/test_cases.json` — 28 labeled test cases across 7 categories (create×7, update×4, delete×4, list×5, plan×3, email×2, message×4); each case has `input`, `context` (datetime/weekday), and `expected` (route + slots)

- `baseline/single_agent.py` — GPT-4.1 with 7 OpenAI function-call tools (create_event, list_events, update_events, delete_events, plan_schedule, search_emails_for_events, respond_to_user); maps tool name → route; returns extracted_slots, latency_ms

- `metrics/intent_metrics.py` — `compute_intent_metrics()`: accuracy, macro-F1, per-class P/R/F1/support, confusion matrix; `format_intent_report()` tabular printer

- `metrics/slot_metrics.py` — `compute_slot_f1()`: flexible value matching (string substring, ±20% numeric tolerance); `compute_aggregate_slot_metrics()`: micro-F1 aggregation over create cases

- `metrics/end_to_end_metrics.py` — `compute_end_to_end_metrics()`: task completion rate, avg/median/p95/p99 latency, avg turns; `compare_end_to_end()`: delta/relative comparison between systems

- `judge/llm_judge.py` — `judge_response()`: GPT-4.1 scores naturalness/helpfulness/accuracy 1–5 with JSON output; `aggregate_judge_scores()`: mean across valid scored cases

- `runner/harness.py` — `run_harness()`: concurrent A/B evaluation; calls router directly (no DB needed), runs baseline in parallel; assembles intent + slot + e2e + judge metrics per system

- `runner/report.py` — `print_summary()`: formatted console A/B comparison; `save_report()`: JSON dump with LangChain message serialisation

- `run_eval.py` — CLI entry point with `--judge`, `--filter`, `--output`, `--concurrency`, `--list-cases` flags

**Usage:**
```bash
cd backend
python -m eval.run_eval                        # router + baseline comparison
python -m eval.run_eval --judge                # add LLM judge scoring
python -m eval.run_eval --filter create list   # subset of categories
python -m eval.run_eval --output eval/results/ # save JSON report
python -m eval.run_eval --list-cases           # enumerate test cases
```
