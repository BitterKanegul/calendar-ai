"""Tests for slot extraction F1 metrics."""
import pytest
from eval.metrics.slot_metrics import compute_slot_f1, compute_aggregate_slot_metrics


def test_perfect_slot_match():
    result = compute_slot_f1(
        predicted_slots={"title": "meeting", "duration": 60},
        expected_slots={"title": "meeting", "duration": 60},
    )
    assert result["f1"] == 1.0
    assert result["tp"] == 2

def test_partial_slot_match():
    result = compute_slot_f1(
        predicted_slots={"title": "meeting"},
        expected_slots={"title": "meeting", "duration": 60},
    )
    assert result["recall"] < 1.0
    assert result["tp"] == 1
    assert result["fn"] == 1

def test_string_substring_matching():
    result = compute_slot_f1(
        predicted_slots={"title": "team meeting with john"},
        expected_slots={"title": "meeting"},
    )
    assert result["tp"] == 1

def test_numeric_tolerance():
    # 58 minutes vs 60 — within 20% tolerance
    result = compute_slot_f1(
        predicted_slots={"duration": 58},
        expected_slots={"duration": 60},
    )
    assert result["tp"] == 1

def test_aggregate_metrics():
    per_case = [
        {"f1": 1.0, "precision": 1.0, "recall": 1.0, "tp": 2, "fp": 0, "fn": 0},
        {"f1": 0.5, "precision": 0.5, "recall": 1.0, "tp": 1, "fp": 1, "fn": 0},
    ]
    agg = compute_aggregate_slot_metrics(per_case)
    assert agg["n"] == 2
    assert agg["mean_f1"] == pytest.approx(0.75)
