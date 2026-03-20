"""
Integration tests — router_agent with mock LLM + real in-memory state.

Requires: pytest -m integration
"""

import json
import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import HumanMessage, SystemMessage

pytestmark = pytest.mark.integration


def _make_state(messages: list, awaiting: bool = False, confirmation_type: str | None = None):
    """Build a minimal FlowState dict."""
    from flow.state import FlowState
    return {
        "router_messages": messages,
        "create_messages": [],
        "delete_messages": [],
        "list_messages": [],
        "update_messages": [],
        "email_messages": [],
        "events": [],
        "route": {},
        "is_success": False,
        "awaiting_confirmation": awaiting,
        "confirmation_type": confirmation_type,
        "confirmation_data": None,
        "resolution_plan": None,
        "resolution_type": None,
        "plan_tasks": [],
        "plan_results": [],
        "plan_summary": None,
        "is_planning_mode": False,
        "email_extracted_events": None,
        "email_search_results": [],
    }


async def test_router_classifies_create():
    """Router correctly sets route=create from mock LLM response."""
    from flow.router_agent.router_agent import router_agent

    state = _make_state([HumanMessage(content="Schedule a dentist appointment tomorrow at 3pm")])
    mock_response = MagicMock()
    mock_response.content = json.dumps({"route": "create", "arguments": {"title": "Dentist", "startDate": "2026-03-21T15:00:00"}})

    with patch("flow.llm.model.ainvoke", return_value=mock_response):
        result = await router_agent(state)

    assert result["route"]["route"] == "create"


async def test_router_classifies_list():
    """Router correctly sets route=list from mock LLM response."""
    from flow.router_agent.router_agent import router_agent

    state = _make_state([HumanMessage(content="What's on my calendar tomorrow?")])
    mock_response = MagicMock()
    mock_response.content = json.dumps({"route": "list", "arguments": {"date": "2026-03-21"}})

    with patch("flow.llm.model.ainvoke", return_value=mock_response):
        result = await router_agent(state)

    assert result["route"]["route"] == "list"


async def test_router_skips_llm_when_awaiting_confirmation():
    """Router must NOT call the LLM when awaiting_confirmation=True."""
    from flow.router_agent.router_agent import router_agent

    state = _make_state(
        [HumanMessage(content="yes")],
        awaiting=True,
        confirmation_type="delete_safety",
    )

    with patch("flow.llm.model.ainvoke") as mock_invoke:
        result = await router_agent(state)
        mock_invoke.assert_not_called()

    # State should be returned unchanged (still awaiting)
    assert result["awaiting_confirmation"] is True
