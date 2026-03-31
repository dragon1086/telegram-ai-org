"""주간회의 smoke test — trigger / hub 등록 / fallback 검증.

테스트 범위:
1. OrgScheduler.weekly_standup() 직접 호출 — broadcast_meeting_start 경유 전 조직 참여
2. GroupChatHub 참가자 등록 + 순차 발언 (mock 사용)
3. 타임아웃/빈 응답 fallback 처리
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.group_chat_hub import GroupChatHub, GroupMessage
from core.scheduler import OrgScheduler

# ── 공통 픽스처 ─────────────────────────────────────────────────────────────────


@pytest.fixture
def sent_messages() -> list[str]:
    """Telegram 전송 메시지를 캡처하는 버퍼."""
    return []


@pytest.fixture
def mock_send(sent_messages: list[str]):
    """send_text 역할의 async mock."""
    async def _send(text: str) -> None:
        sent_messages.append(text)
    return _send


@pytest.fixture
def hub(mock_send) -> GroupChatHub:
    """4개 조직 봇이 등록된 GroupChatHub."""
    _hub = GroupChatHub(send_to_group=mock_send)

    bot_configs = [
        ("aiorg_engineering_bot", "CI/CD 개선, API v2 배포 완료"),
        ("aiorg_design_bot", "대시보드 리디자인 완료, 모바일 와이어프레임 진행 중"),
        ("aiorg_growth_bot", "WAU 12% 증가, 리텐션 실험 진행 중"),
        ("aiorg_product_bot", "Q2 로드맵 확정, 사용자 피드백 분석 완료"),
    ]

    def _make_speak_cb(resp: str):
        async def cb(topic: str, ctx: list[GroupMessage]) -> str:
            return resp
        return cb

    for bot_id, response_text in bot_configs:
        _hub.register_participant(
            bot_id=bot_id,
            speak_callback=_make_speak_cb(response_text),
            domain_keywords=[],
        )
    return _hub


@pytest.fixture
def scheduler(mock_send) -> OrgScheduler:
    """최소 의존성으로 생성한 OrgScheduler (APScheduler 미시작)."""
    sched = OrgScheduler(send_text=mock_send)
    # APScheduler를 시작하지 않아도 잡 함수는 직접 호출 가능
    return sched


# ── 1. weekly_standup() 직접 호출 ────────────────────────────────────────────


class TestWeeklyStandupDirect:
    """OrgScheduler.weekly_standup() 직접 호출 smoke test."""

    @pytest.mark.asyncio
    async def test_weekly_standup_runs_without_pm_orchestrator(
        self, scheduler: OrgScheduler, sent_messages: list[str]
    ) -> None:
        """pm_orchestrator 없이 weekly_standup()이 안전하게 실행되는지 확인.

        pm_orchestrator 미연결 시 broadcast_meeting_start 내부에서
        fallback 메시지만 전송하고 오류 없이 반환해야 한다.
        """
        await scheduler.weekly_standup()

        # 어떤 메시지든 최소 1개는 전송되어야 함 (fallback 포함)
        assert len(sent_messages) >= 1, (
            f"weekly_standup 실행 후 메시지 없음: {sent_messages}"
        )

    @pytest.mark.asyncio
    async def test_weekly_standup_with_group_hub(
        self, mock_send, hub: GroupChatHub, sent_messages: list[str]
    ) -> None:
        """GroupChatHub가 연결된 상태에서 weekly_standup()이 hub.start_meeting을 호출하는지 확인."""
        sched = OrgScheduler(send_text=mock_send, group_chat_hub=hub)
        start_meeting_called = False

        original_start_meeting = hub.start_meeting

        async def _spy_start_meeting(*args, **kwargs):
            nonlocal start_meeting_called
            start_meeting_called = True
            return await original_start_meeting(*args, **kwargs)

        hub.start_meeting = _spy_start_meeting

        await sched.weekly_standup()

        assert start_meeting_called, (
            "GroupChatHub.start_meeting()이 호출되지 않음 — "
            "broadcast_meeting_start 내부 GroupChatHub 연동 확인 필요"
        )

    @pytest.mark.asyncio
    async def test_weekly_standup_does_not_raise_on_exception(
        self, mock_send
    ) -> None:
        """내부 오류 발생 시 예외가 외부로 전파되지 않는지 확인 (방어적 처리)."""
        errors: list[str] = []

        async def _send_capture(text: str) -> None:
            errors.append(text)

        sched = OrgScheduler(send_text=_send_capture)

        # broadcast_meeting_start가 예외를 던지는 상황 시뮬레이션
        async def _raise(*args, **kwargs):
            raise RuntimeError("mock 강제 오류")

        sched.broadcast_meeting_start = _raise

        # 예외 전파 없이 완료되어야 함
        try:
            await sched.weekly_standup()
        except Exception as exc:
            pytest.fail(f"weekly_standup에서 예외 전파됨: {exc}")

        # 오류 메시지 전송 확인
        assert any("오류" in m or "⚠️" in m for m in errors), (
            f"오류 알림 메시지 없음: {errors}"
        )


# ── 2. GroupChatHub 참가자 등록 + 순차 발언 ──────────────────────────────────


class TestGroupChatHubRegistrationAndOrder:
    """GroupChatHub 참가자 등록 및 순차 발언 테스트."""

    @pytest.mark.asyncio
    async def test_register_and_start_meeting_sequential(
        self, sent_messages: list[str], mock_send
    ) -> None:
        """4개 봇이 등록된 순서대로 발언하는지 확인."""
        _hub = GroupChatHub(send_to_group=mock_send)
        participants = [
            ("bot_a", "A팀 보고: 완료 3건"),
            ("bot_b", "B팀 보고: 완료 1건"),
            ("bot_c", "C팀 보고: 완료 2건"),
        ]

        def _make_cb(r: str):
            async def cb(topic: str, ctx: list[GroupMessage]) -> str:
                return r
            return cb

        for bot_id, resp in participants:
            _hub.register_participant(
                bot_id=bot_id,
                speak_callback=_make_cb(resp),
                domain_keywords=[],
            )

        await _hub.start_meeting(
            topic="주간 스탠드업",
            participants=[p[0] for p in participants],
        )

        # 시작 메시지 확인
        assert any("주간 스탠드업" in m and "시작" in m for m in sent_messages), (
            f"시작 메시지 없음: {sent_messages}"
        )
        # 종료 메시지 확인
        assert any("완료" in m for m in sent_messages), (
            f"종료 메시지 없음: {sent_messages}"
        )

        # 발언 순서 검증
        bot_msgs = [m for m in sent_messages if m.startswith("**[bot_")]
        assert len(bot_msgs) == len(participants), (
            f"발언 수 불일치: expected={len(participants)}, got={len(bot_msgs)}"
        )
        for i, (bot_id, _) in enumerate(participants):
            assert bot_id in bot_msgs[i], (
                f"순서 {i}: expected={bot_id}, got={bot_msgs[i]}"
            )

    @pytest.mark.asyncio
    async def test_register_participant_persists(
        self, hub: GroupChatHub
    ) -> None:
        """register_participant() 후 participant_ids에 등록된 봇이 포함되는지 확인."""
        expected = {
            "aiorg_engineering_bot",
            "aiorg_design_bot",
            "aiorg_growth_bot",
            "aiorg_product_bot",
        }
        assert set(hub.participant_ids) == expected, (
            f"등록된 참가자 불일치: {hub.participant_ids}"
        )

    @pytest.mark.asyncio
    async def test_unregister_removes_participant(
        self, hub: GroupChatHub
    ) -> None:
        """unregister_participant() 후 해당 봇이 participant_ids에서 제거되는지 확인."""
        hub.unregister_participant("aiorg_engineering_bot")
        assert "aiorg_engineering_bot" not in hub.participant_ids


# ── 3. 타임아웃 / 빈 응답 fallback ───────────────────────────────────────────


class TestTimeoutAndEmptyResponseFallback:
    """타임아웃·빈 응답 fallback 처리 테스트."""

    @pytest.mark.asyncio
    async def test_timeout_bot_skipped_meeting_continues(
        self, sent_messages: list[str], mock_send
    ) -> None:
        """타임아웃 봇이 있어도 나머지 봇이 정상 발언하고 회의가 완료되는지 확인."""
        import core.group_chat_hub as ghm
        original_timeout = ghm.TURN_TIMEOUT_SEC
        ghm.TURN_TIMEOUT_SEC = 0.05  # 빠른 타임아웃

        _hub = GroupChatHub(send_to_group=mock_send)

        async def _timeout_cb(topic: str, ctx: list[GroupMessage]) -> str:
            await asyncio.sleep(999)
            return "never"

        async def _normal_cb(topic: str, ctx: list[GroupMessage]) -> str:
            return "정상 발언"

        _hub.register_participant("slow_bot", _timeout_cb, domain_keywords=[])
        _hub.register_participant("fast_bot", _normal_cb, domain_keywords=[])

        try:
            await _hub.start_meeting(
                topic="주간 스탠드업", participants=["slow_bot", "fast_bot"]
            )
        finally:
            ghm.TURN_TIMEOUT_SEC = original_timeout

        # 타임아웃 메시지 확인
        assert any("타임아웃" in m for m in sent_messages), (
            f"타임아웃 메시지 없음: {sent_messages}"
        )
        # 정상 봇 발언 확인
        assert any("[fast_bot]" in m for m in sent_messages), (
            f"fast_bot 발언 없음: {sent_messages}"
        )
        # 회의 종료 메시지 확인
        assert any("완료" in m for m in sent_messages), (
            f"종료 메시지 없음: {sent_messages}"
        )

    @pytest.mark.asyncio
    async def test_empty_response_treated_as_pass(
        self, sent_messages: list[str], mock_send
    ) -> None:
        """빈 문자열 / None 반환 봇은 '발언 없음(패스)' 처리되는지 확인."""
        _hub = GroupChatHub(send_to_group=mock_send)

        async def _empty_cb(topic: str, ctx: list[GroupMessage]) -> str | None:
            return ""  # 빈 응답

        async def _none_cb(topic: str, ctx: list[GroupMessage]) -> str | None:
            return None  # None 응답

        _hub.register_participant("empty_bot", _empty_cb, domain_keywords=[])
        _hub.register_participant("none_bot", _none_cb, domain_keywords=[])

        await _hub.start_meeting(
            topic="주간 스탠드업", participants=["empty_bot", "none_bot"]
        )

        # 두 봇 모두 '발언 없음' 처리
        pass_msgs = [m for m in sent_messages if "패스" in m or "발언 없음" in m]
        assert len(pass_msgs) == 2, (
            f"'패스' 처리 메시지 수 불일치: expected=2, got={len(pass_msgs)}\n"
            f"messages={sent_messages}"
        )

    @pytest.mark.asyncio
    async def test_exception_in_bot_callback_does_not_abort_meeting(
        self, sent_messages: list[str], mock_send
    ) -> None:
        """봇 callback에서 예외가 발생해도 나머지 봇 발언과 회의 완료가 진행되는지 확인."""
        _hub = GroupChatHub(send_to_group=mock_send)

        async def _error_cb(topic: str, ctx: list[GroupMessage]) -> str:
            raise ValueError("mock 봇 오류")

        async def _normal_cb(topic: str, ctx: list[GroupMessage]) -> str:
            return "정상 발언"

        _hub.register_participant("error_bot", _error_cb, domain_keywords=[])
        _hub.register_participant("ok_bot", _normal_cb, domain_keywords=[])

        await _hub.start_meeting(
            topic="주간 스탠드업", participants=["error_bot", "ok_bot"]
        )

        # ok_bot은 발언해야 함
        assert any("[ok_bot]" in m for m in sent_messages), (
            f"ok_bot 발언 없음: {sent_messages}"
        )
        # 회의 종료 메시지 확인
        assert any("완료" in m for m in sent_messages), (
            f"종료 메시지 없음: {sent_messages}"
        )
