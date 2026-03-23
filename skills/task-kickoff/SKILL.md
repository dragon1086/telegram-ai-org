---
name: task-kickoff
description: "Use at the start of any new task to clarify scope, assign agents, define deliverables and AC before execution begins. Triggers: '태스크 시작', 'task kickoff', 'kickoff', 'new task', '새 태스크', when a task is received but before any implementation starts"
allowed-tools: Read, Glob, Grep, Bash
context: |
  !git -C /Users/rocky/telegram-ai-org log --oneline -3 2>/dev/null
  !ls /Users/rocky/telegram-ai-org/.claude/agents/ 2>/dev/null | head -20
---

# Task Kickoff (태스크 킥오프)

태스크 수신 직후, 실행 전 반드시 수행하는 5단계 체크리스트 스킬.
Game Studios `/start` 패턴 포팅 — 모호한 태스크를 실행 가능한 상태로 전환한다.

## 언제 사용하나

- PM이 새 태스크를 수신했을 때
- 스펙이 모호하거나 범위가 불명확한 태스크
- 여러 팀이 참여하는 복합 태스크
- Anti-Pattern #5 (Assumption-based implementation) 방지가 필요한 상황

## 5단계 체크리스트

### Step 1: 스코프 명확화

```
[태스크명]을 수신했습니다. 실행 전 스코프를 확인합니다.

- 목표: [한 줄로 요약]
- 포함 범위: [구체적 파일/시스템/기능]
- 제외 범위: [명시적으로 하지 않을 것]
- 전제 조건: [이미 완료되어 있어야 할 것]
```

**스코프가 모호하면**: PM에게 아래 질문 목록을 제시하고 착수 보류.

```
❓ 스코프 확인 필요:
1. [질문1]
2. [질문2]
→ 위 항목 명확화 후 재착수합니다.
```

### Step 2: 담당 에이전트 배정

```bash
# ~/.claude/agents/ 확인
ls ~/.claude/agents/
```

```
담당 에이전트:
- [에이전트A]: [역할]
- [에이전트B]: [역할]
선택 이유: [한 줄]
```

**배정 원칙**:
- 태스크 유형과 에이전트 전문분야 매칭 필수
- 최대 팀 크기 3명 준수 (orchestration.yaml team_config 기준)
- Cross-domain 작업은 해당 도메인 에이전트만 담당

### Step 3: 산출물 정의

```
예상 산출물:
1. [파일/문서/결과물] — 저장 위치: [경로]
2. [파일/문서/결과물] — 저장 위치: [경로]

산출물 형식: [마크다운/코드/JSON 등]
제출 방법: [PM 보고 / 파일 생성 / 커밋]
```

### Step 4: 위험 요소 사전 식별

```
위험 요소:
- [위험1]: 가능성 [상/중/하] — 완화: [방법]
- [위험2]: 가능성 [상/중/하] — 완화: [방법]

안티패턴 체크:
- [ ] Bypassing hierarchy 없음 (PM 통해 모든 결정)
- [ ] Cross-domain 수정 없음 (지정 범위 내)
- [ ] 추측 실행 없음 (스펙 명확 후 착수)
```

### Step 5: Acceptance Criteria (AC) 정의

```
완료 기준 (AC):
- AC-1: [측정 가능한 기준]
- AC-2: [측정 가능한 기준]
- AC-3: [측정 가능한 기준]

검증 방법:
- [ ] 자동 테스트 실행 가능
- [ ] 수동 확인 필요 (항목: )
- [ ] validate-config 통과
```

## 출력 형식 (PM 보고용)

```
## [태스크명] Kickoff 완료

**스코프**: [한 줄]
**팀**: [에이전트 목록]
**예상 산출물**: [N개]
**위험**: [핵심 위험 1개]
**AC**: [N개]

→ 착수합니다.
```

## Gotchas

- 스코프 확인 없이 바로 코딩 시작하면 Anti-Pattern #5 위반
- AC가 없으면 완료 판정 불가 — 반드시 Step 5 완료 후 착수
- 팀 크기 3명 초과 시 PM 승인 필요
