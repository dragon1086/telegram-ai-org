# Gap Analysis: telegram-ai-org vs 단일 Claude Code 세션

> 분석 기준: 2026-03-23
> 참조 문서: `docs/game-studios-analysis.md`, `orchestration.yaml`, `.claude/settings.local.json`, `skills/`, `scripts/hooks/`
> 분석자: aiorg_research_bot (PM 직접 수행)

---

## Executive Summary

**결론**: telegram-ai-org는 실행 능력(코드 변경·커밋·멀티봇 위임·테스트 자동화)에서 단일 Claude Code 세션을 이미 능가한다. 그러나 **자동화 트리거(훅 등록)**, **경로별 룰 세분화**, **문서 템플릿 체계**, **스킬 컨텍스트 주입** 4개 영역에서 구체적인 격차가 존재한다.

| 영역 | 우위 | 열위 |
|------|------|------|
| 실행 능력 | ✅ 멀티봇 위임 + 자율 커밋 | — |
| 훅 시스템 | ⚠️ 스크립트는 존재 | ❌ 등록 누락 3개 |
| 컨텍스트 관리 | ✅ shared_memory + context_cache | ❌ 스킬 context 블록 없음 |
| 품질 검증 | ✅ quality-gate 스킬 완비 | ❌ validate-commit 미등록 |
| 경로별 규칙 | ❌ 전역 규칙만 존재 | ❌ path-scoped 0개 |
| 문서 템플릿 | ❌ templates 디렉토리 없음 | ❌ 0개 |
| 에이전트 조율 | ✅ orchestration.yaml 구조화 | ⚠️ anti-patterns 미주입 |
| 스킬 구조 | ✅ 20개+ 스킬 보유 | ❌ allowed-tools 미지정 |

---

## 비교 기준

1. **훅 시스템**: Claude Code settings.json에 등록된 자동화 훅 수/범위
2. **경로별 규칙(path-scoped rules)**: 디렉토리별 차등 적용 규칙 유무
3. **스킬 구조**: `allowed-tools` 명시, `context` 블록 주입 여부
4. **문서 템플릿**: 표준화된 마크다운 템플릿 유무
5. **컨텍스트 관리**: 세션 간 상태 유지, 인메모리 캐시 구조
6. **에이전트 조율**: anti-pattern 규칙 명시 여부
7. **실행·자율성**: 코드 변경 → 커밋 → 검증 자동화 수준

---

## 항목별 비교 표

| 비교 항목 | Claude-Code-Game-Studios | telegram-ai-org | 판정 |
|-----------|--------------------------|-----------------|------|
| **에이전트 수** | 48개 (도메인별) | 100+ (oh-my-claudecode 통합) | ✅ 우위 |
| **스킬 수** | 37개 | 20개+ (skills/ + .claude/skills/) | ⚠️ 열위 |
| **훅 등록 수** | 8개 (settings.json) | 2개 (ruff PostToolUse + Stop log) | ❌ 열위 |
| **훅 스크립트 구현** | 8개 | 3개 (session-start, validate-dangerous, log-agent) | ❌ 열위(미등록) |
| **Path-scoped Rules** | 11개 (경로별 차등) | 0개 (전역 4개만) | ❌ 열위 |
| **Document Templates** | 27개 | 0개 | ❌ 열위 |
| **자율 실행 모델** | User-approval 기반 | 완전 자율 실행 | ✅ 우위 |
| **멀티봇 병렬 위임** | 없음 | ✅ P2PMessenger + 6개 부서봇 | ✅ 우위 |
| **컨텍스트 캐시** | 없음 | ✅ shared_memory + context_cache | ✅ 우위 |
| **Task Graph** | 없음 | ✅ task_graph.py (111줄) | ✅ 우위 |
| **Quality Gate** | 없음 | ✅ quality-gate 스킬 완비 | ✅ 우위 |
| **자동 커밋** | 금지 (user instruction 필요) | ✅ 자율 커밋 | ✅ 우위 |
| **스킬 allowed-tools** | 명시 | 미명시 | ❌ 열위 |
| **스킬 context 블록** | 실행 시점 셸 주입 | 없음 | ❌ 열위 |
| **Coordination Map** | agent-coordination-map.md | 없음 (workers.yaml로 대체) | ⚠️ 부분 |
| **Anti-pattern 규칙** | 스킬 문서 명시 | orchestration.yaml 미주입 | ❌ 열위 |
| **세션 연속성** | session-start.sh 등록됨 | 스크립트 있지만 미등록 | ❌ 열위 |
| **SubagentStart 감사 로그** | log-agent.sh 등록 | 스크립트 있지만 미등록 | ❌ 열위 |
| **detect-gaps.sh** | 등록됨 | 없음 | ❌ 열위 |
| **validate-commit** | PreToolUse(Bash) 등록 | 스크립트 있지만 미등록 | ❌ 열위 |

---

## 뒤처지는 항목 상세 목록 (근거 포함)

### ❌ GAP-1: 훅 스크립트 3개 미등록 (최우선)

**현상**: `scripts/hooks/` 디렉토리에 구현된 스크립트 3개가 `settings.json`에 등록되지 않아 실제로 실행되지 않는다.

| 스크립트 | 의도 이벤트 | 현재 상태 |
|---------|------------|-----------|
| `scripts/hooks/session-start.sh` | SessionStart | ❌ 미등록 |
| `scripts/hooks/validate-dangerous-patterns.sh` | PreToolUse(Bash) | ❌ 미등록 |
| `scripts/hooks/log-agent.sh` | SubagentStart | ❌ 미등록 |

**근거 (파일 증거)**:
- `.claude/settings.local.json` hooks 블록: `PostToolUse(Write|Edit)` ruff 린트 + `Stop` 세션 로그만 등록됨.
- `~/.claude/settings.json` (글로벌): `SessionStart`(session-start-check.sh + context-mode), `PreToolUse`(context-mode) 등록. 프로젝트 훅 3개는 없음.
- `scripts/hooks/validate-dangerous-patterns.sh` 존재 확인됨 — 하지만 실행 경로에 연결 안 됨.

**영향**: 위험한 glob 패턴 차단이 실제로 작동하지 않는다. 서브에이전트 감사 로그가 쌓이지 않는다. 세션 시작 시 브랜치/스프린트 컨텍스트가 자동 로드되지 않는다.

---

### ❌ GAP-2: Path-Scoped Rules 전무

**현상**: `orchestration.yaml` `global_instructions`에 전역 규칙만 있고, 디렉토리별 차등 적용 규칙이 없다.

**근거**: `orchestration.yaml` 전문 확인 — `path_rules`, `scoped_rules` 같은 필드 없음. 규칙 전부가 `global_instructions` 블록 하나에 flat하게 존재.

**영향**: `core/**`의 async 보존 규칙과 `scripts/**`의 glob 금지 규칙이 분리되지 않아, 에이전트가 어느 파일을 수정할 때 어떤 제약이 적용되는지 불명확. 특히 `bots/` YAML 수정 시 스키마 검증 규칙이 없어 토큰 하드코딩 위험이 존재함.

**참조 설계안** (game-studios-analysis.md 기반):
```
core/**    → async 유지, public 시그니처 보존, secrets 금지
bots/**    → YAML 스키마 검증, 토큰 하드코딩 금지
tests/**   → pytest only, mock DB 금지
scripts/** → glob 홈 탐색 절대 금지, subprocess 외부 실행 금지
```

---

### ❌ GAP-3: 스킬 `allowed-tools` 및 `context` 블록 미지정

**현상**: `skills/` 내 모든 스킬 SKILL.md frontmatter에 `allowed-tools` 필드 없음.

**근거**: `skills/quality-gate/SKILL.md`, `skills/harness-audit/SKILL.md`, `skills/safe-modify/SKILL.md` 확인 — frontmatter에 `name`, `description`, `hooks` 만 있고 `allowed-tools` 없음.

**영향**:
1. 에이전트가 스킬 실행 시 필요한 도구를 매번 추론 → 불필요한 토큰 소비
2. 스킬 범위 이탈 가능성 (quality-gate 스킬이 Write 도구까지 쓸 수 있는지 불명확)
3. `context` 블록 없어 스킬 실행 시 최신 git log, 테스트 결과 등 자동 주입 불가

**Game-Studios 패턴**:
```yaml
---
name: quality-gate
allowed-tools: Read, Bash, Glob, Grep
context: |
  !cd /Users/rocky/telegram-ai-org && .venv/bin/pytest -q --tb=no 2>&1 | tail -3
---
```

---

### ❌ GAP-4: Document Templates 없음

**현상**: `.claude/docs/templates/` 디렉토리가 없음 (빈 `.claude/docs/` 디렉토리만 확인됨).

**근거**: `ls /Users/rocky/telegram-ai-org/.claude/docs/` → `templates` 디렉토리만 있지만 내부 파일 없음 (또는 빈 구조).

**영향**: 봇 장애 시 incident-response, post-mortem, ADR 등 표준화된 형식 없어 각 봇이 다른 포맷으로 산출물 생성. 과거 인시던트 기록 추적 어려움.

**즉시 필요한 템플릿 6개**:
- `incident-response.md` — 봇 장애/glob 사고 기록
- `post-mortem.md` — 사후 분석
- `adr.md` — 시스템 설계 결정 기록
- `sprint-plan.md` — 주간 태스크 계획
- `risk-register-entry.md` — 위험 요소 등록
- `changelog.md` — 버전별 변경 이력

---

### ❌ GAP-5: Agent Anti-Pattern 규칙 미주입

**현상**: orchestration.yaml `global_instructions`에 에이전트 조율 anti-pattern 5개가 명시되지 않음.

**근거**: `orchestration.yaml` global_instructions 블록 — PM 스코프 준수, 배포 전담, Git 워크트리, 현재시간, 위험탐색 금지 5가지만 있음. 아래 5개 anti-pattern 없음:

| Anti-Pattern | 현재 상태 |
|-------------|-----------|
| Bypassing hierarchy (전문가 봇이 PM 건너뜀) | ❌ 미명시 |
| Cross-domain implementation (지정 영역 외 수정) | ❌ 미명시 |
| Shadow decisions (추론 없이 실행) | ❌ 미명시 |
| Monolithic tasks (1-3일 이상 태스크 미분해) | ❌ 미명시 |
| Assumption-based implementation (스펙 모호 시 추측 실행) | ❌ 미명시 |

---

### ❌ GAP-6: detect-gaps.sh (코드↔문서 불일치 감지) 없음

**현상**: `scripts/hooks/` 에 `detect-gaps.sh`가 없고, SessionStart 훅에도 없음.

**영향**: 새 core 모듈이 생겨도 문서가 없음을 아무도 경고하지 않음. 90개 이상 core 파일 중 문서화된 것이 얼마나 되는지 자동 추적 불가.

---

## 우리가 단일 Claude Code 세션 대비 확실히 우위인 항목

| 강점 | 근거 |
|------|------|
| **멀티봇 병렬 위임** | P2PMessenger, 6개 부서봇 동시 실행 가능 |
| **완전 자율 실행** | 커밋·배포까지 자율 (user-approval 불필요) |
| **인메모리 컨텍스트** | `shared_memory.py(145줄)` + `context_cache.py(144줄)` |
| **Task Graph** | `task_graph.py` — 태스크 의존성 추적 |
| **Quality Gate 스킬** | ruff + pytest + import 검증 통합 자동화 |
| **Safe Modify 방법론** | 6개 방법론(CRAP, Guard Clause, Feature Flag 등) |
| **Error Gotcha 루프** | 에러 → gotchas.md 자동 추가 재발 방지 |
| **Verification Profiles** | orchestration.yaml에 require_plan/tests/status_snapshot 강제 |
| **Artifact Pipeline** | `artifact_pipeline.py` — 파일 첨부 자동 처리 |
| **Bot Triage 런북** | 장애 → 진단 → 복구 → 보고 자동화 스킬 |

---

## 개선 제언 (우선순위별)

### 🔴 1순위 — 즉시 (훅 등록, 1일 내)

**GAP-1 해소**: `.claude/settings.local.json`에 3개 훅 추가

```json
{
  "hooks": {
    "SessionStart": [...기존...,
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

---

### 🟠 2순위 — 단기 (Path-Scoped Rules + Anti-Patterns, 1주 내)

**GAP-2 해소**: `.claude/` 하위에 경로별 규칙 파일 추가 또는 orchestration.yaml에 `path_rules` 블록 도입.

**GAP-5 해소**: `orchestration.yaml` global_instructions에 anti-pattern 5개 추가.

---

### 🟡 3순위 — 중기 (스킬 구조 개선 + 템플릿, 2-3주 내)

**GAP-3 해소**: 각 SKILL.md frontmatter에 `allowed-tools` 및 `context` 블록 추가.

**GAP-4 해소**: `.claude/docs/templates/` 에 6개 표준 템플릿 작성.

**GAP-6 해소**: `scripts/hooks/detect-gaps.sh` 작성 + SessionStart 등록.

---

## 결론

단일 Claude Code 세션 대비 **실행 능력은 이미 압도적 우위**다. 단 "항상 압도적"이 되려면 **훅 등록 3개(GAP-1)**가 가장 빠른 ROI다 — 스크립트는 이미 만들어져 있고, settings.json 수정 20줄로 즉시 활성화 가능하다. 이 하나만 해도 위험 패턴 차단 + 세션 컨텍스트 자동 로드 + 에이전트 감사 로그가 즉시 살아난다.

Path-scoped rules와 스킬 allowed-tools는 우선순위 2-3위지만, 봇 수가 6개에서 늘어날수록 복잡도가 증가하므로 조기 정착이 권장된다.
