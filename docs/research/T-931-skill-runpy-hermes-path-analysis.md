# 스킬 run.py 전수조사 + Hermes 실행 경로 분석 보고서

**태스크**: T-aiorg_pm_bot-931
**작성**: 리서치실 PM
**작성일**: 2026-03-31
**조사 범위**: skills/ 24개 스킬 전수 + core/hermes_integration.py, tool_registry.py, platform_adapter.py

---

## 결론

**run.py 추가 = Hermes 우회 방지가 아니다.** 현재 Hermes는 스킬 run.py를 전혀 호출하지 않으며, 두 시스템은 완전히 분리되어 있다. run.py가 있는 스킬도 Claude Code(LLM)가 직접 `python scripts/run.py` 명령으로 실행할 뿐, Hermes 경로를 거치지 않는다. Hermes 연동은 `tool_registry.handler` 함수 교체가 필요한 별도 작업이다.

---

## Phase 1: run.py 전수조사 분류표

### 전체 스킬 목록 (24개)

| # | 스킬명 | run.py | 비고 |
|---|--------|--------|------|
| 1 | autonomous-skill-proxy | ❌ 없음 | SKILL.md + config.json |
| 2 | bot-triage | ❌ 없음 | scripts/: diagnose.sh, run.sh (쉘만) |
| 3 | brainstorming-auto | ❌ 없음 | SKILL.md만 |
| 4 | create-skill | ❌ 없음 | SKILL.md만 |
| 5 | design-critique | ❌ 없음 | SKILL.md만 |
| 6 | e2e-regression | ❌ 없음 | SKILL.md만 |
| 7 | engineering-review | ❌ 없음 | SKILL.md만 |
| 8 | **error-gotcha** | ✅ **있음** | scripts/run.py (CLI 도구) |
| 9 | failure-detect-llm | ❌ 없음 | scripts/run_llm_detect.py (이름 다름) |
| 10 | gemini-image-gen | ❌ 없음 | SKILL.md만 |
| 11 | growth-analysis | ❌ 없음 | SKILL.md만 |
| 12 | harness-audit | ❌ 없음 | SKILL.md만 |
| 13 | loop-checkpoint | ❌ 없음 | SKILL.md만 |
| 14 | performance-eval | ❌ 없음 | SKILL.md만 |
| 15 | pm-discussion | ❌ 없음 | SKILL.md만 |
| 16 | **pm-progress-tracker** | ✅ **있음** | scripts/run.py (목표 추적 CLI) |
| 17 | pm-task-dispatch | ❌ 없음 | SKILL.md + config.json |
| 18 | quality-gate | ❌ 없음 | scripts/: lint-only.sh, run.sh (쉘만) |
| 19 | retro | ❌ 없음 | SKILL.md만 |
| 20 | safe-modify | ❌ 없음 | SKILL.md만 |
| 21 | skill-evolve | ❌ 없음 | SKILL.md만 |
| 22 | weekly-review | ❌ 없음 | SKILL.md + templates/ |
| 23 | _shared | — | save-log.py (공유 유틸, 스킬 아님) |
| 24 | (skills/__init__.py) | — | 패키지 파일, 스킬 아님 |

> **실제 스킬 수**: ls 기준 22개 (autonomous-skill-proxy ~ weekly-review). `_shared`는 공유 유틸 디렉토리.

### 요약

| 분류 | 스킬 목록 | 수 |
|------|-----------|-----|
| **run.py 보유** | error-gotcha, pm-progress-tracker | **2개** |
| **scripts/ 있으나 run.py 없음** | bot-triage (sh), quality-gate (sh), failure-detect-llm (py 다른이름) | **3개** |
| **scripts/ 없음 (SKILL.md 방식)** | 나머지 17개 | **17개** |

---

## Phase 2: Hermes 스킬 실행 경로 분석

### 파일: `core/hermes_integration.py`

#### 핵심 구조

```
HermesRuntime
  ├── on_init(bot_sender)        → ToolRegistry 초기화 + TelegramPlatformAdapter 등록
  ├── on_message(raw_event)      → platform_adapter.normalize_inbound() 위임
  └── on_teardown()              → adapter.on_shutdown() 호출

register_hermes_tools(registry)  → HERMES_TOOL_METADATA 3개 도구 등록
  ├── "hermes_dispatch"          → handler=None ⚠️
  ├── "hermes_compress_context"  → handler=None ⚠️
  └── "hermes_normalize_inbound" → handler=None ⚠️
```

#### 실행 경로 분석

| 질문 | 분석 결과 |
|------|-----------|
| run.py를 직접 subprocess/exec 호출하는가? | **없음** — hermes_integration.py 전체에 subprocess, exec, run.py 참조 코드 없음 |
| tool_registry를 경유하는가? | **경유함** — on_init()에서 get_registry() 호출, register_hermes_tools()로 3개 도구 등록 |
| platform_adapter를 경유하는가? | **경유함** — on_init()에서 TelegramPlatformAdapter 등록, on_message()에서 normalize_inbound() 위임 |
| 스킬 실행 연결점이 있는가? | **없음** — 3개 Hermes 도구 handler=None (Phase 1 스켈레톤 상태) |

#### 핵심 발견: handler=None 문제

```python
# hermes_integration.py:255
registry.register(
    name=meta["tool_name"],
    description=meta["description"],
    handler=None,  # Phase 1: no-op 핸들러 (Phase 2에서 교체)
    ...
)
```

Hermes는 ToolRegistry에 도구를 등록하지만, 모든 handler가 None이라 `registry.dispatch()` 호출 시 실제 실행이 불가능하다.

---

## Phase 3: tool_registry / platform_adapter 연계 구조

### tool_registry.py 실행 흐름

```
ToolRegistry.dispatch(name, **kwargs)
  → _is_enabled() 확인 (ENABLE_TOOL_REGISTRY env, default=true)
  → _tools[name] 조회
  → entry.enabled 확인
  → entry.handler 확인  ← ⚠️ handler=None이면 여기서 중단 (warning 로그만)
  → handler(**kwargs) 호출  ← 실제 실행 지점
```

**현재 상태**: Hermes가 등록한 3개 도구 모두 `handler=None` → `dispatch()` 호출 시 warning 로그만 출력, 실제 실행 없음.

### platform_adapter.py 역할

platform_adapter는 **메시지 정규화** 담당. 스킬 실행과 직접 연결점 없음.

```
TelegramPlatformAdapter.normalize_inbound(raw_event)
  → Telegram Update → InboundMessage(platform, chat_id, sender_id, text, ...)

TelegramPlatformAdapter.send_message(OutboundMessage)
  → bot_sender(chat_id, text, parse_mode, ...)
```

### 스킬 실행 흐름 다이어그램 (텍스트)

#### 현재 방식 (SKILL.md → LLM 주입)

```
사용자 메시지
    │
    ▼
telegram_relay.py / bot_message_handler.py
    │
    ▼
메시지 파싱 → 스킬 트리거 감지 (/quality-gate, /error-gotcha 등)
    │
    ▼
Claude Code (LLM) 컨텍스트에 SKILL.md 내용 주입
    │
    ▼
LLM이 SKILL.md 지시에 따라 단계별 실행
    │
    ├── (run.py 있는 스킬) → python skills/X/scripts/run.py 직접 호출
    └── (run.py 없는 스킬) → LLM 자체가 파일 읽기/쓰기/검색 실행
```

#### Hermes 연동 후 예상 경로 (현재 미구현)

```
사용자 메시지
    │
    ▼
HermesRuntime.on_message(raw_event)
    │
    ▼
platform_adapter.normalize_inbound() → InboundMessage
    │
    ▼
tool_registry.dispatch("hermes_dispatch", task_id=..., target_org=..., message=...)
    │
    ▼
handler 함수 실행 ← ⚠️ 현재 None (미구현)
```

### 엔트리포인트 파일 목록

| 방식 | 파일 | 스킬 |
|------|------|------|
| SKILL.md (LLM 주입) | skills/*/SKILL.md | 전체 22개 |
| Python CLI | skills/error-gotcha/scripts/run.py | error-gotcha |
| Python CLI | skills/pm-progress-tracker/scripts/run.py | pm-progress-tracker |
| Python (다른이름) | skills/failure-detect-llm/scripts/run_llm_detect.py | failure-detect-llm |
| Shell Script | skills/bot-triage/scripts/run.sh | bot-triage |
| Shell Script | skills/quality-gate/scripts/run.sh | quality-gate |
| ToolRegistry handler | (미구현) | Hermes 3개 도구 |

---

## Phase 4: 통합 분석 및 핵심 인사이트

### 핵심 질문 답변: "run.py 추가 = Hermes 우회 방지?"

**결론: 반대다.** run.py는 Hermes와 무관하다.

| 항목 | run.py 방식 | Hermes tool_registry 방식 |
|------|------------|--------------------------|
| 호출 주체 | Claude Code(LLM)가 직접 | tool_registry.dispatch() |
| 등록 방식 | 없음 (경로 직접 호출) | registry.register(handler=fn) |
| Hermes 경유 | **없음** (완전 우회) | **경유** |
| 현재 동작 | ✅ 작동 | ❌ handler=None (미구현) |

- **run.py를 추가해도** → Claude Code가 직접 실행하는 CLI일 뿐, Hermes는 여전히 우회됨
- **Hermes를 통하려면** → tool_registry에 `handler=실제_함수` 등록이 필요
- run.py는 LLM이 자체 판단으로 실행하는 도구일 뿐, Hermes 연동과 무관

### run.py 없는 스킬의 실행 동작

| 상황 | 예상 동작 |
|------|-----------|
| LLM이 SKILL.md 기반 실행 시 | ✅ 정상 동작 — LLM이 직접 처리 |
| tool_registry.dispatch() 호출 시 | ⚠️ handler=None → warning 로그, 실행 없음 |
| Hermes on_message() 호출 시 | ⚠️ normalize_inbound만 동작, 스킬 실행 없음 |
| fallback 존재 여부 | handler=None → warning 로그만, 오류 전파 없음 (no-op) |

### run.py 추가 전략 권고

run.py 추가가 의미 있는 경우:
1. **CLI 직접 실행 편의** (개발/디버깅 시 `python skills/X/scripts/run.py` 호출)
2. **tool_registry handler로 wrap** → `registry.register(handler=lambda **kw: subprocess.run(['python', 'skills/X/scripts/run.py', ...]))` 형태로 Hermes 연동 가능

Hermes를 통한 스킬 실행을 원하면:
1. `hermes_integration.py`의 `handler=None` 3개를 실제 함수로 교체
2. 봇 시작 코드에 `HermesRuntime.on_init()` 삽입
3. 각 스킬의 tool_registry handler 구현 (run.py 여부와 무관)

---

## 조사 요약

| 항목 | 값 |
|------|-----|
| 전체 스킬 수 | 22개 |
| run.py 보유 | 2개 (error-gotcha, pm-progress-tracker) |
| run.py 미보유 | 20개 |
| Hermes → run.py 직접 호출 경로 | 없음 |
| Hermes → tool_registry 경유 경로 | 있음 (단, handler=None으로 미작동) |
| 현재 스킬 실행 방식 | SKILL.md → LLM 주입 (100%) |

---

*조사 기준: 2026-03-31, main 브랜치 `/Users/rocky/telegram-ai-org/`*
