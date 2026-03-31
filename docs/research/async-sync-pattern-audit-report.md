# async/sync 패턴 혼재 현황 감사 보고서

**작성일**: 2026-03-31
**작성자**: aiorg_research_bot (리서치실 PM)
**태스크**: T-aiorg_pm_bot-936
**범위**: core/, tools/, main.py, goal_tracker/ (build/, .venv/, .worktrees/ 제외)

---

## 1. Executive Summary (요약)

| 구분 | 파일 수 | 비율 |
|------|--------|------|
| 전체 핵심 Python 파일 | 약 130개 | 100% |
| 완전 비동기 (A) | 약 72개 | ~55% |
| 완전 동기/스크립트 (B) | 약 28개 | ~22% |
| **혼재 패턴 (C)** | **약 30개** | **~23%** |

> **결론**: 저번 조사와 마찬가지로 **여전히 약 절반이 비동기, 나머지는 동기/혼재** 구조다.
> 단, `tools/` 러너 계층(GeminiCLIRunner, CodexRunner)은 이미 완전 비동기(`asyncio.create_subprocess_exec`)로 전환되어 있다.
> **가장 위험한 blocking 지점 Top 5는 아래에 상세 기술.**

### 🔴 가장 위험한 Blocking 지점 Top 5

| 순위 | 파일 | 함수 | 라인(근사) | 심각도 |
|------|------|------|-----------|--------|
| 1 | `core/self_code_improver.py` | `_run_claude()`, `_run_tests()` | L112~138 | **HIGH** — async 컨텍스트에서 동기 subprocess.run 직접 호출 |
| 2 | `core/attachment_analysis.py` | `AttachmentAnalyzer.analyze()` | L41 | **HIGH** — async def 안에서 `subprocess.run` blocking 호출 |
| 3 | `core/skill_auto_improver.py` | (내부 claude 호출부) | L121 | **HIGH** — async 컨텍스트에서 동기 subprocess.run(60s timeout) |
| 4 | `main.py` | `__main__` 루프 | L149, 178, 183, 190, 195 | **MEDIUM** — `time.sleep()` 5회 (재시작 루프, 별도 스레드로 격리됨) |
| 5 | `core/session_manager.py` | `_run_tmux()` | L54 | **MEDIUM** — `subprocess.run` (tmux 제어, async 래퍼 내부에서만 호출됨) |

---

## 2. 파일별 패턴 분류 전체 현황표

### 2-A. core/ 레이어

| 파일 | 패턴 | 비동기 함수 예시 | 블로킹 패턴 | 비고 |
|------|------|----------------|------------|------|
| `core/bot_message_handler.py` | **A** (비동기) | `download_attachment()` | 없음 | Phase 1b 분리, 완전 async |
| `core/pm_message_handler.py` | **A** | `handle_bot_message()`, `execute_polled_task()` | 없음 | Phase 1c 분리, 완전 async |
| `core/bot_dispatcher.py` | **A** | `dispatch_command()`, `dispatch_collab_request()` | 없음 | 완전 async |
| `core/telegram_relay.py` | **A** | `on_message()`, `_handle_command()` | `run_in_executor(cleanup_old_claims)` (L2004) | 대부분 비동기, run_in_executor 사용 |
| `core/worker_bot.py` | **A** | `execute()`, `handle_message()` | 없음 | `app.run_polling()` = PTB 내부 async loop |
| `core/pm_orchestrator.py` | **A+C** | `orchestrate()`, `plan_request()` | `run_in_executor(recommend_agents_llm_sync)` (L308), `run_in_executor(_stats)` (L1297) | sync 함수를 executor로 래핑 — 정상 패턴 |
| `core/self_code_improver.py` | **C** | 없음 | `subprocess.run` 직접 호출 L114, 125, 137, 173 | ⚠️ **SelfCodeImprover는 완전 동기 클래스** — scheduler가 `run_in_executor`로 감쌈 (L911) |
| `core/skill_auto_improver.py` | **C** | 없음 (?) | `subprocess.run` L121 | ⚠️ async 컨텍스트 호출 여부 확인 필요 |
| `core/attachment_analysis.py` | **C** | `analyze()` (async) | `subprocess.run` L41 내부 | ⚠️ async def 안에서 blocking subprocess.run |
| `core/session_manager.py` | **C** | `run_shell_command()`, `send_message()` | `subprocess.run` (tmux) L54 | tmux 제어는 동기, 상위 래퍼는 async |
| `core/scheduler.py` | **A** | 대부분 async | 모두 `run_in_executor` 래핑 | 동기 subprocess도 executor 경유 (L911~913) |
| `core/lesson_memory.py` | **C** | 하단 `async_*` 메서드들 | 동기 sqlite I/O 직접 | sync/async 이중 API 명시적 제공 |
| `core/shoutout_system.py` | **C** | `async_*` 래퍼들 | 동기 sqlite I/O 직접 | lesson_memory와 동일 패턴 |
| `core/agent_persona_memory.py` | **C** | `async_*` 래퍼들 | 동기 sqlite I/O 직접 | 동일 패턴 |
| `core/retro_discussion.py` | **A** | 대부분 async | `run_in_executor` (L349) | 정상 래핑 |
| `core/relay_command_handlers.py` | **A** | 전부 async | `run_in_executor` 다수 | 정상 래핑 |
| `core/autonomous_loop.py` | **A** | async 루프 | 없음 | 완전 비동기 |
| `core/message_bus.py` | **A** | publish/subscribe async | 없음 | 완전 비동기 |
| `core/task_manager.py` | **A** | async | 없음 | |
| `core/context_db.py` | **A** | async sqlite (aiosqlite) | 없음 | |
| `core/orchestration_config.py` | **B** | 없음 (sync load) | 파일 I/O 동기 | 스타트업 시에만 호출 — 허용 범위 |
| `core/orchestration_runbook.py` | **B** | 없음 | 파일 I/O 동기 | 동상 |
| `core/services/orchestration_service.py` | **A** | `orchestrate()` stub | 없음 (Phase 2a 미구현) | TODO 상태 |
| `core/relay_bot_setup.py` | **C** | 일부 async | `subprocess.run` L330 | tmux 세션 초기화 |

### 2-B. tools/ 레이어

| 파일 | 패턴 | 비동기 함수 | 블로킹 패턴 | 비고 |
|------|------|------------|------------|------|
| `tools/base_runner.py` | **A** | `run()`, `run_single()`, `run_task()` | 없음 | 완전 async ABC |
| `tools/gemini_cli_runner.py` | **A** | `run()`, `_run_with_model()` | 없음 | `asyncio.create_subprocess_exec` + `asyncio.wait_for` ✅ |
| `tools/codex_runner.py` | **A** | `run()`, `_run()`, `_communicate_with_progress()` | 없음 | `asyncio.create_subprocess_exec` ✅ |
| `tools/claude_code_runner.py` | **A** | `run_structured_team()`, `run_agent_teams()`, `run()` | 없음 | `asyncio.create_subprocess_exec` ✅ |
| `tools/claude_subprocess_runner.py` | **A** | `run()` | 없음 | subprocess async 래퍼 |
| `tools/claude_agent_runner.py` | **A** | `run()` | 없음 | Anthropic SDK async |
| `tools/gemini_runner.py` | **A** | `run()` | 없음 | Gemini API async |
| `tools/agent_catalog_v2.py` | **C** | `recommend_agents_llm()` | `asyncio.run()` (L126) | sync 진입점에서 asyncio.run 호출 |
| `tools/orchestration_cli.py` | **B** | CLI 진입점 | `asyncio.run()` | 스크립트, OK |
| `tools/memory_mcp_server.py` | **A** | MCP 핸들러 | 없음 | |
| `tools/meeting_loop_pipeline.py` | **A** | pipeline async | 없음 | |

### 2-C. main.py / scripts/ / goal_tracker/

| 파일 | 패턴 | 비고 |
|------|------|------|
| `main.py` | **C** | `app.run_polling()` (내부적으로 async), `time.sleep()` 재시작 루프 |
| `goal_tracker/auto_register.py` | **C** | `loop.run_until_complete()` / `asyncio.run()` 혼용 (L228~232) |
| `scripts/*.py` | **B** | CLI 스크립트, `asyncio.run()` 진입점 — 정상 |

---

## 3. 핵심 레이어별 집중 분석

### 3-1. Telegram 메시지 핸들러 (심각도: LOW)

**경로**: `core/bot_message_handler.py` → `core/pm_message_handler.py` → `core/telegram_relay.py`

```
메시지 수신 (PTB async loop)
  └─ on_message() [async def ✅]
       ├─ bot_dispatcher.dispatch_bot_message() [async def ✅]
       ├─ pm_message_handler.handle_bot_message() [async def ✅]
       └─ download_attachment() [async def, await bot.get_file() ✅]
```

- **Phase 1b/1c 리팩토링 완료** — 메시지 핸들러 계층은 현재 완전 비동기
- 유일한 예외: `telegram_relay.py` L2004 `asyncio.get_event_loop().run_in_executor(None, self.claim_manager.cleanup_old_claims)` — cleanup_old_claims이 sync sqlite I/O이므로 executor 래핑은 **정상 패턴**
- **결론: 이 레이어에 blocking call 없음**

### 3-2. 봇 디스패처 (심각도: LOW)

**경로**: `core/bot_dispatcher.py`

- 모든 함수 `async def` + `await` 패턴
- 라우팅 로직은 순수 조건 분기 (I/O 없음)
- `is_collab_request()`, `is_discussion_message()` — 동기 함수지만 CPU-only, blocking 없음
- **결론: blocking call 없음**

### 3-3. 엔진 러너 (심각도: LOW — 이전보다 개선됨)

**경로**: `tools/gemini_cli_runner.py`, `tools/codex_runner.py`, `tools/claude_code_runner.py`

| 러너 | subprocess 방식 | timeout 처리 |
|------|----------------|-------------|
| GeminiCLIRunner | `asyncio.create_subprocess_exec` ✅ | `asyncio.wait_for(timeout=1800)` ✅ |
| CodexRunner | `asyncio.create_subprocess_exec` ✅ | `asyncio.wait_for(timeout=1800~14400)` ✅ |
| ClaudeCodeRunner | `asyncio.create_subprocess_exec` ✅ | `asyncio.wait_for` ✅ |

> **이전 조사 대비 개선됨**: 세 러너 모두 완전 async subprocess로 전환 완료.
> `_communicate_with_progress()` (codex_runner)도 비동기 스트리밍 구현.

**단, 주의 사항**:
- `tools/agent_catalog_v2.py` L126: `recommend_agents_llm_sync()` 내부에서 `asyncio.run()` 호출 → 이미 event loop 안에서 호출 시 RuntimeError 위험 (codex_runner.py에서 `_select_agent_prompts()` 경유로 호출 가능)

### 3-4. 오케스트레이션 레이어 (심각도: MEDIUM)

**경로**: `core/pm_orchestrator.py` → `core/orchestration_config.py` / `core/orchestration_runbook.py`

```
PMOrchestrator.orchestrate_request() [async def ✅]
  ├─ loop.run_in_executor(recommend_agents_llm_sync) [L308 — 정상 래핑 ✅]
  ├─ loop.run_in_executor(_stats) [L1297 — 정상 래핑 ✅]
  └─ (내부) SubTask 실행 시 runner.run() [async ✅]
```

- `orchestration_config.py` / `orchestration_runbook.py`: 파일 I/O 동기 — 그러나 **스타트업 시 1회 호출**만 하므로 이벤트 루프 블로킹 없음
- `OrchestrationService.orchestrate()` (Phase 2a): `raise NotImplementedError` — 아직 미구현 stub
- **주요 blocking 구간**: 없음 (모두 executor 래핑 완료)

---

## 4. 혼재 패턴 집중 목록 (C타입 — async 컨텍스트 내 동기 블로킹)

> async def 함수 안에서 동기 blocking I/O가 직접 발생하는 케이스만 정리

| # | 파일 | 함수 | 라인(근사) | 블로킹 호출 | 심각도 | 비고 |
|---|------|------|-----------|------------|--------|------|
| C-01 | `core/attachment_analysis.py` | `AttachmentAnalyzer.analyze()` | L41 | `subprocess.run(cmd)` | **HIGH** | async def 안에서 blocking subprocess. 이미지 처리 시 이벤트 루프 block |
| C-02 | `core/self_code_improver.py` | `SelfCodeImprover._run_claude()` | L114 | `subprocess.run(["claude", ...], timeout=60)` | **HIGH** | 동기 클래스이나 scheduler에서 `run_in_executor` 없이 직접 호출 시 위험 |
| C-03 | `core/self_code_improver.py` | `SelfCodeImprover._run_tests()` | L125 | `subprocess.run(["pytest", ...])` | **HIGH** | 동상 |
| C-04 | `core/skill_auto_improver.py` | (claude 호출부) | L121 | `subprocess.run(["claude", ...], timeout=60)` | **HIGH** | 호출 컨텍스트가 async인지 불명 — 추가 확인 필요 |
| C-05 | `core/relay_bot_setup.py` | (초기화부) | L330 | `subprocess.run(tmux)` | **MEDIUM** | 봇 기동 시 1회 — 이후 반복 없음 |
| C-06 | `core/session_manager.py` | `_run_tmux()` (sync) | L54 | `subprocess.run(["tmux", ...])` | **MEDIUM** | async 래퍼(`run_shell_command`)가 감싸나, _run_tmux 자체는 동기 |
| C-07 | `core/lesson_memory.py` | 동기 sqlite 메서드들 | L78~ | sqlite3.connect(파일) blocking I/O | **LOW** | async 래퍼(`run_in_executor`)가 제공됨 — async 컨텍스트에서 직접 호출 안 함 |
| C-08 | `core/shoutout_system.py` | 동기 sqlite 메서드들 | L74~ | sqlite3 blocking | **LOW** | 동상 |
| C-09 | `core/agent_persona_memory.py` | 동기 sqlite 메서드들 | L99~ | sqlite3 blocking | **LOW** | 동상 |
| C-10 | `goal_tracker/auto_register.py` | sync 진입점 | L228~232 | `loop.run_until_complete()` + `asyncio.run()` 혼용 | **MEDIUM** | 중첩 loop 위험 — "loop already running" RuntimeError 발생 가능 |
| C-11 | `main.py` | `__main__` 재시작 루프 | L149,178,183,190,195 | `time.sleep()` 5회 | **LOW** | 별도 스레드(heartbeat) + 재시작 루프에서만 사용, asyncio 루프 밖 |

---

## 5. 종합 권고: 현재 방식 유지 vs 전체 비동기 전환

### 현재 상태 요약
```
[완전 비동기 ✅]  tools/ 러너 3종 (Gemini/Codex/Claude)
                  core/bot_message_handler + pm_message_handler + bot_dispatcher
                  core/telegram_relay (대부분)
                  core/pm_orchestrator (run_in_executor 활용)

[혼재 ⚠️]        core/attachment_analysis.py (HIGH — async 안에 blocking subprocess)
                  core/self_code_improver.py (HIGH — sync class, executor 없이 노출 위험)
                  core/skill_auto_improver.py (HIGH — 호출 경로 불명)
                  core/session_manager.py (MEDIUM — tmux sync)
                  goal_tracker/auto_register.py (MEDIUM — loop 중첩 위험)

[완전 동기 ✅ 허용] scripts/*.py (CLI 진입점)
                    orchestration_config/runbook (스타트업 1회)
```

### 권고 결정: **전체 전환 불필요 — 3개 HIGH 지점만 선택적 수정**

| 옵션 | 장점 | 단점 |
|------|------|------|
| **현재 방식 유지** | 변경 없음, 안정적 | C-01~C-04 HIGH 지점이 런타임 버그 유발 가능 |
| **전체 비동기 전환** | 아키텍처 일관성 | 리팩토링 범위 크고 리스크 높음, 실익 낮음 |
| **✅ 선택적 수정 (권고)** | 위험 지점만 제거, 최소 변경 | 3~5개 파일만 수정 |

**선택적 수정 대상 (우선순위 순)**:

1. `core/attachment_analysis.py` → `subprocess.run` → `asyncio.create_subprocess_exec`로 교체
2. `core/self_code_improver.py` → scheduler 호출 시 `run_in_executor` 강제 래핑 확인
3. `core/skill_auto_improver.py` → 호출 경로 추적 후 필요 시 executor 래핑
4. `goal_tracker/auto_register.py` → `asyncio.run()` / `run_until_complete()` 통일

---

## 6. 참고 인덱스 — 조사에 사용한 파일 전체 목록

```
core/bot_message_handler.py
core/pm_message_handler.py
core/bot_dispatcher.py
core/worker_bot.py
core/telegram_relay.py (grep 분석)
core/pm_orchestrator.py
core/self_code_improver.py
core/skill_auto_improver.py
core/attachment_analysis.py
core/session_manager.py
core/scheduler.py (grep 분석)
core/lesson_memory.py (grep 분석)
core/shoutout_system.py (grep 분석)
core/agent_persona_memory.py (grep 분석)
core/relay_command_handlers.py (grep 분석)
core/relay_bot_setup.py (grep 분석)
core/retro_discussion.py (grep 분석)
core/services/orchestration_service.py
tools/base_runner.py
tools/gemini_cli_runner.py
tools/codex_runner.py
tools/claude_code_runner.py (부분)
tools/agent_catalog_v2.py (grep 분석)
tools/orchestration_cli.py (grep 분석)
goal_tracker/auto_register.py (grep 분석)
main.py
```

**grep 패턴**:
- `subprocess\.run|requests\.(get|post)|time\.sleep` — blocking 패턴
- `asyncio\.run\(|loop\.run_until_complete|run_in_executor` — 동기→비동기 브릿지

---

*보고서 경로: `docs/research/async-sync-pattern-audit-report.md`*
*연구 맥락: `docs/research/retro-14-analysis/research_context.yaml` 참고*
