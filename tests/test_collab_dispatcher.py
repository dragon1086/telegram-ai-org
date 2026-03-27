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

신규 (skipped_no_chat_id 원인 분류/재시도/fallback):
5. test_dispatch_logs_permanent_failure_env_key_missing
   - env_key 매핑 없는 부서 → permanent 실패 로그 기록
6. test_dispatch_logs_permanent_failure_env_var_unset
   - 환경변수 미설정 → permanent 실패 로그 + failure_type 필드 포함
7. test_dispatch_retries_on_transient_failure_then_succeeds
   - 커스텀 resolver가 Exception → 재시도 후 성공 시 dispatched 목록 반환
8. test_dispatch_retries_on_transient_failure_exhausted
   - 재시도 소진 → transient 실패 로그 기록, send 미호출
9. test_dispatch_sends_admin_alert_on_transient_failure
   - admin_chat_id 지정 시 일시적 재시도 소진 후 관리자 알림 전송
10. test_dispatch_no_admin_alert_on_permanent_failure
    - permanent 실패에는 관리자 알림 전송 안 함
11. test_dispatch_metric_status_permanent_vs_transient
    - JSONL 로그에 skipped_no_chat_id_permanent / skipped_no_chat_id_transient 구분 기록
"""
# ruff: noqa: E402,I001
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.collab_dispatcher import CollabDispatcher, parse_collab_tags, resolve_target_depts


# ── 헬퍼 ────────────────────────────────────────────────────────────────────

def _make_dispatcher(
    chat_id_map: dict[str, int] | None = None,
    admin_chat_id: int | None = None,
) -> tuple[CollabDispatcher, AsyncMock]:
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
        admin_chat_id=admin_chat_id,
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
    async def test_dispatch_sends_to_target_dept(self, tmp_path, monkeypatch):
        """COLLAB 태스크가 명시된 대상 부서로 정상 전달되어야 한다."""
        monkeypatch.setattr("core.collab_dispatcher._DISPATCH_LOG_PATH", tmp_path / "collab_dispatch.jsonl")
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
    async def test_dispatch_returns_empty_when_no_chat_id(self, tmp_path, monkeypatch):
        """chat_id 해석 불가 부서는 건너뛰고 빈 리스트를 반환해야 한다."""
        import core.collab_dispatcher as collab_module
        monkeypatch.setattr(collab_module, "_DISPATCH_LOG_PATH", tmp_path / "collab_dispatch.jsonl")

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
    async def test_dispatch_from_tag_extracts_and_sends(self, tmp_path, monkeypatch):
        """[COLLAB:...] 태그에서 자동 추출해 dispatch해야 한다."""
        monkeypatch.setattr("core.collab_dispatcher._DISPATCH_LOG_PATH", tmp_path / "collab_dispatch.jsonl")
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


# ── skipped_no_chat_id 원인 분류 / 재시도 / fallback ─────────────────────────

class TestChatIdFailureHandling:
    """chat_id 조회 실패 처리 — 원인 분류·재시도·fallback 검증."""

    @pytest.mark.asyncio
    async def test_permanent_failure_logs_status_permanent(self, tmp_path, monkeypatch):
        """resolver가 None 반환(영구적 실패) 시 skipped_no_chat_id_permanent 로그가 남아야 한다."""
        import core.collab_dispatcher as collab_module
        log_path = tmp_path / "collab_dispatch.jsonl"
        monkeypatch.setattr(collab_module, "_DISPATCH_LOG_PATH", log_path)

        dispatcher, send_mock = _make_dispatcher(chat_id_map={})  # 모든 부서 None 반환

        await dispatcher.dispatch(
            task_id="T-PERM-001",
            task_text="영구적 실패 테스트",
            source_dept="aiorg_engineering_bot",
            target_depts=["aiorg_design_bot"],
        )

        send_mock.assert_not_awaited()
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["status"] == "skipped_no_chat_id_permanent"
        assert payload["failure_type"] == "permanent"
        assert payload["target_dept"] == "aiorg_design_bot"

    @pytest.mark.asyncio
    async def test_permanent_failure_detail_contains_reason(self, tmp_path, monkeypatch):
        """영구적 실패 로그의 detail 필드에 실패 원인이 포함되어야 한다."""
        import core.collab_dispatcher as collab_module
        log_path = tmp_path / "collab_dispatch.jsonl"
        monkeypatch.setattr(collab_module, "_DISPATCH_LOG_PATH", log_path)

        dispatcher, _ = _make_dispatcher(chat_id_map={})

        await dispatcher.dispatch(
            task_id="T-PERM-002",
            task_text="원인 로그 테스트",
            source_dept="aiorg_engineering_bot",
            target_depts=["aiorg_design_bot"],
        )

        payload = json.loads(log_path.read_text(encoding="utf-8").splitlines()[0])
        # detail에 실패 원인이 포함되어야 함 (비어 있으면 안 됨)
        assert len(payload.get("detail", "")) > 0

    @pytest.mark.asyncio
    async def test_transient_failure_retries_and_succeeds(self, tmp_path, monkeypatch):
        """resolver가 첫 번째 호출에서 Exception, 두 번째에서 성공하면 dispatched에 포함된다."""
        import core.collab_dispatcher as collab_module
        log_path = tmp_path / "collab_dispatch.jsonl"
        monkeypatch.setattr(collab_module, "_DISPATCH_LOG_PATH", log_path)

        call_count = 0

        def flaky_resolver(dept_id: str) -> int | None:
            nonlocal call_count
            call_count += 1
            if dept_id == "aiorg_design_bot" and call_count == 1:
                raise ConnectionError("일시적 네트워크 오류")
            return {"aiorg_design_bot": 222}.get(dept_id)

        send_mock = AsyncMock()
        dispatcher = CollabDispatcher(
            send_func=send_mock,
            chat_id_resolver=flaky_resolver,
        )

        result = await dispatcher.dispatch(
            task_id="T-TRANS-001",
            task_text="일시적 실패 후 재시도 성공 테스트",
            source_dept="aiorg_engineering_bot",
            target_depts=["aiorg_design_bot"],
        )

        assert "aiorg_design_bot" in result
        send_mock.assert_awaited_once()
        # 1차 실패 + 1번 재시도 = 총 2회 호출
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_transient_failure_exhausted_logs_transient(self, tmp_path, monkeypatch):
        """재시도 소진 시 skipped_no_chat_id_transient 로그가 남아야 한다."""
        import core.collab_dispatcher as collab_module
        log_path = tmp_path / "collab_dispatch.jsonl"
        monkeypatch.setattr(collab_module, "_DISPATCH_LOG_PATH", log_path)

        def always_fail(dept_id: str) -> int | None:
            raise TimeoutError("API 타임아웃")

        send_mock = AsyncMock()
        dispatcher = CollabDispatcher(
            send_func=send_mock,
            chat_id_resolver=always_fail,
        )

        result = await dispatcher.dispatch(
            task_id="T-TRANS-002",
            task_text="항상 실패하는 resolver",
            source_dept="aiorg_engineering_bot",
            target_depts=["aiorg_design_bot"],
        )

        assert result == []
        send_mock.assert_not_awaited()

        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        payload = json.loads(lines[0])
        assert payload["status"] == "skipped_no_chat_id_transient"
        assert payload["failure_type"] == "transient"

    @pytest.mark.asyncio
    async def test_admin_alert_sent_on_transient_exhausted(self, tmp_path, monkeypatch):
        """admin_chat_id 지정 + 일시적 실패 소진 시 관리자 채널에 알림이 전송되어야 한다."""
        import core.collab_dispatcher as collab_module
        monkeypatch.setattr(collab_module, "_DISPATCH_LOG_PATH", tmp_path / "collab_dispatch.jsonl")

        def always_fail(dept_id: str) -> int | None:
            raise TimeoutError("연결 타임아웃")

        send_mock = AsyncMock()
        dispatcher = CollabDispatcher(
            send_func=send_mock,
            chat_id_resolver=always_fail,
            admin_chat_id=9999,
        )

        await dispatcher.dispatch(
            task_id="T-ADMIN-001",
            task_text="관리자 알림 테스트",
            source_dept="aiorg_engineering_bot",
            target_depts=["aiorg_design_bot"],
        )

        # send_mock이 관리자 채널(9999)으로 한 번 호출돼야 함
        assert send_mock.await_count == 1
        admin_call = send_mock.call_args
        assert admin_call[0][0] == 9999
        assert "COLLAB_DISPATCH_ALERT" in admin_call[0][1]

    @pytest.mark.asyncio
    async def test_no_admin_alert_on_permanent_failure(self, tmp_path, monkeypatch):
        """영구적 실패 시에는 관리자 알림이 전송되지 않아야 한다."""
        import core.collab_dispatcher as collab_module
        monkeypatch.setattr(collab_module, "_DISPATCH_LOG_PATH", tmp_path / "collab_dispatch.jsonl")

        dispatcher, send_mock = _make_dispatcher(
            chat_id_map={},     # 영구적 실패
            admin_chat_id=9999,
        )

        await dispatcher.dispatch(
            task_id="T-ADMIN-002",
            task_text="영구적 실패 — 관리자 알림 없어야 함",
            source_dept="aiorg_engineering_bot",
            target_depts=["aiorg_design_bot"],
        )

        # 영구적 실패는 관리자 알림 불필요 — send 호출 없어야 함
        send_mock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_metric_status_permanent_vs_transient_separate(self, tmp_path, monkeypatch):
        """영구적·일시적 실패가 혼재할 때 JSONL에 각각 다른 status로 기록되어야 한다."""
        import core.collab_dispatcher as collab_module
        log_path = tmp_path / "collab_dispatch.jsonl"
        monkeypatch.setattr(collab_module, "_DISPATCH_LOG_PATH", log_path)

        call_counts: dict[str, int] = {}

        def mixed_resolver(dept_id: str) -> int | None:
            call_counts[dept_id] = call_counts.get(dept_id, 0) + 1
            if dept_id == "aiorg_design_bot":
                # 영구적 실패: None 반환
                return None
            if dept_id == "aiorg_ops_bot":
                # 일시적 실패: 항상 Exception
                raise ConnectionError("일시적 오류")
            return None

        send_mock = AsyncMock()
        dispatcher = CollabDispatcher(
            send_func=send_mock,
            chat_id_resolver=mixed_resolver,
        )

        await dispatcher.dispatch(
            task_id="T-METRIC-001",
            task_text="메트릭 세분화 테스트",
            source_dept="aiorg_engineering_bot",
            target_depts=["aiorg_design_bot", "aiorg_ops_bot"],
        )

        send_mock.assert_not_awaited()
        lines = log_path.read_text(encoding="utf-8").splitlines()
        statuses = {json.loads(l)["status"] for l in lines}
        assert "skipped_no_chat_id_permanent" in statuses
        assert "skipped_no_chat_id_transient" in statuses

    @pytest.mark.asyncio
    async def test_classify_env_failure_unknown_dept(self):
        """알 수 없는 dept_id는 permanent 실패로 분류되어야 한다."""
        failure_type, reason = CollabDispatcher._classify_env_failure("unknown_dept_xyz")
        assert failure_type == "permanent"
        assert "알 수 없는 부서" in reason or "unknown_dept_xyz" in reason

    @pytest.mark.asyncio
    async def test_classify_env_failure_unset_env_var(self, monkeypatch):
        """환경변수가 설정되지 않은 경우 permanent 실패 + env_key 포함 메시지."""
        monkeypatch.delenv("DESIGN_BOT_CHAT_ID", raising=False)
        failure_type, reason = CollabDispatcher._classify_env_failure("aiorg_design_bot")
        assert failure_type == "permanent"
        assert "DESIGN_BOT_CHAT_ID" in reason
