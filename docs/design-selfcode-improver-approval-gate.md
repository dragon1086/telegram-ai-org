# SelfCodeImprover 승인 게이트 — UX/인터랙션 설계 명세서

> Task ID: T-aiorg_pm_bot-368 | 2026-03-24 | 디자인실

---

## 0. 현황 요약 (설계 전 베이스라인)

현재 `improvement_bus.py:_format_approval_notification()`이 생성하는 메시지:
```
🔔 *코드 자동 수정 승인 요청*

• ID: `{approval_id}`
• 대상: `{signal.target}`
• 우선순위: {priority}/10
• 신호 종류: {kind}
• 제안 내용: {suggested_action}

✅ 승인: `/approve_code_fix {approval_id}`
❌ 거절: `/reject_code_fix {approval_id}`

⏰ 24시간 내 응답 없으면 자동 만료됩니다.
```

**문제점 3가지**:
1. 텍스트 명령어 직접 입력 필요 — 모바일에서 복사/붙여넣기 마찰
2. 증거(evidence) 데이터가 메시지에 노출되지 않아 맥락 부족
3. 결과 피드백 메시지 없음 (승인/거절 후 어떻게 됐는지 Rocky가 모름)

---

## Phase 1: UX 리서치 보고서

### 1.1 사용자 프로파일

| 항목 | 내용 |
|------|------|
| 사용자 | Rocky (단일 인간 의사결정자) |
| 컨텍스트 | 텔레그램 모바일/데스크탑 혼용 |
| 빈도 | 일 1~3회 (ImprovementBus 02:00 KST 실행 기준) |
| 인지 부하 | 낮아야 함 — 승인 결정에 30초 이내 소요 목표 |
| 리스크 인식 | priority≥8 코드 변경 = git push까지 자동 실행, 고위험 |

### 1.2 사용자 핵심 니즈

| 니즈 | 현재 충족? | 개선 방향 |
|------|-----------|-----------|
| "이게 왜 필요한지 알고 싶다" | ❌ 신호 종류만 표시 | evidence 요약 + 코드 파일 명시 |
| "탭 한 번으로 결정하고 싶다" | ❌ 명령어 직접 입력 | Inline Keyboard Button (✅/❌) |
| "내가 승인했는지 확인하고 싶다" | ❌ 피드백 없음 | 결과 Confirmation 메시지 |
| "보류하고 나중에 결정하고 싶다" | ❌ defer 없음 | 🕐 Defer(+4h) 버튼 추가 |
| "대기 중인 게 뭔지 한눈에 보고 싶다" | ❌ 목록 조회 없음 | `/pending_fixes` 요약 커맨드 |

### 1.3 경쟁/레퍼런스 패턴 분석

| 서비스 | 패턴 | 차용 포인트 |
|--------|------|------------|
| GitHub PR Review | 변경 파일 목록 + Approve/Request Changes | diff 요약을 메시지에 포함 |
| PagerDuty Alert | Alert → Acknowledge → Resolve 3단계 | 상태 전이 명확화 |
| Slack Approval Bot | Block Kit Button (Primary/Danger) | 버튼 계층 시각화 |
| Vercel Deploy Preview | 자동 배포 전 Preview URL + 확인 버튼 | 실행 결과 예측 정보 제공 |

### 1.4 리스크 분류

```
HIGH RISK  : priority ≥ 9 — 코드 실행 + git push + bot restart 가능
MED RISK   : priority 8   — 코드 변경 + git push
LOW RISK   : priority < 8 — 승인 게이트 불필요 (현행 유지)
```

---

## Phase 2: 정보 구조(IA) 문서

### 2.1 승인 게이트 상태 머신

```
                    ┌─────────────────────────────────────────────┐
                    │           ImprovementBus._dispatch()         │
                    │   priority ≥ 8 AND target.startswith("code:")│
                    └──────────────────┬──────────────────────────┘
                                       │ enqueue()
                                       ▼
                               ┌──────────────┐
                               │   PENDING    │◄──────────────────┐
                               │  (큐 적재)   │                   │
                               └──────┬───────┘              defer(+4h)
                                      │                           │
                         Telegram 승인 요청 메시지 전송             │
                                      │                           │
                    ┌─────────────────┼─────────────────────┐     │
                    │                 │                      │     │
               ✅ approve        ❌ reject              🕐 defer───┘
                    │                 │
                    ▼                 ▼
             ┌──────────┐      ┌──────────┐
             │ APPROVED │      │ REJECTED │
             └────┬─────┘      └────┬─────┘
                  │                 │
             SelfCodeImprover   skip + log
             .fix() 실행
                  │
                  ▼
             ┌──────────┐
             │ EXECUTED │◄── mark_executed()
             └──────────┘

※ 24h 미응답 → EXPIRED (expire_old_pending() cron)
```

### 2.2 메시지 정보 계층

```
Level 1 — 헤더: 심각도 + 제목
Level 2 — 핵심 메타: ID, 대상 파일, 우선순위
Level 3 — 근거: 신호 종류, 발생 횟수, 제안 내용
Level 4 — 위험 지표: 예상 변경 범위, 자동 실행 포함 여부
Level 5 — 액션: 승인 / 거절 / 보류 버튼
Level 6 — 만료 안내: 타임아웃 명시
```

### 2.3 네비게이션 맵

```
Rocky의 진입점
├── 푸시 알림 탭 → [승인 요청 메시지] (Primary Flow)
│   ├── ✅ 승인 → [승인 확인 메시지] → (SelfCodeImprover 실행)
│   │                                 └── [실행 결과 메시지]
│   ├── ❌ 거절 → [거절 확인 메시지]
│   └── 🕐 보류 → [보류 확인 메시지] → (4시간 후 재알림)
│
└── 커맨드 입력
    ├── /pending_fixes      → [대기 목록 메시지]
    ├── /approve_code_fix {id} → [승인 확인 메시지]
    └── /reject_code_fix {id}  → [거절 확인 메시지]
```

---

## Phase 3: 와이어프레임

### WF-01: 승인 요청 메시지 (PRIMARY — Telegram Inline Keyboard)

```
┌─────────────────────────────────────────────┐
│ 🚨 코드 자동 수정 승인 요청                    │ ← Header (priority≥9: 🚨, priority=8: 🔔)
│                                              │
│ ┌─ 핵심 정보 ──────────────────────────────┐ │
│ │  📁 대상    core/nl_classifier.py         │ │
│ │  🎯 우선순위 9/10  🏷 CODE_SMELL          │ │
│ │  🆔 ID      a3f7c1e2d4b5                  │ │
│ └────────────────────────────────────────── ┘ │
│                                              │
│ ┌─ 근거 ───────────────────────────────────┐ │
│ │  반복 에러 패턴 7회 감지 (14일 내)          │ │
│ │  → 함수 길이 초과 + import cycle 경고      │ │
│ └────────────────────────────────────────── ┘ │
│                                              │
│ ┌─ 제안 내용 ───────────────────────────────┐ │
│ │  nl_classifier.py 분리 리팩토링 (claude    │ │
│ │  subprocess → TDD → git push)              │ │
│ └────────────────────────────────────────── ┘ │
│                                              │
│ ⚠️ 실행 시: claude subprocess + git push     │ ← 위험 지표 (필수)
│                                              │
│ ┌─────────────────────────────────────────┐ │
│ │ [✅ 승인 실행]  [❌ 거절]  [🕐 4시간 보류] │ │ ← Inline Keyboard (3버튼)
│ └─────────────────────────────────────────┘ │
│                                              │
│ ⏰ 2026-03-25 02:17 KST 자동 만료             │ ← 절대 시각 표시
└─────────────────────────────────────────────┘
```

---

### WF-02: 승인 확인 메시지 (버튼 탭 후 즉시 전송)

```
┌─────────────────────────────────────────────┐
│ ✅ 승인 완료                                  │
│                                              │
│  ID: a3f7c1e2d4b5                            │
│  대상: core/nl_classifier.py                 │
│  SelfCodeImprover 실행 시작 중...             │
│                                              │
│  결과는 완료 후 별도 메시지로 알립니다.         │
└─────────────────────────────────────────────┘
```

---

### WF-03: 거절 확인 메시지

```
┌─────────────────────────────────────────────┐
│ ❌ 거절 처리됨                                │
│                                              │
│  ID: a3f7c1e2d4b5                            │
│  대상: core/nl_classifier.py                 │
│  신호는 rejected 상태로 보관됩니다.            │
│  동일 신호가 재발하면 재요청됩니다.             │
└─────────────────────────────────────────────┘
```

---

### WF-04: 실행 결과 메시지 (SelfCodeImprover 완료 후)

```
┌─────────────────────────────────────────────┐
│ 🎉 자동 수정 완료  /  💥 수정 실패            │ (결과에 따라)
│                                              │
│  ID: a3f7c1e2d4b5                            │
│  대상: core/nl_classifier.py                 │
│  브랜치: fix/auto-2026-03-24-nl_classifier   │
│  커밋: abc1234                               │
│  시도: 2/3                                   │
│                                              │
│ [성공 시] PR 머지 후 봇 재시작 권장            │
│ [실패 시] 수동 수정이 필요합니다.              │
└─────────────────────────────────────────────┘
```

---

### WF-05: 보류(Defer) 확인 메시지

```
┌─────────────────────────────────────────────┐
│ 🕐 4시간 후 재알림 예약됨                     │
│                                              │
│  ID: a3f7c1e2d4b5                            │
│  재알림: 2026-03-24 06:17 KST               │
└─────────────────────────────────────────────┘
```

---

### WF-06: 대기 목록 메시지 (/pending_fixes)

```
┌─────────────────────────────────────────────┐
│ 📋 코드 수정 승인 대기 목록 (2건)              │
│                                              │
│ 1. a3f7c1e2d4b5  priority=9                  │
│    core/nl_classifier.py                     │
│    대기 중: 1시간 23분                        │
│    [✅ 승인] [❌ 거절]                        │
│                                              │
│ 2. b9d4f2e1c3a6  priority=8                  │
│    core/improvement_bus.py                   │
│    대기 중: 3시간 41분                        │
│    [✅ 승인] [❌ 거절]                        │
└─────────────────────────────────────────────┘
```

---

## Phase 4: 디자인 시스템 + 최종 메시지 템플릿

### 4.1 디자인 토큰

#### 이모지 심볼 체계 (WCAG AAA 대체 텍스트 병행)

| 토큰 | 이모지 | 의미 | 대체 텍스트 |
|------|-------|------|------------|
| `ICON_CRITICAL` | 🚨 | priority=9~10 | 긴급 |
| `ICON_HIGH` | 🔔 | priority=8 | 요청 |
| `ICON_FILE` | 📁 | 파일 대상 | 대상 |
| `ICON_PRIORITY` | 🎯 | 우선순위 | 우선순위 |
| `ICON_ID` | 🆔 | 승인 ID | ID |
| `ICON_APPROVE` | ✅ | 승인 | 승인 |
| `ICON_REJECT` | ❌ | 거절 | 거절 |
| `ICON_DEFER` | 🕐 | 보류 | 보류 |
| `ICON_WARN` | ⚠️ | 위험 경고 | 경고 |
| `ICON_EXPIRE` | ⏰ | 만료 시각 | 만료 |
| `ICON_SUCCESS` | 🎉 | 성공 완료 | 완료 |
| `ICON_FAIL` | 💥 | 실패 | 실패 |

#### 버튼 레이아웃 규칙

```
- 버튼 최대 3개 / 1행 (모바일 최소 탭 타겟 44px 고려)
- 버튼 순서: [Primary Positive] [Primary Negative] [Secondary]
- callback_data 포맷: "{action}_{approval_id}"
  예: "approve_a3f7c1e2d4b5", "reject_a3f7c1e2d4b5", "defer_a3f7c1e2d4b5"
```

### 4.2 최종 Telegram 메시지 템플릿 (Python 코드 명세)

#### 승인 요청 메시지 — `_format_approval_notification()` 교체 명세

```python
# 개선된 포맷 명세 (engineering_bot 구현용)
# parse_mode = "Markdown" (기존 유지)
# reply_markup = InlineKeyboardMarkup (신규 추가)

def _format_approval_notification(self, signal, approval_id: str) -> tuple[str, dict]:
    """
    Returns:
        text: Telegram 메시지 본문 (Markdown)
        reply_markup: InlineKeyboardMarkup dict
    """
    icon = "🚨" if signal.priority >= 9 else "🔔"
    target_file = signal.target.replace("code:", "")
    expire_kst = (datetime.now(timezone.utc) + timedelta(hours=24))
    expire_str = expire_kst.strftime("%Y-%m-%d %H:%M KST")

    # evidence 요약 (최대 2줄)
    evidence_lines = []
    if "repeat_count" in signal.evidence:
        evidence_lines.append(f"반복 에러 {signal.evidence['repeat_count']}회 감지")
    if "file_lines" in signal.evidence:
        evidence_lines.append(f"코드 라인 수: {signal.evidence['file_lines']}L")
    evidence_summary = "\n".join(f"  {l}" for l in evidence_lines) or "  (근거 데이터 없음)"

    text = (
        f"{icon} *코드 자동 수정 승인 요청*\n"
        f"\n"
        f"📁 대상: `{target_file}`\n"
        f"🎯 우선순위: `{signal.priority}/10`  🏷 `{signal.kind.value}`\n"
        f"🆔 ID: `{approval_id}`\n"
        f"\n"
        f"*근거*\n"
        f"{evidence_summary}\n"
        f"\n"
        f"*제안*\n"
        f"  {signal.suggested_action}\n"
        f"\n"
        f"⚠️ 실행 시: claude subprocess → git push\n"
        f"\n"
        f"⏰ 만료: {expire_str}"
    )

    reply_markup = {
        "inline_keyboard": [[
            {"text": "✅ 승인 실행", "callback_data": f"approve_{approval_id}"},
            {"text": "❌ 거절",     "callback_data": f"reject_{approval_id}"},
            {"text": "🕐 4h 보류",  "callback_data": f"defer_{approval_id}"},
        ]]
    }

    return text, reply_markup
```

#### 콜백 핸들러 응답 명세 (callback_query 처리)

```python
# approve_{id} 수신 시
CONFIRM_APPROVE = (
    "✅ *승인 완료*\n"
    "\n"
    "ID: `{approval_id}`\n"
    "대상: `{target}`\n"
    "SelfCodeImprover 실행 시작 중...\n"
    "\n"
    "결과는 완료 후 별도 메시지로 알립니다."
)

# reject_{id} 수신 시
CONFIRM_REJECT = (
    "❌ *거절 처리됨*\n"
    "\n"
    "ID: `{approval_id}`\n"
    "대상: `{target}`\n"
    "신호는 rejected 상태로 보관됩니다."
)

# defer_{id} 수신 시
CONFIRM_DEFER = (
    "🕐 *4시간 후 재알림 예약됨*\n"
    "\n"
    "ID: `{approval_id}`\n"
    "재알림: {defer_time_kst} KST"
)
```

#### 실행 결과 메시지 (SelfCodeImprover 완료 후 별도 전송)

```python
# 성공
RESULT_SUCCESS = (
    "🎉 *자동 수정 완료*\n"
    "\n"
    "ID: `{approval_id}`\n"
    "대상: `{target}`\n"
    "브랜치: `{branch}`\n"
    "커밋: `{commit_hash[:7]}`\n"
    "시도: {attempts}/3\n"
    "\n"
    "PR 머지 후 봇 재시작을 권장합니다."
)

# 실패
RESULT_FAIL = (
    "💥 *자동 수정 실패*\n"
    "\n"
    "ID: `{approval_id}`\n"
    "대상: `{target}`\n"
    "오류: `{error_message}`\n"
    "\n"
    "수동 수정이 필요합니다."
)
```

### 4.3 접근성(WCAG) 준수 체크리스트

| 항목 | 기준 | 현황 | 비고 |
|------|------|------|------|
| 텍스트 대체 | WCAG 1.1.1 | ✅ 이모지+텍스트 병기 | 이모지만 단독 사용 금지 |
| 명확한 레이블 | WCAG 2.4.6 | ✅ 버튼 텍스트 명시적 | "✅ 승인 실행" (동사 포함) |
| 오류 방지 | WCAG 3.3.4 | ✅ Confirmation 메시지 | 버튼 클릭 후 확인 전송 |
| 시간 제한 경고 | WCAG 2.2.1 | ✅ 만료 절대시각 명시 | "24시간 내" → 절대시각 변경 |
| 포커스 순서 | WCAG 2.4.3 | ✅ 긍정→부정→보조 순서 | Inline Keyboard 순서 준수 |

### 4.4 엣지 케이스 처리 명세

| 케이스 | 처리 방식 |
|--------|----------|
| 이미 승인된 ID에 재클릭 | "이미 처리된 요청입니다. (status: approved)" |
| 만료된 ID 승인 시도 | "만료된 요청입니다. 동일 신호는 다음 스캔 시 재등록됩니다." |
| 존재하지 않는 ID | "ID를 찾을 수 없습니다. /pending_fixes 로 목록 확인" |
| 동시 다중 대기 (3건 이상) | 우선순위 내림차순 정렬 + 총 건수 헤더 표시 |
| defer 중 만료 시각 도달 | defer 예약 무시, expired 처리 후 "이미 만료" 안내 |

---

## 구현 위임 요약 (engineering_bot 인계 사항)

| 변경 파일 | 변경 내용 |
|----------|----------|
| `core/improvement_bus.py` | `_format_approval_notification()` → `(text, reply_markup)` tuple 반환으로 변경 |
| `core/bot_commands.py` | `callback_query` 핸들러 신규 추가: `approve_*`, `reject_*`, `defer_*` |
| `core/code_improvement_approval_store.py` | `defer()` 메서드 신규 추가 (status=deferred, defer_until 필드) |
| `bots/` (pm_bot or ops_bot) | `send_message()` 호출 시 `reply_markup` 파라미터 전달 |
| `core/scheduler.py` | defer 만료 체크 cron 추가 (1h 간격) |
