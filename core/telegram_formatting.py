"""텔레그램 출력용 경량 포맷팅 유틸리티."""
from __future__ import annotations

import re

# fix_html_tag_pairs 에서 검증·보정할 태그 목록
_TRACKED_HTML_TAGS = frozenset(["pre", "code", "blockquote", "b", "i", "s", "u"])
_HTML_TAG_RE = re.compile(
    r"<(/?)(" + "|".join(sorted(_TRACKED_HTML_TAGS)) + r")(?:\s[^>]*)?>",
    re.IGNORECASE,
)

_CONTINUATION = "…(이어짐)"  # 청크가 잘릴 때 말미에 붙는 연출 문자열

# [TEAM:...], [COLLAB:...], [AGENT:...] 등 내부 메타데이터 태그 패턴
_METADATA_TAG_RE = re.compile(r"\[[A-Z_]+:[^\]]*\]")


def escape_html(text: str) -> str:
    """HTML 특수문자를 텔레그램 HTML parse_mode용으로 이스케이프한다.

    텔레그램 HTML 모드에서 이스케이프가 필요한 문자: & < >
    """
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def fix_html_tag_pairs(html: str) -> str:
    """<pre>/<blockquote> 등 HTML 태그 쌍 불일치를 스택 기반으로 자동 보정한다.

    Telegram HTML parse_mode 에서 지원하는 주요 태그들의 열림/닫힘 쌍이
    올바르게 매칭되도록 보정한다:
    - 닫히지 않은 태그 → 문서 말미에 닫는 태그 자동 추가
    - 잘못 닫힌 태그 (스택에 없는 닫힘 태그) → 해당 닫힘 태그 제거
    - 중첩 순서 불일치 (예: <pre><blockquote>...</pre></blockquote>) →
      올바른 역순으로 자동 재정렬

    대상 태그: pre, code, blockquote, b, i, s, u
    """
    parts: list[str] = []
    stack: list[str] = []
    pos = 0

    for m in _HTML_TAG_RE.finditer(html):
        tag = m.group(2).lower()
        is_close = m.group(1) == "/"

        # 매치 이전 텍스트 보존
        parts.append(html[pos : m.start()])
        pos = m.end()

        if not is_close:
            # 열린 태그: 스택에 추가
            stack.append(tag)
            parts.append(m.group(0))
        else:
            # 닫힌 태그: 스택에서 매칭
            if stack and stack[-1] == tag:
                # 올바른 닫힘: 그대로 출력
                stack.pop()
                parts.append(m.group(0))
            elif tag in stack:
                # 중첩 순서 불일치: 스택 최상단부터 해당 태그까지 순서대로 닫음
                while stack and stack[-1] != tag:
                    parts.append(f"</{stack.pop()}>")
                if stack:
                    stack.pop()
                    parts.append(m.group(0))
            # else: 스택에 없는 닫힘 태그 → 제거 (아무것도 추가하지 않음)

    # 나머지 텍스트 보존
    parts.append(html[pos:])

    # 스택에 남은 미닫힌 태그 역순으로 자동 닫음
    for tag in reversed(stack):
        parts.append(f"</{tag}>")

    return "".join(parts)


def _convert_blockquotes(text: str) -> str:
    """HTML 이스케이프 후 &gt; 로 시작하는 줄을 <blockquote> 태그로 변환한다.

    연속된 blockquote 줄은 하나의 <blockquote> 블록으로 병합한다.
    빈 &gt; 줄(내용 없는 blockquote)도 빈 줄로 처리한다.
    <pre> 블록 내부의 &gt; 줄은 blockquote로 변환하지 않는다
    (Telegram HTML은 <pre> 를 <blockquote> 안에 중첩 허용하지 않음).
    """
    lines = text.split("\n")
    result: list[str] = []
    bq_lines: list[str] = []
    in_pre = False  # <pre> 블록 내부 추적

    def _flush() -> None:
        if bq_lines:
            content = "\n".join(bq_lines)
            result.append(f"<blockquote>{content}</blockquote>")
            bq_lines.clear()

    for line in lines:
        # <pre> 블록 진입 감지 (아직 pre 안에 있지 않을 때)
        if not in_pre and "<pre" in line:
            _flush()
            result.append(line)
            # 같은 줄에서 닫히지 않으면 multi-line pre 모드 진입
            if "</pre>" not in line:
                in_pre = True
            continue

        # <pre> 블록 내부: blockquote 변환 없이 그대로 출력
        if in_pre:
            result.append(line)
            if "</pre>" in line:
                in_pre = False
            continue

        if line.startswith("&gt; ") or line == "&gt;":
            bq_lines.append(line[5:] if line.startswith("&gt; ") else "")
        else:
            _flush()
            result.append(line)
    _flush()
    return "\n".join(result)


def markdown_to_html(text: str) -> str:
    """LLM이 생성한 표준 마크다운을 텔레그램 HTML parse_mode용으로 변환한다.

    처리 순서:
    1. 펜스 코드 블록(```...```) → <pre>...</pre>
    2. 인라인 코드(`...`) → <code>...</code>
    3. 나머지 텍스트 HTML 이스케이프 (& < >)
    4. **bold** / *italic* / ### Header / [link](url) 변환
    5. 플레이스홀더 복원
    6. blockquote (> text) → <blockquote>text</blockquote>

    지원 변환:
    - **text** / __text__ → <b>text</b>
    - *text* / _text_ → <i>text</i>
    - `code` → <code>code</code>
    - ```lang...``` → <pre><code class="language-lang">...</code></pre> (언어 syntax highlight)
    - ```...``` → <pre>...</pre>
    - [text](url) → <a href="url">text</a>
    - # Header     → <b>Header</b> + 구분선 (H1)
    - ## Header    → <b>▸ Header</b> (H2)
    - ### Header   → <b>Header</b> (H3~H6)
    - > text → <blockquote>text</blockquote>
    - ~~text~~ → <s>text</s>
    - - item / + item (줄 시작) → • item
    - 1. item / 2. item (순서 있는 목록) → 숫자 그대로 유지 (Telegram HTML 미지원)
    - | col | col | (테이블 행) → 앞뒤 파이프 제거, 셀 구분자 │ 로 통일
    """
    if not text:
        return text

    # 1. 펜스 코드 블록 추출 및 플레이스홀더 치환
    fenced_blocks: list[str] = []

    def _save_fenced(m: re.Match) -> str:
        lang = (m.group(1) or "").strip()
        content = escape_html(m.group(2) if m.group(2) is not None else "")
        if lang:
            # 언어 지정 시 <pre><code class="language-xxx"> 태그로 감싸 Telegram 채널 syntax highlight 지원
            fenced_blocks.append(f'<pre><code class="language-{lang}">{content}</code></pre>')
        else:
            fenced_blocks.append(f"<pre>{content}</pre>")
        return f"\x00FENCED{len(fenced_blocks) - 1}\x00"

    text = re.sub(r"```(\w+)?\n?([\s\S]*?)```", _save_fenced, text)

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
    # 헤더 계층 구분
    # H1 → bold + 구분선, H2 → 화살표 prefix + bold, H3~H6 → bold
    text = re.sub(r"^#\s+(.+)$", r"<b>\1</b>\n──────────", text, flags=re.MULTILINE)
    text = re.sub(r"^##\s+(.+)$", r"<b>▸ \1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"^#{3,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    # 수평선 (---, ***, ___ 단독 줄) → 유니코드 구분선
    text = re.sub(r"^[ \t]*(?:---+|\*\*\*+|___+)[ \t]*$", "──────────", text, flags=re.MULTILINE)
    # 테이블 구분자 행 (|---|---| 패턴) 제거
    text = re.sub(r"^\|[ \t]*:?-+:?[ \t]*(\|[ \t]*:?-+:?[ \t]*)+\|?[ \t]*$", "", text, flags=re.MULTILINE)
    # 테이블 콘텐츠 행: 앞뒤 | 제거, 셀 구분자를 │ 로 통일

    def _clean_table_row(m: re.Match) -> str:
        inner = m.group(0).strip().strip("|")
        cells = [c.strip() for c in inner.split("|")]
        return "  │  ".join(cells)

    text = re.sub(r"^\|.+\|[ \t]*$", _clean_table_row, text, flags=re.MULTILINE)
    # Bold+Italic: ***text*** 또는 ___text___ (반드시 ** / __ 보다 먼저 처리)
    # re.DOTALL 제거: 미닫힌 *** 가 다음 *** 까지 greedy 매칭하는 버그 방지
    text = re.sub(r"\*\*\*([^\n]+?)\*\*\*", r"<b><i>\1</i></b>", text)
    text = re.sub(r"___([^\n]+?)___", r"<b><i>\1</i></b>", text)
    # Bold: **text** 또는 __text__
    # re.DOTALL 제거: 미닫힌 ** 가 다음 ** 까지 greedy 매칭하는 버그 방지 (단일 줄 내에서만)
    text = re.sub(r"\*\*([^\n]+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__([^\n]+?)__", r"<b>\1</b>", text)
    # 순서 없는 목록: 줄 시작의 - / + / * 를 • 로 변환 (들여쓰기 지원, 코드블록은 이미 보호됨)
    # * bullet은 Italic 처리 전에 먼저 변환해야 함 (lookahead로 ** bold와 구별)
    # 단, --- 수평선은 이미 처리됐으므로 단독 줄 - 는 해당 없음
    text = re.sub(r"^([ \t]*)\* (?!\*)", r"\1• ", text, flags=re.MULTILINE)
    text = re.sub(r"^([ \t]*)[-+] ", r"\1• ", text, flags=re.MULTILINE)
    # Italic: *text* (단, ** 처리 후라 * 하나만 남음, bullet * 도 이미 처리됨)
    text = re.sub(r"\*([^*\n]+?)\*", r"<i>\1</i>", text)
    # Italic: _text_ — 단어 경계로 제한하여 snake_case 오인식 방지
    # (?<!\w) : 앞이 단어 문자가 아님 (공백/구두점/줄 시작)
    # (?!\w) : 뒤가 단어 문자가 아님
    text = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"<i>\1</i>", text)
    # 링크: [text](url)
    # URL 내에 괄호가 포함된 경우(예: Wikipedia 링크)도 처리하기 위해
    # 단순 [^)]+ 대신 균형잡힌 괄호 허용 패턴 사용:
    # - [^()]+  : 괄호 없는 문자들
    # - \([^)]*\) : 한 단계 중첩된 괄호 (예: /wiki/Python_(language))
    text = re.sub(r"\[([^\]]+)\]\(([^()]+(?:\([^)]*\)[^()]*)*)\)", r'<a href="\2">\1</a>', text)
    # 취소선: ~~text~~
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)

    # 5. 플레이스홀더 복원
    for i, block in enumerate(fenced_blocks):
        text = text.replace(f"\x00FENCED{i}\x00", block)
    for i, block in enumerate(inline_codes):
        text = text.replace(f"\x00INLINE{i}\x00", block)

    # 6. blockquote 변환 (HTML 이스케이프 이후라 > 는 &gt; 로 표현됨)
    text = _convert_blockquotes(text)

    # 7. 최종 HTML 태그 쌍 검증·자동 보정 (safety net)
    #    LLM 출력이나 엣지 케이스로 인한 미닫힘/중첩 불일치 방지
    text = fix_html_tag_pairs(text)

    return text


def format_for_telegram(text: str) -> str:
    """LLM 출력을 텔레그램 HTML parse_mode용으로 최종 변환한다.

    markdown_to_html()과의 차이점:
    - 내부 메타데이터 태그([TEAM:...], [COLLAB:...] 등)를 먼저 제거한다.
    - LLM 응답을 사용자에게 직접 전달하는 모든 경로에서 이 함수를 사용해야 한다.
    """
    if not text:
        return text
    text = _METADATA_TAG_RE.sub("", text).strip()
    return markdown_to_html(text)


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

    # 중간 청크에 _CONTINUATION 문자열이 붙으므로 유효 길이를 그만큼 줄임
    effective_len = max_len - len(_CONTINUATION)

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
        chunks.append(piece + _CONTINUATION)  # 중간 청크: 이어짐 표시 추가
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks
