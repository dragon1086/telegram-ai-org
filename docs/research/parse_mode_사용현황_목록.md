# parse_mode 사용현황 목록

> 분석 대상: /Users/rocky/telegram-ai-org (Python 파일 전체)
> 분석 일자: 2026-03-21

## parse_mode 분포 요약

| parse_mode 값 | 발생 횟수 | 비율 |
|--------------|---------|------|
| `"HTML"`     | 65+건   | 100% |
| `"MarkdownV2"` | 0건   | 0%   |
| `"Markdown"` | 0건     | 0%   |
| `None` (미지정) | ~40건  | (별도 목록 참조) |

**결론: 코드베이스 전체가 `parse_mode="HTML"` 단일 표준을 사용 중.**

---

## parse_mode="HTML" 명시 전송부 목록

### core/telegram_relay.py (핵심 메시지 경로)
| 라인 | 함수 | 메모 |
|------|------|------|
| 803 | reply_text | markdown_to_html() 적용 |
| 856 | reply_text | markdown_to_html() 적용 |
| 986 | edit_text | markdown_to_html() 적용 |
| 1411 | send_message | markdown_to_html() 적용 |
| 1770 | edit_text | markdown_to_html() 적용 |
| 1781 | edit_text | markdown_to_html() 적용 |
| 2235 | reply_text | markdown_to_html() 적용 |
| 2265 | edit_text | parse_mode="HTML" |
| 2306 | reply_text | markdown_to_html() 적용 |
| 2343 | reply_text | parse_mode="HTML" |
| 2389 | reply_text | markdown_to_html() 적용 |
| 2412 | reply_text | markdown_to_html() 적용 |
| 2415 | reply_text | markdown_to_html() 적용 |
| 2490 | reply_text | HTML 수동 조립 |
| 2694 | reply_text | markdown_to_html() 적용 |
| 2727 | reply_text | parse_mode="HTML" |
| 2750 | edit_text | markdown_to_html() 적용 |
| 2759 | edit_text | parse_mode="HTML" |
| 2813 | reply_text | parse_mode="HTML" |
| 2842 | reply_text | parse_mode="HTML" |
| 2895 | reply_text | parse_mode="HTML" |
| 3521 | reply_text | markdown_to_html() 적용 |
| 3550 | edit_text | markdown_to_html() 적용 |
| 3583 | reply_text | markdown_to_html() 적용 |
| 3586 | reply_text | markdown_to_html() 적용 |
| 3637 | reply_text | parse_mode="HTML" |
| 3659 | reply_text | HTML 수동 조립 (`<b>`, `<code>` 직접 사용) |
| 3686 | reply_text | HTML 수동 조립 (`<b>` 직접 사용) |
| 3696 | reply_text | HTML 수동 조립 |
| 3750 | reply_text | parse_mode="HTML" |
| 3758~3791 | reply_text ×4 | parse_mode="HTML" |
| 3812 | reply_text | parse_mode="HTML" |
| 3826 | reply_text | parse_mode="HTML" |
| 3958~4019 | reply_text ×6 | parse_mode="HTML" |
| 4062 | reply_text | parse_mode="HTML" |
| 4092 | reply_text | HTML 수동 조립 |
| 4115 | reply_text | HTML 수동 조립 |

### core/display_limiter.py (메시지 디스플레이 레이어)
| 라인 | 함수 | 메모 |
|------|------|------|
| 60 | edit_text | markdown_to_html() 적용 |
| 75 | kwargs dict | `{"parse_mode": "HTML"}` 기본 kwargs |
| 83 | reply_text | markdown_to_html() 적용 |
| 89 | edit_text | markdown_to_html() 적용 |
| 102 | kwargs dict | `{"parse_mode": "HTML"}` |
| 110 | send_message | markdown_to_html() 적용 |
| 131 | edit_text | markdown_to_html() 적용 |

### core/worker_bot.py
| 라인 | 함수 | 메모 |
|------|------|------|
| 73 | send_message | parse_mode="HTML" |
| 91 | send_message | parse_mode="HTML" |

### core/cross_org_bridge.py
| 라인 | 함수 | 메모 |
|------|------|------|
| 110 | send_message | parse_mode="HTML" |

### tools/telegram_uploader.py
| 라인 | 함수 | 메모 |
|------|------|------|
| 37 | send_photo | caption parse_mode="HTML" |
| 39 | send_video | caption parse_mode="HTML" |
| 41 | send_audio | caption parse_mode="HTML" |
| 43 | send_document | caption parse_mode="HTML" |

### scripts/ (자동화 스크립트)
| 파일 | 라인 | 메모 |
|------|------|------|
| scripts/monthly_review.py | 205 | parse_mode="HTML" |
| scripts/morning_goals.py | 122 | parse_mode="HTML" |
| scripts/daily_metrics.py | 170 | parse_mode="HTML" |
| scripts/weekly_standup.py | 222 | parse_mode="HTML" |
| scripts/daily_retro.py | 233 | parse_mode="HTML" |
| scripts/bot_watchdog.py | 73 | parse_mode="HTML" (kwargs dict) |
