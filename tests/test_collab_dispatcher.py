"""ST-11 CollabDispatcher 단위 테스트.

테스트 케이스:
1. test_dispatch_sends_to_target_dept
   - COLLAB 태스크를 명시된 대상 부서로 정상 전달하는지 검증
2. test_dispatch_skips_source_dept
   - 발신 부서 자신에게는 메시지를 보내지 않는지 검증
3. test_dispatch_from_tag_extracts_and_sends
   - [COLLAB:...] 태그에서 자동 추출 후 dispatch하는지 검증
4. test_dispatch_returns_empty_when_no_chat_id
   - chat_id를 해석할 수 없을 때 빈 리스트 반환하는지 검증
"""
# ruff: noqa: E402,I001
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.collab_dispatcher import CollabDispatcher, parse_collab_tags, resolve_target_depts


# ── 헬퍼 ────────────────────────────────────────────────────────────────────

def _make_dispatcher(chat_id_map: dict[str, int] | None = None) -> tuple[CollabDispatcher, AsyncMock]:
    """테스트용 CollabDispatcher + send_func mock을 반환한다."""
    send_mock = AsyncMock()
    # NOTE: `chat_id_map or {...}` 대신 `is not None` 체크 — 빈 dict {}는 falsy이므로
    _map = chat_id_map if chat_id_map is not None else {
        "aiorg_engineering_bot": 111,
        "aiorg_design_bot":      222,
        "aiorg_ops_bot":         333,
    }
    dispatcher = CollabDispatcher(
        send_func=send_mock,
        chat_id_resolver=lambda dept_id: _map.get(dept_id),
    )
    return dispatcher, send_mock


# ── parse_collab_tags ────────────────────────────────────────────────────────

class TestParseCollabTags:
    def test_single_tag_no_context(self):
        text = "작업 완료. [COLLAB:디자인 검토 요청] 확인 바람."
        tags = parse_collab_tags(text)
        assert len(tags) == 1
        assert tags[0]["task"] == "디자인 검토 요청"
        assert tags[0]["context"] == ""

    def test_single_tag_with_context(self):
        text = "[COLLAB:UI 컴포넌트 설계|맥락: 로그인 화면 개선 작업]"
        tags = parse_collab_tags(text)
        assert len(tags) == 1
        assert tags[0]["task"] == "UI 컴포넌트 설계"
        assert tags[0]["context"] == "로그인 화면 개선 작업"

    def test_multiple_tags(self):
        text = "[COLLAB:디자인 검토|맥락: v2 개편] 그리고 [COLLAB:성장 지표 분석]"
        tags = parse_collab_tags(text)
        assert len(tags) == 2

    def test_no_tags_returns_empty(self):
        assert parse_collab_tags("일반 메시지입니다.") == []


# ── resolve_target_depts ─────────────────────────────────────────────────────

class TestResolveTargetDepts:
    def test_explicit_targets_filtered(self):
        result = resolve_target_depts("텍스트", ["aiorg_design_bot", "unknown_org"])
        assert result == ["aiorg_design_bot"]

    def test_mention_in_text(self):
        result = resolve_target_depts("aiorg_ops_bot 에게 부탁합니다")
        assert "aiorg_ops_bot" in result

    def test_fallback_all_depts(self):
        result = resolve_target_depts("아무 언급 없는 텍스트")
        assert len(result) > 1  # 전체 부서 반환


# ── CollabDispatcher.dispatch ────────────────────────────────────────────────

class TestCollabDispatcherDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_sends_to_target_dept(self):
        """COLLAB 태스크가 명시된 대상 부서로 정상 전달되어야 한다."""
        dispatcher, send_mock = _make_dispatcher()

        result = await dispatcher.dispatch(
            task_id="T-ST11-001",
            task_text="디자인 리뷰 요청",
            source_dept="aiorg_engineering_bot",
            target_depts=["aiorg_design_bot"],
        )

        assert "aiorg_design_bot" in result
        send_mock.assert_awaited_once()
        call_args = send_mock.call_args
        # chat_id 222로 전달됐는지 확인
        assert call_args[0][0] == 222
        # 태스크 ID가 메시지에 포함됐는지 확인
        assert "T-ST11-001" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_dispatch_skips_source_dept(self):
        """발신 부서 자신에게는 메시지를 보내지 않아야 한다."""
        dispatcher, send_mock = _make_dispatcher()

        result = await dispatcher.dispatch(
            task_id="T-ST11-002",
            task_text="자기 자신에게 보내는 경우",
            source_dept="aiorg_engineering_bot",
            # 대상이 자신과 같음
            target_depts=["aiorg_engineering_bot"],
        )

        # 자기 자신은 제외되므로 dispatched 목록이 비어야 함
        assert result == []
        send_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dispatch_returns_empty_when_no_chat_id(self):
        """chat_id 해석 불가 부서는 건너뛰고 빈 리스트를 반환해야 한다."""
        dispatcher, send_mock = _make_dispatcher(chat_id_map={})  # 빈 맵

        result = await dispatcher.dispatch(
            task_id="T-ST11-003",
            task_text="채팅방 없는 부서에 보내기",
            source_dept="aiorg_engineering_bot",
            target_depts=["aiorg_design_bot"],
        )

        assert result == []
        send_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dispatch_from_tag_extracts_and_sends(self):
        """[COLLAB:...] 태그에서 자동 추출해 dispatch해야 한다."""
        dispatcher, send_mock = _make_dispatcher()

        full_text = (
            "작업 완료. "
            "[COLLAB:디자인 시안 검토 요청|맥락: 로그인 화면 v2] "
            "확인 부탁드립니다."
        )

        result = await dispatcher.dispatch_from_tag(
            task_id="T-ST11-004",
            full_text=full_text,
            source_dept="aiorg_engineering_bot",
        )

        # 태그가 있으므로 최소 1개 부서에 전달
        assert len(result) > 0
        send_mock.assert_awaited()

    @pytest.mark.asyncio
    async def test_dispatch_from_tag_no_tag_returns_empty(self):
        """COLLAB 태그 없으면 빈 리스트를 반환해야 한다."""
        dispatcher, send_mock = _make_dispatcher()

        result = await dispatcher.dispatch_from_tag(
            task_id="T-ST11-005",
            full_text="일반 태스크 결과 — COLLAB 태그 없음",
            source_dept="aiorg_engineering_bot",
        )

        assert result == []
        send_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_dispatch_writes_structured_log(self, tmp_path, monkeypatch):
        """성공 dispatch 시 collab_dispatch.jsonl에 구조화 로그가 남아야 한다."""
        import core.collab_dispatcher as collab_module

        log_path = tmp_path / "collab_dispatch.jsonl"
        monkeypatch.setattr(collab_module, "_DISPATCH_LOG_PATH", log_path)

        dispatcher, _ = _make_dispatcher()
        await dispatcher.dispatch(
            task_id="T-ST11-006",
            task_text="운영 검토 요청",
            source_dept="aiorg_engineering_bot",
            target_depts=["aiorg_ops_bot"],
            context="배포 직전",
        )

        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["status"] == "dispatched"
        assert payload["task_id"] == "T-ST11-006"
        assert payload["target_dept"] == "aiorg_ops_bot"
