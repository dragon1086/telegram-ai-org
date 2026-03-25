"""HealthReportParser 단위 테스트.

커버리지:
  - parse(dataclass) — CodeHealthReport dataclass 파싱
  - parse(dict)       — JSON-deserialized dict 파싱
  - parse_text()      — 텍스트(Telegram 메시지) 파싱
  - 트리거 기준: critical_kb=150, repeat_threshold=3
  - ok 항목 필터링
  - 우선순위 정렬 (critical > warn)
  - 반복 에러 미달(2회) 항목 무시
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.health_report_parser import HealthReportParser, ImprovementItem

# ------------------------------------------------------------------
# 테스트용 가짜 CodeHealthReport
# ------------------------------------------------------------------

@dataclass
class FakeFileEntry:
    path: str
    size_kb: float
    status: str
    note: str = ""


@dataclass
class FakeCodeHealthReport:
    file_entries: list
    top_error_categories: list
    total_files: int = 0
    warn_count: int = 0
    critical_count: int = 0
    scanned_at: str = "2026-03-22T00:00:00+00:00"


# ------------------------------------------------------------------
# fixtures
# ------------------------------------------------------------------

@pytest.fixture
def parser():
    return HealthReportParser()


@pytest.fixture
def sample_report():
    return FakeCodeHealthReport(
        file_entries=[
            FakeFileEntry("core/telegram_relay.py", 205.0, "critical"),
            FakeFileEntry("core/pm_orchestrator.py", 95.0, "warn"),
            FakeFileEntry("core/small_module.py", 10.0, "ok"),
        ],
        top_error_categories=[
            ("approach", 49),
            ("timeout", 3),
            ("rare_error", 2),  # 임계값 미달 → 무시
        ],
        total_files=3,
        warn_count=1,
        critical_count=1,
    )


@pytest.fixture
def sample_telegram_text():
    return """🏥 코드 건강 리포트
스캔: 80개 파일 | ⚠️ 1 | 🔴 1

🔴 크리티컬 파일:
  • core/telegram_relay.py (205KB) — 분리 권장 (>150KB)

📋 반복 에러 패턴:
  • approach: 49회
  • timeout: 3회
  • rare_error: 2회
"""


# ------------------------------------------------------------------
# 1. dataclass 파싱
# ------------------------------------------------------------------

class TestParseDataclass:
    def test_critical_file_detected(self, parser, sample_report):
        items = parser.parse(sample_report)
        critical = [i for i in items if i.severity == "critical"]
        assert len(critical) == 1
        assert critical[0].file_path == "core/telegram_relay.py"
        assert critical[0].issue_type == "file_size_critical"

    def test_warn_file_detected(self, parser, sample_report):
        items = parser.parse(sample_report)
        warn_files = [i for i in items if i.issue_type == "file_size_warn"]
        assert len(warn_files) == 1
        assert warn_files[0].file_path == "core/pm_orchestrator.py"

    def test_ok_file_excluded(self, parser, sample_report):
        items = parser.parse(sample_report)
        paths = [i.file_path for i in items if i.file_path]
        assert "core/small_module.py" not in paths

    def test_error_pattern_above_threshold(self, parser, sample_report):
        items = parser.parse(sample_report)
        error_items = [i for i in items if i.issue_type == "error_pattern"]
        patterns = [i.error_pattern for i in error_items]
        assert "approach" in patterns
        assert "timeout" in patterns

    def test_error_pattern_below_threshold_excluded(self, parser, sample_report):
        items = parser.parse(sample_report)
        error_items = [i for i in items if i.issue_type == "error_pattern"]
        patterns = [i.error_pattern for i in error_items]
        assert "rare_error" not in patterns  # count=2 < threshold=3

    def test_sorted_by_priority_desc(self, parser, sample_report):
        items = parser.parse(sample_report)
        priorities = [i.priority for i in items]
        assert priorities == sorted(priorities, reverse=True)

    def test_critical_has_higher_priority_than_warn(self, parser, sample_report):
        items = parser.parse(sample_report)
        critical = next(i for i in items if i.severity == "critical")
        warn = next(i for i in items if i.issue_type == "file_size_warn")
        assert critical.priority > warn.priority

    def test_item_has_detail_size_kb(self, parser, sample_report):
        items = parser.parse(sample_report)
        critical = next(i for i in items if i.severity == "critical")
        assert critical.detail["size_kb"] == 205.0


# ------------------------------------------------------------------
# 2. dict 파싱
# ------------------------------------------------------------------

class TestParseDict:
    def test_dict_with_list_tuples(self, parser):
        data = {
            "file_entries": [
                {"path": "core/big.py", "size_kb": 200.0, "status": "critical"},
            ],
            "top_error_categories": [["approach", 10]],
        }
        items = parser.parse(data)
        assert any(i.file_path == "core/big.py" for i in items)
        assert any(i.error_pattern == "approach" for i in items)

    def test_dict_with_dict_error_categories(self, parser):
        data = {
            "file_entries": [],
            "top_error_categories": [{"category": "timeout", "count": 5}],
        }
        items = parser.parse(data)
        assert any(i.error_pattern == "timeout" for i in items)

    def test_dict_ok_files_excluded(self, parser):
        data = {
            "file_entries": [
                {"path": "core/tiny.py", "size_kb": 5.0, "status": "ok"},
            ],
            "top_error_categories": [],
        }
        items = parser.parse(data)
        assert items == []

    def test_empty_dict(self, parser):
        items = parser.parse({})
        assert items == []


# ------------------------------------------------------------------
# 3. 텍스트 파싱
# ------------------------------------------------------------------

class TestParseText:
    def test_telegram_text_critical_file(self, parser, sample_telegram_text):
        items = parser.parse_text(sample_telegram_text)
        critical = [i for i in items if i.issue_type == "file_size_critical"]
        assert len(critical) >= 1
        assert any("telegram_relay" in (i.file_path or "") for i in critical)

    def test_telegram_text_error_pattern(self, parser, sample_telegram_text):
        items = parser.parse_text(sample_telegram_text)
        error_items = [i for i in items if i.issue_type == "error_pattern"]
        patterns = [i.error_pattern for i in error_items]
        assert "approach" in patterns
        assert "timeout" in patterns

    def test_telegram_text_below_threshold_excluded(self, parser, sample_telegram_text):
        items = parser.parse_text(sample_telegram_text)
        patterns = [i.error_pattern for i in items if i.error_pattern]
        assert "rare_error" not in patterns  # 2회 < threshold=3

    def test_empty_text_returns_empty(self, parser):
        items = parser.parse_text("")
        assert items == []

    def test_text_no_issues_returns_empty(self, parser):
        items = parser.parse_text("모든 파일 정상입니다.")
        assert items == []


# ------------------------------------------------------------------
# 4. parse() 타입 자동 판별
# ------------------------------------------------------------------

class TestParseDispatch:
    def test_string_input_delegates_to_parse_text(self, parser):
        text = "🔴 크리티컬 파일:\n  • core/big.py (200KB) — 분리 권장 (>150KB)"
        items = parser.parse(text)
        assert any(i.file_path and "big.py" in i.file_path for i in items)

    def test_unknown_type_returns_empty(self, parser):
        items = parser.parse(12345)
        assert items == []


# ------------------------------------------------------------------
# 5. ImprovementItem 스키마
# ------------------------------------------------------------------

class TestImprovementItemSchema:
    def test_resolved_default_false(self):
        item = ImprovementItem(
            issue_type="file_size_critical",
            severity="critical",
            priority=8,
            suggested_action="test",
        )
        assert item.resolved is False

    def test_repr_contains_severity(self):
        item = ImprovementItem(
            issue_type="error_pattern",
            severity="warn",
            priority=5,
            suggested_action="test",
            error_pattern="approach",
        )
        assert "warn" in repr(item)
        assert "approach" in repr(item)
