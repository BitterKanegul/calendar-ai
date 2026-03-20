"""
Email Retrieval Agent — LangGraph Node

Orchestrates the full email RAG pipeline:
  1. Generate a targeted search query from the user's message.
  2. Incrementally refresh the email index (rate-limited).
  3. Semantic search over the vector store.
  4. Extract structured events from top results via LLM.
  5. Return proposals grouped by confidence (high/medium/low).

If the user has no Gmail credentials, returns a clear error message.
"""
import logging
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import PromptTemplate

from ..state import FlowState
from ..llm import model
from .embeddings import EmailVectorStore
from .extractor import extract_events_from_chunks
from .index_manager import refresh_email_index
from .email_mcp_client import call_email_tool
from mcp_servers.email_auth import has_gmail_access

logger = logging.getLogger(__name__)

SEARCH_QUERY_PROMPT = """You are a Gmail search assistant. Given the user's request below, generate a concise Gmail search query (< 15 words) that will find relevant scheduling emails.

User request: {user_message}

Output ONLY the search query string, nothing else. Examples:
- "team meeting next week"
- "flight confirmation booking"
- "doctor appointment schedule"
- "event invitation conference"
"""


async def _generate_search_query(user_message: str) -> str:
    """Use the LLM to produce a focused Gmail search query from the user's message."""
    template = PromptTemplate.from_template(SEARCH_QUERY_PROMPT)
    prompt_text = template.format(user_message=user_message)
    try:
        response = await model.ainvoke([SystemMessage(content=prompt_text)])
        return response.content.strip().strip('"')
    except Exception:
        return "meeting appointment schedule"


async def email_retrieval_agent(state: FlowState) -> FlowState:
    """
    LangGraph node for the email RAG pipeline.
    Populates state['email_extracted_events'] and state['email_search_results'].
    """
    user_id = state["user_id"]

    # Guard: check Gmail credentials
    if not has_gmail_access(user_id):
        state["email_messages"].append(
            AIMessage(
                content=(
                    "I don't have access to your Gmail yet. "
                    "Please connect your Google account first by visiting /auth/google/connect."
                )
            )
        )
        state["email_extracted_events"] = {"high": [], "medium": [], "low": []}
        state["email_search_results"] = []
        state["is_success"] = True
        return state

    # Get the user's most recent message
    user_message = state.get("input_text", "")
    if not user_message and state.get("email_messages"):
        for msg in reversed(state["email_messages"]):
            if isinstance(msg, HumanMessage):
                user_message = msg.content
                break

    # Step 1: Generate search query
    search_query = await _generate_search_query(user_message)
    logger.info(f"Email search query for user {user_id}: '{search_query}'")

    # Step 2: Refresh index (incremental, rate-limited)
    store = EmailVectorStore(user_id)
    try:
        await refresh_email_index(store, user_id, call_email_tool)
    except Exception as e:
        logger.warning(f"Email index refresh failed for user {user_id}: {e}")
        # Continue with whatever is already indexed

    # Step 3: Semantic search
    try:
        chunks = store.search(search_query, top_k=10)
    except Exception as e:
        logger.error(f"Email semantic search failed: {e}")
        chunks = []

    # Step 4: Extract events
    extracted = await extract_events_from_chunks(chunks)

    total = sum(len(v) for v in extracted.values())
    high   = len(extracted.get("high",   []))
    medium = len(extracted.get("medium", []))
    low    = len(extracted.get("low",    []))

    if total == 0:
        reply = "I searched your recent emails but didn't find any clear scheduling information."
    else:
        parts = []
        if high:
            parts.append(f"{high} confirmed event{'s' if high > 1 else ''}")
        if medium:
            parts.append(f"{medium} possible meeting{'s' if medium > 1 else ''}")
        if low:
            parts.append(f"{low} informal mention{'s' if low > 1 else ''}")
        reply = "I found " + ", ".join(parts) + " in your recent emails."

    state["email_messages"].append(AIMessage(content=reply))
    state["email_extracted_events"] = extracted
    state["email_search_results"] = chunks
    state["is_success"] = True

    return state
