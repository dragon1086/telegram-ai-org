# Improvement Plan: telegram-ai-org vs 단일 Claude Code 세션

> 작성 기준: 2026-03-23
> 참조 문서: `docs/gap-analysis-vs-single-claude.md`, `docs/game-studios-analysis.md`, `docs/retrospective-vs-game-studios-20260322.md`
> 작성자: aiorg_product_bot (PM)
> 목적: Harness 구조 관점의 개선 우선순위 + 항목별 실행 계획 + PM 반복 검증 AC

---

## Executive Summary

gap-analysis 결과 6개 핵심 격차(GAP-1~6) + 회고 기반 2개 추가 항목(GAP-7~8) 총 **8개 개선 항목**이 확인되었다.
실행 능력(코드 변경·커밋·멀티봇)은 이미 단일 Claude Code 세션을 능가하나, **자동화 트리거 부재·경로별 규칙 없음·스킬 구조 미비**가 "압도적 우위"의 걸림돌이다.

**PM 판정**: Quick Win 4개를 먼저 실행하면 즉시 체감 격차가 해소된다. 전략적 과제 1개(태스크 생애주기 스킬)는 별도 스프린트로 진행.

---

## Phase 1: 개선 항목 전체 목록 및 우선순위 매트릭스

### 1-1. 개선 항목 Raw List

| ID | 항목명 | 출처 GAP |
|----|--------|---------|
| IMP-1 | 훅 스크립트 3개 settings.json 등록 | GAP-1 |
| IMP-2 | Agent Anti-Pattern 5개 orchestration.yaml 주입 | GAP-5 |
| IMP-3 | Path-Scoped Rules 4개 작성 및 적용 | GAP-2 |
| IMP-4 | 스킬 allowed-tools + context 블록 추가 | GAP-3 |
| IMP-5 | Document Templates 6개 작성 | GAP-4 |
| IMP-6 | detect-gaps.sh 작성 + SessionStart 등록 | GAP-6 |
| IMP-7 | 태스크 생애주기 스킬 신설 (kickoff/retro/design-review) | GAP-7 |
| IMP-8 | 세션 상태 지속성 구조 도입 | GAP-8 |

---

### 1-2. 임팩트 × 구현 난이도 매트릭스

```
                  구현 난이도
                  하(Low)         중(Medium)      상(High)
              ┌───────────────┬───────────────┬───────────────┐
임팩트 상(H)  │ ★ IMP-1       │ ★ IMP-3       │ ◆ IMP-7       │
              │   훅 3개 등록  │   Path-Rules  │   생애주기스킬 │
              ├───────────────┼───────────────┼───────────────┤
임팩트 중(M)  │ ★ IMP-2       │ ▲ IMP-6       │ ● IMP-8       │
              │   Anti-Pattern │   detect-gaps │   세션 상태    │
              │ ★ IMP-4       │               │               │
              │   스킬 구조    │               │               │
              │ ★ IMP-5       │               │               │
              │   Templates   │               │               │
              └───────────────┴───────────────┴───────────────┘

★ = Quick Win   ◆ = 전략적 과제   ▲ = 보완 과제   ● = 재검토
```

---

### 1-3. 우선순위 정렬 테이블

| 순위 | ID | 항목명 | 임팩트 | 난이도 | 등급 | 예상 기간 |
|------|----|--------|--------|--------|------|----------|
| **1** | IMP-1 | 훅 스크립트 3개 등록 | 상 | 하 | 🔴 Quick Win | 즉시 (1일) |
| **2** | IMP-2 | Anti-Pattern 5개 주입 | 중 | 하 | 🔴 Quick Win | 즉시 (1일) |
| **3** | IMP-4 | 스킬 allowed-tools + context | 중 | 하 | 🔴 Quick Win | 즉시 (1일) |
| **4** | IMP-5 | Document Templates 6개 | 중 | 하 | 🔴 Quick Win | 1-2일 |
| **5** | IMP-3 | Path-Scoped Rules 4개 | 상 | 중 | 🟠 전략적 Quick Win | 1주 |
| **6** | IMP-6 | detect-gaps.sh | 중 | 중 | 🟡 보완 과제 | 1-2주 |
| **7** | IMP-7 | 태스크 생애주기 스킬 | 상 | 상 | 🔵 전략적 과제 | 2-3주 |
| **8** | IMP-8 | 세션 상태 지속성 | 중 | 상 | ⚪ 재검토 | 검토 후 결정 |

---

## Phase 2: 항목별 개선 방향 및 Harness 구조 적용

---

### IMP-1: 훅 스크립트 3개 settings.json 등록

**우선순위**: 1위 (Quick Win, 즉시)

#### What · Why · How

- **What**: `scripts/hooks/` 에 이미 구현된 3개 스크립트를 `.claude/settings.local.json` hooks 블록에 등록
- **Why**: 스크립트는 존재하나 등록이 누락돼 위험 패턴 차단·감사 로그·세션 컨텍스트 자동 로드가 전혀 작동하지 않는다
- **How**: `update-config` 스킬 또는 직접 Edit으로 아래 3개 항목 추가

#### Harness 수정 대상

| 파일/컴포넌트 | 수정 내용 |
|--------------|----------|
| `.claude/settings.local.json` | hooks 블록에 SessionStart, PreToolUse(Bash), SubagentStart 추가 |
| `scripts/hooks/session-start.sh` | 기존 파일 — 등록만 하면 됨 (수정 불필요) |
| `scripts/hooks/validate-dangerous-patterns.sh` | 기존 파일 — 등록만 하면 됨 |
| `scripts/hooks/log-agent.sh` | 기존 파일 — 등록만 하면 됨 |

#### 등록 설계 (settings.local.json 추가분)

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [{
          "type": "command",
          "command": "bash /Users/rocky/telegram-ai-org/scripts/hooks/session-start.sh",
          "timeout": 10
        }]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [{
          "type": "command",
          "command": "bash /Users/rocky/telegram-ai-org/scripts/hooks/validate-dangerous-patterns.sh",
          "timeout": 5
        }]
      }
    ],
    "SubagentStart": [
      {
        "hooks": [{
          "type": "command",
          "command": "bash /Users/rocky/telegram-ai-org/scripts/hooks/log-agent.sh",
          "async": true
        }]
      }
    ]
  }
}
```

#### Acceptance Criteria

- [ ] **AC-1-1**: 새 Claude Code 세션 시작 후 `session-start.sh` 실행 로그가 터미널에 출력되거나 로그 파일에 기록됨
- [ ] **AC-1-2**: `glob('/**')` 또는 `os.walk(Path.home())` 패턴이 포함된 Bash 명령 실행 시 훅이 exit 2 이상으로 차단하고 오류 메시지 반환
- [ ] **AC-1-3**: 서브에이전트 호출 시 `~/.ai-org-agent-audit.log` 또는 지정 로그 파일에 에이전트 이름·시각이 기록됨
- [ ] **AC-1-4**: 위 3개 훅 추가 후 `python tools/orchestration_cli.py validate-config` 실행 시 오류(ERROR) 0건

---

### IMP-2: Agent Anti-Pattern 5개 orchestration.yaml 주입

**우선순위**: 2위 (Quick Win, 즉시)

#### What · Why · How

- **What**: `orchestration.yaml` `global_instructions` 블록에 Anti-Pattern 5개 명문화
- **Why**: 에이전트가 PM을 건너뛰거나 범위 외 파일을 수정하는 월권 사고를 예방. 현재 미주입으로 인해 Cross-domain 수정·모호 스펙 추측 실행 발생 가능
- **How**: orchestration.yaml global_instructions 말미에 `## 금지 패턴 (Anti-Patterns)` 섹션 추가

#### Harness 수정 대상

| 파일/컴포넌트 | 수정 내용 |
|--------------|----------|
| `orchestration.yaml` | `global_instructions` 블록 말미에 anti-pattern 5개 섹션 추가 |
| 각 봇 system prompt (자동 주입됨) | orchestration.yaml 변경 시 자동 적용 |

#### 추가할 Anti-Pattern 텍스트 (orchestration.yaml)

```yaml
## 금지 패턴 (Anti-Patterns) — 전체 에이전트 공통 적용

1. Bypassing Hierarchy: 전문가 봇이 PM 승인 없이 직접 다른 봇에 작업 지시하거나 최종 결정을 내리는 것 금지
2. Cross-Domain Implementation: 배정된 영역(bots/, core/, scripts/ 등) 외의 파일을 무단으로 수정하는 것 금지
3. Shadow Decisions: 모든 설계 결정은 로그 또는 문서에 근거를 남길 것. 추론 없이 실행하는 것 금지
4. Monolithic Tasks: 단일 태스크로 1일 이상 소요되는 작업은 반드시 하위 태스크로 분해 후 실행
5. Assumption-Based Implementation: 스펙이 모호하거나 범위가 불명확하면 추측 실행 금지 — PM에게 확인 요청 후 착수
```

#### Acceptance Criteria

- [ ] **AC-2-1**: `orchestration.yaml` 에 anti-pattern 섹션 5개 항목이 포함되고 YAML 파싱 오류 없음
- [ ] **AC-2-2**: `python tools/orchestration_cli.py validate-config` 실행 시 PASS (오류 0건)
- [ ] **AC-2-3**: 봇 재기동 후 PM 봇에게 "지금 anti-pattern 규칙이 뭐야"라고 물었을 때 5개 항목을 정확히 응답 (수동 확인)

---

### IMP-3: Path-Scoped Rules 4개 작성 및 적용

**우선순위**: 5위 (전략적 Quick Win, 1주)

#### What · Why · How

- **What**: `.claude/rules/` 디렉토리를 생성하고 경로별 규칙 파일 4개 작성
- **Why**: 현재 전역 규칙만 존재해 `core/`의 async 보존 규칙과 `scripts/`의 glob 금지 규칙이 구분되지 않음. 에이전트가 어느 파일 수정 시 어떤 제약이 적용되는지 불명확
- **How**: Claude Code의 `.claude/rules/` 디렉토리 기반 path-scoped 규칙 적용 (Game Studios 패턴 포팅)

#### Harness 수정 대상

| 파일/컴포넌트 | 수정 내용 |
|--------------|----------|
| `.claude/rules/core-rules.md` | 신규 생성: async 유지, public 시그니처 보존, secrets 금지 |
| `.claude/rules/bots-rules.md` | 신규 생성: YAML 스키마 검증, 토큰 하드코딩 금지 |
| `.claude/rules/tests-rules.md` | 신규 생성: pytest only, mock DB 금지 |
| `.claude/rules/scripts-rules.md` | 신규 생성: glob 홈 탐색 절대 금지, subprocess 외부 실행 금지 |
| `orchestration.yaml` | path_rules 블록 또는 규칙 파일 참조 추가 (필요 시) |

#### 규칙 파일 설계 초안

**core-rules.md** (적용: `core/**`)
```markdown
# Core Module Rules

- async/await 구조를 제거하거나 동기 함수로 변경하지 말 것
- public 함수 시그니처(인자명·타입·반환값) 변경 시 반드시 테스트 업데이트
- 환경변수 키 이름은 코드에 하드코딩 금지 (settings 또는 env_loader 경유 필수)
- 줄 길이 100자 초과 금지
- ImportError silencing (try/except ImportError: pass) 패턴 금지
```

**bots-rules.md** (적용: `bots/**`)
```markdown
# Bot Configuration Rules

- YAML 파일 수정 후 스키마 검증 필수 (required fields: name, engine, system_prompt)
- 토큰/API 키 하드코딩 절대 금지 — 환경변수 참조만 허용
- engine 필드 누락 시 배포 금지
- 봇 파일 직접 삭제 시 PM 승인 필수
```

**tests-rules.md** (적용: `tests/**`)
```markdown
# Test Rules

- pytest 프레임워크만 사용 (unittest, nose 금지)
- 실 DB 연결 금지 — 인메모리 또는 fixture 기반 mock 사용
- 실 API 키가 필요한 테스트는 @pytest.mark.integration 마킹 + skip 처리
- 테스트 함수명: test_[기능]_[조건]_[기대결과] 형식 준수
```

**scripts-rules.md** (적용: `scripts/**`)
```markdown
# Scripts Rules

- glob('/**'), glob('/~'), os.walk(Path.home()), find ~, find / 패턴 절대 금지
- 프로젝트 루트(/Users/rocky/telegram-ai-org) 외부 경로 접근 금지
- subprocess 외부 시스템 명령 실행 시 이유를 주석으로 명시
- .env 파일 직접 읽기/쓰기 금지
```

#### Acceptance Criteria

- [ ] **AC-3-1**: `.claude/rules/` 하위에 4개 파일 생성 완료, 각 파일 비어있지 않음
- [ ] **AC-3-2**: `core/` 파일 수정 작업 시 에이전트가 async 보존 규칙을 언급하거나 위반 시 경고 (수동 확인 1회)
- [ ] **AC-3-3**: `scripts/` 파일 수정 시 glob 홈 탐색 패턴이 포함된 코드를 에이전트가 자동으로 거부하거나 수정 제안

---

### IMP-4: 스킬 allowed-tools + context 블록 추가

**우선순위**: 3위 (Quick Win, 즉시)

#### What · Why · How

- **What**: `skills/` 하위 핵심 스킬 SKILL.md frontmatter에 `allowed-tools` 및 `context` 블록 추가
- **Why**: 에이전트가 스킬 실행 시 필요한 도구를 매번 추론하여 불필요한 토큰 소비 + 스킬 범위 이탈 가능. context 블록 없어 실행 시점 최신 상태(테스트 결과, git log 등) 자동 주입 불가
- **How**: 각 SKILL.md frontmatter에 2개 필드 추가 (Game Studios 패턴 포팅)

#### Harness 수정 대상

| 파일/컴포넌트 | 수정 내용 |
|--------------|----------|
| `skills/quality-gate/SKILL.md` | allowed-tools + context(pytest 결과 자동 주입) 추가 |
| `skills/bot-triage/SKILL.md` | allowed-tools + context(프로세스 상태 자동 주입) 추가 |
| `skills/error-gotcha/SKILL.md` | allowed-tools 추가 |
| `skills/brainstorming-auto/SKILL.md` | allowed-tools 추가 |
| `skills/harness-audit/SKILL.md` | allowed-tools + context(설정 파일 현황 자동 주입) 추가 |
| `skills/safe-modify/SKILL.md` | allowed-tools 추가 |

#### 스킬별 allowed-tools 설계

| 스킬 | allowed-tools | context 블록 내용 |
|------|--------------|------------------|
| quality-gate | Read, Bash, Glob, Grep | `!cd /Users/rocky/telegram-ai-org && .venv/bin/pytest -q --tb=no 2>&1 \| tail -5` |
| bot-triage | Read, Bash, Glob, Grep | `!ps aux \| grep -E 'aiorg_.*bot' \| head -10` |
| error-gotcha | Read, Edit, Glob, Grep | — |
| brainstorming-auto | Read, Write, Edit, Glob, Grep | — |
| harness-audit | Read, Bash, Glob, Grep | `!cat /Users/rocky/telegram-ai-org/.claude/settings.local.json 2>/dev/null \| head -30` |
| safe-modify | Read, Edit, Bash, Glob, Grep | — |

#### Acceptance Criteria

- [ ] **AC-4-1**: `skills/quality-gate/SKILL.md` frontmatter에 `allowed-tools` 필드와 `context` 블록이 존재
- [ ] **AC-4-2**: quality-gate 스킬 호출 시 pytest 결과 3~5줄이 context로 자동 주입되어 에이전트 응답에 반영됨 (수동 확인)
- [ ] **AC-4-3**: 핵심 스킬 6개 전체에 allowed-tools 추가 완료 (Glob으로 확인)

---

### IMP-5: Document Templates 6개 작성

**우선순위**: 4위 (Quick Win, 1-2일)

#### What · Why · How

- **What**: `.claude/docs/templates/` 디렉토리에 표준화된 마크다운 템플릿 6개 작성
- **Why**: 봇 장애·스프린트 계획·설계 결정 시 각 봇이 다른 포맷으로 산출물 생성. 과거 인시던트 추적 및 설계 결정 이력 관리 불가
- **How**: Game Studios `~/.claude/docs/templates/` 참조하여 telegram-ai-org 맥락으로 재작성

#### Harness 수정 대상

| 파일/컴포넌트 | 수정 내용 |
|--------------|----------|
| `.claude/docs/templates/incident-response.md` | 봇 장애 기록 템플릿 (신규) |
| `.claude/docs/templates/post-mortem.md` | 사후 분석 템플릿 (신규) |
| `.claude/docs/templates/adr.md` | 아키텍처 결정 기록 템플릿 (신규) |
| `.claude/docs/templates/sprint-plan.md` | 주간 태스크 계획 템플릿 (신규) |
| `.claude/docs/templates/risk-register-entry.md` | 위험 요소 등록 템플릿 (신규) |
| `.claude/docs/templates/changelog.md` | 버전별 변경 이력 템플릿 (신규) |

#### 각 템플릿 필수 섹션

| 템플릿 | 필수 섹션 |
|--------|----------|
| incident-response | 발생시각, 영향 봇, 증상, 원인, 즉시 조치, 재발 방지 |
| post-mortem | 타임라인, 근본 원인, 영향 범위, 교훈, 액션 아이템 |
| adr | 상태, 맥락, 결정사항, 결과, 대안 검토 |
| sprint-plan | 기간, 목표, 태스크 목록, 완료 기준, 위험 요소 |
| risk-register-entry | 위험 ID, 설명, 영향도, 발생 가능성, 완화 전략 |
| changelog | 버전, 날짜, Added/Changed/Fixed/Removed |

#### Acceptance Criteria

- [ ] **AC-5-1**: `.claude/docs/templates/` 하위에 6개 파일 존재, 각 필수 섹션 포함
- [ ] **AC-5-2**: bot-triage 스킬 실행 후 incident-response.md 형식으로 보고서가 생성됨 (수동 확인 1회)
- [ ] **AC-5-3**: 각 템플릿 파일이 비어있지 않고 100줄 이상 내용 포함 (Bash wc -l 확인)

---

### IMP-6: detect-gaps.sh 작성 + SessionStart 등록

**우선순위**: 6위 (보완 과제, 1-2주)

#### What · Why · How

- **What**: `scripts/hooks/detect-gaps.sh` 작성 후 SessionStart 훅으로 등록
- **Why**: 새 core 모듈이 추가되어도 대응 문서가 없음을 아무도 경고하지 않음. 90개 이상 core 파일 중 문서화 비율 자동 추적 불가
- **How**: Game Studios `detect-gaps.sh` 5가지 체크를 우리 프로젝트 맥락으로 포팅

#### Harness 수정 대상

| 파일/컴포넌트 | 수정 내용 |
|--------------|----------|
| `scripts/hooks/detect-gaps.sh` | 신규 작성: 5가지 불일치 체크 스크립트 |
| `.claude/settings.local.json` | SessionStart hooks 배열에 detect-gaps.sh 추가 |

#### detect-gaps.sh 체크 항목 (5가지)

```bash
# 1. core/ 파일 중 대응 docstring 없는 파일 탐지
# 2. skills/ 중 SKILL.md 없는 디렉토리 탐지
# 3. bots/ YAML 중 system_prompt 누락 봇 탐지
# 4. scripts/hooks/ 중 settings.json 미등록 스크립트 탐지
# 5. tests/ 커버리지가 없는 core 모듈 탐지 (파일 존재 여부 기준)
```

#### Acceptance Criteria

- [ ] **AC-6-1**: `scripts/hooks/detect-gaps.sh` 파일 생성 완료, 실행 권한 부여 (`chmod +x`)
- [ ] **AC-6-2**: 세션 시작 시 detect-gaps.sh 실행 결과가 출력되며 미등록 훅 스크립트 1개 이상 감지 가능 (테스트용 더미 파일로 검증)
- [ ] **AC-6-3**: skills/ 중 SKILL.md 없는 디렉토리가 있을 경우 경고 메시지 출력 확인

---

### IMP-7: 태스크 생애주기 스킬 신설

**우선순위**: 7위 (전략적 과제, 2-3주)

#### What · Why · How

- **What**: `/task-kickoff`, `/design-review`, `/retrospective` 스킬 3개 신설
- **Why**: 현재 태스크 시작-설계-완료 전 과정에 표준화된 스킬이 없어 봇마다 다른 방식으로 진행. Game Studios의 `/start`, `/gate-check` 패턴에서 임팩트 확인
- **How**: Game Studios 스킬 패턴 참조하여 우리 orchestration 맥락으로 재설계

#### Harness 수정 대상

| 파일/컴포넌트 | 수정 내용 |
|--------------|----------|
| `skills/task-kickoff/SKILL.md` | 신규: 태스크 시작 5단계 체크리스트 (스코프·에이전트·산출물·위험·AC 확인) |
| `skills/design-review/SKILL.md` | 신규: PRD/설계서 필수 섹션 자동 검증 (What/Why/How/AC/리스크) |
| `skills/retrospective/SKILL.md` | 신규: 태스크 완료 후 회고 자동화 (교훈 추출 + MEMORY.md 업데이트) |
| `orchestration.yaml` | 각 스킬 트리거 조건 추가 |

#### 스킬별 핵심 설계

**task-kickoff**: 태스크 수신 시 → 스코프 명확화 → 담당 에이전트 배정 → 산출물·AC 정의 → PM 확인 후 착수
**design-review**: PRD 또는 설계서 제출 시 → 5개 필수 섹션 체크리스트 자동 검증 → PASS/FAIL 판정 → Fail 시 보완 요청
**retrospective**: 태스크 완료 후 → 성공/실패 요소 추출 → MEMORY.md 업데이트 → 다음 스프린트 반영 항목 정리

#### Acceptance Criteria

- [ ] **AC-7-1**: 3개 스킬 디렉토리 + SKILL.md 파일 생성 완료
- [ ] **AC-7-2**: `/task-kickoff` 실행 시 스코프·에이전트·AC 3개 항목이 반드시 포함된 응답 생성
- [ ] **AC-7-3**: `/design-review` 실행 시 What/Why/How/AC/리스크 5개 섹션 중 누락 항목을 명시적으로 지적
- [ ] **AC-7-4**: `/retrospective` 실행 시 MEMORY.md에 교훈 항목이 추가됨 (수동 확인)

---

### IMP-8: 세션 상태 지속성 구조 도입

**우선순위**: 8위 (재검토 — 복잡도 대비 ROI 검토 필요)

#### What · Why · How

- **What**: 태스크 단위 세션 상태 저장 구조 도입 (`session-state/` 디렉토리 또는 context_db 확장)
- **Why**: 현재 MEMORY.md 파일로만 태스크 간 컨텍스트가 이어져 장기 태스크에서 이전 단계 결과 참조가 수동. Game Studios의 `stage.txt + session-state/` 패턴 참고
- **How**: 기존 `shared_memory.py` + `context_cache.py` 활용 또는 경량 파일 기반 상태 저장소 설계

#### PM 판정

> **재검토 사유**: `shared_memory.py(145줄)` + `context_cache.py(144줄)` + `task_graph.py`가 이미 존재하여 부분적으로 해소됨.
> 완전 구현 전 IMP-7까지 완료 후 실제 필요성 재평가 권장.

#### Harness 수정 대상 (잠정)

| 파일/컴포넌트 | 수정 내용 (검토용) |
|--------------|----------|
| `core/shared_memory.py` | 태스크별 상태 슬롯 추가 (재검토) |
| `session-state/` 디렉토리 | 신규: 태스크 진행 상태 파일 저장 (재검토) |

#### Acceptance Criteria (재검토 시 적용)

- [ ] **AC-8-1**: 동일 태스크의 Phase 1 결과가 Phase 2 시작 시 자동 로드됨
- [ ] **AC-8-2**: 봇 재기동 후에도 진행 중인 태스크 상태 복원 성공
- [ ] **AC-8-3**: 상태 파일 크기 제한 1MB 이하 준수 (비대화 방지)

---

## PM 반복 검증 루프 (Harness Loop)

```
[태스크 수신]
     ↓
[IMP-1,2,4 Quick Wins 실행] ← 즉시 시작
     ↓
[AC 체크: validate-config + 수동 확인]
     ↓
[PASS?] → YES → [IMP-5 Templates 실행]
          → NO  → [원인 파악 + 수정] → 재검증
     ↓
[IMP-3 Path-Rules 실행]
     ↓
[AC 체크: 에이전트 응답 확인]
     ↓
[IMP-6 detect-gaps.sh 실행]
     ↓
[IMP-7 생애주기 스킬 스프린트]
     ↓
[전체 quality-gate 실행]
     ↓
[PM 최종 승인: 8개 AC 중 6개 이상 PASS → 완료]
```

---

## 전체 우선순위 실행 로드맵

| 기간 | 항목 | 담당 팀 | 핵심 산출물 |
|------|------|---------|-----------|
| **즉시 (1일)** | IMP-1, IMP-2, IMP-4 | @aiorg_engineering_bot | settings.json 수정, orchestration.yaml 수정, SKILL.md 수정 |
| **단기 (2-3일)** | IMP-5 | @aiorg_engineering_bot | 6개 템플릿 파일 생성 |
| **1주** | IMP-3 | @aiorg_engineering_bot | 4개 rules 파일 생성 |
| **1-2주** | IMP-6 | @aiorg_engineering_bot | detect-gaps.sh 구현 |
| **2-3주** | IMP-7 | @aiorg_engineering_bot + @aiorg_design_bot | 3개 스킬 신설 |
| **재검토** | IMP-8 | IMP-7 완료 후 재평가 | — |

---

## PM 완료 기준 (Overall Acceptance)

> 아래 기준 6/8 이상 충족 시 "압도적 우위" 달성으로 판정

| 항목 | 측정 방법 | 기준 |
|------|---------|------|
| 훅 등록 3개 | settings.json 확인 + 세션 시작 로그 | 3개 전부 등록, 오류 0 |
| Anti-pattern 주입 | orchestration.yaml grep | 5개 항목 전부 포함 |
| Path-rules | `.claude/rules/` 파일 수 | 4개 파일 존재 |
| 스킬 allowed-tools | SKILL.md frontmatter grep | 6개 핵심 스킬 전부 포함 |
| Templates | `.claude/docs/templates/` 파일 수 | 6개 파일 존재 |
| detect-gaps.sh | scripts/hooks/ 파일 존재 + 실행 테스트 | 오류 없이 실행, 체크 5개 동작 |
| quality-gate PASS | 전체 pytest 결과 | 오류 로그 0건 |
| validate-config | orchestration_cli 실행 | PASS 판정 |

---

*이 문서는 PM 하네스 루프의 기준 문서다. 각 IMP 항목 완료 후 해당 AC를 체크하고 다음 항목으로 이동한다.*
*최종 승인자: aiorg_product_bot (PM)*
