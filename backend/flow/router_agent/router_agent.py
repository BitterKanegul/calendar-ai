from langchain_core.messages import SystemMessage, AIMessage
from langchain_core.prompts import PromptTemplate
from ..state import FlowState
from .prompt import ROUTER_AGENT_PROMPT
from ..llm import model
from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type
from openai import OpenAIError, RateLimitError
import json

retryable_exceptions = (OpenAIError, RateLimitError)


@retry(
    wait=wait_random_exponential(min=1, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(retryable_exceptions),
)
async def router_agent(state: FlowState):
    # Skip LLM routing when waiting for conflict resolution confirmation
    if state.get("awaiting_confirmation"):
        return state

    template = PromptTemplate.from_template(ROUTER_AGENT_PROMPT)
    prompt_text = template.format()

    if state["router_messages"] and isinstance(state["router_messages"][0], SystemMessage):
        state["router_messages"][0] = SystemMessage(content=prompt_text)
    else:
        state["router_messages"].insert(0, SystemMessage(content=prompt_text))

    response = [await model.ainvoke(state["router_messages"])]

    # Parse the JSON response
    try:
        route_data = json.loads(response[0].content)
        state['route'] = route_data
    except json.JSONDecodeError:
        state['route'] = response[0].content

    return state

def route_action(state: FlowState):
    # If waiting for any confirmation, bypass normal routing
    if state.get("awaiting_confirmation"):
        confirmation_type = state.get("confirmation_type")
        if confirmation_type in ("delete_safety", "update_safety"):
            return "safety_confirmation_handler"
        return "confirmation_handler"  # conflict resolution

    if isinstance(state['route'], dict) and "route" in state['route']:
        route = state["route"]["route"]

        match route:
            case "create":
                return "create_agent"
            case "update":
                return "update_date_range_agent"
            case "delete":
                return "delete_date_range_agent"
            case "list":
                return "list_date_range_agent"
            case "plan":
                return "plan_executor"
            case "email":
                return "email_retrieval_agent"
            case "leisure":
                return "leisure_search_agent"
            case _:
                return 'router_message_handler'
    return 'router_message_handler'
        
def router_message_handler(state: FlowState):
    """Handle cases where router returns a message instead of a route"""
    state['is_success'] = True
    return {"router_messages": [AIMessage(content=state['route'])]}