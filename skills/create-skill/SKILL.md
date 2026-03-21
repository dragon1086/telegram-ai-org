---
name: create-skill
description: "Create a new Claude Code skill following official best practices. Use when building new skills for this project's bots. Triggers: '스킬 만들기', 'create skill', 'new skill', '새 스킬'"
disable-model-invocation: true
---

# Skill Factory (스킬 제작 가이드)

> 출처: [Lessons from Building Claude Code: How We Use Skills](https://x.com/trq212/status/2033949937936085378) + 프로젝트 실전 경험

$ARGUMENTS 를 기반으로 새 스킬을 제작하라.

## Step 0: 스킬 카테고리 선택

새 스킬을 만들기 전에 어떤 카테고리에 해당하는지 먼저 파악하라. 좋은 스킬은 하나의 카테고리에 깔끔히 들어간다:

**1. Process Enforcement** — 프로세스 강제
- 팀이 따라야 할 절차를 코드화. 사람이 잊어도 스킬이 강제
- 예: `engineering-review`, `quality-gate`

**2. Domain Knowledge Bases** — 도메인 지식
- Claude가 기본적으로 모르는 조직 고유 지식을 주입
- Claude는 코드베이스와 코딩을 잘 알지만 **기본 의견을 깨는 정보**에 집중할 것
- 예: `frontend-design` (Inter 폰트와 보라색 그라디언트 같은 클리셰 회피)

**3. Workflow Automation** — 워크플로 자동화
- 반복 작업을 한 명령으로. 다른 스킬/MCP에 의존할 수 있음
- 이전 실행 결과를 로그 파일로 저장하면 일관성 유지에 도움
- 예: `standup-post`, `weekly-review`, `create-ticket`

**4. Business Process & Team Automation** — 비즈니스 프로세스
- 팀 협업 절차를 자동화
- 예: `pm-task-dispatch`, `pm-discussion`

**5. Code Scaffolding & Templates** — 코드 스캐폴딩
- 프레임워크 보일러플레이트 생성. 스크립트와 조합 가능
- 자연어 요구사항이 순수 코드로 커버 안 될 때 유용
- 예: `new-migration`, `create-app`

**6. Code Quality & Review** — 코드 품질
- 조직의 코드 품질 기준 강제. 결정론적 스크립트/도구와 결합하면 최대 견고성
- hooks나 GitHub Action으로 자동 실행 가능
- 예: `engineering-review`, `quality-gate`

**7. CI/CD & Deployment** — 배포
- 빌드 → 테스트 → 점진적 롤아웃 → 자동 롤백
- 예: `deploy-<service>`, `babysit-pr`, `cherry-pick-prod`

**8. Runbooks** — 런북
- 증상(Slack 스레드, 알럿, 에러 시그니처)을 받아 다중 도구 조사 후 구조화된 보고서 생성
- 예: `<service>-debugging`, `triage-alert`

**9. Infrastructure Operations** — 인프라 운영
- 루틴 유지보수와 운영 절차. 파괴적 작업에 가드레일 제공
- 예: `restart_bots`, `auto-rollback`

## Step 1: 요구사항 정리

아래 항목을 먼저 정리하라 (모르는 건 합리적으로 추론):

- **스킬 이름**: kebab-case (예: `api-resilience`)
- **카테고리**: Step 0의 9개 카테고리 중 택 1
- **목적**: 이 스킬이 해결하는 문제 한 줄
- **유형**: reference(가이드/컨벤션) | task(단계별 작업) | hybrid(둘 다)
- **호출 방식**: 자동(description 매칭) | 수동(`/skill-name`) | 둘 다
- **실행 컨텍스트**: inline(현재 대화) | fork(서브에이전트)

## Step 2: 스킬 구조 결정

### 유형별 템플릿

**Reference 스킬** (가이드, 컨벤션):
```yaml
---
name: {name}
description: "{한 줄 설명}. Triggers: '{트리거1}', '{트리거2}'"
---
```
- 현재 대화에서 inline으로 로드됨
- 규칙/패턴/스타일 가이드에 적합
- `disable-model-invocation: true` 불필요 (자동 감지 유용)

**Task 스킬** (단계별 작업):
```yaml
---
name: {name}
description: "{한 줄 설명}. Triggers: '{트리거1}', '{트리거2}'"
disable-model-invocation: true
---
```
- 명시적 `/skill-name`으로만 호출
- 배포, 리뷰, 생성 작업에 적합

**Fork 스킬** (독립 에이전트 실행):
```yaml
---
name: {name}
description: "{한 줄 설명}"
context: fork
agent: {Explore|Plan|general-purpose}
---
```
- 별도 컨텍스트에서 실행, 메인 대화 오염 없음
- 리서치, 분석, 탐색에 적합

## Step 3: SKILL.md 작성 원칙

### 필수 규칙

1. **description은 트리거 조건으로 작성** — Claude는 세션 시작 시 모든 스킬의 description 목록을 스캔하여 "이 요청에 맞는 스킬이 있는가?" 판단함. description은 요약이 아니라 **언제 이 스킬을 발동할지**를 설명하는 것
2. **Triggers 포함** — 한국어/영어 트리거 키워드 명시
3. **$ARGUMENTS 활용** — 동적 입력이 필요하면 `$ARGUMENTS` 사용
4. **단계별 구조** — Step 1, Step 2... 로 명확한 실행 순서
5. **완료 조건 명시** — 스킬이 "끝났다"고 판단할 기준
6. **gotcha로 점진 개선** — "대부분의 스킬은 몇 줄과 gotcha 하나로 시작해서, Claude가 새 엣지 케이스를 만날 때마다 추가되며 좋아진다" (Anthropic)

### Best Practices (Anthropic 공식)

- **결정론적 스크립트 결합** — 코드 품질 스킬은 ruff/pytest 같은 도구와 결합하면 최대 견고성
- **이전 실행 로그 저장** — 워크플로 자동화 스킬은 이전 결과를 로그 파일로 저장하면 일관성 유지
- **Claude의 기본 의견을 깨는 정보에 집중** — 지식 스킬은 Claude가 이미 아는 것 말고, 조직 고유의 관점/규칙을 넣어야 의미 있음
- **hooks와 결합** — 스킬 호출 시에만 활성화되는 On Demand Hooks로 평소엔 안 쓰지만 특정 상황에 극도로 유용한 훅 부착 가능

### On Demand Hooks

스킬에 hooks를 포함하면 해당 스킬 호출 시에만 활성화되고, 세션 동안 유지된다:

```yaml
---
name: {name}
description: "..."
hooks:
  PreToolUse:
    - matcher: "Write"
      hook: "echo 'Write 호출 전 검증'"
  PostToolUse:
    - matcher: "Bash"
      hook: "echo 'Bash 실행 후 검증'"
---
```

예: 배포 스킬에서 Write 전 자동 린트, 테스트 스킬에서 Bash 후 커버리지 체크

### 금지 사항

- 2000줄 이상 스킬 금지 — 길면 supporting 파일로 분리
- 모호한 description 금지 — "유용한 스킬" (X) → "API 호출 시 retry + backoff 패턴 적용 가이드" (O)
- 인터랙티브 질문 남발 금지 — autonomous mode 봇은 응답 못함. 합리적 기본값 사용

### 품질 체크리스트

- [ ] description만 읽고도 언제 트리거되는 스킬인지 알 수 있는가?
- [ ] 봇이 autonomous mode에서도 실행 가능한가?
- [ ] 단계가 5개 이하로 간결한가? (넘으면 분할 고려)
- [ ] 기존 스킬과 중복되지 않는가?
- [ ] 해당 카테고리(Step 0)에 깔끔히 들어가는가? (여러 카테고리에 걸치면 분할 고려)

## Step 4: 파일 생성

1. `skills/{name}/SKILL.md` 생성 (필수)
2. `.claude/skills/{name}` 심볼릭 링크 생성:
   ```bash
   ln -sf ../../skills/{name}/ .claude/skills/{name}
   ```
3. Supporting 파일 추가 (아래 가이드 참조)

### Supporting 파일 구조

스킬은 SKILL.md 하나만으로도 작동하지만, 복잡한 스킬은 아래 파일을 조합한다:

```
skills/{name}/
├── SKILL.md              # 필수 — 스킬 본체 (frontmatter + 실행 절차)
├── gotchas.md            # 권장 — 이 스킬 사용 시 자주 발생하는 실수와 해결책
├── references/           # 선택 — 참조 문서 (라우팅 테이블, API 스펙 등)
│   └── bot-routing.md
├── templates/            # 선택 — 출력 템플릿 (보고서, 회고 등)
│   └── report-template.md
└── scripts/              # 선택 — 스킬 전용 CLI/자동화 스크립트
    └── validate.sh
```

**gotchas.md 작성 규칙:**
- 제목: `# {스킬 이름} — Gotchas`
- 각 항목: `## Gotcha N: {제목}` + **상황/증상/해결** 3단 구성
- 실제 인시던트 기반으로 작성 (가상 시나리오 금지)
- 에러 수정 후 `error-gotcha` 스킬로 자동 추가 가능

**references/ 작성 규칙:**
- SKILL.md가 2000줄을 넘길 때 분리
- 자주 변경되는 데이터(라우팅, 설정값)는 별도 파일로

**scripts/ 작성 규칙:**
- 스킬이 자동 실행하는 검증/생성 스크립트
- 반드시 `set -euo pipefail` (bash) 또는 적절한 에러 핸들링
- 프로젝트 venv 사용: `.venv/bin/python` 경로 명시

## Step 5: 스킬 등록 (organizations.yaml)

봇이 스킬의 존재를 인지하려면 `organizations.yaml`에 등록해야 한다. 등록하지 않으면 봇 시스템 프롬프트에 스킬이 주입되지 않는다.

**등록 유형 판단:**
- **모든 봇이 필요** (품질, 에러 처리, 운영 등) → `common_skills`에 추가
- **특정 역할만 필요** (디자인, 엔지니어링 등) → 해당 봇의 `preferred_skills`에 추가
- **둘 다 아님** (수동 호출 전용) → 등록 불필요

**common_skills 추가** (파일 최상위):
```yaml
common_skills:
- quality-gate
- error-gotcha
- bot-triage
- {new-skill-name}  # ← 여기에 추가
```

**preferred_skills 추가** (봇별):
```yaml
organizations:
- id: aiorg_engineering_bot
  team:
    preferred_skills:
    - engineering-review
    - {new-skill-name}  # ← 해당 봇에 추가
```

**역할→스킬 매핑 참고:**
- PM/오케스트레이터: pm-task-dispatch, pm-discussion, weekly-review, retro, performance-eval
- 엔지니어링: engineering-review, quality-gate
- 디자인: design-critique, brainstorming-auto
- 그로스/리서치: growth-analysis
- 운영: harness-audit, bot-triage
- 프로덕트: brainstorming-auto

또한 `core/setup_registration.py`의 `team_profiles`에도 해당 역할의 `preferred_skills` 기본값을 업데이트하라 (신규 조직 생성 시 자동 적용).

## Step 6: 검증

생성 후 반드시 확인:
1. SKILL.md frontmatter YAML이 유효한가
2. 심볼릭 링크가 올바른가 (`ls -la .claude/skills/{name}`)
3. description에 Triggers가 포함되어 있는가
4. organizations.yaml에 등록했는가 (common_skills 또는 해당 봇 preferred_skills)

## Step 7: 배포 (Distributing)

스킬의 가장 큰 장점은 팀과 공유할 수 있다는 것이다:

1. **프로젝트 내 배포**: `skills/` 디렉토리 + `.claude/skills/` 심볼릭 링크 → git push만으로 팀 전체 적용
2. **CLAUDE.md에서 참조**: 프로젝트 CLAUDE.md에 스킬 사용 가이드 추가
3. **점진적 개선**: gotchas.md에 엣지 케이스 축적 → `error-gotcha` 스킬로 자동 추가 → `skill-evolve`로 주기적 패턴 분석

## 참고: 기존 스킬 목록

새 스킬 작성 전 기존 스킬과 중복 확인:
```
skills/retro/              — 스프린트 회고 (Workflow Automation)
skills/brainstorming-auto/ — 자동 브레인스토밍 (Business Process)
skills/quality-gate/       — 품질 게이트 (Code Quality)
skills/harness-audit/      — 하네스 감사 (Code Quality)
skills/design-critique/    — 디자인 비평 (Code Quality)
skills/pm-task-dispatch/   — PM 태스크 배분 (Business Process)
skills/pm-discussion/      — PM 논의 (Business Process)
skills/engineering-review/ — 엔지니어링 리뷰 (Code Quality)
skills/loop-checkpoint/    — 루프 체크포인트 (Infrastructure Ops)
skills/performance-eval/   — 성과 평가 (Workflow Automation)
skills/autonomous-skill-proxy/ — 자율 스킬 프록시 (Process Enforcement)
skills/growth-analysis/    — 성장 분석 (Domain Knowledge)
skills/weekly-review/      — 주간 리뷰 (Workflow Automation)
skills/error-gotcha/       — 에러 → gotcha 자동 추가 (Process Enforcement)
skills/skill-evolve/       — 교훈 기반 스킬 개선 (Process Enforcement)
skills/bot-triage/         — 봇 장애 진단/복구 런북 (Runbook)
skills/create-skill/       — 스킬 제작 가이드 (이 스킬)
```

## 참고: frontmatter 필드 전체 목록

| 필드 | 필수 | 설명 |
|------|------|------|
| name | O | 슬래시 커맨드 이름 (kebab-case) |
| description | O | Claude 자동 매칭용 설명 |
| disable-model-invocation | - | true면 수동 호출만 가능 |
| context | - | `fork`면 서브에이전트에서 실행 |
| agent | - | fork 시 에이전트 유형 (Explore, Plan 등) |
| allowed-tools | - | 사용 가능 도구 제한 |
| hooks | - | 스킬 라이프사이클 훅 |

## 참고: $ARGUMENTS 치환 변수

| 변수 | 설명 |
|------|------|
| `$ARGUMENTS` | 호출 시 전달된 전체 인자 |
| `$ARGUMENTS[N]` | N번째 인자 (0-based) |
| `$0`, `$1` | `$ARGUMENTS[0]`, `$ARGUMENTS[1]` 축약형 |
| `${CLAUDE_SESSION_ID}` | 현재 세션 ID |
| `${CLAUDE_SKILL_DIR}` | 스킬 디렉토리 경로 |
