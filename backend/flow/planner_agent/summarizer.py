"""
Plan Summarizer

Generates a natural language summary of all calendar changes made during
a planning session. Called as the final step of plan_executor.
"""
from langchain_core.messages import SystemMessage
from ..llm import model

SUMMARY_PROMPT = """You are summarizing calendar changes made during a planning session.

Changes made:
{changes}

Generate a clear, friendly 2-4 sentence summary. Be specific: mention event titles,
counts, and days where relevant. End with a brief note about the updated schedule
(e.g., total events, key busy days). Do not use bullet points — write in natural prose."""


async def generate_summary(changes: list[dict]) -> str:
    """
    Generate a natural language summary of planning changes via LLM.

    Each change dict has:
      - action: "created" | "updated" | "deleted" | "skipped"
      - event: dict with title, startDate, etc.
      - detail: optional extra context (e.g. "moved to avoid conflict")
    """
    if not changes:
        return "I reviewed your schedule but didn't make any changes."

    # Build a structured change log for the LLM
    lines = []
    for ch in changes:
        action = ch.get("action", "processed")
        ev = ch.get("event", {})
        title = ev.get("title", "event")
        start = ev.get("startDate", "")
        detail = ch.get("detail", "")

        # Format datetime for readability
        if start:
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(start)
                start = dt.strftime("%a %b %d at %I:%M %p")
            except Exception:
                pass

        line = f"- {action.upper()}: '{title}'"
        if start:
            line += f" on {start}"
        if detail:
            line += f" ({detail})"
        lines.append(line)

    changes_text = "\n".join(lines)
    prompt_text = SUMMARY_PROMPT.format(changes=changes_text)

    try:
        response = await model.ainvoke([SystemMessage(content=prompt_text)])
        return response.content.strip()
    except Exception:
        # Fallback: count-based summary
        created = sum(1 for c in changes if c.get("action") == "created")
        updated = sum(1 for c in changes if c.get("action") == "updated")
        deleted = sum(1 for c in changes if c.get("action") == "deleted")
        parts = []
        if created:
            parts.append(f"created {created} event{'s' if created > 1 else ''}")
        if updated:
            parts.append(f"updated {updated} event{'s' if updated > 1 else ''}")
        if deleted:
            parts.append(f"deleted {deleted} event{'s' if deleted > 1 else ''}")
        return "Done! I " + ", ".join(parts) + "." if parts else "Done!"
