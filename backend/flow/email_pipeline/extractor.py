"""
Email Event Extractor

Uses the LLM to extract structured scheduling events from email chunks.
Results are grouped into three confidence tiers:
  - HIGH:   flight/hotel confirmations, formal calendar invites → auto-propose
  - MEDIUM: meeting requests, rescheduling notices → show to user
  - LOW:    casual mentions ("let's meet Tuesday") → mention in passing
"""
import json
import logging
from langchain_core.messages import SystemMessage
from ..llm import model

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are a calendar event extraction assistant.

Given email content below, extract any scheduling-relevant information.
For each potential event found, produce one JSON object.

Email content:
{email_text}

Return ONLY a JSON array (no extra text). Each item:
{{
  "title":       "descriptive event title (in English)",
  "start_date":  "ISO 8601 datetime string, or null if unknown",
  "end_date":    "ISO 8601 datetime string, or null",
  "location":    "location string, or null",
  "confidence":  "high" | "medium" | "low",
  "source_type": "confirmation" | "invitation" | "informal_mention",
  "evidence":    "the exact text excerpt that indicates this event"
}}

Confidence guidelines:
- "high":   flight/hotel/restaurant confirmations, registration confirmations,
            formal calendar invites (.ics), any email with a specific date+time
            AND a confirmation or booking number.
- "medium": meeting requests, rescheduling notices, emails with a proposed
            specific date+time but no booking confirmation.
- "low":    casual mentions of a future activity ("let's grab coffee Tuesday"),
            vague scheduling references ("we should meet soon").

Return [] if no scheduling information is found."""


async def extract_events_from_chunks(chunks: list[dict]) -> dict:
    """
    Run event extraction over a list of email chunk dicts.

    Returns:
      {
        "high":   [event_dict, ...],
        "medium": [event_dict, ...],
        "low":    [event_dict, ...],
      }
    """
    if not chunks:
        return {"high": [], "medium": [], "low": []}

    # Deduplicate by email_id so we don't send the same email twice
    seen: set[str] = set()
    unique_chunks: list[dict] = []
    for chunk in chunks:
        eid = chunk.get("email_id", "")
        if eid not in seen:
            seen.add(eid)
            unique_chunks.append(chunk)

    combined_text = "\n---\n".join(
        f"Subject: {c['subject']}\nFrom: {c['sender']}\nDate: {c['date']}\n\n{c['chunk_text']}"
        for c in unique_chunks[:10]   # cap to avoid blowing context window
    )

    prompt_text = EXTRACTION_PROMPT.format(email_text=combined_text)

    try:
        response = await model.ainvoke([SystemMessage(content=prompt_text)])
        events = json.loads(response.content.strip())
        if not isinstance(events, list):
            events = []
    except Exception as e:
        logger.warning(f"Event extraction failed: {e}")
        events = []

    grouped: dict[str, list] = {"high": [], "medium": [], "low": []}
    for ev in events:
        confidence = ev.get("confidence", "low")
        if confidence in grouped:
            grouped[confidence].append(ev)
        else:
            grouped["low"].append(ev)

    return grouped
