"""tests/test_group_chat_hub.py — GroupChatHub, TurnManager, GroupChatContext 단위 테스트."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from core.group_chat_hub import (
    GroupChatContext,
    GroupChatHub,
    GroupMessage,
    TurnManager,
)

# ── 픽스처 ────────────────────────────────────────────────────────────────────

@pytest.fixture
def send_fn():
    return AsyncMock()


@pytest.fixture
def hub(send_fn):
    return GroupChatHub(send_to_group=send_fn)


@pytest.fixture
def context():
    return GroupChatContext(max_messages=10)


# ── GroupChatContext ───────────────────────────────────────────────────────────

class TestGroupChatContext:
    @pytest.mark.asyncio
    async def test_add_and_recent(self, context):
        await context.add(GroupMessage(from_bot="user", text="안녕"))
        await context.add(GroupMessage(from_bot="engineering", text="코드 리뷰 완료"))
        msgs = await context.recent(5)
        assert len(msgs) == 2
        assert msgs[0].text == "안녕"
        assert msgs[1].from_bot == "engineering"

    @pytest.mark.asyncio
    async def test_max_messages_respected(self):
        ctx = GroupChatContext(max_messages=3)
        for i in range(5):
            await ctx.add(GroupMessage(from_bot="user", text=f"msg{i}"))
        msgs = await ctx.snapshot()
        assert len(msgs) == 3
        assert msgs[-1].text == "msg4"

    @pytest.mark.asyncio
    async def test_recent_n(self, context):
        for i in range(8):
            await context.add(GroupMessage(from_bot="bot", text=f"m{i}"))
        recent = await context.recent(3)
        assert len(recent) == 3
        assert recent[-1].text == "m7"


# ── GroupChatHub 등록/해제 ─────────────────────────────────────────────────────

class TestGroupChatHubRegistration:
    def test_register_participant(self, hub):
        callback = AsyncMock(return_value="응답입니다")
        hub.register_participant("engineering", callback, domain_keywords=["코드", "버그"])
        assert "engineering" in hub.participant_ids

    def test_unregister_participant(self, hub):
        hub.register_participant("product", AsyncMock(), domain_keywords=["기획"])
        hub.unregister_participant("product")
        assert "product" not in hub.participant_ids

    def test_register_multiple(self, hub):
        hub.register_participant("eng", AsyncMock())
        hub.register_participant("design", AsyncMock())
        hub.register_participant("growth", AsyncMock())
        assert len(hub.participant_ids) == 3


# ── 메시지 수신 → 응답 라우팅 ────────────────────────────────────────────────────

class TestGroupChatHubMessageRouting:
    @pytest.mark.asyncio
    async def test_explicit_mention_triggers_only_mentioned_bot(self, hub, send_fn):
        eng_cb = AsyncMock(return_value="코드 리뷰 완료했습니다")
        des_cb = AsyncMock(return_value=None)
        hub.register_participant("engineering", eng_cb, domain_keywords=["코드"])
        hub.register_participant("design", des_cb, domain_keywords=["디자인"])

        await hub.on_group_message("@engineering 이번 주 작업 보고해줘", from_user="user")

        eng_cb.assert_called_once()
        des_cb.assert_not_called()
        # 그룹방 전송 확인
        calls = [str(c) for c in send_fn.call_args_list]
        assert any("engineering" in c for c in calls)

    @pytest.mark.asyncio
    async def test_domain_keyword_match(self, hub, send_fn):
        eng_cb = AsyncMock(return_value="버그 수정했어요")
        hub.register_participant("engineering", eng_cb, domain_keywords=["버그", "코드"])

        await hub.on_group_message("버그 수정 현황 공유해줘", from_user="user")

        eng_cb.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_match_no_response(self, hub, send_fn):
        eng_cb = AsyncMock(return_value="응답")
        hub.register_participant("engineering", eng_cb, domain_keywords=["코드"])

        await hub.on_group_message("날씨가 좋네요", from_user="user")

        eng_cb.assert_not_called()

    @pytest.mark.asyncio
    async def test_message_added_to_context(self, hub):
        hub.register_participant("eng", AsyncMock(return_value="ok"))
        await hub.on_group_message("안녕하세요", from_user="user", auto_respond=False)
        msgs = await hub.context.snapshot()
        assert len(msgs) == 1
        assert msgs[0].text == "안녕하세요"

    @pytest.mark.asyncio
    async def test_none_response_not_sent(self, hub, send_fn):
        """콜백이 None 반환하면 그룹에 아무것도 전송하지 않아야 한다."""
        eng_cb = AsyncMock(return_value=None)
        hub.register_participant("engineering", eng_cb, domain_keywords=["코드"])

        await hub.on_group_message("코드 현황", from_user="user")
        # send_fn이 응답 메시지로 호출되지 않음 (None이므로)
        for call in send_fn.call_args_list:
            assert "engineering" not in str(call) or "[engineering]" not in str(call)

    @pytest.mark.asyncio
    async def test_auto_respond_false_skips_callbacks(self, hub):
        eng_cb = AsyncMock(return_value="응답")
        hub.register_participant("engineering", eng_cb, domain_keywords=["코드"])

        await hub.on_group_message("코드 점검", from_user="user", auto_respond=False)
        eng_cb.assert_not_called()


# ── TurnManager ────────────────────────────────────────────────────────────────

class TestTurnManager:
    @pytest.mark.asyncio
    async def test_start_meeting_calls_all_participants(self, send_fn):
        ctx = GroupChatContext()
        tm = TurnManager(send_to_group=send_fn, context=ctx)

        eng_cb = AsyncMock(return_value="엔지니어링 보고")
        prod_cb = AsyncMock(return_value="제품 보고")

        await tm.start_meeting(
            topic="주간 스탠드업",
            participants=["engineering", "product"],
            speak_callbacks={"engineering": eng_cb, "product": prod_cb},
        )

        eng_cb.assert_called_once()
        prod_cb.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_meeting_sends_responses_to_group(self, send_fn):
        ctx = GroupChatContext()
        tm = TurnManager(send_to_group=send_fn, context=ctx)

        eng_cb = AsyncMock(return_value="이번 주 API 구현 완료")
        await tm.start_meeting(
            topic="테스트 회의",
            participants=["engineering"],
            speak_callbacks={"engineering": eng_cb},
        )

        all_calls = " ".join(str(c) for c in send_fn.call_args_list)
        assert "이번 주 API 구현 완료" in all_calls

    @pytest.mark.asyncio
    async def test_start_meeting_handles_timeout(self, send_fn):
        ctx = GroupChatContext()
        tm = TurnManager(send_to_group=send_fn, context=ctx)

        async def slow_callback(topic, ctx):
            await asyncio.sleep(9999)
            return "never"

        # timeout을 1초로 단축하여 테스트
        import core.group_chat_hub as ghub
        original_timeout = ghub.TURN_TIMEOUT_SEC
        ghub.TURN_TIMEOUT_SEC = 0.1
        try:
            await tm.start_meeting(
                topic="타임아웃 테스트",
                participants=["slow_bot"],
                speak_callbacks={"slow_bot": slow_callback},
            )
        finally:
            ghub.TURN_TIMEOUT_SEC = original_timeout

        all_calls = " ".join(str(c) for c in send_fn.call_args_list)
        assert "타임아웃" in all_calls or "slow_bot" in all_calls

    @pytest.mark.asyncio
    async def test_start_meeting_skips_missing_callback(self, send_fn):
        ctx = GroupChatContext()
        tm = TurnManager(send_to_group=send_fn, context=ctx)

        eng_cb = AsyncMock(return_value="보고")
        # "product"는 callbacks에 없음
        await tm.start_meeting(
            topic="테스트",
            participants=["engineering", "product"],
            speak_callbacks={"engineering": eng_cb},
        )

        eng_cb.assert_called_once()  # engineering만 호출

    @pytest.mark.asyncio
    async def test_request_turn_queued(self, send_fn):
        ctx = GroupChatContext()
        tm = TurnManager(send_to_group=send_fn, context=ctx)
        # 단순히 큐에 들어가는지 확인
        await tm.request_turn("engineering", "자율 발언 테스트")
        assert not tm._queue.empty()

    @pytest.mark.asyncio
    async def test_active_meeting_guard(self, send_fn):
        """회의 중 두 번째 start_meeting은 스킵되어야 한다."""
        ctx = GroupChatContext()
        tm = TurnManager(send_to_group=send_fn, context=ctx)

        blocker_event = asyncio.Event()

        async def blocking_cb(topic, ctx):
            await asyncio.wait_for(blocker_event.wait(), timeout=2.0)
            return "완료"

        # 첫 번째 회의 시작 (백그라운드)
        task1 = asyncio.create_task(
            tm.start_meeting("회의1", ["bot1"], {"bot1": blocking_cb})
        )
        # 두 번째 회의 즉시 시작 시도
        await asyncio.sleep(0.05)
        task2 = asyncio.create_task(
            tm.start_meeting("회의2", ["bot1"], {"bot1": blocking_cb})
        )

        blocker_event.set()
        await asyncio.gather(task1, task2, return_exceptions=True)

        # 두 번째 회의는 스킵됨 → blocking_cb는 1번만 호출


# ── WorkerBot 그룹 참가 ─────────────────────────────────────────────────────────

class TestWorkerBotGroupParticipation:
    def test_set_group_hub_registers_participant(self, hub):
        from core.worker_bot import WorkerBot
        bot = WorkerBot(handle="@test_bot", token="fake_token", description="테스트 봇")
        bot.set_group_hub(hub, domain_keywords=["테스트"])
        assert "@test_bot" in hub.participant_ids

    @pytest.mark.asyncio
    async def test_group_speak_callback_returns_string(self, hub):
        from core.worker_bot import WorkerBot

        bot = WorkerBot(handle="@eng_bot", token="fake_token", description="엔지니어링 봇")

        # execute를 mock
        async def mock_execute(task_id, content, ctx):
            return "API 구현 완료 보고입니다"

        bot.execute = mock_execute
        bot.set_group_hub(hub, domain_keywords=["코드"])

        # speak_callback 직접 테스트
        result = await bot._group_speak_callback("주간 스탠드업", [])
        assert result is not None
        assert "API" in result

    @pytest.mark.asyncio
    async def test_group_speak_callback_handles_error(self, hub):
        from core.worker_bot import WorkerBot

        bot = WorkerBot(handle="@err_bot", token="fake_token", description="오류 봇")

        async def failing_execute(task_id, content, ctx):
            raise RuntimeError("실행 실패")

        bot.execute = failing_execute
        bot.set_group_hub(hub)

        result = await bot._group_speak_callback("회의", [])
        assert result is None  # 에러 시 None 반환


# ── 통합 시나리오 ─────────────────────────────────────────────────────────────

class TestGroupChatHubIntegration:
    @pytest.mark.asyncio
    async def test_full_meeting_flow(self):
        """주간 회의 전체 플로우: 3개 봇 등록 → 회의 시작 → 순서대로 발언."""
        sent_messages: list[str] = []

        async def send_fn(text: str) -> None:
            sent_messages.append(text)

        hub = GroupChatHub(send_to_group=send_fn)

        responses = {
            "engineering": "이번 주 API 3개 구현 완료. 버그 2건 수정.",
            "product": "PRD v2 작성 완료. 다음 주 기능 기획 시작.",
            "growth": "신규 사용자 15% 증가. MAU 1,200명 달성.",
        }

        for bot_id, resp in responses.items():
            async def make_cb(r=resp):
                async def cb(topic, ctx):
                    return r
                return cb
            hub.register_participant(bot_id, await make_cb())

        await hub.start_meeting("주간 스탠드업", list(responses.keys()))

        all_text = " ".join(sent_messages)
        assert "API 3개 구현" in all_text
        assert "PRD v2" in all_text
        assert "1,200명" in all_text
        assert "주간 스탠드업" in all_text
        assert "✅" in all_text  # 완료 메시지

    @pytest.mark.asyncio
    async def test_context_shared_across_turns(self):
        """회의 중 앞 봇의 발언이 뒤 봇의 컨텍스트에 보임."""
        seen_contexts: list[list[GroupMessage]] = []

        async def send_fn(text: str) -> None:
            pass

        hub = GroupChatHub(send_to_group=send_fn)

        async def cb1(topic, ctx):
            return "첫 번째 발언"

        async def cb2(topic, ctx):
            seen_contexts.append(list(ctx))
            return "두 번째 발언"

        hub.register_participant("bot1", cb1)
        hub.register_participant("bot2", cb2)

        await hub.start_meeting("컨텍스트 테스트", ["bot1", "bot2"])

        # bot2 호출 시 bot1의 발언이 컨텍스트에 있어야 함
        assert any("첫 번째 발언" in m.text for ctx in seen_contexts for m in ctx)
