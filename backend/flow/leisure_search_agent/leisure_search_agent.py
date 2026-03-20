"""
Leisure Search Agent

Three LangGraph nodes:
  - leisure_search_agent: LLM parses user intent → stores leisure_search_params
  - leisure_search_executor: Calls Event Search MCP, fetches calendar, filters to free time
  - leisure_message_handler: Handles clarification/error fallback
"""
import json
import logging
from datetime import datetime, timedelta, date

from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.prompts import PromptTemplate
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from openai import OpenAIError, RateLimitError

from ..state import FlowState
from ..llm import model
from .prompt import LEISURE_SEARCH_AGENT_PROMPT
from ..event_search_mcp_client import call_event_search_tool
from ..mcp_client import call_calendar_tool
from ..planner_agent.optimizer import _busy_intervals_for_day

logger = logging.getLogger(__name__)

retryable_exceptions = (OpenAIError, RateLimitError)


@retry(
    wait=wait_random_exponential(min=1, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(retryable_exceptions),
)
async def leisure_search_agent(state: FlowState):
    """Parse user intent into structured search parameters."""
    template = PromptTemplate.from_template(LEISURE_SEARCH_AGENT_PROMPT)
    prompt_text = template.format(
        current_datetime=state.get("current_datetime", ""),
        weekday=state.get("weekday", ""),
    )

    messages = list(state.get("leisure_messages") or [])
    if messages and isinstance(messages[0], SystemMessage):
        messages[0] = SystemMessage(content=prompt_text)
    else:
        messages.insert(0, SystemMessage(content=prompt_text))

    response = await model.ainvoke(messages)

    try:
        params = json.loads(response.content)
        state["leisure_search_params"] = params
    except json.JSONDecodeError:
        state["leisure_search_params"] = None

    state["leisure_messages"] = [response]
    return state


def leisure_action(state: FlowState):
    """Route based on whether we got valid search params."""
    if state.get("leisure_search_params"):
        return "leisure_search_executor"
    return "leisure_message_handler"


def _free_windows_for_day(
    busy: list[tuple[datetime, datetime]],
    target_date: date,
) -> list[tuple[datetime, datetime]]:
    """Invert busy intervals to find free windows (8am-10pm)."""
    day_start = datetime(target_date.year, target_date.month, target_date.day, 8, 0)
    day_end = datetime(target_date.year, target_date.month, target_date.day, 22, 0)

    free: list[tuple[datetime, datetime]] = []
    cursor = day_start
    for busy_start, busy_end in sorted(busy):
        if busy_start > cursor:
            free.append((cursor, min(busy_start, day_end)))
        cursor = max(cursor, busy_end)
    if cursor < day_end:
        free.append((cursor, day_end))
    return free


def _event_fits_free_time(
    event_start_str: str | None,
    event_end_str: str | None,
    free_windows: dict[date, list[tuple[datetime, datetime]]],
) -> bool:
    """Check if an event fits within any free window."""
    if not event_start_str or not event_end_str:
        return False
    try:
        start = datetime.fromisoformat(event_start_str.replace("Z", "+00:00")).replace(tzinfo=None)
        end = datetime.fromisoformat(event_end_str.replace("Z", "+00:00")).replace(tzinfo=None)
    except (ValueError, TypeError):
        return False

    target = start.date()
    windows = free_windows.get(target, [])
    return any(start >= w_start and end <= w_end for w_start, w_end in windows)


async def leisure_search_executor(state: FlowState):
    """Call Event Search MCP, fetch user calendar, filter/rank results."""
    params = state.get("leisure_search_params", {})
    user_id = state.get("user_id")

    # Search external events
    search_args = {
        "query": params.get("query", ""),
        "size": params.get("max_results", 10),
    }
    if params.get("start_date"):
        search_args["start_date"] = params["start_date"]
    if params.get("end_date"):
        search_args["end_date"] = params["end_date"]
    if params.get("location"):
        search_args["location"] = params["location"]
    if params.get("category"):
        search_args["category"] = params["category"]

    try:
        results = await call_event_search_tool("search_events", search_args)
    except Exception as e:
        logger.error(f"Event search failed: {e}")
        results = []

    if not results:
        results = []

    # Fetch user's calendar for the search date range to check free time
    free_windows: dict[date, list[tuple[datetime, datetime]]] = {}
    if user_id and params.get("start_date") and params.get("end_date"):
        try:
            calendar_events = await call_calendar_tool("list_events", {
                "user_id": user_id,
                "start_date": params["start_date"],
                "end_date": params["end_date"],
            })
        except Exception as e:
            logger.error(f"Calendar fetch failed: {e}")
            calendar_events = []

        if calendar_events:
            try:
                range_start = datetime.fromisoformat(params["start_date"]).date()
                range_end = datetime.fromisoformat(params["end_date"]).date()
            except (ValueError, TypeError):
                range_start = range_end = None

            if range_start and range_end:
                current = range_start
                while current <= range_end:
                    busy = _busy_intervals_for_day(calendar_events, current, buffer_minutes=0)
                    free_windows[current] = _free_windows_for_day(busy, current)
                    current += timedelta(days=1)

    # Tag each result with fits_free_time
    recommended = []
    for event in results:
        event["fits_free_time"] = _event_fits_free_time(
            event.get("start_date"),
            event.get("end_date"),
            free_windows,
        )
        recommended.append(event)

    # Sort: events that fit free time first
    recommended.sort(key=lambda e: (not e.get("fits_free_time", False),))

    state["leisure_search_results"] = results
    state["leisure_recommended_events"] = recommended
    state["is_success"] = True

    # Build summary message
    count = len(recommended)
    fits_count = sum(1 for e in recommended if e.get("fits_free_time"))
    query = params.get("query", "events")
    location = params.get("location", "")

    if count == 0:
        msg = f"I couldn't find any {query} events{' in ' + location if location else ''} for those dates."
    else:
        msg = f"I found {count} {query} event{'s' if count != 1 else ''}{' in ' + location if location else ''}."
        if fits_count > 0:
            msg += f" {fits_count} fit{'s' if fits_count == 1 else ''} your free time!"

    state["leisure_messages"] = [AIMessage(content=msg)]
    return state


def leisure_message_handler(state: FlowState):
    """Fallback when params couldn't be parsed."""
    state["is_success"] = True
    state["leisure_messages"] = [AIMessage(
        content="I'd be happy to help you find events! Could you tell me what kind of events you're looking for, and when/where?"
    )]
    return state
