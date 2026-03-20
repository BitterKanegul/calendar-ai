"""
Single-agent baseline: one GPT-4.1 call with all calendar tools exposed via
OpenAI function-calling.  Used as the A/B comparison target against the
multi-agent LangGraph system.

The baseline intentionally avoids all specialisation: no separate router,
no dedicated slot-extraction agents, no conflict checks — just one LLM that
picks the right tool and fills in the arguments.
"""

import json
import time
import logging
from openai import AsyncOpenAI
from config import settings

logger = logging.getLogger(__name__)

# ── Tool schemas ──────────────────────────────────────────────────────────────

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "create_event",
            "description": "Create one or more new calendar events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title"},
                    "startDate": {"type": "string", "description": "ISO 8601 datetime"},
                    "duration": {"type": "integer", "description": "Duration in minutes"},
                    "location": {"type": "string"},
                    "priority": {"type": "string", "enum": ["mandatory", "optional"]},
                    "flexibility": {"type": "string", "enum": ["fixed", "movable", "flexible"]},
                    "category": {
                        "type": "string",
                        "enum": ["work", "personal", "health", "social", "other"],
                    },
                },
                "required": ["title", "startDate"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_events",
            "description": "List calendar events within a date range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string", "description": "ISO 8601 date"},
                    "end_date": {"type": "string", "description": "ISO 8601 date"},
                    "title_filter": {"type": "string", "description": "Optional keyword filter"},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_events",
            "description": "Update one or more existing calendar events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "title_filter": {"type": "string"},
                    "new_title": {"type": "string"},
                    "new_startDate": {"type": "string"},
                    "new_duration": {"type": "integer"},
                    "new_location": {"type": "string"},
                    "new_priority": {"type": "string", "enum": ["mandatory", "optional"]},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_events",
            "description": "Delete one or more calendar events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                    "title_filter": {"type": "string"},
                },
                "required": ["start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan_schedule",
            "description": (
                "Create multiple events as part of a schedule plan "
                "(e.g. recurring focus blocks, weekly routines)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "Plain-text description of what to schedule",
                    },
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                },
                "required": ["description", "start_date", "end_date"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_emails_for_events",
            "description": "Search the user's emails to find calendar-relevant events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query for emails"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "respond_to_user",
            "description": "Send a plain-text response when no calendar action is needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                },
                "required": ["message"],
            },
        },
    },
]

_TOOL_TO_ROUTE = {
    "create_event": "create",
    "list_events": "list",
    "update_events": "update",
    "delete_events": "delete",
    "plan_schedule": "plan",
    "search_emails_for_events": "email",
    "respond_to_user": "message",
}

SYSTEM_PROMPT = (
    "You are a calendar assistant. Help users manage their calendar by creating, "
    "listing, updating, or deleting events. Use the available tools to handle "
    "their requests. Always pick the most appropriate tool.\n\n"
    "Current date/time: {current_datetime}\n"
    "Day of week: {weekday}"
)


async def run_baseline(
    user_input: str,
    current_datetime: str,
    weekday: str,
    days_in_month: int = 31,
) -> dict:
    """
    Run the single-agent baseline on a single user input.

    Returns a dict with:
      route          – classified route (create/list/update/delete/plan/email/message)
      extracted_slots – arguments passed to the chosen tool
      response_text  – LLM text (if any)
      tool_name      – exact OpenAI tool name called
      latency_ms     – wall-clock time in ms
      success        – bool
      error          – str (only present on failure)
    """
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    start = time.perf_counter()

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.format(
                current_datetime=current_datetime,
                weekday=weekday,
            ),
        },
        {"role": "user", "content": user_input},
    ]

    try:
        resp = await client.chat.completions.create(
            model="gpt-4.1",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0,
        )

        latency_ms = (time.perf_counter() - start) * 1000
        msg = resp.choices[0].message

        if msg.tool_calls:
            tc = msg.tool_calls[0]
            tool_name = tc.function.name
            try:
                tool_args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            return {
                "route": _TOOL_TO_ROUTE.get(tool_name, "message"),
                "extracted_slots": tool_args,
                "response_text": msg.content or "",
                "tool_name": tool_name,
                "latency_ms": round(latency_ms, 1),
                "success": True,
            }

        # No tool call → conversational reply
        latency_ms = (time.perf_counter() - start) * 1000
        return {
            "route": "message",
            "extracted_slots": {},
            "response_text": msg.content or "",
            "tool_name": "respond_to_user",
            "latency_ms": round(latency_ms, 1),
            "success": True,
        }

    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.error("Baseline error: %s", exc)
        return {
            "route": "error",
            "extracted_slots": {},
            "response_text": "",
            "tool_name": None,
            "latency_ms": round(latency_ms, 1),
            "success": False,
            "error": str(exc),
        }
