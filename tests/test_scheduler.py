"""OrgScheduler 단위 테스트."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from core.scheduler import OrgScheduler


@pytest.fixture
def send_text_mock() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def scheduler(send_text_mock: AsyncMock) -> OrgScheduler:
    return OrgScheduler(send_text=send_text_mock)


# ── 잡 등록 테스트 ────────────────────────────────────────────────────────────

def test_scheduler_jobs_registered(scheduler: OrgScheduler) -> None:
    """5개 잡이 정상 등록되는지 확인."""
    job_ids = scheduler.get_job_ids()
    assert "morning_standup" in job_ids
    assert "daily_retro" in job_ids
    assert "weekly_standup" in job_ids
    assert "friday_retro" in job_ids
    assert "conversation_cleanup" in job_ids
    assert len(job_ids) == 5


# ── 잡 실행 크래시 테스트 ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_morning_standup_no_crash(scheduler: OrgScheduler) -> None:
    """morning_standup() 호출 시 크래시 없는지 확인 (스크립트 mock)."""
    mock_main = AsyncMock()
    with patch("scripts.morning_goals.main", mock_main):
        await scheduler.morning_standup()
    mock_main.assert_awaited_once()


@pytest.mark.asyncio
async def test_daily_retro_no_crash(scheduler: OrgScheduler) -> None:
    """daily_retro() 호출 시 크래시 없는지 확인 (스크립트 mock)."""
    mock_main = AsyncMock()
    with patch("scripts.daily_retro.main", mock_main):
        await scheduler.daily_retro()
    mock_main.assert_awaited_once()


# ── 오류 복원력 테스트 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_morning_standup_error_sends_notification(
    scheduler: OrgScheduler, send_text_mock: AsyncMock
) -> None:
    """스크립트 오류 시 Telegram 오류 알림이 전송되는지 확인."""
    with patch("scripts.morning_goals.main", side_effect=RuntimeError("test error")):
        await scheduler.morning_standup()
    # 오류 알림이 전송됐는지 확인
    send_text_mock.assert_awaited_once()
    call_text = send_text_mock.call_args[0][0]
    assert "오류" in call_text or "error" in call_text.lower()


# ── 라이프사이클 테스트 ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_scheduler_start_stop(scheduler: OrgScheduler) -> None:
    """start/stop 이 정상 작동하는지 확인."""
    assert not scheduler.scheduler.running
    scheduler.start()
    assert scheduler.scheduler.running
    scheduler.stop()
    # AsyncIOScheduler shutdown은 비동기 처리 — 이벤트 루프 한 틱 양보
    await asyncio.sleep(0)
    assert not scheduler.scheduler.running


@pytest.mark.asyncio
async def test_scheduler_start_idempotent(scheduler: OrgScheduler) -> None:
    """start를 두 번 호출해도 오류 없는지 확인."""
    scheduler.start()
    scheduler.start()  # 두 번째 호출은 no-op
    assert scheduler.scheduler.running
    scheduler.stop()
