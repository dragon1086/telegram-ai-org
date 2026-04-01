"""재작업 follow-up 프롬프트 압축 회귀 방지 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.pm_synthesis_mixin import PMSynthesisMixin


def test_narrow_rework_scope_limits_phase_count():
    original = """
    [보완 필요] RETRO-31/32 구현 전체 재수행

    === Phase 1: 분석 및 설계 ===
    criteria.yaml과 severity 매핑 규칙을 검토한다.
    edge case를 모두 정리한다.

    === Phase 2: 구현 ===
    UI severity 자동 결정 로직을 구현한다.
    접근성 가이드라인 문서를 함께 작성한다.

    === Phase 3: 테스트 및 검증 ===
    회귀 테스트와 E2E 결과를 정리한다.
    """

    narrowed = PMSynthesisMixin._narrow_rework_scope(original)

    assert "[보완 필요]" not in narrowed
    assert "Phase 1" in narrowed
    assert "Phase 2" in narrowed
    assert "Phase 3" not in narrowed
    assert len(narrowed) <= 360


def test_build_rework_follow_up_description_preserves_scope_but_not_full_brief():
    subtask = {
        "description": "fallback",
        "result": "초안은 작성했지만 근거 표와 회귀 검증이 빠졌습니다.",
        "metadata": {
            "original_description": """
            [보완 필요] Phase 3 — 대시보드 프론트엔드 구현: 만화 캐릭터 컨셉 UI를 백엔드 API에 연동,
            실시간 시각화(애니메이션·상태 변화 표현) 완성 및 E2E 동작 검증

            === Phase 1: 구현 ===
            백엔드 API 연동

            === Phase 2: 시각화 ===
            애니메이션 및 상태 변화

            === Phase 3: 검증 ===
            E2E 동작 검증
            """,
            "task_type": "구현",
            "allow_file_change": True,
        },
    }

    follow_up = PMSynthesisMixin._build_rework_follow_up_description(subtask)

    assert "태스크 유형 유지: 구현" in follow_up
    assert "가장 중요한 누락 산출물 1개" in follow_up
    assert "Phase 3" not in follow_up
    assert "초안은 작성했지만 근거 표와 회귀 검증이 빠졌습니다." in follow_up
    assert len(follow_up) < 800
