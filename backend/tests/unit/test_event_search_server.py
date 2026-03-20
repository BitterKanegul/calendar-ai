"""
Unit tests for the Event Search MCP Server.

Mocks httpx.AsyncClient to test normalization, category mapping, and error handling.
"""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from mcp_servers.event_search_server import (
    search_events,
    get_event_details,
    _normalize_event,
    _ticketmaster_request,
    CATEGORY_DURATION,
)


# ---------------------------------------------------------------------------
# Sample Ticketmaster API response fixtures
# ---------------------------------------------------------------------------

SAMPLE_TM_EVENT = {
    "id": "vvG1HZ4pMFkmSS",
    "name": "Lakers vs Celtics",
    "info": "NBA regular season game.",
    "url": "https://www.ticketmaster.com/event/vvG1HZ4pMFkmSS",
    "dates": {
        "start": {"dateTime": "2026-03-25T19:30:00Z"},
    },
    "classifications": [
        {"segment": {"name": "Sports"}, "genre": {"name": "Basketball"}}
    ],
    "_embedded": {
        "venues": [
            {
                "name": "Crypto.com Arena",
                "address": {"line1": "1111 S Figueroa St"},
                "city": {"name": "Los Angeles"},
            }
        ]
    },
    "priceRanges": [{"min": 45, "max": 250, "currency": "USD"}],
    "images": [{"url": "https://images.ticketmaster.com/dam/a/abc.jpg"}],
}

SAMPLE_TM_EVENT_MUSIC = {
    "id": "music123",
    "name": "Taylor Swift | The Eras Tour",
    "dates": {
        "start": {"dateTime": "2026-04-10T20:00:00Z"},
        "end": {"dateTime": "2026-04-10T23:30:00Z"},
    },
    "classifications": [
        {"segment": {"name": "Music"}, "genre": {"name": "Pop"}}
    ],
    "_embedded": {
        "venues": [
            {
                "name": "MetLife Stadium",
                "address": {"line1": "1 MetLife Stadium Dr"},
                "city": {"name": "East Rutherford"},
            }
        ]
    },
    "priceRanges": [{"min": 120, "max": 800, "currency": "USD"}],
    "images": [],
}


# ---------------------------------------------------------------------------
# _normalize_event tests
# ---------------------------------------------------------------------------

class TestNormalizeEvent:
    def test_normalizes_sports_event(self):
        result = _normalize_event(SAMPLE_TM_EVENT)

        assert result["external_id"] == "vvG1HZ4pMFkmSS"
        assert result["title"] == "Lakers vs Celtics"
        assert result["category"] == "sports"
        assert result["venue_name"] == "Crypto.com Arena"
        assert result["city"] == "Los Angeles"
        assert result["price_range"] == "$45 - $250"
        assert result["duration"] == CATEGORY_DURATION["sports"]
        # end_date should be estimated since API only has start
        assert result["end_date"] is not None

    def test_normalizes_music_event_with_end_date(self):
        result = _normalize_event(SAMPLE_TM_EVENT_MUSIC)

        assert result["category"] == "music"
        assert result["end_date"] == "2026-04-10T23:30:00Z"
        assert result["venue_name"] == "MetLife Stadium"

    def test_normalizes_event_missing_fields(self):
        minimal = {"id": "x", "name": "Minimal Event", "dates": {"start": {}}}
        result = _normalize_event(minimal)

        assert result["external_id"] == "x"
        assert result["title"] == "Minimal Event"
        assert result["category"] == "miscellaneous"
        assert result["venue_name"] == ""
        assert result["price_range"] == ""

    def test_category_mapping(self):
        for segment, expected in [("Music", "music"), ("Sports", "sports"), ("Arts & Theatre", "arts")]:
            ev = {
                "id": "test",
                "name": "Test",
                "dates": {"start": {}},
                "classifications": [{"segment": {"name": segment}}],
            }
            assert _normalize_event(ev)["category"] == expected


# ---------------------------------------------------------------------------
# _ticketmaster_request tests
# ---------------------------------------------------------------------------

class TestTicketmasterRequest:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_api_key(self):
        with patch("mcp_servers.event_search_server.settings") as mock_settings:
            mock_settings.TICKETMASTER_API_KEY = None
            result = await _ticketmaster_request("/events.json", {})
            assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_timeout(self):
        with patch("mcp_servers.event_search_server.settings") as mock_settings:
            mock_settings.TICKETMASTER_API_KEY = "test-key"
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.get.side_effect = httpx.TimeoutException("timeout")
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = instance

                result = await _ticketmaster_request("/events.json", {"keyword": "test"})
                assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_on_http_error(self):
        with patch("mcp_servers.event_search_server.settings") as mock_settings:
            mock_settings.TICKETMASTER_API_KEY = "test-key"
            with patch("httpx.AsyncClient") as MockClient:
                instance = AsyncMock()
                mock_response = MagicMock()
                mock_response.status_code = 401
                mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                    "Unauthorized", request=MagicMock(), response=mock_response
                )
                instance.get.return_value = mock_response
                instance.__aenter__ = AsyncMock(return_value=instance)
                instance.__aexit__ = AsyncMock(return_value=False)
                MockClient.return_value = instance

                result = await _ticketmaster_request("/events.json", {})
                assert result is None


# ---------------------------------------------------------------------------
# search_events tests
# ---------------------------------------------------------------------------

class TestSearchEvents:
    @pytest.mark.asyncio
    async def test_returns_normalized_events(self):
        mock_response = {
            "_embedded": {"events": [SAMPLE_TM_EVENT, SAMPLE_TM_EVENT_MUSIC]},
            "page": {"totalElements": 2},
        }
        with patch("mcp_servers.event_search_server._ticketmaster_request", return_value=mock_response):
            results = await search_events(query="test")

        assert len(results) == 2
        assert results[0]["external_id"] == "vvG1HZ4pMFkmSS"
        assert results[1]["category"] == "music"

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_results(self):
        with patch("mcp_servers.event_search_server._ticketmaster_request", return_value=None):
            results = await search_events(query="nonexistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_empty_embedded(self):
        with patch("mcp_servers.event_search_server._ticketmaster_request", return_value={"_embedded": {}}):
            results = await search_events(query="test")
        assert results == []


# ---------------------------------------------------------------------------
# get_event_details tests
# ---------------------------------------------------------------------------

class TestGetEventDetails:
    @pytest.mark.asyncio
    async def test_returns_normalized_event(self):
        with patch("mcp_servers.event_search_server._ticketmaster_request", return_value=SAMPLE_TM_EVENT):
            result = await get_event_details(event_id="vvG1HZ4pMFkmSS")

        assert result is not None
        assert result["title"] == "Lakers vs Celtics"

    @pytest.mark.asyncio
    async def test_returns_none_on_failure(self):
        with patch("mcp_servers.event_search_server._ticketmaster_request", return_value=None):
            result = await get_event_details(event_id="bad-id")
        assert result is None
