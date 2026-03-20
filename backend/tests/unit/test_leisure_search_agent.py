"""
Unit tests for the Leisure Search Agent.

Mocks LLM and MCP to test param extraction, routing, and free-time filtering.
"""
import json
import pytest
from datetime import datetime, date
from unittest.mock import AsyncMock, patch, MagicMock

from flow.leisure_search_agent.leisure_search_agent import (
    leisure_search_agent,
    leisure_action,
    leisure_search_executor,
    leisure_message_handler,
    _free_windows_for_day,
    _event_fits_free_time,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(**overrides):
    """Build a minimal FlowState-like dict."""
    base = {
        "router_messages": [],
        "create_messages": [],
        "delete_messages": [],
        "list_messages": [],
        "update_messages": [],
        "email_messages": [],
        "leisure_messages": [],
        "input_text": "find concerts this weekend",
        "current_datetime": "2026-03-20T10:00:00",
        "weekday": "Friday",
        "days_in_month": 31,
        "user_id": 1,
        "route": {},
        "leisure_search_params": None,
        "leisure_search_results": None,
        "leisure_recommended_events": None,
        "is_success": False,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# leisure_action routing tests
# ---------------------------------------------------------------------------

class TestLeisureAction:
    def test_routes_to_executor_when_params_present(self):
        state = _make_state(leisure_search_params={"query": "concerts"})
        assert leisure_action(state) == "leisure_search_executor"

    def test_routes_to_handler_when_no_params(self):
        state = _make_state(leisure_search_params=None)
        assert leisure_action(state) == "leisure_message_handler"

    def test_routes_to_handler_when_empty_params(self):
        state = _make_state(leisure_search_params={})
        # Empty dict is falsy in Python — routes to message handler
        assert leisure_action(state) == "leisure_message_handler"


# ---------------------------------------------------------------------------
# _free_windows_for_day tests
# ---------------------------------------------------------------------------

class TestFreeWindowsForDay:
    def test_no_busy_intervals(self):
        windows = _free_windows_for_day([], date(2026, 3, 21))
        assert len(windows) == 1
        assert windows[0][0] == datetime(2026, 3, 21, 8, 0)
        assert windows[0][1] == datetime(2026, 3, 21, 22, 0)

    def test_single_busy_block(self):
        busy = [
            (datetime(2026, 3, 21, 10, 0), datetime(2026, 3, 21, 12, 0)),
        ]
        windows = _free_windows_for_day(busy, date(2026, 3, 21))
        assert len(windows) == 2
        assert windows[0] == (datetime(2026, 3, 21, 8, 0), datetime(2026, 3, 21, 10, 0))
        assert windows[1] == (datetime(2026, 3, 21, 12, 0), datetime(2026, 3, 21, 22, 0))

    def test_full_day_busy(self):
        busy = [
            (datetime(2026, 3, 21, 7, 0), datetime(2026, 3, 21, 23, 0)),
        ]
        windows = _free_windows_for_day(busy, date(2026, 3, 21))
        assert len(windows) == 0


# ---------------------------------------------------------------------------
# _event_fits_free_time tests
# ---------------------------------------------------------------------------

class TestEventFitsFreeTime:
    def test_fits_in_free_window(self):
        windows = {
            date(2026, 3, 21): [
                (datetime(2026, 3, 21, 14, 0), datetime(2026, 3, 21, 22, 0)),
            ],
        }
        assert _event_fits_free_time(
            "2026-03-21T15:00:00", "2026-03-21T17:00:00", windows
        ) is True

    def test_does_not_fit(self):
        windows = {
            date(2026, 3, 21): [
                (datetime(2026, 3, 21, 14, 0), datetime(2026, 3, 21, 16, 0)),
            ],
        }
        assert _event_fits_free_time(
            "2026-03-21T15:00:00", "2026-03-21T18:00:00", windows
        ) is False

    def test_no_start_date(self):
        assert _event_fits_free_time(None, "2026-03-21T17:00:00", {}) is False

    def test_no_free_windows_for_date(self):
        assert _event_fits_free_time(
            "2026-03-21T15:00:00", "2026-03-21T17:00:00", {}
        ) is False


# ---------------------------------------------------------------------------
# leisure_search_agent tests (mocked LLM)
# ---------------------------------------------------------------------------

class TestLeisureSearchAgentNode:
    @pytest.mark.asyncio
    async def test_extracts_valid_params(self):
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "query": "concerts",
            "start_date": "2026-03-21",
            "end_date": "2026-03-22",
            "location": "Syracuse",
            "category": "music",
            "prefer_free_time": False,
            "max_results": 10,
        })

        with patch("flow.leisure_search_agent.leisure_search_agent.model") as mock_model:
            mock_model.ainvoke = AsyncMock(return_value=mock_response)

            state = _make_state(
                leisure_messages=[MagicMock(content="find concerts this weekend in Syracuse")]
            )
            result = await leisure_search_agent(state)

        assert result["leisure_search_params"] is not None
        assert result["leisure_search_params"]["query"] == "concerts"
        assert result["leisure_search_params"]["location"] == "Syracuse"

    @pytest.mark.asyncio
    async def test_handles_invalid_json(self):
        mock_response = MagicMock()
        mock_response.content = "I'm not sure what you mean."

        with patch("flow.leisure_search_agent.leisure_search_agent.model") as mock_model:
            mock_model.ainvoke = AsyncMock(return_value=mock_response)

            state = _make_state(leisure_messages=[MagicMock(content="hello")])
            result = await leisure_search_agent(state)

        assert result["leisure_search_params"] is None


# ---------------------------------------------------------------------------
# leisure_search_executor tests (mocked MCP)
# ---------------------------------------------------------------------------

class TestLeisureSearchExecutor:
    @pytest.mark.asyncio
    async def test_returns_results_with_free_time_flags(self):
        mock_search_results = [
            {
                "external_id": "ev1",
                "title": "Concert A",
                "start_date": "2026-03-21T15:00:00",
                "end_date": "2026-03-21T18:00:00",
                "category": "music",
            },
            {
                "external_id": "ev2",
                "title": "Game B",
                "start_date": "2026-03-21T10:00:00",
                "end_date": "2026-03-21T12:30:00",
                "category": "sports",
            },
        ]
        mock_calendar_events = [
            {"startDate": "2026-03-21T09:00:00", "endDate": "2026-03-21T11:00:00"},
        ]

        with patch(
            "flow.leisure_search_agent.leisure_search_agent.call_event_search_tool",
            new_callable=AsyncMock,
            return_value=mock_search_results,
        ), patch(
            "flow.leisure_search_agent.leisure_search_agent.call_calendar_tool",
            new_callable=AsyncMock,
            return_value=mock_calendar_events,
        ):
            state = _make_state(
                leisure_search_params={
                    "query": "events",
                    "start_date": "2026-03-21",
                    "end_date": "2026-03-21",
                    "max_results": 10,
                }
            )
            result = await leisure_search_executor(state)

        assert result["is_success"] is True
        events = result["leisure_recommended_events"]
        assert len(events) == 2

        # Concert A (15:00-18:00) should fit — busy is only 09:00-11:00
        concert = next(e for e in events if e["title"] == "Concert A")
        assert concert["fits_free_time"] is True

        # Game B (10:00-12:30) overlaps with busy 09:00-11:00
        game = next(e for e in events if e["title"] == "Game B")
        assert game["fits_free_time"] is False

    @pytest.mark.asyncio
    async def test_handles_empty_search_results(self):
        with patch(
            "flow.leisure_search_agent.leisure_search_agent.call_event_search_tool",
            new_callable=AsyncMock,
            return_value=[],
        ):
            state = _make_state(
                leisure_search_params={"query": "nothing", "max_results": 10}
            )
            result = await leisure_search_executor(state)

        assert result["is_success"] is True
        assert result["leisure_recommended_events"] == []
        assert "couldn't find" in result["leisure_messages"][0].content


# ---------------------------------------------------------------------------
# leisure_message_handler tests
# ---------------------------------------------------------------------------

class TestLeisureMessageHandler:
    def test_returns_helpful_message(self):
        state = _make_state()
        result = leisure_message_handler(state)
        assert result["is_success"] is True
        assert "find events" in result["leisure_messages"][0].content.lower()
