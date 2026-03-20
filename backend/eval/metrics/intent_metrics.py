"""
Intent classification metrics.

Computes accuracy and per-class precision / recall / F1 for route predictions
compared against ground-truth labels.
"""

from collections import defaultdict
from typing import Optional


def compute_intent_metrics(
    predictions: list[str],
    ground_truth: list[str],
) -> dict:
    """
    Args:
        predictions:  list of predicted route strings
        ground_truth: list of expected route strings (same length)

    Returns a dict with:
        accuracy      – overall fraction correct
        macro_f1      – unweighted mean F1 across classes
        per_class     – {class: {precision, recall, f1, support, tp, fp, fn}}
        confusion     – {actual: {predicted: count}}  (confusion matrix)
        n             – total test cases
        n_correct     – total correct
    """
    assert len(predictions) == len(ground_truth), "Lists must have equal length"

    n = len(predictions)
    n_correct = sum(p == g for p, g in zip(predictions, ground_truth))

    classes = sorted(set(ground_truth) | set(predictions))

    # Build confusion matrix
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for pred, true in zip(predictions, ground_truth):
        confusion[true][pred] += 1

    per_class: dict[str, dict] = {}
    f1_sum = 0.0
    for cls in classes:
        tp = confusion[cls].get(cls, 0)
        fp = sum(confusion[other].get(cls, 0) for other in classes if other != cls)
        fn = sum(confusion[cls].get(other, 0) for other in classes if other != cls)
        support = tp + fn  # total ground-truth positives for this class

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = (
            2 * precision * recall / (precision + recall)
            if (precision + recall) > 0
            else 0.0
        )

        per_class[cls] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": support,
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }
        f1_sum += f1

    macro_f1 = f1_sum / len(classes) if classes else 0.0

    return {
        "accuracy": round(n_correct / n, 4) if n > 0 else 0.0,
        "macro_f1": round(macro_f1, 4),
        "per_class": per_class,
        "confusion": {k: dict(v) for k, v in confusion.items()},
        "n": n,
        "n_correct": n_correct,
    }


def format_intent_report(metrics: dict, system_name: str = "System") -> str:
    """Return a human-readable intent metrics table."""
    lines = [
        f"\n{'='*55}",
        f"  Intent Classification — {system_name}",
        f"{'='*55}",
        f"  Overall accuracy : {metrics['accuracy']:.1%}  ({metrics['n_correct']}/{metrics['n']})",
        f"  Macro F1         : {metrics['macro_f1']:.4f}",
        f"\n  {'Class':<18} {'P':>6} {'R':>6} {'F1':>6} {'Supp':>6}",
        f"  {'-'*46}",
    ]
    for cls, s in sorted(metrics["per_class"].items()):
        lines.append(
            f"  {cls:<18} {s['precision']:>6.3f} {s['recall']:>6.3f} {s['f1']:>6.3f} {s['support']:>6}"
        )
    lines.append(f"{'='*55}\n")
    return "\n".join(lines)
