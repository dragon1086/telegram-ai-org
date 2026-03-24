# Claude-Code-Game-Studios 분석 및 적용 계획

> 분석 기준: 2026-03-23
> 참조 저장소: `~/Claude-Code-Game-Studios` (clone됨)
> 원본: https://github.com/Donchitos/Claude-Code-Game-Studios

---

## 개요

Claude-Code-Game-Studios는 48개 에이전트, 37개 스킬, 8개 훅, 11개 path-scoped 규칙, 29개 문서 템플릿으로 구성된 Claude Code 기반 게임 스튜디오 오케스트레이션 템플릿이다. 우리 프로젝트(telegram-ai-org)와 구조적으로 유사하지만, 훅 시스템·path-scoped 규칙·문서 템플릿 면에서 상당히 앞서 있다.

---

## 수치 비교

| 항목 | Claude-Code-Game-Studios | telegram-ai-org |
|------|--------------------------|-----------------|
| Agents | 48개 (도메인별) | 100+ (oh-my-claudecode 통합) |
| Skills | 37개 | 4개 local + 프로젝트 스킬 |
| Hooks | **8개** (Claude Code settings.json 등록) | pre-compact 1개 |
| Rules | **11개 (path-scoped)** | 전역 4개 |
| Document Templates | **27개** | 없음 |
| Coordination Map | 명시적 문서 (agent-coordination-map.md) | workers.yaml + organizations.yaml |
| 자율성 모델 | User-approval 기반 (쓰기 전 승인 필수) | 완전 자율 실행 |

---

## Hooks 상세 — 가장 큰 격차

저쪽은 `settings.json`에 Claude Code hook 이벤트로 직접 등록:

```json
{
  "SessionStart":   ["session-start.sh", "detect-gaps.sh"],
  "PreToolUse":     ["validate-commit.sh", "validate-push.sh"],   // matcher: "Bash"
  "PostToolUse":    ["validate-assets.sh"],                        // matcher: "Write|Edit"
  "PreCompact":     ["pre-compact.sh"],
  "Stop":           ["session-stop.sh"],
  "SubagentStart":  ["log-agent.sh"]
}
```

### 각 훅 역할

| 훅 파일 | 이벤트 | 역할 | 우리 현황 |
|---------|--------|------|-----------|
| `session-start.sh` | SessionStart | 현재 브랜치, 스프린트, 마일스톤, 버그 카운트, 최근 git 활동 로드 | 없음 |
| `detect-gaps.sh` | SessionStart | 코드 있는데 문서 없으면 경고 (5가지 체크) | 없음 |
| `validate-commit.sh` | PreToolUse(Bash) | 하드코딩 값, glob 위험 패턴, .env 노출 차단 | **없음 — 어제 인시던트와 직결** |
| `validate-push.sh` | PreToolUse(Bash) | protected branch 푸시 경고 | 없음 |
| `validate-assets.sh` | PostToolUse(Write\|Edit) | 파일 네이밍 컨벤션, JSON 유효성 | 없음 |
| `pre-compact.sh` | PreCompact | 세션 상태 보존 | oh-my-claudecode로 일부 처리 |
| `session-stop.sh` | Stop | 세션 종료 시 작업 로그 | 없음 |
| `log-agent.sh` | SubagentStart | 모든 서브에이전트 호출 감사 로그 | 없음 |

### validate-commit.sh 차단 패턴 (우리가 즉시 포팅해야 할 것)

- 하드코딩된 상수값 (gameplay 코드 내)
- `glob('/**')`, `os.walk(Path.home())` 등 위험 탐색 패턴
- `.env` 파일 노출
- TODO/FIXME에 담당자 미지정
- JSON 파일 유효성

---

## Path-Scoped Rules — 우리는 전역 규칙만 있음

저쪽은 파일 경로별로 다른 규칙 적용:

| 경로 | 규칙 파일 |
|------|-----------|
| `src/ai/**` | AI Code Rules (2ms 예산, 데이터 파일 튜닝 가능, 디버그 시각화 필수) |
| `src/gameplay/**` | Gameplay Code Rules |
| `src/engine/**` | Engine Code Rules |
| `src/network/**` | Network Code Rules |
| `src/ui/**` | UI Code Rules |
| `design/**` | Design Document Rules |
| `design/narrative/**` | Narrative Rules |
| `assets/data/**` | Data File Rules |
| `assets/shaders/**` | Shader Code Standards |
| `tests/**` | Test Standards |
| `prototypes/**` | Prototype Code Standards (Relaxed) |

### 우리 프로젝트에 적용할 path-scoped rules (초안)

| 경로 | 적용할 규칙 |
|------|------------|
| `core/**` | async 유지, public 시그니처 보존, secrets 금지, 줄 길이 100자 |
| `bots/**` | YAML 스키마 검증, 토큰 하드코딩 금지, engine 필드 필수 |
| `tests/**` | pytest only, mock DB 금지, 실 API 키 필요 시 skip 마킹 |
| `scripts/**` | glob 홈 탐색 절대 금지, 프로젝트 내 경로만, subprocess 외부 실행 금지 |

---

## Agent 조율 Anti-patterns (저쪽 문서 → 우리에게도 적용)

저쪽 `.claude/skills/` 내 coordination 문서에서 명시한 5가지:

1. **Bypassing hierarchy** — 전문가 봇이 PM 건너뛰고 직접 결정 금지
2. **Cross-domain implementation** — 지정 영역 외 파일 무단 수정 금지
3. **Shadow decisions** — 모든 결정은 로그/문서화 (봇이 추론 없이 실행하면 안 됨)
4. **Monolithic tasks** — 1-3일 이내 완료 불가한 태스크는 반드시 분해 먼저
5. **Assumption-based implementation** — 스펙 모호하면 추측 실행 금지, PM에게 확인

이 5가지를 `orchestration.yaml` global_instructions에 추가하면 Codex·Gemini CLI에도 자동 적용됨.

---

## Skill 구조 패턴 — 우리 스킬에 도입할 것

### allowed-tools 명시

저쪽 skill frontmatter:
```yaml
---
name: sprint-plan
description: "..."
user-invocable: true
allowed-tools: Read, Glob, Grep, Write, Edit
---
```

우리 스킬은 `allowed-tools`가 없어 에이전트가 매번 추론. 추가하면 실행 범위 명확.

### context 블록 — 실행 시점 셸 결과 자동 주입

```yaml
context: |
  !git log --oneline --since="2 weeks ago" 2>/dev/null
```

세션 시작 시 관련 컨텍스트를 자동으로 가져옴. 우리 스킬에도 도입 가능.

---

## Document Templates — 우리에게 바로 쓸 수 있는 것

저쪽 `/.claude/docs/templates/` 27개 중 우리 프로젝트 적용 가능한 것:

| 저쪽 템플릿 | 우리 용도 |
|------------|-----------|
| `incident-response.md` | 봇 장애/인시던트 리포트 (glob 사고 등) |
| `sprint-plan.md` | 주간 태스크 계획 |
| `milestone-definition.md` | 분기/월 목표 정의 |
| `post-mortem.md` | 봇 장애 사후 분석 |
| `architecture-decision-record.md` | 시스템 설계 결정 기록 (ADR) |
| `risk-register-entry.md` | 위험 요소 등록 |
| `changelog-template.md` | 버전별 변경 이력 |

참조 경로: `~/Claude-Code-Game-Studios/.claude/docs/templates/`

---

## 배우지 말아야 할 것

| 항목 | 이유 |
|------|------|
| User-approval 프로토콜 ("May I write this?") | 우리는 완전 자율 실행 모델 — 승인 대기는 흐름 파괴 |
| No commits without user instruction | 우리 봇은 커밋까지 자율 수행이 설계 목표 |
| 게임 도메인 전용 스킬/에이전트 | 도메인 불일치 |

---

## 우선순위별 적용 계획

### 1순위 — 즉시 (보안/안전)

**작업**: `.claude/settings.json`에 훅 추가 + 스크립트 작성

- `PreToolUse(Bash)` hook → `scripts/hooks/validate-dangerous-patterns.sh`
  - `glob('/**')`, `os.walk(Path.home())`, `find ~`, `find /` 패턴 차단 (exit 2)
  - `.env` 파일 직접 쓰기 차단
- `SubagentStart` hook → `scripts/hooks/log-agent.sh`
  - 에이전트 이름, 시각, 호출 맥락 로그 (`~/.ai-org-agent-audit.log`)

### 2순위 — 단기 (1주)

- `SessionStart` hook → `scripts/hooks/session-start.sh`
  - 현재 실행 중인 봇 태스크 상태 + 최근 커밋 로드
- Path-scoped rules 4개 작성 (`core/`, `bots/`, `tests/`, `scripts/`)

### 3순위 — 중기 (2-3주)

- Document templates 6개 작성 (incident-response, sprint-plan, ADR, post-mortem 우선)
- Anti-patterns 5개를 `orchestration.yaml` global_instructions에 추가
- `docs/agent-coordination-map.md` 작성 — 태스크 유형별 봇 라우팅 플로우

---

## 실행 시 참고 경로

```
~/Claude-Code-Game-Studios/.claude/hooks/          # 8개 훅 스크립트 원본
~/Claude-Code-Game-Studios/.claude/rules/          # 11개 path-scoped 규칙 원본
~/Claude-Code-Game-Studios/.claude/skills/         # 37개 스킬 원본
~/Claude-Code-Game-Studios/.claude/docs/templates/ # 27개 문서 템플릿 원본
~/Claude-Code-Game-Studios/.claude/settings.json   # hook 등록 패턴 원본
```

이 파일들을 참조해서 우리 프로젝트에 포팅할 것. 게임 도메인 특화 내용은 제거하고 봇 오케스트레이션 맥락으로 변환.
