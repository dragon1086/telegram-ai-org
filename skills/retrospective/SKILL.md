---
name: retrospective
description: "Use after completing a task or sprint to extract lessons learned and update MEMORY.md. Triggers: '회고', 'retrospective', 'retro', 'lessons learned', '태스크 완료 후 회고', after any task marked complete, after sprint end"
allowed-tools: Read, Edit, Glob, Grep, Bash
context: |
  !git -C /Users/rocky/telegram-ai-org log --oneline -10 2>/dev/null
  !cat /Users/rocky/telegram-ai-org/memory/MEMORY.md 2>/dev/null | tail -30
---

# Retrospective (태스크 완료 후 회고)

태스크 완료 직후 교훈을 추출하고 MEMORY.md에 자동 업데이트한다.
Game Studios 회고 자동화 패턴 포팅. retro 스킬의 MEMORY 업데이트 특화 버전.

## 언제 사용하나

- 태스크(T-XXXX) 완료 후
- 스프린트 종료 후
- 버그 수정 완료 후 (error-gotcha와 병행)
- 인시던트 복구 후 (post-mortem과 병행)

## 실행 절차

### Step 1: 완료 태스크 컨텍스트 수집

```bash
# 최근 커밋 확인
git -C /Users/rocky/telegram-ai-org log --oneline -10
```

- 태스크 ID, 담당 에이전트, 완료 시각 확인
- 변경된 파일 목록 수집
- 발생했던 이슈 목록 수집

### Step 2: 교훈 추출 (Start/Stop/Continue + 5-Why)

**Start (시작해야 할 것)**:
```
- 이번에 없었지만 있었으면 좋았을 것:
  → [예: 태스크 킥오프 전 AC 정의]
```

**Stop (멈춰야 할 것)**:
```
- 이번에 했지만 다음엔 하지 말아야 할 것:
  → [예: 스펙 불명확한 상태로 착수]
```

**Continue (계속해야 할 것)**:
```
- 잘 동작했으니 계속해야 할 것:
  → [예: 커밋 단위 분리]
```

**5-Why (근본 원인 — 문제가 있었을 경우)**:
```
문제: [설명]
Why1: → Why2: → Why3: → Why4: → Why5: [근본 원인]
```

### Step 3: MEMORY.md 업데이트

교훈 항목을 MEMORY.md에 추가한다.

```bash
# MEMORY.md 현재 상태 확인
cat /Users/rocky/telegram-ai-org/memory/MEMORY.md | tail -30
```

**추가 형식 (MEMORY.md 말미에 append)**:

```markdown
## [YYYY-MM-DD] T-XXXX 회고 — [태스크명]

### 성공 요인
- [요인1]

### 개선 요인
- [요인1]

### 교훈 (다음 태스크에 적용)
- [교훈1]: [적용 방법]
- [교훈2]: [적용 방법]
```

Edit 도구로 MEMORY.md 말미에 추가한다.

### Step 4: 다음 스프린트 반영 항목 정리

```
다음 스프린트 반영 사항:
1. [백로그 항목1] — 우선순위: 상/중/하
2. [백로그 항목2] — 우선순위: 상/중/하

→ PM에게 다음 스프린트 계획 시 참고 요청
```

## 출력 형식 (PM 보고용)

```
## [태스크명] Retrospective 완료

**잘된 것**: [핵심 1개]
**개선할 것**: [핵심 1개]
**교훈**: [N개] → MEMORY.md 업데이트 완료

다음 스프린트 반영: [N개 항목]
```

## MEMORY.md 업데이트 원칙

- 기존 내용 삭제 금지 — 말미에 추가만
- 중복 교훈은 기존 항목 강화(횟수 표시)
- 태스크 ID 반드시 포함 (추적 가능성)
- 실행 가능한 교훈만 기록 ("더 잘하자" 같은 추상 교훈 금지)

## Gotchas

- MEMORY.md 경로: `/Users/rocky/telegram-ai-org/memory/MEMORY.md`
- 회고 없이 태스크 닫으면 같은 실수 반복 위험 (경험상 3회 이상 반복 패턴)
- 인시던트 회고는 post-mortem 템플릿과 병행 작성 권장
