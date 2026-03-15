# Architecture Comparison: `telegram-ai-org` vs `oh-my-claudecode` vs `oh-my-openagent`

작성일: 2026-03-15  
범위: 로컬에 있는 다음 자료 기준 비교

- `/Users/rocky/telegram-ai-org/ARCHITECTURE.md`
- `/Users/rocky/Downloads/agent-reference/oh-my-claudecode/docs/ARCHITECTURE.md`
- `/Users/rocky/Downloads/agent-reference/oh-my-openagent/docs/guide/orchestration.md`

## 결론 요약

`telegram-ai-org`는 이미 "여러 코딩에이전트를 조직 단위로 통제하는 상위 레이어"라는 방향이 맞다. 다만 `oh-my-claudecode`와 `oh-my-openagent`에 비해 아직 약한 부분은 다음 세 가지다.

1. 사용자의 의도를 더 명확하게 게이팅하고 실행 표면을 일관되게 고르는 계층
2. 계획, 실행, 검증, 회고가 하나의 작업 그래프로 이어지는 운영 강제력
3. 장기 운영 중 자동 품질 점검과 자기개선 루프의 제품화 수준

반대로 `telegram-ai-org`가 더 강한 부분도 있다.

1. Telegram을 실사용 UI이자 조직 버스로 직접 사용한다
2. 조직별 identity, chat binding, engine, backend policy가 실제 운영에 연결돼 있다
3. 사용자와 하위 에이전트 사이의 협업/배분 흔적이 비교적 명시적으로 남는다

## 1. 핵심 아키텍처 철학 비교

### `telegram-ai-org`

- 중심 철학: Telegram 방을 작업 허브로 두고, Global PM이 specialist 조직을 배분/통제한다.
- 운영 단위: `global + specialist orgs`
- 핵심 자산: `organizations.yaml`, `orchestration.yaml`, `ContextDB`, runbook, Telegram relay

### `oh-my-claudecode`

- 중심 철학: Claude Code 안에 skill composition을 주입해, 하나의 에이전트를 다중 skill / 다중 agent orchestration으로 바꾼다.
- 운영 단위: skill layer + agent tier + verification protocol
- 핵심 자산: `CLAUDE.md`, skills, hooks, state files

### `oh-my-openagent`

- 중심 철학: planning layer와 execution layer를 분리하고, orchestrator가 specialized worker를 category로 라우팅한다.
- 운영 단위: planner, conductor, workers, wisdom/notepad, intent gate
- 핵심 자산: plan files, orchestration layers, category-based routing

## 2. 현재 `telegram-ai-org`의 강점

### 실제 운영형 Telegram binding

- 단순 CLI 실험이 아니라 실제 Telegram room을 입출력 인터페이스로 삼는다.
- 조직별 bot token/chat binding이 canonical config로 관리된다.
- 사용자, PM, 조직봇, 첨부파일, 산출물 업로드가 실제 운영 경로로 이어진다.

### 조직 단위의 책임 분리

- product/design/engineering/growth/ops/research 등 specialist org가 명시적이다.
- 각 조직은 identity, engine preference, team config를 가진다.
- PM이 직접 실행할지, local execution으로 갈지, delegate할지 전략적으로 고른다.

### 런북과 상태 추적

- planning/design/implementation/verification/feedback이 runbook에 기록된다.
- ContextDB에 pm_tasks, dependencies, discussions, goals, verification 데이터가 축적된다.

## 3. 현재 `telegram-ai-org`의 약점

### Intent Gate가 약하다

- `NLClassifier + PMRouter + plan_request()` 조합은 있지만, 사용자의 "진짜 원하는 것"을 한 번에 안정적으로 분기하는 전용 게이트가 약하다.
- `oh-my-openagent`의 Intent Gate처럼 research / implementation / investigation / planning / review를 더 명시적으로 갈라줄 필요가 있다.

### 실행 강제력이 아직 분산돼 있다

- 계획, 태스크 분해, 실행, 검증, 회고는 존재하지만 코드 상 여러 컴포넌트에 흩어져 있다.
- `oh-my-claudecode`의 hook discipline, `oh-my-openagent`의 conductor-first 흐름처럼 더 강한 single control loop가 필요하다.

### 자기개선 루프가 아직 제품화되지 않았다

- 최근 대화 리뷰 스크립트와 runbook은 생겼지만, 개선 제안을 코드 액션 후보와 운영 지표로 자동 연결하는 수준은 아직 초기다.

### multimodal/attachment lane이 아직 1차 수준이다

- 이미지와 PDF 입력은 이제 처리 가능하지만, OCR/diagram/table/slide/vision lane이 별도 전략으로 분리돼 있지는 않다.

## 4. `oh-my-claudecode`에서 배울 점

### Skill composition

- 기능을 "새 agent 추가"가 아니라 "behavior injection"으로 설계하는 점이 좋다.
- `telegram-ai-org`도 장기적으로는 기능 추가를 모듈형 execution policy / workflow skill로 더 분해하는 편이 좋다.

### Hook-based discipline

- lifecycle hook으로 continuation, verification, tool-use discipline을 강제하는 구조는 운영 품질을 올린다.
- 현재 리포는 일부 규율이 prompt에 많이 의존하므로, runtime hook 성격의 강제를 더 늘릴 여지가 크다.

### CLI-first control surface

- 설치/운영/진단/팀 실행이 명확한 CLI로 정리돼 있다.
- `telegram-ai-org`도 최근 `orchestration_cli`와 review job을 확장했지만, 아직 운영 surface가 더 부족하다.

## 5. `oh-my-openagent`에서 배울 점

### Planning layer와 execution layer 분리

- planner가 계획을 만들고 conductor가 실행하는 분리가 명확하다.
- `telegram-ai-org`도 PM planning과 specialist execution이 있지만, 경계와 데이터 계약을 더 선명하게 만들 필요가 있다.

### Wisdom accumulation

- 이전 작업의 learnings를 구조적으로 누적하고 후속 worker에게 넘기는 철학이 강하다.
- 현재 `telegram-ai-org`는 global context / memory / runbook이 있으나, 후속 태스크로 전달되는 지혜가 아직 얕다.

### Category-based routing

- 구체 모델명이 아니라 category로 worker lane을 고르게 하는 점이 좋다.
- `telegram-ai-org`도 engine 선택은 있으나, "task category -> execution lane" 매핑은 더 발전시킬 수 있다.

## 6. 즉시 가져올 가치가 큰 개선 방향

### A. Intent Gate 강화

- `route_request`를 더 세분화해서 최소한 아래 범주를 명시적으로 나누는 것이 좋다.
- `clarify`
- `direct_answer`
- `single_org_execution`
- `multi_org_execution`
- `review_or_audit`
- `attachment_analysis`

### B. Execution lane 분리

- 현재 하나의 relay에 많은 책임이 있다.
- 다음 lane을 명시적으로 분리하면 유지보수가 쉬워진다.
- `chat lane`
- `task lane`
- `attachment lane`
- `review lane`
- `delivery lane`

### C. Review/Autopilot lane 강화

- 최근 대화 리뷰는 이제 cron으로 돌 수 있지만, 다음 단계는 "리포트 -> 개선 후보 -> 승인 가능한 patch plan"으로 이어지는 것이다.

### D. Multimodal lane 강화

- 이미지/문서/다중 첨부 묶음을 하나의 task packet으로 표준화하는 것이 좋다.
- 이 리포는 그 방향의 1차 확장으로 간주할 수 있다.

## 7. 권장 로드맵

### P0

- Intent Gate 강화
- delivery lane와 attachment lane 분리
- runbook / ContextDB / review job 사이의 연결 강화

### P1

- review 리포트가 자동으로 개선 issue / patch plan 후보를 만들게 확장
- specialist org 간 context handoff 포맷 표준화
- artifact type별 post-processing 강화 (PDF/slide/image/web snapshot)

### P2

- 장기적으로는 Telegram layer를 유지한 채 내부 orchestration contract를 더 CLI-first / state-machine 방식으로 정제
- 즉 "Telegram UI + orchestrator core" 구조로 명확히 분리

## 최종 판단

`telegram-ai-org`는 이미 단순한 봇 묶음이 아니라 "상위 코딩에이전트 레이어"로 가는 올바른 방향 위에 있다.  
다만 현재는 운영형 PM 조직 시스템과 실험형 orchestration harness 사이의 중간 상태다.

가장 중요한 다음 단계는 "더 많은 기능 추가"가 아니라 다음 세 가지를 더 선명하게 만드는 것이다.

1. 의도 분기
2. 실행 lane 분리
3. 자기개선 루프의 제품화

이 세 가지가 정리되면, Telegram 기반 상위 코딩에이전트라는 포지션은 충분히 경쟁력 있다.
