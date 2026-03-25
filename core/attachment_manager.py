"""텔레그램 첨부 입력을 LLM 친화적인 컨텍스트로 정리한다."""
from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path

_TEXT_PREVIEW_SUFFIXES = {
    ".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".tsv",
    ".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".sql",
    ".xml", ".log",
}


@dataclass
class AttachmentContext:
    kind: str
    local_path: Path
    caption: str
    original_filename: str
    mime_type: str
    size_bytes: int
    preview_text: str = ""
    analysis_text: str = ""

    @classmethod
    def from_local_file(
        cls,
        *,
        kind: str,
        local_path: str | Path,
        caption: str,
        original_filename: str = "",
        mime_type: str = "",
    ) -> "AttachmentContext":
        path = Path(local_path).expanduser().resolve()
        inferred_mime, _ = mimetypes.guess_type(path.name)
        mime = mime_type or inferred_mime or "application/octet-stream"
        preview = _read_preview(path)
        return cls(
            kind=kind,
            local_path=path,
            caption=caption.strip(),
            original_filename=original_filename or path.name,
            mime_type=mime,
            size_bytes=path.stat().st_size if path.exists() else 0,
            preview_text=preview,
        )

    def build_task_prompt(self) -> str:
        lines = [
            self.caption or "첨부파일을 분석해줘",
            "",
            "[첨부 입력]",
            f"- 종류: {self.kind}",
            f"- 파일명: {self.original_filename}",
            f"- MIME: {self.mime_type}",
            f"- 크기(bytes): {self.size_bytes}",
            f"- 로컬 경로: {self.local_path}",
        ]
        if self.preview_text:
            lines.extend([
                "",
                "[첨부 미리보기]",
                self.preview_text,
            ])
        if self.analysis_text:
            lines.extend([
                "",
                "[첨부 해석 요약]",
                self.analysis_text,
            ])
        elif self.kind == "photo":
            lines.extend([
                "",
                "[첨부 해석 지침]",
                "이 첨부는 이미지다. 로컬 파일을 직접 읽거나 비전/이미지 처리 수단을 우선 활용해 분석하라.",
            ])
        else:
            lines.extend([
                "",
                "[첨부 해석 지침]",
                "로컬 파일을 직접 읽어 실제 내용을 기준으로 작업하라. 경로 문자열만 보고 추정하지 마라.",
            ])
        return "\n".join(lines).strip()


@dataclass
class AttachmentBundle:
    items: list[AttachmentContext]
    caption: str = ""

    def build_task_prompt(self) -> str:
        headline = self.caption.strip() or "첨부 묶음을 함께 분석해줘"
        parts = [
            headline,
            "",
            f"[첨부 묶음] 총 {len(self.items)}개",
        ]
        for index, item in enumerate(self.items, start=1):
            parts.extend([
                "",
                f"=== 첨부 {index} ===",
                item.build_task_prompt(),
            ])
        return "\n".join(parts).strip()


def _read_preview(path: Path, max_chars: int = 1500) -> str:
    if not path.exists() or not path.is_file():
        return ""
    if path.suffix.lower() not in _TEXT_PREVIEW_SUFFIXES:
        return ""
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    text = raw.strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n..."
    return text
