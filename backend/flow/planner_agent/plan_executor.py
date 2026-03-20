"""
Plan Executor

Orchestrates multi-step calendar planning by executing an ordered task list
produced by the planner LLM. Calls MCP tools directly for each step and
uses the optimizer for `create_optimized` tasks.

Supported task operations:
  - list            : fetch events for a date range
  - create          : create events with explicit start times
  - create_optimized: use optimizer to place events in free slots
  - update_matching : find events matching a text description, then update fields
  - delete_matching : find events matching a text description, then delete them
"""
import logging
from datetime import datetime, timedelta
from langchain_core.messages import AIMessage, SystemMessage

from ..state import FlowState
from ..mcp_client import call_calendar_tool
from ..llm import model
from .optimizer import optimize_templates
from .summarizer import generate_summary

logger = logging.getLogger(__name__)

# How many days to search when a task has no explicit date range
DEFAULT_SEARCH_DAYS = 7

# Email-trigger keywords — stub until PLAN-05 is implemented
EMAIL_TRIGGERS = {"email", "inbox", "missing", "forgot", "check if"}


def _has_email_trigger(text: str) -> bool:
    return any(kw in text.lower() for kw in EMAIL_TRIGGERS)


def _fmt(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%a %b %d at %I:%M %p")
    except Exception:
        return iso


async def _match_events_by_description(
    events: list[dict],
    filter_description: str,
) -> list[dict]:
    """
    Use the LLM to select which events from the list match the filter description.
    Returns matching event dicts.
    """
    if not events:
        return []

    events_text = "\n".join(
        f"{i+1}. {ev.get('title')} — {_fmt(ev.get('startDate',''))} (id={ev.get('id')})"
        for i, ev in enumerate(events)
    )
    prompt = (
        f"From this list of calendar events:\n{events_text}\n\n"
        f"Which events match this description: \"{filter_description}\"?\n\n"
        f"Reply with ONLY a JSON array of the matching event IDs, e.g. [\"id1\",\"id2\"]. "
        f"If none match, reply with []."
    )
    try:
        response = await model.ainvoke([SystemMessage(content=prompt)])
        import json
        ids = json.loads(response.content.strip())
        return [ev for ev in events if ev.get("id") in ids]
    except Exception:
        return []


async def _execute_task(
    task: dict,
    user_id: int,
    step_results: dict,   # step_num → {"events": [...], "params": {...}}
    changes: list[dict],
) -> list[dict]:
    """
    Execute a single plan task. Returns list of resulting event dicts.
    """
    operation = task.get("operation", "")
    params = task.get("params", {})
    depends_on = task.get("depends_on", [])

    # Collect events from dependency steps
    dep_events: list[dict] = []
    dep_params: dict = {}
    for dep_step in depends_on:
        if dep_step in step_results:
            dep_events.extend(step_results[dep_step].get("events", []))
            dep_params.update(step_results[dep_step].get("params", {}))

    # ── LIST ──────────────────────────────────────────────────────────────────
    if operation == "list":
        start = params.get("start_date")
        end = params.get("end_date")
        try:
            result = await call_calendar_tool("list_events", {
                "user_id": user_id,
                "start_date": start,
                "end_date": end,
            }) or []
        except Exception as e:
            logger.warning(f"list task failed: {e}")
            result = []
        return result

    # ── CREATE (explicit times) ───────────────────────────────────────────────
    if operation == "create":
        created = []
        for ev in params.get("events", []):
            try:
                result = await call_calendar_tool("create_event", {
                    "user_id":     user_id,
                    "title":       ev.get("title"),
                    "start_date":  ev.get("startDate"),
                    "duration":    ev.get("duration", 60),
                    "location":    ev.get("location"),
                    "priority":    ev.get("priority", "optional"),
                    "flexibility": ev.get("flexibility", "movable"),
                    "category":    ev.get("category", "personal"),
                })
                if result:
                    created.append(result)
                    changes.append({
                        "action": "created",
                        "event": result,
                    })
            except Exception as e:
                logger.warning(f"create task event failed: {e}")
        return created

    # ── CREATE OPTIMIZED (optimizer finds slots) ──────────────────────────────
    if operation == "create_optimized":
        # Date range: from dependency list step's params, or use current week
        range_start = dep_params.get("start_date") or params.get("start_date")
        range_end   = dep_params.get("end_date")   or params.get("end_date")

        if not range_start:
            range_start = datetime.now().replace(hour=0, minute=0, second=0).isoformat()
        if not range_end:
            range_end = (
                datetime.fromisoformat(range_start) + timedelta(days=DEFAULT_SEARCH_DAYS)
            ).isoformat()

        templates = params.get("events", [])
        placed = optimize_templates(templates, dep_events, range_start, range_end)

        created = []
        for ev in placed:
            try:
                result = await call_calendar_tool("create_event", {
                    "user_id":     user_id,
                    "title":       ev.get("title"),
                    "start_date":  ev.get("startDate"),
                    "duration":    ev.get("duration", 60),
                    "location":    ev.get("location"),
                    "priority":    ev.get("priority", "optional"),
                    "flexibility": ev.get("flexibility", "movable"),
                    "category":    ev.get("category", "personal"),
                })
                if result:
                    created.append(result)
                    changes.append({
                        "action": "created",
                        "event": result,
                        "detail": "placed in optimized slot",
                    })
            except Exception as e:
                logger.warning(f"create_optimized event failed: {e}")
        return created

    # ── UPDATE MATCHING ───────────────────────────────────────────────────────
    if operation == "update_matching":
        filter_desc = params.get("filter_description", "")
        updates = params.get("updates", {})

        # Use dep_events if available, otherwise fetch a broad range
        pool = dep_events
        if not pool:
            try:
                pool = await call_calendar_tool("list_events", {
                    "user_id": user_id,
                }) or []
            except Exception:
                pool = []

        matched = await _match_events_by_description(pool, filter_desc)
        updated = []
        for ev in matched:
            try:
                result = await call_calendar_tool("update_event", {
                    "event_id": ev.get("id"),
                    "user_id":  user_id,
                    **updates,
                })
                if result:
                    updated.append(result)
                    changes.append({
                        "action": "updated",
                        "event": result,
                        "detail": f"matched '{filter_desc}'",
                    })
            except Exception as e:
                logger.warning(f"update_matching event failed: {e}")
        return updated

    # ── DELETE MATCHING ───────────────────────────────────────────────────────
    if operation == "delete_matching":
        filter_desc = params.get("filter_description", "")

        pool = dep_events
        if not pool:
            try:
                pool = await call_calendar_tool("list_events", {
                    "user_id": user_id,
                }) or []
            except Exception:
                pool = []

        matched = await _match_events_by_description(pool, filter_desc)
        deleted = []
        for ev in matched:
            try:
                await call_calendar_tool("delete_event", {
                    "event_id": ev.get("id"),
                    "user_id":  user_id,
                })
                deleted.append(ev)
                changes.append({
                    "action": "deleted",
                    "event": ev,
                    "detail": f"matched '{filter_desc}'",
                })
            except Exception as e:
                logger.warning(f"delete_matching event failed: {e}")
        return deleted

    # ── EMAIL RETRIEVAL ───────────────────────────────────────────────────────
    if operation == "email_retrieval":
        try:
            from flow.email_pipeline.embeddings import EmailVectorStore
            from flow.email_pipeline.extractor import extract_events_from_chunks
            from flow.email_pipeline.index_manager import refresh_email_index
            from flow.email_pipeline.email_mcp_client import call_email_tool
            from mcp_servers.email_auth import has_gmail_access

            if not has_gmail_access(user_id):
                logger.info(f"Email retrieval skipped — no Gmail credentials for user {user_id}")
                return []

            store = EmailVectorStore(user_id)
            await refresh_email_index(store, user_id, call_email_tool)
            query = params.get("query", "meeting appointment schedule")
            chunks = store.search(query, top_k=10)
            extracted = await extract_events_from_chunks(chunks)
            # Return high+medium events as a flat list for the plan executor
            return extracted.get("high", []) + extracted.get("medium", [])
        except Exception as e:
            logger.warning(f"Email retrieval in plan_executor failed: {e}")
            return []

    logger.warning(f"Unknown plan operation: {operation}")
    return []


async def plan_executor(state: FlowState) -> FlowState:
    """
    Execute a multi-step plan from state['route']['tasks'].

    Sets state['plan_results'], state['plan_summary'], state['is_planning_mode'].
    """
    route_data = state.get("route", {})
    tasks: list[dict] = route_data.get("tasks", []) if isinstance(route_data, dict) else []
    user_id = state["user_id"]
    input_text = state.get("input_text", "")

    # Optionally inject an email retrieval step if keywords are present
    if _has_email_trigger(input_text) and not any(
        t.get("operation") == "email_retrieval" for t in tasks
    ):
        tasks = [{"step": 0, "operation": "email_retrieval", "description": "Check emails for scheduling content", "depends_on": [], "params": {}}] + tasks

    if not tasks:
        state["create_messages"].append(AIMessage(content="I couldn't figure out a plan for that. Could you rephrase?"))
        state["is_planning_mode"] = True
        state["is_success"] = True
        return state

    changes: list[dict] = []
    step_results: dict = {}  # step_num → {"events": [...], "params": {...}}

    for task in sorted(tasks, key=lambda t: t.get("step", 0)):
        step_num = task.get("step", 0)
        try:
            result_events = await _execute_task(task, user_id, step_results, changes)
            step_results[step_num] = {
                "events": result_events,
                "params": task.get("params", {}),
            }
        except Exception as e:
            logger.error(f"Plan step {step_num} ({task.get('operation')}) failed: {e}")
            step_results[step_num] = {"events": [], "params": {}}

    # Generate natural language summary
    try:
        summary = await generate_summary(changes)
    except Exception:
        summary = f"Done! Completed {len(tasks)} planning step(s)."

    state["plan_results"] = changes
    state["plan_summary"] = summary
    state["is_planning_mode"] = True
    state["is_success"] = True
    state["create_messages"].append(AIMessage(content=summary))

    return state
