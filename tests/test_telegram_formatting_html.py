"""텔레그램 HTML 포맷팅 유틸리티 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.telegram_formatting import escape_html, markdown_to_html


# ── escape_html ────────────────────────────────────────────────────────────

def test_escape_html_ampersand() -> None:
    assert escape_html("R&D") == "R&amp;D"


def test_escape_html_angle_brackets() -> None:
    assert escape_html("<봇이름>") == "&lt;봇이름&gt;"


def test_escape_html_combined() -> None:
    assert escape_html("a < b & c > d") == "a &lt; b &amp; c &gt; d"


def test_escape_html_no_change() -> None:
    assert escape_html("안녕하세요 hello 123") == "안녕하세요 hello 123"


# ── markdown_to_html ───────────────────────────────────────────────────────

def test_bold_double_asterisk() -> None:
    result = markdown_to_html("**굵게**")
    assert result == "<b>굵게</b>"


def test_bold_double_underscore() -> None:
    result = markdown_to_html("__굵게__")
    assert result == "<b>굵게</b>"


def test_italic_single_asterisk() -> None:
    result = markdown_to_html("*기울임*")
    assert result == "<i>기울임</i>"


def test_italic_single_underscore() -> None:
    result = markdown_to_html("_기울임_")
    assert result == "<i>기울임</i>"


def test_inline_code() -> None:
    result = markdown_to_html("`코드`")
    assert result == "<code>코드</code>"


def test_inline_code_html_escape() -> None:
    result = markdown_to_html("`<tag> & foo`")
    assert result == "<code>&lt;tag&gt; &amp; foo</code>"


def test_fenced_code_block() -> None:
    result = markdown_to_html("```\nprint('hello')\n```")
    assert "<pre>" in result
    assert "print" in result


def test_fenced_code_block_with_lang() -> None:
    result = markdown_to_html("```python\nx = 1\n```")
    assert "<pre>" in result
    assert "x = 1" in result


def test_header_h1() -> None:
    result = markdown_to_html("# 제목")
    assert result == "<b>제목</b>"


def test_header_h3() -> None:
    result = markdown_to_html("### 소제목")
    assert result == "<b>소제목</b>"


def test_link() -> None:
    result = markdown_to_html("[클릭](https://example.com)")
    assert result == '<a href="https://example.com">클릭</a>'


def test_html_special_chars_in_plain_text() -> None:
    result = markdown_to_html("a < b & c > d")
    assert result == "a &lt; b &amp; c &gt; d"


def test_mixed_formatting() -> None:
    text = "## 제목\n\n**볼드** 텍스트와 *이탤릭*\n\n`코드` 예시"
    result = markdown_to_html(text)
    assert "<b>제목</b>" in result
    assert "<b>볼드</b>" in result
    assert "<i>이탤릭</i>" in result
    assert "<code>코드</code>" in result


def test_empty_string() -> None:
    assert markdown_to_html("") == ""


def test_plain_text_unchanged() -> None:
    text = "안녕하세요 일반 텍스트입니다."
    assert markdown_to_html(text) == text


def test_code_block_not_double_processed() -> None:
    """코드 블록 내부의 *italic* 같은 패턴이 변환되지 않아야 한다."""
    result = markdown_to_html("```\n*not italic*\n```")
    assert "<i>" not in result
    assert "*not italic*" in result or "not italic" in result


# ── 추가 패턴 (bold+italic, 수평선, 테이블 구분자) ─────────────────────────────

def test_bold_italic_triple_asterisk() -> None:
    """***text*** → <b><i>text</i></b>"""
    result = markdown_to_html("***굵은 이탤릭***")
    assert result == "<b><i>굵은 이탤릭</i></b>"


def test_bold_italic_triple_underscore() -> None:
    """___text___ → <b><i>text</i></b>"""
    result = markdown_to_html("___굵은 이탤릭___")
    assert result == "<b><i>굵은 이탤릭</i></b>"


def test_horizontal_rule_dashes() -> None:
    """--- 단독 줄 → 유니코드 구분선"""
    result = markdown_to_html("위\n---\n아래")
    assert "──────────" in result
    assert "---" not in result


def test_horizontal_rule_asterisks() -> None:
    """*** 단독 줄 → 유니코드 구분선 (수평선으로 처리)"""
    result = markdown_to_html("위\n***\n아래")
    assert "──────────" in result


def test_table_separator_stripped() -> None:
    """|---|---| 테이블 구분자 행 제거"""
    text = "| 이름 | 값 |\n|------|------|\n| A | 1 |"
    result = markdown_to_html(text)
    assert "|------|" not in result
    assert "| 이름 | 값 |" in result
    assert "| A | 1 |" in result


def test_strikethrough() -> None:
    """~~text~~ → <s>text</s>"""
    result = markdown_to_html("~~삭제~~")
    assert result == "<s>삭제</s>"


def test_mixed_bold_italic_in_paragraph() -> None:
    """실제 LLM 출력 패턴: 헤더 + 볼드이탤릭 + 수평선 혼합"""
    text = "## 결론\n\n***핵심 변경점***: 이스케이프 처리\n\n---\n\n일반 텍스트"
    result = markdown_to_html(text)
    assert "<b>결론</b>" in result
    assert "<b><i>핵심 변경점</i></b>" in result
    assert "──────────" in result
    assert "일반 텍스트" in result
