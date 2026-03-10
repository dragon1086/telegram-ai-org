# FINDINGS.md — omc/AgentTeams 기능 조사 결과

> 최종 업데이트: 2026-03-10

## 핵심 발견 (새 아키텍처 근거)

### 1. ~/.claude/agents/ — 21개 에이전트 페르소나
- analyst, architect, build-fixer, code-reviewer, code-simplifier, critic, debugger
- deep-executor, designer, document-specialist, executor, explore, git-master
- planner, qa-tester, quality-reviewer, scientist, security-reviewer
- test-engineer, verifier, writer
- **활용 방법**: AgentCatalog가 동적 로드 -> DynamicTeamBuilder가 LLM으로 선택

### 2. CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1
- Claude Code 네이티브 팀 기능 활성화
- 병렬 서브에이전트 실행 지원
- **활용 방법**: agent_teams 실행 모드에서 환경변수 주입

### 3. oh-my-claudecode /team 명령
- 형식: `/team N:executor,M:analyst "task"`
- plan->prd->exec->verify->fix 파이프라인 자동 실행
- **활용 방법**: omc_team 실행 모드에서 claude CLI에 전달

### 4. omc MCP 서버 (team-mcp.cjs)
- TeamCreate, TaskCreate, SendMessage 등 팀 관리 도구
- **현재 상태**: 이 프로젝트의 ClaudeCodeRunner가 omc /team을 CLI로 호출

## 새 아키텍처 설계 결정

| 결정 | 이유 |
|------|------|
| workers.yaml -> hint-only | 실제 팀은 Agent Teams/omc가 동적 구성 |
| AgentCatalog 추가 | ~/.claude/agents/ 페르소나 재사용 |
| 3가지 실행 모드 | 태스크 복잡도에 따른 최적 실행 선택 |
| DynamicTeamBuilder | LLM이 매 요청마다 최적 팀 결정 |

---

# MCP / Superpowers 플러그인 조사 결과

> 조사일: 2026-03-10
> 명령어: `claude mcp list`

## 현재 등록된 MCP 서버

| 서버 이름 | 경로 | 상태 |
|-----------|------|------|
| `plugin:oh-my-claudecode:t` | `node ~/.claude/plugins/cache/omc/oh-my-claudecode/4.5.1/bridge/mcp-server.cjs` | Connected |
| `plugin:oh-my-claudecode:team` | `node ~/.claude/plugins/cache/omc/oh-my-claudecode/4.5.1/bridge/team-mcp.cjs` | Connected |
| `plugin:context-mode:context-mode` | `node ~/.claude/plugins/cache/context-mode/context-mode/1.0.15/start.mjs` | Connected |

## 플러그인 기능 요약

### oh-my-claudecode (v4.5.1)
- **팀 조율**: `TeamCreate`, `SendMessage`, `TaskCreate` 등 멀티 에이전트 팀 오케스트레이션
- **상태 관리**: `state_read`, `state_write` — 에이전트 상태 파일 기반 지속성
- **노트패드**: `notepad_read/write` — 세션 메모리
- **프로젝트 메모리**: `project_memory_read/write` — 영구 프로젝트 컨텍스트
- **코드 인텔리전스**: LSP hover/definition/references, AST 패턴 검색/치환
- **Python REPL**: 데이터 분석용 영구 REPL 세션

### context-mode (v1.0.15)
- **컨텍스트 보호**: 대용량 CLI 출력을 샌드박스에서 처리해 컨텍스트 윈도우 절약
- **배치 실행**: `ctx_batch_execute` — 다중 명령 + 인덱싱 + 검색 원스톱
- **파일 실행**: `ctx_execute_file` — 파일 경로 기반 코드 실행

## worker_bot 활용 방안

### 현재 claude_code_runner.py 개선 사항
- `--dangerously-skip-permissions` -> `--permission-mode bypassPermissions --print` 완료
- `CLAUDE_CODE_OAUTH_TOKEN` 환경변수 자동 주입 완료
- CLI 경로 고정: `/Users/rocky/.local/bin/claude` 완료

### MCP 활용 가능성 (향후 구현)

#### 1. oh-my-claudecode LSP 활용 (analyst 워커)
```python
# analyst 워커가 코드 리뷰 시 LSP 심볼 분석 활용 가능
# claude --permission-mode bypassPermissions --print "lsp_diagnostics 실행 후 버그 진단: ..."
```

#### 2. context-mode 활용 (researcher 워커)
- 대용량 웹 데이터 처리 시 `ctx_batch_execute`로 컨텍스트 낭비 방지
- researcher가 Codex 엔진으로 실행 시 대용량 리서치 결과 자동 인덱싱

#### 3. 프로젝트 메모리 연동 (pm_bot)
- `project_memory_read`로 과거 태스크 컨텍스트를 PM 라우팅에 활용
- TaskPlanner가 `get_planning_context()` 호출 시 MCP 메모리도 조회 가능

## 결론

현재 Claude Code 환경에는 **oh-my-claudecode + context-mode** 2개 플러그인이 활성화되어 있으며,
worker_bot이 claude CLI를 subprocess로 호출할 때 이 플러그인들이 자동으로 로드됩니다.

추가 설정 없이도 `--permission-mode bypassPermissions` 플래그로 Claude Code를 headless 실행하면
모든 MCP 기능에 접근 가능합니다.
