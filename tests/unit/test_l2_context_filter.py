"""
tests/unit/test_l2_context_filter.py

Phase 2 unit tests for core/l2_context_filter.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest

from core.l2_context_filter import L2Item, filter_l2_items, inject_l2_context, serialize_context


# ──────────────────────────────────────────────
# Fixtures & helpers
# ──────────────────────────────────────────────


def make_item(id: str, score: float, ttl_days: int = 14) -> L2Item:
    return L2Item(
        id=id,
        title=f"Title for {id}",
        created_at="2026-03-01",
        last_accessed="2026-03-27",
        ttl_days=ttl_days,
        score=score,
    )


@pytest.fixture
def sample_items() -> list[L2Item]:
    return [
        make_item("L2-001", 0.9),
        make_item("L2-002", 0.7),
        make_item("L2-003", 0.5),
        make_item("L2-004", 0.3),
        make_item("L2-005", 0.1),
    ]


# ──────────────────────────────────────────────
# filter_l2_items tests
# ──────────────────────────────────────────────


class TestFilterL2Items:
    def test_normal_case_returns_above_threshold(self, sample_items):
        result = filter_l2_items(sample_items, threshold=0.5)
        # 0.9, 0.7, 0.5 should pass
        assert len(result) == 3
        assert all(item.score >= 0.5 for item in result)

    def test_empty_list_returns_empty(self):
        assert filter_l2_items([]) == []

    def test_all_below_threshold_returns_empty(self, sample_items):
        result = filter_l2_items(sample_items, threshold=0.99)
        assert result == []

    def test_all_above_threshold(self, sample_items):
        result = filter_l2_items(sample_items, threshold=0.0)
        assert len(result) == 5

    def test_sorted_by_score_descending(self, sample_items):
        result = filter_l2_items(sample_items, threshold=0.0, top_n=0)
        scores = [item.score for item in result]
        assert scores == sorted(scores, reverse=True)

    def test_top_n_limits_results(self, sample_items):
        result = filter_l2_items(sample_items, threshold=0.0, top_n=3)
        assert len(result) == 3

    def test_top_n_zero_means_no_limit(self, sample_items):
        result = filter_l2_items(sample_items, threshold=0.0, top_n=0)
        assert len(result) == 5

    def test_top_n_larger_than_items_returns_all_filtered(self, sample_items):
        result = filter_l2_items(sample_items, threshold=0.5, top_n=100)
        assert len(result) == 3  # only 0.9, 0.7, 0.5

    def test_threshold_exact_boundary_included(self, sample_items):
        """score == threshold should be included."""
        result = filter_l2_items(sample_items, threshold=0.5)
        ids = [item.id for item in result]
        assert "L2-003" in ids  # score=0.5

    def test_threshold_just_below_boundary_excluded(self, sample_items):
        """Items just below threshold are excluded."""
        result = filter_l2_items(sample_items, threshold=0.31)
        ids = [item.id for item in result]
        assert "L2-004" not in ids  # score=0.3

    def test_threshold_1_0_returns_only_perfect(self):
        items = [make_item("A", 1.0), make_item("B", 0.99), make_item("C", 0.5)]
        result = filter_l2_items(items, threshold=1.0)
        assert len(result) == 1
        assert result[0].id == "A"

    def test_threshold_0_0_returns_all(self):
        items = [make_item("A", 0.0), make_item("B", 0.5), make_item("C", 1.0)]
        result = filter_l2_items(items, threshold=0.0)
        assert len(result) == 3

    def test_ties_deterministic_id_descending(self):
        """Equal scores sorted by id descending (reverse alphabetical)."""
        items = [
            make_item("L2-001", 0.7),
            make_item("L2-003", 0.7),
            make_item("L2-002", 0.7),
        ]
        result = filter_l2_items(items, threshold=0.0, top_n=0)
        ids = [item.id for item in result]
        assert ids == ["L2-003", "L2-002", "L2-001"]

    def test_single_item_above_threshold(self):
        items = [make_item("L2-X", 0.8)]
        result = filter_l2_items(items, threshold=0.5)
        assert len(result) == 1
        assert result[0].id == "L2-X"

    def test_single_item_below_threshold(self):
        items = [make_item("L2-X", 0.4)]
        result = filter_l2_items(items, threshold=0.5)
        assert result == []

    def test_top_n_one_returns_highest_score(self, sample_items):
        result = filter_l2_items(sample_items, threshold=0.0, top_n=1)
        assert len(result) == 1
        assert result[0].score == 0.9

    def test_default_threshold_is_0_5(self):
        items = [make_item("A", 0.5), make_item("B", 0.49)]
        result = filter_l2_items(items)
        assert len(result) == 1
        assert result[0].id == "A"


# ──────────────────────────────────────────────
# serialize_context tests
# ──────────────────────────────────────────────


class TestSerializeContext:
    def test_empty_list_returns_empty_string(self):
        assert serialize_context([]) == ""

    def test_output_contains_header(self):
        items = [make_item("L2-001", 0.9)]
        output = serialize_context(items)
        assert "## L2 중기 기억 컨텍스트" in output

    def test_output_contains_item_id(self):
        items = [make_item("L2-001", 0.9)]
        output = serialize_context(items)
        assert "L2-001" in output

    def test_output_contains_item_title(self):
        items = [make_item("L2-001", 0.9)]
        output = serialize_context(items)
        assert "Title for L2-001" in output

    def test_output_contains_all_items(self):
        items = [make_item("L2-001", 0.9), make_item("L2-002", 0.7)]
        output = serialize_context(items)
        assert "L2-001" in output
        assert "L2-002" in output

    def test_output_is_string(self):
        items = [make_item("L2-001", 0.9)]
        assert isinstance(serialize_context(items), str)

    def test_output_contains_score(self):
        items = [make_item("L2-001", 0.85)]
        output = serialize_context(items)
        assert "0.85" in output

    def test_output_contains_last_accessed(self):
        items = [make_item("L2-001", 0.9)]
        output = serialize_context(items)
        assert "2026-03-27" in output


# ──────────────────────────────────────────────
# inject_l2_context tests
# ──────────────────────────────────────────────


class TestInjectL2Context:
    def test_returns_string(self, sample_items):
        result = inject_l2_context(sample_items)
        assert isinstance(result, str)

    def test_empty_list_returns_empty_string(self):
        assert inject_l2_context([]) == ""

    def test_below_threshold_items_excluded(self, sample_items):
        # threshold=0.8: only L2-001 (score=0.9) should pass
        result = inject_l2_context(sample_items, threshold=0.8)
        assert "L2-001" in result
        assert "L2-002" not in result
        assert "L2-003" not in result

    def test_combines_filter_and_serialize(self, sample_items):
        filtered = filter_l2_items(sample_items, threshold=0.5, top_n=10)
        serialized = serialize_context(filtered)
        combined = inject_l2_context(sample_items, threshold=0.5, top_n=10)
        assert combined == serialized

    def test_all_below_threshold_returns_empty_string(self, sample_items):
        result = inject_l2_context(sample_items, threshold=0.99)
        assert result == ""

    def test_top_n_respected(self, sample_items):
        # top_n=1 → only highest score item
        result = inject_l2_context(sample_items, threshold=0.0, top_n=1)
        assert "L2-001" in result
        assert "L2-002" not in result
