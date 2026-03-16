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
    slides_html = []
    for i, (title, content) in enumerate(sections):
        rendered = _markdownish_to_html(content)
        slides_html.append(
            f"<div class='slide' id='s{i}'>"
            f"<div class='slide-num'>{i + 1} / {len(sections)}</div>"
            f"<h1>{html.escape(title)}</h1>"
            f"<div class='slide-body'>{rendered}</div>"
            "</div>"
        )
    target.write_text(
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
        f"<title>{html.escape(source.stem)}</title>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<style>"
        "*{box-sizing:border-box;margin:0;padding:0}"
        "body{background:#0f172a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
        "height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;"
        "color:#f1f5f9}"
        ".slide{display:none;width:min(900px,96vw);min-height:500px;background:linear-gradient(135deg,#1e293b 0%,#0f172a 100%);"
        "border:1px solid rgba(99,179,237,.2);border-radius:24px;padding:56px 64px;"
        "box-shadow:0 32px 80px rgba(0,0,0,.5);position:relative;animation:fadein .3s ease}"
        ".slide.active{display:flex;flex-direction:column;gap:24px}"
        "@keyframes fadein{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}"
        ".slide-num{position:absolute;top:20px;right:28px;font-size:13px;color:#64748b;letter-spacing:.05em}"
        ".slide h1{font-size:clamp(22px,3vw,32px);font-weight:700;color:#7dd3fc;"
        "border-bottom:2px solid rgba(99,179,237,.25);padding-bottom:16px;line-height:1.3}"
        ".slide-body{flex:1;overflow:auto;font-size:clamp(14px,1.8vw,17px);line-height:1.75;color:#cbd5e1}"
        ".slide-body h2{color:#38bdf8;font-size:1.2em;margin:16px 0 8px}"
        ".slide-body h3{color:#7dd3fc;font-size:1.05em;margin:14px 0 6px}"
        ".slide-body ul{padding-left:1.4em}.slide-body li{margin:6px 0;color:#e2e8f0}"
        ".slide-body p{margin:8px 0}"
        ".slide-body pre{background:#020617;border:1px solid #1e293b;border-radius:10px;"
        "padding:14px 16px;overflow:auto;font-size:.85em;color:#a5f3fc}"
        ".slide-body strong,.slide-body b{color:#f8fafc;font-weight:600}"
        ".nav{display:flex;align-items:center;gap:16px;margin-top:20px}"
        ".nav button{background:rgba(99,179,237,.15);border:1px solid rgba(99,179,237,.3);"
        "color:#7dd3fc;font-size:20px;width:44px;height:44px;border-radius:50%;cursor:pointer;"
        "transition:all .15s;display:flex;align-items:center;justify-content:center}"
        ".nav button:hover{background:rgba(99,179,237,.3);transform:scale(1.1)}"
        ".nav button:disabled{opacity:.25;cursor:default;transform:none}"
        ".progress{height:3px;background:rgba(99,179,237,.15);border-radius:2px;width:200px}"
        ".progress-bar{height:100%;background:linear-gradient(90deg,#38bdf8,#818cf8);border-radius:2px;"
        "transition:width .3s ease}"
        "</style></head><body>"
        f"{''.join(slides_html)}"
        "<nav class='nav'>"
        "<button id='prev' onclick='go(-1)'>&#8592;</button>"
        "<div class='progress'><div class='progress-bar' id='pbar'></div></div>"
        "<button id='next' onclick='go(1)'>&#8594;</button>"
        "</nav>"
        "<script>"
        f"var N={len(sections)},cur=0;"
        "function show(i){"
        "  document.querySelectorAll('.slide').forEach(function(s){s.classList.remove('active')});"
        "  document.getElementById('s'+i).classList.add('active');"
        "  document.getElementById('pbar').style.width=((i+1)/N*100)+'%';"
        "  document.getElementById('prev').disabled=i===0;"
        "  document.getElementById('next').disabled=i===N-1;"
        "  cur=i;"
        "}"
        "function go(d){var n=cur+d;if(n>=0&&n<N)show(n);}"
        "document.addEventListener('keydown',function(e){"
        "  if(e.key==='ArrowRight'||e.key===' ')go(1);"
        "  if(e.key==='ArrowLeft')go(-1);"
        "});"
        "show(0);"
        "</script>"
        "</body></html>",
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
