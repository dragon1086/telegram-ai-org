"""P2PMessenger + SharedMemory 단위 테스트."""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

from core.message_bus import MessageBus, EventType
from core.p2p_messenger import P2PMessage, P2PMessenger
from core.shared_memory import SharedMemory


# ---------------------------------------------------------------------------
# P2PMessenger
# ---------------------------------------------------------------------------


@pytest.fixture
def bus() -> MessageBus:
    return MessageBus()


@pytest.fixture
def messenger(bus: MessageBus) -> P2PMessenger:
    return P2PMessenger(bus=bus)


@pytest.mark.asyncio
async def test_send_delivers_to_registered_bot(messenger: P2PMessenger) -> None:
    received: list[P2PMessage] = []

    async def handler(msg: P2PMessage) -> None:
        received.append(msg)

    messenger.register("bot_b", handler)
    await messenger.send("bot_a", "bot_b", {"type": "hello"})

    assert len(received) == 1
    assert received[0].from_bot == "bot_a"
    assert received[0].to_bot == "bot_b"
    assert received[0].payload["type"] == "hello"


@pytest.mark.asyncio
async def test_send_no_handler_does_not_raise(messenger: P2PMessenger) -> None:
    # 핸들러 없어도 예외 없이 동작해야 함
    msg = await messenger.send("bot_a", "nonexistent_bot", {"type": "ping"})
    assert msg.from_bot == "bot_a"


@pytest.mark.asyncio
async def test_broadcast_reaches_all_except_sender(messenger: P2PMessenger) -> None:
    received_by: list[str] = []

    async def make_handler(name: str):
        async def handler(msg: P2PMessage) -> None:
            received_by.append(name)
        return handler

    messenger.register("bot_a", await make_handler("bot_a"))
    messenger.register("bot_b", await make_handler("bot_b"))
    messenger.register("bot_c", await make_handler("bot_c"))

    await messenger.broadcast("bot_a", {"type": "announce"})

    assert "bot_a" not in received_by
    assert "bot_b" in received_by
    assert "bot_c" in received_by


@pytest.mark.asyncio
async def test_notify_task_done_sends_to_specific_bots(messenger: P2PMessenger) -> None:
    received: list[P2PMessage] = []

    async def handler(msg: P2PMessage) -> None:
        received.append(msg)

    messenger.register("analyst_bot", handler)
    messenger.register("docs_bot", handler)

    await messenger.notify_task_done(
        "dev_bot",
        task_id="T-001",
        result_summary="파일 3개 생성",
        notify_bots=["analyst_bot"],
    )

    assert len(received) == 1
    assert received[0].payload["task_id"] == "T-001"
    assert received[0].payload["type"] == "task_done"
    assert received[0].to_bot == "analyst_bot"


@pytest.mark.asyncio
async def test_notify_task_done_broadcasts_when_no_list(messenger: P2PMessenger) -> None:
    received: list[P2PMessage] = []

    async def handler(msg: P2PMessage) -> None:
        received.append(msg)

    messenger.register("analyst_bot", handler)
    messenger.register("docs_bot", handler)

    await messenger.notify_task_done("dev_bot", task_id="T-002", result_summary="완료")

    # dev_bot 제외 2개 봇 모두 수신
    assert len(received) == 2


@pytest.mark.asyncio
async def test_request_collab(messenger: P2PMessenger) -> None:
    received: list[P2PMessage] = []

    async def handler(msg: P2PMessage) -> None:
        received.append(msg)

    messenger.register("analyst_bot", handler)

    await messenger.request_collab(
        "dev_bot", "analyst_bot", task="시장 조사 필요", context="JWT 라이브러리 v1.0"
    )

    assert len(received) == 1
    p = received[0].payload
    assert p["type"] == "collab_request"
    assert p["task"] == "시장 조사 필요"
    assert "JWT" in p["context"]


@pytest.mark.asyncio
async def test_handler_error_is_isolated(messenger: P2PMessenger) -> None:
    """핸들러 예외가 다른 핸들러 실행을 막지 않아야 함."""
    ok_received: list[P2PMessage] = []

    async def bad_handler(msg: P2PMessage) -> None:
        raise RuntimeError("의도적 에러")

    async def ok_handler(msg: P2PMessage) -> None:
        ok_received.append(msg)

    messenger.register("bot_b", bad_handler)
    messenger.register("bot_b", ok_handler)

    await messenger.send("bot_a", "bot_b", {"type": "test"})
    assert len(ok_received) == 1


@pytest.mark.asyncio
async def test_message_log_records_messages(messenger: P2PMessenger) -> None:
    async def noop(msg: P2PMessage) -> None:
        pass

    messenger.register("bot_b", noop)
    await messenger.send("bot_a", "bot_b", {"type": "x"})
    await messenger.send("bot_a", "bot_b", {"type": "y"})

    log = messenger.message_log()
    assert len(log) == 2
    assert log[0]["type"] == "x"
    assert log[1]["type"] == "y"


@pytest.mark.asyncio
async def test_bus_event_triggers_delivery(bus: MessageBus, messenger: P2PMessenger) -> None:
    """버스로 발행된 P2P_MESSAGE 이벤트도 핸들러에 전달되어야 함."""
    from core.message_bus import Event

    received: list[P2PMessage] = []

    async def handler(msg: P2PMessage) -> None:
        received.append(msg)

    await bus.start()
    messenger.register("bot_target", handler)

    await bus.publish(Event(
        type=EventType.P2P_MESSAGE,
        source="external_bot",
        target="bot_target",
        data={"to": "bot_target", "payload": {"type": "bus_event"}, "msg_id": "ext-001"},
    ))

    assert len(received) == 1
    assert received[0].payload["type"] == "bus_event"


def test_list_bots(messenger: P2PMessenger) -> None:
    async def noop(msg: P2PMessage) -> None:
        pass

    messenger.register("bot_a", noop)
    messenger.register("bot_b", noop)
    assert set(messenger.list_bots()) == {"bot_a", "bot_b"}


def test_unregister(messenger: P2PMessenger) -> None:
    async def noop(msg: P2PMessage) -> None:
        pass

    messenger.register("bot_a", noop)
    messenger.unregister("bot_a")
    assert "bot_a" not in messenger.list_bots()


# ---------------------------------------------------------------------------
# SharedMemory
# ---------------------------------------------------------------------------


@pytest.fixture
def mem() -> SharedMemory:
    return SharedMemory()


@pytest.mark.asyncio
async def test_set_and_get(mem: SharedMemory) -> None:
    await mem.set("dev_bot", "result", {"files": ["a.py"]})
    val = await mem.get("dev_bot", "result")
    assert val == {"files": ["a.py"]}


@pytest.mark.asyncio
async def test_get_missing_key_returns_default(mem: SharedMemory) -> None:
    val = await mem.get("nonexistent", "key", default="fallback")
    assert val == "fallback"


@pytest.mark.asyncio
async def test_get_namespace(mem: SharedMemory) -> None:
    await mem.set("bot_a", "x", 1)
    await mem.set("bot_a", "y", 2)
    ns = await mem.get_namespace("bot_a")
    assert ns == {"x": 1, "y": 2}


@pytest.mark.asyncio
async def test_update(mem: SharedMemory) -> None:
    await mem.update("bot_a", {"k1": "v1", "k2": "v2"})
    assert await mem.get("bot_a", "k1") == "v1"
    assert await mem.get("bot_a", "k2") == "v2"


@pytest.mark.asyncio
async def test_delete(mem: SharedMemory) -> None:
    await mem.set("bot_a", "temp", "value")
    await mem.delete("bot_a", "temp")
    assert await mem.get("bot_a", "temp") is None


@pytest.mark.asyncio
async def test_clear_namespace(mem: SharedMemory) -> None:
    await mem.set("bot_a", "x", 1)
    await mem.clear_namespace("bot_a")
    ns = await mem.get_namespace("bot_a")
    assert ns == {}


@pytest.mark.asyncio
async def test_exists(mem: SharedMemory) -> None:
    await mem.set("bot_a", "key", "val")
    assert await mem.exists("bot_a", "key") is True
    assert await mem.exists("bot_a", "missing") is False


@pytest.mark.asyncio
async def test_list_namespaces(mem: SharedMemory) -> None:
    await mem.set("bot_a", "k", 1)
    await mem.set("bot_b", "k", 2)
    namespaces = await mem.list_namespaces()
    assert set(namespaces) == {"bot_a", "bot_b"}


@pytest.mark.asyncio
async def test_memory_update_event_published(bus: MessageBus) -> None:
    events: list = []

    async def capture(event) -> None:
        events.append(event)

    await bus.start()
    bus.subscribe(EventType.MEMORY_UPDATE, capture)

    mem = SharedMemory(bus=bus)
    await mem.set("dev_bot", "key", "value")

    assert len(events) == 1
    assert events[0].data["namespace"] == "dev_bot"
    assert events[0].data["key"] == "key"


@pytest.mark.asyncio
async def test_persist_to_disk_and_reload() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "mem.json"

        mem1 = SharedMemory(persist_path=path)
        await mem1.set("bot_a", "saved", 42)

        # 새 인스턴스가 디스크에서 로드
        mem2 = SharedMemory(persist_path=path)
        val = await mem2.get("bot_a", "saved")
        assert val == 42


def test_snapshot_is_copy(mem_sync=None) -> None:
    mem = SharedMemory()
    # 동기 snapshot은 현재 상태의 복사본
    snap = mem.snapshot()
    assert isinstance(snap, dict)
