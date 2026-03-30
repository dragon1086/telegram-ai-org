"""
RETRO-02: ENV_DEBUG_GUIDE.md 참조 파일 존재 검증 테스트

이 테스트는 docs/ENV_DEBUG_GUIDE.md 가 참조하는 모든 파일/디렉토리가
실제로 존재하는지 확인합니다.
가이드 내용이 현실과 어긋나지 않도록 "문서 정합성"을 보장합니다.
"""
import os
import pytest

# 프로젝트 루트 기준 경로
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))


def _path(*parts: str) -> str:
    return os.path.join(PROJECT_ROOT, *parts)


# -------------------------------------------------------------------
# 1) 가이드 본문이 참조하는 파일/디렉토리 존재 확인
# -------------------------------------------------------------------

@pytest.mark.parametrize("rel_path, description", [
    ("docs/ENV_DEBUG_GUIDE.md",           "디버깅 가이드 본체"),
    ("scripts/preflight_check.sh",        "Bash pre-flight 스크립트 (RETRO-01)"),
    ("scripts/preflight_check.py",        "Python pre-flight 스크립트 (JSON 출력)"),
    ("infra-baseline.yaml",               "인프라 기준 파라미터 명세"),
    ("docs/pre_flight_checklist.md",      "Pre-flight 상세 절차서"),
    ("docs/env_isolation_debug_guide.md", "증상별 심층 디버깅 트리"),
    ("core/env_guard.py",                 "런타임 환경변수 가드"),
    ("docs/lessons_learned",              "장애 기록 디렉토리"),
])
def test_referenced_file_exists(rel_path: str, description: str):
    """ENV_DEBUG_GUIDE.md 가 참조하는 파일/디렉토리가 실제로 존재해야 한다."""
    full_path = _path(rel_path)
    assert os.path.exists(full_path), (
        f"[RETRO-02] 가이드 참조 파일 누락: {rel_path}\n"
        f"  설명: {description}\n"
        f"  전체 경로: {full_path}"
    )


# -------------------------------------------------------------------
# 2) 가이드 문서 구조(섹션) 존재 확인
# -------------------------------------------------------------------

REQUIRED_SECTIONS = [
    "## 1. 개요",
    "## 2. 환경 격리 절차",
    "## 3. 이분 판단 체크포인트",
    "## 4. 코드 문제 시그니처 예시",
    "## 5. 인프라 문제 시그니처 예시",
    "## 6. 팀 공유 절차",
    "## 빠른 참조",
]


def test_env_debug_guide_sections():
    """ENV_DEBUG_GUIDE.md 가 6개 필수 섹션을 모두 포함해야 한다."""
    guide_path = _path("docs/ENV_DEBUG_GUIDE.md")
    assert os.path.exists(guide_path), "ENV_DEBUG_GUIDE.md 파일 없음"

    content = open(guide_path, encoding="utf-8").read()
    missing = [s for s in REQUIRED_SECTIONS if s not in content]
    assert not missing, (
        f"[RETRO-02] 필수 섹션 누락: {missing}\n"
        f"  파일: {guide_path}"
    )


# -------------------------------------------------------------------
# 3) infra-baseline.yaml 필수 필드 존재 확인
# -------------------------------------------------------------------

def test_infra_baseline_has_required_fields():
    """infra-baseline.yaml 에 timeout 필드가 있어야 한다."""
    baseline_path = _path("infra-baseline.yaml")
    assert os.path.exists(baseline_path), "infra-baseline.yaml 없음"

    content = open(baseline_path, encoding="utf-8").read()
    assert "timeout:" in content, (
        "[RETRO-02] infra-baseline.yaml 에 timeout 필드 없음 — "
        "가이드 Q3 체크포인트가 이 필드를 참조함"
    )


def test_infra_baseline_timeout_sufficient():
    """infra-baseline.yaml 의 timeout 이 60 초과여야 한다 (Q3 체크포인트)."""
    import re
    baseline_path = _path("infra-baseline.yaml")
    content = open(baseline_path, encoding="utf-8").read()

    match = re.search(r"^timeout\s*:\s*(\d+)", content, re.MULTILINE)
    assert match, "timeout 필드 파싱 실패"

    timeout_val = int(match.group(1))
    assert timeout_val > 60, (
        f"[RETRO-02] timeout={timeout_val} — 60 이하면 S-P1 타임아웃 재발 위험\n"
        "  권장값: 120 이상 (가이드 Q3 기준)"
    )


# -------------------------------------------------------------------
# 4) lessons_learned 디렉토리에 최소 1개 기록 존재 확인
# -------------------------------------------------------------------

def test_lessons_learned_has_at_least_one_entry():
    """docs/lessons_learned/ 에 최소 1개의 장애 기록 파일이 있어야 한다."""
    ll_dir = _path("docs/lessons_learned")
    assert os.path.isdir(ll_dir), "docs/lessons_learned 디렉토리 없음"

    entries = [f for f in os.listdir(ll_dir) if f.endswith(".md")]
    assert len(entries) >= 1, (
        "[RETRO-02] docs/lessons_learned/ 에 장애 기록 없음 — "
        "첫 번째 사례(2026-03-26_e2e_timeout_s-p1.md)를 추가하세요"
    )
