from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from core.telegram_user_guardrail import (
    ensure_user_friendly_output,
    extract_local_artifact_paths,
    extract_local_artifact_names,
    is_already_structured_report,
    needs_rewrite_for_telegram,
)


def test_extract_local_artifact_names() -> None:
    text = "결과는 /tmp/report.md 와 ~/work/output/slides.html 에 있습니다."
    names = extract_local_artifact_names(text)
    assert names == ["report.md", "slides.html"]


def test_extract_local_artifact_paths_includes_markers() -> None:
    text = "[ARTIFACT:/tmp/report.md]\n결과는 ~/work/output/slides.html 에 있습니다."
    paths = extract_local_artifact_paths(text)
    assert paths == ["/tmp/report.md", "~/work/output/slides.html"]


def test_needs_rewrite_for_path_heavy_output() -> None:
    text = "/tmp/report.md\n/Users/rocky/telegram-ai-org/.omx/reports/foo.md"
    assert needs_rewrite_for_telegram(text) is True


@pytest.mark.asyncio
async def test_ensure_user_friendly_output_removes_local_paths() -> None:
    text = "최종 정리는 /tmp/report.md 를 보고 ~/work/slides.html 를 참고하세요."
    cleaned = await ensure_user_friendly_output(text, original_request="요약해줘")
    assert "/tmp/report.md" not in cleaned
    assert "slides.html" in cleaned
    assert "첨부 산출물" in cleaned


@pytest.mark.asyncio
async def test_ensure_user_friendly_output_removes_artifact_markers() -> None:
    text = "통합 보고서를 보냈습니다.\n[ARTIFACT:/tmp/report.md]"
    cleaned = await ensure_user_friendly_output(text, original_request="정리해줘")
    assert "[ARTIFACT:" not in cleaned
    assert "report.md" in cleaned


@pytest.mark.asyncio
async def test_ensure_user_friendly_output_strips_team_tag() -> None:
    """[TEAM:...] 메타 태그가 최종 사용자 출력에서 제거되어야 한다."""
    text = "[TEAM:executor,analyst]\n\n💬 PM 직접 답변\n\n결론: HTML parse_mode를 사용합니다."
    cleaned = await ensure_user_friendly_output(text, original_request="포맷 수정해줘")
    assert "[TEAM:" not in cleaned
    assert "PM 직접 답변" in cleaned


@pytest.mark.asyncio
async def test_ensure_user_friendly_output_strips_collab_tag() -> None:
    """[COLLAB:...] 메타 태그가 최종 사용자 출력에서 제거되어야 한다."""
    text = "작업 완료.\n[COLLAB:디자인 작업 필요|맥락: 현재 개발 중]\n이상입니다."
    cleaned = await ensure_user_friendly_output(text, original_request="완료 보고")
    assert "[COLLAB:" not in cleaned
    assert "작업 완료" in cleaned


@pytest.mark.asyncio
async def test_ensure_user_friendly_output_strips_solo_tag() -> None:
    """[SOLO] 태그가 최종 출력에서 제거되어야 한다."""
    text = "[TEAM:solo]\n\n안녕하세요! 무엇을 도와드릴까요?"
    cleaned = await ensure_user_friendly_output(text, original_request="인사")
    assert "[TEAM:" not in cleaned
    assert "안녕하세요" in cleaned


# ── 구조화된 보고서 감지 테스트 ──────────────────────────────────────────────

def test_is_already_structured_report_detects_결론_section() -> None:
    """## 결론으로 시작하는 보고서는 이미 구조화된 것으로 감지해야 한다."""
    text = "## 결론\n배포 자동화 구축 완료, 즉시 적용 권고.\n\n## 핵심 내용\n- 커밋 3건 반영됨"
    assert is_already_structured_report(text) is True


def test_is_already_structured_report_false_for_raw_output() -> None:
    """일반 텍스트(비구조화) 보고서는 False를 반환해야 한다."""
    text = "개발실 결과: 배포 완료.\n기획실 결과: 계획 수립됨."
    assert is_already_structured_report(text) is False


def test_is_already_structured_report_middle_결론() -> None:
    """## 결론 이 중간에 있어도 구조화된 것으로 감지."""
    text = "요약:\n## 결론\n작업 완료."
    assert is_already_structured_report(text) is True


@pytest.mark.asyncio
async def test_ensure_user_friendly_output_skips_rewrite_for_structured_report() -> None:
    """이미 구조화된(## 결론) 보고서는 full_context 없으면 LLM 재작성을 건너뛴다."""
    structured = "## 결론\n배포 자동화 완료, P1 적용 권고.\n\n## 핵심 내용\n- 코드 3파일 수정\n- 테스트 통과"

    call_count = 0

    class _TrackingClient:
        async def complete(self, prompt: str) -> str:
            nonlocal call_count
            call_count += 1
            return "rewritten"

    # full_context 없음 → LLM 호출 없어야 함
    result = await ensure_user_friendly_output(
        structured,
        original_request="배포해줘",
        full_context="",
        decision_client=_TrackingClient(),  # type: ignore[arg-type]
    )
    assert call_count == 0, "구조화된 보고서는 LLM 재작성 없어야 함"
    assert "## 결론" in result


@pytest.mark.asyncio
async def test_ensure_user_friendly_output_rewrites_when_full_context_given() -> None:
    """full_context가 있으면(합성 fallback) 구조화된 보고서도 재작성해야 한다."""
    structured = "## 결론\n일단 완료.\n\n## 핵심 내용\n- 항목 A"

    class _FixedClient:
        async def complete(self, prompt: str) -> str:
            return "## 결론\n재작성 완료.\n\n## 핵심 내용\n- 더 풍부한 항목"

    result = await ensure_user_friendly_output(
        structured,
        original_request="분석해줘",
        full_context="개발실: 코드 배포 완료. 기획실: 계획 수립 완료.",
        decision_client=_FixedClient(),  # type: ignore[arg-type]
    )
    assert "재작성 완료" in result
