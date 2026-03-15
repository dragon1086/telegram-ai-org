"""산출물 파일을 텔레그램 전달용 번들로 재가공한다."""
from __future__ import annotations

import html
from pathlib import Path


_TEXTISH_SUFFIXES = {".md", ".txt"}


def prepare_upload_bundle(path: str | Path) -> list[Path]:
    source = Path(path).expanduser().resolve()
    if not source.exists() or not source.is_file():
        return []

    bundle: list[Path] = [source]
    if source.suffix.lower() in _TEXTISH_SUFFIXES:
        html_path = _render_html_preview(source)
        if html_path is not None:
            bundle.append(html_path)
        slides_path = _render_slide_html(source)
        if slides_path is not None:
            bundle.append(slides_path)
    return bundle


def _render_html_preview(source: Path) -> Path | None:
    text = source.read_text(encoding="utf-8", errors="replace")
    target = source.with_name(f"{source.stem}.telegram-preview.html")
    body = _markdownish_to_html(text)
    target.write_text(
        (
            "<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{html.escape(source.name)}</title>"
            "<style>body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
            "max-width:880px;margin:40px auto;padding:0 20px;line-height:1.6;color:#10243e}"
            "pre{background:#f5f7fa;padding:12px;border-radius:8px;overflow:auto}"
            "code{background:#f5f7fa;padding:2px 4px;border-radius:4px}"
            "h1,h2,h3{color:#0b3b68} li{margin:6px 0}</style></head><body>"
            f"{body}</body></html>"
        ),
        encoding="utf-8",
    )
    return target


def _render_slide_html(source: Path) -> Path | None:
    text = source.read_text(encoding="utf-8", errors="replace")
    sections = _split_sections(text)
    if len(sections) < 2:
        return None
    target = source.with_name(f"{source.stem}.telegram-slides.html")
    slides = []
    for title, content in sections:
        rendered = _markdownish_to_html(content)
        slides.append(
            "<section class='slide'>"
            f"<h1>{html.escape(title)}</h1>{rendered}</section>"
        )
    target.write_text(
        (
            "<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{html.escape(source.name)} slides</title>"
            "<style>body{margin:0;background:#f4f7fb;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}"
            ".deck{display:grid;gap:24px;padding:24px}.slide{background:white;border-radius:20px;"
            "padding:48px;min-height:540px;box-shadow:0 12px 40px rgba(16,36,62,.08)}"
            "h1{margin-top:0;color:#0b3b68} li{margin:8px 0} pre{background:#f5f7fa;padding:12px;border-radius:8px}"
            "</style></head><body><main class='deck'>"
            f"{''.join(slides)}</main></body></html>"
        ),
        encoding="utf-8",
    )
    return target


def _split_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title = "Overview"
    current_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if current_lines:
                sections.append((current_title, "\n".join(current_lines).strip()))
                current_lines = []
            current_title = stripped.lstrip("#").strip() or current_title
            continue
        current_lines.append(line)
    if current_lines:
        sections.append((current_title, "\n".join(current_lines).strip()))
    return [(title, body) for title, body in sections if body]


def _markdownish_to_html(text: str) -> str:
    lines = text.splitlines()
    parts: list[str] = []
    in_list = False
    in_code = False
    code_lines: list[str] = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            parts.append("</ul>")
            in_list = False

    def close_code() -> None:
        nonlocal in_code, code_lines
        if in_code:
            parts.append(f"<pre><code>{html.escape(chr(10).join(code_lines))}</code></pre>")
            in_code = False
            code_lines = []

    for raw in lines:
        stripped = raw.rstrip()
        marker = stripped.strip()
        if marker.startswith("```"):
            close_list()
            if in_code:
                close_code()
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(stripped)
            continue
        if not marker:
            close_list()
            continue
        if marker.startswith("# "):
            close_list()
            parts.append(f"<h1>{html.escape(marker[2:].strip())}</h1>")
            continue
        if marker.startswith("## "):
            close_list()
            parts.append(f"<h2>{html.escape(marker[3:].strip())}</h2>")
            continue
        if marker.startswith("### "):
            close_list()
            parts.append(f"<h3>{html.escape(marker[4:].strip())}</h3>")
            continue
        if marker.startswith(("- ", "* ", "• ")):
            if not in_list:
                parts.append("<ul>")
                in_list = True
            parts.append(f"<li>{html.escape(marker[2:].strip())}</li>")
            continue
        close_list()
        parts.append(f"<p>{html.escape(marker)}</p>")

    close_list()
    close_code()
    return "".join(parts)
