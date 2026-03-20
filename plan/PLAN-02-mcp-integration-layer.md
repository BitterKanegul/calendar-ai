# PLAN-02: MCP Integration Layer

## Goal

Introduce Model Context Protocol (MCP) servers as the standardized interface between agents and external services. This decouples agent reasoning from service-specific logic, enabling service portability (e.g., swapping PostgreSQL for Google Calendar without changing agent code).

---

## Current State

- Agents in `flow/` directly import and call `event_adapter.py` functions (e.g., `EventAdapter().get_events_by_date_range()`)
- No MCP infrastructure exists
- `requirements.txt` has no MCP-related packages
- The proposal requires three MCP servers: Calendar, Email, Event Search (stretch)

---

## Architecture Decision

Use **FastMCP** (the Python MCP SDK) to build MCP servers. Each server runs as a subprocess or is connected via stdio transport. LangGraph agents interact with MCP servers through an MCP client that discovers and invokes tools.

Two deployment options:
1. **In-process (recommended for now)**: MCP servers run within the same Python process using FastMCP's direct integration, avoiding network overhead during development
2. **Subprocess/stdio**: MCP servers run as separate processes, communicated with via stdio — better for production isolation

Start with option 1 for development simplicity; the MCP protocol ensures you can switch to option 2 later without changing agent code.

---

## Implementation Steps

### Step 1: Add MCP dependencies

**File: `backend/requirements.txt`**

```
fastmcp>=2.0.0
```

FastMCP v2+ includes both server and client functionality.

### Step 2: Create the Calendar MCP Server

**New file: `backend/mcp_servers/calendar_server.py`**

```python
from fastmcp import FastMCP

mcp = FastMCP("Calendar")

@mcp.tool()
async def create_event(title: str, start_date: str, end_date: str,
                       location: str = None, priority: str = "optional",
                       flexibility: str = "movable", category: str = "personal",
                       user_id: int = None) -> dict:
    """Create a calendar event."""
    # Delegate to EventAdapter
    ...

@mcp.tool()
async def update_event(event_id: str, user_id: int, **fields) -> dict:
    """Update an existing calendar event."""
    ...

@mcp.tool()
async def delete_event(event_id: str, user_id: int) -> dict:
    """Delete a calendar event."""
    ...

@mcp.tool()
async def list_events(user_id: int, start_date: str = None,
                      end_date: str = None) -> list[dict]:
    """List calendar events within a date range."""
    ...

@mcp.tool()
async def check_conflicts(user_id: int, start_date: str,
                          end_date: str, exclude_event_id: str = None) -> list[dict]:
    """Check for time conflicts with existing events."""
    ...
```

**Key design decisions:**
- Each tool receives `user_id` as a parameter (the agent passes it from FlowState)
- Tools internally use `EventAdapter` for database access, maintaining the existing data layer
- Tools return plain dicts (JSON-serializable), not SQLAlchemy models
- The MCP server needs access to the async database session — pass the session factory or use a dependency injection pattern

### Step 3: Create MCP client utility for agents

**New file: `backend/flow/mcp_client.py`**

Create a utility that agents use to call MCP tools:

```python
from fastmcp import Client

async def get_mcp_client():
    """Get an MCP client connected to the Calendar server."""
    from mcp_servers.calendar_server import mcp
    client = Client(mcp)
    return client

async def call_tool(server_name: str, tool_name: str, arguments: dict) -> Any:
    """Call an MCP tool and return the result."""
    client = await get_mcp_client()  # or route by server_name
    async with client:
        result = await client.call_tool(tool_name, arguments)
        return result
```

### Step 4: Refactor create_agent to use MCP tools

**File: `backend/flow/create_agent/create_agent.py`**

Current flow:
1. LLM extracts event data → stored in `state["create_event_data"]`
2. `check_event_conflict` calls `EventAdapter().check_event_conflict()` directly
3. Event creation happens in `assistant_service.py` after the flow completes

Refactored flow:
1. LLM extracts event data (unchanged)
2. `check_event_conflict` node calls `call_tool("calendar", "check_conflicts", {...})`
3. If no conflict, call `call_tool("calendar", "create_event", {...})` within the flow itself

This moves event creation inside the LangGraph flow, which is necessary for the Planner Agent to orchestrate multi-step operations.

### Step 5: Refactor list_agent to use MCP tools

**File: `backend/flow/list_agent/list_agent.py`**

- `list_event_by_date_range()`: Replace `EventAdapter().get_events_by_date_range()` with `call_tool("calendar", "list_events", {...})`

### Step 6: Refactor update_agent to use MCP tools

**File: `backend/flow/update_agent/update_agent.py`**

- `get_events_for_update()`: Replace adapter call with `call_tool("calendar", "list_events", {...})`
- `update_filter_event_agent()`: Replace adapter update call with `call_tool("calendar", "update_event", {...})`
- Conflict check: Replace with `call_tool("calendar", "check_conflicts", {...})`

### Step 7: Refactor delete_agent to use MCP tools

**File: `backend/flow/delete_agent/delete_agent.py`**

- `delete_event_by_date_range()`: Replace adapter call with `call_tool("calendar", "list_events", {...})`
- Deletion: Replace with `call_tool("calendar", "delete_event", {...})`

### Step 8: Update assistant_service.py

**File: `backend/services/assistant_service.py`**

- Remove direct event creation/update/deletion after flow completion (this is now handled inside the flow via MCP tools)
- The flow's final state should contain the operation results, which `assistant_service` formats and returns

### Step 9: Handle database session lifecycle

The MCP tools need async database sessions. Options:

**Option A (recommended)**: Pass the session factory to the MCP server at startup:
```python
# In main.py or calendar_server.py
from database.config import async_session_factory
mcp.state["db_session_factory"] = async_session_factory
```

**Option B**: Use FastMCP's context/dependency system to inject the session per-request.

### Step 10: Verify existing REST endpoints still work

The `event_controller.py` REST endpoints should continue to work unchanged — they call `event_service.py` directly, not through MCP. MCP is only for agent-to-service communication.

---

## Directory Structure After Implementation

```
backend/
├── mcp_servers/
│   ├── __init__.py
│   ├── calendar_server.py      # Calendar MCP Server
│   └── email_server.py         # (PLAN-05, Email MCP Server)
├── flow/
│   ├── mcp_client.py           # MCP client utility
│   ├── create_agent/           # Refactored to use MCP
│   ├── list_agent/             # Refactored to use MCP
│   ├── update_agent/           # Refactored to use MCP
│   └── delete_agent/           # Refactored to use MCP
```

---

## Testing Strategy

1. **MCP server unit test**: Instantiate the Calendar MCP server, call each tool directly with test data, verify correct adapter calls and return values
2. **MCP client integration test**: Use FastMCP's `Client` to connect to the server in-process and call tools end-to-end
3. **Flow regression test**: Run the full LangGraph flow via `/assistant/` with create/list/update/delete requests. Verify identical behavior to the pre-MCP version.
4. **REST endpoint regression**: Verify `POST /events`, `GET /events`, etc. still work (they bypass MCP)

---

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Async session sharing between MCP server and FastAPI | Use separate session instances per MCP tool call; don't share sessions across contexts |
| Performance overhead of MCP protocol | Start with in-process FastMCP (negligible overhead); benchmark before adding network transport |
| Breaking existing agent flows | Implement incrementally — refactor one agent at a time, verify each before moving to the next |

---

## Files Modified/Created (Summary)

| File | Change |
|------|--------|
| `requirements.txt` | Add `fastmcp` |
| `mcp_servers/__init__.py` | **New** |
| `mcp_servers/calendar_server.py` | **New** Calendar MCP Server |
| `flow/mcp_client.py` | **New** MCP client utility |
| `flow/create_agent/create_agent.py` | Refactor to use MCP tools |
| `flow/list_agent/list_agent.py` | Refactor to use MCP tools |
| `flow/update_agent/update_agent.py` | Refactor to use MCP tools |
| `flow/delete_agent/delete_agent.py` | Refactor to use MCP tools |
| `services/assistant_service.py` | Remove post-flow direct DB calls |
