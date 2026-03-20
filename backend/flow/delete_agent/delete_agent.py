from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langchain_core.prompts import PromptTemplate
from ..state import FlowState
from .delete_data_range_agent_prompt import DELETE_DATE_RANGE_AGENT_PROMPT
from ..llm import model
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from openai import OpenAIError, RateLimitError
import json
from typing import List
from models import Event
from .delete_filter_event_agent_prompt import DELETE_FILTER_EVENT_AGENT_PROMPT
from datetime import datetime
from ..mcp_client import call_calendar_tool
retryable_exceptions = (OpenAIError, RateLimitError)


def _dict_to_event(d: dict, fallback_user_id: int) -> Event:
    """Reconstruct a Pydantic Event from an MCP tool result dict."""
    return Event(
        id=d['id'],
        title=d['title'],
        startDate=d['startDate'],
        endDate=d['endDate'],
        duration=d.get('duration'),
        location=d.get('location'),
        user_id=d.get('user_id', fallback_user_id),
        priority=d.get('priority', 'optional'),
        flexibility=d.get('flexibility', 'movable'),
        category=d.get('category', 'personal'),
    )


@retry(
    wait=wait_random_exponential(min=1, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(retryable_exceptions),
)
async def delete_date_range_agent(state: FlowState):
    
    template = PromptTemplate.from_template(DELETE_DATE_RANGE_AGENT_PROMPT)
    prompt_text = template.format(
            current_datetime=state['current_datetime'],
            weekday=state['weekday'],
            days_in_month=state['days_in_month']
        )

    state["delete_messages"].append(HumanMessage(content=state["input_text"]))
    
    if state["delete_messages"] and isinstance(state["delete_messages"][0], SystemMessage):
        state["delete_messages"][0] = SystemMessage(content=prompt_text)
    else:
        state["delete_messages"].insert(0, SystemMessage(content=prompt_text))

    

    try:
        response = [await model.ainvoke(state["delete_messages"])]
        route_data = json.loads(response[0].content)
        state['delete_date_range_data'] = route_data
    except Exception as e:
        state['delete_date_range_data'] = {"message": "An error occurred. Please try again later."}
    
    return state

def delete_action(state: FlowState):
    if "function" in state['delete_date_range_data'] and "arguments" in state['delete_date_range_data']:
        return "delete_event_by_date_range"
    else:
        return "delete_message_handler"
        
def delete_message_handler(_: FlowState):
        """Handle cases where router returns a message instead of arguments"""
        return {"delete_messages": [AIMessage(content="An error occurred. Please try again later.")]}

async def delete_event_by_date_range(state: FlowState) -> List[Event]:
    """
    Get events by date range via the Calendar MCP Server.
    """
    try:
        start_date = state['delete_date_range_data']['arguments'].get('startDate')
        end_date = state['delete_date_range_data']['arguments'].get('endDate')
        result = await call_calendar_tool("list_events", {
            "user_id": state['user_id'],
            "start_date": start_date,
            "end_date": end_date,
        })
        state['delete_date_range_filtered_events'] = [_dict_to_event(d, state['user_id']) for d in (result or [])]
        return state
    except Exception as e:
        state['delete_date_range_filtered_events'] = []
        return state
    
@retry(
    wait=wait_random_exponential(min=1, max=10),
    stop=stop_after_attempt(2),
    retry=retry_if_exception_type(retryable_exceptions),
)
async def delete_filter_event_agent(state: FlowState):
    if state['delete_date_range_filtered_events']:
        template = PromptTemplate.from_template(DELETE_FILTER_EVENT_AGENT_PROMPT)
        prompt_text = template.format(
                user_events=state['delete_date_range_filtered_events']
            )
        
        if state["delete_messages"] and isinstance(state["delete_messages"][0], SystemMessage):
            state["delete_messages"][0] = SystemMessage(content=prompt_text)
        else:
            state["delete_messages"].insert(0, SystemMessage(content=prompt_text))
            
        state["delete_messages"].append(HumanMessage(content=state["input_text"]))

        response = [await model.ainvoke(state["delete_messages"])]
        try:
            delete_event_data = json.loads(response[0].content)
            
            if isinstance(delete_event_data, list):
                events = []
                for event_dict in delete_event_data:
                    try:
                        start_date = datetime.fromisoformat(event_dict.get('startDate')) 
                        end_date = datetime.fromisoformat(event_dict.get('endDate'))
                        
                        event = Event(
                            id=event_dict.get('id'),
                            title=event_dict.get('title'),
                            startDate=start_date,
                            endDate=end_date,
                            duration=event_dict.get('duration'),
                            location=event_dict.get('location'),
                            user_id=state['user_id'],
                            priority=event_dict.get('priority', 'optional'),
                            flexibility=event_dict.get('flexibility', 'movable'),
                            category=event_dict.get('category', 'personal'),
                        )
                        events.append(event)
                    except Exception as e:
                        continue
                
                state['delete_final_filtered_events'] = events
                if len(events) == 0:
                    state['delete_messages'].append(AIMessage(content="No events to delete found"))
                else:
                    state['delete_messages'].append(AIMessage(content=f"Are you sure you want to delete the following events?"))
                    state['is_success'] = True
            else:
                state['delete_messages'].append(AIMessage(content="An error occurred. Please try again later."))
                
        except Exception as e:
            state['delete_messages'].append(AIMessage(content="An error occurred. Please try again later."))
    else:
        state['delete_messages'].append(AIMessage(content="No events to delete found"))
    
    return state