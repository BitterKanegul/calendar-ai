"""
End-to-end metrics: task completion rate, latency statistics, turn efficiency.

`results` is a list of dicts with at minimum:
  success    – bool  (did the operation complete without error?)
  latency_ms – float (wall-clock time from request to response)
  turns      – int   (number of conversation turns, default 1 for direct ops;
                       2+ for confirmation / conflict-resolution flows)
"""

import statistics
from typing import Any


def compute_end_to_end_metrics(results: list[dict]) -> dict:
    """
    Aggregate end-to-end metrics.

    Returns:
        task_completion_rate  – fraction of successful completions
        avg_latency_ms        – mean latency
        median_latency_ms     – median latency
        p95_latency_ms        – 95th-percentile latency
        p99_latency_ms        – 99th-percentile latency
        avg_turns             – mean conversation turns to completion
        n                     – total cases
        n_success             – cases where success == True
    """
    if not results:
        return {}

    n = len(results)
    successes = [bool(r.get("success", False)) for r in results]
    latencies = [float(r.get("latency_ms", 0)) for r in results]
    turns = [int(r.get("turns", 1)) for r in results]

    sorted_lat = sorted(latencies)

    def percentile(data: list[float], pct: float) -> float:
        if not data:
            return 0.0
        idx = max(0, min(int(pct / 100 * len(data)), len(data) - 1))
        return round(data[idx], 1)

    return {
        "task_completion_rate": round(sum(successes) / n, 4),
        "avg_latency_ms": round(statistics.mean(latencies), 1),
        "median_latency_ms": round(statistics.median(latencies), 1),
        "p95_latency_ms": percentile(sorted_lat, 95),
        "p99_latency_ms": percentile(sorted_lat, 99),
        "avg_turns": round(statistics.mean(turns), 2),
        "n": n,
        "n_success": sum(successes),
    }


def compare_end_to_end(multi_agent: dict, baseline: dict) -> dict:
    """
    Side-by-side comparison of multi-agent vs baseline end-to-end metrics.
    Returns a diff dict with absolute and relative improvements.
    """
    if not multi_agent or not baseline:
        return {}

    def delta(key: str) -> dict[str, Any]:
        a = multi_agent.get(key, 0)
        b = baseline.get(key, 0)
        diff = round(a - b, 4)
        rel = round(diff / b, 4) if b else 0.0
        return {"multi_agent": a, "baseline": b, "delta": diff, "relative": rel}

    return {
        "task_completion_rate": delta("task_completion_rate"),
        "avg_latency_ms": delta("avg_latency_ms"),
        "median_latency_ms": delta("median_latency_ms"),
        "p95_latency_ms": delta("p95_latency_ms"),
        "avg_turns": delta("avg_turns"),
    }


def format_e2e_report(metrics: dict, system_name: str = "System") -> str:
    lines = [
        f"\n{'='*45}",
        f"  End-to-End Metrics — {system_name}",
        f"{'='*45}",
        f"  Task completion : {metrics.get('task_completion_rate', 0):.1%}  "
        f"({metrics.get('n_success', 0)}/{metrics.get('n', 0)})",
        f"  Avg latency     : {metrics.get('avg_latency_ms', 0):.0f} ms",
        f"  Median latency  : {metrics.get('median_latency_ms', 0):.0f} ms",
        f"  P95 latency     : {metrics.get('p95_latency_ms', 0):.0f} ms",
        f"  Avg turns       : {metrics.get('avg_turns', 1):.2f}",
        f"{'='*45}\n",
    ]
    return "\n".join(lines)
