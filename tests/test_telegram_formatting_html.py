"""텔레그램 HTML 포맷팅 유틸리티 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.telegram_formatting import escape_html, format_for_telegram, markdown_to_html

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
    assert '<pre><code class="language-python">' in result
    assert "x = 1" in result


def test_fenced_code_block_with_lang_syntax_highlight() -> None:
    """언어 지정 코드블록은 Telegram 채널 syntax highlight 용 class 속성 포함."""
    result = markdown_to_html("```typescript\nconst x: number = 1;\n```")
    assert '<pre><code class="language-typescript">' in result
    assert "const x" in result
    assert "</code></pre>" in result


def test_fenced_code_block_no_lang_uses_pre_only() -> None:
    """언어 미지정 코드블록은 <pre>만 사용."""
    result = markdown_to_html("```\nprint('hello')\n```")
    assert result.startswith("<pre>") or "<pre>" in result
    assert 'class="language-' not in result


def test_header_h1() -> None:
    result = markdown_to_html("# 제목")
    assert result == "<b>제목</b>\n──────────"


def test_header_h2() -> None:
    result = markdown_to_html("## 제목")
    assert result == "<b>▸ 제목</b>"


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
    assert "<b>▸ 제목</b>" in result
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
    """|---|---| 테이블 구분자 행 제거, 콘텐츠 행 앞뒤 파이프 제거"""
    text = "| 이름 | 값 |\n|------|------|\n| A | 1 |"
    result = markdown_to_html(text)
    assert "|------|" not in result
    # 앞뒤 파이프 제거 후 │ 구분자 사용
    assert "이름  │  값" in result
    assert "A  │  1" in result
    # 원본 파이프 문법은 사라짐
    assert "| 이름 | 값 |" not in result
    assert "| A | 1 |" not in result


def test_table_pipes_stripped() -> None:
    """테이블 행의 앞뒤 파이프를 제거하고 셀 구분을 │ 로 변환한다"""
    text = "| 단계 | 담당 | 상태 |\n|------|------|------|\n| 분석 | analyst | ✅ |"
    result = markdown_to_html(text)
    assert "단계  │  담당  │  상태" in result
    assert "분석  │  analyst  │  ✅" in result
    assert "| 단계" not in result


def test_strikethrough() -> None:
    """~~text~~ → <s>text</s>"""
    result = markdown_to_html("~~삭제~~")
    assert result == "<s>삭제</s>"


def test_mixed_bold_italic_in_paragraph() -> None:
    """실제 LLM 출력 패턴: 헤더 + 볼드이탤릭 + 수평선 혼합"""
    text = "## 결론\n\n***핵심 변경점***: 이스케이프 처리\n\n---\n\n일반 텍스트"
    result = markdown_to_html(text)
    assert "<b>▸ 결론</b>" in result
    assert "<b><i>핵심 변경점</i></b>" in result
    assert "──────────" in result
    assert "일반 텍스트" in result


# ── blockquote ─────────────────────────────────────────────────────────────

def test_blockquote_single_line() -> None:
    """> text → <blockquote>text</blockquote>"""
    result = markdown_to_html("> 참고 사항입니다.")
    assert result == "<blockquote>참고 사항입니다.</blockquote>"


def test_blockquote_multiline_merged() -> None:
    """연속된 > 줄은 하나의 <blockquote>로 병합"""
    text = "> 첫 번째 줄\n> 두 번째 줄"
    result = markdown_to_html(text)
    assert result == "<blockquote>첫 번째 줄\n두 번째 줄</blockquote>"


def test_blockquote_with_bold() -> None:
    """> **bold** 내부 포맷 변환 확인"""
    result = markdown_to_html("> **중요 내용**")
    assert "<blockquote>" in result
    assert "<b>중요 내용</b>" in result


def test_blockquote_surrounded_by_text() -> None:
    """blockquote 앞뒤 일반 텍스트는 유지"""
    text = "일반 텍스트\n\n> 인용 문구\n\n이후 텍스트"
    result = markdown_to_html(text)
    assert "<blockquote>인용 문구</blockquote>" in result
    assert "일반 텍스트" in result
    assert "이후 텍스트" in result


def test_blockquote_not_triggered_in_middle_of_text() -> None:
    """줄 중간의 > 는 blockquote로 변환하지 않음 (x > 5 같은 표현식)"""
    result = markdown_to_html("if x &gt; 5: pass")
    assert "<blockquote>" not in result


def test_blockquote_empty_gt() -> None:
    """&gt; 단독 줄 (내용 없는 blockquote) 처리"""
    text = "> "
    result = markdown_to_html(text)
    assert "<blockquote>" in result


# ── 순서 없는 목록 변환 ──────────────────────────────────────────────────────

def test_unordered_list_dash() -> None:
    """- item → • item"""
    result = markdown_to_html("- 항목 하나")
    assert result == "• 항목 하나"


def test_unordered_list_plus() -> None:
    """+ item → • item"""
    result = markdown_to_html("+ 항목 둘")
    assert result == "• 항목 둘"


def test_unordered_list_multiline() -> None:
    """여러 줄 목록 변환"""
    text = "- 첫 번째\n- 두 번째\n- 세 번째"
    result = markdown_to_html(text)
    assert result == "• 첫 번째\n• 두 번째\n• 세 번째"


def test_unordered_list_with_bold() -> None:
    """- **bold** item → • <b>bold</b> item"""
    result = markdown_to_html("- **핵심 변경점**: 설명")
    assert result == "• <b>핵심 변경점</b>: 설명"


def test_unordered_list_indented() -> None:
    """들여쓰기된 목록도 변환"""
    result = markdown_to_html("  - 들여쓰기 항목")
    assert result == "  • 들여쓰기 항목"


def test_horizontal_rule_not_converted_to_bullet() -> None:
    """--- 수평선은 bullet 변환 대상 아님 (이미 ── 로 처리됨)"""
    result = markdown_to_html("---")
    assert "•" not in result
    assert "──────────" in result


def test_list_inside_code_block_not_converted() -> None:
    """코드 블록 내부의 - item 은 변환하지 않음"""
    result = markdown_to_html("```\n- not a bullet\n```")
    assert "• not a bullet" not in result
    assert "- not a bullet" in result


def test_list_mixed_with_bold_and_code() -> None:
    """실제 LLM 출력 패턴: 목록 + 볼드 + 코드"""
    text = (
        "## 핵심 변경점\n\n"
        "- **파일 A**: `escape_html()` 추가\n"
        "- **파일 B**: parse_mode 적용\n"
        "- 단위 테스트 통과"
    )
    result = markdown_to_html(text)
    assert "<b>▸ 핵심 변경점</b>" in result
    assert "• <b>파일 A</b>:" in result
    assert "<code>escape_html()</code>" in result
    assert "• <b>파일 B</b>:" in result
    assert "• 단위 테스트 통과" in result


# ── 실제 PM 봇 응답 패턴 ────────────────────────────────────────────────────

def test_pm_response_pattern_team_announcement() -> None:
    """팀 구성 발표 후 마크다운이 올바르게 변환되어야 한다."""
    text = (
        "🏗️ 팀 구성\n"
        "• **analyst**: 코드베이스 전수 조사\n"
        "• **executor**: 구현 및 테스트\n\n"
        "이유: 분석 → 구현 순서로 진행"
    )
    result = markdown_to_html(text)
    assert "• <b>analyst</b>:" in result
    assert "• <b>executor</b>:" in result
    assert "이유:" in result


def test_pm_response_html_not_double_escaped() -> None:
    """HTML 태그를 직접 쓴 경우 이스케이프되어 안전하게 처리되어야 한다."""
    text = "<b>이미 HTML 태그가 있어요</b>"
    result = markdown_to_html(text)
    # 텔레그램 HTML parse_mode에서 그대로 전달되면 <b>가 렌더링되어 보안상 위험
    # 따라서 이스케이프되어 리터럴 텍스트로 표시되어야 함
    assert "&lt;b&gt;" in result
    assert "<b>" not in result


def test_pm_response_code_comparison_operators() -> None:
    """코드 내 비교 연산자(<, >)가 올바르게 이스케이프되어야 한다."""
    text = "```python\nif score < 6:\n    return False\n```"
    result = markdown_to_html(text)
    assert "<pre>" in result
    assert "&lt;" in result
    assert "score < 6" not in result


def test_pm_response_horizontal_rule_in_section() -> None:
    """섹션 구분선이 유니코드로 변환되어야 한다."""
    text = "## 결론\n\n핵심 내용입니다.\n\n---\n\n다음 단계"
    result = markdown_to_html(text)
    assert "──────────" in result
    assert "---" not in result
    assert "<b>▸ 결론</b>" in result


def test_ordered_list_unchanged() -> None:
    """순서 있는 목록(1. 2. 3.)은 Telegram에서 그대로 읽히므로 변환하지 않는다."""
    text = "1. 첫 번째 단계\n2. 두 번째 단계\n3. 세 번째 단계"
    result = markdown_to_html(text)
    assert "1. 첫 번째 단계" in result
    assert "2. 두 번째 단계" in result
    assert "3. 세 번째 단계" in result


def test_header_hierarchy_visual_distinction() -> None:
    """H1/H2/H3이 서로 시각적으로 다르게 렌더링되어야 한다."""
    text = "# 대제목\n\n## 중제목\n\n### 소제목"
    result = markdown_to_html(text)
    # H1: bold + 구분선
    assert "<b>대제목</b>\n──────────" in result
    # H2: 화살표 prefix
    assert "<b>▸ 중제목</b>" in result
    # H3: 단순 bold
    assert "<b>소제목</b>" in result


# ── format_for_telegram (통합 함수) ─────────────────────────────────────────

def test_format_for_telegram_strips_team_tag() -> None:
    """[TEAM:...] 메타데이터 태그를 제거하고 마크다운을 HTML로 변환한다."""
    text = "[TEAM:solo]\n\n**결론:** 작업 완료했습니다."
    result = format_for_telegram(text)
    assert "[TEAM:" not in result
    assert "<b>결론:</b>" in result


def test_format_for_telegram_strips_collab_tag() -> None:
    """[COLLAB:...] 태그를 제거한다."""
    text = "[COLLAB:디자인 요청|맥락: 현재 작업]\n\n진행 중입니다."
    result = format_for_telegram(text)
    assert "[COLLAB:" not in result
    assert "진행 중입니다." in result


def test_format_for_telegram_strips_multiple_tags() -> None:
    """여러 메타데이터 태그를 모두 제거한다."""
    text = "[TEAM:agent1,agent2]\n[COLLAB:작업]\n\n**본문** 내용"
    result = format_for_telegram(text)
    assert "[TEAM:" not in result
    assert "[COLLAB:" not in result
    assert "<b>본문</b>" in result


def test_format_for_telegram_preserves_markdown_rendering() -> None:
    """메타데이터 태그 제거 후에도 마크다운이 올바르게 변환된다."""
    text = (
        "[TEAM:T-global-091]\n\n"
        "## 분석 결과\n\n"
        "- **parse_mode**: HTML 통일 ✅\n"
        "> 변경 완료\n"
    )
    result = format_for_telegram(text)
    assert "[TEAM:" not in result
    assert "<b>▸ 분석 결과</b>" in result
    assert "• <b>parse_mode</b>:" in result
    assert "<blockquote>변경 완료</blockquote>" in result


def test_format_for_telegram_empty_string() -> None:
    """빈 문자열은 그대로 반환한다."""
    assert format_for_telegram("") == ""


def test_format_for_telegram_no_metadata_tag_unchanged() -> None:
    """메타데이터 태그 없는 텍스트는 markdown_to_html과 동일한 결과를 낸다."""
    text = "**볼드** 텍스트와 `인라인 코드`"
    assert format_for_telegram(text) == markdown_to_html(text)


def test_format_for_telegram_hardcoded_html_not_double_escaped() -> None:
    """마크다운 포맷 사용 시 올바른 HTML이 생성된다 (이중 이스케이프 없음)."""
    # 올바른 방식: 마크다운으로 작성 → format_for_telegram 변환
    text = "또는 `/org set-tone <봇이름> <말투지시>` 명령어를 사용하세요."
    result = format_for_telegram(text)
    # backtick → <code>, angle brackets → escaped safely
    assert "<code>/org set-tone" in result
    assert "&lt;봇이름&gt;" in result
    # 이중 이스케이프 없음
    assert "&amp;lt;" not in result


# ── Risk-2: * item bullet 변환 ────────────────────────────────────────────

def test_star_bullet_single() -> None:
    """* item → • item (LLM이 자주 사용하는 별표 bullet)"""
    result = markdown_to_html("* 항목 하나")
    assert result == "• 항목 하나"


def test_star_bullet_multiline() -> None:
    """여러 줄 * 목록 변환"""
    text = "* 첫 번째\n* 두 번째\n* 세 번째"
    result = markdown_to_html(text)
    assert result == "• 첫 번째\n• 두 번째\n• 세 번째"


def test_star_bullet_not_italic() -> None:
    """* item 이 이탤릭으로 오변환되지 않아야 한다"""
    text = "* 항목 one\n* 항목 two"
    result = markdown_to_html(text)
    assert "<i>" not in result
    assert "• 항목 one" in result
    assert "• 항목 two" in result


def test_star_bullet_does_not_affect_bold() -> None:
    """** bold ** 는 bullet 변환 대상 아님 (lookahead 검증)"""
    result = markdown_to_html("** 굵게 **")
    # ** 는 bullet이 아닌 bold
    assert "•" not in result


def test_star_bullet_with_bold_text() -> None:
    """* **bold** item → • <b>bold</b> item"""
    result = markdown_to_html("* **핵심**: 설명")
    assert result == "• <b>핵심</b>: 설명"


def test_star_bullet_indented() -> None:
    """들여쓰기된 * 목록도 변환"""
    result = markdown_to_html("  * 들여쓰기 항목")
    assert result == "  • 들여쓰기 항목"


# ── Risk-3: re.DOTALL 제거 — 단일 줄 bold ───────────────────────────────

def test_bold_single_line_still_works() -> None:
    """**bold** 단일 줄 변환은 여전히 작동해야 한다"""
    result = markdown_to_html("**굵게**")
    assert result == "<b>굵게</b>"


def test_bold_unclosed_does_not_greedy_match_next_bold() -> None:
    """미닫힌 ** 가 다음 줄의 ** 까지 greedy 매칭하지 않아야 한다 (DOTALL 제거 검증)"""
    # 두 번째 줄에 정상 bold가 있을 때, 첫 줄의 미닫힌 ** 가 탐욕적으로 삼켜선 안 됨
    text = "첫 줄 ** 미닫힘\n**정상 bold**"
    result = markdown_to_html(text)
    # 두 번째 줄의 **정상 bold** 가 정상 변환되어야 함
    assert "<b>정상 bold</b>" in result


def test_bold_multiline_no_crossline_match() -> None:
    """** 는 줄 경계를 넘어 매칭하지 않는다"""
    text = "줄1 **볼드시작\n줄2 볼드끝** 여기"
    result = markdown_to_html(text)
    # 줄을 넘는 bold는 변환되지 않음 → ** 그대로 남음 (HTML 렌더링에서는 무시됨)
    assert "<b>볼드시작\n줄2 볼드끝</b>" not in result


# ── escape_html 엔진 인자 / 예외 메시지 안전성 (parse_mode="HTML" 일관성) ────

def test_escape_html_engine_name_with_angle_brackets() -> None:
    """/set_engine 사용법 안내 텍스트: <engine> 리터럴이 이스케이프되어야 한다."""
    from core.telegram_formatting import escape_html
    # 이미 이스케이프된 &lt;&gt; 는 이중 이스케이프되지 않아야 한다
    # &lt; → &amp;lt; 가 되는 이중 이스케이프가 발생하면 안 됨
    # 위 문자열은 이미 HTML 이스케이프된 리터럴이므로 escape_html을 추가로 호출하면 이중 이스케이프됨
    # 실제 코드에서는 이미 이스케이프된 문자열에 escape_html을 쓰지 않도록 설계되어야 함
    assert "&amp;lt;" not in escape_html("a < b")  # 이스케이프 자체는 1번만
    assert escape_html("a < b") == "a &lt; b"


def test_escape_html_user_input_engine() -> None:
    """사용자 입력 engine 값에 HTML 특수문자가 포함된 경우 안전하게 이스케이프."""
    from core.telegram_formatting import escape_html
    malicious_engine = "<script>alert(1)</script>"
    result = escape_html(malicious_engine)
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_escape_html_exception_message() -> None:
    """예외 메시지 내 HTML 특수문자가 parse_mode='HTML' 전송 전에 이스케이프된다."""
    from core.telegram_formatting import escape_html
    exc_msg = "Connection error: url=<https://api.telegram.org> & timeout=30"
    result = escape_html(exc_msg)
    assert "<https" not in result
    assert "&lt;https" in result
    assert "&amp;" in result


def test_markdown_bold_with_html_special_chars() -> None:
    """**bold** 내부에 HTML 특수문자가 있어도 올바르게 이스케이프+변환된다."""
    result = markdown_to_html("**엔진: <claude-code>**")
    assert "<b>엔진: &lt;claude-code&gt;</b>" == result


def test_ampersand_in_plain_text_escaped() -> None:
    """일반 텍스트의 & 가 &amp; 로 이스케이프되어 HTML 모드에서 안전하다."""
    result = markdown_to_html("R&D 팀 결과: **완료**")
    assert "R&amp;D" in result
    assert "<b>완료</b>" in result


def test_wikipedia_url_with_parentheses() -> None:
    """Wikipedia 스타일 괄호 포함 URL이 올바르게 링크로 변환된다."""
    text = "[Python](https://en.wikipedia.org/wiki/Python_(programming_language))"
    result = markdown_to_html(text)
    assert '<a href="https://en.wikipedia.org/wiki/Python_(programming_language)">Python</a>' == result


def test_raw_html_tags_escaped_in_output() -> None:
    """LLM이 직접 쓴 <b> 등 HTML 태그는 이스케이프되어 리터럴 텍스트로 표시된다."""
    result = markdown_to_html("<b>직접 쓴 태그</b>")
    assert "<b>" not in result          # 렌더링되면 안 됨
    assert "&lt;b&gt;" in result        # 리터럴로 표시되어야 함


def test_numbered_header_h3() -> None:
    """### 1. 숫자로 시작하는 H3 헤더도 bold로 변환된다."""
    result = markdown_to_html("### 1. 첫 번째 단계")
    assert "<b>1. 첫 번째 단계</b>" == result


def test_full_pm_report_renders_correctly() -> None:
    """실제 PM 보고서 전체 패턴이 올바르게 HTML로 변환된다."""
    report = (
        "## 결론\n\n"
        "**텔레그램 파싱 수정 완료됐습니다.**\n\n"
        "## 핵심 내용\n\n"
        "- **parse_mode**: HTML로 통일 ✅\n"
        "- **escape_html**: 동적 데이터 전체 적용\n"
        "- **테스트**: 80개 통과\n\n"
        "> 참고: MarkdownV2 대신 HTML 선택 (유지보수 용이)\n\n"
        "## 다음 조치\n"
        "1. 커밋 및 푸시\n"
        "2. 봇 재기동 요청\n"
    )
    result = format_for_telegram(report)
    assert "<b>▸ 결론</b>" in result
    assert "<b>텔레그램 파싱 수정 완료됐습니다.</b>" in result
    assert "<b>▸ 핵심 내용</b>" in result
    assert "• <b>parse_mode</b>: HTML로 통일" in result
    assert "<blockquote>참고:" in result
    assert "<b>▸ 다음 조치</b>" in result
    # 순서 있는 목록은 그대로 유지
    assert "1. 커밋 및 푸시" in result
    assert "2. 봇 재기동 요청" in result
