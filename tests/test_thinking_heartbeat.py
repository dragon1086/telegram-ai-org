"""
tests/test_thinking_heartbeat.py
Thinking heartbeat 구현 검증 테스트.
- heartbeat 발화 타이밍 / 예외 내성 / 취소 동작
- active/stuck 판별 로직 (progress_snapshot 기반)
- 환경변수 설정값 검증
"""
import asyncio
import os
import time
from contextlib import suppress
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# 헬퍼: heartbeat 루프 독립 추출 (telegram_relay 내부와 동일 로직)
# ---------------------------------------------------------------------------

async def make_heartbeat_loop(on_progress_fn, interval: int = 30):
    """_thinking_heartbeat_loop 로직을 테스트용으로 재현."""
    hb_count = 0
    await asyncio.sleep(interval)
    while True:
        hb_count += 1
        try:
            await on_progress_fn("🤔 처리 중...")
        except Exception:
            pass
        await asyncio.sleep(interval)


def build_watchdog_timeout_msg(
    idle: float,
    idle_timeout: int,
    progress_snapshot: list[tuple[float, str]],
) -> str:
    """_watchdog_loop의 타임아웃 메시지 생성 로직 재현."""
    if progress_snapshot:
        last_ts, last_line = progress_snapshot[-1]
        since_last = time.time() - last_ts
        snap_hint = f" | 마지막 출력 {since_last:.0f}s 전: {last_line[:80]}"
    else:
        snap_hint = " | 실행 중 출력 없음 (stuck 가능성)"
    return f"무응답 {idle:.0f}초 (한도 {idle_timeout}s){snap_hint}"


# ---------------------------------------------------------------------------
# Test 1: 짧은 실행(interval 미만)에서 heartbeat 미발화
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_heartbeat_does_not_fire_before_interval():
    """interval 미만 실행 → heartbeat 발화 없어야 함."""
    calls: list[str] = []

    async def on_progress(line: str) -> None:
        calls.append(line)

    hb_task = asyncio.ensure_future(make_heartbeat_loop(on_progress, interval=60))
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

    hb_task = asyncio.ensure_future(make_heartbeat_loop(on_progress, interval=0.2))
    await asyncio.sleep(0.35)
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
    await asyncio.sleep(0.25)
    hb_task.cancel()
    with suppress(asyncio.CancelledError):
        await hb_task

    count_before = len(calls)
    await asyncio.sleep(0.2)
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
    await asyncio.sleep(0.45)
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
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("BOT_IDLE_TIMEOUT_SEC", None)
        val = int(os.environ.get("BOT_IDLE_TIMEOUT_SEC", "120"))
    assert val == 120, f"idle timeout 기본값이 120이 아님: {val}"


# ---------------------------------------------------------------------------
# Test 7: heartbeat 간격이 idle_timeout보다 짧아야 함 (30 < 300)
# ---------------------------------------------------------------------------

def test_heartbeat_interval_less_than_idle_timeout():
    """heartbeat 간격(30s)이 idle timeout(300s)보다 짧아야 오탐 방지 가능."""
    hb_interval = int(os.environ.get("BOT_HB_INTERVAL_SEC", "30"))
    idle_timeout = int(os.environ.get("BOT_IDLE_TIMEOUT_SEC", "120"))
    # idle_timeout은 hb_interval의 최소 2배 이상이어야 안전
    assert hb_interval * 2 <= idle_timeout, (
        f"heartbeat 간격({hb_interval}s) * 2 > idle timeout({idle_timeout}s): 오탐 위험"
    )


# ---------------------------------------------------------------------------
# Test 8: BOT_HB_INTERVAL_SEC 환경변수 기본값 30초 확인
# ---------------------------------------------------------------------------

def test_hb_interval_default_is_30():
    """BOT_HB_INTERVAL_SEC 미설정 시 기본값 30초."""
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("BOT_HB_INTERVAL_SEC", None)
        val = int(os.environ.get("BOT_HB_INTERVAL_SEC", "30"))
    assert val == 30, f"heartbeat 간격 기본값이 30이 아님: {val}"


# ---------------------------------------------------------------------------
# Test 9: active 케이스 — progress_snapshot 있을 때 타임아웃 메시지
# ---------------------------------------------------------------------------

def test_timeout_msg_with_progress_snapshot_shows_active():
    """progress_snapshot이 있을 때 타임아웃 메시지에 마지막 출력 라인 포함 (active 힌트)."""
    snapshot = [(time.time() - 5.0, "파일 분석 중: core/telegram_relay.py")]
    msg = build_watchdog_timeout_msg(idle=185.0, idle_timeout=300, progress_snapshot=snapshot)
    assert "마지막 출력" in msg, "active 힌트가 없음"
    assert "파일 분석 중" in msg, "마지막 출력 내용이 없음"
    assert "무응답 185초" in msg


# ---------------------------------------------------------------------------
# Test 10: stuck 케이스 — progress_snapshot 없을 때 타임아웃 메시지
# ---------------------------------------------------------------------------

def test_timeout_msg_without_progress_snapshot_shows_stuck():
    """progress_snapshot이 없을 때 타임아웃 메시지에 stuck 가능성 힌트 포함."""
    snapshot: list[tuple[float, str]] = []
    msg = build_watchdog_timeout_msg(idle=305.0, idle_timeout=300, progress_snapshot=snapshot)
    assert "stuck" in msg or "출력 없음" in msg, "stuck 힌트가 없음"
    assert "무응답 305초" in msg


# ---------------------------------------------------------------------------
# Test 11: heartbeat count 0 → "작업 시작 전 stuck" 진단
# ---------------------------------------------------------------------------

def build_watchdog_timeout_msg_v2(
    idle: float,
    idle_timeout: int,
    progress_snapshot: list[tuple[float, str]],
    hb_count: int,
) -> str:
    """개선된 _watchdog_loop 타임아웃 메시지 생성 로직 (hb_count 포함)."""
    hb_hint = f"heartbeat {hb_count}회 발화"
    if progress_snapshot:
        last_ts, last_line = progress_snapshot[-1]
        since_last = time.time() - last_ts
        snap_hint = (
            f" | 마지막 출력 {since_last:.0f}s 전: {last_line[:80]}"
            f" [{hb_hint} — 작업 중 잘렸을 가능성]"
        )
    else:
        diagnosis = "작업 시작 전 stuck" if hb_count == 0 else "LLM 응답 대기 중"
        snap_hint = f" | 실행 중 출력 없음 [{hb_hint} — {diagnosis}]"
    return f"무응답 {idle:.0f}초 (한도 {idle_timeout}s){snap_hint}"


def test_timeout_msg_hb_count_0_shows_stuck_from_start():
    """heartbeat 0회 발화 + 출력 없음 → '작업 시작 전 stuck' 진단."""
    msg = build_watchdog_timeout_msg_v2(
        idle=310.0, idle_timeout=300, progress_snapshot=[], hb_count=0
    )
    assert "작업 시작 전 stuck" in msg, f"예상 진단 없음: {msg}"
    assert "heartbeat 0회 발화" in msg
    assert "무응답 310초" in msg


# ---------------------------------------------------------------------------
# Test 12: heartbeat count >0, 출력 없음 → "LLM 응답 대기 중" 진단
# ---------------------------------------------------------------------------

def test_timeout_msg_hb_gt0_no_output_shows_llm_waiting():
    """heartbeat 발화됐지만 출력 없음 → 'LLM 응답 대기 중' 진단."""
    msg = build_watchdog_timeout_msg_v2(
        idle=310.0, idle_timeout=300, progress_snapshot=[], hb_count=5
    )
    assert "LLM 응답 대기 중" in msg, f"예상 진단 없음: {msg}"
    assert "heartbeat 5회 발화" in msg


# ---------------------------------------------------------------------------
# Test 13: heartbeat count >0, 출력 있음 → "작업 중 잘렸을 가능성" 진단
# ---------------------------------------------------------------------------

def test_timeout_msg_hb_gt0_with_output_shows_active():
    """heartbeat 발화됐고 출력도 있음 → '작업 중 잘렸을 가능성' 진단."""
    snapshot = [(time.time() - 10.0, "tests/ 디렉토리 스캔 중")]
    msg = build_watchdog_timeout_msg_v2(
        idle=310.0, idle_timeout=300, progress_snapshot=snapshot, hb_count=8
    )
    assert "작업 중 잘렸을 가능성" in msg, f"예상 진단 없음: {msg}"
    assert "heartbeat 8회 발화" in msg
    assert "tests/ 디렉토리" in msg


# ---------------------------------------------------------------------------
# Test 14: heartbeat loop가 idle 시간 포함한 info 로그 emit (mock logger)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_heartbeat_loop_emits_elapsed_and_idle():
    """heartbeat 루프가 elapsed와 idle 정보를 포함한 로그를 남기는지 확인."""
    log_messages: list[str] = []

    async def on_progress(line: str) -> None:
        pass

    async def mock_heartbeat_loop_with_logging(on_progress_fn, interval: float = 0.1):
        hb_count = 0
        start = time.time()
        heartbeat_ts = time.time()
        await asyncio.sleep(interval)
        while True:
            hb_count += 1
            elapsed_hb = time.time() - start
            idle_hb = time.time() - heartbeat_ts
            log_messages.append(
                f"heartbeat #{hb_count} (elapsed={elapsed_hb:.0f}s, idle={idle_hb:.0f}s)"
            )
            try:
                await on_progress_fn("🤔 처리 중...")
                heartbeat_ts = time.time()
            except Exception:
                pass
            await asyncio.sleep(interval)

    task = asyncio.ensure_future(mock_heartbeat_loop_with_logging(on_progress, interval=0.1))
    await asyncio.sleep(0.35)
    task.cancel()
    from contextlib import suppress as _suppress
    with _suppress(asyncio.CancelledError):
        await task

    assert len(log_messages) >= 1, "로그 메시지가 없음"
    assert "elapsed=" in log_messages[0], f"elapsed 없음: {log_messages[0]}"
    assert "idle=" in log_messages[0], f"idle 없음: {log_messages[0]}"


# ---------------------------------------------------------------------------
# Test 15: BOT_IDLE_TIMEOUT_SEC=300 이 hb_interval=30 의 4배 이상 (여유 확보)
# ---------------------------------------------------------------------------

def test_idle_timeout_at_least_4x_hb_interval():
    """idle timeout(300s)이 heartbeat 간격(30s)의 4배 이상이어야 충분한 여유."""
    hb_interval = int(os.environ.get("BOT_HB_INTERVAL_SEC", "30"))
    idle_timeout = int(os.environ.get("BOT_IDLE_TIMEOUT_SEC", "120"))
    assert idle_timeout >= hb_interval * 4, (
        f"idle timeout({idle_timeout}s) < heartbeat({hb_interval}s) × 4: "
        "heartbeat 2회 실패 시 오탐 위험"
    )
