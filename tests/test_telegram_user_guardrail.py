from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from core.telegram_user_guardrail import (
    ensure_user_friendly_output,
    extract_local_artifact_names,
    needs_rewrite_for_telegram,
)


def test_extract_local_artifact_names() -> None:
    text = "결과는 /tmp/report.md 와 ~/work/output/slides.html 에 있습니다."
    names = extract_local_artifact_names(text)
    assert names == ["report.md", "slides.html"]


def test_needs_rewrite_for_path_heavy_output() -> None:
    text = "/tmp/report.md\n/Users/rocky/telegram-ai-org/.omx/reports/foo.md"
    assert needs_rewrite_for_telegram(text) is True


@pytest.mark.asyncio
async def test_ensure_user_friendly_output_removes_local_paths() -> None:
    text = "최종 정리는 /tmp/report.md 를 보고 ~/work/slides.html 를 참고하세요."
    cleaned = await ensure_user_friendly_output(text, original_request="요약해줘")
    assert "/tmp/report.md" not in cleaned
    assert "slides.html" in cleaned
    assert "첨부 예정 산출물" in cleaned
