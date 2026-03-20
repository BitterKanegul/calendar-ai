"""
Report generation: console summary + JSON output.
"""

import json
import os
from datetime import datetime

from eval.metrics.intent_metrics import format_intent_report
from eval.metrics.end_to_end_metrics import format_e2e_report
from eval.judge.llm_judge import format_judge_report


def print_summary(results: dict) -> None:
    """Print a human-readable A/B comparison to stdout."""
    sep = "=" * 60

    print(f"\n{sep}")
    print("  CALENDAR AI — EVALUATION REPORT")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Test cases: {results['n_cases']}")
    print(sep)

    # ── Intent classification ─────────────────────────────────────────────────
    print(format_intent_report(results["multi_agent"]["intent"], "Multi-Agent Router"))
    print(format_intent_report(results["baseline"]["intent"], "Single-Agent Baseline"))

    ma_acc = results["multi_agent"]["intent"]["accuracy"]
    bl_acc = results["baseline"]["intent"]["accuracy"]
    delta_acc = results["intent_delta"]["accuracy"]
    winner = "Multi-Agent" if delta_acc >= 0 else "Baseline"
    print(f"  Intent accuracy delta: {delta_acc:+.1%}  → {winner} wins\n")

    # ── Slot extraction ───────────────────────────────────────────────────────
    ma_sf = results["multi_agent"]["slot_f1"]
    bl_sf = results["baseline"]["slot_f1"]
    if ma_sf.get("n", 0) > 0:
        print(f"  Slot Extraction F1 (create cases, n={ma_sf['n']})")
        print(f"    Multi-Agent  mean F1 = {ma_sf['mean_f1']:.4f}  micro F1 = {ma_sf.get('micro_f1', 0):.4f}")
        print(f"    Baseline     mean F1 = {bl_sf['mean_f1']:.4f}  micro F1 = {bl_sf.get('micro_f1', 0):.4f}")
        delta_sf = results["slot_delta"]["mean_f1"]
        print(f"    Slot F1 delta: {delta_sf:+.4f}\n")

    # ── End-to-end ────────────────────────────────────────────────────────────
    print(format_e2e_report(results["multi_agent"]["e2e"], "Multi-Agent"))
    print(format_e2e_report(results["baseline"]["e2e"], "Single-Agent Baseline"))

    cmp = results.get("e2e_comparison", {})
    if cmp:
        lat = cmp.get("avg_latency_ms", {})
        print(
            f"  Latency delta: {lat.get('delta', 0):+.0f} ms  "
            f"({lat.get('relative', 0):+.1%} vs baseline)"
        )
        comp_rate = cmp.get("task_completion_rate", {})
        print(
            f"  Completion delta: {comp_rate.get('delta', 0):+.1%}\n"
        )

    # ── LLM judge ─────────────────────────────────────────────────────────────
    if results["multi_agent"]["judge"].get("n", 0) > 0:
        print(format_judge_report(results["multi_agent"]["judge"], "Multi-Agent"))
        print(format_judge_report(results["baseline"]["judge"], "Single-Agent Baseline"))

        ma_j = results["multi_agent"]["judge"]
        bl_j = results["baseline"]["judge"]
        delta_nat = round(ma_j["mean_naturalness"] - bl_j["mean_naturalness"], 2)
        delta_help = round(ma_j["mean_helpfulness"] - bl_j["mean_helpfulness"], 2)
        delta_acc_j = round(ma_j["mean_accuracy"] - bl_j["mean_accuracy"], 2)
        print(
            f"  Judge deltas  naturalness={delta_nat:+.2f}  "
            f"helpfulness={delta_help:+.2f}  accuracy={delta_acc_j:+.2f}\n"
        )

    print(sep + "\n")


def save_report(results: dict, output_path: str) -> None:
    """Write full results to a JSON file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Make JSON-serialisable (remove raw LangChain message objects)
    def _clean(obj):
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean(i) for i in obj]
        if hasattr(obj, "content"):   # BaseMessage
            return {"role": type(obj).__name__, "content": obj.content}
        return obj

    clean = _clean(results)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, default=str)
    print(f"  Report saved → {output_path}")
