"""Tests for intent classification metrics."""
import pytest
from eval.metrics.intent_metrics import compute_intent_metrics


def test_perfect_accuracy():
    preds = ["create", "list", "delete", "update"]
    truth = ["create", "list", "delete", "update"]
    m = compute_intent_metrics(preds, truth)
    assert m["accuracy"] == 1.0
    assert m["n_correct"] == 4

def test_half_accuracy():
    preds = ["create", "list", "create", "list"]
    truth = ["create", "list", "delete", "update"]
    m = compute_intent_metrics(preds, truth)
    assert m["accuracy"] == 0.5

def test_per_class_f1():
    preds = ["create", "create", "list"]
    truth = ["create", "list",   "list"]
    m = compute_intent_metrics(preds, truth)
    # "create": TP=1, FP=1, FN=0  → precision=0.5, recall=1.0
    assert m["per_class"]["create"]["tp"] == 1
    assert m["per_class"]["create"]["fp"] == 1

def test_confusion_matrix():
    preds = ["create", "list"]
    truth = ["list",   "list"]
    m = compute_intent_metrics(preds, truth)
    assert m["confusion"]["list"]["create"] == 1  # predicted create, actual list
    assert m["confusion"]["list"]["list"] == 1
