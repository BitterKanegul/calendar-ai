"""
Email MCP Server

Exposes Gmail operations as MCP tools, following the same pattern as
calendar_server.py. Agents call `call_email_tool()` from email_mcp_client.py
and never import this module directly.

Tools:
  - search_emails: query Gmail inbox, return email summaries
  - get_email_content: fetch full body of a specific email
"""
import base64
import logging
from typing import Optional

from fastmcp import FastMCP
from googleapiclient.discovery import build
from bs4 import BeautifulSoup

from .email_auth import get_gmail_credentials

logger = logging.getLogger(__name__)

mcp = FastMCP("Email")


def _build_gmail_service(user_id: int):
    creds = get_gmail_credentials(user_id)
    if not creds:
        raise PermissionError(f"No valid Gmail credentials for user {user_id}. Please connect Gmail first.")
    return build("gmail", "v1", credentials=creds)


def _decode_body(part: dict) -> str:
    """Decode a MIME body part to plain text."""
    data = part.get("body", {}).get("data", "")
    if not data:
        return ""
    try:
        return base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_text_from_payload(payload: dict) -> str:
    """Recursively extract plain text from a Gmail message payload."""
    mime_type = payload.get("mimeType", "")

    if mime_type == "text/plain":
        return _decode_body(payload)

    if mime_type == "text/html":
        html = _decode_body(payload)
        if html:
            return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)
        return ""

    # Multipart: recurse into parts
    if mime_type.startswith("multipart"):
        parts = payload.get("parts", [])
        # Prefer text/plain first
        for part in parts:
            if part.get("mimeType") == "text/plain":
                text = _decode_body(part)
                if text:
                    return text
        # Fall back to HTML
        for part in parts:
            text = _extract_text_from_payload(part)
            if text:
                return text

    return ""


@mcp.tool()
async def search_emails(
    user_id: int,
    query: str,
    date_range_start: Optional[str] = None,
    date_range_end: Optional[str] = None,
    sender: Optional[str] = None,
    max_results: int = 20,
) -> list[dict]:
    """
    Search a user's Gmail inbox.

    Returns a list of email summaries:
    [{"email_id": str, "subject": str, "sender": str, "date": str, "snippet": str}]
    """
    service = _build_gmail_service(user_id)

    # Build Gmail search query
    q_parts = [query] if query else []
    if date_range_start:
        q_parts.append(f"after:{date_range_start.replace('-', '/')}")
    if date_range_end:
        q_parts.append(f"before:{date_range_end.replace('-', '/')}")
    if sender:
        q_parts.append(f"from:{sender}")
    full_query = " ".join(q_parts) or "in:inbox"

    try:
        result = service.users().messages().list(
            userId="me",
            q=full_query,
            maxResults=max_results,
        ).execute()
    except Exception as e:
        logger.error(f"Gmail search failed for user {user_id}: {e}")
        return []

    messages = result.get("messages", [])
    summaries = []

    for msg in messages:
        try:
            detail = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="metadata",
                metadataHeaders=["Subject", "From", "Date"],
            ).execute()

            headers = {h["name"]: h["value"] for h in detail.get("payload", {}).get("headers", [])}
            summaries.append({
                "email_id": msg["id"],
                "subject":  headers.get("Subject", "(no subject)"),
                "sender":   headers.get("From", ""),
                "date":     headers.get("Date", ""),
                "snippet":  detail.get("snippet", ""),
            })
        except Exception as e:
            logger.warning(f"Failed to fetch email metadata {msg['id']}: {e}")
            continue

    return summaries


@mcp.tool()
async def get_email_content(email_id: str, user_id: int) -> dict:
    """
    Fetch the full content of a specific email.

    Returns: {"email_id": str, "subject": str, "sender": str,
              "date": str, "body": str}
    """
    service = _build_gmail_service(user_id)

    try:
        message = service.users().messages().get(
            userId="me",
            id=email_id,
            format="full",
        ).execute()
    except Exception as e:
        logger.error(f"Failed to fetch email {email_id} for user {user_id}: {e}")
        return {}

    payload = message.get("payload", {})
    headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
    body = _extract_text_from_payload(payload)

    return {
        "email_id": email_id,
        "subject":  headers.get("Subject", "(no subject)"),
        "sender":   headers.get("From", ""),
        "date":     headers.get("Date", ""),
        "body":     body,
    }
