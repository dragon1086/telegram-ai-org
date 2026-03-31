# RETRO-26 리서치 보고서: Skills → Hermes 연동 현황 및 개선 방향

**작성일**: 2026-03-31
**리서치실 산출물**: RETRO-26
**대상 범위**: `/skills/` 전수 조사 + `core/` Hermes 3모듈 분석 + 오픈소스 레퍼런스 비교

---

## (a) 핵심 발견 요약

1. **skills/ 디렉토리는 "실행 코드 없는 프롬프트 스킬" 패러다임**
   23개 스킬 중 22개는 `SKILL.md`(LLM 지시문) + `gotchas.md`(재발방지 메모)로만 구성된다. Python/JS 진입점 코드가 없다. 단 2개 예외(pm-progress-tracker, failure-detect-llm, error-gotcha)만 실행 스크립트를 포함.

2. **Hermes 3모듈은 구현 완료되었으나 런타임 비활성 상태**
   `core/tool_registry.py`, `core/platform_adapter.py`, `core/context_compressor.py` 3개 모듈은 완전 구현된 상태이다. 그러나 `main.py`, `bots/`, `core/telegram_relay.py`에서 이 모듈들을 import하는 코드가 **전혀 없다**. `core/hermes_integration.py`라는 연결 레이어도 존재하지만 마찬가지로 런타임에서 호출되지 않는다.

3. **스킬 → 런타임 연결 경로는 단일 경로만 존재**
   현재 유일한 연결 경로는 `core/skill_loader.py` → `core/telegram_relay.py:3658`이다. `build_skill_context(org_id, description)` 호출로 스킬 목록이 시스템 프롬프트에 텍스트로 주입된다. Tool Registry를 통한 프로그래밍적 등록/디스패치 경로는 미사용.

4. **feature flag 기본값이 "true"이지만 호출처가 없어 의미 없음**
   3모듈의 `ENABLE_*` feature flag 기본값이 모두 `"true"`로 설정되어 있으나, 런타임에서 이 모듈들을 초기화하는 코드가 없으므로 플래그 상태와 무관하게 비활성이다.

---

## (b) 현황 진단

### B-1. Skills/ 전수 목록표

| # | 스킬명 | 진입점 유형 | 실행 트리거 방식 | 메타데이터 파일 | 특이사항 |
|---|--------|-------------|-----------------|----------------|---------|
| 1 | autonomous-skill-proxy | SKILL.md (LLM 지시문) | SKILL.md 트리거 문구 | SKILL.md, config.json | config.json: autonomous_mode, fallback_strategy |
| 2 | bot-triage | SKILL.md + scripts/ | SKILL.md 트리거 문구 | SKILL.md, gotchas.md | scripts/diagnose.sh 포함 |
| 3 | brainstorming-auto | SKILL.md | SKILL.md 트리거 문구 | SKILL.md, gotchas.md | |
| 4 | create-skill | SKILL.md | SKILL.md 트리거 문구 | SKILL.md, gotchas.md | |
| 5 | design-critique | SKILL.md | SKILL.md 트리거 문구 | SKILL.md, gotchas.md | |
| 6 | e2e-regression | SKILL.md | SKILL.md 트리거 문구 | SKILL.md, gotchas.md | |
| 7 | engineering-review | SKILL.md | SKILL.md 트리거 문구 | SKILL.md, gotchas.md | |
| 8 | error-gotcha | SKILL.md + scripts/ | SKILL.md 트리거 문구 | SKILL.md, gotchas.md | scripts/run.py 포함 |
| 9 | failure-detect-llm | SKILL.md + scripts/ | SKILL.md 트리거 문구 | SKILL.md, gotchas.md | scripts/run_llm_detect.py |
| 10 | gemini-image-gen | SKILL.md | SKILL.md 트리거 문구 | SKILL.md, gotchas.md | |
| 11 | growth-analysis | SKILL.md | SKILL.md 트리거 문구 | SKILL.md, gotchas.md | |
| 12 | harness-audit | SKILL.md | SKILL.md 트리거 문구 | SKILL.md, gotchas.md | |
| 13 | loop-checkpoint | SKILL.md | SKILL.md 트리거 문구 | SKILL.md, gotchas.md | |
| 14 | performance-eval | SKILL.md | SKILL.md 트리거 문구 | SKILL.md, gotchas.md | |
| 15 | pm-discussion | SKILL.md | SKILL.md 트리거 문구 | SKILL.md, gotchas.md | |
| 16 | pm-progress-tracker | SKILL.md + scripts/run.py | SKILL.md 트리거 문구 + CLI | SKILL.md, skill.md(중복) | scripts/run.py: Python CLI 진입점 — **예외 패턴** |
| 17 | pm-task-dispatch | SKILL.md + config.json | SKILL.md 트리거 문구 | SKILL.md, config.json, gotchas.md | config.json: routing_matrix, chat_id |
| 18 | quality-gate | SKILL.md + scripts/ | SKILL.md 트리거 문구 + PostToolUse hook | SKILL.md, gotchas.md | hooks.PostToolUse.matcher: "Write" |
| 19 | retro | SKILL.md | SKILL.md 트리거 문구 | SKILL.md, gotchas.md | |
| 20 | safe-modify | SKILL.md | SKILL.md 트리거 문구 | SKILL.md, gotchas.md | |
| 21 | skill-evolve | SKILL.md | SKILL.md 트리거 문구 | SKILL.md (only) | gotchas.md 없음 — 최소 구조 |
| 22 | weekly-review | SKILL.md + templates/ | SKILL.md 트리거 문구 | SKILL.md, gotchas.md | templates/ 디렉토리 포함 |
| 23 | _shared | save-log.py | Python CLI | (없음) | 공유 유틸리티 — 스킬이 아님 |

### B-2. 진입점 패턴 분류

**공통 패턴 (21/23개)**:
- 진입점: `SKILL.md` (YAML frontmatter + Markdown 지시문)
- 트리거: frontmatter의 `description` 필드에 명시된 자연어 트리거 문구
- 런타임 연결: `core/skill_loader.py::build_skill_context()` → 시스템 프롬프트 텍스트 주입

**SKILL.md 표준 frontmatter 필드**:
```yaml
name: {skill-name}
description: "... Triggers: '트리거1', '트리거2'"
allowed-tools: Read, Write, Bash  # 선택적
hooks:                             # 선택적 (quality-gate만 사용)
  PostToolUse:
    - matcher: "Write"
      hook: "bash skills/.../script.sh"
```

**예외 패턴 1 — scripts/ 포함 스킬 (4개)**:
- bot-triage, error-gotcha, failure-detect-llm, quality-gate
- Bash 스크립트 또는 Python 스크립트를 SKILL.md 지시문에서 실행 명령으로 참조
- 진입점은 여전히 SKILL.md; 스크립트는 지시문 내 `bash skills/.../run.sh` 형식으로 호출

**예외 패턴 2 — 독립 Python CLI 스킬 (1개)**:
- pm-progress-tracker: `scripts/run.py` — argparse 기반 독립 실행 가능 CLI
- `SKILL.md`와 독립적으로 `python skills/pm-progress-tracker/scripts/run.py status` 형식으로 호출 가능

**예외 패턴 3 — config.json 포함 스킬 (2개)**:
- autonomous-skill-proxy: autonomous_mode, fallback_strategy 설정
- pm-task-dispatch: routing_matrix, chat_id, urgency_keywords — 정적 라우팅 테이블

### B-3. Hermes 3모듈 런타임 연결 현황표

| 모듈 | 위치 | public API | feature flag | 런타임 호출 여부 |
|------|------|-----------|--------------|----------------|
| ToolRegistry | `core/tool_registry.py` | `get_registry()`, `register()`, `unregister()`, `get()`, `get_tools_by_tag()`, `dispatch()`, `list_all()`, `all_tags()` | `ENABLE_TOOL_REGISTRY` (기본 true) | **없음** — 테스트 코드만 |
| PlatformAdapter | `core/platform_adapter.py` | `PlatformAdapter(ABC)`, `TelegramPlatformAdapter`, `register_adapter()`, `get_adapter()`, `list_adapters()`, `InboundMessage`, `OutboundMessage` | `ENABLE_PLATFORM_ADAPTER` (기본 true) | **없음** — 테스트 코드만 |
| ContextCompressor | `core/context_compressor.py` | `get_compressor()`, `compress(messages, max_tokens, keep_last_n)`, `estimate_tokens(text)`, `reset_compressor()` | `ENABLE_CONTEXT_COMPRESSOR` (기본 true) | **없음** — 테스트 코드만 |
| HermesIntegration | `core/hermes_integration.py` | `get_hermes_runtime()`, `on_init(bot_sender)`, `on_message(raw_event)`, `on_teardown()`, `register_hermes_tools(registry)` | 개별 3모듈 플래그 통합 | **없음** — 테스트 코드만 |

**실제 런타임 호출 경로 (skill_loader 전용)**:
```
main.py
  └→ TelegramRelay.__init__()  (core/telegram_relay.py)
       └→ build_skill_context(org_id, description)  [line 3658~3663]
            └→ skill_loader.get_preferred_skills(org_id)
                 └→ SKILL.md frontmatter 읽기 → 텍스트 반환
```

### B-4. 초기화 순서 (설계 vs 현실)

**설계된 초기화 순서** (`hermes_integration.py` 기준):
```
1. HermesRuntime.on_init(bot_sender)
   ├─ ToolRegistry 초기화 (get_registry())
   ├─ register_hermes_tools() → 3개 도구 등록 (handler=None)
   └─ TelegramPlatformAdapter 등록 (register_adapter())
```

**실제 초기화 순서** (`main.py` 기준):
```
1. MemoryManager, MessageBus, SessionManager 생성
2. TelegramRelay 생성 (token, chat_id, engine, bus, ...)
3. relay.run() → telegram bot polling 시작
   [Hermes 3모듈은 어느 단계에서도 초기화되지 않음]
```

---

## (c) 연동 변경 필요 항목 (코드 근거 포함)

### C-1. HermesRuntime.on_init() 호출 누락

**현재**: `main.py`에서 `HermesRuntime`을 전혀 사용하지 않음
**필요**: TelegramRelay 생성 직후 `on_init(bot_sender)` 호출

```python
# main.py 예상 변경 위치: line ~128 이후
from core.hermes_integration import get_hermes_runtime
runtime = get_hermes_runtime()
runtime.on_init(bot_sender=relay.send_message)  # relay.send_message 시그니처 확인 필요
relay.run()
```

**근거**: `core/hermes_integration.py:133` — `on_init()` docstring에 "봇 시작 시 호출"로 명시
**우선순위**: HIGH (연결 레이어 존재 목적 실현)

### C-2. 스킬 → ToolRegistry 등록 브릿지 미구현

**현재**: `skill_loader.py::build_skill_context()`는 SKILL.md를 텍스트로만 읽어 시스템 프롬프트에 주입
**필요**: 스킬을 ToolRegistry에도 등록하여 프로그래밍적 dispatch 가능하게 해야 함

**ToolRegistry.register()에 필요한 필드** (`core/tool_registry.py:80~118`):
```python
registry.register(
    name="pm-task-dispatch",          # SKILL.md frontmatter: name
    description="...",                 # SKILL.md frontmatter: description (첫 문장)
    handler=None,                      # 현재는 None (Phase 1 패턴 유지 가능)
    tags={"skill", "pm", "dispatch"},  # SKILL.md 스킬명에서 파생
    schema={                           # config.json 있으면 변환, 없으면 최소 스키마
        "type": "object",
        "properties": {"task": {"type": "string"}},
        "required": ["task"]
    },
    enabled=True,
)
```

**근거**: `core/tool_registry.py:36~58` (ToolEntry 필드 정의), `core/skill_loader.py:64~79` (load_skill_content — frontmatter 파싱 로직 재사용 가능)
**우선순위**: MEDIUM (텍스트 주입 방식이 현재 정상 동작 중이므로)

### C-3. PlatformAdapter.normalize_inbound() 미활용

**현재**: `core/telegram_relay.py`의 메시지 처리가 python-telegram-bot 객체를 직접 다룸
**필요**: `TelegramPlatformAdapter.normalize_inbound(update)` 호출로 `InboundMessage` DTOs를 생성하면 플랫폼 추상화 완성

**시그니처 변경 필요 범위** (`core/platform_adapter.py:170~220`):
- 입력: `raw_event` — `telegram.Update` 또는 `effective_message` 속성 보유 객체
- 출력: `InboundMessage(platform, message_id, chat_id, sender_id, text, raw, metadata)`
- **기존 코드 변경 없이 선택적으로 적용 가능** (`can_handle()` → `normalize_inbound()` 체인)

**근거**: `core/platform_adapter.py:170~220` (normalize_inbound 구현), `core/platform_adapter.py:263~267` (can_handle: telegram.Update 감지)
**우선순위**: LOW (기능적 가치는 크지만 기존 동작에 영향 없이 점진적 도입 가능)

### C-4. ContextCompressor 미활용

**현재**: `core/context_window.py` 또는 개별 모듈이 독자적인 토큰 제한 처리
**필요**: `get_compressor().compress(messages, max_tokens=8000, keep_last_n=6)` 호출 지점 삽입

**삽입 후보 위치**: `core/telegram_relay.py`의 LLM 호출 직전 (messages 리스트 구성 이후)
**입출력 구조** (`core/context_compressor.py:107~181`):
- 입력: `list[{"role": str, "content": str}]`
- 출력: 같은 형식, 압축됨 (system + keep_last_n 보존, older 예산 내 선택)

**근거**: `core/context_compressor.py:107` (compress 시그니처)
**우선순위**: LOW (현재 기능 손실 없음, 장기 대화 품질 개선 효과)

### C-5. scripts/ 스킬의 handler 연결 방식 미정의

**현재**: bot-triage/scripts/diagnose.sh 등은 SKILL.md 지시문에서 `bash skills/...` 명령으로만 참조
**필요**: 프로그래밍적 디스패치 시 `handler=subprocess.run(["bash", "skills/.../run.sh"])` 패턴 정의 필요

**근거**: `core/tool_registry.py:186~221` (dispatch() — handler 직접 호출)
**우선순위**: LOW (스킬 수동 트리거 방식이 현재 유효)

---

## (d) 오픈소스 레퍼런스 비교표

### D-1. 비교 대상 3개 프레임워크 요약

| 항목 | LangChain | Microsoft Semantic Kernel | CrewAI |
|------|-----------|--------------------------|--------|
| **버전/시점** | 최신 (langchain-core) | 2025 GA | 2025 |
| **스킬/툴 등록 방식** | `@tool` 데코레이터 / `StructuredTool.from_function()` / `BaseTool` 서브클래싱 | `@kernel_function` 데코레이터 + `KernelPlugin` | `BaseTool` 서브클래싱 + `@tool` 데코레이터 |
| **등록 단위** | 함수 단위 | 클래스(Plugin) → 메서드(Function) | 클래스(Tool) / 함수 |
| **메타데이터** | 함수명 + docstring 자동 추출, `args_schema: BaseModel` | `description=` 파라미터 + `KernelArguments` | `name`, `description`, `args_schema: BaseModel` |
| **어댑터 인터페이스** | `BaseTool._run(input) → str`, `_arun` async | `KernelFunction.invoke(context)` | `BaseTool._run(input) → str` |
| **컨텍스트 압축/메모리** | `ConversationTokenBufferMemory`, `ConversationSummaryMemory` | `VolatileMemoryStore` / `KernelMemory` | 내장 없음, 외부 연동 |
| **디스패치 방식** | Agent → Tool 선택 (LLM function calling) | Kernel.invoke_async("plugin", "function") | Agent의 tools 리스트 → LLM 선택 |
| **MCP 지원** | 부분 (플러그인 형태) | 지원 예정 | 지원 (MCP 서버 연동) |
| **특징** | 가장 성숙, 생태계 최대 | 엔터프라이즈 친화, 강타입 | 멀티에이전트 협업 특화 |

### D-2. Hermes 설계와 비교

| 비교 축 | 오픈소스 표준 패턴 | Hermes 현재 설계 | 평가 |
|--------|------------------|----------------|-----|
| **스킬 등록 방식** | Python 코드 기반 (데코레이터/서브클래싱) | YAML frontmatter + LLM 지시문 (SKILL.md) | Hermes는 LLM-native 패러다임 — 코드 스킬 불필요한 경우 더 가볍다 |
| **어댑터 추상화** | 플랫폼별 어댑터 클래스 계층 | `PlatformAdapter ABC` + `TelegramPlatformAdapter` | **동일한 패턴** 채택 — 설계 방향 올바름 |
| **Tool 메타데이터** | name + description + JSON schema | `ToolEntry(name, description, tags, schema, handler)` | **동일 수준** — tags 필드가 추가적 차별화 |
| **컨텍스트 압축** | 전용 Memory 클래스 (LangChain) 또는 KernelMemory | `ContextCompressor` (3계층 우선순위 압축) | **유사한 설계** — system 메시지 보존 + keep_last_n은 베스트 프랙티스 |
| **디스패치** | LLM function calling 또는 코드 기반 router | `ToolRegistry.dispatch(name, **kwargs)` | 현재 LLM 기반(skill_loader) + 코드 기반(tool_registry) 이중화 가능하나 통합 미완 |
| **MCP 지원** | CrewAI/AutoGen: 지원 방향 | 미지원 | 미래 확장 고려 필요 |

### D-3. 벤치마킹 포인트

1. **LangChain의 점진적 호환성 전략 참고**: "BaseTool ↔ StructuredTool 하위 호환" 패턴처럼, Hermes도 `SKILL.md` 텍스트 주입 방식과 `ToolRegistry` 프로그래밍 방식을 공존시키는 점진적 마이그레이션 가능

2. **Semantic Kernel의 Plugin-Function 2계층 참고**: 스킬을 Plugin(스킬 디렉토리) → Function(개별 기능) 2계층으로 구조화하면 `pm-task-dispatch` 같은 복합 스킬의 기능별 디스패치 가능

3. **CrewAI의 args_schema Pydantic 모델 참고**: 현재 `config.json`(routing_matrix 등)을 `args_schema`로 정식화하면 Tool Registry와 자동 통합 가능

### D-4. Hermes 차별점

- **LLM-native 스킬 정의**: SKILL.md 방식은 코드 없이 LLM에게 직접 지시문을 전달 — 오픈소스 프레임워크에서 유사한 패턴은 AutoGen Studio의 "skill as Python docstring"이 가장 가깝지만 완전한 마크다운 런북 형식은 독자적
- **gotchas.md 패턴**: 재발방지 학습 메모를 스킬과 동거시키는 구조 — 오픈소스에서 직접 대응하는 패턴 없음 (CrewAI의 memory와 유사하나 스킬 디렉토리 내 정적 문서로 관리하는 방식은 독창적)
- **organizations.yaml 기반 스킬 배정**: 조직별로 preferred_skills를 선언적으로 배정 — Semantic Kernel의 KernelPlugin per-agent 할당과 개념적으로 동일하나 YAML 선언형으로 더 운영 친화적

---

## (e) 권고사항

### 우선순위 1 (즉시 실행 권장): HermesRuntime 활성화

`main.py`에 `get_hermes_runtime().on_init(bot_sender=...)` 호출 1줄 추가로 Tool Registry + Platform Adapter가 즉시 활성화된다. 기존 코드 변경 없이 점진적으로 적용 가능하며, feature flag가 이미 true 기본값으로 설정되어 있어 추가 설정 불필요.

**예상 작업량**: 3줄 추가 (import + on_init 호출 + on_teardown 호출)

### 우선순위 2 (단기): skill_loader → ToolRegistry 브릿지 구현

`skill_loader.py::build_skill_context()` 실행 시 ToolRegistry에도 스킬을 동시 등록하는 `_register_skill_to_registry(name, frontmatter)` 내부 함수 추가. handler=None으로 시작해 Phase 2에서 실제 핸들러 연결.

**예상 작업량**: skill_loader.py 20~30줄 추가

### 우선순위 3 (중기): config.json → args_schema 정식화

pm-task-dispatch의 `config/routing_matrix`, autonomous-skill-proxy의 `config.json`을 ToolRegistry의 `schema` 필드로 통합. CrewAI의 args_schema Pydantic 모델 패턴 참고.

### 우선순위 4 (장기): ContextCompressor 주입 지점 결정

`core/telegram_relay.py`의 LLM 호출 직전에 `get_compressor().compress()` 삽입. 단, 현재 `context_window.py`와의 중복 처리 여부 확인 후 진행 (코드 베이스 중복 제거 필요).

### 우선순위 5 (장기): MCP 레이어 검토

CrewAI, AutoGen이 MCP(Model Context Protocol) 방향으로 수렴하고 있어, Hermes의 PlatformAdapter → MCP Client Adapter 확장 가능성을 설계 단계에서 검토할 것.

---

## 참고: 조사 파일 경로 목록

- `/Users/rocky/telegram-ai-org/core/tool_registry.py` — ToolEntry, ToolRegistry, get_registry()
- `/Users/rocky/telegram-ai-org/core/platform_adapter.py` — PlatformAdapter, TelegramPlatformAdapter, InboundMessage, OutboundMessage
- `/Users/rocky/telegram-ai-org/core/context_compressor.py` — ContextCompressor, compress(), estimate_tokens()
- `/Users/rocky/telegram-ai-org/core/hermes_integration.py` — HermesRuntime, register_hermes_tools()
- `/Users/rocky/telegram-ai-org/core/skill_loader.py` — build_skill_context(), get_preferred_skills()
- `/Users/rocky/telegram-ai-org/core/telegram_relay.py:3658` — skill_loader 호출 유일 지점
- `/Users/rocky/telegram-ai-org/main.py` — 런타임 진입점 (Hermes 호출 없음 확인)
- `/Users/rocky/telegram-ai-org/skills/` — 23개 스킬 디렉토리 전수 조사 완료

---

*Sources:*
- [LangChain Tools Complete Guide 2025](https://latenode.com/blog/langchain-tools-complete-guide-creating-using-custom-llm-tools-code-examples-2025)
- [Plugins in Semantic Kernel | Microsoft Learn](https://learn.microsoft.com/en-us/semantic-kernel/concepts/plugins/)
- [CrewAI Tools Documentation](https://docs.crewai.com/en/concepts/tools)
- [AutoGen Agent Framework](https://github.com/microsoft/autogen)
- [Semantic Kernel + AutoGen = Microsoft Agent Framework](https://visualstudiomagazine.com/articles/2025/10/01/semantic-kernel-autogen--open-source-microsoft-agent-framework.aspx)
