# MarkdownV2 vs HTML parse_mode 비교표

> 출처: Telegram Bot API 공식 문서 (https://core.telegram.org/bots/api#formatting-options)
> 작성: 2026-03-21, aiorg_research_bot

---

## 1. 개요 비교

| 항목 | HTML | MarkdownV2 | 레거시 Markdown (deprecated) |
|------|------|------------|------------------------------|
| parse_mode 값 | `"HTML"` | `"MarkdownV2"` | `"Markdown"` |
| 이스케이프 문자 수 | 3개 (`&`, `<`, `>`) | 18개 | 일부 |
| 동적 콘텐츠 안전성 | ✅ 높음 | ⚠️ 낮음 (특수문자 많음) | ❌ 권장 안 함 |
| 지원 태그/문법 | HTML 태그 | 마크다운 기호 | 마크다운 기호 (제한적) |
| 텔레그램 공식 권장 | ✅ | ✅ | ❌ Deprecated |

---

## 2. HTML parse_mode — 지원 태그 전체 목록

| HTML 태그 | 효과 | 예시 |
|-----------|------|------|
| `<b>`, `<strong>` | **굵게** | `<b>굵게</b>` |
| `<i>`, `<em>` | *기울임* | `<i>기울임</i>` |
| `<u>`, `<ins>` | 밑줄 | `<u>밑줄</u>` |
| `<s>`, `<strike>`, `<del>` | ~~취소선~~ | `<s>취소선</s>` |
| `<tg-spoiler>` 또는 `<span class="tg-spoiler">` | 스포일러 | `<tg-spoiler>숨김</tg-spoiler>` |
| `<a href="URL">` | 링크 | `<a href="https://...">텍스트</a>` |
| `<a href="tg://user?id=ID">` | 유저 멘션 | `<a href="tg://user?id=123">이름</a>` |
| `<code>` | 인라인 코드 (모노스페이스) | `<code>코드</code>` |
| `<pre>` | 코드 블록 | `<pre>블록</pre>` |
| `<pre><code class="language-python">` | 언어 지정 코드 블록 | `<pre><code class="language-python">x=1</code></pre>` |
| `<blockquote>` | 인용구 | `<blockquote>인용</blockquote>` |
| `<blockquote expandable>` | 접을 수 있는 인용구 | `<blockquote expandable>내용</blockquote>` |
| `<tg-emoji emoji-id="ID">` | 커스텀 이모지 | `<tg-emoji emoji-id="...">🎉</tg-emoji>` |

**이스케이프 필수 문자 (HTML):**

| 원문 | 변환 |
|------|------|
| `&` | `&amp;` |
| `<` | `&lt;` |
| `>` | `&gt;` |

---

## 3. MarkdownV2 parse_mode — 지원 문법 전체 목록

| 효과 | 문법 | 예시 |
|------|------|------|
| **굵게** | `*text*` | `*굵게*` |
| *기울임* | `_text_` | `_기울임_` |
| 밑줄 | `__text__` | `__밑줄__` |
| ~~취소선~~ | `~text~` | `~취소선~` |
| 스포일러 | `\|\|text\|\|` | `\|\|스포일러\|\|` |
| 링크 | `[text](URL)` | `[클릭](https://...)` |
| 유저 멘션 | `[이름](tg://user?id=ID)` | — |
| 인라인 코드 | `` `code` `` | `` `코드` `` |
| 코드 블록 | ` ```code``` ` | — |
| 인용구 | `>text` | `>인용` |
| 커스텀 이모지 | `![emoji](tg://emoji?id=ID)` | — |

**이스케이프 필수 특수문자 (18개):**

`_`, `*`, `[`, `]`, `(`, `)`, `~`, `` ` ``, `>`, `#`, `+`, `-`, `=`, `|`, `{`, `}`, `.`, `!`

→ **이 문자들이 포매팅 문법 외에 일반 텍스트로 등장할 때는 반드시 `\`를 앞에 붙여야 한다.**

예: `1\.5` `\#태그` `A \- B`

---

## 4. 핵심 차이점 요약

### HTML이 동적 콘텐츠에 유리한 이유
- 이스케이프 필요 문자가 3개뿐 (`&`, `<`, `>`)
- LLM 출력에 `-`, `.`, `!`, `#` 등이 빈번하게 등장 → MarkdownV2에서는 전부 이스케이프 필요
- 이스케이프 누락 시 MarkdownV2는 400 Bad Request 에러 발생
- HTML은 태그가 아닌 모든 텍스트를 그대로 통과시킴

### MarkdownV2가 선호되는 경우
- 순수 마크다운 문서를 그대로 전달할 때
- 이스케이프 처리가 자동화된 SDK를 사용할 때

### 레거시 Markdown
- **사용 금지**: 공식 Deprecated, 예측 불가능한 동작 있음

---

## 5. 결론

**코드베이스에는 HTML parse_mode가 최적**:
- LLM 출력 → `markdown_to_html()` 변환 → `parse_mode="HTML"` 전송 패턴이 가장 안전
- MarkdownV2 전환 시 LLM 출력의 모든 특수문자를 이스케이프하는 별도 레이어가 필요함
