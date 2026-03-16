# 코딩에이전트 아키텍처 심층 분석
## "전통적 CS 레이어 + LLM 레이어" 관점

> 분석 대상: oh-my-claudecode (OMC), oh-my-openagent (OOA), telegram-ai-org
> 작성일: 2026-03-16

---

## 목차

1. [핵심 인사이트: 레이어 구조](#1-핵심-인사이트-레이어-구조)
2. [OMC / OOA 아키텍처 분석](#2-omc--ooa-아키텍처-분석)
3. [telegram-ai-org 아키텍처 분석](#3-telegram-ai-org-아키텍처-분석)
4. [비교 분석](#4-비교-분석)
5. [telegram-ai-org 개선 제안](#5-telegram-ai-org-개선-제안)
6. [개선 우선순위 요약](#6-개선-우선순위-요약)
7. [최근 변경사항 이력 (2026-03-16 이후)](#7-최근-변경사항-이력-2026-03-16-이후)
8. [핵심 참조 파일](#8-핵심-참조-파일)

---

## 1. 핵심 인사이트: 레이어 구조

### 1.1 레이어 구조 전체도

```
┌──────────────────────────────────────────────────────────────┐
│                     사용자 입력/이벤트                         │
└─────────────────────────────┬────────────────────────────────┘
                              │
        ── 전통적 CS 레이어 ──────────────────────────────────
                    ┌─────────▼─────────┐
                    │  이벤트 감지/라우팅  │  regex, keyword matching
                    │  상태 읽기/쓰기    │  파일시스템/DB I/O
                    │  동시성 제어       │  세마포어, 큐, 뮤텍스
                    └─────────┬─────────┘
        ── LLM 레이어 ──────────────────────────────────────
                    ┌─────────▼─────────┐
                    │  프롬프트 주입     │  SKILL.md, system prompt
                    │  LLM 판단 호출    │  분류, 계획, 실행, 검증
                    │  응답 해석        │  JSON 파싱, 패턴 감지
                    └─────────┬─────────┘
        ── 전통적 CS 레이어 ──────────────────────────────────
                    ┌─────────▼─────────┐
                    │  닫힌 루프 제어    │  재시도, fallback, 탈출구
                    │  상태 지속        │  파일/DB 저장
                    │  결과 검증        │  패턴 매칭, 임계값 비교
                    └──────────────────┘
```

### 1.2 핵심 원칙: "코드가 WHEN, LLM이 WHAT"

가장 중요한 설계 패턴은 **판단의 분리**다:

| 결정 | 담당 | 방법 |
|------|------|------|
| **언제** 루프를 계속할지 | 코드 | 상태 파일 존재 여부, 카운터 비교 |
| **언제** fallback으로 전환할지 | 코드 | 에러 타입 분류, 타임아웃 체크 |
| **어떻게** 문제를 해결할지 | LLM | 자연어 판단 |
| **무엇을** 다음에 할지 | LLM | 자연어 지시 해석 |

### 1.3 "LLM 프로그래밍"의 본질

전통적 코드 패러다임과의 대응:

| 전통적 코드 | LLM 에이전트 패턴 |
|------------|-----------------|
| `while (!done) { ... }` | Stop Hook: `shouldBlock=true` + 다음 작업 지시 주입 |
| `if (condition) goto state2` | Phase Transition: 상태 파일 전이 + 자연어 지시 주입 |
| `call library.func()` | Skill 로딩: SKILL.md → 프롬프트에 주입 |
| `import module` | MCP 서버: Tool로 노출된 기능 |
| `throw Exception` | Hook 차단: `blockReason` + 수정 지시 주입 |
| `retry(n)` | Tool error retry: 카운터 + "대안 접근법 유도" 메시지 |

---

## 2. OMC / OOA 아키텍처 분석

### 2.1 전통적 CS 레이어

#### 파일시스템 기반 상태머신

두 프로젝트 모두 DB 대신 **JSON 파일 + atomic write** 를 상태 저장소로 쓴다.

**OMC 상태 파일 목록:**
| 파일 | 역할 | TTL |
|------|------|-----|
| `ralph-state.json` | Ralph 루프 반복 횟수, active 플래그 | - |
| `ultrawork-state.json` | Ultrawork 모드 활성 여부 | - |
| `autopilot-state.json` | 파이프라인 단계, phase duration | - |
| `cancel-signal` | 취소 시그널 | 30초 |
| `last-tool-error.json` | 마지막 도구 에러 | 60초 |
| `{mode}-stop-breaker.json` | Circuit breaker 카운트 | 5분/45분 |

**왜 파일시스템인가?**
- 에이전트 프로세스가 언제든 크래시될 수 있음
- 트랜잭션보다 원자적 파일 쓰기(write-then-rename)가 더 단순
- 사용자가 직접 상태 파일을 읽어 디버깅 가능 (투명성)

`src/lib/atomic-write.ts`의 `atomicWriteJsonSync()` — write-to-temp-then-rename 패턴으로 파일 손상 방지.

#### 동시성 제어

**OOA `concurrency.ts`:**
```typescript
class ConcurrencyManager {
  private counts: Map<string, number>   // 현재 실행 수
  private queues: Map<string, QueueEntry[]>  // 대기 큐
  async acquire(model: string): Promise<void> { ... }
  release(model: string): void { ... }
}
```
모델(GPT-4, Claude 등)별 동시 실행 수를 세마포어로 제어. OS 수준 세마포어와 동일한 패턴.

#### IPC: Hook Bridge (Unix Pipe)

OMC의 핵심 인프라는 **쉘 스크립트 → Node.js bridge** Unix pipe IPC:

```
Claude Code (호스트)
  └─ shell hook script
      └─ node hook-bridge.mjs --hook=keyword-detector
          └─ bridge.ts processHook()
              ├─ (순수 코드) 상태 파싱, 조건 평가
              └─ JSON response → stdout → Claude Code
```

OOA는 더 발전된 **in-process 플러그인 인터페이스**를 사용:
```
tool.execute.before → PreToolUse 미들웨어
tool.execute.after  → PostToolUse 미들웨어
chat.message        → 메시지 변환
experimental.chat.system.transform → 시스템 프롬프트 변환
```

#### Team 모드: Actor 모델 (파일시스템 Mailbox)

OMC `src/team/`:
```
Leader (main session)
  ├─ inbox-outbox.ts: appendOutbox() / readNewInboxMessages()
  ├─ task-file-ops.ts: readTask() / findNextTask() / areBlockersResolved()
  ├─ tmux-session.ts: createSession() / spawnBridgeInSession()
  └─ heartbeat: writeHeartbeat() / isWorkerAlive()
         │
Worker 1 (tmux pane: claude)
Worker 2 (tmux pane: codex)
```
파일시스템 기반 mailbox — Erlang Actor 모델과 동일한 패턴.

### 2.2 LLM 레이어

#### 프롬프트를 데이터로 취급

**OMC:** `.md` 파일로 완전 분리. `agents/*.md` 19개 파일이 에이전트 성격/행동 정의.
```
loadAgentPrompt('debugger') → agents/debugger.md → 프롬프트 주입
```
코드 변경 없이 프롬프트만 수정해 에이전트 행동 변경 가능.

**OOA:** TypeScript 모듈 내 인라인 + **모델별 프롬프트 변형**:
```
Hephaestus/gpt.ts, Hephaestus/gpt-5-3-codex.ts, Hephaestus/gpt-5-4.ts
```
멀티 프로바이더(Anthropic, OpenAI, Google, Ollama) 지원을 위해 런타임 모델 감지 후 적절한 프롬프트 선택.

#### Skill = 프롬프트 주입 라이브러리

```
사용자: "/ralph fix tests"
  → (순수 코드) auto-slash-command hook이 "/ralph" 감지
  → (순수 코드) skills/ralph/SKILL.md 파일 로드 + frontmatter 파싱
  → (LLM 레이어) SKILL.md 본문이 <command-name> 태그로 system prompt에 주입
  → LLM이 스킬 지시 따라 행동
  → (순수 코드) ralph hook이 ralph-state.json 생성
  → (순수 코드) Stop hook이 상태 확인 → 루프 강제
```

Skills 안에 CLI 코드, MCP 서버, 다른 스킬 호출이 포함될 수 있다.

#### MCP = Tool 노출 메커니즘

**OMC `src/mcp/omc-tools-server.ts`:**
```typescript
createSdkMcpServer({
  name: "t",
  tools: [lspTools(12개), astTools(2개), pythonRepl, stateTools, notepadTools, ...]
})
// → Claude가 mcp__t__lsp_hover, mcp__t__ast_grep_search 등으로 사용
```

**OOA:** 동적 매니저로 스킬별 MCP 서버를 런타임에 시작/중지. OAuth, HTTP, stdio 3가지 연결 유형 지원.

### 2.3 닫힌 루프 (Closed Loop) 메커니즘

#### Ralph Loop — 핵심 패턴

```
시작: ralph-state.json { active: true, iteration: 1, max: 20 }
  ↓
LLM 작업 → 완료 판단 → Stop 시도
  ↓
Stop Hook intercept:
  (순수 코드) state.active && iteration < max → shouldBlock=true
  (LLM 레이어) "[RALPH - ITERATION 2/20] 작업 미완료..." 주입
  ↓
LLM 계속 작업 → ... (반복)
  ↓
승인 감지: checkArchitectApprovalInTranscript()
  → (순수 코드) 트랜스크립트에서 "APPROVED" 패턴 찾기
  → clearRalphState() → 루프 종료
```

#### Circuit Breaker (무한 루프 방지)

```
TEAM_PIPELINE_STOP_BLOCKER_MAX = 20
RALPLAN_STOP_BLOCKER_MAX = 30

breakerCount > MAX → shouldBlock=false (강제 탈출)
rate limit error  → shouldBlock=false (절대 차단 안 함)
auth error        → shouldBlock=false
context window 95% → shouldBlock=false
```

**안정성의 핵심은 "탈출구" 설계.** 진짜 문제(rate limit, OOM, auth)일 때 반드시 탈출해야 무한 루프를 막는다.

#### Autopilot Pipeline — 다단계 상태머신

```
STAGE_ORDER = ['ralplan', 'execution', 'ralph', 'qa']

전이: advanceStage()
  → 현재 stage 'complete' 마킹
  → 다음 non-skipped stage 'active'로
  → onExit/onEnter 콜백 실행

실패: failCurrentStage(error)
  → stage 'failed' 마킹
  → 에러 기록 후 재시도 결정
```

### 2.4 LLM이 개입하는 정확한 지점

**순수 코드 영역 (LLM 불필요):**
- 상태 파일 읽기/쓰기
- 키워드 감지 (regex)
- 에러 타입 분류
- Circuit breaker 카운터 비교
- 취소 시그널 TTL 체크
- Tmux 프로세스 관리
- Heartbeat 체크

**LLM 판단 의존 영역:**
- 작업 완료 판단 (Stop 시도 자체)
- Architect 승인 판단 ("APPROVED" 텍스트 생성)
- 태스크 분해 (요구사항 → 하위 태스크)
- 코드 작성/수정
- 에러 분석 후 수정 방법 결정
- PRD 수락 기준 충족 여부 판단

**하이브리드 지점 (코드=구조, LLM=내용):**
- Stop Hook: 코드가 "지금 멈추면 안 된다" 결정 + LLM에 "왜 계속해야 하는지" 자연어로 전달
- Phase Transition: 코드가 "다음 단계 전환" 결정 + LLM에 "다음에 무엇을 해야 하는지" 전달
- Tool Guard: 코드가 "이 도구 차단" 결정 + LLM에 "왜 차단됐는지, 대신 무엇을 해야 하는지" 전달

---

## 3. telegram-ai-org 아키텍처 분석

### 3.1 전통적 CS 레이어

#### 3-tier 데이터 저장

| DB | 파일 | 용도 | 비동기 방식 |
|---|---|---|---|
| `ContextDB` | `~/.ai-org/context.db` | PM 태스크, DAG, 토론 | aiosqlite (async) |
| `LessonMemory` | `.ai-org/lesson_memory.db` | 실패 패턴 | sqlite3 (sync ⚠️) |
| `AgentPersonaMemory` | `.ai-org/agent_persona_memory.db` | 시너지/성과 | sqlite3 (sync ⚠️) |

⚠️ `LessonMemory`, `AgentPersonaMemory`, `ShoutoutSystem`, `UserScheduleStore` 모두 sync sqlite3 사용 → asyncio 이벤트 루프 blocking 위험.

#### 태스크 의존성 DAG

`task_graph.py`: `pm_task_dependencies` 테이블 기반 DAG.
- `detect_cycle()`: DFS로 순환 검사
- `get_ready_tasks()`: 의존성 모두 `done`인 태스크 반환
- `mark_complete()`: 완료 처리 후 새로 unblock된 태스크 목록 반환

#### 파일 기반 Claim/뮤텍스

`claim_manager.py`:
```python
# os.O_CREAT | os.O_EXCL 플래그로 원자적 claim
# TTL 기반 만료 (기본 600초)
# 다중 PM 봇 간 메시지 처리 경쟁 방지
```

#### Bid 경매 시스템 (ClaimManager)

`telegram_relay.py`:
1. 메시지 수신 → 각 PM 봇이 confidence score 계산
2. 2.5초 대기 (BID_WAIT_SEC)
3. 파일 기반 bid 제출 → 최고 점수 봇이 처리
4. PM org는 `bid_score=999`로 항상 승리

#### TaskPoller: DB 폴링 기반 IPC

Telegram Bot API가 봇→봇 메시지를 수신할 수 없으므로, 부서봇이 10초 간격으로 ContextDB 폴링:
```
부서봇 TaskPoller (10초 간격)
  → assigned 상태 태스크 조회
  → lease 기반 중복 실행 방지
  → heartbeat (30초 간격)
  → 완료 시 ContextDB에 결과 기록
```

### 3.2 LLM 레이어

#### LLM 호출 지점 맵

| 컴포넌트 | LLM 위임 내용 | fallback |
|---|---|---|
| `NLClassifier` | 1차 키워드 프리필터 (순수 코드) | — |
| `PMRouter` | intent 분류 5가지 | keyword heuristic |
| `PMOrchestrator._classify_lane` | lane 분류 6가지 | `_heuristic_lane()` |
| `PMOrchestrator._llm_plan_request` | route/complexity/rationale | `_heuristic_plan_request()` |
| `PMOrchestrator._llm_decompose` | 부서별 서브태스크 분해 | keyword 매칭 |
| `ResultSynthesizer` | 부서 결과 합성 판단 | `_keyword_synthesize()` |
| `ConfidenceScorer` | 메시지-봇 적합도 점수 | score=0 |
| `GlobalContext` | 대화 맥락 추출/요약 | skip |
| `_reply_with_pm_chat` | 최종 사용자 응답 | recovery message |

하나의 메시지 처리에 **최대 5-6회 순차 LLM 호출** 발생.

#### 프롬프트 패턴

일관된 구조: **structured instructions + JSON output format + rules section**

`PMDecisionClient` (`pm_decision.py`): 모든 판단 호출에 system prompt 주입:
```
당신은 사용자를 대신해 실행하는 PM의 내부 판단 엔진이다.
이 호출에서는 실제 작업을 수행하지 말고, 요청된 분류/계획/판단만 하라.
```
"실행"과 "판단" 분리 — 잘 설계된 부분.

### 3.3 전체 오케스트레이션 흐름

```
사용자 메시지 (Telegram)
  ↓
TelegramRelay.on_message()
  ↓
NLClassifier (순수 코드 키워드 프리필터)
  ↓
PMRouter (LLM intent 분류)
  ↓
ClaimManager bid 경매 (순수 코드)
  ↓
PMOrchestrator.plan_request()
  ├── direct_reply  → LLM 직접 응답
  ├── local_execution → DynamicTeamBuilder + runner
  └── delegate
        ↓
      LLM decompose → ContextDB에 subtask 저장
        ↓
      TaskPoller 폴링 (10초 간격, 순수 코드)
        ↓
      부서봇 실행 → ContextDB 결과 기록
        ↓
      ResultSynthesizer (LLM 판단)
        ↓
      사용자에게 통합 보고
```

### 3.4 닫힌 루프 현황

**존재하는 루프:**
| 루프 | 위치 | 메커니즘 |
|---|---|---|
| 워커 재시도 | `worker_health.py` | 지수 백오프(base=2s, max=120s), 최대 3회 → DLQ |
| Codex→Claude fallback | `telegram_relay.py:740` | Codex 실패 시 Claude Code 재시도 |
| LLM 판단 fallback | 전체 | 모든 LLM 호출에 keyword/heuristic fallback |
| TaskPoller 재큐잉 | `task_poller.py` | lease TTL(180초) 후 재큐잉 |
| 워커 상태머신 | `worker_health.py` | ONLINE→DEGRADED(3회)→QUARANTINED(5회) |
| 응답 품질 가드 | `telegram_relay.py:755` | `ensure_user_friendly_output()` |
| 세션 자동 compact | `core/session_manager.py` | 컨텍스트 70% 초과 시 자동 /compact |
| PMDecisionClient 세션 분리 | `core/telegram_relay.py` | 전용 세션으로 --resume 충돌 방지 |

**닫힌 루프가 없는 곳 (갭):**
1. **스케줄러 잡 실패**: ~~재시도 없음~~ **✅ 수정 (d6fcde0): 지수 백오프 재시도 3회**
2. **DAG 선행 태스크 실패**: ~~cascade fail 정책 없음~~ **✅ 수정 (e2f5ec1): cascade_fail 정책 구현**
3. **ResultSynthesizer follow_up_tasks**: ~~실행 보장 없음~~ **✅ 수정 (b48aaae, b94a644): SUFFICIENT 후 follow_up 방지 + 무한루프 수정**
4. **WorkerHealthMonitor DLQ**: ~~in-memory, 프로세스 재시작 시 소실~~ **✅ 부분 수정 (020e919): DLQ 크기 상한 100 설정**

### 3.5 캐릭터/메모리 시스템

**BotCharacterEvolution**: 순수 통계 기반 (LLM 불필요):
```
success_patterns[task_type] >= 3 → strengths에 추가
failure_patterns[category] >= 3 → weaknesses에 추가
```
금요일 `friday_retro`에서 자동 호출.

**AgentPersonaMemory**: EMA 기반 시너지 스코어:
```python
score = 0.8 * old + 0.2 * (1.0 if success else 0.0)
```
`recommend_team(task_type, count)` — 특정 task_type에서 성공률 높은 에이전트 추천.

**LessonMemory**: 실패 패턴 keyword overlap scoring (semantic search 아님).

### 3.6 LLM API 직접 호출 제거 리팩토링

**배경 (bc4a478, bad83e9, 75a444b):** `llm_provider.py`가 삭제되고 모든 LLM 직접 호출이 제거됐다.

**Before:**
```python
# llm_provider.py (삭제됨)
client = AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
response = await client.messages.create(...)
```

**After:** 모든 LLM 호출은 `claude-code` / `codex` CLI를 통해서만 이루어진다. `llm_router.py`가 이를 추상화한다.

**영향:**
- `attachment_analysis.py`, `memory_manager.py`, `nl_schedule_parser.py`, `pm_bot.py`, `task_planner.py`, `telegram_relay.py` 등 전수 리팩토링
- 직접 API 키 의존성 제거 → `ANTHROPIC_API_KEY` 없어도 OAuth 토큰 fallback (a53d915)
- `DynamicTeamBuilder`의 `AsyncAnthropic` 직접 호출도 제거 (bad83e9)

### 3.7 세션 자동 compact

**배경 (47fe506, b48b97c):** 장시간 실행되는 Claude Code / Codex 세션이 컨텍스트 임계값(70%)을 초과하면 자동으로 compact된다.

**구현 (`core/session_manager.py`):**
- 컨텍스트 사용률 70% 초과 → `/compact` 명령 자동 주입
- Codex와 Claude Code 세션명 불일치 수정 포함
- 세션 만료(code=1 에러) 시 자동 초기화 (5e0afb6)

**효과:** 장시간 자율 실행 시 컨텍스트 오버플로우로 인한 세션 실패 방지.

---

## 4. 비교 분석

### 4.1 아키텍처 패턴 비교

| 축 | OMC/OOA | telegram-ai-org |
|---|---|---|
| **주요 언어** | TypeScript (Node.js) | Python (asyncio) |
| **상태 저장** | 파일시스템 JSON + atomic write | SQLite 3개 (혼합 async/sync) |
| **IPC** | Unix pipe (shell→node) / in-process 플러그인 | Telegram API + DB 폴링 |
| **닫힌 루프** | persistent-mode hook (1200줄) + 40+ 개별 hook | worker_health + LLM fallback |
| **프롬프트 관리** | .md 파일 분리 / TS 모듈 | 인라인 Python 문자열 |
| **에이전트 정의** | 역할 기반 md 파일 | workers.yaml (비어있음), 동적 팀빌더 |
| **Circuit breaker** | stop-breaker.json + TTL | WorkerHealthMonitor (in-memory) |
| **스킬 시스템** | 명시적 (SKILL.md + 6개 소스) | 없음 |
| **MCP 지원** | 있음 (in-process + 동적) | 없음 |
| **멀티 모델 지원** | OOA: Anthropic/OpenAI/Google/Ollama | claude-code / codex 2가지 |

### 4.2 "LLM 레이어 vs CS 레이어" 비율 비교

**OMC/OOA:**
- CS 레이어가 LLM을 **감싸고 통제**: hook이 LLM의 모든 입출력을 가로챔
- 루프 제어, 에러 감지, 상태 전이가 **모두 코드**
- LLM은 "내용 생성"에만 집중

**telegram-ai-org:**
- LLM 레이어가 **더 많은 것을 결정**: 5-6회 순차 호출로 판단 체인
- CS 레이어(fallback, DB, 라우팅)가 잘 갖춰져 있지만
- **루프 제어 메커니즘이 약함** (persistent-mode hook에 해당하는 것이 없음)
- Stop/Continue 결정을 LLM에 더 많이 의존

### 4.3 강점/약점 비교

**telegram-ai-org 강점:**
- fallback 전략이 전 계층에 일관되게 적용됨 (LLM 실패 → keyword)
- Telegram이라는 실제 UX 채널을 통한 자연스러운 인터페이스
- 비용 효율적 구조 (동적 팀빌더로 별도 봇 불필요)
- EMA 기반 시너지 추적 등 정교한 메모리 시스템

**telegram-ai-org 약점:**
- 닫힌 루프(persistent-mode) 메커니즘 부재
- 단일 프로세스 가정 (WorkerHealthMonitor in-memory)
- sync SQLite + async 혼재로 이벤트 루프 blocking 위험
- 순차 LLM 호출 체인으로 누적 지연 수십~수백 초
- DAG 실패 전파 정책 없음

---

## 5. telegram-ai-org 개선 제안

### 5.1 🔴 Critical: 닫힌 루프 메커니즘 추가

**문제**: `pm_orchestrator.py`에 ralph-style persistent loop가 없음. 부서봇이 작업을 중간에 포기해도 PM이 재시도를 강제하지 못함.

**제안: `core/task_loop_guard.py` 신설**
```python
class TaskLoopGuard:
    """
    태스크 실행 후 "완료"를 검증하고, 미완료 시 재시도를 강제하는 닫힌 루프.
    OMC persistent-mode hook의 Python 구현체.
    """
    MAX_ITERATIONS = 10

    async def enforce_completion(self, task_id: str, runner_fn) -> TaskResult:
        for iteration in range(self.MAX_ITERATIONS):
            result = await runner_fn()

            # 순수 코드: 완료 판단 (텍스트 패턴 + 구조 확인)
            if self._is_genuinely_complete(result):
                return result

            # LLM 레이어: 왜 미완료인지, 다음에 무엇을 할지 지시
            continuation = self._build_continuation_prompt(result, iteration)
            await self._inject_and_retry(task_id, continuation)

        return TaskResult(status='max_iterations_reached', ...)

    def _is_genuinely_complete(self, result) -> bool:
        # 순수 코드: "완료" 패턴 감지
        # - 코드 변경이 있었는가?
        # - 에러가 없는가?
        # - 산출물이 예상 형식인가?
        ...
```

### 5.2 🔴 Critical: TaskPoller finally/except 이중 release 버그

**문제**: `task_poller.py`에서 except에서 `requeue_if_running=True`로 재큐잉 후, finally에서 `requeue_if_running=False`로 다시 호출해 재큐잉이 취소될 수 있음.

**수정:**
```python
async def _execute_task(self, task):
    released = False
    try:
        await self._run(task)
        await self.context_db.release_pm_task_lease(task.id, requeue_if_running=False)
        released = True
    except Exception as e:
        logger.error(f"Task {task.id} failed: {e}")
        await self.context_db.release_pm_task_lease(task.id, requeue_if_running=True)
        released = True
    finally:
        if not released:  # 예외 처리 중 또 다른 예외 발생 시만 도달
            await self.context_db.release_pm_task_lease(task.id, requeue_if_running=True)
```

### **✅ 구현완료 (e2f5ec1)** 5.3 🔴 Critical: DAG 실패 전파 정책

**문제**: 선행 태스크가 `failed`이면 후속 태스크가 영원히 `pending` 상태.

**수정 (`task_graph.py`):**
```python
async def handle_task_failure(self, task_id: str, policy: str = 'cascade_fail'):
    """
    policy:
      'cascade_fail' - 모든 후속 태스크를 즉시 failed로
      'skip'         - 후속 태스크를 skipped로 (partial result 허용)
      'wait'         - 현재 동작 유지 (영원히 pending - 권장하지 않음)
    """
    if policy == 'cascade_fail':
        successors = await self.get_all_successors(task_id)
        for s_id in successors:
            await self.update_task_status(s_id, 'failed',
                reason=f'cascade from {task_id}')
```

### 5.4 🔴 Critical: sync SQLite → async 통일

**문제**: `LessonMemory`, `AgentPersonaMemory`, `ShoutoutSystem`, `UserScheduleStore`가 sync sqlite3 사용.

**수정 패턴:**
```python
# Before
def record_lesson(self, ...):
    with sqlite3.connect(self.db_path) as conn:
        conn.execute(...)

# After (aiosqlite로 통일)
async def record_lesson(self, ...):
    async with aiosqlite.connect(self.db_path) as conn:
        await conn.execute(...)
        await conn.commit()
```

또는 단기 대안: `run_in_executor`로 래핑:
```python
async def record_lesson(self, ...):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, self._sync_record_lesson, ...)
```

### 5.5 🟡 High: LLM 호출 체인 병렬화

**문제**: `_classify_lane` (25s) → `_llm_plan_request` (35s) 순차 실행 = 누적 60초.

**분석**: 두 호출이 서로 독립적이라면 병렬 실행 가능.

**제안:**
```python
# Before (순차)
lane = await self._classify_lane(message)
plan = await self._llm_plan_request(message, lane)

# After (병렬)
lane_task = asyncio.create_task(self._classify_lane(message))
plan_task = asyncio.create_task(self._llm_plan_request(message))
lane, plan = await asyncio.gather(lane_task, plan_task)
# plan이 lane에 의존한다면: 먼저 lane만 병렬로 빠르게 가져오고
# plan은 lane 결과를 받아 호출
```

### 5.6 🟡 High: 워커 상태 영속화

**문제**: `WorkerHealthMonitor._health`, `_attempts`, `_dlq`가 in-memory. 프로세스 재시작 시 소실.

**제안: `core/worker_health_store.py` 신설**
```python
class WorkerHealthStore:
    """WorkerHealthMonitor의 상태를 SQLite에 영속화"""

    async def save_worker_state(self, worker_id: str, state: WorkerState):
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO worker_health VALUES (?,?,?,?)",
                (worker_id, state.status, state.consecutive_failures,
                 json.dumps(state.dlq_tasks))
            )

    async def load_worker_states(self) -> dict[str, WorkerState]:
        """프로세스 재시작 시 상태 복원"""
        ...
```

### 5.7 🟡 High: 봇 완료 감지 → 이벤트 기반으로

**문제**: `telegram_relay.py:1140`의 `"태스크" in text and "완료" in text` 텍스트 매칭이 brittle.

**제안: ContextDB 상태 변경 이벤트 기반 감지**
```python
# worker가 작업 완료 시 직접 ContextDB 업데이트
await context_db.update_task_status(task_id, 'done', result=result)

# PM은 DB 폴링 또는 asyncio.Event 기반으로 완료 감지
# → 텍스트 파싱 불필요, 포맷 변화에 강건
```

### **✅ 구현완료 (d6fcde0)** 5.8 🟡 Medium: 스케줄러 잡 재시도

**문제**: `scheduler.py`의 morning_standup, daily_retro 등이 실패 시 재시도 없음.

**제안:**
```python
async def _retryable_job(self, job_fn, max_retries=3, backoff_base=60):
    """스케줄 잡 실패 시 지수 백오프 재시도"""
    for attempt in range(max_retries):
        try:
            await job_fn()
            return
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"Job {job_fn.__name__} failed after {max_retries} attempts")
                await self._notify_job_failure(job_fn.__name__, str(e))
                return
            wait = backoff_base * (2 ** attempt)
            logger.warning(f"Job failed, retry in {wait}s: {e}")
            await asyncio.sleep(wait)
```

### **✅ 구현완료 (d6fcde0)** 5.9 🟡 Medium: ClaimManager 파일 자동 정리

**문제**: `~/.ai-org/claims/` 에 파일이 무한 누적.

**제안: 스케줄러에 정리 잡 등록**
```python
# scheduler.py
scheduler.add_job(
    self._cleanup_claims,
    CronTrigger(hour='*'),  # 매시간
    id='claim_cleanup',
    misfire_grace_time=3600
)

async def _cleanup_claims(self):
    await self.claim_manager.cleanup_old_claims(max_age_seconds=3600)
```

### **✅ 구현완료 (020e919, daefc49)** 5.10 🟡 Medium: DLQ 크기 상한 + 알림

**문제**: `WorkerHealthMonitor._dlq`가 무한 증가.

**제안:**
```python
DLQ_MAX_SIZE = 100

def _add_to_dlq(self, task):
    if len(self._dlq) >= DLQ_MAX_SIZE:
        evicted = self._dlq.pop(0)  # FIFO 방식으로 오래된 항목 제거
        logger.warning(f"DLQ full, evicted oldest task: {evicted.id}")
    self._dlq.append(task)

    # DLQ 임계치 알림 (예: 10개 이상)
    if len(self._dlq) >= 10:
        asyncio.create_task(self._notify_dlq_overflow())
```

### **✅ 구현완료 (0579b14)** 5.11 🟢 Low: 응답 SLA 정의

**현재**: 최악의 경우 5-6 LLM 호출 × 타임아웃 = 수분 대기.

**제안: 중간 progress 피드백 강제**
```python
async def plan_request(self, message: str, ...):
    # 즉시 "처리 중" 피드백
    await self._send_typing_indicator()

    # 3초 후 아직 처리 중이면 progress 메시지
    progress_task = asyncio.create_task(
        self._send_progress_after(delay=3.0, message="🤔 분석 중...")
    )

    try:
        result = await self._full_pipeline(message)
        progress_task.cancel()
        return result
    except asyncio.TimeoutError:
        await self._send("⏱️ 처리 시간이 초과됐습니다. 더 간단하게 다시 시도해주세요.")
```

### 5.12 🟢 Low: LessonMemory에 벡터 검색 도입

**현재**: keyword overlap scoring (단순 단어 교집합).

**제안**: 단기적으로는 현재 구조 유지하되, 중기적으로 sqlite-vss 또는 chromadb를 통한 semantic search 도입:
```python
# 현재
def get_relevant(self, task_description: str) -> list[Lesson]:
    words = set(task_description.split())  # keyword overlap

# 개선 방향
async def get_relevant_semantic(self, task_description: str) -> list[Lesson]:
    embedding = await self.embedder.embed(task_description)
    return await self.vector_store.search(embedding, top_k=5)
```

---

## 6. 개선 우선순위 요약

| 우선순위 | 항목 | 예상 임팩트 |
|---------|------|------------|
| 🔴 Critical | TaskPoller finally/except 이중 release 버그 수정 | ~~태스크 소실 방지~~ ✅ 구현완료 (이번 세션) |
| 🔴 Critical | DAG 실패 전파 정책 구현 | ~~교착 상태 방지~~ ✅ 구현완료 |
| 🔴 Critical | sync SQLite → aiosqlite 통일 | 이벤트 루프 안정성 |
| 🔴 Critical | TaskLoopGuard (닫힌 루프) 신설 | 작업 완료율 향상 |
| 🟡 High | 워커 상태 영속화 | 재시작 안정성 |
| 🟡 High | LLM 호출 체인 병렬화 | ✅ 구현완료 (이번 세션) |
| 🟡 High | 봇 완료 감지 이벤트 기반으로 | brittle 패턴 제거 |
| 🟡 Medium | 스케줄러 잡 재시도 로직 | ✅ 구현완료 |
| 🟡 Medium | ClaimManager 자동 정리 | ✅ 구현완료 |
| 🟡 Medium | DLQ 상한 + 알림 | ✅ 구현완료 |
| 🟢 Low | 응답 SLA + progress 피드백 | ✅ 구현완료 |
| 🟢 Low | LessonMemory 시맨틱 검색 | 교훈 검색 정확도 |
| 🔴 Critical | TaskPoller 이중 release 버그 수정 | ✅ 구현완료 (이번 세션) |
| 🟡 High | LLM 호출 체인 병렬화 (pm_orchestrator.py) | ✅ 구현완료 (이번 세션) |
| 🟡 High | sync SQLite run_in_executor 보호 | ✅ 부분 구현 (d6fcde0: scheduler) |
| 🟡 High | LLM 호출 통합 분류 (`_llm_unified_classify`) | ✅ 구현완료 (이번 세션) |
| 🟡 High | 즉시 ACK 패턴 (`_with_immediate_ack`) | ✅ 구현완료 (이번 세션) |
| 🟡 Medium | BID_WAIT 2.5s→0.8s, TaskPoller 10s→2s | ✅ 구현완료 (이번 세션) |
| 🟡 Medium | WarmSessionPool 세션 예열 | ✅ 구현완료 (이번 세션) |

---

## 7. 최근 변경사항 이력 (2026-03-16 이후)

| 커밋 | 분류 | 내용 |
|------|------|------|
| 77eb1dc | ⚡ perf | BID_WAIT 2.5s→0.8s, TaskPoller 폴링 10s→2s |
| 17d3994 | ⚡ perf | PMRouter+classify_lane+plan_request → 단일 LLM 통합 분류 |
| eb919ae | ⚡ perf | 즉시 ACK 패턴 — BID 완료 직후 분석중 메시지 즉시 전송 |
| 30b4201 | ⚡ perf | WarmSessionPool — 세션 예열로 cold start 제거 |
| bc4a478 | 🔧 refactor | LLM API 직접 호출 전수 제거 (llm_provider.py 삭제) |
| bad83e9 | 🔧 refactor | DynamicTeamBuilder AsyncAnthropic 직접 호출 제거 |
| 75a444b | 🔧 refactor | llm_provider.py 파일 제거 |
| a53d915 | ✨ feat | ANTHROPIC_API_KEY 없을 때 Claude Code OAuth 토큰 자동 fallback |
| b48b97c | 🐛 fix | Codex/Claude Code 세션 자동 compact 세션명 불일치 수정 |
| 47fe506 | ✨ feat | 세션 자동 compact (임계값 70%) |
| b48aaae | 🐛 fix | result_synthesizer SUFFICIENT 후 불필요한 follow_up 생성 방지 |
| b94a644 | 🐛 fix | SynthesisPoller 무한 루프 — follow_up 후 parent done 처리 누락 |
| 8d15128 | 🐛 fix | 첨부파일 3개 중복 업로드 버그 수정 |
| d3fffbe | 🐛 fix | PMDecisionClient 전용 세션 분리 — 동시 --resume 충돌 방지 |
| ac47726 | 🐛 fix | cleanup_old_claims hash lock 파일(*.lock) 누락 버그 수정 |
| 5e0afb6 | 🐛 fix | 만료된 --resume 세션 code=1 에러 시 자동 초기화 |
| daefc49 | ✨ feat | 에이전트 아키텍처 업그레이드 (DAG cascade, DLQ cap, ClaimManager cleanup, progress feedback) |
| 44aacbd | 🐛 fix | 스케줄러 잡 retry 래핑 제거 (테스트 호환성) |
| 54c0a5d | ✨ feat | PM 합성 시 LLM이 첨부 파일 직접 선별 |
| b999778 | 🐛 fix | PM 합성 결과에 하위 조직 생성 파일(PNG 등) 첨부 누락 수정 |
| 17df138 | 🐛 fix | claude_code_runner stderr ERROR 레벨 로깅 |
| 02f8702 | 🐛 fix | claude_code_runner 에러 메시지에 raw_lines 포함 |
| 0579b14 | ✨ feat | 복잡 태스크 처리 시 progress 피드백 (3초 후 분석중 표시) |
| d6fcde0 | ✨ feat | 스케줄러 지수 백오프 재시도 + ClaimManager 정기 정리 + sync SQLite run_in_executor 보호 |
| e2f5ec1 | ✨ feat | DAG 실패 전파 정책 (cascade_fail) 구현 |
| 020e919 | ✨ feat | DLQ 크기 상한(100) 설정 및 overflow 경고 로깅 |
| 6ed92da | 🐛 fix | 하위 조직 '요청 요약' 항상 [배경]으로 표시되는 버그 수정 |

---

## 8. 핵심 참조 파일

### telegram-ai-org
| 파일 | 역할 |
|------|------|
| `core/telegram_relay.py` (1300+줄) | 전체 메시지 흐름의 중심 |
| `core/pm_orchestrator.py` | LLM 판단 체인 핵심 |
| `core/pm_router.py` | 2-tier 라우팅 |
| `core/pm_decision.py` | LLM 실행 엔진 추상화 |
| `core/task_graph.py` | DAG 의존성 관리 |
| `core/result_synthesizer.py` | 결과 합성 + 판단 |
| `core/worker_health.py` | 워커 상태머신 + 재시도 + DLQ |
| `core/task_poller.py` | DB 폴링 기반 태스크 수신 |
| `core/claim_manager.py` | 파일 기반 원자적 claim |
| `core/agent_persona_memory.py` | EMA 시너지 + 성과 추적 |

### agent-reference (OMC)
| 파일 | 역할 |
|------|------|
| `src/hooks/persistent-mode/index.ts` (1200줄) | 닫힌 루프의 핵심 |
| `src/hooks/bridge.ts` | LLM-코드 연결 IPC |
| `src/hooks/autopilot/pipeline.ts` | 다단계 상태머신 |
| `src/lib/atomic-write.ts` | 안전한 파일 쓰기 |
| `src/features/magic-keywords.ts` | 키워드→프롬프트 변환 |
| `src/mcp/omc-tools-server.ts` | MCP Tool 노출 |
| `src/team/inbox-outbox.ts` | Actor 모델 mailbox |
