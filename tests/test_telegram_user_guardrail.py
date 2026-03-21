from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from core.telegram_user_guardrail import (
    ensure_user_friendly_output,
    extract_local_artifact_paths,
    extract_local_artifact_names,
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
