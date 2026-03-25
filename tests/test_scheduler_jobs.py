"""OrgScheduler 잡 등록 테스트.

ST-11 추가 (2026-03-25):
- weekly_meeting_automation, monthly_audit_automation, weekly_audit_report 잡 등록 검증
- 핸들러 실행 smoke test (stub 출력 확인)
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


@pytest.fixture
def scheduler():
    from core.scheduler import OrgScheduler
    return OrgScheduler(send_text=AsyncMock())


def test_routing_optimizer_job_registered(scheduler):
    """routing_optimizer_daily 잡이 스케줄러에 등록되어 있어야 한다."""
    assert "routing_optimizer_daily" in scheduler.get_job_ids()


# ── ST-11: 신규 자동화 협업 프로세스 잡 등록 검증 ──────────────────────────

def test_weekly_meeting_automation_registered(scheduler):
    """weekly_meeting_automation 잡이 매주 월요일 09:00 KST에 등록돼야 한다."""
    job_ids = scheduler.get_job_ids()
    assert "weekly_meeting_automation" in job_ids, (
        "ST-11 주간회의 자동화 잡(weekly_meeting_automation)이 등록되지 않았습니다"
    )


def test_monthly_audit_automation_registered(scheduler):
    """monthly_audit_automation 잡이 매월 1일 09:30 KST에 등록돼야 한다."""
    job_ids = scheduler.get_job_ids()
    assert "monthly_audit_automation" in job_ids, (
        "ST-11 감사 자동화 잡(monthly_audit_automation)이 등록되지 않았습니다"
    )


def test_weekly_audit_report_registered(scheduler):
    """weekly_audit_report 잡이 매주 금요일 17:00 KST에 등록돼야 한다."""
    job_ids = scheduler.get_job_ids()
    assert "weekly_audit_report" in job_ids, (
        "ST-11 감사 리포트 잡(weekly_audit_report)이 등록되지 않았습니다"
    )


def test_all_st11_jobs_registered(scheduler):
    """ST-11 3개 자동화 잡이 모두 등록돼야 한다."""
    job_ids = scheduler.get_job_ids()
    required = {
        "weekly_meeting_automation",
        "monthly_audit_automation",
        "weekly_audit_report",
    }
    missing = required - set(job_ids)
    assert not missing, f"미등록 ST-11 잡: {missing}"


# ── ST-11: 핸들러 smoke test ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_weekly_meeting_automation_sends_message():
    """_weekly_meeting_automation 핸들러가 Telegram 메시지를 전송해야 한다."""
    send_mock = AsyncMock()
    from core.scheduler import OrgScheduler
    sched = OrgScheduler(send_text=send_mock)

    await sched._weekly_meeting_automation()

    send_mock.assert_called_once()
    call_text = send_mock.call_args[0][0]
    assert "주간회의" in call_text or "weekly" in call_text.lower()


@pytest.mark.asyncio
async def test_monthly_audit_automation_sends_message():
    """_monthly_audit_automation 핸들러가 Telegram 메시지를 전송해야 한다."""
    send_mock = AsyncMock()
    from core.scheduler import OrgScheduler
    sched = OrgScheduler(send_text=send_mock)

    await sched._monthly_audit_automation()

    send_mock.assert_called_once()
    call_text = send_mock.call_args[0][0]
    assert "감사" in call_text or "audit" in call_text.lower()


@pytest.mark.asyncio
async def test_weekly_audit_report_sends_message():
    """_weekly_audit_report 핸들러가 Telegram 메시지를 전송해야 한다."""
    send_mock = AsyncMock()
    from core.scheduler import OrgScheduler
    sched = OrgScheduler(send_text=send_mock)

    await sched._weekly_audit_report()

    send_mock.assert_called_once()
    call_text = send_mock.call_args[0][0]
    assert "리포트" in call_text or "report" in call_text.lower() or "감사" in call_text
