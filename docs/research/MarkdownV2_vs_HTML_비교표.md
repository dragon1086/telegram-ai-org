# MarkdownV2 vs HTML parse_mode 비교표

> 출처: Telegram Bot API 공식 문서 (https://core.telegram.org/bots/api#formatting-options)

## 핵심 비교

| 항목 | MarkdownV2 | HTML |
|------|-----------|------|
| 이스케이프 대상 | 18개 특수문자 전체 `\` 필요 | `&`, `<`, `>` 3개만 엔티티 치환 |
| 이스케이프 방식 | 백슬래시 `\` 앞에 붙임 | HTML 엔티티: `&amp;` `&lt;` `&gt;` |
| 프로그래밍 편의성 | 낮음 (모든 특수문자 escape 필요) | 높음 (3개 엔티티만 처리) |
| 오작동 위험 | 높음 (특수문자 하나 누락 시 메시지 전체 파싱 실패) | 낮음 (안전한 이스케이프) |
| 지원 서식 | bold, italic, underline, strikethrough, spoiler, inline_url, inline_mention, custom_emoji, code, pre, blockquote | 동일 (태그 기반) |
| 중첩 가능 여부 | 일부 제한적 | HTML 태그 중첩 가능 |
| 채널 메시지 지원 | 지원 | 지원 |
| 봇 메시지 지원 | 지원 | 지원 |

## HTML 지원 태그 전체 목록

```
<b>, <strong>               → 굵게 (Bold)
<i>, <em>                   → 기울임 (Italic)
<u>, <ins>                  → 밑줄 (Underline)
<s>, <strike>, <del>        → 취소선 (Strikethrough)
<span class="tg-spoiler">   → 스포일러
<a href="URL">              → 하이퍼링크
<a href="tg://user?id=ID">  → 사용자 멘션
<tg-emoji emoji-id="ID">    → 커스텀 이모지
<code>                      → 인라인 코드 (monospace)
<pre>                       → 코드 블록 (pre-formatted)
<pre><code class="language-LANG"> → 언어 지정 코드 블록
<blockquote>                → 인용구 (blockquote)
<blockquote expandable>     → 펼침형 인용구
```

## MarkdownV2 지원 서식

```
**text** 또는 __text__   → 굵게
_text_                   → 기울임
__text__                 → 밑줄 (※ 굵게와 구문 충돌 주의)
~~text~~                 → 취소선
||text||                 → 스포일러
[text](url)              → 링크
`text`                   → 인라인 코드
```pre```                → 코드 블록
>text                    → 인용구 (줄 시작)
```

## HTML이 권장되는 이유

1. **이스케이프 규칙이 단순** — `&`, `<`, `>` 3가지만 처리
2. **파싱 실패 위험이 낮음** — MarkdownV2는 `!`, `.`, `-` 하나 누락해도 400 에러
3. **LLM 출력 변환에 적합** — LLM은 표준 마크다운을 생성하므로 HTML 변환 레이어가 더 안전
4. **중첩 서식 표현 용이** — `<b><i>text</i></b>` 형태로 명확하게 표현
