# aiorg 조직 회고 리포트
**비교 기준**: Claude Code Game Studios (github.com/Donchitos/Claude-Code-Game-Studios)
**작성 기준일**: 2026-03-22
**작성자**: aiorg_pm_bot (리서치실 통합)

---

## 1. Executive Summary (핵심 발견 3줄)

> **규모는 압도적이나, 운영 자동화와 AI 행동 철학에서 뒤집힌다.**
>
> 1. aiorg는 에이전트 수(197 vs 48)와 스킬 깊이(safe-modify 6단계 방법론 등)에서 Game Studios를 앞서지만, **이벤트 훅(1개 vs 6종 8개)과 커버리지(20스킬 vs 37스킬)에서 명확히 뒤처진다.**
> 2. 가장 큰 구조적 차이는 **AI 행동 철학**: Game Studios는 "질문→대기→승인" 원칙을 전체 48개 에이전트에 일관 적용하나, aiorg는 "자율 실행"이 기본값이다.
> 3. 위계 구조는 aiorg가 2-tier(PM→전문실)인 반면 Game Studios는 3-tier(Director→Lead→Specialist)로, **복잡한 태스크에서 에스컬레이션 경로가 불명확하다.**

---

## 2. 4개 기준축별 비교 매핑 테이블

### Phase 1 산출물: 4축 비교 매핑 테이블

| 기준축 | SNS 벤치마크 (Game Studios) | aiorg 현황 | 갭 |
|--------|---------------------------|------------|-----|
| **① 스킬 정교함** | 37개 스킬, 생애주기 전 단계 커버 (brainstorm→prototype→sprint→gate-check→release→retro→hotfix) | 20개 스킬, 단계별 gotchas.md, LLM 연동 스킬(failure-detect-llm) | ⚠️ 커버리지 -46%, 깊이는 동등↑ |
| **② 분업 위계** | 3-tier 계층(Director→Lead→Specialist), 도메인 전용 에이전트 48개 | 2-tier(PM Orchestrator→6 전문실), 범용 서브에이전트 197개 | ⚠️ Lead 티어 부재, 에스컬레이션 경로 불명확 |
| **③ 워크플로우 자동화** | 이벤트 훅 6종 8개(SessionStart×2, PreToolUse×2, PostToolUse×1, PreCompact×1, Stop×1, SubagentStart×1), 권한 allow/deny 명시, statusline, session-state 크래시 복구 | 스킬 내 PostToolUse 훅 1개(quality-gate), orchestration.yaml phase_policies/backend_policies | ❌ 이벤트 훅 대비 8분의 1, 자동 검수 훅 부재 |
| **④ AI 질문-대기 패턴** | "Question→Options→Decision→Draft→Approval" 전사 적용, 파일 쓰기 전 반드시 승인 요청, AskUserQuestion UI 도구 | [COLLAB] 태그 기반 조직 간 위임, 자율 실행 규칙이 기본값 | ❌ 패턴 역전: aiorg는 자율이 기본, 질문-대기가 예외 |

---

### Phase 1 산출물: aiorg 현황 요약 시트

| 항목 | 수치/현황 |
|------|----------|
| 에이전트(서브에이전트) 수 | 197개 |
| 전문 부서 수 | 7개 (PM×1 + 전문실×6: 개발/디자인/성장/운영/기획/리서치) |
| 스킬 수 | 20개 (quality-gate, safe-modify, bot-triage, failure-detect-llm, engineering-review, design-critique, brainstorming-auto, growth-analysis, harness-audit, performance-eval, pm-discussion, pm-task-dispatch, retro, weekly-review, loop-checkpoint, skill-evolve, create-skill, error-gotcha, autonomous-skill-proxy, failure-detect-llm) |
| 스킬당 gotchas.md | ✅ 대부분 보유 (학습 루프 존재) |
| 이벤트 훅 | 스킬 레벨 1개 (quality-gate PostToolUse/Write), 프로젝트 레벨 settings.json 없음 |
| 글로벌 운영 원칙 | orchestration.yaml global_instructions (5개 원칙: 스코프, 인프라전담, git worktree, 현재시간, 위험탐색금지) |
| 위계 구조 | 2-tier (PM Orchestrator → Specialist) |
| 공통 스킬(전 부서 적용) | 3개 (quality-gate, error-gotcha, bot-triage) |
| AI 행동 기본값 | 자율 실행 (확인 없이 완료 후 보고) |
| 크래시 복구 메커니즘 | 없음 (Game Studios: session-state 파일 기반 복구 존재) |

---

## 3. 강점·약점 분석 (Phase 2)

### 강점 (잘하고 있는 것)

#### ① 스킬 정교함 — 강점
- **safe-modify**: 6단계 방법론(Pre-flight → Defensive Programming → Feature Flag → Canary → Smoke Test → Rollback), Game Studios에 없는 수준의 고위험 코드 수정 가이드라인
- **failure-detect-llm**: LLM(Gemini 2.5 Flash) 연동으로 경계 케이스 자동 재검증 — Game Studios에는 이런 AI 보강 스킬 없음
- **gotchas.md 학습 루프**: 스킬별 오류 기록 및 재발 방지 — 조직 학습이 파일로 축적됨
- **skill-evolve + create-skill**: 스킬 자체를 진화시키는 메타 스킬 보유

#### ② 분업 위계 — 강점
- **에이전트 풀 규모**: 197개 vs 48개 — 도메인 커버리지에서 4배 이상 우위
- **organizations.yaml 기반 라우팅**: 태스크별 자동 부서 배정 로직 존재
- **COLLAB 태그 패턴**: 조직 간 협업 위임 경로가 명시적

#### ③ 워크플로우 자동화 — 강점
- **orchestration.yaml phase_policies**: intake→planning→design→implementation→verification→feedback 6단계 자동 문서화 요구
- **backend_policies**: tmux_batch, resume_session 전략으로 장기 실행 태스크 처리
- **global_instructions**: 전 조직에 동일한 5개 핵심 원칙 자동 주입

#### ④ AI 질문-대기 패턴 — 강점
- **자율 실행의 생산성**: 반복적이고 명확한 태스크에서 Game Studios보다 훨씬 빠른 처리 속도
- **[TEAM:solo] 직접 답변 원칙**: PM이 판단해 팀 구성 없이 즉시 응답 가능 — 불필요한 대기 제거

---

### 약점 (부족한 것) + 우선순위 매트릭스

#### Phase 2 산출물: 영향도 × 실행용이성 매트릭스

```
               실행 용이성
               쉬움        어려움
              ┌──────────────┬──────────────┐
영향도 높음   │  HIGH        │  HIGH        │
              │ [A] 이벤트훅 │ [B] Lead티어  │
              │ [C] 스킬커버 │              │
              ├──────────────┼──────────────┤
영향도 낮음   │  MID         │  LOW         │
              │ [D] 질문패턴 │ [E] 크래시복구│
              │  일부도입    │              │
              └──────────────┴──────────────┘
```

#### Phase 2 산출물: 개선 우선순위 표

| # | 약점 항목 | 기준축 | 영향도 | 용이성 | 우선순위 | 개선 방향 |
|---|-----------|--------|--------|--------|---------|-----------|
| A | **이벤트 훅 부재** — 프로젝트 레벨 settings.json 없음, SessionStart/PreToolUse/Stop 훅 0개 | ③ 자동화 | 높음 | 쉬움 | **HIGH** | .claude/settings.json 생성 + SessionStart(현재시간 확인), PreToolUse(dangerous pattern 차단), Stop(산출물 저장) 3개 훅 즉시 추가 |
| C | **스킬 커버리지 공백** — /sprint-plan, /scope-check, /gate-check, /estimate, /tech-debt 없음 | ① 스킬 | 높음 | 쉬움 | **HIGH** | create-skill 스킬을 활용해 sprint-plan, scope-check 2개 우선 작성 (템플릿 이미 보유) |
| D | **질문-대기 패턴 미정착** — 고위험/모호한 태스크에서도 자율실행 기본값 적용됨 | ④ AI패턴 | 높음 | 쉬움 | **HIGH** | orchestration.yaml global_instructions에 "모호한 태스크 수신 시 먼저 가정 목록을 사용자에게 확인" 원칙 추가 |
| B | **Lead 티어 부재** — PM → Specialist 2단계, 복잡 태스크 에스컬레이션 경로 없음 | ② 위계 | 높음 | 어려움 | **HIGH** | PM 역할 내 "Tech Lead / Design Lead" 역할을 수행하는 전담 에이전트 지정 (신규 조직 불필요, 기존 PM 프롬프트에 조정자 역할 추가) |
| E | **크래시 복구 없음** — 세션 중단 시 진행 상태 소실 | ③ 자동화 | 낮음 | 어려움 | **LOW** | session-state 파일 패턴 벤치마킹 후 중기 도입 |

---

## 4. 개선 우선순위 로드맵 (Phase 3)

### 단기 — 즉시 실행 (이번 주 내)

| 액션 | 담당 | 산출물 |
|------|------|--------|
| **[A] 프로젝트 레벨 .claude/settings.json 생성** — SessionStart(date 확인 훅), PreToolUse(위험 패턴 차단), Stop(보고 훅) 3개 이벤트 추가 | 운영실 | settings.json |
| **[D] global_instructions 업데이트** — "모호성 임계 기준 3가지 조건" 추가: ① 파일 수정 범위 불명확 ② 사용자 의도 다중 해석 가능 ③ 복구 불가능한 작업 → 이 3조건 중 하나라도 해당하면 실행 전 가정 목록 확인 요청 | PM | orchestration.yaml |

### 중기 — 1~3개월

| 액션 | 담당 | 산출물 |
|------|------|--------|
| **[C] sprint-plan 스킬 작성** — 주간 태스크 우선순위화, 부서별 로드 밸런싱 | 기획실 + PM | skills/sprint-plan/ |
| **[C] scope-check 스킬 작성** — 태스크 수신 시 범위·영향 파일 목록·예상 시간 3가지를 먼저 출력 | 개발실 | skills/scope-check/ |
| **[B] PM 역할에 Lead 기능 명시** — organizations.yaml PM identity에 "복잡 기술 판단 → Tech Lead 역할 위임 가능" 추가, 기존 backend-architect 에이전트를 Lead급으로 명시 지정 | PM | organizations.yaml |
| **[C] gate-check 스킬 작성** — 도메인별 체크리스트 (설계→구현→테스트→배포) | 운영실 | skills/gate-check/ |

---

## 5. 결론

aiorg는 **"규모와 깊이"** 측면에서 Game Studios를 앞선다.
197개 에이전트 풀, safe-modify의 방법론적 완성도, LLM 보강 스킬, gotchas 학습 루프는 단순 숫자 이상의 성숙도를 보여준다.

그러나 SNS 글이 지적한 **"얼마나 정교한 스킬과 파이프라인으로 쪼개느냐"** 기준에서는 세 가지를 놓치고 있다:

1. **자동화 접착제(훅) 부재** — 잘 정의된 스킬들이 이벤트로 연결되지 않으면 워크플로우가 아닌 체크리스트에 머문다.
2. **스킬 생애주기 커버리지 공백** — sprint-plan, scope-check, gate-check 같은 "흐름 제어" 스킬이 없어 태스크 경계가 흐릿하다.
3. **AI 행동 철학의 방향** — Game Studios가 "질문-대기-승인"을 기본값으로 삼는 반면, aiorg는 자율 실행이 기본이다. 이는 생산성과 안전성 사이의 의식적 선택인데, **모호한 태스크에서의 예외 기준이 명문화되지 않은 것**이 리스크다.

**다음 한 발**: settings.json 이벤트 훅 3개 추가 + global_instructions 모호성 기준 명문화가 가장 작은 비용으로 가장 큰 효과를 낸다.

---

*보고서 생성: aiorg_pm_bot | 조사 기준: 2026-03-22 | 비교 대상: github.com/Donchitos/Claude-Code-Game-Studios (로컬 클론 기준)*
