# TODO Plan: Calen — Current State → Proposal Target

This document maps the gap between the existing codebase and the project proposal, organized by priority.

---

## Legend

- **[NEW]** — Feature does not exist yet; must be built from scratch
- **[MODIFY]** — Existing code needs changes to meet proposal requirements
- **[STRETCH]** — Stretch scope per the proposal

---

## 1. MCP Integration Layer

The proposal's core architectural differentiator is MCP (Model Context Protocol) for all external service connections. The current codebase has no MCP usage — agents call adapters/services directly.

### 1.1 [NEW] Calendar MCP Server (FastMCP)
- Build a FastMCP server wrapping calendar operations
- Expose tools: `create_event`, `update_event`, `delete_event`, `list_events`, `check_conflicts`
- **Currently:** Agents call `event_service.py` / `event_adapter.py` directly via Python functions in the LangGraph nodes
- **Target:** Agents invoke calendar tools through standardized MCP tool interface

### 1.2 [NEW] Email MCP Server (FastMCP)
- Build a FastMCP server wrapping the Gmail API
- Expose tools: `search_emails`, `get_email_content`
- Requires Gmail API OAuth2 setup and credentials

### 1.3 [STRETCH] Event Search MCP Server
- Wraps Ticketmaster / SeatGeek APIs for leisure event discovery
- Tools: `search_events`, `get_event_details`

### 1.4 [MODIFY] Agent nodes to use MCP clients
- **Files:** All files under `flow/` (create_agent, list_agent, update_agent, delete_agent)
- Currently agents call Python service functions directly; refactor to invoke MCP tool endpoints via MCP clients

---

## 2. Agent Architecture Upgrades

The current LangGraph flow has a basic router + CRUD agents. The proposal requires a significantly richer agent system.

### 2.1 [MODIFY] Router Agent → Planner Agent
- **File:** `flow/router_agent/`
- **Currently:** Simple intent classifier that routes to create/list/update/delete
- **Target:** Full Planner Agent with:
  - Multi-step task decomposition (e.g., "plan my week" → multiple sub-tasks)
  - Utility-based schedule optimization (priority weighting, preference matching)
  - Focus slot management (reserve and dynamically relocate time blocks)
  - Proactive email awareness (trigger RAG pipeline when context suggests it)
  - Conversational feedback and change summaries after multi-step operations

### 2.2 [MODIFY] Conflict Detection → Conflict Resolution Agent
- **File:** `flow/builder.py` (the `check_event_conflict` node), `services/event_service.py`
- **Currently:** Binary conflict check — detects overlap, blocks creation
- **Target:** Dedicated Conflict Resolution Agent that:
  - Evaluates priority and flexibility of conflicting events
  - Suggests ranked alternative time slots
  - Handles bulk/recursive conflict resolution for recurring events
  - Presents tradeoff explanations and asks for user confirmation

### 2.3 [NEW] Email Retrieval Pipeline (RAG)
- Build a full RAG pipeline:
  - **Ingestion:** Fetch emails via Email MCP Server, parse .ics attachments
  - **Chunking + Embedding:** Chunk email content, embed into vector store (ChromaDB or FAISS)
  - **Retrieval:** Semantic search over vector store given user query / scheduling context
  - **Extraction:** LLM extracts structured event data from retrieved chunks
- New tools: `embed_and_store`, `semantic_search`, `extract_events_from_text`
- Support explicit retrieval ("check my email") and contextual retrieval ("my flight Thursday")
- Confidence-based handling: high confidence for structured emails, confirmation-required for informal mentions

### 2.4 [STRETCH] Leisure Search Agent
- New agent that queries Event Search MCP Server
- Filters results by user preferences, free time, location
- Passes selected events to Scheduling Agent for creation

---

## 3. Event Model Enhancements

### 3.1 [MODIFY] Add event metadata fields
- **Files:** `database/models/event.py`, `models.py` (Pydantic schemas), `adapter/event_adapter.py`
- Add fields per proposal:
  - `priority`: enum (mandatory / optional)
  - `flexibility`: enum (fixed / movable)
  - `category`: enum (work / study / personal / leisure)
- Update all CRUD flows to handle new fields
- Update mobile app models and UI to support new fields

---

## 4. Google Calendar Integration

### 4.1 [MODIFY] Switch from internal DB to Google Calendar as primary data source
- **Currently:** Events stored in PostgreSQL via custom models
- **Target:** Calendar MCP Server wraps Google Calendar API; internal DB may serve as cache or be replaced
- Requires Google Calendar API OAuth2 setup
- **Decision needed:** Keep PostgreSQL as source of truth with Google Calendar sync, or make Google Calendar the primary store?

---

## 5. Conversation & Memory

### 5.1 [MODIFY] Short-term memory with context compaction
- **File:** `flow/redis_checkpointer.py`, `flow/state.py`
- **Currently:** Redis checkpointer persists message arrays between turns
- **Target:** Add context compaction — summarize older conversation turns while preserving key entities and decisions to stay within token limits during extended sessions

### 5.2 [MODIFY] Confirmation-first safety policy
- **Files:** `flow/builder.py`, agent nodes
- Add confirmation gates before destructive/ambiguous operations:
  - Low-confidence email extractions
  - Ambiguous event references ("delete that meeting" with multiple candidates)
  - High-impact modifications (rescheduling mandatory events)
- Planner Agent enforces this before delegating to downstream agents

---

## 6. Mobile App Updates

### 6.1 [MODIFY] Support new event metadata in UI
- **Files:** `mobile/src/models/event.tsx`, `mobile/src/components/AddEventModal.tsx`, `mobile/src/components/UpdateEventModal.tsx`
- Add priority, flexibility, and category pickers to event creation/editing

### 6.2 [MODIFY] Enhanced AI feedback display
- **File:** `mobile/src/components/AssistantFeedback.tsx`
- Support richer conversational feedback: multi-step summaries, conflict resolution options, confirmation prompts
- Handle confirmation workflows (user approves/rejects proposed changes)

### 6.3 [MODIFY] API service updates
- **File:** `mobile/src/services/api.ts`
- Add endpoints/parameters for new features (email retrieval trigger, confirmation responses, new event fields)

---

## 7. Evaluation Framework

### 7.1 [NEW] Single-agent baseline
- Build a single LLM agent with direct access to the same MCP tools
- All reasoning (decomposition, conflict handling, retrieval) in one prompt/context
- Used for comparative evaluation against the multi-agent system

### 7.2 [NEW] Test scenario suite
- Create labeled test sets:
  - Simple CRUD tasks ("Create a meeting at 3 PM tomorrow")
  - Complex multi-step tasks ("Plan my week, check email for missing events, add study time around classes")
  - Conflict resolution scenarios
  - Email extraction scenarios (structured confirmations + informal mentions)

### 7.3 [NEW] Evaluation metrics implementation
- Task completion rate measurement
- Constraint satisfaction scoring (hard + soft constraints)
- Conflict resolution quality assessment
- Interaction turn counting
- Unnecessary tool call tracking
- Intent classification accuracy (precision, recall, F1)
- Email retrieval quality (precision@k, recall@k)

### 7.4 [NEW] LLM-as-a-judge evaluation
- Automated qualitative assessment of conversational quality, response clarity, logical consistency
- End-to-end scenario walkthroughs

---

## Suggested Implementation Order

1. **Event model enhancements** (3.1) — foundational; everything else builds on richer event metadata
2. **MCP Calendar Server** (1.1) — enables the standardized tool interface pattern
3. **Planner Agent upgrade** (2.1) — core orchestration improvements
4. **Conflict Resolution Agent** (2.2) — depends on priority/flexibility metadata
5. **Email MCP Server + RAG pipeline** (1.2, 2.3) — parallel workstream, independent of calendar changes
6. **Google Calendar integration** (4.1) — can be deferred; current PostgreSQL backend works for development
7. **Memory & safety** (5.1, 5.2) — polish after core agents work
8. **Mobile app updates** (6.x) — after backend APIs stabilize
9. **Evaluation framework** (7.x) — build alongside or after features; baseline can be started early
10. **Stretch features** (1.3, 2.4) — only if time permits
