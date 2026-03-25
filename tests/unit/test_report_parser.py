"""report_parser + auto_register 단위 테스트.

검증 범위:
    1. parse_action_items() — daily_retro 포맷 파싱
    2. parse_action_items() — weekly_meeting 포맷 파싱
    3. parse_report_metadata() — 날짜·참석자·제목 추출
    4. auto_register_from_report() — GoalTracker 없는 파싱 전용 경로
    5. auto_register_from_report() — 상태머신 트리거
    6. 엣지 케이스: 빈 텍스트, 조치사항 없음
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from goal_tracker.action_parser import ActionItem
from goal_tracker.report_parser import (
    parse_action_items,
    parse_report_metadata,
    _normalize_report_type,
)
from goal_tracker.meeting_handler import MeetingType
from goal_tracker.auto_register import (
    auto_register_from_report,
    AutoRegisterResult,
    _inject_to_state_machine,
)
from goal_tracker.state_machine import GoalTrackerState, GoalTrackerStateMachine


# ── 픽스처: 샘플 보고 텍스트 ─────────────────────────────────────────────────

DAILY_RETRO_SAMPLE = """
# 일일회고 2026-03-25

## 오늘 한 일
- API 엔드포인트 구현 완료
- 코드 리뷰 2건 처리

## 이슈/블로커
- DB 연결 타임아웃 문제 발견

## 내일 할 일
- [ ] DB 타임아웃 원인 분석 담당자: 개발실
- [ ] 성능 테스트 수행 담당자: 운영실
- [ ] 팀장 보고서 작성

## 조치사항:
- DB 연결 풀 설정 검토 → aiorg_ops_bot
- 모니터링 알림 임계값 조정
"""

WEEKLY_MEETING_SAMPLE = """
# 주간회의 2026-03-25

참석: 개발실, 기획실, 운영실

## 주간 목표 달성 현황
- GoalTracker v1.0 구현: 80% 완료
- 테스트 커버리지: 75%

## 다음 주 계획
- [ ] 상태머신 단위 테스트 작성 담당자: 개발실
- [ ] PRD 업데이트 완료
- [ ] 배포 파이프라인 구성 담당자: 운영실

## 결정 사항:
- 릴리스 날짜: 2026-03-31
- 개발실: state_machine.py 리팩토링 완료
- 기획실: 사용자 스토리 추가 작성
- 운영실: Docker 이미지 빌드 자동화

## 액션아이템:
- 긴급 보안 패치 적용 → aiorg_ops_bot 마감: 2026-03-27
- API 문서 업데이트
"""

EMPTY_TEXT = ""

NO_ACTION_TEXT = """
# 주간 공지

이번 주는 특별한 사항이 없습니다.
다음 주도 잘 부탁드립니다.
"""


# ════════════════════════════════════════════════════════════════════════════
# 1. _normalize_report_type()
# ════════════════════════════════════════════════════════════════════════════

class TestNormalizeReportType:
    def test_daily_retro_variants(self):
        for rt in ["daily_retro", "daily-retro", "DAILY_RETRO", "daily", "일일회고", "데일리"]:
            assert _normalize_report_type(rt) == MeetingType.DAILY_RETRO, rt

    def test_weekly_meeting_variants(self):
        for rt in ["weekly_meeting", "weekly-meeting", "WEEKLY", "주간회의", "주간"]:
            assert _normalize_report_type(rt) == MeetingType.WEEKLY_MEETING, rt

    def test_unknown_type(self):
        assert _normalize_report_type("unknown") == MeetingType.UNKNOWN
        assert _normalize_report_type("") == MeetingType.UNKNOWN


# ════════════════════════════════════════════════════════════════════════════
# 2. parse_action_items() — daily_retro
# ════════════════════════════════════════════════════════════════════════════

class TestParseActionItemsDailyRetro:
    def test_returns_list(self):
        items = parse_action_items(DAILY_RETRO_SAMPLE, "daily_retro")
        assert isinstance(items, list)

    def test_extracts_at_least_one_item(self):
        items = parse_action_items(DAILY_RETRO_SAMPLE, "daily_retro")
        assert len(items) >= 1

    def test_items_are_action_item_instances(self):
        items = parse_action_items(DAILY_RETRO_SAMPLE, "daily_retro")
        for item in items:
            assert isinstance(item, ActionItem)

    def test_descriptions_not_empty(self):
        items = parse_action_items(DAILY_RETRO_SAMPLE, "daily_retro")
        for item in items:
            assert item.description.strip() != ""

    def test_db_timeout_item_found(self):
        items = parse_action_items(DAILY_RETRO_SAMPLE, "daily_retro")
        descriptions = [i.description.lower() for i in items]
        assert any("db" in d or "타임아웃" in d or "연결" in d for d in descriptions)

    def test_ops_assignee_extracted(self):
        items = parse_action_items(DAILY_RETRO_SAMPLE, "daily_retro")
        assignees = [i.assigned_dept for i in items if i.assigned_dept]
        assert any("ops" in (a or "") for a in assignees)

    def test_sorted_by_confidence_desc(self):
        items = parse_action_items(DAILY_RETRO_SAMPLE, "daily_retro")
        confidences = [i.confidence for i in items]
        assert confidences == sorted(confidences, reverse=True)

    def test_empty_text_returns_empty(self):
        items = parse_action_items(EMPTY_TEXT, "daily_retro")
        assert items == []

    def test_no_duplicates(self):
        items = parse_action_items(DAILY_RETRO_SAMPLE, "daily_retro")
        descriptions = [i.description.strip().lower() for i in items]
        assert len(descriptions) == len(set(descriptions))

    def test_min_confidence_filter(self):
        all_items = parse_action_items(DAILY_RETRO_SAMPLE, "daily_retro")
        high_conf_items = parse_action_items(
            DAILY_RETRO_SAMPLE, "daily_retro", min_confidence=0.9
        )
        assert all(i.confidence >= 0.9 for i in high_conf_items)
        assert len(high_conf_items) <= len(all_items)


# ════════════════════════════════════════════════════════════════════════════
# 3. parse_action_items() — weekly_meeting
# ════════════════════════════════════════════════════════════════════════════

class TestParseActionItemsWeeklyMeeting:
    def test_returns_list(self):
        items = parse_action_items(WEEKLY_MEETING_SAMPLE, "weekly_meeting")
        assert isinstance(items, list)

    def test_extracts_multiple_items(self):
        items = parse_action_items(WEEKLY_MEETING_SAMPLE, "weekly_meeting")
        assert len(items) >= 2

    def test_urgent_item_has_high_priority(self):
        items = parse_action_items(WEEKLY_MEETING_SAMPLE, "weekly_meeting")
        # "긴급 보안 패치" 항목이 high priority로 파싱되어야 함
        high_priority = [i for i in items if i.priority == "high"]
        assert len(high_priority) >= 1

    def test_due_date_extracted(self):
        items = parse_action_items(WEEKLY_MEETING_SAMPLE, "weekly_meeting")
        dated = [i for i in items if i.due_date]
        assert len(dated) >= 1
        # 2026-03-27 형식이어야 함
        for item in dated:
            assert "-" in item.due_date

    def test_assignee_mapping_ops(self):
        """'운영실' → 'aiorg_ops_bot' 매핑 확인."""
        items = parse_action_items(WEEKLY_MEETING_SAMPLE, "weekly_meeting")
        ops_tasks = [i for i in items if i.assigned_dept == "aiorg_ops_bot"]
        assert len(ops_tasks) >= 1

    def test_no_duplicates_weekly(self):
        items = parse_action_items(WEEKLY_MEETING_SAMPLE, "weekly_meeting")
        descriptions = [i.description.strip().lower() for i in items]
        assert len(descriptions) == len(set(descriptions))

    def test_no_action_text_returns_few_or_no_items(self):
        items = parse_action_items(NO_ACTION_TEXT, "weekly_meeting")
        # 조치사항 없는 텍스트 → 아이템 없거나 최소화
        assert len(items) <= 3


# ════════════════════════════════════════════════════════════════════════════
# 4. parse_report_metadata()
# ════════════════════════════════════════════════════════════════════════════

class TestParseReportMetadata:
    def test_returns_dict(self):
        meta = parse_report_metadata(DAILY_RETRO_SAMPLE, "daily_retro")
        assert isinstance(meta, dict)

    def test_meeting_type_field(self):
        meta = parse_report_metadata(DAILY_RETRO_SAMPLE, "daily_retro")
        assert meta["meeting_type"] == "daily_retro"

    def test_date_extracted(self):
        meta = parse_report_metadata(DAILY_RETRO_SAMPLE, "daily_retro")
        assert meta["date"] == "2026-03-25"

    def test_date_extracted_weekly(self):
        meta = parse_report_metadata(WEEKLY_MEETING_SAMPLE, "weekly_meeting")
        assert meta["date"] == "2026-03-25"

    def test_participants_extracted(self):
        meta = parse_report_metadata(WEEKLY_MEETING_SAMPLE, "weekly_meeting")
        assert isinstance(meta["participants"], list)
        # 개발실, 기획실, 운영실 파싱 확인
        assert len(meta["participants"]) >= 1

    def test_title_extracted(self):
        meta = parse_report_metadata(DAILY_RETRO_SAMPLE, "daily_retro")
        assert meta["title"] != ""
        assert "일일회고" in meta["title"] or "2026" in meta["title"]

    def test_required_keys_present(self):
        meta = parse_report_metadata(DAILY_RETRO_SAMPLE, "daily_retro")
        for key in ["report_type", "meeting_type", "date", "participants", "title"]:
            assert key in meta, f"키 누락: {key}"

    def test_empty_text_returns_meta_with_defaults(self):
        meta = parse_report_metadata("", "daily_retro")
        assert meta["date"] is None
        assert meta["participants"] == []


# ════════════════════════════════════════════════════════════════════════════
# 5. auto_register_from_report() — 파싱 전용 경로
# ════════════════════════════════════════════════════════════════════════════

class TestAutoRegisterNoTracker:
    def test_returns_auto_register_result(self):
        result = asyncio.run(
            auto_register_from_report(DAILY_RETRO_SAMPLE, "daily_retro")
        )
        assert isinstance(result, AutoRegisterResult)

    def test_action_items_found_count(self):
        result = asyncio.run(
            auto_register_from_report(DAILY_RETRO_SAMPLE, "daily_retro")
        )
        assert result.action_items_found >= 1

    def test_no_registered_ids_without_tracker(self):
        result = asyncio.run(
            auto_register_from_report(DAILY_RETRO_SAMPLE, "daily_retro")
        )
        assert result.registered_ids == []
        assert result.registered_count == 0

    def test_empty_text_returns_empty_result(self):
        result = asyncio.run(
            auto_register_from_report(EMPTY_TEXT, "daily_retro")
        )
        assert result.action_items_found == 0
        assert result.registered_count == 0

    def test_result_meeting_type(self):
        result = asyncio.run(
            auto_register_from_report(WEEKLY_MEETING_SAMPLE, "weekly_meeting")
        )
        assert result.meeting_type == "weekly_meeting"

    def test_result_report_type_preserved(self):
        result = asyncio.run(
            auto_register_from_report(DAILY_RETRO_SAMPLE, "daily_retro")
        )
        assert result.report_type == "daily_retro"

    def test_no_errors_on_valid_text(self):
        result = asyncio.run(
            auto_register_from_report(DAILY_RETRO_SAMPLE, "daily_retro")
        )
        assert result.errors == []

    def test_success_property(self):
        result = asyncio.run(
            auto_register_from_report(DAILY_RETRO_SAMPLE, "daily_retro")
        )
        assert result.success is True


# ════════════════════════════════════════════════════════════════════════════
# 6. auto_register_from_report() — 상태머신 트리거
# ════════════════════════════════════════════════════════════════════════════

class TestAutoRegisterWithStateMachine:
    def _make_mock_registrar(self, goal_ids: list[str]):
        """registered_ids를 반환하는 모의 registrar 생성."""
        registrar = MagicMock()
        registrar.register_from_event = AsyncMock(return_value=goal_ids)
        return registrar

    def test_state_machine_triggered_when_idle(self):
        sm = GoalTrackerStateMachine("G-test-002")
        registrar = self._make_mock_registrar(["G-test-002"])

        result = asyncio.run(
            auto_register_from_report(
                DAILY_RETRO_SAMPLE,
                "daily_retro",
                registrar=registrar,
                state_machine=sm,
            )
        )
        assert result.state_machine_triggered is True
        assert sm.state == GoalTrackerState.EVALUATE

    def test_state_machine_not_triggered_when_not_idle(self):
        sm = GoalTrackerStateMachine("G-test-003")
        sm.start_evaluate()  # EVALUATE 상태로 이동
        registrar = self._make_mock_registrar(["G-test-003"])

        result = asyncio.run(
            auto_register_from_report(
                DAILY_RETRO_SAMPLE,
                "daily_retro",
                registrar=registrar,
                state_machine=sm,
            )
        )
        assert result.state_machine_triggered is False
        assert sm.state == GoalTrackerState.EVALUATE  # 변경 없음

    def test_inject_to_state_machine_idle_success(self):
        sm = GoalTrackerStateMachine("G-inject-001")
        result = _inject_to_state_machine(sm, ["T-001", "T-002"])
        assert result is True
        assert sm.state == GoalTrackerState.EVALUATE

    def test_inject_to_state_machine_non_idle_fails(self):
        sm = GoalTrackerStateMachine("G-inject-002")
        sm.start_evaluate()
        result = _inject_to_state_machine(sm, ["T-001"])
        assert result is False
        assert sm.state == GoalTrackerState.EVALUATE

    def test_inject_to_state_machine_empty_tasks(self):
        sm = GoalTrackerStateMachine("G-inject-003")
        # 빈 task_ids여도 상태머신 트리거는 EVALUATE 진입 가능 (start_evaluate 호출)
        result = _inject_to_state_machine(sm, [])
        # 빈 리스트여도 start_evaluate는 성공할 수 있음
        # (task_ids는 sm 트리거와 별개)
        assert isinstance(result, bool)

    def test_registrar_called_with_correct_event(self):
        registrar = self._make_mock_registrar(["G-weekly-001"])
        result = asyncio.run(
            auto_register_from_report(
                WEEKLY_MEETING_SAMPLE,
                "weekly_meeting",
                registrar=registrar,
                chat_id=12345,
            )
        )
        assert registrar.register_from_event.called
        call_args = registrar.register_from_event.call_args[0][0]
        assert call_args.meeting_type == MeetingType.WEEKLY_MEETING
        assert call_args.chat_id == 12345

    def test_registered_ids_populated(self):
        registrar = self._make_mock_registrar(["G-001", "G-002"])
        result = asyncio.run(
            auto_register_from_report(
                DAILY_RETRO_SAMPLE,
                "daily_retro",
                registrar=registrar,
            )
        )
        assert result.registered_ids == ["G-001", "G-002"]
        assert result.registered_count == 2


# ════════════════════════════════════════════════════════════════════════════
# 7. AutoRegisterResult 속성 검증
# ════════════════════════════════════════════════════════════════════════════

class TestAutoRegisterResult:
    def test_success_true_when_no_errors(self):
        r = AutoRegisterResult(
            report_type="daily_retro",
            meeting_type="daily_retro",
            action_items_found=3,
            registered_ids=["G-001"],
        )
        assert r.success is True

    def test_success_false_when_errors(self):
        r = AutoRegisterResult(
            report_type="daily_retro",
            meeting_type="daily_retro",
            action_items_found=0,
            errors=["some error"],
        )
        assert r.success is False

    def test_registered_count_property(self):
        r = AutoRegisterResult(
            report_type="daily_retro",
            meeting_type="daily_retro",
            action_items_found=2,
            registered_ids=["G-001", "G-002", "G-003"],
        )
        assert r.registered_count == 3

    def test_str_representation(self):
        r = AutoRegisterResult(
            report_type="weekly_meeting",
            meeting_type="weekly_meeting",
            action_items_found=5,
        )
        assert "weekly_meeting" in str(r)
        assert "5" in str(r)
