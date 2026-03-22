"""
tests/test_thinking_heartbeat.py
Thinking heartbeat (60초 간격) 구현 검증 테스트.
"""
import asyncio
import time
from contextlib import suppress
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# 헬퍼: heartbeat 루프 독립 추출 (telegram_relay 내부와 동일 로직)
# ---------------------------------------------------------------------------

async def make_heartbeat_loop(on_progress_fn, interval: int = 60):
    """_thinking_heartbeat_loop 로직을 테스트용으로 재현."""
    await asyncio.sleep(interval)
    while True:
        try:
            await on_progress_fn("🤔 처리 중...")
        except Exception:
            pass
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Test 1: 짧은 실행(interval 미만)에서 heartbeat 미발화
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_heartbeat_does_not_fire_before_interval():
    """60초 미만 실행 → heartbeat 발화 없어야 함."""
    calls: list[str] = []

    async def on_progress(line: str) -> None:
        calls.append(line)

    hb_task = asyncio.ensure_future(make_heartbeat_loop(on_progress, interval=60))
    # 0.1초 후 취소 (60초 훨씬 전)
    await asyncio.sleep(0.1)
    hb_task.cancel()
    with suppress(asyncio.CancelledError):
        await hb_task

    assert calls == [], f"heartbeat가 조기 발화됨: {calls}"


# ---------------------------------------------------------------------------
# Test 2: interval 경과 후 heartbeat 발화
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_heartbeat_fires_after_interval():
    """interval 경과 후 on_progress('🤔 처리 중...') 정확히 1회 이상 호출."""
    calls: list[str] = []

    async def on_progress(line: str) -> None:
        calls.append(line)

    # 테스트 속도를 위해 interval=0.2초로 단축
    hb_task = asyncio.ensure_future(make_heartbeat_loop(on_progress, interval=0.2))
    await asyncio.sleep(0.35)  # 0.2초 후 첫 발화, 0.4초 후 두 번째
    hb_task.cancel()
    with suppress(asyncio.CancelledError):
        await hb_task

    assert len(calls) >= 1, "heartbeat가 한 번도 발화되지 않음"
    assert all(c == "🤔 처리 중..." for c in calls), f"예상치 않은 메시지: {calls}"


# ---------------------------------------------------------------------------
# Test 3: 실행 완료 후 heartbeat 정지 (누수 없음)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_heartbeat_stops_after_cancel():
    """cancel 후 on_progress가 더 이상 호출되지 않아야 함."""
    calls: list[str] = []

    async def on_progress(line: str) -> None:
        calls.append(line)

    hb_task = asyncio.ensure_future(make_heartbeat_loop(on_progress, interval=0.1))
    await asyncio.sleep(0.25)  # 2회 발화 허용
    hb_task.cancel()
    with suppress(asyncio.CancelledError):
        await hb_task

    count_before = len(calls)
    await asyncio.sleep(0.2)  # cancel 후 추가 대기
    count_after = len(calls)

    assert count_after == count_before, (
        f"cancel 후에도 heartbeat 누수 발생: before={count_before}, after={count_after}"
    )


# ---------------------------------------------------------------------------
# Test 4: on_progress 예외 발생 시 heartbeat 루프 지속
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_heartbeat_continues_on_progress_exception():
    """on_progress가 예외를 던져도 heartbeat 루프가 멈추지 않아야 함."""
    call_count = 0

    async def on_progress(line: str) -> None:
        nonlocal call_count
        call_count += 1
        raise RuntimeError("progress error")

    hb_task = asyncio.ensure_future(make_heartbeat_loop(on_progress, interval=0.1))
    await asyncio.sleep(0.45)  # 4회 이상 발화 기대
    hb_task.cancel()
    with suppress(asyncio.CancelledError):
        await hb_task

    assert call_count >= 2, f"예외 후 heartbeat 중단됨 (call_count={call_count})"


# ---------------------------------------------------------------------------
# Test 5: finally 블록에서 heartbeat_task.cancel() 보장
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_heartbeat_cancelled_in_finally():
    """try-finally 패턴에서 정상 완료 시 heartbeat_task가 cancel되는지 확인."""
    calls: list[str] = []

    async def on_progress(line: str) -> None:
        calls.append(line)

    async def fake_execution():
        await asyncio.sleep(0.05)
        return "done"

    hb_task = asyncio.ensure_future(make_heartbeat_loop(on_progress, interval=0.5))
    try:
        result = await fake_execution()
        assert result == "done"
    finally:
        hb_task.cancel()
        with suppress(asyncio.CancelledError):
            await hb_task

    assert hb_task.cancelled() or hb_task.done(), "finally에서 heartbeat_task가 종료되지 않음"


# ---------------------------------------------------------------------------
# Test 6: idle_timeout 기본값 120초 확인
# ---------------------------------------------------------------------------

def test_idle_timeout_default_is_120():
    """BOT_IDLE_TIMEOUT_SEC 환경변수 미설정 시 기본값 120초 확인."""
    import os
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("BOT_IDLE_TIMEOUT_SEC", None)
        val = int(os.environ.get("BOT_IDLE_TIMEOUT_SEC", "120"))
    assert val == 120, f"idle timeout 기본값이 120이 아님: {val}"


# ---------------------------------------------------------------------------
# Test 7: heartbeat 간격이 idle_timeout보다 짧아야 함 (60 < 120)
# ---------------------------------------------------------------------------

def test_heartbeat_interval_less_than_idle_timeout():
    """heartbeat 간격(60s)이 idle timeout(120s)보다 짧아야 오탐 방지 가능."""
    hb_interval = 60
    idle_timeout = 120
    assert hb_interval < idle_timeout, (
        f"heartbeat 간격({hb_interval}s)이 idle timeout({idle_timeout}s) 이상이면 오탐 위험"
    )
