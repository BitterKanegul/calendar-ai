"""
A/B comparison harness.

Runs each test case through:
  1. The multi-agent router (component-level — no DB required)
  2. The single-agent baseline

Collects per-case results and feeds them to the metrics modules.
"""

import asyncio
import logging
import time
from langchain_core.messages import HumanMessage, SystemMessage

from eval.baseline.single_agent import run_baseline
from eval.metrics.intent_metrics import compute_intent_metrics
from eval.metrics.slot_metrics import compute_slot_f1, compute_aggregate_slot_metrics
from eval.metrics.end_to_end_metrics import compute_end_to_end_metrics, compare_end_to_end
from eval.judge.llm_judge import judge_response, aggregate_judge_scores

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_router_state(tc: dict) -> dict:
    """Build a minimal FlowState dict sufficient for router_agent."""
    ctx = tc["context"]
    return {
        "router_messages": [HumanMessage(content=tc["input"])],
        "create_messages": [],
        "delete_messages": [],
        "list_messages": [],
        "update_messages": [],
        "email_messages": [],
        "input_text": tc["input"],
        "current_datetime": ctx["current_datetime"],
        "weekday": ctx["weekday"],
        "days_in_month": ctx["days_in_month"],
        "user_id": 0,
        "route": {},
        "create_event_data": None,
        "create_conflict_events": [],
        "list_date_range_data": {},
        "list_date_range_filtered_events": [],
        "list_final_filtered_events": [],
        "delete_date_range_data": {},
        "delete_date_range_filtered_events": [],
        "delete_final_filtered_events": [],
        "update_date_range_data": {},
        "update_date_range_filtered_events": [],
        "update_final_filtered_events": [],
        "update_arguments": {},
        "update_conflict_event": None,
        "resolution_plan": None,
        "resolution_type": None,
        "awaiting_confirmation": False,
        "confirmation_type": None,
        "confirmation_data": None,
        "plan_tasks": None,
        "plan_results": None,
        "plan_summary": None,
        "is_planning_mode": False,
        "email_extracted_events": None,
        "email_search_results": None,
        "is_success": False,
    }


async def _run_router(tc: dict) -> dict:
    """Run the multi-agent router on a single test case (no DB needed)."""
    from flow.router_agent.router_agent import router_agent

    state = _make_router_state(tc)
    start = time.perf_counter()
    try:
        result = await router_agent(state)
        latency_ms = (time.perf_counter() - start) * 1000
        route_data = result.get("route", {})
        predicted_route = (
            route_data.get("route", "message")
            if isinstance(route_data, dict)
            else "message"
        )
        response_text = ""
        if result.get("router_messages"):
            last = result["router_messages"][-1]
            if hasattr(last, "content"):
                response_text = last.content
        return {
            "id": tc["id"],
            "predicted_route": predicted_route,
            "route_data": route_data,
            "response_text": response_text,
            "latency_ms": round(latency_ms, 1),
            "success": True,
            "turns": 1,
        }
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        logger.error("Router eval error on %s: %s", tc["id"], exc)
        return {
            "id": tc["id"],
            "predicted_route": "error",
            "route_data": {},
            "response_text": "",
            "latency_ms": round(latency_ms, 1),
            "success": False,
            "turns": 1,
            "error": str(exc),
        }


# ── Main harness ─────────────────────────────────────────────────────────────

async def run_harness(
    test_cases: list[dict],
    run_judge: bool = True,
    concurrency: int = 5,
) -> dict:
    """
    Execute A/B evaluation on all test cases.

    Args:
        test_cases  – loaded from dataset/test_cases.json
        run_judge   – if True, call LLM judge for each case (costs tokens)
        concurrency – max parallel API calls per system

    Returns a nested dict with all raw results and aggregated metrics.
    """
    sem = asyncio.Semaphore(concurrency)

    async def bounded_router(tc):
        async with sem:
            return await _run_router(tc)

    async def bounded_baseline(tc):
        async with sem:
            ctx = tc["context"]
            return {
                "id": tc["id"],
                **await run_baseline(
                    user_input=tc["input"],
                    current_datetime=ctx["current_datetime"],
                    weekday=ctx["weekday"],
                    days_in_month=ctx.get("days_in_month", 31),
                ),
                "turns": 1,
            }

    logger.info("Running multi-agent router on %d test cases …", len(test_cases))
    router_raw = await asyncio.gather(*[bounded_router(tc) for tc in test_cases])

    logger.info("Running single-agent baseline on %d test cases …", len(test_cases))
    baseline_raw = await asyncio.gather(*[bounded_baseline(tc) for tc in test_cases])

    # ── Intent metrics ────────────────────────────────────────────────────────
    gt_routes = [tc["expected"]["route"] for tc in test_cases]
    router_preds = [r["predicted_route"] for r in router_raw]
    baseline_preds = [r["route"] for r in baseline_raw]

    router_intent = compute_intent_metrics(router_preds, gt_routes)
    baseline_intent = compute_intent_metrics(baseline_preds, gt_routes)

    # ── Slot metrics (create cases only, where expected slots are non-empty) ──
    slot_cases = [
        tc for tc in test_cases
        if tc["expected"].get("slots") and tc["expected"]["route"] == "create"
    ]
    router_slot_results, baseline_slot_results = [], []

    router_by_id = {r["id"]: r for r in router_raw}
    baseline_by_id = {r["id"]: r for r in baseline_raw}

    for tc in slot_cases:
        expected_slots = tc["expected"]["slots"]

        # Router: extract slots from route_data if route is create
        r_data = router_by_id.get(tc["id"], {})
        r_slots = r_data.get("route_data", {})  # router returns full route dict
        # Flatten one level if needed
        if "arguments" in r_slots:
            r_slots = r_slots["arguments"]

        sf_router = compute_slot_f1(r_slots, expected_slots)
        sf_router["id"] = tc["id"]
        router_slot_results.append(sf_router)

        b_data = baseline_by_id.get(tc["id"], {})
        b_slots = b_data.get("extracted_slots", {})
        sf_baseline = compute_slot_f1(b_slots, expected_slots)
        sf_baseline["id"] = tc["id"]
        baseline_slot_results.append(sf_baseline)

    router_slots_agg = compute_aggregate_slot_metrics(router_slot_results)
    baseline_slots_agg = compute_aggregate_slot_metrics(baseline_slot_results)

    # ── End-to-end (latency + completion) ────────────────────────────────────
    router_e2e = compute_end_to_end_metrics(router_raw)
    baseline_e2e = compute_end_to_end_metrics(baseline_raw)
    e2e_comparison = compare_end_to_end(router_e2e, baseline_e2e)

    # ── LLM judge ─────────────────────────────────────────────────────────────
    router_judge_scores, baseline_judge_scores = [], []
    if run_judge:
        logger.info("Running LLM judge …")
        judge_sem = asyncio.Semaphore(3)  # rate-limit judge calls

        async def judge_pair(tc, r_result, b_result):
            async with judge_sem:
                gt_route = tc["expected"]["route"]
                r_score = await judge_response(
                    user_input=tc["input"],
                    response_text=r_result.get("response_text", ""),
                    expected_route=gt_route,
                    actual_route=r_result.get("predicted_route", ""),
                )
                b_score = await judge_response(
                    user_input=tc["input"],
                    response_text=b_result.get("response_text", ""),
                    expected_route=gt_route,
                    actual_route=b_result.get("route", ""),
                )
                return r_score, b_score

        judge_pairs = await asyncio.gather(*[
            judge_pair(tc, router_by_id[tc["id"]], baseline_by_id[tc["id"]])
            for tc in test_cases
        ])
        router_judge_scores = [p[0] for p in judge_pairs]
        baseline_judge_scores = [p[1] for p in judge_pairs]

    router_judge_agg = aggregate_judge_scores(router_judge_scores)
    baseline_judge_agg = aggregate_judge_scores(baseline_judge_scores)

    # ── Assemble full report dict ─────────────────────────────────────────────
    return {
        "n_cases": len(test_cases),
        "multi_agent": {
            "raw": router_raw,
            "intent": router_intent,
            "slot_f1": router_slots_agg,
            "per_case_slots": router_slot_results,
            "e2e": router_e2e,
            "judge": router_judge_agg,
            "judge_per_case": router_judge_scores,
        },
        "baseline": {
            "raw": baseline_raw,
            "intent": baseline_intent,
            "slot_f1": baseline_slots_agg,
            "per_case_slots": baseline_slot_results,
            "e2e": baseline_e2e,
            "judge": baseline_judge_agg,
            "judge_per_case": baseline_judge_scores,
        },
        "e2e_comparison": e2e_comparison,
        "intent_delta": {
            "accuracy": round(router_intent["accuracy"] - baseline_intent["accuracy"], 4),
            "macro_f1": round(router_intent["macro_f1"] - baseline_intent["macro_f1"], 4),
        },
        "slot_delta": {
            "mean_f1": round(
                router_slots_agg.get("mean_f1", 0) - baseline_slots_agg.get("mean_f1", 0), 4
            ),
        },
    }
