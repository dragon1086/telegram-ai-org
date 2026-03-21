"""Tests for lesson_memory — approach category spam prevention."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.lesson_memory import CATEGORIES, LessonMemory


def test_approach_in_categories():
    """approach is a valid lesson category."""
    assert "approach" in CATEGORIES


def test_record_success_approach_stores_meaningful_lesson():
    """record_success with approach category must store the lesson correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        lm = LessonMemory(db_path=Path(tmpdir) / "test.db")
        lesson = lm.record_success(
            task_description="단계별 분해로 복잡한 LLM 태스크 처리",
            category="approach",
            what_went_well="태스크를 서브태스크로 분해하니 오류율 감소",
            reuse_tip="LLM 응답을 파이프라인으로 연결할 때 유효",
        )
        assert lesson.category == "approach"
        assert lesson.outcome == "success"
        stats = lm.get_category_stats()
        assert stats.get("approach", 0) == 1


def test_no_generic_completion_approach_in_telegram_relay():
    """telegram_relay must NOT record category='approach' for every generic task completion.

    This is a regression test: the pattern 'arecord_success' with category='approach'
    and what_went_well='태스크 ... 정상 완료' (generic) must not exist in the source.
    """
    relay_src = Path("core/telegram_relay.py").read_text(encoding="utf-8")
    # Look for the exact bad pattern: generic success recording with approach category
    bad_pattern = 'category="approach"'
    # If this pattern exists near "정상 완료", that's the bug
    lines = relay_src.splitlines()
    approach_linenos = [
        i + 1
        for i, line in enumerate(lines)
        if bad_pattern in line
    ]
    # Find lines within ±5 of approach lines that mention "정상 완료"
    generic_windows = []
    for lineno in approach_linenos:
        window = lines[max(0, lineno - 6) : lineno + 5]
        if any("정상 완료" in line for line in window):
            generic_windows.append(lineno)

    assert not generic_windows, (
        f"Found generic '정상 완료' task completion recorded as category='approach' "
        f"in telegram_relay.py at lines: {generic_windows}. "
        "Every task completion must NOT be logged as an 'approach' lesson — "
        "only meaningful insights should use this category."
    )
