"""주간회의 멀티봇 토론 E2E 테스트.

시나리오:
1. PM 봇이 weekly-review 트리거 시 각 팀 봇에게 순차 발언 위임
2. 각 봇이 자신의 담당 섹션만 채팅방에 전송
3. 모든 봇 발언 완료 후 PM이 종합 마무리 멘트

실제 Telegram/LLM 호출 없음 — GroupChatHub + TurnManager mock 기반.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.group_chat_hub import GroupChatHub, GroupMessage


# ── 봇별 speak callback 팩토리 ──────────────────────────────────────────────

BOT_CONFIGS = [
    ("aiorg_engineering_bot", "Engineering", "지난 주 완료 작업: CI/CD 파이프라인 개선, API v2 배포"),
    ("aiorg_design_bot", "Design", "디자인 진행상황: 대시보드 리디자인 완료, 모바일 와이어프레임 작업 중"),
    ("aiorg_growth_bot", "Growth", "지표 현황: WAU 12% 증가, 리텐션 개선 실험 진행 중"),
    ("aiorg_product_bot", "Product", "기획 현황: Q2 로드맵 확정, 사용자 피드백 분석 완료"),
]


def _make_speak_callback(bot_id: str, response_text: str):
    """봇별 speak callback 생성. 호출 시 고정 응답 반환."""
    async def callback(topic: str, ctx: list[GroupMessage]) -> str:
        return response_text
    callback.__bot_id__ = bot_id
    return callback


# ── 테스트 ─────────────────────────────────────────────────────────────────


@pytest.fixture
def sent_messages():
    """Telegram 전송 메시지를 캡처하는 리스트."""
    return []


@pytest.fixture
def hub(sent_messages):
    """GroupChatHub with mock send and registered bots."""
    async def mock_send(text: str) -> None:
        sent_messages.append(text)

    hub = GroupChatHub(send_to_group=mock_send)
    for bot_id, _label, response in BOT_CONFIGS:
        hub.register_participant(
            bot_id=bot_id,
            speak_callback=_make_speak_callback(bot_id, response),
            domain_keywords=[],
        )
    return hub


class TestWeeklyMultibotMeeting:
    """주간회의 멀티봇 순차 발언 테스트."""

    @pytest.mark.asyncio
    async def test_meeting_sends_opening_and_closing(self, hub, sent_messages):
        """회의 시작/종료 메시지가 전송되는지 확인."""
        participants = [bot_id for bot_id, _, _ in BOT_CONFIGS]
        await hub.start_meeting(topic="주간 스탠드업", participants=participants)

        # 시작 메시지
        assert any("주간 스탠드업" in m and "시작" in m for m in sent_messages), (
            f"회의 시작 메시지 없음: {sent_messages}"
        )
        # 종료 메시지
        assert any("완료" in m for m in sent_messages), (
            f"회의 종료 메시지 없음: {sent_messages}"
        )

    @pytest.mark.asyncio
    async def test_each_bot_speaks_in_order(self, hub, sent_messages):
        """각 봇이 등록된 순서대로 발언하는지 검증."""
        participants = [bot_id for bot_id, _, _ in BOT_CONFIGS]
        await hub.start_meeting(topic="주간 스탠드업", participants=participants)

        # 봇 발언 메시지만 추출 (** [bot_id] ** 형태)
        bot_utterances = [
            m for m in sent_messages
            if m.startswith("**[") and "]**" in m
        ]

        assert len(bot_utterances) == len(BOT_CONFIGS), (
            f"봇 발언 수 불일치: expected={len(BOT_CONFIGS)}, got={len(bot_utterances)}\n"
            f"messages={bot_utterances}"
        )

        # 발언 순서 검증
        for i, (bot_id, _label, _resp) in enumerate(BOT_CONFIGS):
            assert bot_id in bot_utterances[i], (
                f"순서 {i}: expected {bot_id}, got {bot_utterances[i]}"
            )

    @pytest.mark.asyncio
    async def test_each_bot_speaks_own_section(self, hub, sent_messages):
        """각 봇이 자신의 담당 섹션 내용만 발언하는지 확인."""
        participants = [bot_id for bot_id, _, _ in BOT_CONFIGS]
        await hub.start_meeting(topic="주간 스탠드업", participants=participants)

        for bot_id, _label, expected_content in BOT_CONFIGS:
            # 해당 봇의 발언 메시지 찾기
            bot_msgs = [m for m in sent_messages if f"[{bot_id}]" in m]
            assert len(bot_msgs) == 1, (
                f"{bot_id}: 발언 {len(bot_msgs)}개 (expected 1)"
            )
            assert expected_content in bot_msgs[0], (
                f"{bot_id}: 기대 내용 없음. got={bot_msgs[0]}"
            )

    @pytest.mark.asyncio
    async def test_pm_closing_after_all_bots(self, hub, sent_messages):
        """모든 봇 발언 후 PM이 종합 마무리 메시지를 보내는지 확인."""
        participants = [bot_id for bot_id, _, _ in BOT_CONFIGS]
        await hub.start_meeting(topic="주간 스탠드업", participants=participants)

        # 마지막 봇 발언 이후에 완료 메시지가 와야 함
        last_bot = BOT_CONFIGS[-1][0]
        last_bot_idx = None
        closing_idx = None
        for i, m in enumerate(sent_messages):
            if f"[{last_bot}]" in m:
                last_bot_idx = i
            if "완료" in m:
                closing_idx = i

        assert last_bot_idx is not None, f"마지막 봇 발언 없음"
        assert closing_idx is not None, f"종료 메시지 없음"
        assert closing_idx > last_bot_idx, (
            f"종료 메시지({closing_idx})가 마지막 봇 발언({last_bot_idx}) 이전"
        )


class TestWeeklyMultibotContext:
    """봇 간 컨텍스트 공유 테스트."""

    @pytest.mark.asyncio
    async def test_later_bots_see_earlier_context(self, sent_messages):
        """뒤에 발언하는 봇이 앞선 봇의 발언을 컨텍스트로 받는지 확인."""
        context_received: dict[str, list[GroupMessage]] = {}

        async def mock_send(text: str) -> None:
            sent_messages.append(text)

        hub = GroupChatHub(send_to_group=mock_send)

        for bot_id, _label, response in BOT_CONFIGS:
            async def make_cb(bid=bot_id, resp=response):
                async def cb(topic: str, ctx: list[GroupMessage]) -> str:
                    context_received[bid] = list(ctx)
                    return resp
                return cb

            hub.register_participant(
                bot_id=bot_id,
                speak_callback=await make_cb(),
                domain_keywords=[],
            )

        participants = [bot_id for bot_id, _, _ in BOT_CONFIGS]
        await hub.start_meeting(topic="주간 스탠드업", participants=participants)

        # 첫 번째 봇은 컨텍스트 없음 (또는 시작 메시지만)
        first_bot = BOT_CONFIGS[0][0]
        first_ctx = context_received.get(first_bot, [])
        first_bot_msgs = [m for m in first_ctx if m.from_bot in [b[0] for b in BOT_CONFIGS]]
        assert len(first_bot_msgs) == 0, (
            f"첫 번째 봇이 다른 봇 발언을 컨텍스트로 받음: {first_bot_msgs}"
        )

        # 마지막 봇은 이전 봇들의 발언이 컨텍스트에 포함
        last_bot = BOT_CONFIGS[-1][0]
        last_ctx = context_received.get(last_bot, [])
        earlier_bots_in_ctx = [
            m.from_bot for m in last_ctx
            if m.from_bot in [b[0] for b in BOT_CONFIGS[:-1]]
        ]
        assert len(earlier_bots_in_ctx) >= 1, (
            f"마지막 봇 컨텍스트에 이전 봇 발언 없음: {[m.from_bot for m in last_ctx]}"
        )


class TestWeeklyMultibotTimeoutHandling:
    """봇 타임아웃 처리 테스트."""

    @pytest.mark.asyncio
    async def test_timeout_bot_skipped_others_continue(self, sent_messages):
        """한 봇이 타임아웃되어도 나머지 봇은 정상 발언하는지 확인."""
        async def mock_send(text: str) -> None:
            sent_messages.append(text)

        hub = GroupChatHub(send_to_group=mock_send)

        for i, (bot_id, _label, response) in enumerate(BOT_CONFIGS):
            if i == 1:  # 두 번째 봇 타임아웃 시뮬레이션
                async def timeout_cb(topic: str, ctx: list[GroupMessage]) -> str:
                    await asyncio.sleep(999)
                    return "never"
                hub.register_participant(bot_id=bot_id, speak_callback=timeout_cb)
            else:
                hub.register_participant(
                    bot_id=bot_id,
                    speak_callback=_make_speak_callback(bot_id, response),
                )

        # TURN_TIMEOUT_SEC=45 이므로 테스트에서는 패치
        import core.group_chat_hub as ghm
        original_timeout = ghm.TURN_TIMEOUT_SEC
        ghm.TURN_TIMEOUT_SEC = 0.1  # 빠른 타임아웃

        try:
            participants = [bot_id for bot_id, _, _ in BOT_CONFIGS]
            await hub.start_meeting(topic="주간 스탠드업", participants=participants)
        finally:
            ghm.TURN_TIMEOUT_SEC = original_timeout

        # 타임아웃 메시지 확인
        timeout_msgs = [m for m in sent_messages if "타임아웃" in m]
        assert len(timeout_msgs) >= 1, f"타임아웃 메시지 없음: {sent_messages}"

        # 나머지 봇 발언 확인 (1번 제외 = 3개)
        normal_bots = [b[0] for i, b in enumerate(BOT_CONFIGS) if i != 1]
        for bot_id in normal_bots:
            assert any(f"[{bot_id}]" in m for m in sent_messages), (
                f"{bot_id} 발언 없음 (타임아웃 봇 이후에도 진행되어야 함)"
            )

        # 종료 메시지 확인
        assert any("완료" in m for m in sent_messages)


class TestWeeklyMultibotDiscussionDispatch:
    """PM discussion_dispatch를 통한 멀티봇 토론 위임 테스트."""

    @pytest.mark.asyncio
    async def test_discussion_dispatch_creates_subtasks_for_all_participants(self):
        """discussion_dispatch가 각 참여 봇에 대해 서브태스크를 생성하는지 확인."""
        from unittest.mock import MagicMock, AsyncMock, patch
        from core.pm_orchestrator import PMOrchestrator

        db = MagicMock()
        created_tasks: list[dict] = []

        async def capture_create_task(**kwargs):
            created_tasks.append(kwargs)

        db.create_pm_task = AsyncMock(side_effect=capture_create_task)
        db.update_pm_task_status = AsyncMock()
        db.update_pm_task_metadata = AsyncMock()
        db.get_pm_task = AsyncMock(return_value=None)
        db.get_subtasks = AsyncMock(return_value=[])
        db.get_active_parent_tasks = AsyncMock(return_value=[])
        db.db_path = ":memory:"

        send_func = AsyncMock()

        orch = PMOrchestrator(
            context_db=db,
            task_graph=MagicMock(
                add_task=AsyncMock(),
                get_ready_tasks=AsyncMock(return_value=[]),
                mark_complete=AsyncMock(return_value=[]),
            ),
            claim_manager=MagicMock(),
            memory=MagicMock(),
            org_id="aiorg_pm_bot",
            telegram_send_func=send_func,
            decision_client=None,
        )
        orch._task_counter = 0

        participants = ["aiorg_engineering_bot", "aiorg_design_bot", "aiorg_growth_bot"]

        with patch("core.pm_orchestrator.load_orchestration_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(
                list_specialist_orgs=MagicMock(return_value=[]),
                list_orgs=MagicMock(return_value=[]),
            )

            task_ids = await orch.discussion_dispatch(
                topic="주간회의 — 이번 주 성과와 다음 주 계획",
                dept_hints=participants,
                chat_id=-123456,
                rounds=2,
            )

        # 부모 태스크 1개 + 봇별 서브태스크 3개
        assert len(created_tasks) == 4, (
            f"태스크 수: expected 4 (1 parent + 3 sub), got {len(created_tasks)}"
        )

        # 부모 태스크 메타데이터 검증
        parent = created_tasks[0]
        assert parent["metadata"]["interaction_mode"] == "discussion"
        assert parent["metadata"]["discussion_rounds"] == 2
        assert parent["metadata"]["discussion_participants"] == participants

        # 서브태스크별 assigned_dept 검증
        sub_depts = [t["assigned_dept"] for t in created_tasks[1:]]
        assert sub_depts == participants, (
            f"서브태스크 부서 할당 불일치: {sub_depts}"
        )

        # 반환된 task_ids 수 검증
        assert len(task_ids) == 3

    @pytest.mark.asyncio
    async def test_discussion_dispatch_sends_telegram_notifications(self):
        """discussion_dispatch가 각 봇에 Telegram 알림을 보내는지 확인."""
        from unittest.mock import MagicMock, AsyncMock, patch
        from core.pm_orchestrator import PMOrchestrator

        db = MagicMock()
        db.create_pm_task = AsyncMock()
        db.update_pm_task_status = AsyncMock()
        db.update_pm_task_metadata = AsyncMock()
        db.get_pm_task = AsyncMock(return_value=None)
        db.get_subtasks = AsyncMock(return_value=[])
        db.get_active_parent_tasks = AsyncMock(return_value=[])
        db.db_path = ":memory:"

        send_func = AsyncMock()

        orch = PMOrchestrator(
            context_db=db,
            task_graph=MagicMock(
                add_task=AsyncMock(),
                get_ready_tasks=AsyncMock(return_value=[]),
                mark_complete=AsyncMock(return_value=[]),
            ),
            claim_manager=MagicMock(),
            memory=MagicMock(),
            org_id="aiorg_pm_bot",
            telegram_send_func=send_func,
            decision_client=None,
        )
        orch._task_counter = 0

        participants = ["aiorg_engineering_bot", "aiorg_growth_bot"]

        with patch("core.pm_orchestrator.load_orchestration_config") as mock_cfg:
            mock_cfg.return_value = MagicMock(
                list_specialist_orgs=MagicMock(return_value=[]),
                list_orgs=MagicMock(return_value=[]),
            )
            await orch.discussion_dispatch(
                topic="주간 성과 토론",
                dept_hints=participants,
                chat_id=-123456,
                rounds=1,
            )

        # 각 봇에 대해 토론 참여 알림 전송
        assert send_func.call_count >= len(participants), (
            f"Telegram 전송 횟수 부족: {send_func.call_count}"
        )
        all_texts = [str(c) for c in send_func.call_args_list]
        for bot_id in participants:
            assert any(bot_id in t for t in all_texts), (
                f"{bot_id}에 대한 알림 없음"
            )
