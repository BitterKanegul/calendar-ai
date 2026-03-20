"""
Conflict Resolution Agent - Agentic Implementation

This agent uses LLM with tools to check conflicts and suggest alternatives.
The LLM decides which tools to use and how to respond.
"""

import logging
from typing import Optional
from datetime import datetime
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage, ToolMessage
from langchain_core.prompts import PromptTemplate
from ..state import FlowState
from .system_prompt import CONFLICT_RESOLUTION_AGENT_PROMPT
from ..llm import model
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from openai import OpenAIError, RateLimitError
from ..tools.conflict_resolution_tools import (
    check_conflict_tool_factory,
    suggest_alternative_times_tool_factory,
    find_free_slots_tool_factory
)
from models import Event
import json

logger = logging.getLogger(__name__)

retryable_exceptions = (OpenAIError, RateLimitError)


@retry(
    wait=wait_random_exponential(min=1, max=10),
    stop=stop_after_attempt(3),
    retry_if_exception_type=retryable_exceptions,
)
async def conflict_resolution_agent(state: FlowState):
    """
    Conflict Resolution Agent - Agentic implementation.
    
    The LLM decides which tools to use and orchestrates conflict checking and suggestions.
    """
    # Check if conflict check was requested
    if not state.get('conflict_check_request'):
        logger.warning("No conflict check request found in state")
        return {
            "conflict_check_result": {
                "has_conflict": False,
                "conflicting_events": [],
                "suggestions": [],
                "recommendation": "No conflict check requested"
            },
            "conflict_resolution_messages": [AIMessage(content="No conflict check requested.")],
            "create_conflict_events": [],
            "create_messages": [AIMessage(content="Do you want to create the following events?")],
            "is_success": True
        }
    
    request = state['conflict_check_request']
    user_id = state['user_id']
    
    logger.info(f"Conflict Resolution Agent: Checking conflicts for user {user_id}")
    
    try:
        # Create tools bound to user_id
        check_conflict_tool = check_conflict_tool_factory(user_id)
        suggest_tool = suggest_alternative_times_tool_factory(user_id)
        find_free_slots_tool = find_free_slots_tool_factory(user_id)
        
        # Bind tools to model
        model_with_tools = model.bind_tools([check_conflict_tool, suggest_tool, find_free_slots_tool])
        
        # Prepare system prompt
        template = PromptTemplate.from_template(CONFLICT_RESOLUTION_AGENT_PROMPT)
        prompt_text = template.format()
        
        # Initialize messages list
        messages = []
        
        # Add system prompt
        if state.get("conflict_resolution_messages") and isinstance(state["conflict_resolution_messages"][0], SystemMessage):
            state["conflict_resolution_messages"][0] = SystemMessage(content=prompt_text)
            messages = state["conflict_resolution_messages"]
        else:
            messages = [SystemMessage(content=prompt_text)]
            if "conflict_resolution_messages" in state:
                messages.extend(state["conflict_resolution_messages"])
        
        # Add user request as HumanMessage
        request_text = f"""Please check for conflicts for the following time slot:
- Start Date: {request.get('startDate')}
- End Date: {request.get('endDate')}
- Duration: {request.get('duration_minutes', 60)} minutes
- Exclude Event ID: {request.get('exclude_event_id', 'None')}

Check for conflicts and suggest alternatives if conflicts are found. Provide a clear recommendation."""
        
        messages.append(HumanMessage(content=request_text))
        
        # Agentic loop: Let LLM call tools until it's done
        max_iterations = 5
        iteration = 0
        conflict_result_from_tools = None  # Capture from check_conflict tool
        suggestions_from_tools = None  # Capture from suggest_alternative_times tool

        while iteration < max_iterations:
            iteration += 1
            logger.debug(f"Conflict Resolution Agent iteration {iteration}")
            
            # Invoke model with tools
            response = await model_with_tools.ainvoke(messages)
            messages.append(response)
            
            # Check if model wants to call tools
            if hasattr(response, 'tool_calls') and response.tool_calls:
                # Execute tool calls
                for tool_call in response.tool_calls:
                    tool_name = tool_call['name']
                    tool_args = tool_call.get('args', {})
                    
                    logger.info(f"Conflict Resolution Agent calling tool: {tool_name}")
                    
                    # Execute appropriate tool
                    if tool_name == 'check_conflict':
                        # Convert string dates to datetime if needed
                        if isinstance(tool_args.get('startDate'), str):
                            tool_args['startDate'] = datetime.fromisoformat(tool_args['startDate'])
                        if isinstance(tool_args.get('endDate'), str):
                            tool_args['endDate'] = datetime.fromisoformat(tool_args['endDate'])
                        
                        tool_result = await check_conflict_tool.ainvoke(tool_args)
                        conflict_result_from_tools = tool_result

                    elif tool_name == 'suggest_alternative_times':
                        # Convert string dates to datetime if needed
                        if isinstance(tool_args.get('requested_startDate'), str):
                            tool_args['requested_startDate'] = datetime.fromisoformat(tool_args['requested_startDate'])
                        if isinstance(tool_args.get('requested_endDate'), str):
                            tool_args['requested_endDate'] = datetime.fromisoformat(tool_args['requested_endDate'])
                        
                        tool_result = await suggest_tool.ainvoke(tool_args)
                        suggestions_from_tools = tool_result

                    elif tool_name == 'find_free_slots':
                        # Convert string dates to datetime if needed
                        if isinstance(tool_args.get('startDate'), str):
                            tool_args['startDate'] = datetime.fromisoformat(tool_args['startDate'])
                        if isinstance(tool_args.get('endDate'), str):
                            tool_args['endDate'] = datetime.fromisoformat(tool_args['endDate'])
                        
                        tool_result = await find_free_slots_tool.ainvoke(tool_args)
                    else:
                        tool_result = {"error": f"Unknown tool: {tool_name}"}
                    
                    # Add tool result as ToolMessage
                    tool_message = ToolMessage(
                        content=json.dumps(tool_result, default=str),
                        tool_call_id=tool_call.get('id', '')
                    )
                    messages.append(tool_message)
                
                # Continue loop to let LLM process tool results
                continue
            else:
                # LLM provided final response (no more tool calls)
                break
        
        # Build conflict_result from tool results (preferred) or LLM response
        final_response = messages[-1].content if messages else "No response generated"
        if conflict_result_from_tools:
            conflict_result = {
                "has_conflict": conflict_result_from_tools.get("has_conflict", False),
                "conflicting_events": conflict_result_from_tools.get("conflicting_events", []),
                "conflict_count": conflict_result_from_tools.get("conflict_count", 0),
                "suggestions": suggestions_from_tools.get("suggestions", []) if suggestions_from_tools else [],
                "recommendation": final_response
            }
        else:
            conflict_result = _parse_llm_response(final_response, request)

        logger.info(f"Conflict Resolution Agent: Found {conflict_result.get('conflict_count', 0)} conflicts, {len(conflict_result.get('suggestions', []))} suggestions")

        # Convert conflicting_events to Event objects for backward compatibility
        create_conflict_events = _dicts_to_events(
            conflict_result.get("conflicting_events", []),
            user_id
        )

        return {
            "conflict_check_result": conflict_result,
            "conflict_resolution_messages": messages,
            "create_conflict_events": create_conflict_events,
            "create_messages": [AIMessage(content=conflict_result.get("recommendation", "Do you want to create the following events?"))],
            "is_success": True
        }
        
    except Exception as e:
        logger.error(f"Error in conflict resolution agent: {e}", exc_info=True)
        return {
            "conflict_check_result": {
                "has_conflict": False,
                "conflicting_events": [],
                "suggestions": [],
                "recommendation": f"Error checking conflicts: {str(e)}"
            },
            "conflict_resolution_messages": [AIMessage(content="An error occurred while checking conflicts.")],
            "create_conflict_events": [],
            "create_messages": [AIMessage(content="An error occurred. Please try again later.")],
            "is_success": False
        }


def _dicts_to_events(conflicting_events: list, user_id: int) -> list:
    """Convert conflict event dicts to Event objects for backward compatibility."""
    events = []
    for d in conflicting_events:
        try:
            event_id = d.get("event_id") or d.get("id")
            start_date = d.get("startDate")
            end_date = d.get("endDate")
            if isinstance(start_date, str):
                start_date = datetime.fromisoformat(start_date)
            if isinstance(end_date, str):
                end_date = datetime.fromisoformat(end_date)
            duration = d.get("duration")
            if duration is None and start_date and end_date:
                duration = int((end_date - start_date).total_seconds() / 60)
            events.append(Event(
                id=event_id,
                title=d.get("title", ""),
                startDate=start_date,
                endDate=end_date,
                duration=duration,
                location=d.get("location"),
                user_id=user_id
            ))
        except Exception:
            continue
    return events


def _parse_llm_response(response: str, request: dict) -> dict:
    """
    Parse LLM response to extract conflict information.
    
    The LLM should provide structured information about conflicts and suggestions.
    If it's JSON, parse it. Otherwise, extract from text.
    """
    try:
        # Try to parse as JSON first
        if response.strip().startswith('{'):
            parsed = json.loads(response)
            return {
                "has_conflict": parsed.get('has_conflict', False),
                "conflicting_events": parsed.get('conflicting_events', []),
                "conflict_count": parsed.get('conflict_count', 0),
                "suggestions": parsed.get('suggestions', []),
                "recommendation": parsed.get('recommendation', response)
            }
    except json.JSONDecodeError:
        pass
    
    # If not JSON, create result from text response
    # The LLM should have called tools and provided a summary
    return {
        "has_conflict": "conflict" in response.lower() or "conflicts" in response.lower(),
        "conflicting_events": [],
        "conflict_count": 0,
        "suggestions": [],
        "recommendation": response
    }


def conflict_resolution_action(state: FlowState):
    """Determine next action after conflict resolution."""
    result = state.get('conflict_check_result', {})
    
    if not result.get('has_conflict'):
        return "no_conflict"  # Proceed with operation
    elif result.get('suggestions'):
        return "conflict_with_suggestions"  # Has alternatives
    else:
        return "conflict_no_suggestions"  # Conflict but no alternatives
