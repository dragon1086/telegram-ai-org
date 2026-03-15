# ARCHITECTURE.md — telegram-ai-org 상세 설계

## 1. 비전

텔레그램 그룹 채팅방을 동적 AI 조직의 오피스로 활용한다.
유저가 방향만 제시하면 PM AI가 LLM으로 최적 팀을 즉석 구성하고 실행한다.
고정된 워커 역할 대신 **21개 에이전트 페르소나**에서 태스크마다 최적 조합을 선택한다.

## 2. 핵심 철학

**동적 팀 구성 (Dynamic Team Composition)**

- 팀 구성은 미리 정해지지 않는다. LLM이 매 요청마다 최적 팀을 결정한다.
- `workers.yaml`은 hint-only다. 실제 실행 팀은 DynamicTeamBuilder가 결정한다.
- `~/.claude/agents/` 페르소나를 재사용한다. 중복 정의 없음.
- 태스크 복잡도에 따라 3가지 실행 모드 중 최적을 선택한다.

## 3. 핵심 컴포넌트

### 3.1 PM Bot (`@pm_bot`)

- **역할**: 오케스트레이터 + 팀 구성 총괄
- **기능**:
  - 유저 요청 수신 → DynamicTeamBuilder로 팀 구성
  - 팀 구성 결과 텔레그램 발표
  - ClaudeCodeRunner로 실행 위임
  - 모든 작업 상태 추적 + 완료 판단
  - answer-first rewrite, attachment-safe upload, smart chunking으로 Telegram 전달 품질 보정
- **모델**: claude-sonnet-4-6

### 3.2 AgentCatalog (`core/agent_catalog.py`) — 신규

- **역할**: `~/.claude/agents/` 디렉토리에서 페르소나 동적 로드
- **기능**:
  - 21개 에이전트 파일 파싱 (이름, 설명, 전문 영역)
  - `recommend(task_description)` — 태스크에 적합한 페르소나 추천 (폴백용)
  - `get_persona(name)` — 특정 페르소나 전체 프롬프트 반환
- **폴백**: DynamicTeamBuilder LLM 호출 실패 시 키워드 매칭으로 추천

### 3.3 DynamicTeamBuilder (`core/dynamic_team_builder.py`) — 신규

- **역할**: LLM 기반 태스크별 팀 구성 결정기
- **기능**:
  - `build_team(task)` → `TeamConfig` 반환
  - LLM 분석: "이 태스크에 어떤 페르소나가 몇 명 필요한가?"
  - 실행 모드 결정: omc_team / agent_teams / sequential
  - omc_team 형식 생성: `/team 2:executor,1:analyst "task"`
- **출력 (`TeamConfig`)**:
  ```python
  @dataclass
  class TeamConfig:
      agents: list[AgentAssignment]  # 페르소나 + 수량
      execution_mode: str            # "omc_team" | "agent_teams" | "sequential"
      omc_team_format: str | None    # "/team 2:executor,1:analyst"
      rationale: str                 # LLM이 설명하는 선택 이유
  ```

### 3.4 ClaudeCodeRunner (`tools/claude_code_runner.py`)

- **역할**: Claude Code CLI 실행 래퍼 (3가지 모드)
- **실행 모드**:

| 모드 | 설명 | 환경 조건 |
|------|------|-----------|
| `omc_team` | `/team N:executor,M:analyst "task"` 형식으로 omc 파이프라인 실행 | oh-my-claudecode 설치 필요 |
| `agent_teams` | `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` 환경변수로 네이티브 팀 실행 | 실험적 기능 |
| `sequential` | 단일 페르소나로 순차 실행 | 기본값 |

- **공통 플래그**: `--permission-mode bypassPermissions --print`
- **CLI 경로**: `/Users/rocky/.local/bin/claude`

### 3.5 기존 컴포넌트

| 컴포넌트 | 파일 | 역할 |
|----------|------|------|
| TaskPlanner | `core/task_planner.py` | LLM 기반 태스크 단계 분해 |
| WorkerRegistry | `core/worker_registry.py` | `workers.yaml` 로더 (hint-only) |
| WorkerHealthMonitor | `core/worker_health.py` | 워커 실행 상태 추적 |
| ProjectMemory | `core/project_memory.py` | 태스크 이력 RAG |
| LLMRouter | `core/llm_router.py` | 태스크 → 워커 라우팅 |
| ContextDB | `core/context_db.py` | SQLite 공유 컨텍스트 |
| TaskManager | `core/task_manager.py` | 태스크 상태 추적 |
| CompletionProtocol | `core/completion.py` | 완료 검증 |
| OrgRegistry | `core/org_registry.py` | 조직 레지스트리 (Phase 2) |
| CrossOrgBridge | `core/cross_org_bridge.py` | 크로스 조직 라우터 (Phase 2) |

## 4. 데이터 흐름

```
유저 메시지
  |
  v
PM Bot
  |
  v
DynamicTeamBuilder.build_team(task)
  |-- LLM 분석: "어떤 페르소나가 필요한가?"
  |-- AgentCatalog.recommend(task) [폴백]
  +-> TeamConfig (agents, execution_mode, omc_team_format)
  |
  v
팀 구성 텔레그램 발표 "팀 구성: executor×2 + analyst×1"
  |
  v
ClaudeCodeRunner
  |-- omc_team:     /team 2:executor,1:analyst "task"
  |-- agent_teams:  CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 실행
  +-- sequential:   단일 페르소나 실행
  |
  v
결과 -> 텔레그램 그룹
```

## 5. 에이전트 페르소나 목록

`~/.claude/agents/`에서 로드되는 21개 페르소나:

| 페르소나 | 전문 영역 |
|----------|-----------|
| `analyst` | 요구사항 분석, 수용 기준, 숨겨진 제약 |
| `architect` | 시스템 설계, 경계, 인터페이스, 장기 트레이드오프 |
| `build-fixer` | 빌드/툴체인/타입 오류 수정 |
| `code-reviewer` | 종합 코드 리뷰, API 계약, 버전 호환성 |
| `code-simplifier` | 코드 단순화, 복잡도 감소 |
| `critic` | 계획/설계 비판적 검토 |
| `debugger` | 근본 원인 분석, 회귀 격리, 장애 진단 |
| `deep-executor` | 복잡한 자율 목표 지향 태스크 |
| `designer` | UX/UI 아키텍처, 인터랙션 설계 |
| `document-specialist` | 외부 문서 및 레퍼런스 조회 |
| `executor` | 코드 구현, 리팩토링, 기능 개발 |
| `explore` | 내부 코드베이스 탐색, 심볼/파일 매핑 |
| `git-master` | Git 워크플로우, 브랜치 전략, 충돌 해결 |
| `planner` | 태스크 시퀀싱, 실행 계획, 리스크 플래그 |
| `qa-tester` | 대화형 CLI/서비스 런타임 검증 |
| `quality-reviewer` | 로직 결함, 유지보수성, 안티패턴, 성능 |
| `scientist` | 데이터/통계 분석 |
| `security-reviewer` | 취약점, 신뢰 경계, 인증/인가 |
| `test-engineer` | 테스트 전략, 커버리지, 불안정 테스트 강화 |
| `verifier` | 완료 증거, 클레임 검증, 테스트 적절성 |
| `writer` | 문서, 마이그레이션 노트, 사용자 가이드 |

## 6. 설정 파일

### agent_hints.yaml

라우팅 힌트 파일. 실제 런타임 팀 구성이 아닌 DynamicTeamBuilder의 기본값 참고용.

```yaml
# agent_hints.yaml — 라우팅 힌트 (런타임 팀 구성 아님)
# DynamicTeamBuilder LLM 폴백 시 참고
hints:
  coding:
    preferred: [executor, debugger]
    fallback: [deep-executor]
  analysis:
    preferred: [analyst, scientist]
    fallback: [explore]
  review:
    preferred: [code-reviewer, quality-reviewer, security-reviewer]
    fallback: [verifier]
  documentation:
    preferred: [writer, document-specialist]
    fallback: [executor]
```

### workers.yaml (deprecated — hint-only)

과거 고정 워커 설정. 현재는 DynamicTeamBuilder가 대체한다.
참고용으로만 유지되며 런타임 팀 구성에 사용되지 않는다.

## 7. 기술 스택

| 레이어 | 기술 |
|--------|------|
| 언어 | Python 3.11+ |
| 봇 프레임워크 | python-telegram-bot 20.x |
| 공유 DB | SQLite + sqlite-vec |
| 실행 엔진 | subprocess (claude CLI) |
| 비동기 | asyncio |
| 스키마 검증 | pydantic v2 |
| 의존성 관리 | uv + pyproject.toml |
| 에이전트 페르소나 | ~/.claude/agents/ (21개) |
| 팀 오케스트레이션 | oh-my-claudecode /team |
| 네이티브 팀 | CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 |

## 8. 디렉토리 구조

```
telegram-ai-org/
├── core/
│   ├── pm_bot.py              # PM 봇 오케스트레이터
│   ├── agent_catalog.py       # ~/.claude/agents/ 동적 로더         <- 신규
│   ├── dynamic_team_builder.py# LLM 기반 팀 구성 결정기             <- 신규
│   ├── worker_bot.py          # Worker 봇 베이스 클래스
│   ├── message_schema.py      # OrgMessage pydantic 모델
│   ├── context_db.py          # 공유 컨텍스트 DB (SQLite)
│   ├── task_manager.py        # 태스크 상태 추적
│   ├── task_planner.py        # 단계 분해 플래너 (LLM)
│   ├── completion.py          # 완료 검증 프로토콜
│   ├── worker_registry.py     # workers.yaml 로더 (hint-only)
│   ├── worker_health.py       # 워커 헬스 모니터링
│   ├── project_memory.py      # 프로젝트 메모리 (RAG)
│   ├── llm_router.py          # LLM 기반 태스크 라우터
│   ├── org_registry.py        # 조직 레지스트리 (Phase 2)
│   └── cross_org_bridge.py    # 크로스 조직 메시지 라우터 (Phase 2)
├── tools/
│   ├── claude_code_runner.py  # Claude Code 실행 래퍼 (3모드)
│   ├── codex_runner.py        # Codex 실행 래퍼
│   └── amp_caller.py          # amp MCP 연동
├── agent_hints.yaml           # 라우팅 힌트 (런타임 팀 구성 아님)  <- 신규
├── workers.yaml               # deprecated — hint-only
├── organizations.yaml         # 조직 설정 (Phase 2)
├── simulation_mode.py         # 오프라인 E2E 시뮬레이션
├── ARCHITECTURE.md            # 이 파일
└── FINDINGS.md                # MCP/플러그인 조사 결과
```

## 9. 보안 고려사항

- 봇 토큰은 환경변수로만 관리 (`.env`)
- PM Bot만 Context DB 쓰기 권한
- 메시지 발신자 검증 (화이트리스트)
- `--permission-mode bypassPermissions`는 신뢰된 내부 태스크에만 사용
- 외부 코드 실행 시 샌드박스 적용 고려

## 10. Phase 2: 멀티 조직 아키텍처

### 10.1 개요

단일 조직(1 PM + N Workers)에서 **복수 조직(M PM x N Workers)**으로 확장.
각 조직은 독립된 PM봇 토큰 + Telegram 그룹 채팅방을 보유한다.

```
유저 (상록)
  |
  |-- dev_team PM (@dev_pm_bot)
  |       |-- DynamicTeamBuilder -> executor, debugger, test-engineer
  |       +-- AgentCatalog -> ~/.claude/agents/
  |
  +-- marketing_team PM (@mkt_pm_bot)
          |-- DynamicTeamBuilder -> writer, analyst, document-specialist
          +-- AgentCatalog -> ~/.claude/agents/
```

### 10.2 핵심 컴포넌트

#### OrgRegistry (`core/org_registry.py`)

- `organizations.yaml`에서 조직 목록 로드
- `Organization`: name, pm_token, group_chat_id, workers
- `get_org_for_worker(handle)` — 워커가 속한 조직 반환
- `route_cross_org(from_org, to_worker)` — 크로스 조직 라우팅 경로 결정

#### CrossOrgBridge (`core/cross_org_bridge.py`)

- `CrossOrgMessage`: from_org + to_org + inner OrgMessage
- `route(msg, from_org)` — 대상 조직 탐색 + 텔레그램 전달
- 동일 조직 메시지는 통과, 크로스 조직만 브릿지 처리
- 유저는 어느 조직 PM과도 직접 대화 가능

### 10.3 크로스 조직 데이터 흐름

```
dev_team PM이 writer(marketing_team) 요청 시:

dev_team PM
  |
  v CrossOrgBridge.route(msg, from_org="dev_team")
  |
  |-- OrgRegistry.get_org_for_worker("writer") -> marketing_team
  |
  v CrossOrgMessage(from_org="dev_team", to_org="marketing_team", inner=msg)
  |
  v Telegram send -> marketing_team group_chat_id
  |
  v marketing_team PM이 DynamicTeamBuilder로 writer 팀 구성 후 실행
```
