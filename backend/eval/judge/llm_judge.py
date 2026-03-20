"""
LLM-as-a-judge: rates responses on three 1–5 dimensions.

  naturalness  – does the response read naturally / conversationally?
  helpfulness  – does it address what the user asked for?
  accuracy     – did it take the correct action (route matches expected)?

Uses GPT-4.1 with a structured JSON output schema for deterministic scoring.
"""

import json
import logging
from openai import AsyncOpenAI
from config import settings

logger = logging.getLogger(__name__)

JUDGE_SYSTEM = (
    "You are an expert evaluator of conversational AI assistants. "
    "You will be given a user request, the assistant's response text, "
    "and metadata about the expected vs actual action taken. "
    "Rate the response on three dimensions using integers 1–5:\n\n"
    "  naturalness : 1=robotic/awkward, 5=natural and conversational\n"
    "  helpfulness : 1=completely unhelpful, 5=fully addresses the request\n"
    "  accuracy    : 1=wrong action taken, 5=exactly right action taken\n\n"
    "Return ONLY valid JSON in the form:\n"
    '{"naturalness": <int>, "helpfulness": <int>, "accuracy": <int>, '
    '"reasoning": "<one sentence>"}'
)

JUDGE_USER_TEMPLATE = """\
User request: {user_input}

Expected action: {expected_route}
Actual action taken: {actual_route}

Assistant response:
{response_text}
"""


async def judge_response(
    user_input: str,
    response_text: str,
    expected_route: str,
    actual_route: str,
) -> dict:
    """
    Score a single (user_input, response) pair.

    Returns:
        naturalness  – int 1–5
        helpfulness  – int 1–5
        accuracy     – int 1–5
        reasoning    – str
        error        – str (only on failure)
    """
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

    user_msg = JUDGE_USER_TEMPLATE.format(
        user_input=user_input,
        expected_route=expected_route,
        actual_route=actual_route,
        response_text=response_text or "(no text response)",
    )

    try:
        resp = await client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            temperature=0,
            max_tokens=200,
        )
        raw = resp.choices[0].message.content or ""
        scores = json.loads(raw)
        return {
            "naturalness": int(scores.get("naturalness", 3)),
            "helpfulness": int(scores.get("helpfulness", 3)),
            "accuracy": int(scores.get("accuracy", 3)),
            "reasoning": scores.get("reasoning", ""),
        }
    except Exception as exc:
        logger.warning("LLM judge failed: %s", exc)
        return {
            "naturalness": 0,
            "helpfulness": 0,
            "accuracy": 0,
            "reasoning": f"ERROR: {exc}",
            "error": str(exc),
        }


def aggregate_judge_scores(scores: list[dict]) -> dict:
    """
    Compute mean scores across a list of judge outputs.
    Skips entries with errors (score == 0 for all dims).
    """
    valid = [s for s in scores if s.get("naturalness", 0) > 0]
    if not valid:
        return {"mean_naturalness": 0.0, "mean_helpfulness": 0.0, "mean_accuracy": 0.0, "n": 0}

    n = len(valid)
    return {
        "mean_naturalness": round(sum(s["naturalness"] for s in valid) / n, 2),
        "mean_helpfulness": round(sum(s["helpfulness"] for s in valid) / n, 2),
        "mean_accuracy": round(sum(s["accuracy"] for s in valid) / n, 2),
        "n": n,
        "n_errors": len(scores) - n,
    }


def format_judge_report(agg: dict, system_name: str = "System") -> str:
    lines = [
        f"\n{'='*45}",
        f"  LLM Judge Scores — {system_name}  (1–5)",
        f"{'='*45}",
        f"  Naturalness : {agg.get('mean_naturalness', 0):.2f}",
        f"  Helpfulness : {agg.get('mean_helpfulness', 0):.2f}",
        f"  Accuracy    : {agg.get('mean_accuracy', 0):.2f}",
        f"  Scored      : {agg.get('n', 0)} / {agg.get('n', 0) + agg.get('n_errors', 0)}",
        f"{'='*45}\n",
    ]
    return "\n".join(lines)
