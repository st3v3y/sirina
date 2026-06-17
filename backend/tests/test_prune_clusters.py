"""Tests for negligible-cluster pruning (the diarization 'phantom speaker' fix)."""
from dataclasses import dataclass

from app.processing.job import _prune_clusters


@dataclass
class L:
    start: float
    end: float


def test_drops_negligible_cluster_and_keeps_text():
    by = {
        "A": [L(0, 30)],          # 30s — real speaker
        "B": [L(30, 60)],         # 30s — real speaker
        "C": [L(60, 60.5)],       # 0.5s — brief noise
    }
    order = _prune_clusters(["A", "B", "C"], by)
    assert order == ["A", "B"]
    assert "C" not in by
    # The dropped cluster's line is merged into a kept speaker (no transcript lost).
    total_lines = sum(len(v) for v in by.values())
    assert total_lines == 3


def test_keeps_all_when_balanced():
    by = {"A": [L(0, 20)], "B": [L(20, 40)]}
    order = _prune_clusters(["A", "B"], by)
    assert order == ["A", "B"]


def test_always_keeps_at_least_one():
    by = {"A": [L(0, 0.4)], "B": [L(0.4, 0.8)]}
    order = _prune_clusters(["A", "B"], by)
    assert len(order) >= 1


def test_single_cluster_untouched():
    by = {"A": [L(0, 1)]}
    assert _prune_clusters(["A"], by) == ["A"]
