"""
MCP Client for the Event Search server.

Follows the same pattern as mcp_client.py — agents call
`call_event_search_tool` instead of importing the server directly.
"""
import json
import logging
from typing import Any

from fastmcp import Client

logger = logging.getLogger(__name__)

from mcp_servers.event_search_server import mcp as _event_search_mcp


async def call_event_search_tool(tool_name: str, arguments: dict) -> Any:
    """
    Call an Event Search MCP tool and return the deserialized Python result.

    Args:
        tool_name: Name of the MCP tool (e.g. "search_events", "get_event_details").
        arguments: Dict of arguments to pass to the tool.

    Returns:
        Deserialized result (list, dict, or None).
    """
    try:
        async with Client(_event_search_mcp) as client:
            result = await client.call_tool(tool_name, arguments)

        if not result:
            return None

        content = result[0]
        raw = content.text if hasattr(content, "text") else str(content)
        return json.loads(raw)

    except Exception as e:
        logger.error(f"Event Search MCP tool call failed — tool={tool_name} args={arguments}: {e}")
        raise
