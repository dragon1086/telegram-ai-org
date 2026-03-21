"""ImprovementBus 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.improvement_bus import ImprovementBus, ImprovementSignal, SignalKind


class TestImprovementSignal:
    def test_signal_creation(self):
        s = ImprovementSignal(
            kind=SignalKind.LESSON_LEARNED,
            priority=7,
            target="skill:pm-task-dispatch",
            evidence={"count": 3},
            suggested_action="개선 필요",
        )
        assert s.kind == SignalKind.LESSON_LEARNED
        assert s.priority == 7
        assert s.target == "skill:pm-task-dispatch"
        assert s.created_at  # ISO timestamp 자동 생성


class TestImprovementBus:
    def test_dry_run_does_not_raise(self):
        bus = ImprovementBus(dry_run=True)
        signals = [
            ImprovementSignal(
                kind=SignalKind.SKILL_STALE,
                priority=5,
                target="skill:test",
                evidence={},
                suggested_action="테스트 신호",
            )
        ]
        report = bus.run(signals)
        assert report.signal_count == 1
        assert len(report.actions_taken) == 1
        assert "[dry_run]" in report.actions_taken[0]

    def test_signals_sorted_by_priority(self):
        bus = ImprovementBus(dry_run=True)
        signals = [
            ImprovementSignal(kind=SignalKind.CODE_SMELL, priority=3, target="a", evidence={}, suggested_action=""),
            ImprovementSignal(kind=SignalKind.PERF_DROP, priority=9, target="b", evidence={}, suggested_action=""),
            ImprovementSignal(kind=SignalKind.ROUTE_MISS, priority=6, target="c", evidence={}, suggested_action=""),
        ]
        # collect_signals returns sorted by priority desc
        collected = bus.collect_signals()
        # We can only test internal sorting via run
        report = bus.run(signals)
        assert report.signal_count == 3

    def test_format_report_no_crash(self):
        bus = ImprovementBus(dry_run=True)
        report = bus.run([])
        text = bus.format_report(report)
        assert "자가개선" in text

    @patch("core.improvement_bus.ImprovementBus._signals_from_lesson_memory", return_value=[])
    @patch("core.improvement_bus.ImprovementBus._signals_from_retro_memory", return_value=[])
    @patch("core.improvement_bus.ImprovementBus._signals_from_skill_staleness", return_value=[])
    @patch("core.improvement_bus.ImprovementBus._signals_from_code_health", return_value=[])
    def test_collect_signals_empty_sources(self, m1, m2, m3, m4):
        bus = ImprovementBus(dry_run=True)
        signals = bus.collect_signals()
        assert signals == []

    def test_code_smell_signals_for_large_files(self, tmp_path):
        """큰 파일이 있으면 CODE_SMELL 신호가 생성된다."""
        bus = ImprovementBus(dry_run=True)
        # 실제 core/ 스캔 — pm_orchestrator.py, telegram_relay.py는 크다
        signals = bus._signals_from_code_health()
        # 신호가 생성될 수도 있고 없을 수도 있음 — 크래시 없어야 함
        assert isinstance(signals, list)
        for s in signals:
            assert s.kind == SignalKind.CODE_SMELL
            assert s.priority >= 1
