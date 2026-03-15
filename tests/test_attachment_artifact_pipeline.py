from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.attachment_manager import AttachmentContext
from core.artifact_pipeline import prepare_upload_bundle


def test_attachment_context_includes_preview(tmp_path: Path) -> None:
    sample = tmp_path / "report.md"
    sample.write_text("# Title\n\nhello world", encoding="utf-8")

    ctx = AttachmentContext.from_local_file(
        kind="document",
        local_path=sample,
        caption="이 문서를 요약해줘",
        original_filename="report.md",
        mime_type="text/markdown",
    )

    prompt = ctx.build_task_prompt()
    assert "첨부 입력" in prompt
    assert "report.md" in prompt
    assert "hello world" in prompt


def test_prepare_upload_bundle_generates_html_and_slides(tmp_path: Path) -> None:
    sample = tmp_path / "report.md"
    sample.write_text(
        "# Title\n\nintro\n\n## Section A\n\n- item1\n\n## Section B\n\ntext",
        encoding="utf-8",
    )

    bundle = prepare_upload_bundle(sample)
    names = [path.name for path in bundle]

    assert "report.md" in names
    assert "report.telegram-preview.html" in names
    assert "report.telegram-slides.html" in names
