"""Phase 2 — 기억·성격·회의 강화 테스트."""
from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path



# ── LessonMemory 테스트 ───────────────────────────────────────────────────

def test_lesson_memory_record_and_retrieve():
    """교훈 기록 후 관련 교훈 검색."""
    from core.lesson_memory import LessonMemory
    with tempfile.TemporaryDirectory() as tmpdir:
        lm = LessonMemory(db_path=Path(tmpdir) / "test.db")
        lesson = lm.record(
            task_description="Python API timeout test",
            category="timeout",
            what_went_wrong="API call timed out after 30s",
            how_to_prevent="Set timeout=10s and add retry logic",
            worker="aiorg_engineering_bot",
        )
        assert lesson.id
        assert lesson.category == "timeout"

        # 관련 교훈 검색
        results = lm.get_relevant("Python API timeout issue")
        assert len(results) >= 1
        assert results[0].category == "timeout"


def test_lesson_memory_category_stats():
    """카테고리별 통계 집계."""
    from core.lesson_memory import LessonMemory
    with tempfile.TemporaryDirectory() as tmpdir:
        lm = LessonMemory(db_path=Path(tmpdir) / "test.db")
        lm.record("task1", "timeout", "timed out", "add retry")
        lm.record("task2", "timeout", "timed out again", "shorter timeout")
        lm.record("task3", "api_failure", "api down", "fallback needed")

        stats = lm.get_category_stats()
        assert stats.get("timeout", 0) == 2
        assert stats.get("api_failure", 0) == 1


def test_lesson_memory_mark_resolved():
    """교훈 해결 처리."""
    from core.lesson_memory import LessonMemory
    with tempfile.TemporaryDirectory() as tmpdir:
        lm = LessonMemory(db_path=Path(tmpdir) / "test.db")
        lesson = lm.record("task", "logic_error", "wrong logic", "fix logic")
        lm.mark_resolved(lesson.id)

        # resolved 교훈은 get_relevant에서 제외
        results = lm.get_relevant("wrong logic task")
        assert len(results) == 0


# ── RetroMemory 테스트 ────────────────────────────────────────────────────

def test_retro_memory_save_and_report():
    """일일 회고 저장 + 주간 리포트 생성."""
    from core.retro_memory import RetroMemory, RetroEntry
    with tempfile.TemporaryDirectory() as tmpdir:
        rm = RetroMemory(db_path=Path(tmpdir) / "retro.db")

        # 현재 주 엔트리 3개 저장
        today = date.today()
        for i in range(3):
            rm.save_daily(RetroEntry(
                date=today.isoformat(),
                best_thing=f"오늘 {8+i}건 완료",
                failure_summary="1건 실패",
                experiment="새 접근법 시도",
                task_count=9 + i,
                success_count=8 + i,
            ))

        report = rm.generate_weekly_report()
        assert report.period  # e.g. "2026-W11"
        assert 0.0 <= report.avg_success_rate <= 1.0
        assert isinstance(report.achievements, list)
        assert isinstance(report.action_items, list)
        assert len(report.action_items) >= 1

        # Telegram 포맷 확인
        msg = rm.format_telegram(report)
        assert "주간 회고" in msg or "리포트" in msg


def test_retro_memory_week_entries():
    """주간 엔트리 조회."""
    from core.retro_memory import RetroMemory, RetroEntry
    with tempfile.TemporaryDirectory() as tmpdir:
        rm = RetroMemory(db_path=Path(tmpdir) / "retro.db")
        today = date.today()
        rm.save_daily(RetroEntry(
            date=today.isoformat(),
            best_thing="테스트 통과",
            failure_summary="없음",
            experiment="새 기능",
            task_count=5,
            success_count=5,
        ))
        entries = rm.get_week_entries()
        assert len(entries) >= 1


# ── weekly_standup 테스트 ─────────────────────────────────────────────────

def test_weekly_standup_has_new_sections():
    """weekly_standup 메시지에 새 섹션 포함 여부."""
    from scripts.weekly_standup import build_standup_message

    tasks = [
        {"assigned_dept": "aiorg_engineering_bot", "description": "API 구현", "status": "completed"},
        {"assigned_dept": "aiorg_engineering_bot", "description": "버그 수정", "status": "completed"},
        {"assigned_dept": "aiorg_pm_bot", "description": "일정 관리", "status": "completed"},
    ]
    tg_msg, md_content = build_standup_message(tasks, [])

    # 기존 섹션
    assert "주간 회의" in tg_msg

    # 새 섹션 — MVP, 실패 패턴, 목표 중 하나 이상 있어야 함
    has_new_sections = any(s in tg_msg for s in ["MVP", "실패 패턴", "목표", "이번 주"])
    assert has_new_sections, f"새 섹션 없음. 메시지: {tg_msg[:200]}"


# ── agent_catalog personality 테스트 ─────────────────────────────────────

def test_bot_personality_loaded():
    """agent_catalog에서 봇 personality 필드 로드 여부."""
    from core.agent_catalog import AgentCatalog
    bots_dir = Path(__file__).parent.parent / "bots"
    catalog = AgentCatalog()
    catalog.load_bot_yamls(bots_dir)

    personas = catalog.list_agents()
    # 최소 1개 봇에 personality 필드가 있어야 함
    with_personality = [p for p in personas if p.personality]
    assert len(with_personality) >= 1, "personality 필드가 있는 봇이 없음"
