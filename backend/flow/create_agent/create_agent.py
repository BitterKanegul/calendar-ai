from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_core.prompts import PromptTemplate
from ..state import FlowState
from .prompt import CREATE_EVENT_AGENT_PROMPT
from ..llm import model
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from openai import OpenAIError, RateLimitError
import json
from typing import Optional
from models import Event
from datetime import timedelta, datetime
from ..mcp_client import call_calendar_tool

retryable_exceptions = (OpenAIError, RateLimitError)


@retry(
    wait=wait_random_exponential(min=1, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(retryable_exceptions),
)
async def create_agent(state: FlowState):
    
    template = PromptTemplate.from_template(CREATE_EVENT_AGENT_PROMPT)
    prompt_text = template.format(
            current_datetime=state['current_datetime'],
            weekday=state['weekday'],
            days_in_month=state['days_in_month']
        )

    
    state["create_messages"].append(HumanMessage(content=state["input_text"]))

    if state["create_messages"] and isinstance(state["create_messages"][0], SystemMessage):
        state["create_messages"][0] = SystemMessage(content=prompt_text)
    else:
        state["create_messages"].insert(0, SystemMessage(content=prompt_text))


    try:
        response = [await model.ainvoke(state["create_messages"])]
        create_event_data = json.loads(response[0].content)

        state['create_event_data'] = create_event_data

        # Set conflict_check_request for Conflict Resolution Agent (first event)
        if isinstance(create_event_data, list) and len(create_event_data) > 0:
            first_event = create_event_data[0].get("arguments", {})
            start_date = first_event.get("startDate")
            duration = first_event.get("duration", 60)
            if start_date:
                start_dt = datetime.fromisoformat(start_date) if isinstance(start_date, str) else start_date
                end_dt = start_dt + timedelta(minutes=duration)
                state['conflict_check_request'] = {
                    "startDate": start_date if isinstance(start_date, str) else start_dt.isoformat(),
                    "endDate": end_dt.isoformat(),
                    "duration_minutes": duration,
                    "exclude_event_id": None
                }
    except Exception as e:
        state['create_event_data'] = None

    return state

def create_action(state: FlowState):
    if isinstance(state['create_event_data'], list):
        return "conflict_resolution_agent"
    else:
        return "create_message_handler"
        
def create_message_handler(state: FlowState):
    return {"create_messages": [AIMessage(content='An error occurred. Please try again later.')]}

async def check_event_conflict(state: FlowState) -> Optional[Event]:
    """
    Check for event conflicts before creating the event via the Calendar MCP Server.
    """
    try:
        conflict_events = []
        for event_data in state['create_event_data']:
            start_date = datetime.fromisoformat(event_data.get('arguments', {}).get('startDate'))
            duration = event_data.get('arguments', {}).get('duration', 0) or 0
            end_date = start_date + timedelta(minutes=duration)
            conflict_dict = await call_calendar_tool("check_conflicts", {
                "user_id": state['user_id'],
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
            })
            if conflict_dict:
                conflict_events.append(Event(
                    id=conflict_dict['id'],
                    title=conflict_dict['title'],
                    startDate=conflict_dict['startDate'],
                    endDate=conflict_dict['endDate'],
                    duration=conflict_dict.get('duration'),
                    location=conflict_dict.get('location'),
                    user_id=conflict_dict.get('user_id', state['user_id']),
                    priority=conflict_dict.get('priority', 'optional'),
                    flexibility=conflict_dict.get('flexibility', 'movable'),
                    category=conflict_dict.get('category', 'personal'),
                ))
        state['create_conflict_events'] = conflict_events
        state['is_success'] = True
        state['create_messages'].append(AIMessage(content="Do you want to create the following events?"))
        return state
    except Exception as e:
        state['create_messages'].append(AIMessage(content="An error occurred. Please try again later."))
        return state
