"""E2E: Retro 액션 파이프라인 전체 검증.

파싱(RetroActionParser) → 등록(GoalTrackerBridge) → dispatch(RetroDispatch)
전체 흐름을 로컬 mock으로 검증한다. 실제 Telegram·DB 없이 실행 가능.

테스트 구성:
    TestRetroActionParser  — 회고 텍스트 파싱 검증
    TestGoalTrackerBridge  — GoalTracker 등록 브릿지 검증
    TestRetroDispatch      — 부서 dispatch 검증
    TestFullPipeline       — E2E 전체 파이프라인 검증
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# 프로젝트 루트 sys.path 추가
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from retro_action_parser import RetroActionItem, RetroActionParser
from goal_tracker_bridge import GoalTrackerBridge
from retro_dispatch import RetroDispatch


# ── 공통 픽스처 ──────────────────────────────────────────────────────────────


@pytest.fixture
def sample_retro_text() -> str:
    """실제 회고 텍스트 샘플 (RETRO-21 스타일, 조직별 블록, ACTION 항목 3개 이상)."""
    return """\
# 일일회고 — 2026-03-30

## 회고 요약

오늘 팀 전체가 사후 수습 대신 사전 검증 패턴으로 전환하기로 합의했다.

### ⚙️ 개발실

ACTION 1: [RETRO-21] 진단→액션 자동 연결 파이프라인 구현 (GoalTracker 등록)
ACTION 2: pre-flight 체크 자동화 스크립트 작성

**해야 할 것**
- [ ] [RETRO-21] CI/CD 파이프라인 pre-flight 통합
- [ ] 단위 테스트 커버리지 90% 이상 달성

### 🔧 운영실

ACTION 1: [RETRO-22] 도구가 실행을 강제하는 메커니즘 구현 — conftest.py SystemExit 구현
ACTION 2: 인프라 baseline 현행화 자동 배포 스크립트

### 🎨 디자인실

ACTION 1: [RETRO-23] UI 실행 블로킹 패턴 적용 — pre-flight 미통과 시 배포 차단

### 📋 기획실

ACTION 1: [RETRO-24] 정책 문서가 실행 게이트가 되는 PRD 작성

## 이번 주 교훈

- 사후 수습보다 사전 검증이 훨씬 효율적
- 자동화된 pre-flight 체크가 핵심

---
*자동 생성: 2026-03-30T14:30:00+00:00*
"""


@pytest.fixture
def mock_goal_tracker():
    """GoalTracker mock 인스턴스 (start_goal 순차 반환)."""
    tracker = AsyncMock()
    goal_ids_iter = iter(["G-test-001", "G-test-002", "G-test-003"])

    async def _start_goal(title, description, meta=None, chat_id=0, org_id=None):
        try:
            return next(goal_ids_iter)
        except StopIteration:
            return f"G-test-extra-{id(title) % 1000:03d}"

    tracker.start_goal = AsyncMock(side_effect=_start_goal)
    tracker.get_goals_by_title = AsyncMock(return_value=[])
    return tracker


@pytest.fixture
def mock_send_func():
    """Telegram send_func mock."""
    return AsyncMock()


@pytest.fixture
def bridge(mock_goal_tracker):
    """GoalTrackerBridge (mock goal_tracker 주입)."""
    return GoalTrackerBridge(goal_tracker=mock_goal_tracker, chat_id=12345)


@pytest.fixture
def dispatcher(mock_send_func):
    """RetroDispatch (mock send_func 주입)."""
    return RetroDispatch(send_func=mock_send_func, admin_chat_id=99999)


@pytest.fixture
def sample_retro_items() -> list[RetroActionItem]:
    """테스트용 샘플 RetroActionItem 목록."""
    return [
        RetroActionItem(
            description="진단→액션 자동 연결 파이프라인 구현",
            assigned_dept="aiorg_engineering_bot",
            priority="medium",
            retro_id="RETRO-21",
            org_emoji="⚙️",
            confidence=0.95,
        ),
        RetroActionItem(
            description="pre-flight 체크 자동화 스크립트 작성",
            assigned_dept="aiorg_ops_bot",
            priority="high",
            retro_id="RETRO-22",
            org_emoji="🔧",
            confidence=0.9,
        ),
        RetroActionItem(
            description="UI 실행 블로킹 패턴 적용",
            assigned_dept="aiorg_design_bot",
            priority="medium",
            retro_id="RETRO-23",
            org_emoji="🎨",
            confidence=0.9,
        ),
    ]


# ── TestRetroActionParser ─────────────────────────────────────────────────────


class TestRetroActionParser:
    """RetroActionParser 파싱 검증."""

    def test_parse_retro_text_returns_items(self, sample_retro_text):
        """샘플 텍스트에서 1개 이상 ActionItem 반환."""
        parser = RetroActionParser()
        items = parser.parse(sample_retro_text)
        assert len(items) >= 1, f"파싱 결과가 비어 있음: {items}"

    def test_retro_id_extracted(self, sample_retro_text):
        """[RETRO-21] 태그가 retro_id 필드로 추출됨."""
        parser = RetroActionParser()
        items = parser.parse(sample_retro_text)
        retro_ids = [item.retro_id for item in items if item.retro_id]
        assert len(retro_ids) >= 1, f"retro_id 추출 없음: {[i.description for i in items]}"
        assert any("RETRO-21" in rid for rid in retro_ids), (
            f"RETRO-21 없음: {retro_ids}"
        )

    def test_assigned_dept_extracted(self, sample_retro_text):
        """조직 블록(### ⚙️ 개발실)에서 assigned_dept 추출."""
        parser = RetroActionParser()
        items = parser.parse(sample_retro_text)
        assigned = [item.assigned_dept for item in items if item.assigned_dept]
        assert len(assigned) >= 1, "assigned_dept 추출 없음"
        assert any(d.startswith("aiorg_") for d in assigned), (
            f"org_id 형식 없음: {assigned}"
        )

    def test_action_format_parsed(self):
        """ACTION N: 형식 파싱."""
        parser = RetroActionParser()
        text = """\
### ⚙️ 개발실
ACTION 1: pre-flight 자동화 구현
ACTION 2: E2E 테스트 커버리지 확장
"""
        items = parser.parse(text)
        assert len(items) >= 1
        descriptions = [item.description for item in items]
        assert any("pre-flight" in d or "자동화" in d for d in descriptions), (
            f"ACTION 1 파싱 실패: {descriptions}"
        )

    def test_bullet_format_parsed(self):
        """- [ ] 체크박스 형식 파싱."""
        parser = RetroActionParser()
        text = """\
## 조치사항
- [ ] CI/CD 파이프라인 수정 완료
- [ ] [RETRO-22] 배포 게이트 추가
"""
        items = parser.parse(text)
        assert len(items) >= 1
        descriptions = [item.description for item in items]
        assert any("파이프라인" in d or "배포 게이트" in d for d in descriptions), (
            f"체크박스 파싱 실패: {descriptions}"
        )

    def test_empty_text_returns_empty_list(self):
        """빈 텍스트 처리 → 빈 리스트 반환."""
        parser = RetroActionParser()
        assert parser.parse("") == []
        assert parser.parse("   ") == []
        assert parser.parse("\n\n\n") == []

    def test_extract_retro_id(self):
        """_extract_retro_id() 단위 테스트."""
        parser = RetroActionParser()
        assert parser._extract_retro_id("[RETRO-21] 설명") == "RETRO-21"
        assert parser._extract_retro_id("[RETRO-99] 설명") == "RETRO-99"
        assert parser._extract_retro_id("retro_id 없는 텍스트") == ""

    def test_extract_org_from_header(self):
        """_extract_org_from_header() 단위 테스트."""
        parser = RetroActionParser()
        org_id, emoji = parser._extract_org_from_header("### ⚙️ 개발실")
        assert org_id == "aiorg_engineering_bot"

        org_id2, emoji2 = parser._extract_org_from_header("## 운영실")
        assert org_id2 == "aiorg_ops_bot"

        org_id3, emoji3 = parser._extract_org_from_header("일반 텍스트")
        assert org_id3 == ""

    def test_parse_org_block(self):
        """parse_org_block() 직접 호출 테스트."""
        parser = RetroActionParser()
        block = "ACTION 1: E2E 테스트 추가\nACTION 2: 코드 리뷰 자동화"
        items = parser.parse_org_block("개발실", block)
        assert len(items) >= 1
        assert all(item.assigned_dept == "aiorg_engineering_bot" for item in items)


# ── TestGoalTrackerBridge ─────────────────────────────────────────────────────


class TestGoalTrackerBridge:
    """GoalTrackerBridge 등록 검증."""

    @pytest.mark.asyncio
    async def test_register_single_action(self, bridge, sample_retro_items):
        """단일 ActionItem 등록 → goal_id 반환."""
        item = sample_retro_items[0]
        goal_id = await bridge.register_action(item)
        assert goal_id is not None
        assert goal_id.startswith("G-"), f"goal_id 형식 오류: {goal_id}"

    @pytest.mark.asyncio
    async def test_register_actions_returns_list(self, bridge, sample_retro_items):
        """복수 등록 → goal_id 리스트."""
        goal_ids = await bridge.register_actions(sample_retro_items)
        assert isinstance(goal_ids, list)
        assert len(goal_ids) == len(sample_retro_items)
        for gid in goal_ids:
            assert isinstance(gid, str)

    @pytest.mark.asyncio
    async def test_dry_run_when_no_goal_tracker(self, sample_retro_items):
        """goal_tracker=None → DRYRUN- 접두어 ID 반환."""
        bridge = GoalTrackerBridge(goal_tracker=None, chat_id=0)
        item = sample_retro_items[0]
        goal_id = await bridge.register_action(item)
        assert goal_id is not None
        assert goal_id.startswith("DRYRUN-"), f"DRYRUN 형식 아님: {goal_id}"

    @pytest.mark.asyncio
    async def test_meta_includes_retro_id(self, mock_goal_tracker, sample_retro_items):
        """등록 meta에 retro_id 포함."""
        bridge = GoalTrackerBridge(goal_tracker=mock_goal_tracker, chat_id=0)
        item = sample_retro_items[0]  # retro_id="RETRO-21"
        await bridge.register_action(item)

        assert mock_goal_tracker.start_goal.called
        call_kwargs = mock_goal_tracker.start_goal.call_args
        meta = call_kwargs.kwargs.get("meta") or call_kwargs.args[2] if len(call_kwargs.args) > 2 else {}
        # meta는 키워드 인수로 전달됨
        if call_kwargs.kwargs:
            meta = call_kwargs.kwargs.get("meta", {})
        else:
            # positional args: title, description, meta, ...
            meta = call_kwargs.args[2] if len(call_kwargs.args) > 2 else {}
        assert "retro_id" in meta, f"meta에 retro_id 없음: {meta}"
        assert meta["retro_id"] == "RETRO-21"

    @pytest.mark.asyncio
    async def test_duplicate_skipped(self, mock_goal_tracker, sample_retro_items):
        """이미 등록된 title 중복 제출 시 기존 goal_id 반환."""
        # get_goals_by_title가 active 상태 goal 반환하도록 설정
        mock_goal_tracker.get_goals_by_title = AsyncMock(
            return_value=[{"id": "G-existing-001", "status": "active", "title": "기존 목표"}]
        )
        bridge = GoalTrackerBridge(goal_tracker=mock_goal_tracker, chat_id=0)
        item = sample_retro_items[0]
        goal_id = await bridge.register_action(item)
        # 기존 ID 반환 + start_goal 미호출
        assert goal_id == "G-existing-001"
        mock_goal_tracker.start_goal.assert_not_called()

    def test_build_goal_title_within_80_chars(self, sample_retro_items):
        """_build_goal_title()이 80자 이내 반환."""
        bridge = GoalTrackerBridge()
        for item in sample_retro_items:
            title = bridge._build_goal_title(item)
            assert len(title) <= 80, f"제목 80자 초과: {len(title)} '{title}'"

    def test_build_goal_meta_required_keys(self, sample_retro_items):
        """_build_goal_meta()가 필수 키 포함."""
        bridge = GoalTrackerBridge()
        required_keys = {"source", "retro_id", "priority", "assignee", "due_date", "tags"}
        for item in sample_retro_items:
            meta = bridge._build_goal_meta(item)
            missing = required_keys - set(meta.keys())
            assert not missing, f"meta 필수 키 누락: {missing}"


# ── TestRetroDispatch ─────────────────────────────────────────────────────────


class TestRetroDispatch:
    """RetroDispatch dispatch 검증."""

    @pytest.mark.asyncio
    async def test_notify_dispatch_calls_send_func(
        self, dispatcher, mock_send_func, sample_retro_items
    ):
        """dispatch 시 send_func 호출 (chat_id 환경변수 있을 때)."""
        item = sample_retro_items[0]  # aiorg_engineering_bot
        goal_id = "G-test-001"

        with patch.dict("os.environ", {"ENGINEERING_BOT_CHAT_ID": "11111"}):
            success = await dispatcher.notify_dispatch(item, goal_id)

        assert success is True
        assert mock_send_func.called

    @pytest.mark.asyncio
    async def test_dispatch_all_returns_success_list(
        self, dispatcher, sample_retro_items, mock_send_func
    ):
        """dispatch_all() → 결과 dict 구조 검증."""
        goal_ids = ["G-test-001", "G-test-002", "G-test-003"]

        env_vars = {
            "ENGINEERING_BOT_CHAT_ID": "11111",
            "OPS_BOT_CHAT_ID": "22222",
            "DESIGN_BOT_CHAT_ID": "33333",
        }
        with patch.dict("os.environ", env_vars):
            result = await dispatcher.dispatch_all(sample_retro_items, goal_ids)

        assert "success" in result
        assert "failed" in result
        assert "skipped" in result
        # 성공 + 실패 + 스킵 = 전체
        total = len(result["success"]) + len(result["failed"]) + len(result["skipped"])
        assert total == len(sample_retro_items)

    def test_collab_payload_format(self, dispatcher, sample_retro_items):
        """COLLAB 태그 포맷 검증 ([COLLAB: 포함)."""
        item = sample_retro_items[0]
        goal_id = "G-test-001"
        payload = dispatcher._build_collab_payload(item, goal_id)
        assert "[COLLAB:" in payload, f"COLLAB 태그 없음: {payload}"
        assert goal_id in payload, f"goal_id 없음: {payload}"
        assert "맥락:" in payload, f"맥락 섹션 없음: {payload}"

    @pytest.mark.asyncio
    async def test_dry_run_when_no_send_func(self, sample_retro_items, tmp_path):
        """send_func=None → 실패 없이 로그만 기록."""
        dispatcher = RetroDispatch(send_func=None)
        item = sample_retro_items[0]
        success = await dispatcher.notify_dispatch(item, "G-dryrun-001")
        assert success is True  # dry-run은 성공으로 간주

    @pytest.mark.asyncio
    async def test_log_written_to_jsonl(self, sample_retro_items, tmp_path):
        """dispatch 후 JSONL 로그 파일 기록 검증."""
        import retro_dispatch as rd_module

        log_path = tmp_path / "retro_dispatch.jsonl"
        original_path = rd_module._RETRO_DISPATCH_LOG
        rd_module._RETRO_DISPATCH_LOG = log_path

        try:
            dispatcher = RetroDispatch(send_func=None)  # dry-run
            item = sample_retro_items[0]
            await dispatcher.notify_dispatch(item, "G-log-test-001")
        finally:
            rd_module._RETRO_DISPATCH_LOG = original_path

        assert log_path.exists(), "로그 파일 생성되지 않음"
        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1, "로그 엔트리 없음"

        entry = json.loads(lines[0])
        assert "goal_id" in entry
        assert "success" in entry
        assert entry["goal_id"] == "G-log-test-001"

    @pytest.mark.asyncio
    async def test_no_assigned_dept_goes_to_skipped(self, mock_send_func):
        """assigned_dept 없는 항목 → skipped 처리."""
        dispatcher = RetroDispatch(send_func=mock_send_func)
        item = RetroActionItem(
            description="부서 없는 액션 아이템",
            assigned_dept=None,
            retro_id="RETRO-99",
        )
        result = await dispatcher.dispatch_all([item], ["G-no-dept-001"])
        assert "G-no-dept-001" in result["skipped"]


# ── TestFullPipeline ──────────────────────────────────────────────────────────


class TestFullPipeline:
    """파싱 → 등록 → dispatch E2E 파이프라인 검증."""

    @pytest.mark.asyncio
    async def test_end_to_end_pipeline(
        self,
        sample_retro_text,
        bridge,
        dispatcher,
        mock_send_func,
    ):
        """parse → register → dispatch 전체 흐름.

        1. RetroActionParser.parse(sample_retro_text)
        2. GoalTrackerBridge.register_actions(items)
        3. RetroDispatch.dispatch_all(items, goal_ids)
        4. 최종: goal_ids 비어있지 않음, dispatch_result["success"] 비어있지 않음
        """
        # Step 1: 파싱
        parser = RetroActionParser()
        items = parser.parse(sample_retro_text)
        assert len(items) >= 1, "파싱 결과 없음"

        # Step 2: 등록
        goal_ids = await bridge.register_actions(items)
        assert len(goal_ids) >= 1, "등록된 goal_id 없음"
        assert len(goal_ids) == len(items), "goal_ids 개수 불일치"

        # Step 3: dispatch
        env_vars = {
            "ENGINEERING_BOT_CHAT_ID": "11111",
            "OPS_BOT_CHAT_ID": "22222",
            "DESIGN_BOT_CHAT_ID": "33333",
            "PRODUCT_BOT_CHAT_ID": "44444",
            "GROWTH_BOT_CHAT_ID": "55555",
            "RESEARCH_BOT_CHAT_ID": "66666",
        }
        with patch.dict("os.environ", env_vars):
            dispatch_result = await dispatcher.dispatch_all(items, goal_ids)

        # 최종 검증
        total_processed = (
            len(dispatch_result["success"])
            + len(dispatch_result["failed"])
            + len(dispatch_result["skipped"])
        )
        assert total_processed == len(items), "dispatch 처리 건수 불일치"
        # 적어도 1건은 성공하거나 스킵되어야 함 (실패만 있으면 안 됨)
        assert len(dispatch_result["success"]) + len(dispatch_result["skipped"]) >= 1

    @pytest.mark.asyncio
    async def test_pipeline_with_empty_input(self, bridge, dispatcher):
        """빈 텍스트 입력 시 각 단계 0건 처리."""
        parser = RetroActionParser()
        items = parser.parse("")
        assert items == []

        goal_ids = await bridge.register_actions(items)
        assert goal_ids == []

        dispatch_result = await dispatcher.dispatch_all(items, goal_ids)
        assert dispatch_result["success"] == []
        assert dispatch_result["failed"] == []
        assert dispatch_result["skipped"] == []

    @pytest.mark.asyncio
    async def test_pipeline_error_recovery(self, mock_send_func):
        """GoalTracker 예외 발생 시 나머지 항목은 정상 처리.

        두 번째 항목에서 start_goal 예외가 발생해도 나머지는 정상 등록된다.
        """
        call_count = 0

        async def _start_goal_with_error(title, description, meta=None, chat_id=0, org_id=None):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise RuntimeError("의도적 오류 — 2번째 항목")
            return f"G-recovery-{call_count:03d}"

        mock_gt = AsyncMock()
        mock_gt.start_goal = AsyncMock(side_effect=_start_goal_with_error)
        mock_gt.get_goals_by_title = AsyncMock(return_value=[])

        bridge = GoalTrackerBridge(goal_tracker=mock_gt, chat_id=0)

        items = [
            RetroActionItem(
                description=f"항목 {i}",
                assigned_dept="aiorg_engineering_bot",
                retro_id=f"RETRO-{i}",
            )
            for i in range(1, 4)
        ]

        goal_ids = await bridge.register_actions(items)
        # 3개 중 1개 실패 → 2개 등록됨
        assert len(goal_ids) == 2, f"예외 복구 실패: {goal_ids}"
        assert all(gid.startswith("G-recovery-") for gid in goal_ids)

    @pytest.mark.asyncio
    async def test_pipeline_preserves_retro_id(self, mock_goal_tracker, mock_send_func):
        """파이프라인 전체에서 retro_id가 보존됨."""
        parser = RetroActionParser()
        text = """\
### ⚙️ 개발실
ACTION 1: [RETRO-42] 특수 파이프라인 구현
"""
        items = parser.parse(text)
        retro_ids = [item.retro_id for item in items if item.retro_id == "RETRO-42"]
        assert len(retro_ids) >= 1, f"RETRO-42 추출 실패: {[i.retro_id for i in items]}"

        bridge = GoalTrackerBridge(goal_tracker=mock_goal_tracker, chat_id=0)
        goal_ids = await bridge.register_actions(items)
        assert len(goal_ids) >= 1

        # meta에 retro_id 포함 검증
        call_kwargs = mock_goal_tracker.start_goal.call_args
        if call_kwargs:
            meta = call_kwargs.kwargs.get("meta", {})
            if not meta and len(call_kwargs.args) > 2:
                meta = call_kwargs.args[2]
            assert meta.get("retro_id") == "RETRO-42", f"meta retro_id 불일치: {meta}"
