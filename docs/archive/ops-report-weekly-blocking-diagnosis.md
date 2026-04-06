# 주간보고 수렴 블로킹 근본원인 진단 리포트 (최종판)

> **작성**: 운영실 (aiorg_ops_bot)
> **작성일**: 2026-03-30 (최종 갱신)
> **진단 방식**: 실제 코드 직접 분석 + 환경변수 확인 + 실행 로그 교차 검증
> **대상 이슈**: message_id 3731(수렴 메시지) 이후 각 부서 응답 수신 불가 → 주간보고 수렴 블로킹

---

## 1. 요약 (Executive Summary)

**블로킹 근본원인은 2가지 독립적 결함의 복합 작용입니다.**

- **원인 A (최우선)**: Telethon 세션 파일(`.e2e_session`)이 존재하지 않아 `_collect_dept_responses()`가 즉시 early return → 부서 응답 수집 0건 확정.
- **원인 B (2차)**: GoalTracker registrar가 `goal_tracker=None` 상태로 연결되어 파싱된 17개 조치사항이 전부 noop_dispatch → 실제 부서 실행 트리거 0건.

이 두 원인이 동시에 작동하여 주간보고 수렴 전체가 무효화됩니다.
TELEGRAM_API_ID/HASH 환경변수는 정상 설정되어 있으며, 봇 프로세스 7개 모두 UP 상태입니다. 코드 결함이나 봇 다운은 원인이 아닙니다.

---

## 2. 증거 데이터

### 2-1. Phase 1: 부서별 응답 수신 현황

| 부서 | COLLAB 요청 발송 | 응답 수신 | 상태 | 차단 원인 |
|------|----------------|-----------|------|-----------|
| 🔧 개발실 | ✅ 2026-03-30 00:03:04Z | ❌ 없음 | **미수집** | Telethon 세션 없음 → early return |
| ⚙️ 운영실 | ✅ 2026-03-30 00:03:04Z | ❌ 없음 | **미수집** | 동일 |
| 🎨 디자인실 | ✅ 2026-03-30 00:03:04Z | ❌ 없음 | **미수집** | 동일 |
| 📋 기획실 | ✅ 2026-03-30 00:03:04Z | ❌ 없음 | **미수집** | 동일 |
| 📈 성장실 | ✅ 2026-03-30 00:03:04Z | ❌ 없음 | **미수집** | 동일 |
| 🔍 리서치실 | ✅ 2026-03-30 00:03:04Z | ❌ 없음 | **미수집** | 동일 |

> **확인 근거**: 실행 로그에서 `_collect_dept_responses()` 관련 출력(min_id 기록, 대기 시작 등) 부재.
> `docs/weekly/2026-W14-weekly-meeting.md` — "응답 후 작성 예정" 빈 템플릿으로 저장됨.

### 2-2. Phase 2: 큐·리스너 상태 점검 결과

| 점검 항목 | 현재값 | 정상 여부 | 비고 |
|----------|--------|-----------|------|
| `TELEGRAM_API_ID` | `30080750` | ✅ 설정됨 | `.env` line 32 확인 |
| `TELEGRAM_API_HASH` | `8ed02782...` | ✅ 설정됨 | `.env` line 33 확인 |
| `.e2e_session` 파일 | **존재하지 않음** | ❌ **결함** | `ls .e2e_session*` → no matches |
| Telethon 리스너 코드 | `_collect_dept_responses()` 구현됨 | ✅ 코드 정상 | `scripts/weekly_meeting_multibot.py` L236-323 |
| `COLLECT_TIMEOUT_SEC` | `180s` (기본값) | ✅ 정상 | 환경변수 오버라이드 가능 |
| `min_id` 설정 전략 | `record_on_activation` | ✅ 정상 | 수렴 메시지 이후 min_id 기록 |
| GoalTracker registrar | `goal_tracker=None` | ❌ **결함** | 파싱만 됨, 실제 등록 불가 |
| goal_tracker_dispatch | `goals=0 tasks=0` 지속 | ❌ 비정상 | dispatch.log 전 항목 empty |
| 봇 프로세스 (7개) | 전부 UP | ✅ 정상 | watchdog 감시 중 |

---

## 3. 근본원인 확정

### 코드 흐름도 (run_weekly_meeting 실행 경로)

```
[weekly_meeting_multibot.py] run_weekly_meeting()
│
├─ async with Bot as bot:
│   ├─ Step 1: send_message(opening)                   ← ✅ 정상 전송
│   ├─ Step 2: for dept in DEPARTMENTS:
│   │           send_message(collab_msg, delay=3*i)    ← ✅ 6개 부서 전송 확인
│   ├─ Step 3: asyncio.sleep(20s)
│   └─         send_message(convergence_msg)           ← ✅ message_id ~3731 전송
│ (Bot 컨텍스트 종료)
│
├─ _collect_dept_responses(collect_sec=180)
│   ├─ TELEGRAM_API_ID=30080750 ✅
│   ├─ TELEGRAM_API_HASH 설정됨 ✅
│   ├─ SESSION_FILE = PROJECT_ROOT/.e2e_session
│   ├─ SESSION_FILE.exists() → False ❌
│   └─ [즉시 return []]  ← ██ 1차 블로킹: 세션 없음 early return
│       print("[weekly_meeting] Telethon 세션 파일 없음 (...) — 수집 생략")
│
├─ collected_responses = []  (0건)
│
├─ _save_meeting_log(year, week_num, date_str, [])
│   └─ "응답 후 작성 예정" 빈 템플릿 저장
│
└─ _register_weekly_meeting_actions(meeting_content)
    ├─ registrar = MeetingActionRegistrar(goal_tracker=None, ...)
    ├─ auto_register_from_report(registrar=registrar)
    │   └─ 17개 조치사항 파싱 완료
    │   └─ registered=0 (goal_tracker=None → 등록 경로 차단)
    │                                        ← ██ 2차 블로킹: goal_tracker 미주입
    └─ run_meeting_cycle(dispatch_func=_dispatch_to_telegram)
        └─ 17개 전부 noop_dispatch (GoalTracker에 등록된 것이 없으므로)
```

### 근본원인 후보 목록

| # | 원인 | 근거 | 가능성 |
|---|------|------|--------|
| **A** | `.e2e_session` Telethon 세션 파일 없음 | `ls .e2e_session*` → no matches. 코드 L255: `SESSION_FILE.exists() → False` 시 즉시 return [] | **CONFIRMED HIGH** |
| **B** | GoalTracker `goal_tracker=None` 주입 | 코드 L447-449: `MeetingActionRegistrar(goal_tracker=None)`. 로그: `registered=0, noop×17` | **CONFIRMED HIGH** |
| **C** | min_id 필터 오설정 | min_id 설정 자체는 정상(`record_on_activation`). 세션 없음이 선행 문제 | **LOW (2차)** |
| **D** | timeout 부족 | COLLECT_TIMEOUT_SEC=180s, 충분. 세션 없으면 timeout 자체가 무의미 | **LOW** |
| **E** | 봇 다운/크래시 | 7개 봇 전부 UP. watchdog 정상. healthcheck 확인됨 | **NOT AN ISSUE** |
| **F** | 메시지 큐 적체 | goal_tracker_dispatch.log: `goals=0 tasks=0` → 큐 비어있음, 적체 아님 | **NOT AN ISSUE** |

---

## 4. 영향 범위

- **주간보고 수렴**: 매주 월요일 09:03 크론 실행 시 **항상 0건 수집** — 모든 부서의 주간보고가 누락됨
- **GoalTracker 조치사항**: 주간회의에서 도출된 17개 조치사항이 **영구 noop** — 실제 부서 실행 트리거 없음
- **goal_tracker_stage_runner**: `goals=0 tasks=0` 지속 — 독립 스케줄러도 빈 상태 유지
- **주간회의 로그**: `docs/weekly/2026-W14-weekly-meeting.md` 매주 빈 템플릿으로 저장됨

---

## 5. 재현 조건

주간보고 블로킹을 **100% 재현**하는 최소 조건:

```
조건 1: .e2e_session 파일이 PROJECT_ROOT에 존재하지 않음
→ _collect_dept_responses()가 즉시 return [] 실행

조건 2: weekly_meeting_multibot.py L447-449에서
        MeetingActionRegistrar(goal_tracker=None) 상태
→ 파싱된 조치사항이 GoalTracker에 등록되지 않음
```

두 조건 중 하나만 존재해도 부분 블로킹, 두 조건 동시 존재 시 완전 블로킹.
**현재 두 조건 모두 충족 상태.**

---

## 6. 권고 조치

### 단기 조치 (즉시 적용 — 코드 수정 불필요)

| 우선순위 | 조치 | 방법 | 예상 효과 |
|---------|------|------|-----------|
| **P0** | Telethon 세션 파일 생성 | `cd ~/telegram-ai-org && .venv/bin/python -c "from telethon.sync import TelegramClient; c=TelegramClient('.e2e_session', API_ID, API_HASH); c.start(); c.disconnect()"` (Rocky 실행 필요 — 전화번호 인증 필요) | `_collect_dept_responses()` 정상 실행 즉시 복구 |
| **P0** | 다음 주 회의 전 세션 유효성 재확인 | 세션 파일 생성 후 `python -c "from telethon import TelegramClient; ..."` 로 `is_user_authorized()` = True 확인 | 세션 만료 재발 방지 |
| **P1** | `WEEKLY_COLLECT_TIMEOUT_SEC` 환경변수 설정 | `.env`에 `WEEKLY_COLLECT_TIMEOUT_SEC=300` 추가 | 응답 수집 대기 시간 여유 확보 |

### 중기 조치 (코드 수정 필요 — 개발실 태스크)

| 우선순위 | 조치 | 코드 위치 | 예상 효과 |
|---------|------|-----------|-----------|
| **P1** | `GoalTracker` 인스턴스를 `_bootstrap_registrar()`로 생성하여 주입 | `weekly_meeting_multibot.py` L396-518, `_register_weekly_meeting_actions()` | 17개 조치사항 실제 GoalTracker 등록 활성화 |
| **P1** | 세션 파일 없음 시 Telegram 경고 알림 추가 | `_collect_dept_responses()` L258-258 early return 직전 | 운영팀이 세션 만료를 즉시 인지 가능 |
| **P2** | Telethon 세션 자동 갱신 체크 크론 추가 | 별도 `scripts/check_telethon_session.py` 신규 작성 | 세션 만료 선제 감지 |
| **P2** | `_bootstrap_registrar()` 를 `_collect_dept_responses()` 실행 전에 호출하도록 순서 조정 | `run_weekly_meeting()` L158-173 | GoalTracker 초기화와 응답 수집 병렬 실행 가능 |
| **P3** | `collected_responses = []` 시 자동 수동 수집 폴백 (Bot API `getUpdates` 활용) | `_collect_dept_responses()` 반환 이후 fallback 로직 추가 | Telethon 세션 없을 때도 부분 수집 가능 |

---

## 7. 권고 조치 요약 슬라이드

| 단계 | 조치 | 담당 | 우선순위 | 기대 결과 |
|------|------|------|---------|-----------|
| **즉시** | Telethon 세션 파일 생성 (전화번호 인증) | Rocky 직접 | P0 | 응답 수집 정상화 |
| **즉시** | `WEEKLY_COLLECT_TIMEOUT_SEC=300` 환경변수 추가 | 운영실 | P0 | 수집 대기 여유 확보 |
| **이번 주** | GoalTracker 인스턴스 `_register_weekly_meeting_actions()`에 주입 | 개발실 | P1 | 조치사항 실제 등록 활성화 |
| **이번 주** | 세션 파일 없음 시 Telegram 경고 발송 | 개발실 | P1 | 운영 가시성 확보 |
| **다음 주** | Telethon 세션 자동 갱신 체크 크론 | 개발실/운영실 | P2 | 세션 만료 재발 방지 |

---

## 8. 정정 사항 (이전 리포트 vs 실제)

이전 진단 리포트(동일 파일 초기 버전)에서 일부 내용이 현재 코드와 불일치합니다.

| 항목 | 이전 리포트 | 실제 현황 |
|------|-------------|-----------|
| 응답 수집 리스너 구현 여부 | "미구현" | ✅ **구현됨** (`_collect_dept_responses()` L236-323) |
| 블로킹 원인 | "리스너 코드 없음" | ❌ **세션 파일 없음** (코드는 있지만 실행 불가) |
| GoalTracker registrar | "완전 미연결" | 연결됨 (`goal_tracker=None`으로 파싱만 가능) |

---

## 참조

- **실행 로그**: `logs/weekly_meeting.log` — 2026-03-30 00:03:04 실행 기록
- **조치사항 로그**: `logs/goal_tracker_dispatch.log` — `goals=0 tasks=0` 반복 확인
- **주간회의 로그**: `docs/weekly/2026-W14-weekly-meeting.md` — 빈 템플릿 확인
- **환경변수**: `.env` L32-33 — TELEGRAM_API_ID/HASH 설정 확인
- **세션 파일**: `.e2e_session` — **존재하지 않음** (직접 확인)
- **코드**: `scripts/weekly_meeting_multibot.py` L236-323, L396-518

---

*최종 작성: 운영실 (aiorg_ops_bot) — 2026-03-30*
*사용 에이전트: engineering-sre, engineering-devops-automator*
