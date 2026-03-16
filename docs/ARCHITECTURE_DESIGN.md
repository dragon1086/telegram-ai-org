# telegram-ai-org 아키텍처 설계 문서

> 생성일: 2026-03-16 | 버전: v2

---

## 1. 시스템 개요

**telegram-ai-org**는 Telegram 그룹 채팅방을 AI 조직의 오피스로 사용하는 **멀티봇 자율 오케스트레이션** 시스템이다.

- **진입점**: Python 봇은 얇은 릴레이 역할, 실제 두뇌는 `tmux` 상주 Claude Code
- **엔진**: `claude-code` (기본) / `codex` (대안)
- **봇 수**: 7개 (PM + 6개 부서봇)
- **채널**: 단일 Telegram 그룹 채팅 (`chat_id: -5203707291`)

---

## 2. 전체 파이프라인 (Mermaid)

```mermaid
flowchart TD
    USER["👤 사용자 (Telegram)"]

    subgraph INFRA["인프라 계층"]
        MAIN["main.py\n(진입점 + PID lock)"]
        RELAY["TelegramRelay\n(Polling + Handler)"]
        BUS["MessageBus\n(내부 pub/sub)"]
        SESSION["SessionManager"]
        MEMORY["MemoryManager"]
    end

    subgraph LLM_ROUTING["LLM 라우팅 계층"]
        ROUTER["PMRouter\n(LLM 기반 의도 분류)"]
        NLC["NLClassifier\n(2-tier 자연어 분류)"]
        DECISION["DecisionClient\n(Claude/Codex 호출)"]
    end

    subgraph ORCHESTRATION["오케스트레이션 계층"]
        ORCH["PMOrchestrator\n(태스크 분해 + 부서 위임)"]
        RUNBOOK["OrchestrationRunbook\n(실행 순서 정의)"]
        DISPATCH["DispatchEngine\n(워커 실행)"]
        SYNTH["ResultSynthesizer\n(결과 종합)"]
    end

    subgraph WORKERS["워커 봇 계층"]
        PM["🤖 PM Bot\n(총괄/조율)"]
        DESIGN["🎨 Design Bot\n(UI/UX)"]
        ENG["💻 Engineering Bot\n(개발/코딩)"]
        GROWTH["📈 Growth Bot\n(성장/마케팅)"]
        OPS["⚙️ Ops Bot\n(운영/인프라)"]
        PRODUCT["📋 Product Bot\n(기획/PRD)"]
        RESEARCH["🔍 Research Bot\n(리서치)"]
    end

    subgraph MEMORY_LAYER["메모리 계층"]
        LESSON["LessonMemory\n(SQLite - 실패 패턴)"]
        PROJ_MEM["ProjectMemory"]
        RETRO["RetroMemory"]
        SHARED["SharedMemory"]
        CONTEXT_DB["ContextDB"]
    end

    subgraph SCHEDULER["스케줄러"]
        SCHED["OrgScheduler\n(APScheduler KST)"]
        STANDUP["🌅 Daily Standup\n09:00"]
        RETRO_JOB["🌙 Daily Retro\n23:30"]
        WEEKLY["📅 Weekly Standup\n월 09:05"]
    end

    USER -->|"메시지 수신"| RELAY
    RELAY --> ROUTER
    ROUTER -->|"LLM 분류"| DECISION
    DECISION -->|"new_task/chat/status_query"| NLC
    NLC -->|"multi_org/single_org/direct"| ORCH
    ORCH --> RUNBOOK
    RUNBOOK --> DISPATCH
    DISPATCH -->|"claude-code engine"| ENG
    DISPATCH -->|"claude-code engine"| RESEARCH
    DISPATCH -->|"claude-code engine"| DESIGN
    DISPATCH -->|"claude-code engine"| GROWTH
    DISPATCH -->|"claude-code engine"| OPS
    DISPATCH -->|"claude-code engine"| PRODUCT
    SYNTH -->|"결과 종합 → Telegram"| RELAY
    RELAY -->|"메시지 전송"| USER
    SCHED --> STANDUP
    SCHED --> RETRO_JOB
    SCHED --> WEEKLY
    ORCH -.->|"기록"| LESSON
    ORCH -.->|"세션"| SESSION
    RELAY -.->|"메모리"| MEMORY
```

---

## 3. 메시지 처리 파이프라인 (상세)

```mermaid
sequenceDiagram
    participant U as 사용자
    participant R as TelegramRelay
    participant PR as PMRouter
    participant NL as NLClassifier
    participant O as PMOrchestrator
    participant D as DispatchEngine
    participant W as WorkerBot(s)
    participant S as ResultSynthesizer

    U->>R: Telegram 메시지
    R->>PR: route(text, context)
    PR->>PR: LLM 호출 (JSON 반환)
    PR-->>R: PMRoute{action, confidence}

    alt action == new_task
        R->>NL: classify(text)
        NL-->>R: Intent{lane, complexity}

        alt multi_org_execution
            R->>O: orchestrate(task)
            O->>O: 태스크 분해 + 부서 선택
            O->>D: dispatch(subtasks[])
            D->>W: Claude Code 실행 (병렬)
            W-->>D: 결과 반환
            D->>S: synthesize(results)
            S-->>R: 종합 보고서
        else single_org_execution
            R->>W: 단일 워커 위임
            W-->>R: 결과
        else direct_reply
            R-->>U: 직접 응답
        end
    end

    R-->>U: 최종 Telegram 메시지
```

---

## 4. LLM 계층 설계

```mermaid
graph LR
    subgraph LLM_LAYER["LLM 요소"]
        SP["StructuredPrompt\n(16KB - 프롬프트 빌더)"]
        LP["LLMProvider\n(API 호출 추상화)"]
        LR["LLMRouter\n(claude-code / codex 선택)"]

        subgraph ENGINES["실행 엔진"]
            CC["claude_code_runner.py\n(Claude Code CLI)"]
            CX["codex_runner.py\n(OpenAI Codex)"]
            AMP["amp_caller.py\n(Amp)"]
        end

        subgraph AGENTS["에이전트 페르소나"]
            AC["AgentCatalog\n(에이전트 목록)"]
            APM["AgentPersonaMemory\n(페르소나 기억)"]
            BCE["BotCharacterEvolution\n(캐릭터 진화)"]
            DTB["DynamicTeamBuilder\n(팀 구성)"]
        end

        subgraph PROMPTS["프롬프트 구조"]
            SYS["시스템 프롬프트\n(role + personality)"]
            INST["instruction (bot YAML)"]
            CTX["context (태스크 + 기억)"]
        end
    end

    LR -->|"route"| CC
    LR -->|"route"| CX
    SP --> SYS
    SP --> INST
    SP --> CTX
    AC --> DTB
    APM --> BCE
```

---

## 5. 봇 설정 구조 (YAML 스키마)

```yaml
# bots/aiorg_*.yaml 구조
schema_version: 2
org_id: aiorg_pm_bot          # 조직 식별자
token_env: PM_BOT_TOKEN       # Telegram 토큰 환경변수
chat_id: -5203707291          # 공유 그룹 채팅 ID
engine: claude-code           # 실행 엔진
dept_name: PM                 # 부서명 (한국어)
role: 프로젝트 총괄/...        # 역할 설명
is_pm: true                   # PM 여부
team_config:
  max_team_size: 5
  guidance: "태스크 분해 후 위임"
# 캐릭터 설정 (LLM 요소)
personality: "전략적이고 체계적"
tone: "명확하고 리더십 있음"
catchphrase: "목표부터 정하자"
strengths: [프로젝트 관리, 팀 조율, 의사결정]
```

---

## 6. 메모리 계층

| 저장소 | 유형 | 목적 |
|--------|------|------|
| `LessonMemory` | SQLite (WAL) | 실패 패턴 기록 + 재발 방지 |
| `ProjectMemory` | 파일 기반 | 프로젝트 장기 기억 |
| `RetroMemory` | 파일 기반 | 회고 기록 |
| `SharedMemory` | 공유 메모리 | 봇 간 상태 공유 |
| `ContextDB` | DB | 태스크 컨텍스트 |
| `AgentPersonaMemory` | 파일 기반 | 에이전트 페르소나 발전 기록 |

---

## 7. 스케줄러 구조

```
OrgScheduler (APScheduler, KST)
├── morning_standup    → 09:00 매일
├── daily_retro        → 23:30 매일
└── weekly_standup     → 09:05 월요일
    + UserSchedule     → 사용자 정의 스케줄 (NL 파싱)
```

---

## 8. 7개 봇 조직도

```mermaid
graph TB
    PM["🤖 aiorg_pm_bot\n총괄 PM"]
    DESIGN["🎨 디자인실\nUI/UX/프로토타입"]
    ENG["💻 개발실\n코딩/API/버그수정"]
    GROWTH["📈 성장실\n마케팅/지표분석"]
    OPS["⚙️ 운영실\n인프라/모니터링"]
    PRODUCT["📋 기획실\nPRD/요구사항"]
    RESEARCH["🔍 리서치실\n시장조사/분석"]

    PM -->|"위임"| DESIGN
    PM -->|"위임"| ENG
    PM -->|"위임"| GROWTH
    PM -->|"위임"| OPS
    PM -->|"위임"| PRODUCT
    PM -->|"위임"| RESEARCH
```

---

## 9. 핵심 파일 맵

| 계층 | 파일 | 역할 |
|------|------|------|
| **인프라** | `main.py` | 진입점, PID lock |
| **인프라** | `core/telegram_relay.py` | Telegram 폴링 + 핸들러 (167KB) |
| **인프라** | `core/message_bus.py` | 내부 pub/sub |
| **LLM** | `core/pm_router.py` | LLM 기반 라우팅 |
| **LLM** | `core/nl_classifier.py` | 자연어 분류 |
| **LLM** | `core/structured_prompt.py` | 프롬프트 빌더 (16KB) |
| **LLM** | `core/llm_provider.py` | LLM API 추상화 |
| **오케스트레이션** | `core/pm_orchestrator.py` | 태스크 분해/위임 (51KB) |
| **오케스트레이션** | `core/orchestration_runbook.py` | 실행 순서 |
| **오케스트레이션** | `core/result_synthesizer.py` | 결과 종합 |
| **봇 설정** | `bots/*.yaml` | 봇 정의 + 캐릭터 |
| **메모리** | `core/lesson_memory.py` | 실패 패턴 SQLite |
| **스케줄러** | `core/scheduler.py` | APScheduler (KST) |
| **툴** | `tools/claude_code_runner.py` | Claude Code CLI |
| **툴** | `tools/codex_runner.py` | Codex CLI |
