"""
Email MCP Client

Mirrors flow/mcp_client.py but for the Email MCP Server.
Agents use call_email_tool() so they stay decoupled from the server.
"""
import json
import logging
from typing import Any

from fastmcp import Client
from mcp_servers.email_server import mcp as _email_mcp

logger = logging.getLogger(__name__)


async def call_email_tool(tool_name: str, arguments: dict) -> Any:
    """
    Call an Email MCP tool and return the deserialized result.
    """
    try:
        async with Client(_email_mcp) as client:
            result = await client.call_tool(tool_name, arguments)

        if not result:
            return None

        content = result[0]
        raw = content.text if hasattr(content, "text") else str(content)
        return json.loads(raw)

    except Exception as e:
        logger.error(f"Email MCP tool call failed — tool={tool_name}: {e}")
        raise
