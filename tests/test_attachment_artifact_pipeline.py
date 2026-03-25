from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.artifact_pipeline import prepare_upload_bundle
from core.attachment_analysis import AttachmentAnalyzer
from core.attachment_manager import AttachmentContext


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


def test_prepare_upload_bundle_returns_source_only(tmp_path: Path) -> None:
    sample = tmp_path / "report.md"
    sample.write_text(
        "# Title\n\nintro\n\n## Section A\n\n- item1\n\n## Section B\n\ntext",
        encoding="utf-8",
    )

    bundle = prepare_upload_bundle(sample)

    assert len(bundle) == 1
    assert bundle[0].name == "report.md"


def test_attachment_bundle_prompt(tmp_path: Path) -> None:
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("alpha", encoding="utf-8")
    b.write_text("beta", encoding="utf-8")
    from core.attachment_manager import AttachmentBundle

    bundle = AttachmentBundle(
        items=[
            AttachmentContext.from_local_file(kind="document", local_path=a, caption="A"),
            AttachmentContext.from_local_file(kind="document", local_path=b, caption="B"),
        ],
        caption="두 파일을 함께 비교해줘",
    )

    prompt = bundle.build_task_prompt()
    assert "총 2개" in prompt
    assert "alpha" in prompt
    assert "beta" in prompt


def test_attachment_analyzer_bridge(monkeypatch, tmp_path: Path) -> None:
    image = tmp_path / "image.jpg"
    image.write_bytes(b"fake")
    AttachmentContext.from_local_file(
        kind="photo",
        local_path=image,
        caption="img",
        mime_type="image/jpeg",
    )
    analyzer = AttachmentAnalyzer()

    class _Proc:
        returncode = 0
        stdout = "bridge summary"

    monkeypatch.setenv("ATTACHMENT_VISION_BRIDGE_CMD", "/usr/bin/printf")
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: _Proc())

    summary = analyzer._analyze_image_with_bridge(image, "image/jpeg")

    assert summary == "bridge summary"


def test_attachment_analyzer_multimodal_bridge(monkeypatch, tmp_path: Path) -> None:
    audio = tmp_path / "voice.ogg"
    audio.write_bytes(b"fake")
    analyzer = AttachmentAnalyzer()

    class _Proc:
        returncode = 0
        stdout = "audio summary"

    monkeypatch.setenv("ATTACHMENT_MULTIMODAL_BRIDGE_CMD", "/usr/bin/printf")
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: _Proc())

    summary = analyzer._analyze_media_with_bridge(audio, "audio/ogg")

    assert summary == "audio summary"
