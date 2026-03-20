"""
Slot extraction metrics.

Computes per-field and aggregated precision / recall / F1 by comparing
predicted slot dicts against expected slot dicts.

Value matching uses flexible rules:
  - Strings: case-insensitive substring match (predicted ⊆ expected or vice versa)
  - Numbers: within 20% relative tolerance
  - None expected value: treated as "don't care" (always matches)
"""

from typing import Any, Optional


def _values_match(predicted: Any, expected: Any) -> bool:
    """Flexible value equality for slot comparison."""
    if expected is None:
        return True  # "don't care"
    if predicted is None:
        return False
    # Numeric tolerance
    try:
        p_f, e_f = float(predicted), float(expected)
        denom = max(abs(e_f), 1.0)
        return abs(p_f - e_f) / denom <= 0.20
    except (TypeError, ValueError):
        pass
    # String substring match (case-insensitive)
    p_s, e_s = str(predicted).lower().strip(), str(expected).lower().strip()
    return e_s in p_s or p_s in e_s


def compute_slot_f1(
    predicted_slots: dict,
    expected_slots: dict,
    ignore_keys: Optional[set] = None,
) -> dict:
    """
    Compute precision / recall / F1 for a single (predicted, expected) slot pair.

    Only fields present in expected_slots (with non-None values) count as
    relevant; extra fields in predicted_slots are false positives only if
    they are not in expected_slots and not in ignore_keys.

    Returns: {f1, precision, recall, tp, fp, fn}
    """
    if ignore_keys is None:
        ignore_keys = set()

    relevant = {k: v for k, v in expected_slots.items() if k not in ignore_keys and v is not None}

    if not relevant:
        return {"f1": 1.0, "precision": 1.0, "recall": 1.0, "tp": 0, "fp": 0, "fn": 0}

    tp = sum(
        1 for k, v in relevant.items()
        if k in predicted_slots and _values_match(predicted_slots[k], v)
    )
    fp = sum(
        1 for k in predicted_slots
        if k not in relevant and k not in ignore_keys
    )
    fn = sum(1 for k in relevant if k not in predicted_slots)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return {
        "f1": round(f1, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def compute_aggregate_slot_metrics(results: list[dict]) -> dict:
    """
    Aggregate slot F1 over a list of per-case results.

    Each item in `results` must have keys: slot_f1, slot_precision, slot_recall.
    Returns mean values plus micro-aggregate TP/FP/FN.
    """
    if not results:
        return {"mean_f1": 0.0, "mean_precision": 0.0, "mean_recall": 0.0, "n": 0}

    total_tp = sum(r.get("tp", 0) for r in results)
    total_fp = sum(r.get("fp", 0) for r in results)
    total_fn = sum(r.get("fn", 0) for r in results)

    micro_prec = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
    micro_rec = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
    micro_f1 = (
        2 * micro_prec * micro_rec / (micro_prec + micro_rec)
        if (micro_prec + micro_rec) > 0
        else 0.0
    )

    mean_f1 = sum(r.get("f1", 0) for r in results) / len(results)

    return {
        "mean_f1": round(mean_f1, 4),
        "micro_f1": round(micro_f1, 4),
        "micro_precision": round(micro_prec, 4),
        "micro_recall": round(micro_rec, 4),
        "total_tp": total_tp,
        "total_fp": total_fp,
        "total_fn": total_fn,
        "n": len(results),
    }
