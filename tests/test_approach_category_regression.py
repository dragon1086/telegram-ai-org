"""회귀 테스트: post-task 성공 교훈이 'approach' 카테고리로 하드코딩되지 않아야 함.

버그: telegram_relay.py의 post-task debrief에서 모든 성공 태스크를
category='approach'로 기록해 49-54개의 approach 교훈이 누적됨.
health_report_parser가 이를 에러 패턴으로 탐지 → fix_error_pattern 자동 실행.

근본 원인 1: category="approach" 하드코딩이 잘못된 카테고리임.
'approach'는 잘못된 접근 방식에 쓰는 카테고리; 일반 성공 기록에는 'other' 사용.

근본 원인 2: get_category_stats()가 outcome='success' 레코드까지 집계해
성공 교훈이 에러 패턴 카운트에 포함됨. failure 레코드만 집계해야 함.
"""
from __future__ import annotations

import pathlib
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))


TELEGRAM_RELAY = pathlib.Path(__file__).parent.parent / "core" / "telegram_relay.py"


def test_post_task_debrief_does_not_use_approach_category():
    """post-task debrief의 arecord_success가 category='approach'를 사용하지 않아야 한다."""
    source = TELEGRAM_RELAY.read_text()

    # arecord_success(... category="approach" ...) 패턴 탐지
    pattern = re.compile(
        r'arecord_success\s*\([^)]*category\s*=\s*["\']approach["\']',
        re.DOTALL,
    )
    matches = pattern.findall(source)

    assert not matches, (
        "telegram_relay.py의 arecord_success 호출에 category='approach'가 "
        f"사용됨 ({len(matches)}곳). "
        "'approach'는 잘못된 접근 방식 교훈 전용 카테고리이므로 "
        "일반 태스크 성공 기록에는 'other'를 사용해야 한다."
    )


def test_approach_category_count_in_lesson_memory_schema():
    """lesson_memory.py의 CATEGORIES에 'approach'가 존재하나 적절히 제한된다."""
    lesson_memory = pathlib.Path(__file__).parent.parent / "core" / "lesson_memory.py"
    source = lesson_memory.read_text()
    assert '"approach"' in source, "CATEGORIES에 'approach'는 유지되어야 한다 (유효한 카테고리)"


def test_get_category_stats_excludes_success_records():
    """get_category_stats()는 outcome='failure' 레코드만 집계해야 한다.

    성공 교훈(outcome='success')이 카테고리 통계에 포함되면
    health_report_parser가 이를 에러 패턴으로 오탐한다.
    """
    from core.lesson_memory import LessonMemory

    with tempfile.TemporaryDirectory() as tmp:
        lm = LessonMemory(db_path=Path(tmp) / "test.db")

        # 성공 교훈 3개 기록
        for i in range(3):
            lm.record_success(
                task_description=f"task-{i}",
                category="approach",
                what_went_well="잘 됐음",
                reuse_tip="재사용 팁",
            )

        stats = lm.get_category_stats()

        assert "approach" not in stats, (
            "get_category_stats()가 outcome='success' 레코드를 포함함. "
            "성공 교훈은 에러 패턴 통계에서 제외해야 한다."
        )
