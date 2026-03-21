"""텔레그램 출력용 경량 포맷팅 유틸리티."""
from __future__ import annotations

import re

_CONTINUATION = "…(이어짐)"  # 청크가 잘릴 때 말미에 붙는 연출 문자열


def escape_html(text: str) -> str:
    """HTML 특수문자를 텔레그램 HTML parse_mode용으로 이스케이프한다.

    텔레그램 HTML 모드에서 이스케이프가 필요한 문자: & < >
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def markdown_to_html(text: str) -> str:
    """LLM이 생성한 표준 마크다운을 텔레그램 HTML parse_mode용으로 변환한다.

    처리 순서:
    1. 펜스 코드 블록(```...```) → <pre>...</pre>
    2. 인라인 코드(`...`) → <code>...</code>
    3. 나머지 텍스트 HTML 이스케이프 (& < >)
    4. **bold** / *italic* / ### Header / [link](url) 변환
    5. 플레이스홀더 복원

    지원 변환:
    - **text** / __text__ → <b>text</b>
    - *text* / _text_ → <i>text</i>
    - `code` → <code>code</code>
    - ```...``` → <pre>...</pre>
    - [text](url) → <a href="url">text</a>
    - # ~ ###### Header → <b>Header</b>
    """
    if not text:
        return text

    # 1. 펜스 코드 블록 추출 및 플레이스홀더 치환
    fenced_blocks: list[str] = []

    def _save_fenced(m: re.Match) -> str:
        content = escape_html(m.group(1) if m.group(1) is not None else "")
        fenced_blocks.append(f"<pre>{content}</pre>")
        return f"\x00FENCED{len(fenced_blocks) - 1}\x00"

    text = re.sub(r"```(?:\w+)?\n?([\s\S]*?)```", _save_fenced, text)

    # 2. 인라인 코드 추출 및 플레이스홀더 치환
    inline_codes: list[str] = []

    def _save_inline(m: re.Match) -> str:
        content = escape_html(m.group(1))
        inline_codes.append(f"<code>{content}</code>")
        return f"\x00INLINE{len(inline_codes) - 1}\x00"

    text = re.sub(r"`([^`\n]+)`", _save_inline, text)

    # 3. 나머지 텍스트 HTML 이스케이프
    text = escape_html(text)

    # 4. 마크다운 → HTML 변환
    # 헤더 (# ~ ######) → <b>
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    # Bold: **text** 또는 __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text, flags=re.DOTALL)
    # Italic: *text* (단, ** 처리 후라 * 하나만 남음)
    text = re.sub(r"\*([^*\n]+?)\*", r"<i>\1</i>", text)
    # Italic: _text_ — 단어 경계로 제한하여 snake_case 오인식 방지
    # (?<!\w) : 앞이 단어 문자가 아님 (공백/구두점/줄 시작)
    # (?!\w) : 뒤가 단어 문자가 아님
    text = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"<i>\1</i>", text)
    # 링크: [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
    # 취소선: ~~text~~
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    # 5. 플레이스홀더 복원
    for i, block in enumerate(fenced_blocks):
        text = text.replace(f"\x00FENCED{i}\x00", block)
    for i, block in enumerate(inline_codes):
        text = text.replace(f"\x00INLINE{i}\x00", block)

    return text


def split_message(text: str, max_len: int) -> list[str]:
    """긴 메시지를 문단/문장 경계를 우선으로 분할한다.

    2개 이상 청크로 나뉠 때 중간 청크 말미에 '…(이어짐)'을 붙여
    사용자가 내용이 이어짐을 자연스럽게 인지하도록 한다.
    """
    body = (text or "").strip()
    if not body:
        return [""]
    if len(body) <= max_len:
        return [body]

    effective_len = max_len

    def _find_breakpoint(chunk: str, limit: int) -> int:
        lower_bound = max(1, int(limit * 0.55))
        for token in ("\n\n", "\n- ", "\n• ", "\n", ". ", "? ", "! ", "; ", ", ", " "):
            idx = chunk.rfind(token, lower_bound, limit + 1)
            if idx != -1:
                return idx + len(token.rstrip())
        return limit

    chunks: list[str] = []
    remaining = body
    while len(remaining) > max_len:
        window = remaining[: effective_len + 1]
        cut = _find_breakpoint(window, effective_len)
        piece = remaining[:cut].rstrip()
        if not piece:
            piece = remaining[:effective_len].rstrip()
            cut = len(piece)
        chunks.append(piece)
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks
