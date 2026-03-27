"""
tests/unit/test_l2_to_l3_archiver.py

Phase 3 unit tests for core/l2_to_l3_archiver.py
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from loguru import logger

from core.l2_context_filter import L2Item
from core.l2_to_l3_archiver import (
    L3ArchiveEntry,
    archive_expired_items,
    is_expired,
)


# ──────────────────────────────────────────────
# Fixtures & helpers
# ──────────────────────────────────────────────

TODAY = date(2026, 3, 27)


def make_item(
    id: str,
    score: float,
    ttl_days: int = 14,
    last_accessed: str = "2026-03-27",
    expired: bool | None = None,
) -> L2Item:
    item = L2Item(
        id=id,
        title=f"Title for {id}",
        created_at="2026-03-01",
        last_accessed=last_accessed,
        ttl_days=ttl_days,
        score=score,
    )
    if expired is not None:
        object.__setattr__(item, "expired", expired) if hasattr(item, "__setattr__") else None
        # L2Item is a regular dataclass — just set the attribute
        item.__dict__["expired"] = expired
    return item


def add_expired_flag(item: L2Item, value: bool) -> L2Item:
    """Helper: attach 'expired' attribute to an existing L2Item."""
    item.__dict__["expired"] = value
    return item


@pytest.fixture
def healthy_item() -> L2Item:
    return make_item("L2-H", score=0.8, ttl_days=14, last_accessed="2026-03-27")


@pytest.fixture
def low_score_item() -> L2Item:
    return make_item("L2-LS", score=0.2, ttl_days=14, last_accessed="2026-03-27")


@pytest.fixture
def ttl_expired_item() -> L2Item:
    # last_accessed 20 days ago, ttl_days=10 → expired
    return make_item("L2-TTL", score=0.6, ttl_days=10, last_accessed="2026-03-07")


@pytest.fixture
def explicit_expired_item() -> L2Item:
    item = make_item("L2-EXP", score=0.8, ttl_days=14, last_accessed="2026-03-27")
    add_expired_flag(item, True)
    return item


# ──────────────────────────────────────────────
# is_expired tests
# ──────────────────────────────────────────────


class TestIsExpired:
    def test_healthy_item_not_expired(self, healthy_item):
        expired, reason = is_expired(healthy_item, today=TODAY)
        assert not expired
        assert reason == ""

    def test_score_below_min_is_expired(self, low_score_item):
        expired, reason = is_expired(low_score_item, today=TODAY)
        assert expired
        assert reason == "score_below_min"

    def test_score_exactly_0_3_not_expired(self):
        item = make_item("L2-B", score=0.3, ttl_days=14, last_accessed="2026-03-27")
        expired, reason = is_expired(item, today=TODAY)
        assert not expired
        assert reason == ""

    def test_score_0_29_is_expired(self):
        item = make_item("L2-B", score=0.29, ttl_days=14, last_accessed="2026-03-27")
        expired, reason = is_expired(item, today=TODAY)
        assert expired
        assert reason == "score_below_min"

    def test_ttl_exceeded_is_expired(self, ttl_expired_item):
        expired, reason = is_expired(ttl_expired_item, today=TODAY)
        assert expired
        assert reason == "ttl_expired"

    def test_ttl_not_exceeded_is_not_expired(self):
        # accessed 5 days ago, ttl=14
        item = make_item("L2-OK", score=0.6, ttl_days=14, last_accessed="2026-03-22")
        expired, reason = is_expired(item, today=TODAY)
        assert not expired
        assert reason == ""

    def test_ttl_exactly_met_is_not_expired(self):
        # accessed exactly ttl_days ago — days_elapsed == ttl_days (not >)
        item = make_item("L2-EQ", score=0.6, ttl_days=14, last_accessed="2026-03-13")
        expired, reason = is_expired(item, today=TODAY)
        assert not expired

    def test_ttl_one_day_over_is_expired(self):
        # accessed ttl_days+1 days ago
        item = make_item("L2-OVR", score=0.6, ttl_days=14, last_accessed="2026-03-12")
        expired, reason = is_expired(item, today=TODAY)
        assert expired
        assert reason == "ttl_expired"

    def test_explicit_expiry_flag_true(self, explicit_expired_item):
        expired, reason = is_expired(explicit_expired_item, today=TODAY)
        assert expired
        assert reason == "explicit_expiry"

    def test_explicit_expiry_takes_priority_over_score(self):
        """explicit_expiry checked before score_below_min."""
        item = make_item("L2-PRI", score=0.1, ttl_days=14, last_accessed="2026-03-27")
        add_expired_flag(item, True)
        expired, reason = is_expired(item, today=TODAY)
        assert expired
        assert reason == "explicit_expiry"

    def test_explicit_flag_false_not_expired(self):
        item = make_item("L2-OK2", score=0.8, ttl_days=14, last_accessed="2026-03-27")
        add_expired_flag(item, False)
        expired, reason = is_expired(item, today=TODAY)
        assert not expired

    def test_today_defaults_to_real_today(self):
        """is_expired with today=None should not raise."""
        item = make_item("L2-DEF", score=0.8, ttl_days=14, last_accessed="2026-03-27")
        # Just assert it runs without error
        result = is_expired(item, today=None)
        assert isinstance(result, tuple)
        assert len(result) == 2


# ──────────────────────────────────────────────
# archive_expired_items tests
# ──────────────────────────────────────────────


class TestArchiveExpiredItems:
    def test_empty_list_returns_empty(self):
        archived, remaining = archive_expired_items([], today=TODAY)
        assert archived == []
        assert remaining == []

    def test_no_expired_items_returns_all_remaining(self, healthy_item):
        archived, remaining = archive_expired_items([healthy_item], today=TODAY)
        assert archived == []
        assert len(remaining) == 1
        assert remaining[0].id == "L2-H"

    def test_all_expired_returns_all_archived(self, low_score_item, ttl_expired_item):
        archived, remaining = archive_expired_items(
            [low_score_item, ttl_expired_item], today=TODAY
        )
        assert len(archived) == 2
        assert remaining == []

    def test_mixed_returns_correct_split(
        self, healthy_item, low_score_item, ttl_expired_item
    ):
        items = [healthy_item, low_score_item, ttl_expired_item]
        archived, remaining = archive_expired_items(items, today=TODAY)
        assert len(archived) == 2
        assert len(remaining) == 1
        assert remaining[0].id == "L2-H"

    def test_remaining_preserves_order(self):
        items = [
            make_item("L2-A", score=0.8, last_accessed="2026-03-27"),
            make_item("L2-B", score=0.8, last_accessed="2026-03-27"),
            make_item("L2-C", score=0.8, last_accessed="2026-03-27"),
        ]
        _, remaining = archive_expired_items(items, today=TODAY)
        assert [i.id for i in remaining] == ["L2-A", "L2-B", "L2-C"]

    def test_l3_archive_entry_has_correct_source_id(self, low_score_item):
        archived, _ = archive_expired_items([low_score_item], today=TODAY)
        assert archived[0].source_l2_id == "L2-LS"

    def test_l3_archive_entry_has_correct_reason(self, low_score_item, ttl_expired_item):
        archived, _ = archive_expired_items(
            [low_score_item, ttl_expired_item], today=TODAY
        )
        reasons = {e.source_l2_id: e.reason for e in archived}
        assert reasons["L2-LS"] == "score_below_min"
        assert reasons["L2-TTL"] == "ttl_expired"

    def test_l3_archive_entry_fields(self, low_score_item):
        archived, _ = archive_expired_items([low_score_item], today=TODAY)
        entry = archived[0]
        assert isinstance(entry, L3ArchiveEntry)
        assert entry.id == "L3-L2-LS"
        assert entry.title == "Title for L2-LS"
        assert entry.archived_at == TODAY.isoformat()
        assert entry.original_score == pytest.approx(0.2)
        assert entry.original_ttl_days == 14

    def test_writes_to_archive_path(self, tmp_path, low_score_item):
        archive_file = tmp_path / "l3_archive.jsonl"
        archive_expired_items([low_score_item], archive_path=archive_file, today=TODAY)
        assert archive_file.exists()
        lines = archive_file.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["source_l2_id"] == "L2-LS"
        assert data["reason"] == "score_below_min"

    def test_appends_to_existing_file(self, tmp_path, low_score_item, ttl_expired_item):
        archive_file = tmp_path / "l3_archive.jsonl"
        archive_expired_items([low_score_item], archive_path=archive_file, today=TODAY)
        archive_expired_items([ttl_expired_item], archive_path=archive_file, today=TODAY)
        lines = archive_file.read_text().strip().splitlines()
        assert len(lines) == 2  # file was appended, not overwritten

    def test_no_archive_path_does_not_create_file(self, tmp_path, low_score_item):
        archive_expired_items([low_score_item], archive_path=None, today=TODAY)
        # No file should exist
        assert not any(tmp_path.iterdir())

    def test_logging_on_archive(self, low_score_item, capfd):
        """Verify logger.info is called (captured via loguru sink)."""
        log_messages: list[str] = []

        def capture(message):
            log_messages.append(message)

        sink_id = logger.add(capture, format="{message}")
        try:
            archive_expired_items([low_score_item], today=TODAY)
        finally:
            logger.remove(sink_id)

        assert any("L2→L3" in m for m in log_messages)
        assert any("L2-LS" in m for m in log_messages)

    def test_archive_jsonl_format(self, tmp_path, low_score_item, ttl_expired_item):
        archive_file = tmp_path / "archive.jsonl"
        archive_expired_items(
            [low_score_item, ttl_expired_item], archive_path=archive_file, today=TODAY
        )
        lines = archive_file.read_text().strip().splitlines()
        assert len(lines) == 2
        for line in lines:
            obj = json.loads(line)
            # Must have all required fields
            for field in (
                "id", "source_l2_id", "title", "archived_at",
                "reason", "original_score", "original_ttl_days",
            ):
                assert field in obj

    def test_explicit_expiry_reason_in_entry(self, explicit_expired_item):
        archived, _ = archive_expired_items([explicit_expired_item], today=TODAY)
        assert archived[0].reason == "explicit_expiry"

    def test_returns_tuple(self, healthy_item):
        result = archive_expired_items([healthy_item], today=TODAY)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_archive_creates_parent_dirs(self, tmp_path, low_score_item):
        nested = tmp_path / "deep" / "nested" / "archive.jsonl"
        archive_expired_items([low_score_item], archive_path=nested, today=TODAY)
        assert nested.exists()
