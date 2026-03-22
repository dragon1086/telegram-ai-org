# Skills 이관 비교 레포트: telegram_relay / result_synthesizer

> **작성일**: 2026-03-22 | **작성**: aiorg_research_bot (PM) | **태스크**: T-aiorg_pm_bot-275

---

## Executive Summary (1페이지 요약)

**결론: telegram_relay와 task_poller는 Skills 이관이 구조적으로 불가능하다. result_synthesizer는 기술적으로 가능하지만 이관 실익이 없다. → 현행 유지 권고.**

핵심 이유는 하나다. Skills 패턴은 **on-demand, stateless, 단발성 실행**에 최적화된 구조인데,
telegram_relay와 task_poller는 **상시 대기 · 폴링 · 인메모리 상태 관리**가 필수인 프로그램이다.
이 두 요구사항은 구조적으로 양립하지 않는다.

| 프로그램 | 이관 가능 여부 | 핵심 이유 |
|---------|--------------|---------|
| telegram_relay | ❌ 불가 | Long-polling 상시 실행, 4,500줄 복잡 상태 |
| task_poller | ❌ 불가 | 2초 폴링 루프 — Skills에서 장기 루프 실행 불가 |
| result_synthesizer | △ 기술적 가능 | 하지만 이관 실익 없음 (호출자와 강결합) |

---

## Phase 1: 현행 아키텍처 코드 분석

### 1-1. telegram_relay.py

| 항목 | 내용 |
|------|------|
| **코드 규모** | 4,512줄 |
| **진입점** | `main.py` → `TelegramRelay.build()` → `app.run_polling()` |
| **실행 방식** | 상시 실행 Python 프로세스, asyncio 이벤트루프 |
| **트리거 방식** | Telegram Long-Polling (60초 타임아웃, drop_pending_updates=True) |
| **상태 저장** | 인메모리 (5개 상태 딕셔너리) + ContextDB (SQLite/파일) |
| **외부 의존성** | PM_BOT_TOKEN, TELEGRAM_GROUP_CHAT_ID, PM_ORG_NAME, PM_CHAT_REPLY_TIMEOUT_SEC 등 |
| **내부 컴포넌트** | SessionManager, MemoryManager, MessageBus, ClaimManager, ConfidenceScorer, TaskPoller, PMOrchestrator, DiscussionManager, DispatchEngine, P2PMessenger 등 15개+ |

**인메모리 상태 목록:**
```python
self._synthesizing: set          # 합성 중복 방지
self._collab_injecting: set[str] # 협업 주입 중복 방지
self._uploaded_artifacts: set    # 파일 업로드 중복 방지
self._pending_confirmation: dict # 사용자 확인 대기 상태
self._attachment_groups: dict    # 첨부파일 그룹 디바운스 상태
```

**실행흐름 다이어그램:**
```
[텔레그램 메시지]
    ↓ (Long-Polling, 60s timeout)
[TelegramRelay.on_message()]
    ↓
[NLClassifier → Intent 분류]
    ↓
    ├─ PM 오케스트레이터 모드 → PMOrchestrator.route()
    │       ↓
    │   [ContextDB에 subtask 저장]
    │       ↓
    │   [부서봇 TaskPoller가 감지 → _execute_polled_task()]
    │       ↓
    │   [PM_DONE 이벤트 수신 → _handle_pm_done_event()]
    │       ↓
    │   [ResultSynthesizer.synthesize() → 통합 응답]
    │
    └─ 직접 처리 모드 → SessionManager.send_message() → tmux Claude Code
```

---

### 1-2. result_synthesizer.py

| 항목 | 내용 |
|------|------|
| **코드 규모** | 328줄 |
| **진입점** | `TelegramRelay._pm_orchestrator._synthesize_and_act()` 내부에서 호출 |
| **실행 방식** | async 메서드 호출 (await synthesize()), 별도 프로세스 없음 |
| **트리거 방식** | `_handle_pm_done_event()` 또는 fallback 폴러에서 직접 호출 |
| **상태 저장** | Stateless (DecisionClientProtocol만 외부 주입) |
| **외부 의존성** | DecisionClientProtocol (LLM 호출), KNOWN_DEPTS 상수 |
| **에러 처리** | LLM 실패 시 keyword fallback으로 자동 강등 |

**호출 흐름:**
```
_synthesize_and_act()
    └─ ResultSynthesizer.synthesize(original_request, subtasks)
           ├─ _llm_synthesize() → DecisionClient.complete(prompt) [timeout=180s]
           │       └─ _parse_synthesis() → SynthesisResult
           └─ fallback: _keyword_synthesize()  ← LLM 실패 시
```

---

### 1-3. task_poller.py (실행흐름 감지의 핵심)

| 항목 | 내용 |
|------|------|
| **코드 규모** | 151줄 |
| **진입점** | `TelegramRelay.build()` 내부 → `self._task_poller.start()` |
| **실행 방식** | `asyncio.create_task(_poll_loop())` — 백그라운드 asyncio 태스크 |
| **트리거 방식** | **2초 간격 폴링** (DEFAULT_POLL_INTERVAL=2.0s) |
| **상태 저장** | 인메모리 `_processing: set`, `_heartbeat_tasks: dict` |
| **Lease 관리** | ContextDB claim/release (TTL 180초, heartbeat 30초) |
| **에러 복구** | 재시작 시 stale 태스크 자동 복구 (`recover_stale_dept_tasks`) |

---

### 1-4. 외부 의존성 목록

| 의존성 | 사용 프로그램 | 유형 |
|-------|-------------|------|
| `PM_BOT_TOKEN` | telegram_relay | 환경변수 (Telegram API) |
| `TELEGRAM_GROUP_CHAT_ID` | telegram_relay | 환경변수 |
| `PM_ORG_NAME` | telegram_relay | 환경변수 |
| `PM_CHAT_REPLY_TIMEOUT_SEC` | telegram_relay | 환경변수 |
| `ContextDB` | telegram_relay, task_poller | 파일 기반 DB (SQLite) |
| `MessageBus` | telegram_relay | 인메모리 이벤트 버스 |
| `DecisionClientProtocol` | result_synthesizer | LLM API (Claude Code 세션) |
| `/tmp/telegram-ai-org-{org}.pid` | main.py (PID lock) | 파일 시스템 |

---

## Phase 2: Skills 패턴 동작 원리

### 2-1. Skills 트리거 방식

Skills는 Claude Code 에이전트가 SKILL.md의 frontmatter `description`에 있는 키워드를 감지해 자동 호출한다.

```yaml
---
name: pm-task-dispatch
description: "Triggers: 'pm dispatch', '업무배분', ..."
---
```

**트리거 방식**: 사용자 메시지 or 에이전트 판단에 의한 `/skill-name` invoke
**호출 주체**: Claude Code 에이전트 (tmux 세션 내)

### 2-2. Skills 실행환경 제약사항 체크리스트

| 제약 항목 | 가능 여부 | 비고 |
|---------|---------|------|
| 네트워크 접근 | ✅ 가능 | Claude Code 환경 내 |
| 파일시스템 읽기/쓰기 | ✅ 가능 | `--dangerously-skip-permissions` |
| 환경변수 접근 | ✅ 가능 | 세션 환경 상속 |
| **상시 대기 / Long-Polling** | ❌ **불가** | Claude Code 세션 타임아웃 존재 |
| **장기 루프 실행 (2초 폴링)** | ❌ **불가** | blocking loop → 세션 멈춤 |
| **인메모리 상태 영속** | ❌ **불가** | 각 스킬 호출은 독립 실행 |
| AskUserQuestion | ❌ **자율모드 불가** | 무한 대기 → 봇 멈춤 (기록된 이슈) |
| 재시도 메커니즘 | △ 수동 구현 필요 | 스킬 코드 내 try/except |
| 다른 Skills 연계 | △ 순차적 가능 | 병렬 실행은 별도 설계 필요 |

### 2-3. Skills 상태 관리 패턴

현행 13개 스킬 전략 문서 분석 결과:

```
Skills = Stateless 절차 문서 (SKILL.md)
  - 각 호출은 독립적 (이전 호출 컨텍스트 없음)
  - 상태 영속이 필요하면 파일/ContextDB에 직접 기록
  - 에러 처리: gotchas.md에 기록, 수동 fallback
  - 장기 실행: loop-checkpoint 스킬로 상태 저장/재개 (but 연속 실행 보장 없음)
```

**everything-claude-code 패턴과의 연관성:**
SKILL.md + YAML frontmatter 구조는 Claude Code/Codex/OpenCode 공통이며,
프로젝트는 이 패턴을 채택해 17개 스킬을 운용 중.
단, 이 패턴은 **절차 지식(how-to) 캡슐화** 목적이며, 상시 실행 데몬 대체가 아님.

---

## Phase 3: 이관 시나리오 설계 및 갭 분석

### 3-1. telegram_relay → Skills 이관 시나리오

**시나리오**: TelegramRelay 클래스를 `/telegram-relay` 스킬로 교체

**이관 가능 부분:**
- `/setup` 마법사 절차 → SKILL.md 문서화 가능
- 메시지 포맷팅 로직 일부 → 유틸 함수로 추출 가능

**이관 불가 부분 (기술적 사유):**

| 불가 항목 | 기술적 이유 |
|---------|-----------|
| Long-Polling 루프 | Skills는 단발 실행. `app.run_polling()`은 무한 이벤트 루프 — 세션 타임아웃으로 종료됨 |
| 인메모리 상태 5종 | Skills는 stateless. `_synthesizing`, `_attachment_groups` 등을 Skills 간 공유할 방법 없음 |
| 15개+ 내부 컴포넌트 조율 | PMOrchestrator, DiscussionManager, DispatchEngine이 모두 동일 이벤트루프 공유 — Skills에서 이런 내부 객체 그래프 유지 불가 |
| 재시작 복구 | PID lock, stale 태스크 복구 로직이 프로세스 생명주기에 의존 |

→ **이관 불가 판정**

---

### 3-2. task_poller → Skills 이관 시나리오

**시나리오**: TaskPoller의 2초 폴링을 `/task-poller` 스킬 + 외부 cron으로 대체

**이관 가능 부분:**
- 단일 태스크 체크 로직 (`_check_for_tasks`)을 스킬로 추출 가능

**이관 불가 부분:**

| 불가 항목 | 기술적 이유 |
|---------|-----------|
| 2초 폴링 루프 | Skills에서 `while True: await asyncio.sleep(2)` 실행 시 세션 타임아웃 또는 blocking |
| Lease/Heartbeat 관리 | `_heartbeat_tasks` dict이 인메모리 상태 — 스킬 재호출 시 초기화됨 |
| 중복 실행 방지 | `_processing: set`이 인메모리 — cron 기반 시 race condition 발생 |
| 즉각성 | cron 최소 간격은 1분. 현행 2초 대비 30배 지연 발생 |

→ **이관 불가 판정** (cron 대체도 기술적 열화)

---

### 3-3. result_synthesizer → Skills 이관 시나리오

**시나리오**: ResultSynthesizer.synthesize()를 `/result-synthesizer` 스킬로 추출

**이관 가능 부분:**
- synthesize() 로직 전체가 stateless async 메서드 → 기술적으로 이관 가능
- LLM 프롬프트 (`_SYNTHESIS_PROMPT`) → SKILL.md에 절차로 문서화 가능
- keyword fallback 로직 포함

**이관 후 문제점:**

| 문제 항목 | 이유 |
|---------|------|
| 호출자 강결합 | `_synthesize_and_act()`가 직접 `await synthesizer.synthesize()` 호출 — Skills invoke로 교체 시 인터페이스 변경 비용 큼 |
| 성능 오버헤드 | 현재 직접 함수 호출 → Skills invoke 레이어 추가 시 지연 증가 |
| 컨텍스트 전달 | `original_request`, `subtasks` 등 복잡한 dict를 Skills 호출 인터페이스로 직렬화해야 함 |
| 실익 없음 | 328줄의 단순 LLM 호출 컴포넌트를 이관해서 얻는 유지보수 이점이 없음 |

→ **기술적 가능, 실익 없어 이관 불필요 판정**

---

### 3-4. 항목별 갭 분석표

| 비교 항목 | 현행 (독립 프로세스) | Skills 이관 후 | 평가 |
|---------|------------------|--------------|------|
| **유지보수성 — 코드 복잡도** | telegram_relay 4,512줄 (높음), result_synthesizer 328줄 (낮음) | Skills SKILL.md는 절차 문서화로 단순화 가능 | △ result_synthesizer만 개선 여지 |
| **유지보수성 — 배포 편의성** | `request_restart.sh` 한 줄로 배포 | Skills 파일 수정 후 에이전트 재로드 필요 | ○ 현행 유리 |
| **유지보수성 — 디버깅 용이성** | loguru 로그 + PID 추적 | Claude Code 세션 로그만 (구조화 어려움) | × Skills 불리 |
| **실행환경 — 장기 실행** | ✅ 무한 루프 지원 | ❌ 세션 타임아웃 존재 | × Skills 불가 |
| **실행환경 — 폴링 가능 여부** | ✅ 2초 간격 asyncio 폴링 | ❌ 장기 루프 불가 | × Skills 불가 |
| **상태관리 — 세션 유지** | ✅ 인메모리 상태 5종 + ContextDB | ❌ 스킬 호출 간 상태 없음 | × Skills 불가 |
| **상태관리 — 복구** | ✅ stale 태스크 자동 복구 | ❌ 수동 복구 절차 필요 | × Skills 불리 |
| **트리거 방식 — 적합성** | ✅ 이벤트 도착 즉시 처리 | △ on-demand only (능동 감지 불가) | × 이벤트 주도 시스템에 Skills 부적합 |
| **운영 복잡도 — 모니터링** | ✅ PID lock + bot-triage 스킬 | △ 세션 상태 추적 도구 부재 | × Skills 불리 |
| **운영 복잡도 — 장애 대응** | ✅ request_restart.sh + watchdog | △ Skills 실패 시 수동 재호출 필요 | × Skills 불리 |

---

## Phase 4: 최종 비교 레포트 및 권고안

### 4-1. 이관 시 예상 리스크

| 리스크 | 영향도 | 발생 가능성 |
|-------|-------|-----------|
| Long-Polling 단절 | 🔴 Critical | 이관 시 100% 발생 (구조적 불가) |
| 인메모리 상태 소실 | 🔴 Critical | 스킬 재호출 시 100% 발생 |
| 태스크 폴링 지연 (2s→60s+) | 🟠 High | 대체 구현 시 필연적 발생 |
| Race condition (lease 관리 불가) | 🟠 High | 멀티봇 환경에서 태스크 중복 실행 |
| 디버깅 가시성 저하 | 🟡 Medium | 운영 중 이슈 추적 어려워짐 |

---

### 4-2. 장단점 비교 매트릭스

| 항목 | 현행 유지 | Skills 이관 |
|------|---------|-----------|
| Long-Polling 실행 | ○ | × |
| 폴링 루프 | ○ | × |
| 인메모리 상태 관리 | ○ | × |
| Lease/Heartbeat | ○ | × |
| 재시작 복구 | ○ | × |
| 코드 복잡도 감소 | × | △ (result_synthesizer만) |
| 배포 편의성 | ○ | △ |
| 스킬 표준화 통일 | × | ○ |
| 유지보수 일원화 | × | △ |

**종합 점수**: 현행 유지 **8/9** vs Skills 이관 **2/9**

---

### 4-3. 권고안: **현행 유지**

**telegram_relay와 task_poller는 현행 유지가 유일한 올바른 선택이다.**

이유:
1. **Long-Polling은 프로세스 생명주기에 묶여 있다.** Skills는 단발 실행이므로 구조적으로 대체 불가.
2. **2초 폴링은 실시간성의 핵심이다.** cron(최소 1분)이나 on-demand 트리거로 대체하면 부서봇 태스크 감지 지연이 30배 이상 증가한다.
3. **인메모리 상태 5종은 현재 시스템의 동시성 제어 기반이다.** Skills로 이관하면 `_synthesizing`, `_attachment_groups` 등의 중복 방지 로직이 모두 무력화된다.

**result_synthesizer는 현행 유지 권고. 단, 선택적 개선 여지 있음.**

현재 구조(TelegramRelay 내부에서 직접 호출)가 가장 단순하고 효율적이다.
만약 향후 합성 로직이 300줄을 크게 초과하거나, 합성 방식을 다양화해야 할 경우 별도 서비스로 분리하는 것이 Skills보다 낫다.

---

### 4-4. "Skills로 이관이 더 나쁜가?" — 직접 답변

**예, 더 나쁜 선택이다.** 구체적 이유:

- `telegram_relay`: Skills 이관 시 Long-Polling 실행 불가 → 봇 자체가 동작하지 않음
- `task_poller`: Skills 이관 시 실시간 태스크 감지 불가 → 부서봇이 PM 태스크를 수신하지 못함
- `result_synthesizer`: 기술적 가능이나 이관 실익(0)이 이관 비용(인터페이스 변경, 지연 증가)보다 작음

Skills 패턴의 강점은 **절차 지식의 표준화, 재사용, 문서화**에 있다.
실행흐름 감지 프로그램은 **상시 대기, 폴링, 상태 관리**가 필요한 서비스 계층이므로 두 패턴의 사용 목적이 근본적으로 다르다.

---

## 참고: 조사 대상 소스 파일

| 파일 | 규모 | 역할 |
|------|------|------|
| `core/telegram_relay.py` | 4,512줄 | Telegram ↔ Claude Code 중계, 이벤트 핸들링 |
| `core/result_synthesizer.py` | 328줄 | 부서 결과 LLM 합성 |
| `core/task_poller.py` | 151줄 | ContextDB 폴링 → 태스크 감지 |
| `main.py` | 160줄+ | 진입점, PID lock, relay 초기화 |
| `skills/README.md` | — | 17개 스킬 목록 |
| `skills/pm-task-dispatch/SKILL.md` | — | Skills 패턴 대표 예시 |
| `memory/project_skills_strategy.md` | — | Skills 전략 및 AskUserQuestion 금지 이슈 |
