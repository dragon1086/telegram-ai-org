# 멀티에이전트 Harness 약점 분석 보고서
> **작성 기준**: 2026-03-23
> **작성자**: aiorg_pm_bot (리서치실)
> **선행 분석**: `reports/retro-gamestudios-comparison-2026-03-22.md`
> **분석 대상**: game-studios-analysis.md + 현재 harness 구조 (orchestration.yaml, CLAUDE.md, settings.local.json)

---

## ① 분석 배경 및 범위

**목표**: 단일 Claude Code 세션 대비 우리 멀티에이전트 시스템의 약점을 구체적으로 식별하고, game-studios-analysis.md에 기록된 적용 계획의 실행 현황을 점검한다.

**분석 범위**:
- `docs/game-studios-analysis.md` — game studios 비교 분석 및 포팅 계획
- `.claude/settings.local.json` — 현재 등록된 훅 및 권한
- `orchestration.yaml` — 글로벌 지시 및 팀 프로파일
- `CLAUDE.md` — 운영 원칙 및 개발 규칙
- `scripts/hooks/` — 현재 작성된 훅 스크립트
- `skills/` — 현재 스킬 목록 및 frontmatter 구조

---

## ② Harness 현황 요약

### 현재 등록된 훅 (settings.local.json 기준 — 실제 실행되는 것)

| 이벤트 | 구현 방식 | 역할 |
|--------|-----------|------|
| `PostToolUse(Write\|Edit)` | inline bash | .py 파일 수정 시 ruff lint 자동 실행 |
| `Stop` | inline bash | 세션 종료 시각 로그 기록 |

**등록된 훅: 2개 (PostToolUse 1개 + Stop 1개)**

### 스크립트는 있지만 훅에 미등록된 것 (스크립트 파일 존재, settings에 없음)

| 스크립트 | 경로 | 연결 이벤트 | 상태 |
|---------|------|------------|------|
| `validate-dangerous-patterns.sh` | `scripts/hooks/` | `PreToolUse(Bash)` | ❌ **미등록 — 실행 안 됨** |
| `session-start.sh` | `scripts/hooks/` | `SessionStart` | ❌ **미등록 — 실행 안 됨** |
| `log-agent.sh` | `scripts/hooks/` | `SubagentStart` | ❌ **미등록 — 실행 안 됨** |

> ⚠️ **가장 중요한 발견**: `validate-dangerous-patterns.sh`는 glob/os.walk 위험 패턴 차단을 목적으로 만들어졌으나, settings.local.json에 등록되지 않아 **현재 전혀 실행되지 않는다**. 2026-03-23 시스템 먹통 인시던트를 재발 방지하기 위해 만든 스크립트가 유령 파일로 존재한다.

### 스킬 현황

| 항목 | 현황 |
|------|------|
| 스킬 수 | 20개 (skills/, .claude/skills/ 합산) |
| `allowed-tools` 명시 | ❌ 전체 0개 |
| `context:` 블록 (셸 자동 주입) | ❌ 전체 0개 |
| Path-scoped rules | ❌ 전체 0개 |
| Document templates | ❌ 전체 0개 |

### orchestration.yaml global_instructions 현황

현재 5개 원칙 포함:
1. PM 업무 스코프 준수
2. 배포·인프라 전담 원칙
3. Git 워크트리 워크플로
4. 현재 시간 사용 원칙
5. 위험한 시스템 탐색 절대 금지

**미포함**: game-studios-analysis.md §Agent 조율 Anti-patterns 5개

---

## ③ 단일 Claude Code 세션 대비 약점·누락 패턴

### A. 단일 세션의 4가지 핵심 강점 vs 우리 대응 현황

| # | 단일 세션 강점 | 우리 harness 대응 | 격차 수준 |
|---|--------------|-------------------|---------|
| 1 | **컨텍스트 일관성** — 모든 도구 호출·파일 읽기·대화가 하나의 메모리에서 유지됨 | `SharedMemory` → `context_db` 캐시 (T-260에서 구현), 대화 히스토리 `MAX_HISTORY_MESSAGES=10` 주입 | ⚠️ 에이전트 간 전달 시 요약 손실 발생 |
| 2 | **즉각적 피드백 루프** — 코드 수정 → 테스트 → 결과 → 재수정이 0-latency로 연결 | 각 봇이 독립 세션 → 태스크 결과를 텍스트로 전달받음 → 에러 컨텍스트 손실 가능 | ❌ 이진 결과(성공/실패)만 전달, 중간 상태 소실 |
| 3 | **상태 공유 무비용** — 모든 변수·함수·메모리가 즉시 공유됨 | `context_db` + `lesson_memory` + `SharedMemory` 캐시로 부분 보완 | ⚠️ DB 조회 비용 + 스키마 맞춤 오버헤드 |
| 4 | **도구 직접 접근** — Bash, Read, Write, Glob 등 모든 도구가 단일 컨텍스트에서 제약 없이 사용 | 각 에이전트가 동일 도구에 접근하나, 전 에이전트 동일 도구 셋 — 스코프 제한 미구현 | ❌ `allowed-tools` 미명시로 에이전트별 도구 범위 불명확 |

### B. 리서치·문서요약·경쟁사 분석 태스크에서 발생하는 누락 패턴

> 근거: `game-studios-analysis.md` §개요 — "48개 에이전트, 37개 스킬, 8개 훅"과 우리 분석 경험 기반

| 패턴 | 발생 메커니즘 | 원인 분류 | 영향 |
|------|-------------|---------|------|
| **정보 단절** | PM→에이전트 태스크 브리프가 텍스트 요약만 전달됨. 원본 파일 경로·쿼리 히스토리가 소실됨 | 설계상 한계 (텍스트 기반 IPC) | 에이전트가 다시 같은 파일 조사 → 중복 비용 |
| **중복 조사** | 동일 키워드로 여러 에이전트가 웹검색/파일검색 수행. 결과 캐시 없음 | 운영상 미비 (검색 결과 공유 레이어 없음) | API 비용 증가, 시간 낭비 |
| **컨텍스트 소실** | PreCompact 시 에이전트별 세션이 독립 compact 됨 | 설계상 한계 (per-agent compact) | 관련 에이전트들이 상이한 컨텍스트 상태에 놓임 |
| **결론 불일치** | 두 에이전트가 동일 문서를 다르게 요약 → PM이 중재 불가 | 운영상 미비 (에이전트 간 검증 레이어 없음) | 보고서 품질 저하 |
| **도구 남용** | allowed-tools 없으므로 리서치 에이전트가 불필요하게 Edit·Write 도구 사용 가능 | 운영상 미비 (allowed-tools 미등록) | 의도치 않은 파일 수정 리스크 |
| **훅 실행 실패** | validate-dangerous-patterns.sh 미등록으로 위험 패턴 실시간 차단 불가 | 운영상 미비 (스크립트-설정 불일치) | 인시던트 재발 가능성 |

### C. game-studios-analysis.md 적용 계획 이행 현황

| 우선순위 | 작업 항목 | 이행 상태 | 비고 |
|---------|----------|---------|------|
| **1순위** | `PreToolUse(Bash)` 훅 등록 | ❌ 스크립트 있음, **미등록** | `scripts/hooks/validate-dangerous-patterns.sh` 존재 |
| **1순위** | `SubagentStart` 훅 등록 | ❌ 스크립트 있음, **미등록** | `scripts/hooks/log-agent.sh` 존재 |
| **2순위** | `SessionStart` 훅 등록 | ❌ 스크립트 있음, **미등록** | `scripts/hooks/session-start.sh` 존재 |
| **2순위** | Path-scoped rules 4개 작성 | ❌ **미작성** | `core/`, `bots/`, `tests/`, `scripts/` 대상 |
| **3순위** | Anti-patterns 5개 → orchestration.yaml 추가 | ❌ **미추가** | game-studios-analysis.md §Agent 조율 Anti-patterns |
| **3순위** | Document templates 6개 작성 | ❌ **미작성** | incident-response, sprint-plan, ADR 등 |
| **-** | `detect-gaps.sh` (SessionStart) | ❌ **미작성** | 코드 있는데 문서 없으면 경고 |
| **-** | `session-stop.sh` (Stop 확장) | ❌ **미작성** | 현재는 타임스탬프만 기록 |
| **-** | Skill `allowed-tools` 추가 | ❌ **전체 0개** | 20개 스킬 전부 미설정 |
| **-** | Skill `context:` 블록 추가 | ❌ **전체 0개** | 실행 시점 셸 컨텍스트 자동 주입 |

---

## ④ 개선 포인트 우선순위표 (Impact × Effort 매트릭스)

```
                    Effort: 낮음          Effort: 높음
                   ┌─────────────────────┬─────────────────────┐
Impact: 높음       │  🟢 QUICK WIN        │  🔵 전략적 투자       │
                   │  QW-1 훅 등록 (3개) │  SI-1 Path-scoped rules│
                   │  QW-2 Anti-patterns  │  SI-2 Lead 티어 에이전트│
                   │  QW-3 allowed-tools  │  SI-3 세션 크래시 복구 │
                   ├─────────────────────┼─────────────────────┤
Impact: 낮음       │  🟡 채우면 좋음      │  ⚪ 장기과제          │
                   │  FI-1 context 블록  │  LT-1 detect-gaps.sh │
                   │  FI-2 session-stop  │  LT-2 doc templates  │
                   └─────────────────────┴─────────────────────┘
```

### 🟢 Quick Win 상세 — 즉시 실행 가능

#### QW-1: 3개 orphaned 훅 스크립트를 settings.local.json에 등록
- **파일**: `.claude/settings.local.json` → `"hooks"` 섹션
- **작업**: 아래 3개 훅 추가
  ```json
  "PreToolUse": [
    { "matcher": "Bash",
      "hooks": [{ "type": "command",
        "command": "bash /Users/rocky/telegram-ai-org/scripts/hooks/validate-dangerous-patterns.sh",
        "timeout": 10 }] }
  ],
  "SessionStart": [
    { "hooks": [{ "type": "command",
        "command": "bash /Users/rocky/telegram-ai-org/scripts/hooks/session-start.sh",
        "timeout": 15 }] }
  ],
  "SubagentStart": [
    { "hooks": [{ "type": "command",
        "command": "bash /Users/rocky/telegram-ai-org/scripts/hooks/log-agent.sh",
        "timeout": 5 }] }
  ]
  ```
- **Impact**: validate-dangerous-patterns.sh가 실제로 실행되어 위험 패턴 실시간 차단
- **Effort**: settings.local.json 편집만 필요 (스크립트는 이미 존재)
- **위험도**: 0 (기존 동작 변경 없음, 추가만)

#### QW-2: orchestration.yaml global_instructions에 Anti-patterns 5개 추가
- **파일**: `orchestration.yaml` → `global_instructions` 섹션 끝에 추가
- **내용** (game-studios-analysis.md §Agent 조율 Anti-patterns 기반):
  ```yaml
  ## 에이전트 조율 금지 패턴 (전체 조직 공통)
  1. Bypassing hierarchy: 전문가 봇이 PM을 건너뛰고 직접 결정·실행 금지
  2. Cross-domain implementation: 자신의 지정 영역(core/, bots/ 등) 외 파일 무단 수정 금지
  3. Shadow decisions: 모든 결정은 태스크 로그/산출물에 근거 명시 — 추론 없는 실행 금지
  4. Monolithic tasks: 1일 이내 완료 불가한 태스크는 반드시 분해 후 PM에 보고
  5. Assumption-based implementation: 스펙이 모호하면 추측 실행 금지, PM에게 가정 목록 확인 요청
  ```
- **Impact**: Codex·Gemini CLI 엔진에도 자동 주입 → 전체 조직 일관 적용
- **Effort**: orchestration.yaml 텍스트 추가 (5~10줄)
- **위험도**: 0 (global_instructions는 지시 추가이므로 기존 동작 파괴 없음)

#### QW-3: 핵심 스킬 3개에 allowed-tools 추가
- **대상 파일**: `skills/quality-gate/SKILL.md`, `skills/bot-triage/SKILL.md`, `skills/safe-modify/SKILL.md`
- **추가 위치**: YAML frontmatter (`---` 블록 내)
- **내용 예시**:
  ```yaml
  # quality-gate
  allowed-tools: Read, Glob, Bash, Write
  # bot-triage
  allowed-tools: Read, Bash, Glob, Grep
  # safe-modify
  allowed-tools: Read, Edit, Bash, Grep
  ```
- **Impact**: 에이전트가 스킬 실행 범위를 명확히 인지 → 의도치 않은 도구 사용 방지
- **Effort**: 각 파일 frontmatter 1줄 추가 (3개 파일)
- **위험도**: 0 (frontmatter 추가, 로직 변경 없음)

### 🔵 전략적 투자 (1주~2주)

#### SI-1: Path-scoped rules 4개 작성
- **작성 위치**: `.claude/rules/` 디렉토리 (현재 미존재)
- **대상**:
  | 파일명 | 경로 | 핵심 규칙 |
  |--------|------|---------|
  | `core-rules.md` | `core/**` | async 유지, public 시그니처 보존, secrets 금지, 100자 제한 |
  | `bots-rules.md` | `bots/**` | YAML 스키마 검증, 토큰 하드코딩 금지, engine 필드 필수 |
  | `tests-rules.md` | `tests/**` | pytest only, mock DB 허용, 외부 API 키 필요 시 skip 마킹 |
  | `scripts-rules.md` | `scripts/**` | glob 홈 탐색 절대 금지, 프로젝트 내 경로만, subprocess 외부 실행 금지 |
- **근거**: game-studios-analysis.md §Path-Scoped Rules, `~/Claude-Code-Game-Studios/.claude/rules/` 11개 원본 참조 가능

#### SI-2: 스킬 context 블록 추가 (상위 우선순위 스킬부터)
- **대상**: `skills/weekly-review/SKILL.md`, `skills/retro/SKILL.md`
- **추가 내용**:
  ```yaml
  context: |
    !git -C /Users/rocky/telegram-ai-org log --oneline -5 2>/dev/null
    !pgrep -c "bot_runner|bot_manager" 2>/dev/null | xargs echo "실행 봇 수:"
  ```
- **Impact**: 스킬 실행 시 최신 git 상태·봇 실행 현황 자동 주입 → 리뷰 품질 향상

### 🟡 채우면 좋음 (2주~1개월)

#### FI-1: session-stop.sh 확장 (Stop 훅 고도화)
- **현재**: 타임스탬프만 기록 (inline 1줄)
- **목표**: 세션 중 생성한 파일 목록 + 최종 git diff 요약 저장
- **파일**: `scripts/hooks/session-stop.sh` 신규 작성 후 settings.local.json Stop 훅 교체

#### FI-2: detect-gaps.sh 작성 (SessionStart 두 번째 훅)
- **역할**: `core/`·`bots/` 내 .py 파일이 있는데 대응 문서(.md)가 없으면 경고
- **파일**: `scripts/hooks/detect-gaps.sh` 신규 작성
- **게임 스튜디오 원본**: `~/Claude-Code-Game-Studios/.claude/hooks/detect-gaps.sh` 참조

### ⚪ 장기과제 (1개월+)

| 항목 | 내용 |
|------|------|
| Document templates 6개 | incident-response, sprint-plan, milestone-definition, post-mortem, ADR, risk-register |
| Lead 티어 에이전트 | PM 역할에 "기술 판단 위임 가능한 Tech Lead 에이전트" 지정 |
| 세션 크래시 복구 | session-state 파일 패턴 (게임 스튜디오 pre-compact.sh 벤치마킹) |
| agent-coordination-map.md | 태스크 유형별 봇 라우팅 플로우 시각화 |

---

## ⑤ 결론 및 권고사항

### 핵심 발견 3줄

> 1. **훅 스크립트 3개가 유령으로 존재** — `validate-dangerous-patterns.sh`, `session-start.sh`, `log-agent.sh`가 `scripts/hooks/`에 있으나 `settings.local.json`에 미등록되어 **지금 이 순간에도 아무 효과가 없다**. 2026-03-23 인시던트 재발 방지 스크립트가 작동하지 않는 상태.
> 2. **스킬 20개 전부 `allowed-tools` 없음** — 단일 세션 대비 가장 두드러지는 차이점. 에이전트가 스킬 실행 중 도구 범위를 추론해야 하므로 예측 불가능한 파일 수정이 발생할 수 있음.
> 3. **game-studios-analysis.md의 적용 계획 10개 항목 중 이행된 것이 0개** — 분석은 정확했으나 실행이 이어지지 않았다. 이번 태스크가 그 연속이다.

### 즉시 실행 권고 (오늘 내 완료 가능)

| 순서 | 작업 | 소요 예상 | 효과 |
|------|------|---------|------|
| 1 | settings.local.json에 PreToolUse + SessionStart + SubagentStart 훅 등록 | 10분 | 위험 패턴 차단 즉시 활성화 |
| 2 | orchestration.yaml global_instructions에 Anti-patterns 5개 추가 | 10분 | 전체 조직 에이전트 행동 표준화 |
| 3 | quality-gate, bot-triage, safe-modify 스킬에 allowed-tools 추가 | 15분 | 핵심 스킬 3개 도구 범위 명확화 |

### PM 판단 기준

단일 Claude Code 세션이 우리보다 잘하는 것은 **"상태 공유 무비용"과 "즉각 피드백 루프"**다.
이를 우리가 이길 수 있는 유일한 방법은 **이벤트 훅 + 스킬 frontmatter + global_instructions의 자동화 접착제**를 완성하는 것이다.
지금 당장 수행해야 할 Quick Win 3개(QW-1~3)는 코드 작성 없이 설정 편집만으로 완료되며, 합산 영향도는 가장 높다.

---

*분석 기준: 2026-03-23 | 참조 파일: docs/game-studios-analysis.md, .claude/settings.local.json, orchestration.yaml, CLAUDE.md, scripts/hooks/, skills/*
