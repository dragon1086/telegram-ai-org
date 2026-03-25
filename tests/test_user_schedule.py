"""자연어 스케줄 등록 인터페이스 테스트."""
from __future__ import annotations

import sqlite3
from unittest.mock import AsyncMock

import pytest

# ── NLScheduleParser 테스트 ───────────────────────────────────────────────
from core.nl_schedule_parser import NLScheduleParser, ParseError
from core.scheduler import OrgScheduler
from core.user_schedule_store import UserSchedule, UserScheduleStore


def test_nl_parser_daily_9am():
    parser = NLScheduleParser()
    result = parser.parse("매일 오전 9시에 AI 뉴스 요약해줘")
    assert result["cron_expr"] == "0 9 * * *"
    assert "매일" in result["human_readable"]
    assert "9" in result["human_readable"]
    assert result["confidence"] > 0.8


def test_nl_parser_daily_pm():
    parser = NLScheduleParser()
    result = parser.parse("매일 오후 3시에 팀 리포트 확인")
    assert result["cron_expr"] == "0 15 * * *"
    assert result["confidence"] > 0.8


def test_nl_parser_weekly_monday():
    parser = NLScheduleParser()
    result = parser.parse("매주 월요일 오전 10시에 주간 회의 리포트 요약")
    assert result["cron_expr"] == "0 10 * * 1"
    assert "월요일" in result["human_readable"]
    assert "10" in result["human_readable"]
    assert result["confidence"] > 0.8


def test_nl_parser_weekly_friday():
    parser = NLScheduleParser()
    result = parser.parse("매주 금요일 오후 6시에 주간 회고 작성")
    assert result["cron_expr"] == "0 18 * * 5"
    assert "금요일" in result["human_readable"]


def test_nl_parser_monthly():
    parser = NLScheduleParser()
    result = parser.parse("매달 1일 오전 9시에 월간 보고서 생성")
    assert result["cron_expr"] == "0 9 1 * *"
    assert result["confidence"] > 0.8


def test_nl_parser_monthly_15th():
    parser = NLScheduleParser()
    result = parser.parse("매월 15일 오전 11시에 중간 점검 리포트")
    assert result["cron_expr"] == "0 11 15 * *"


def test_nl_parser_no_frequency_raises():
    """빈도 표현 없이는 ParseError."""
    parser = NLScheduleParser()
    with pytest.raises(ParseError):
        parser.parse("AI 뉴스 요약해줘")  # 시간 표현 없음


def test_nl_parser_task_description_extracted():
    """태스크 설명이 시간/빈도 표현 없이 추출되는지 확인."""
    parser = NLScheduleParser()
    result = parser.parse("매일 오전 9시에 프리즘 채널 AI 뉴스 3개 요약")
    desc = result["task_description"]
    # 태스크 설명에 시간/빈도 표현이 없어야 함
    assert "매일" not in desc
    assert "9시" not in desc
    assert len(desc) > 0


def test_nl_parser_with_minute():
    parser = NLScheduleParser()
    result = parser.parse("매일 오전 9시 30분에 모닝 브리핑")
    assert result["cron_expr"] == "30 9 * * *"


@pytest.fixture
def store(tmp_path):
    db_path = tmp_path / "test_schedules.db"
    return UserScheduleStore(db_path=db_path)


def test_schedule_store_add(store):
    sched = store.add("매일 오전 9시에 AI 뉴스", "0 9 * * *", "AI 뉴스")
    assert sched.id > 0
    assert sched.raw_text == "매일 오전 9시에 AI 뉴스"
    assert sched.cron_expr == "0 9 * * *"
    assert sched.task_description == "AI 뉴스"
    assert sched.enabled is True


def test_schedule_store_list_all(store):
    store.add("매일 오전 9시", "0 9 * * *", "태스크1")
    store.add("매주 월요일", "0 9 * * 1", "태스크2")
    all_scheds = store.list_all()
    assert len(all_scheds) == 2


def test_schedule_store_get_enabled(store):
    store.add("매일 오전 9시", "0 9 * * *", "활성")
    sched2 = store.add("매주 월요일", "0 9 * * 1", "비활성")
    store.disable(sched2.id)
    enabled = store.get_enabled()
    assert len(enabled) == 1
    assert enabled[0].task_description == "활성"


def test_schedule_store_disable(store):
    sched = store.add("매일 오전 9시", "0 9 * * *", "태스크")
    assert store.disable(sched.id) is True
    retrieved = store.get_by_id(sched.id)
    assert retrieved.enabled is False


def test_schedule_store_enable(store):
    sched = store.add("매일 오전 9시", "0 9 * * *", "태스크")
    store.disable(sched.id)
    assert store.enable(sched.id) is True
    retrieved = store.get_by_id(sched.id)
    assert retrieved.enabled is True


def test_schedule_store_delete(store):
    sched = store.add("매일 오전 9시", "0 9 * * *", "태스크")
    assert store.delete(sched.id) is True
    assert store.get_by_id(sched.id) is None
    assert store.delete(sched.id) is False  # 이미 없음


def test_schedule_store_disable_nonexistent(store):
    assert store.disable(9999) is False


def test_schedule_store_wal(store):
    """WAL 모드가 활성화됐는지 확인."""
    with sqlite3.connect(store.db_path) as conn:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode == "wal"


@pytest.fixture
def scheduler():
    send_text = AsyncMock()
    sched = OrgScheduler(send_text=send_text)
    yield sched
    if sched.scheduler.running:
        sched.scheduler.shutdown(wait=False)


def _make_schedule(id: int, cron: str = "0 9 * * *") -> UserSchedule:
    return UserSchedule(
        id=id,
        raw_text="테스트",
        cron_expr=cron,
        task_description="테스트 태스크",
        created_at="2026-01-01T00:00:00",
        enabled=True,
    )


def test_scheduler_dynamic_add(scheduler):
    sched = _make_schedule(1)
    scheduler.add_user_job(sched)
    job = scheduler.scheduler.get_job("user_schedule_1")
    assert job is not None


def test_scheduler_dynamic_remove(scheduler):
    sched = _make_schedule(1)
    scheduler.add_user_job(sched)
    scheduler.remove_user_job(1)
    assert scheduler.scheduler.get_job("user_schedule_1") is None


def test_scheduler_add_replaces_existing(scheduler):
    sched = _make_schedule(1)
    scheduler.add_user_job(sched)
    # 같은 ID로 다시 추가해도 오류 없이 교체
    scheduler.add_user_job(sched)
    jobs = [j for j in scheduler.scheduler.get_jobs() if j.id == "user_schedule_1"]
    assert len(jobs) == 1


def test_scheduler_remove_nonexistent(scheduler):
    # 없는 job 제거 시 오류 없음
    scheduler.remove_user_job(9999)


def test_scheduler_load_from_store(scheduler, tmp_path):
    """load_user_schedules — 활성 스케줄만 복원."""
    store = UserScheduleStore(db_path=tmp_path / "s.db")
    sched1 = store.add("매일 오전 9시", "0 9 * * *", "태스크1")
    sched2 = store.add("매주 월요일", "0 9 * * 1", "태스크2")
    store.disable(sched2.id)  # 비활성

    scheduler.load_user_schedules(store)
    assert scheduler.scheduler.get_job(f"user_schedule_{sched1.id}") is not None
    assert scheduler.scheduler.get_job(f"user_schedule_{sched2.id}") is None


def test_scheduler_existing_jobs_not_affected(scheduler):
    """동적 job 추가 후 기존 고정 job이 유지되는지 확인."""
    original_jobs = set(j.id for j in scheduler.scheduler.get_jobs())
    assert "morning_standup" in original_jobs

    sched = _make_schedule(99)
    scheduler.add_user_job(sched)

    after_jobs = set(j.id for j in scheduler.scheduler.get_jobs())
    # 기존 job 모두 유지
    assert original_jobs.issubset(after_jobs)
    # 새 job 추가됨
    assert "user_schedule_99" in after_jobs
