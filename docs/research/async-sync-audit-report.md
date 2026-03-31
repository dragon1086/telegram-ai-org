# Async/Sync 패턴 혼재 현황 감사 보고서

**작성일**: 2026-03-31
**범위**: `/Users/rocky/telegram-ai-org` 전체 .py 파일 (build/, dist/, .venv/, .worktrees/, tests/, __pycache__ 제외)
**총 대상 파일**: 226개 (프로덕션 코드 기준)

---

## 1. Executive Summary

| 구분 | 파일 수 | 비율 |
|------|---------|------|
| **전체 스캔 파일** | 226 | 100% |
| **A유형** — 완전 비동기 (async/await 위주, blocking 없음) | 103 | 45.6% |
| **B유형** — 위험 혼재 (async def 내부에 blocking call 존재) | 9 | 4.0% |
| **C유형** — 완전 동기 (의도적 동기 모듈, 독립 실행) | 114 | 50.4% |

**HIGH 위험 지점 수**: 9개 파일 내 총 20건의 blocking call

**주요 결론**:
- Telegram 메시지 핸들러 계층, 봇 디스패처, 엔진 러너는 **완전 비동기** (A유형). 핵심 처리 경로는 안전.
- HIGH 위험은 `core/attachment_analysis.py`, `core/session_manager.py`, `goal_tracker/auto_register.py` 3곳에 집중됨.
- `core/scheduler.py`의 subprocess 호출은 `run_in_executor`로 래핑되어 있어 사실상 안전.
- 나머지 B유형(main.py, scripts/bot_watchdog.py)은 의도적 동기 구조(프로세스 수호자, 데몬 스레드).

---

## 2. 파일별 전체 분류표

### 2-A. A유형 — 완전 비동기 (103개)

| 경로 | 주요 비동기 패턴 |
|------|----------------|
| core/telegram_relay.py | async on_message, Application.run_polling, asyncio.create_task |
| core/bot_dispatcher.py | async dispatch_command/dispatch_bot_message |
| core/bot_message_handler.py | async download_attachment, await bot.get_file |
| core/pm_message_handler.py | async handle_bot_message, execute_polled_task |
| core/pm_orchestrator.py | async plan_request, dispatch, on_task_complete |
| core/task_poller.py | asyncio.create_task, async _poll_loop, async _execute_task |
| core/autonomous_loop.py | asyncio.create_task, async run, async _tick |
| core/scheduler.py* | AsyncIOScheduler, async morning_standup, daily_retro 등 |
| core/context_db.py | aiosqlite async/await |
| core/worker_bot.py | async handle_message, execute, run_polling |
| core/relay_command_handlers.py | async on_command_start/status/reset/schedule |
| core/relay_bot_setup.py* | async _set_org_bot_commands, register_all_bot_commands |
| tools/claude_code_runner.py | asyncio.create_subprocess_exec, async run_structured_team |
| tools/codex_runner.py | asyncio.create_subprocess_exec, async run, _run |
| tools/gemini_cli_runner.py | asyncio.create_subprocess_exec, async run |
| tools/gemini_runner.py | async run, aio.models.generate_content |
| tools/claude_agent_runner.py | async run, run_structured_team |
| tools/base_runner.py | async run, run_task, run_structured_team |
| tools/orchestration_cli.py | asyncio.run(orch.plan_request), asyncio.run(upload_file) |
| goal_tracker/goal_tracker_client.py | async create_goal, update_goal, get_active_goals |
| goal_tracker/loop_runner.py | async run_cycle, _run_full_cycle |
| goal_tracker/dispatcher.py | async dispatch_goal, _notify_dispatch |
| goal_tracker/registrar.py | async register_from_event, register_single |
| goal_tracker/multibot_meeting_handler.py | async handle, _collect_bot_reports |
| goal_tracker/meeting_handler.py | async on_message, on_daily_retro_start |
| goal_tracker/auto_register.py* | async auto_register_from_report + loop.run_until_complete |
| scripts/daily_retro.py | async _llm_call, _generate_org_speech, send_telegram |
| scripts/morning_goals.py | asyncio.run(main()), async _generate_goals |
| scripts/daily_metrics.py | asyncio.run(main()), async send_telegram |
| scripts/telethon_listener.py | client.add_event_handler, async handler |
| core/dispatch_engine.py | async on_task_complete |
| core/collab_dispatcher.py | async dispatch |
| core/group_chat_hub.py | async start_meeting |
| core/p2p_messenger.py | async send |
| core/pm_router.py | async route |
| core/result_synthesizer.py | async synthesize |
| core/shared_memory.py | async read/write |
| core/discussion.py | async run |
| core/retro_discussion.py | async run_retro |
| ... (103개 전체) | |

> *주: scheduler.py, relay_bot_setup.py, auto_register.py는 B유형 요소도 포함하여 별도 상세 기재

### 2-B. B유형 — 위험 혼재 (9개) — HIGH 위험

| 경로 | 위험도 | blocking call | 라인번호 |
|------|--------|---------------|---------|
| core/attachment_analysis.py | HIGH | subprocess.run (async def analyze 내 동기 헬퍼 호출) | 41 |
| core/session_manager.py | HIGH | subprocess.run (L:54), time.sleep (L:144) — 동기 tmux 헬퍼 내 |
| goal_tracker/auto_register.py | HIGH | loop.run_until_complete (L:228), asyncio.run (L:232) — 동기 래퍼에서 이벤트 루프 진입 |
| main.py | MEDIUM | time.sleep (L:149,178,183,190,195), threading.Thread (L:150) — 의도적 수호자 루프 |
| core/relay_bot_setup.py | MEDIUM | subprocess.run (L:330), subprocess.Popen (L:350) — 동기 봇 시작 헬퍼 |
| core/scheduler.py | LOW | subprocess.run (L:913) — run_in_executor 래핑으로 안전 |
| scripts/auto_improve_recent_conversations.py | MEDIUM | subprocess.run 다수 (L:247,257,312,352,378,396,445,452,467,541) |
| scripts/bot_watchdog.py | LOW | time.sleep (L:302,345,411,437), subprocess.run (L:289) — 의도적 프로세스 감시자 |
| tools/amp_caller.py | LOW | subprocess.run (L:23) — 단순 which 명령, async query는 create_subprocess_exec 사용 |

### 2-C. C유형 — 완전 동기 (114개, 주요 항목)

| 경로 | 성격 |
|------|------|
| core/orchestration_config.py | YAML 설정 파서, 순수 동기 |
| core/feedback_loop_runner.py | 독립 동기 루프 (time.sleep 포함, 의도적) |
| core/self_code_improver.py | 독립 git/subprocess 실행기 |
| core/skill_auto_improver.py | 독립 subprocess 실행기 |
| scripts/preflight_check.py | 독립 사전 검증 스크립트 |
| scripts/agent_monitor.py | 독립 모니터링 스크립트 |
| scripts/setup_wizard.py | 대화형 설치 마법사 |
| scripts/bot_deploy_healthcheck.py | 배포 헬스체크 |
| scripts/pm_filter_ai_news.py | requests.post 기반 동기 AI 뉴스 필터 |
| scripts/daily_ai_news.py | requests.post + subprocess.run 동기 파이프라인 |
| core/constants.py, core/types.py, core/keywords.py | 순수 상수/타입 정의 |
| core/env_guard.py | 환경 변수 검증 |
| goal_tracker/action_parser.py, report_parser.py, router.py | 순수 파서/라우터 |
| skills/*/scripts/run.py | 독립 스킬 실행기 |
| ... (114개 전체) | |

---

## 3. 4개 레이어별 현황 요약표

### Layer 1: Telegram 메시지 핸들러 계층

| 컴포넌트 | 이벤트 수신 방식 | async 콜백 여부 | 위험도 |
|---------|---------------|----------------|--------|
| `core/telegram_relay.py` (PM봇 메인) | python-telegram-bot `Application.run_polling()` → `MessageHandler(filters.TEXT, self.on_message)` | `async def on_message` — 완전 비동기 | NONE |
| `core/bot_message_handler.py` | python-telegram-bot 핸들러로 위임 | `async def download_attachment`, `await bot.get_file` | NONE |
| `core/bot_dispatcher.py` | 위임 레이어 — dispatcher 패턴 | `async def dispatch_command/dispatch_bot_message/dispatch_collab_request` | NONE |
| `core/pm_message_handler.py` | 위임 레이어 — relay 패턴 | `async def handle_bot_message, execute_polled_task` | NONE |
| `core/worker_bot.py` (Worker봇) | `Application.run_polling()` + `MessageHandler` | `async def handle_message, _handle_assign` | NONE |
| `scripts/telethon_listener.py` | Telethon `client.add_event_handler()` — event-driven | `async def handler` | NONE |

**결론**: 메시지 핸들러 계층은 **100% 비동기** 완료. blocking call 없음.

### Layer 2: 봇 디스패처 계층

| 컴포넌트 | 라우팅 방식 | async 여부 | 위험도 |
|---------|-----------|-----------|--------|
| `core/bot_dispatcher.py` | 텍스트 분류 후 relay 메서드 위임 | `async def dispatch_*` 전체 비동기 | NONE |
| `core/pm_orchestrator.py` | 다중 LLM 호출 + task graph 관리 | `async def plan_request, dispatch, on_task_complete` — 전체 비동기 | NONE |
| `core/task_poller.py` | asyncio.create_task 기반 폴링 루프 | `async def _poll_loop, _check_for_tasks, _execute_task` | NONE |
| `core/dispatch_engine.py` | task graph 완료 이벤트 처리 | `async def on_task_complete` | NONE |
| `core/collab_dispatcher.py` | 협업 요청 라우팅 | `async def dispatch` | NONE |
| `core/relay_command_handlers.py` | /start, /status, /reset 명령 처리 | `async def on_command_*` | NONE |

**결론**: 메시지 라우팅 체인 전체가 **비동기 단일 흐름**. 내부 호출 체인도 await-체이닝으로 일관됨.

### Layer 3: 엔진 러너 계층

| 엔진 | 구현 파일 | 실행 방식 | async 여부 | 위험도 |
|-----|---------|---------|-----------|--------|
| claude-code | `tools/claude_code_runner.py` | `asyncio.create_subprocess_exec` | 완전 비동기 | NONE |
| codex | `tools/codex_runner.py` | `asyncio.create_subprocess_exec` | 완전 비동기 | NONE |
| gemini-cli | `tools/gemini_cli_runner.py` | `asyncio.create_subprocess_exec` | 완전 비동기 | NONE |
| gemini (API) | `tools/gemini_runner.py` | `aio.models.generate_content` (비동기 SDK) | 완전 비동기 | NONE |
| claude (Agent SDK) | `tools/claude_agent_runner.py` | async SDK 호출 | 완전 비동기 | NONE |
| Base runner | `tools/base_runner.py` | 추상 async run/run_task | 완전 비동기 | NONE |

**결론**: 엔진 러너 계층은 **3개 엔진 모두 `asyncio.create_subprocess_exec` 기반**으로 완전 비동기 전환 완료. `subprocess.run` 사용 러너 없음.

### Layer 4: 오케스트레이션 레이어

| 컴포넌트 | 파일 | 파싱/실행 방식 | async 여부 | 위험도 |
|---------|------|--------------|-----------|--------|
| orchestration.yaml 파싱 | `core/orchestration_config.py` | `yaml.safe_load` + 환경변수 확장 | **완전 동기** (C유형) | NONE (의도적) |
| orchestration CLI | `tools/orchestration_cli.py` | `asyncio.run(orch.plan_request(...))` — 진입점만 동기 | 진입점 동기 + 내부 비동기 | LOW |
| orchestration service | `core/services/orchestration_service.py` | `async def orchestrate, cancel_task, get_task_status` | 완전 비동기 | NONE |
| 오케스트레이션 실행 | `core/pm_orchestrator.py` | `async def dispatch, plan_request` | 완전 비동기 | NONE |

**결론**: orchestration.yaml 파싱 자체는 의도적 동기. 실제 태스크 실행 경로(`orchestration_service` → `pm_orchestrator`)는 완전 비동기. CLI 도구(`orchestration_cli.py`)의 `asyncio.run()` 진입점은 정상 패턴.

---

## 4. HIGH 위험 지점 목록

### HIGH-01: core/attachment_analysis.py:41
```
async def analyze(self, attachment: AttachmentContext) -> str:
    ...
    summary = self._analyze_image_with_bridge(...)  # 동기 호출
    → _run_bridge() → subprocess.run([...], timeout=60)  # blocking, 최대 60초
```
- **blocking call 종류**: `subprocess.run` (외부 vision bridge 명령)
- **영향**: Telegram 메시지 처리 이벤트 루프 최대 60초 block. 메시지 첨부파일이 있는 모든 요청에서 발생 가능.
- **위험 시나리오**: 사진/영상 첨부 메시지 다수 동시 수신 시 이벤트 루프 누적 blocking으로 봇 응답 불가.

### HIGH-02: core/session_manager.py:54,144
```
def _run_tmux(self, *args: str) -> str:  # DEPRECATED 주석 있음
    result = subprocess.run(["tmux", ...], timeout=10)  # L:54

def _is_ready_for_input(...) -> bool:
    ...
    time.sleep(0.5)  # L:144, tmux 폴링 루프
```
- **blocking call 종류**: `subprocess.run` (tmux 명령), `time.sleep` (폴링 대기)
- **영향**: `send_message`, `send_to_session`, `_wait_for_output` 등의 async 메서드 내부에서 간접 호출 가능. tmux 세션이 활성인 경우 이벤트 루프 block.
- **위험 시나리오**: tmux 기반 실행 경로 활성화 시 `time.sleep(0.5) × N회` 폴링이 이벤트 루프를 직접 block.
- **완화 요소**: 코드에 "DEPRECATED: tmux-based execution replaced by SDK runners" 주석 존재. 기본 경로는 SDK 러너.

### HIGH-03: goal_tracker/auto_register.py:228,232
```
def register_from_report_sync(...) -> list[str]:  # 동기 래퍼
    try:
        loop = asyncio.get_running_loop()
        ...
        return loop.run_until_complete(  # L:228 — 실행 중인 루프에서 호출 시 RuntimeError
            auto_register_from_report(...)
        )
    except RuntimeError:
        return asyncio.run(...)  # L:232
```
- **blocking call 종류**: `loop.run_until_complete` (실행 중인 이벤트 루프에서 중첩 호출)
- **영향**: 이미 async 컨텍스트 내에서 이 함수가 호출되면 `RuntimeError: This event loop is already running` 발생. concurrent.futures ThreadPoolExecutor 우회 패턴도 사용하고 있으나 deadlock 가능성 존재.
- **위험 시나리오**: scheduler나 pm_orchestrator에서 회의 종료 후 자동 등록 트리거 시, 이미 실행 중인 이벤트 루프에서 loop.run_until_complete 호출 시도 → RuntimeError 또는 deadlock.

### MEDIUM-04: scripts/auto_improve_recent_conversations.py:312 외 다수
```
async def apply_actions(...) -> list[str]:
    ...
    # 비동기 runner 호출 (정상)
    result = await runner.run(RunContext(...))  # 정상

    # 동기 검증 함수 (별도 함수이나 같은 파일)
def run_verification(...) -> list[VerificationResult]:
    proc = subprocess.run(["bash", "-lc", command], ...)  # L:312
```
- **blocking call 종류**: `subprocess.run` (검증 명령 실행)
- **영향**: `run_verification()`은 동기 함수이므로 직접 blocking은 `run_cycle`(async) 내에서 `await loop.run_in_executor` 없이 호출 시 발생. 현재는 별도 함수 경계 존재.
- **위험 시나리오**: `apply_actions`가 `run_verification()`을 직접 호출하도록 리팩토링될 경우 이벤트 루프 blocking.

### MEDIUM-05: core/relay_bot_setup.py:330,350
```
def _refresh_legacy_bot_configs() -> None:  # 동기 함수
    _subprocess.run([...])  # L:330

def _launch_bot_subprocess(...) -> int:  # 동기 함수
    proc = _subprocess.Popen([...])  # L:350
```
- **blocking call 종류**: `subprocess.run`, `subprocess.Popen` (봇 프로세스 시작)
- **영향**: 동기 함수이므로 직접 block 없으나, async context에서 호출 시 blocking.
- **위험 시나리오**: `register_all_bot_commands()`(async)와 같은 파일 내 async 함수가 이 동기 헬퍼를 await 없이 호출하면 문제.

---

## 5. 비동기:동기 혼재 비율 통계

```
전체 프로덕션 파일: 226개
  완전 비동기 (A유형):   103개  (45.6%)
  위험 혼재   (B유형):     9개  (4.0%)
  완전 동기   (C유형):   114개  (50.4%)

비동기:동기 비율 = 45.6% : 50.4%  (거의 1:1)
위험 혼재 비율  = 4.0%  (9 / 226)

핵심 처리 경로 (core/ 디렉토리 단독):
  전체 core/ 파일:       ~87개
  완전 비동기 (A):        ~55개  (63%)
  위험 혼재   (B):         5개  (6%)
  완전 동기   (C):        ~27개  (31%)

tools/ 러너 계층:
  전체:  약 15개
  비동기:  14개  (93%)
  혼재:    1개   (amp_caller.py - LOW 위험)

goal_tracker/ 계층:
  전체:  10개
  비동기:  9개  (90%)
  혼재:   1개   (auto_register.py - HIGH 위험)

scripts/ (배치/운영):
  전체:  29개
  비동기:  19개  (66%)
  혼재:    2개  (bot_watchdog, auto_improve)
  동기:    8개  (33%)
```

---

## 6. blocking call 발생 가능 시나리오

### 시나리오 1: 첨부파일 동시 다수 수신 (attachment_analysis.py)
```
[상황] 여러 사용자가 동시에 사진/영상 첨부 메시지 전송
[경로] telegram_relay.on_message → bot_message_handler.download_attachment
       → AttachmentAnalyzer.analyze() (async)
       → _analyze_image_with_bridge() (동기)
       → _run_bridge() → subprocess.run(VISION_BRIDGE_CMD, timeout=60)

[결과] Telegram PTB 이벤트 루프 내 asyncio task가 blocking subprocess.run으로
       60초 동안 스레드 점유. 동시 요청이 3건이면 180초 잠재 지연.
       이벤트 루프 자체는 single-threaded이므로 다른 메시지 처리도 중단됨.
```

### 시나리오 2: tmux 세션 폴링 중 이벤트 루프 block (session_manager.py)
```
[상황] tmux 기반 실행 경로 활성화 (TMUX_SESSION_ENABLED 환경변수 존재 시)
[경로] pm_orchestrator.dispatch → session_manager.send_message (async)
       → send_to_session → _wait_for_output → _is_ready_for_input
       → time.sleep(0.5) × polling_count  (동기 sleep이 이벤트 루프 block)

[결과] tmux 출력 대기 중 이벤트 루프 완전 정지. 다른 PM 태스크 및
       Telegram keepalive가 중단되어 봇이 "응답 없음" 상태로 보일 수 있음.
       헤드비트 파일 갱신도 중단 → bot_watchdog이 재시작 트리거.
```

### 시나리오 3: 회의 중 auto_register loop.run_until_complete 충돌 (auto_register.py)
```
[상황] 주간 회의(weekly_standup) 완료 직후 액션 아이템 자동 등록 시도
[경로] scheduler.weekly_standup (async) → _register_action_items (async)
       → auto_register.register_from_report_sync (sync 래퍼)
       → asyncio.get_running_loop() → loop.run_until_complete(...)

[결과] 이미 실행 중인 asyncio 이벤트 루프에서 loop.run_until_complete 호출 시
       RuntimeError: This event loop is already running 발생.
       concurrent.futures 우회 경로도 있으나 ThreadPoolExecutor 내에서
       asyncio.run()을 호출하므로 새 이벤트 루프 생성 — 스레드 안전성 검증 필요.
```

### 시나리오 4: daily_retro + auto_improve 동시 실행 (scripts/)
```
[상황] cron으로 daily_retro.py와 auto_improve_recent_conversations.py 동시 실행
[경로 A] daily_retro.py: asyncio.run(main()) — 정상 (독립 프로세스)
[경로 B] auto_improve: apply_actions (async) 내부에서 동기 run_verification 호출 가능성
         → subprocess.run(["bash", "-lc", cmd]) 다수 × 순차 실행

[결과] auto_improve 단독으로는 독립 프로세스이므로 시스템 수준 block 위험 없음.
       그러나 apply_actions 내부에서 run_verification을 직접 호출하도록
       리팩토링 시 async 컨텍스트에서 blocking subprocess.run 실행 위험.
```

### 시나리오 5: bot_watchdog asyncio.run 중첩 호출 (main.py)
```
[상황] 봇 충돌 후 재시작 시 Telegram Conflict 오류 발생
[경로] main.py _run_relay_bot 루프
       → app.run_polling() (blocking call)
       → Conflict 오류 발생
       → asyncio.run(app.shutdown())  # L:174 — 새 이벤트 루프 생성

[결과] run_polling() 자체가 이벤트 루프를 소유하므로, 오류 후 asyncio.run()은
       새 루프 생성 — 이전 루프의 태스크 정리 없이 종료 가능.
       time.sleep(CONFLICT_WAIT=70초) 이후 재시작 — 의도적 패턴이나
       heartbeat 스레드가 동시에 70초간 파일 갱신을 계속함.
```

---

## 7. 전환 권고

### 권고 A: 즉시 수정 필요 (HIGH 위험)

#### A-1. core/attachment_analysis.py — async 변환 (우선순위: CRITICAL)
```python
# 현재 (B유형 HIGH): async def analyze가 동기 _run_bridge 호출
async def analyze(self, attachment: AttachmentContext) -> str:
    summary = self._analyze_image_with_bridge(...)  # 동기 blocking

# 권고: asyncio.get_running_loop().run_in_executor 래핑
async def analyze(self, attachment: AttachmentContext) -> str:
    loop = asyncio.get_running_loop()
    summary = await loop.run_in_executor(None, self._analyze_image_with_bridge, ...)
```
- **이유**: Telegram 이벤트 루프 내에서 최대 60초 blocking 가능. 첨부파일 처리가 봇 전체를 중단시킬 수 있음.

#### A-2. goal_tracker/auto_register.py — 동기 래퍼 제거 (우선순위: HIGH)
```python
# 현재 (B유형 HIGH): 동기 래퍼에서 loop.run_until_complete 사용
def register_from_report_sync(...):
    loop = asyncio.get_running_loop()
    return loop.run_until_complete(auto_register_from_report(...))  # DANGER

# 권고: 동기 래퍼 제거 후 async 전용으로 전환
# 호출부를 모두 await auto_register_from_report(...)로 변경
```
- **이유**: 실행 중인 이벤트 루프에서 loop.run_until_complete는 RuntimeError/deadlock 유발.

#### A-3. core/session_manager.py — tmux 경로 완전 deprecate (우선순위: HIGH)
```python
# 현재 (B유형 HIGH): async 메서드 내부에서 동기 tmux 헬퍼 간접 호출 가능
# 권고: _run_tmux, _is_ready_for_input 등 tmux 동기 헬퍼를 모두 제거하거나
#       asyncio.create_subprocess_exec 기반 비동기 tmux 호출로 교체
```
- **이유**: 코드에 DEPRECATED 주석이 있음에도 tmux 경로가 아직 남아 있어 실수로 활성화 시 time.sleep이 이벤트 루프를 block.

### 권고 B: 선택적 수정 (MEDIUM 위험)

#### B-1. core/relay_bot_setup.py — 봇 시작 함수 async 분리 (우선순위: MEDIUM)
- `_refresh_legacy_bot_configs()`, `_launch_bot_subprocess()`는 동기 함수이므로 async context에서 호출 시 `await loop.run_in_executor()` 래핑 권고.

#### B-2. scripts/auto_improve_recent_conversations.py — subprocess 검증 함수 분리 유지 (우선순위: LOW)
- `run_verification()`은 독립 동기 함수로 유지. `apply_actions`(async) 내에서 직접 호출하지 않도록 호출 경계 명시적 주석 추가 권고.

### 권고 C: 현행 유지 권고 (낮은 위험 또는 의도적 패턴)

| 파일 | 이유 |
|------|------|
| main.py | 프로세스 수호자(watchdog) — 의도적 blocking. threading.Thread + time.sleep은 정상 패턴. |
| scripts/bot_watchdog.py | 외부 프로세스 감시자 — 독립 프로세스 실행. time.sleep은 폴링 주기 제어용. |
| core/scheduler.py:913 | subprocess.run이 run_in_executor로 래핑됨 — 이미 안전. |
| tools/amp_caller.py | `async def query`는 create_subprocess_exec 사용. L:23의 subprocess.run은 초기화 단계 단발성. |
| scripts/pm_filter_ai_news.py | 독립 동기 스크립트. async context 없음. |
| scripts/daily_ai_news.py | 독립 동기 스크립트. async context 없음. |
| core/orchestration_config.py | YAML 파서는 동기가 적절. |
| core/feedback_loop_runner.py | 독립 동기 피드백 루프. asyncio context 외부 실행. |

### 전체 전환 vs 선택적 수정 권고

**선택적 수정 권고** (전체 비동기 전환 불필요):

1. 핵심 처리 경로(Telegram 핸들러 → 디스패처 → 엔진 러너)는 **이미 완전 비동기**. 전체 전환 불필요.
2. HIGH 위험 3곳(`attachment_analysis`, `session_manager`, `auto_register`)만 수정해도 실질적 위험 대부분 제거 가능.
3. C유형 파일(scripts/, 설정 파서, 독립 실행 도구)은 비동기 전환 불필요 — 오히려 `asyncio.run()` 진입점을 유지하는 것이 올바른 패턴.
4. `tools/` 러너 계층은 이미 완전 비동기 — 추가 작업 불필요.

**수정 우선순위 요약**:
```
CRITICAL  : core/attachment_analysis.py  — run_in_executor 래핑
HIGH      : goal_tracker/auto_register.py — 동기 래퍼 제거
HIGH      : core/session_manager.py       — tmux 동기 헬퍼 완전 제거
MEDIUM    : core/relay_bot_setup.py       — subprocess 함수 run_in_executor 래핑
LOW       : scripts/auto_improve_recent_conversations.py — 경계 명시 주석
HOLD      : main.py, bot_watchdog.py, scheduler.py — 현행 유지
```

---

## 부록: 스캔 방법론

**비동기 키워드**: `async def`, `await `, `asyncio`, `aiohttp`, `add_event_handler`, `run_until_disconnected`, `AsyncClient`, `create_subprocess`

**blocking 키워드**: `requests.get`, `requests.post`, `time.sleep`, `subprocess.run`, `subprocess.call`, `threading.Thread`, `loop.run_until_complete`

**유형 판별 로직**:
- `has_async AND has_blocking` → B유형 (HIGH 위험)
- `has_async AND NOT has_blocking` → A유형 (완전 비동기)
- `NOT has_async` → C유형 (완전 동기)
- B유형 중 blocking이 run_in_executor 래핑되어 있거나 동기 래퍼 함수 내에만 존재하는 경우 → 실제 위험도 조정

**파일 제외 범위**: `tests/`, `build/`, `dist/`, `.venv/`, `.worktrees/`, `__pycache__/`, `telegram_ai_org.egg-info/`
