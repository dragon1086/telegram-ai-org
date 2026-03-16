# Code Review: scheduler.py + telegram_relay.py 통합 검증

**Files Reviewed:** 2 (`core/scheduler.py`, `core/telegram_relay.py`)
**Total Issues:** 7

---

## 1. scheduler.py 전체 흐름 다이어그램

```
TelegramRelay.__init__()
  └─ if self._is_pm_org:
       └─ OrgScheduler(send_text=_sched_send)   # _sched_send → _pm_send_message
            └─ __init__()
                 ├─ self.scheduler = AsyncIOScheduler(timezone="Asia/Seoul")
                 └─ _register_jobs()
                      ├─ morning_standup  → CronTrigger(매일 09:00 KST)
                      ├─ daily_retro      → CronTrigger(매일 23:30 KST)
                      ├─ weekly_standup   → CronTrigger(월요일 09:00 KST)
                      └─ friday_retro     → CronTrigger(금요일 18:00 KST)

TelegramRelay.build_app()
  └─ builder.post_init(self._post_init)   # _org_scheduler가 not None이면 등록

TelegramRelay._post_init()
  └─ if self._org_scheduler is not None:
       └─ self._org_scheduler.start()
            └─ if not scheduler.running: scheduler.start()

각 Job 실행 흐름:
  morning_standup  → scripts.morning_goals.main()        → 내부 Telegram 전송
  daily_retro      → scripts.daily_retro.main()          → 내부 처리
                   → [Phase2] retro_memory.save_daily()   → DB 저장
                   → [Phase3] collaboration_tracker.record() + agent_persona_memory.update_from_task()
  weekly_standup   → scripts.weekly_standup.main()        → 내부 처리
                   → [Phase2] lesson_memory.get_category_stats() → 로그만
                   → [Phase3] agent_persona_memory.get_top_performers() → Telegram 전송
                   → [Phase3] shoutout_system.weekly_mvp() → Telegram 전송
  friday_retro     → scripts.daily_retro 함수들 직접 호출  → Telegram 전송
                   → [Phase2] retro_memory.generate_weekly_report() → 메시지에 추가
                   → [Phase3] bot_character_evolution.evolve_all() → 메시지에 추가
                   → [Phase3] shoutout_system.weekly_mvp() + auto_shoutout()
```

---

## 2. Phase 2/3 연결 현황 표

### Phase 2 모듈

| 모듈 | import 여부 | 실제 호출 여부 | 호출 위치 | 비고 |
|------|-----------|------------|----------|------|
| `retro_memory.RetroMemory` | O (lazy) | O | `daily_retro` (save_daily), `friday_retro` (generate_weekly_report, format_telegram) | 정상 연결 |
| `retro_memory.RetroEntry` | O (lazy) | O | `daily_retro` (인스턴스 생성) | 정상 연결 |
| `lesson_memory.LessonMemory` | O (lazy) | O | `weekly_standup` (get_category_stats) | 로그 출력만, Telegram 미전송 |

### Phase 3 모듈

| 모듈 | import 여부 | 실제 호출 여부 | 호출 위치 | 비고 |
|------|-----------|------------|----------|------|
| `collaboration_tracker.CollaborationTracker` | O (lazy) | O | `daily_retro` (record) | 정상 연결 |
| `agent_persona_memory.AgentPersonaMemory` | O (lazy) | O | `daily_retro` (update_from_task), `weekly_standup` (get_top_performers), `friday_retro` (get_top_performers) | 정상 연결 |
| `shoutout_system.ShoutoutSystem` | O (lazy) | O | `weekly_standup` (weekly_mvp), `friday_retro` (weekly_mvp, auto_shoutout) | 정상 연결 |
| `bot_character_evolution.BotCharacterEvolution` | O (lazy) | O | `friday_retro` (evolve_all, get_evolution_summary) | 정상 연결 |
| `character_system` | X | X | - | **scheduler.py에서 직접 import/호출 없음** |
| `praise_system` | X | X | - | **scheduler.py에서 직접 import/호출 없음** (ShoutoutSystem이 대체 역할 수행 가능) |

---

## 3. 발견된 문제

### By Severity
- CRITICAL: 0
- HIGH: 2
- MEDIUM: 3
- LOW: 2

---

### [HIGH] 월요일 09:00 morning_standup + weekly_standup 동시 실행 — 순서 미보장 + 잠재적 충돌
**File:** `core/scheduler.py:38-55`
**Issue:** `morning_standup`과 `weekly_standup` 모두 월요일 09:00 KST에 트리거됨. APScheduler의 `AsyncIOScheduler`는 동시에 두 코루틴을 `asyncio.create_task`로 실행하므로 실행 순서가 비결정적. 둘 다 Telegram 메시지를 전송하는데 동시 실행 시 메시지 순서가 뒤섞일 수 있고, 공유 리소스(DB, API rate limit)에서 충돌 가능.
**Fix:** `weekly_standup`을 09:05나 09:10으로 변경하거나, `morning_standup`에서 월요일이면 `weekly_standup`을 체이닝 호출하는 방식으로 순차 실행 보장.

---

### [HIGH] `daily_retro` Phase 3 블록에서 `tasks` 변수가 Phase 2 블록의 스코프에 의존 — Phase 2 실패 시 NameError
**File:** `core/scheduler.py:101-118`
**Issue:** Phase 3 블록(line 101-118)에서 `tasks` 변수를 사용하지만, `tasks`는 Phase 2 블록(line 83-100) 안의 `get_today_tasks()` 호출로 생성됨. Phase 2의 `try` 블록이 `get_today_tasks()` 호출 전(예: `from core.retro_memory import RetroMemory` 실패 시)에 예외가 발생하면, `tasks`가 정의되지 않은 상태에서 Phase 3 진입. Python에서는 `try` 블록 안에서 정의된 변수도 블록 탈출 후 유효하지만, import가 먼저 실패하면 `tasks = get_today_tasks()` 라인에 도달하지 못함.

실제 코드 흐름:
```python
# Phase 2 try 블록 (line 83):
try:
    from core.retro_memory import RetroMemory, RetroEntry  # ← 여기서 실패 시
    from scripts.daily_retro import get_today_tasks          # ← 도달 안 됨
    tasks = get_today_tasks()                                # ← tasks 미정의
    ...
except Exception as e2:
    logger.warning(...)  # tasks는 여전히 미정의

# Phase 3 try 블록 (line 108):
for task in tasks:  # ← NameError: name 'tasks' is not defined
```

**Fix:** Phase 3 블록 시작 부분에서 `tasks` 정의 여부 확인 (`tasks = locals().get('tasks') or get_today_tasks()`), 또는 `get_today_tasks()` 호출을 Phase 2/3 공통 영역(outer try 블록 직후)으로 이동.

---

### [MEDIUM] APScheduler misfire_grace_time 미설정 — 장기 프로세스 블로킹 시 job 누락 가능
**File:** `core/scheduler.py:37-61`
**Issue:** `add_job()` 호출 시 `misfire_grace_time`이 지정되지 않음. APScheduler 기본값은 `undefined`(= 무제한 허용)이므로 서버 과부하 시 오래된 job이 뒤늦게 실행될 수 있음. 반대로 명시적으로 짧은 값을 설정하면 의도적 스킵이 가능.
**Fix:** 각 job에 `misfire_grace_time=300` (5분) 정도를 명시하여, 5분 이상 지연된 경우 건너뛰도록 설정.

---

### [MEDIUM] `friday_retro`에서 `from datetime import ..., UTC` — Python 3.11+ 전용
**File:** `core/scheduler.py:170`
**Issue:** `from datetime import datetime, timedelta, timezone, UTC`에서 `UTC`는 Python 3.11에서 추가된 상수. Python 3.10 이하에서는 `ImportError` 발생. 이미 `timezone(timedelta(hours=9))`를 사용하고 있어 `UTC` 자체를 이 함수에서 직접 사용하지 않지만, import 시점에 실패하면 전체 `friday_retro`가 동작 불가.
**Fix:** `UTC`를 import에서 제거하거나, `timezone.utc`를 사용. 또는 프로젝트 최소 Python 버전이 3.11+임을 확인.

---

### [MEDIUM] `_is_pm_org` 판단 로직 — PM bot의 org_id가 KNOWN_DEPTS에 없어야 True
**File:** `core/telegram_relay.py:149`
**Issue:** `self._is_pm_org = ENABLE_PM_ORCHESTRATOR and org_id not in KNOWN_DEPTS`. `KNOWN_DEPTS`는 `load_known_depts()`에서 `is_pm: true`인 봇을 **제외**하고 로드(line 82: `if cfg.get("is_pm"): continue`). 따라서 PM bot(예: `aiorg_pm_bot`)이 yaml에 `is_pm: true`로 설정되어 있으면 KNOWN_DEPTS에 포함되지 않으므로 `_is_pm_org = True`가 됨. 이 로직은 **정상 동작**하지만, `ENABLE_PM_ORCHESTRATOR` 환경변수가 `"0"`(기본값)이면 `_is_pm_org = False`가 되어 OrgScheduler가 생성되지 않음.
**Verdict:** `ENABLE_PM_ORCHESTRATOR=1`이 설정된 환경에서만 스케줄러가 동작함. 환경변수 누락 시 스케줄러 전체가 비활성화됨을 문서화 필요.

---

### [LOW] `_safe_send` 실패 시 로그만 남기고 예외 소멸 — 알림 전달 실패를 감지할 방법 없음
**File:** `core/scheduler.py:229-233`
**Issue:** Telegram 전송 실패 시 `logger.error`만 남기고 예외를 삼킴. 운영 환경에서 Telegram 토큰 만료나 네트워크 장애 시 관리자가 알 수 없음.
**Fix:** 외부 모니터링 연동(예: Sentry, 별도 알림 채널) 또는 연속 실패 카운터를 두어 임계치 초과 시 다른 경로로 알림.

---

### [LOW] `friday_retro`가 `get_today_tasks()`를 호출하지만 주간 집계가 아닌 당일 데이터만 사용
**File:** `core/scheduler.py:173`
**Issue:** 주석에 `# 오늘 기준 — 주간 집계는 별도 구현`이라고 되어 있음. `friday_retro`는 주간 회고인데 오늘 하루의 태스크만 집계. 주간 전체 데이터를 수집하는 별도 함수가 없어 회고 내용이 불완전.
**Fix:** `get_week_tasks()` 같은 함수를 구현하여 월~금 전체 데이터를 수집.

---

## 4. "연결됐다고 했지만 실제론 호출 안 됨" 케이스

| 모듈/기능 | 상태 | 근거 |
|----------|------|------|
| `character_system` (Phase 3 사양) | **scheduler.py에서 직접 호출 없음** | `BotCharacterEvolution`이 대체 역할 수행. `character_system`이라는 별도 모듈이 존재하는지 확인 필요 — glob 결과 해당 파일 없음. |
| `praise_system` (Phase 3 사양) | **scheduler.py에서 직접 호출 없음** | `ShoutoutSystem`이 칭찬 기능을 담당. `praise_system`이라는 별도 모듈 존재 여부 미확인. |
| `lesson_memory` Telegram 전송 | **로그만, 사용자 미전달** | `weekly_standup`에서 `get_category_stats()` 결과를 `logger.info()`로만 출력. Telegram 메시지로는 전송되지 않음. |

**Phase 2/3 실제 연결 요약:** `retro_memory`, `lesson_memory`, `collaboration_tracker`, `agent_persona_memory`, `shoutout_system`, `bot_character_evolution` 모두 import + 호출 확인됨. 다만 `lesson_memory` 결과는 로그에만 남고, 사용자에게 전달되지 않음.

---

## 5. 오류 복원력 평가

| 항목 | 평가 | 근거 |
|------|------|------|
| LLM 호출 실패 시 스케줄러 생존 | **O** | 모든 job에 outer `try/except Exception` 래핑. 실패 시 `_safe_send`로 오류 알림. |
| DB 오류 시 처리 | **O** | Phase 2/3 블록이 별도 `try/except`로 감싸져 있어 DB 오류가 메인 job을 죽이지 않음. |
| 각 job 예외가 다음 실행에 영향 | **O** | APScheduler는 job 예외를 잡고 다음 trigger에서 재실행. `replace_existing=True`로 중복 등록 방지됨. |
| `_safe_send` 실패 시 | **O** | 예외를 삼키고 로그만 남김 — 스케줄러는 계속 동작. |
| 중복 실행 방지 | **O** | `start()`에서 `if not self.scheduler.running:` 체크. |

---

## 6. OrgScheduler 생명주기

| 항목 | 상태 | 근거 |
|------|------|------|
| `start()` 호출 위치 | `_post_init` (telegram_relay.py:2231-2233) | `_post_init`은 `Application.builder().post_init()`로 등록됨 (line 2407-2408) |
| 중복 실행 방지 | **O** | `if not self.scheduler.running:` 가드 (scheduler.py:238) |
| pm_bot 재시작 시 | OrgScheduler **재생성** | `TelegramRelay.__init__`에서 새 `OrgScheduler` 인스턴스 생성. `_post_init`에서 `start()` 재호출. `replace_existing=True`로 job 중복 없음. |
| 종료 처리 | `stop()` 메서드 존재 | `scheduler.shutdown(wait=False)` — 다만 `TelegramRelay`에서 `stop()`을 명시적으로 호출하는 코드는 확인 안 됨. 프로세스 종료 시 APScheduler가 자체 정리. |

---

## Recommendation

**COMMENT** (REQUEST CHANGES에 가까움)

HIGH 이슈 2건은 프로덕션 안정성에 직접 영향:
1. 월요일 09:00 동시 실행 문제는 메시지 순서 혼란 + API rate limit 위험
2. `daily_retro` Phase 2 실패 시 Phase 3에서 `NameError` 발생 가능

이 2건을 수정 후 재검토 권장.
