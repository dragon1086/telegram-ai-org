---
name: create-skill
description: "Create a new Claude Code skill following official best practices. Use when building new skills for this project's bots. Triggers: '스킬 만들기', 'create skill', 'new skill', '새 스킬'"
disable-model-invocation: true
---

# Skill Factory (스킬 제작 가이드)

$ARGUMENTS 를 기반으로 새 스킬을 제작하라.

## Step 1: 요구사항 정리

아래 항목을 먼저 정리하라 (모르는 건 합리적으로 추론):

- **스킬 이름**: kebab-case (예: `api-resilience`)
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

1. **description은 구체적으로** — Claude가 자동 매칭할 수 있게 상세히
2. **Triggers 포함** — 한국어/영어 트리거 키워드 명시
3. **$ARGUMENTS 활용** — 동적 입력이 필요하면 `$ARGUMENTS` 사용
4. **단계별 구조** — Step 1, Step 2... 로 명확한 실행 순서
5. **완료 조건 명시** — 스킬이 "끝났다"고 판단할 기준

### 금지 사항

- 2000줄 이상 스킬 금지 — 길면 supporting 파일로 분리
- 모호한 description 금지 — "유용한 스킬" (X) → "API 호출 시 retry + backoff 패턴 적용 가이드" (O)
- 인터랙티브 질문 남발 금지 — autonomous mode 봇은 응답 못함. 합리적 기본값 사용

### 품질 체크리스트

- [ ] description만 읽고도 언제 쓰는 스킬인지 알 수 있는가?
- [ ] 봇이 autonomous mode에서도 실행 가능한가?
- [ ] 단계가 5개 이하로 간결한가? (넘으면 분할 고려)
- [ ] 기존 스킬과 중복되지 않는가?

## Step 4: 파일 생성

1. `skills/{name}/SKILL.md` 생성
2. `.claude/skills/{name}` 심볼릭 링크 생성:
   ```bash
   ln -sf ../../skills/{name}/ .claude/skills/{name}
   ```
3. 필요 시 supporting 파일 추가 (`skills/{name}/reference.md` 등)

## Step 5: 검증

생성 후 반드시 확인:
1. SKILL.md frontmatter YAML이 유효한가
2. 심볼릭 링크가 올바른가 (`ls -la .claude/skills/{name}`)
3. description에 Triggers가 포함되어 있는가

## 참고: 기존 스킬 목록

새 스킬 작성 전 기존 스킬과 중복 확인:
```
skills/retro/              — 스프린트 회고
skills/brainstorming-auto/ — 자동 브레인스토밍
skills/quality-gate/       — 품질 게이트
skills/harness-audit/      — 하네스 감사
skills/design-critique/    — 디자인 비평
skills/pm-task-dispatch/   — PM 태스크 배분
skills/pm-discussion/      — PM 논의
skills/engineering-review/  — 엔지니어링 리뷰
skills/loop-checkpoint/    — 루프 체크포인트
skills/performance-eval/   — 성과 평가
skills/autonomous-skill-proxy/ — 자율 스킬 프록시
skills/growth-analysis/    — 성장 분석
skills/weekly-review/      — 주간 리뷰
skills/create-skill/       — 스킬 제작 (이 스킬)
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
