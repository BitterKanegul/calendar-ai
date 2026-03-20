
from typing import TypedDict, Annotated, List, Optional
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from models import Event

def merge_is_success(old: bool, new: bool) -> bool:
    return new


class FlowState(TypedDict):
    router_messages: Annotated[list[BaseMessage], add_messages]
    create_messages: Annotated[list[BaseMessage], add_messages]
    delete_messages: Annotated[list[BaseMessage], add_messages]
    list_messages: Annotated[list[BaseMessage], add_messages]
    update_messages: Annotated[list[BaseMessage], add_messages]
    input_text: str
    current_datetime: str
    weekday: str
    days_in_month: int
    user_id: int
    route: dict
    create_event_data: dict
    create_conflict_events: Optional[List[Event]]
    list_date_range_data: dict
    list_date_range_filtered_events: List[Event]
    list_final_filtered_events: List[Event]
    delete_date_range_data: dict
    delete_date_range_filtered_events: List[Event]
    delete_final_filtered_events: List[Event]
    update_date_range_data: dict
    update_date_range_filtered_events: List[Event]
    update_final_filtered_events: List[Event]
    update_arguments: dict
    update_conflict_event: Optional[Event]
    resolution_plan: Optional[dict]
    resolution_type: Optional[str]
    awaiting_confirmation: bool
    confirmation_type: Optional[str]
    confirmation_data: Optional[dict]
    plan_tasks: Optional[list]
    plan_results: Optional[list]
    plan_summary: Optional[str]
    is_planning_mode: bool
    email_messages: Annotated[list[BaseMessage], add_messages]
    email_extracted_events: Optional[dict]
    email_search_results: Optional[list]
    leisure_messages: Annotated[list[BaseMessage], add_messages]
    leisure_search_params: Optional[dict]
    leisure_search_results: Optional[list]
    leisure_recommended_events: Optional[list]
    is_success: Annotated[bool, merge_is_success]
    # Conflict Resolution
    conflict_check_request: Optional[dict]
    conflict_check_result: Optional[dict]
    conflict_resolution_messages: Annotated[list[BaseMessage], add_messages]
