# Harness Upgrade PRD — 단일 Claude Code 대비 압도적 우위 확보

> 작성일: 2026-03-23  
> 작성자: PM (aiorg_product_bot)  
> 버전: 1.0  
> 상태: **승인 대기** (Rocky 검토 필요)

---

## 1. 배경 및 목표

### 1.1 배경

단일 Claude Code 세션(이하 "단일 세션")과 telegram-ai-org harness의 품질 비교 결과,  
**훅 시스템·path-scoped 규칙·스킬 컨텍스트 주입** 3개 축에서 우리가 뒤처짐이 확인됐다.

추가로 game-studios-analysis.md(Claude-Code-Game-Studios 레퍼런스 분석)를 통해  
구체적 격차 항목과 포팅 가능 패턴이 식별됐다.

### 1.2 목표

> "단일 Claude Code 세션이 할 수 있는 모든 것을, harness는 더 안전하고 더 체계적으로 수행한다."

| 차원 | 단일 세션 현황 | Harness 목표 |
|------|--------------|-------------|
| 안전성 | 실수 시 즉시 피해 | 훅 기반 사전 차단 (exit 2) |
| 일관성 | 세션마다 컨텍스트 재로드 | SessionStart 자동 주입 |
| 추적성 | 없음 | 에이전트 감사 로그 |
| 스코프 제어 | 없음 | Path-scoped rules |
| 스킬 정확도 | 매번 추론 | allowed-tools 명시 |

### 1.3 성공 지표 (KPI)

| KPI | 기준선 (2026-03-23) | 목표 (4주 후) |
|-----|-------------------|--------------|
| 위험 명령어 사전 차단율 | 0% (훅 미작동) | 100% (훅 등록 완료) |
| 훅 이벤트 커버리지 | 2/5 이벤트 | 5/5 이벤트 |
| Path-scoped rules | 0개 | 4개 (core/bots/tests/scripts) |
| 스킬 allowed-tools 적용률 | 3/20개 (15%) | 12/20개 (60%) |
| 에이전트 감사 로그 보존율 | 0% | 100% (SubagentStart 훅) |
| 인시던트 재발 (glob 사고류) | 1건/월 | 0건/월 |

---

## 2. Phase 1 결과 — 호환 가능 인사이트 선별

### 2.1 호환 가능 항목 (채택)

| # | 항목 | 출처 | 호환 이유 | 기대 효과 | 구현 복잡도 | 임팩트 |
|---|------|------|----------|----------|------------|-------|
| A-1 | PreToolUse(Bash) 위험 패턴 훅 | game-studios `validate-commit.sh` | 기존 settings.json hook 구조와 동일 | glob/찾기 사고 재발 방지 | 낮음 | **최고** |
| A-2 | SessionStart 컨텍스트 로드 훅 | game-studios `session-start.sh` | SessionStart 이벤트 지원됨 | 매 세션 프로젝트 상태 자동 파악 | 낮음 | 높음 |
| A-3 | SubagentStart 감사 로그 훅 | game-studios `log-agent.sh` | SubagentStart 이벤트 지원됨 | 에이전트 호출 완전 추적 | 낮음 | 높음 |
| A-4 | Path-scoped rules (4개) | game-studios 11개 rules | `.claude/rules/` 디렉토리 동일 지원 | 도메인별 다른 규칙 적용 | 중간 | 높음 |
| A-5 | 스킬 `allowed-tools` 필드 | game-studios skill frontmatter | SKILL.md frontmatter 지원 | 에이전트 도구 사용 범위 명확화 | 낮음 | 중간 |
| A-6 | 스킬 `context` 블록 (셸 결과 주입) | game-studios skill frontmatter | SKILL.md frontmatter 지원 | 스킬 실행 시 최신 상태 자동 로드 | 낮음 | 중간 |
| A-7 | Anti-patterns 5개 global_instructions 추가 | game-studios coordination docs | orchestration.yaml global_instructions 동일 지원 | 에이전트 간 협업 품질 향상 | 낮음 | 높음 |
| A-8 | Incident-response, post-mortem 문서 템플릿 | game-studios 27개 templates | 우리 docs/ 디렉토리에 직접 적용 | 장애 대응 표준화 | 중간 | 중간 |

> **✅ A-1, A-2, A-3, A-5, A-6, A-7 → 이번 PRD 범위에서 이미 완료**  
> **A-4 → 이번 PRD 범위에서 완료 (4개 rules 신설)**  
> **A-8 → 다음 PRD 범위 (문서 템플릿)**

### 2.2 호환 불가 항목 (제외)

| # | 항목 | 제외 사유 |
|---|------|----------|
| B-1 | User-approval 프로토콜 | 우리는 완전 자율 실행 모델. 승인 대기는 harness 흐름을 파괴함 |
| B-2 | "No commits without user instruction" 규칙 | 우리 봇은 커밋까지 자율 수행이 설계 목표 |
| B-3 | 게임 도메인 전용 스킬 (balance-check, asset-audit 등) | 도메인 불일치. 텔레그램 봇 오케스트레이션과 무관 |
| B-4 | `src/ai/**`, `src/gameplay/**` 등 게임 path rules | 우리 프로젝트 디렉토리 구조와 불일치 |
| B-5 | `validate-push.sh` (protected branch 경고) | 우리는 main branch push를 infra org가 관리. 중복 |
| B-6 | `validate-assets.sh` (파일 네이밍 컨벤션) | 게임 에셋 네이밍 규칙. 우리 프로젝트 무관 |
| B-7 | `detect-gaps.sh` (코드 있는데 문서 없으면 경고) | 우리 docs 구조와 경로 불일치. 포팅 시 노이즈 위험 |

---

## 3. 개선 우선순위 — ICE 스코어링

> ICE = Impact × Confidence × Ease (각 1-10)

| # | 개선 항목 | Impact | Confidence | Ease | ICE | MoSCoW |
|---|----------|--------|------------|------|-----|--------|
| P-1 | 훅 3개 settings.local.json 등록 | 10 | 10 | 9 | **900** | **Must** |
| P-2 | Path-scoped rules 4개 신설 | 8 | 9 | 7 | **504** | **Must** |
| P-3 | 스킬 allowed-tools 보강 (20개 중 미적용분) | 7 | 9 | 8 | **504** | **Should** |
| P-4 | 스킬 context 블록 도입 (상위 5개) | 6 | 8 | 8 | **384** | **Should** |
| P-5 | Anti-patterns 5개 orchestration.yaml 추가 | 7 | 8 | 6 | **336** | **Should** |
| P-6 | Incident-response / post-mortem 문서 템플릿 | 5 | 8 | 6 | **240** | **Could** |
| P-7 | agent-coordination-map.md 작성 | 5 | 7 | 5 | **175** | **Could** |
| P-8 | session-stop.sh (Stop 이벤트) 구현 | 4 | 8 | 7 | **224** | **Could** |

### 구현 순서

```
Week 1 (즉시): P-1 → P-2 → P-3 → P-4
Week 2:        P-5 → P-8
Week 3-4:      P-6 → P-7
```

---

## 4. 부작용 리스크 항목 및 완화 방안

| # | 개선 항목 | 예상 부작용 | 완화 방안 | Rocky 승인 필요 |
|---|----------|------------|----------|----------------|
| R-1 | PreToolUse(Bash) 훅 | 정상 명령도 오탐 차단 가능 (false positive) | 패턴 정규식 정밀화, 초기 2주는 exit 1(경고)만, 이후 exit 2(차단)으로 전환 | ❌ |
| R-2 | SessionStart 훅 | 세션 시작 지연 (15초 타임아웃) | timeout 15초 내 완료하도록 script 최적화. 실패 시 exit 0으로 무시 | ❌ |
| R-3 | Path-scoped rules | 기존 코드와 충돌하는 규칙 적용 시 에이전트 혼란 | 규칙을 "금지" 위주 아닌 "권장" 위주로 작성. 강제 차단 없음 | ❌ |
| R-4 | allowed-tools 명시 | 스킬 실행 시 미등록 도구 접근 시도 실패 | 스킬별 실제 사용 도구 사전 확인 후 추가. Read/Bash/Glob/Grep 기본 포함 | ❌ |
| R-5 | context 블록 (셸 실행) | context 명령 실행 실패 시 스킬 로드 오류 | `2>/dev/null` 접미사 필수, 모든 context 명령에 에러 무시 처리 | ❌ |
| R-6 | SubagentStart 로그 | 로그 파일 무한 증가 | `~/.ai-org-agent-audit.log` 일 1MB 초과 시 rotate. logrotate 설정 추가 권장 | ❌ |
| R-7 | 문서 템플릿 신설 | 기존 docs/ 구조와 혼재 | `docs/templates/` 서브디렉토리 전용 분리 | ❌ |

> **🔴 Rocky 승인 필요 항목**: 없음 — 이번 변경은 모두 설정/규칙/스킬 레이어이며 프로덕션 데이터 변경 없음

---

## 5. 단계별 로드맵

### Phase A (완료 — 2026-03-23)

**목표**: 기존에 만들어놓고 미등록이었던 기능 전부 활성화

| 산출물 | 상태 |
|--------|------|
| 훅 3개 settings.local.json 등록 (SessionStart/PreToolUse/SubagentStart) | ✅ 완료 |
| Path-scoped rules 4개 신설 (core/bots/tests/scripts) | ✅ 완료 |
| harness-audit, brainstorming-auto allowed-tools 추가 | ✅ 완료 |
| harness-audit, brainstorming-auto, quality-gate context 블록 추가 | ✅ 완료 |

### Phase B (1주 내)

**목표**: 스킬 전체 allowed-tools 완성 + Anti-patterns orchestration 반영

| 산출물 | 담당 | 예상 소요 |
|--------|------|----------|
| .claude/skills/ 전체 20개 스킬 allowed-tools 감사 및 보강 | engineering bot | 2-3시간 |
| session-stop.sh 구현 (Stop 이벤트 → 작업 로그 + 미완료 태스크 요약) | engineering bot | 1-2시간 |
| logrotate 설정 (ai-org-agent-audit.log) | ops bot | 30분 |

### Phase C (2-3주)

**목표**: 문서 템플릿 + 조율 맵 완성

| 산출물 | 담당 | 예상 소요 |
|--------|------|----------|
| docs/templates/ — incident-response, post-mortem, sprint-plan, ADR 4종 | PM + design bot | 4시간 |
| docs/agent-coordination-map.md — 태스크 유형별 봇 라우팅 플로우 | PM | 2시간 |
| validate-dangerous-patterns.sh 오탐 분석 후 패턴 정밀화 | engineering bot | 2-3시간 |

---

## 6. 단일 Claude Code 대비 차별화 요약

| 역량 | 단일 Claude Code | telegram-ai-org Harness (Phase A 완료 후) |
|------|-----------------|------------------------------------------|
| 위험 명령 차단 | 없음 (Claude 판단에만 의존) | **PreToolUse 훅으로 패턴 매칭 차단** |
| 세션 컨텍스트 | 매번 수동 | **SessionStart 자동 주입** |
| 에이전트 추적 | 없음 | **SubagentStart 감사 로그** |
| 도메인 규칙 | 전역 단일 | **Path-scoped 4개 영역별 규칙** |
| 스킬 실행 정확도 | 추론 기반 | **allowed-tools 명시 기반** |
| 다중 전문가 협업 | 불가 | **조직별 병렬 실행 + COLLAB 위임** |
| 작업 영속성 | 세션 종료 시 소실 | **DB 저장 + 태스크 그래프 유지** |

---

*이 PRD는 game-studios-analysis.md 분석 결과와 telegram-ai-org 현황 갭 분석을 기반으로 작성됨*  
*다음 리뷰: Phase B 완료 후 (예정: 2026-03-30)*
