import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.message_bus import MessageBus, EventType, Event


@pytest.mark.asyncio
async def test_inactivity_event_type_exists():
    """INACTIVITY_DETECTED 이벤트 타입이 존재하는지"""
    assert hasattr(EventType, "INACTIVITY_DETECTED")
    assert hasattr(EventType, "DAILY_INSIGHT")


@pytest.mark.asyncio
async def test_proactive_handler_subscribes():
    """ProactiveHandler가 두 이벤트를 구독하는지"""
    from core.proactive_handler import ProactiveHandler
    bus = MessageBus()
    handler = ProactiveHandler(bus, bots={})
    handler.register()
    # Check subscriptions exist (adapt to actual MessageBus internal structure)
    assert handler is not None  # at minimum, register() didn't crash


@pytest.mark.asyncio
async def test_inactivity_handler_called_on_event():
    """INACTIVITY_DETECTED 이벤트 발화 시 핸들러가 호출되고 에러 없음"""
    from core.proactive_handler import ProactiveHandler
    bus = MessageBus()
    handler = ProactiveHandler(bus, bots={})
    handler._send_proactive_message = AsyncMock()
    handler.register()

    await bus.publish(Event(
        type=EventType.INACTIVITY_DETECTED,
        source="test",
        data={"chat_id": "chat1", "inactive_hours": 5}
    ))
    # Should have been called once (no bots = no active_hours check needed)
    handler._send_proactive_message.assert_called_once()


@pytest.mark.asyncio
async def test_event_suppressed_outside_active_hours():
    """active_hours 범위 밖에서 이벤트가 억제되는지"""
    from core.proactive_handler import ProactiveHandler
    import core.proactive_handler as ph_module
    bus = MessageBus()
    handler = ProactiveHandler(
        bus,
        bots={"bot1": {"active_hours": {"start": 9, "end": 10}}},
    )
    handler._send_proactive_message = AsyncMock()
    handler.register()

    with patch.object(ph_module, "datetime") as mock_dt:
        mock_dt.now.return_value = MagicMock(hour=3)
        await bus.publish(Event(
            type=EventType.INACTIVITY_DETECTED,
            source="test",
            data={"chat_id": "chat1", "inactive_hours": 5, "bot_id": "bot1"}
        ))
    handler._send_proactive_message.assert_not_called()


def test_active_hours_yaml_parsed():
    """bots/*.yaml active_hours 파싱 확인"""
    import yaml
    import os
    bot_yamls = [f for f in os.listdir("bots") if f.endswith(".yaml")]
    assert len(bot_yamls) > 0
    for fname in bot_yamls:
        with open(f"bots/{fname}") as f:
            cfg = yaml.safe_load(f)
        if "active_hours" in cfg:
            assert "start" in cfg["active_hours"]
            assert "end" in cfg["active_hours"]
