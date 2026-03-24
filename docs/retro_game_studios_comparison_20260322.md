# Claude-Code-Game-Studios vs aiorg 비교 회고 보고서

> 작성일: 2026-03-22 | 작성: aiorg_engineering_bot PM

---

## 📋 요약 (TL;DR)

**우리는 규모(에이전트 197개)와 실제 프로덕션 운영 측면에서 앞서 있지만,
"스킬 정의 품질", "hook 커버리지", "경로별 코딩 규칙" 측면에서 Game Studios에 확실히 뒤처진다.**

핵심 인사이트: SNS 글의 메시지("잘 정의된 skills만 잘 사용해도 놀라운 결과물") — 우리에게 직격이다.
우리는 skills가 20개밖에 없고, 그나마도 내부 운영 메타 스킬 위주다.
Game Studios의 skill은 37개이며, 각각 **체크리스트·출력 형식·허용 도구까지 정의된 정밀 절차서**다.

---

## 1. Claude-Code-Game-Studios 구조 개요

### 1.1 레포 기본 정보

| 항목 | 수치 |
|------|------|
| 에이전트 | **48개** (Tier 1~3 계층) |
| 스킬 (Slash Commands) | **37개** |
| Hooks | **8개** |
| Rules (경로별 코딩 기준) | **11개** |
| 문서 템플릿 | **29개** |

### 1.2 에이전트 3티어 계층 구조

```
Tier 1 — Directors (Opus 모델)
  creative-director / technical-director / producer

Tier 2 — Department Leads (Sonnet)
  game-designer / lead-programmer / art-director /
  audio-director / narrative-director / qa-lead /
  release-manager / localization-lead

Tier 3 — Specialists (Sonnet/Haiku)
  gameplay-programmer / engine-programmer / ai-programmer /
  network-programmer / tools-programmer / ui-programmer /
  systems-designer / level-designer / economy-designer /
  technical-artist / sound-designer / writer /
  world-builder / ux-designer / prototyper /
  performance-analyst / devops-engineer / analytics-engineer /
  security-engineer / qa-tester / accessibility-specialist /
  live-ops-designer / community-manager
```

**+ 엔진별 전문 에이전트**: Godot 4 (4개) / Unity (4개) / Unreal Engine 5 (4개)

각 에이전트는 YAML frontmatter로 model, maxTurns, tools, disallowedTools, memory, skills를 명시한다.
예시 (creative-director.md):
```yaml
name: creative-director
model: opus
maxTurns: 30
memory: user
tools: Read, Glob, Grep, Write, Edit, WebSearch
disallowedTools: Bash
skills: [brainstorm, design-review]
```

### 1.3 에이전트 조율 5대 규칙

1. **수직 위임**: Director → Lead → Specialist (계층 건너뜀 금지)
2. **수평 협의**: 같은 Tier끼리 협의 가능, 결정권 없음
3. **갈등 해결**: creative-director(디자인) / technical-director(기술) 에스컬레이션
4. **변경 전파**: producer가 크로스-도메인 변경 조율
5. **도메인 경계**: 지정 디렉토리 밖 수정 불가

### 1.4 협업 프로토콜: "질문 → 옵션 → 결정 → 초안 → 승인"

**AI가 자율적으로 작동하지 않는다.** 모든 에이전트는:
- 파일 쓰기 전 반드시 "May I write to [filepath]?" 질문
- 2-4개 옵션 + 장단점 제시
- 사용자가 최종 결정
- 드래프트 보여준 후 승인 요청
- 커밋은 사용자 명시적 지시 시에만

---

## 2. 스킬 파일 분석

### 2.1 37개 스킬 전체 목록

| 카테고리 | 스킬 |
|----------|------|
| 리뷰·분석 | `/design-review`, `/code-review`, `/balance-check`, `/asset-audit`, `/scope-check`, `/perf-profile`, `/tech-debt` |
| 프로덕션 | `/sprint-plan`, `/milestone-review`, `/estimate`, `/retrospective`, `/bug-report` |
| 프로젝트 관리 | `/start`, `/project-stage-detect`, `/reverse-document`, `/gate-check`, `/map-systems`, `/design-system` |
| 릴리즈 | `/release-checklist`, `/launch-checklist`, `/changelog`, `/patch-notes`, `/hotfix` |
| 크리에이티브 | `/brainstorm`, `/playtest-report`, `/prototype`, `/onboard`, `/localize` |
| 팀 오케스트레이션 | `/team-combat`, `/team-narrative`, `/team-ui`, `/team-release`, `/team-polish`, `/team-audio`, `/team-level` |
| 추가 | `/architecture-decision`, `/setup-engine` |

### 2.2 스킬 정의 패턴 (핵심 차이점)

각 스킬은 `SKILL.md` 파일 하나로 구성. frontmatter + 상세 절차 구성:

```yaml
---
name: code-review
description: "..."
argument-hint: "[path-to-file-or-directory]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash
---
```

본문에는:
- **넘버드 단계별 절차** (1~8단계)
- **체크박스 항목** ([ ] 형식)
- **출력 형식 명시** (출력 템플릿 포함)
- **허용/금지 도구 명시**

예: `/code-review`는 표준 준수, 아키텍처, SOLID, 게임 특화 이슈 체크리스트와 함께
`APPROVED / APPROVED WITH SUGGESTIONS / CHANGES REQUIRED` 3단계 verdict 형식까지 정의한다.

### 2.3 팀 오케스트레이션 스킬 구조

`/team-combat` 예시:
- Phase 1: Design → game-designer
- Phase 2: Architecture → gameplay-programmer
- Phase 3: Implementation (병렬) → gameplay-programmer + ai-programmer + technical-artist + sound-designer
- Phase 4: Integration
- Phase 5: Validation → qa-tester
- Phase 6: Sign-off

각 Phase 전환마다 `AskUserQuestion`으로 사용자 승인 필수.

---

## 3. Hooks 및 자동화 분석

### 3.1 8개 Hook 이벤트-스크립트 매핑

| Hook 이벤트 | 스크립트 | 역할 |
|------------|----------|------|
| SessionStart | `session-start.sh` | 스프린트 컨텍스트·git 활동 로드 |
| SessionStart | `detect-gaps.sh` | 미완료 문서 감지 + `/start` 제안 |
| PreToolUse(Bash) | `validate-commit.sh` | hardcode값·TODO포맷·JSON유효성·디자인doc 섹션 검증 |
| PreToolUse(Bash) | `validate-push.sh` | protected 브랜치 푸시 경고 |
| PostToolUse(Write\|Edit) | `validate-assets.sh` | assets/ 네이밍 규칙·JSON구조 검증 |
| PreCompact | `pre-compact.sh` | 컨텍스트 압축 전 세션 진행상황 보존 |
| Stop | `session-stop.sh` | 세션 종료 시 작업 내역 로그 |
| SubagentStart | `log-agent.sh` | 서브에이전트 호출 감사 추적 |

### 3.2 validate-commit.sh 주요 검증 항목

- `design/gdd/` 파일: 8개 필수 섹션(Overview, Player Fantasy, Formulas, Edge Cases...) 존재 여부
- `assets/data/*.json`: Python으로 JSON 유효성 검증 (invalid면 exit 2 → 커밋 블록)
- `src/gameplay/**`: `damage|health|speed` 등 hardcode 숫자 감지
- `src/**`: `TODO/FIXME` 없이 owner 태그 없는 것 경고

### 3.3 Permission 구조 (settings.json)

Allow: git status/diff/log/branch, ls, python json.tool, pytest
Deny: rm -rf, git push --force, git reset --hard, git clean -f, sudo, chmod 777, .env 읽기/쓰기

---

## 4. 경로별 코딩 규칙 (11 Rules)

| 경로 | 주요 강제 사항 |
|------|---------------|
| `src/gameplay/**` | 모든 값은 외부 config, delta time 필수, UI 참조 금지 |
| `src/core/**` | hot path 제로 할당, thread safety, engine↔gameplay 방향 강제 |
| `src/ai/**` | 성능 예산, data-driven 파라미터 |
| `src/networking/**` | server-authoritative, versioned messages |
| `src/ui/**` | game state 소유 금지, localization 준비, accessibility |
| `design/gdd/**` | 8개 필수 섹션, formula 형식, edge case 기술 |
| `tests/**` | 테스트 네이밍, 커버리지 요구사항, fixture 패턴 |
| `prototypes/**` | 완화된 기준이지만 README + 가설 문서화 필수 |

---

## 5. 우리 시스템(aiorg)과 비교 회고

### 5.1 수치 비교

| 항목 | Game Studios | aiorg | 평가 |
|------|-------------|-------|------|
| 에이전트 수 | 48개 | **197개** | ✅ 우리가 4배 |
| 스킬 수 | 37개 | **20개** | ⚠️ 우리가 절반 |
| Hooks | 8개 (6종 이벤트) | **2개** (PostToolUse ruff, Stop 로그) | ❌ 우리가 훨씬 부족 |
| 경로별 코딩 Rules | 11개 | **0개** | ❌ 우리 없음 |
| 에이전트 계층 | 3-tier 위계 | **flat** | ⚠️ 우리 없음 |
| 문서 템플릿 | 29개 | **없음** | ❌ |
| 실제 프로덕션 운영 | ❌ 템플릿 | **✅ 5봇 24/7** | ✅ 우리가 앞섬 |
| 자율 실행 | ❌ 승인 필수 | **✅ 자율** | 방향 차이 |

### 5.2 우리가 앞서는 점

1. **실제 프로덕션 시스템**: Game Studios는 템플릿, 우리는 실제로 5개 봇이 24/7 운영 중
2. **에이전트 수**: 197개로 거의 4배 (다양한 도메인 커버)
3. **고유 인프라**: Telegram relay, task queue, shared memory, P2P messaging, EventBus — Game Studios엔 없는 실제 시스템 레이어
4. **자율 실행**: 우리는 사람 개입 없이 자율적으로 task를 처리 (의도적 설계 차이)
5. **멀티봇 협업**: 5개 조직(engineering/design/growth/ops/product)이 실시간 협업

### 5.3 우리가 뒤처지는 점 (개선 필요)

#### ❌ 스킬 정의 품질 (가장 심각)

우리 스킬은 trigger 위주. Game Studios는 스킬 하나에:
- 허용 도구 명시
- 단계별 번호 절차
- 체크박스 체크리스트
- 출력 형식 템플릿 (버딕트 포함)

우리 `/quality-gate`, `/engineering-review` 등은 이 수준에 비하면 러프하다.

#### ❌ Hook 커버리지 빈약

우리 hooks: PostToolUse ruff lint + Stop 세션 로그 — 2개뿐.
Game Studios: SessionStart 컨텍스트 로딩, PreCompact 보존, 커밋 검증, 에이전트 감사, 갭 감지 — 8개.

특히 **없어서 아픈 것**:
- SessionStart: 세션 시작 시 현재 태스크 컨텍스트 자동 로드 (우리는 매번 수동)
- PreCompact: 컨텍스트 압축 전 진행상황 보존 (우리는 유실 위험)
- SubagentStart: 에이전트 호출 감사 추적 (누가 언제 어떤 에이전트 호출했는지)
- PreToolUse commit validation: 코드 품질 자동 게이트

#### ❌ 경로별 코딩 Rules 없음

우리는 `core/`, `scripts/`, `tests/` 등 각 경로마다 다른 기준이 있어야 하는데 통일된 규칙 파일이 없다.
특히 `core/telegram_relay.py` (hot path), `tests/**` (네이밍 규칙) 는 path-scoped rules가 있으면 큰 효과.

#### ⚠️ 에이전트 계층 없음

우리는 5개 PM봇이 flat하게 병렬 운영. escalation 경로, conflict resolution 규칙이 없다.
Game Studios의 "갈등 해결: 공통 부모로 에스컬레이션" 패턴은 도입 가치가 있다.

#### ⚠️ 스킬 수 부족 (20개)

우리는 meta/운영 스킬이 대부분. 실제 개발 워크플로우 스킬(code-review, retrospective, sprint-plan 수준의 절차화된 스킬)이 부족하다.

---

## 6. 액션 아이템 (우선순위 순)

### P1 — 즉시 개선 가능

1. **기존 스킬 20개를 Game Studios 수준으로 고도화**
   - SKILL.md에 `allowed-tools`, `argument-hint` 추가
   - 각 스킬에 단계별 체크리스트 + 출력 형식 템플릿 추가
   - 예: `/quality-gate` → 구체적 PASS/WARN/FAIL 출력 형식 + 체크박스 절차

2. **SessionStart hook 추가**
   - 세션 시작 시 현재 활성 태스크, 최근 git 활동, 미완료 TODO 자동 로드
   - Game Studios `session-start.sh` 참고

3. **PreCompact hook 추가**
   - 컨텍스트 압축 전 현재 진행 상태를 파일에 기록
   - 태스크 유실 방지

### P2 — 단기 추가

4. **경로별 코딩 Rules 도입** (`.claude/rules/`)
   - `core/**`: thread safety, 성능 크리티컬 주석 필수
   - `tests/**`: 테스트 네이밍 규칙 (test_단위_케이스명)
   - `scripts/**`: 에러 처리, exit code 규칙

5. **스킬 팀 오케스트레이션 패턴 도입**
   - `/team-release`, `/team-review` 류의 멀티에이전트 조율 스킬

6. **SubagentStart 감사 hook**
   - 어떤 PM봇이 언제 어떤 에이전트 호출했는지 로그

### P3 — 중장기

7. **에이전트 계층 및 escalation 규칙 정의**
   - product/research → 분석, engineering/ops → 실행, PM봇 → 조율 역할 명시화
   - 갈등 해결 프로토콜 문서화

8. **문서 템플릿 라이브러리** (현재 0개)
   - 태스크 브리핑, 회고, 스프린트 플랜 등 최소 10개 템플릿

---

## 7. 결론

> "잘 정의된 skills만 잘 사용해도 놀라운 결과물을 만들 수 있습니다."

이 문장은 우리에게 직접적 지적이다.
**우리는 에이전트는 많지만, 각 스킬의 정의 수준이 낮다.**

Game Studios에서 가장 배워야 할 것은 에이전트 수가 아니라,
**스킬 하나하나에 체크리스트·출력형식·허용도구까지 정의하는 정밀도**와
**hook으로 세션 전 주기를 커버하는 자동화 완결성**이다.

우리의 강점(실제 프로덕션, 자율 실행, 멀티봇 협업)은 유지하면서,
스킬 정의 품질과 hook 커버리지를 Game Studios 수준으로 끌어올리면
"멀티 에이전트 시대의 진짜 경쟁력"을 갖출 수 있다.
