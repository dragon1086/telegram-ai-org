# parse_mode 사용현황 목록

> 조사 범위: /Users/rocky/telegram-ai-org (Python 파일 전체)
> 조사 도구: ripgrep 패턴 검색
> 작성: 2026-03-21, aiorg_research_bot

---

## 요약

| parse_mode 값 | 사용 건수 | 파일 수 |
|--------------|-----------|---------|
| `"HTML"` | **80건+** | 12개 파일 |
| `"MarkdownV2"` | 0건 | — |
| `"Markdown"` (레거시) | 0건 | — |
| 미지정 (None) | 다수 | 다수 |

**결론: 코드베이스는 100% HTML parse_mode 단일 표준 사용 중.**

---

## 파일별 parse_mode="HTML" 사용 현황

### core/telegram_relay.py (핵심 릴레이 — 53건+)

| 라인 | 호출 함수 | markdown_to_html 적용 여부 |
|------|-----------|---------------------------|
| 803 | `reply_text(markdown_to_html(...), parse_mode="HTML")` | ✅ 적용 |
| 856 | `reply_text(markdown_to_html(...), parse_mode="HTML")` | ✅ 적용 |
| 986 | `progress_msg.edit_text(markdown_to_html(first), ...)` | ✅ 적용 |
| 1411 | `bot.send_message(..., text=markdown_to_html(message), ...)` | ✅ 적용 |
| 1770, 1781 | `progress_msg.edit_text(markdown_to_html(...), ...)` | ✅ 적용 |
| 2234, 2264, 2306 | `reply_text(markdown_to_html(...), ...)` | ✅ 적용 |
| 2336~2343 | `reply_text(markdown_to_html(...), ...)` | ✅ 적용 |
| 2389, 2412, 2415 | `reply_text(markdown_to_html(text), ...)` | ✅ 적용 |
| 2490 | `reply_text("\n".join(lines), parse_mode="HTML")` | ⚠️ 미적용 (수동 HTML) |
| 2694 | `reply_text(markdown_to_html(msg), ...)` | ✅ 적용 |
| 2724~2727 | `reply_text(..., parse_mode="HTML")` | ⚠️ 미적용 (수동 HTML) |
| 2750 | `edit_message_text(markdown_to_html(msg), ...)` | ✅ 적용 |
| 2806~2813 | `edit_text(markdown_to_html(...), ...)` | ✅ 적용 |
| 2835~2842 | `processing_msg.edit_text(markdown_to_html(...), ...)` | ✅ 적용 |
| 2884~2895 | `processing_msg.edit_text(markdown_to_html(...), ...)` | ✅ 적용 |
| 3521 | `reply_text(markdown_to_html(brief), ...)` | ✅ 적용 |
| 3549~3550 | `edit_text(markdown_to_html(...), ...)` | ✅ 적용 |
| 3583~3586 | `reply_text(markdown_to_html(...), ...)` | ✅ 적용 |
| 3633~3637 | `reply_text(markdown_to_html(...), ...)` | ✅ 적용 |
| 3659 | `reply_text(msg, parse_mode="HTML")` | ⚠️ 미적용 (수동 HTML f-string) |
| 3686 | `reply_text(msg, parse_mode="HTML")` | ⚠️ 미적용 (수동 HTML f-string) |
| 3693~3696 | `reply_text(..., parse_mode="HTML")` | ⚠️ 미적용 (수동 HTML) |
| 3807~3812 | `reply_text(msg[:4000], parse_mode="HTML")` | ⚠️ 미적용 (수동 HTML f-string) |
| 3824~3826 | `reply_text(..., parse_mode="HTML")` | ⚠️ 미적용 (수동 HTML) |
| 3957~4019 | `reply_text(markdown_to_html(...), ...)` | ✅ 적용 |
| 4062 | `reply_text(msg, parse_mode="HTML")` | ⚠️ 미적용 (수동 HTML f-string) |
| 4092, 4115 | `reply_text("\n".join(lines), parse_mode="HTML")` | ⚠️ 미적용 (수동 HTML) |

### core/display_limiter.py (중앙 전송 레이어 — 8건)

| 라인 | 호출 함수 | markdown_to_html 적용 여부 |
|------|-----------|---------------------------|
| 60 | `edit_text(markdown_to_html(pending.text), ...)` | ✅ 적용 |
| 74~75 | `html_text = markdown_to_html(text); {"parse_mode": "HTML"}` | ✅ 적용 |
| 83 | `reply_text(html_text, parse_mode="HTML")` | ✅ 적용 (74에서 변환) |
| 89 | `edit_text(markdown_to_html(text), ...)` | ✅ 적용 |
| 101~102 | `html_text = markdown_to_html(text); {"parse_mode": "HTML"}` | ✅ 적용 |
| 110 | `send_message(..., text=html_text, parse_mode="HTML")` | ✅ 적용 (101에서 변환) |
| 131 | `edit_text(markdown_to_html(pending.text), ...)` | ✅ 적용 |

### core/worker_bot.py (2건)

| 라인 | 호출 함수 | markdown_to_html 적용 여부 |
|------|-----------|---------------------------|
| 72 | `send_message(text=markdown_to_html(msg.to_telegram_text()), parse_mode="HTML")` | ✅ 적용 |
| 90 | `send_message(text=markdown_to_html(msg.to_telegram_text()), parse_mode="HTML")` | ✅ 적용 |

### core/cross_org_bridge.py (1건)

| 라인 | 호출 함수 | markdown_to_html 적용 여부 |
|------|-----------|---------------------------|
| 109~110 | `send_message(text=markdown_to_html(telegram_text), parse_mode="HTML")` | ✅ 적용 |

### scripts/ (5개 파일, 각 1건)

| 파일 | 라인 | markdown_to_html 적용 여부 |
|------|------|---------------------------|
| monthly_review.py | 204 | ✅ 적용 |
| weekly_standup.py | 221 | ✅ 적용 |
| daily_retro.py | 232 | ✅ 적용 |
| morning_goals.py | 121 | ✅ 적용 |
| daily_metrics.py | 169 | ✅ 적용 |

### tools/telegram_uploader.py (4건)

| 라인 | 호출 함수 | markdown_to_html 적용 여부 |
|------|-----------|---------------------------|
| 37 | `send_photo(..., caption=safe_caption, parse_mode="HTML")` | ✅ 적용 (safe_caption 변환됨) |
| 39 | `send_video(..., caption=safe_caption, parse_mode="HTML")` | ✅ 적용 |
| 41 | `send_audio(..., caption=safe_caption, parse_mode="HTML")` | ✅ 적용 |
| 43 | `send_document(..., caption=safe_caption, parse_mode="HTML")` | ✅ 적용 |

### scripts/bot_watchdog.py (1건, dict 방식)

| 라인 | 호출 방식 |
|------|-----------|
| 73 | `{"parse_mode": "HTML"}` — HTTP raw API 호출 |
