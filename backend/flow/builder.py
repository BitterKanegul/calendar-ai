from langgraph.graph import StateGraph, START, END
from .router_agent.router_agent import router_agent, route_action, router_message_handler
from .create_agent.create_agent import create_agent, create_message_handler, create_action, check_event_conflict
from .list_agent.list_agent import list_date_range_agent, list_message_handler, list_action, list_event_by_date_range, list_filter_event_agent
from .delete_agent.delete_agent import delete_date_range_agent, delete_message_handler, delete_action, delete_event_by_date_range, delete_filter_event_agent
from .update_agent.update_agent import update_date_range_agent, update_message_handler, update_action, get_events_for_update, update_filter_event_agent
from .conflict_resolution_agent.conflict_resolution_agent import conflict_resolution_agent, conflict_action
from .conflict_resolution_agent.confirmation_handler import confirmation_handler
from .planner_agent.plan_executor import plan_executor
from .email_pipeline.email_agent import email_retrieval_agent
from .memory.compaction import memory_compaction_node
from .safety.delete_safety_gate import delete_safety_gate
from .safety.update_safety_gate import update_safety_gate
from .safety.safety_confirmation_handler import safety_confirmation_handler
from .leisure_search_agent.leisure_search_agent import leisure_search_agent, leisure_action, leisure_search_executor, leisure_message_handler
from .state import FlowState
from .redis_checkpointer import get_checkpointer


class FlowBuilder:
    async def create_flow(self):

        # Add nodes
        graph_builder = StateGraph(FlowState)

        graph_builder.add_node("memory_compaction", memory_compaction_node)
        graph_builder.add_node("router_agent", router_agent)
        graph_builder.add_node("router_message_handler", router_message_handler)
        graph_builder.add_node("create_agent", create_agent)
        graph_builder.add_node("create_message_handler", create_message_handler)
        graph_builder.add_node("check_event_conflict", check_event_conflict)
        graph_builder.add_node("conflict_resolution_agent", conflict_resolution_agent)
        graph_builder.add_node("confirmation_handler", confirmation_handler)
        graph_builder.add_node("plan_executor", plan_executor)
        graph_builder.add_node("email_retrieval_agent", email_retrieval_agent)
        graph_builder.add_node("list_date_range_agent", list_date_range_agent)
        graph_builder.add_node("list_message_handler", list_message_handler)
        graph_builder.add_node("list_event_by_date_range", list_event_by_date_range)
        graph_builder.add_node("list_filter_event_agent", list_filter_event_agent)
        graph_builder.add_node("delete_date_range_agent", delete_date_range_agent)
        graph_builder.add_node("delete_message_handler", delete_message_handler)
        graph_builder.add_node("delete_event_by_date_range", delete_event_by_date_range)
        graph_builder.add_node("delete_filter_event_agent", delete_filter_event_agent)
        graph_builder.add_node("delete_safety_gate", delete_safety_gate)
        graph_builder.add_node("update_date_range_agent", update_date_range_agent)
        graph_builder.add_node("update_message_handler", update_message_handler)
        graph_builder.add_node("get_events_for_update", get_events_for_update)
        graph_builder.add_node("update_filter_event_agent", update_filter_event_agent)
        graph_builder.add_node("update_safety_gate", update_safety_gate)
        graph_builder.add_node("safety_confirmation_handler", safety_confirmation_handler)
        graph_builder.add_node("leisure_search_agent", leisure_search_agent)
        graph_builder.add_node("leisure_search_executor", leisure_search_executor)
        graph_builder.add_node("leisure_message_handler", leisure_message_handler)

        # Add edges
        graph_builder.add_edge(START, "memory_compaction")
        graph_builder.add_edge("memory_compaction", "router_agent")
        graph_builder.add_conditional_edges("router_agent", route_action)
        graph_builder.add_edge("router_message_handler", END)

        graph_builder.add_conditional_edges("create_agent", create_action)
        graph_builder.add_edge("create_message_handler", END)
        graph_builder.add_conditional_edges(
            "check_event_conflict",
            conflict_action,
            {"conflict_resolution_agent": "conflict_resolution_agent", "__end__": END},
        )
        graph_builder.add_edge("conflict_resolution_agent", END)
        graph_builder.add_edge("confirmation_handler", END)
        graph_builder.add_edge("plan_executor", END)
        graph_builder.add_edge("email_retrieval_agent", END)

        graph_builder.add_conditional_edges("list_date_range_agent", list_action)
        graph_builder.add_edge("list_message_handler", END)
        graph_builder.add_edge("list_event_by_date_range", "list_filter_event_agent")
        graph_builder.add_edge("list_filter_event_agent", END)

        graph_builder.add_conditional_edges("delete_date_range_agent", delete_action)
        graph_builder.add_edge("delete_message_handler", END)
        graph_builder.add_edge("delete_event_by_date_range", "delete_filter_event_agent")
        graph_builder.add_edge("delete_filter_event_agent", "delete_safety_gate")
        graph_builder.add_edge("delete_safety_gate", END)

        graph_builder.add_conditional_edges("update_date_range_agent", update_action)
        graph_builder.add_edge("update_message_handler", END)
        graph_builder.add_edge("get_events_for_update", "update_filter_event_agent")
        graph_builder.add_edge("update_filter_event_agent", "update_safety_gate")
        graph_builder.add_edge("update_safety_gate", END)

        graph_builder.add_edge("safety_confirmation_handler", END)

        graph_builder.add_conditional_edges("leisure_search_agent", leisure_action)
        graph_builder.add_edge("leisure_search_executor", END)
        graph_builder.add_edge("leisure_message_handler", END)

        checkpointer = await get_checkpointer()
        flow = graph_builder.compile(checkpointer=checkpointer)
        return flow
    
        
    
        
    
    