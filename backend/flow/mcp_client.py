"""
MCP Client utility for agent nodes.

Agents call `call_calendar_tool` instead of importing EventAdapter directly.
This keeps agent logic decoupled from service implementation — swapping the
underlying data source (e.g. Google Calendar) only requires changing
calendar_server.py, not any agent code.
"""
import json
import logging
from typing import Any

from fastmcp import Client

logger = logging.getLogger(__name__)

# Import the server instance once; all agents share the same in-process instance.
# Using in-process (memory) transport avoids network overhead during development
# while preserving the standard MCP protocol interface.
from mcp_servers.calendar_server import mcp as _calendar_mcp


async def call_calendar_tool(tool_name: str, arguments: dict) -> Any:
    """
    Call a Calendar MCP tool and return the deserialized Python result.

    Args:
        tool_name: Name of the MCP tool (e.g. "list_events", "check_conflicts").
        arguments: Dict of arguments to pass to the tool.

    Returns:
        Deserialized result (list, dict, bool, or None).
    """
    try:
        async with Client(_calendar_mcp) as client:
            result = await client.call_tool(tool_name, arguments)

        if not result:
            return None

        # FastMCP v2 returns a list of content objects.
        # Tool return values are serialized as JSON inside a TextContent item.
        content = result[0]
        raw = content.text if hasattr(content, "text") else str(content)

        # Unwrap JSON; handle plain "null" / "true" / "false" scalars too.
        return json.loads(raw)

    except Exception as e:
        logger.error(f"MCP tool call failed — tool={tool_name} args={arguments}: {e}")
        raise
