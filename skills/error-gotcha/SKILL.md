---
name: error-gotcha
description: "Use after fixing a runtime error or bug to automatically add a gotcha entry to the relevant skill. Prevents the same mistake from recurring. Triggers: 'gotcha 추가', 'error gotcha', '에러 회고', 'add gotcha', after fixing any NameError/ImportError/UnboundLocalError or runtime crash"
---

# Error Gotcha (에러 → 자동 Gotcha 추가)

에러를 수정한 직후 실행하여, 관련 스킬의 gotchas.md에 재발 방지 항목을 자동 추가한다.

## 실행 조건

아래 상황에서 자동 또는 수동으로 트리거:
- 런타임 에러 수정 후 (NameError, ImportError, UnboundLocalError 등)
- 봇 crash 원인 분석 및 수정 후
- 같은 유형의 실수가 2회 이상 반복된 경우

## Step 1: 에러 분석

$ARGUMENTS 또는 직전 대화 컨텍스트에서 아래를 추출:

- **에러 유형**: 예외 클래스명 (예: `NameError`, `UnboundLocalError`)
- **발생 파일**: 에러가 발생한 소스 파일 경로
- **근본 원인**: 왜 발생했는지 (1줄)
- **수정 내용**: 어떻게 고쳤는지 (1줄)

## Step 2: 관련 스킬 매칭

에러 유형에 따라 가장 적합한 스킬을 선택:

| 에러 범주 | 대상 스킬 |
|-----------|-----------|
| import 누락, 스코핑, NameError | `engineering-review` |
| 테스트 실패, 환경 문제 | `quality-gate` |
| 태스크 배분/라우팅 오류 | `pm-task-dispatch` |
| 배포/재시작 관련 | `pm-task-dispatch` (자기파괴 작업) |
| 성능/블로킹 이슈 | `engineering-review` |
| 해당 없음 | 새 gotchas.md 생성 제안 |

## Step 3: Gotcha 항목 작성

아래 형식으로 gotcha 항목을 생성:

```markdown
## Gotcha N: {에러를 설명하는 짧은 제목}
**상황**: {어떤 작업을 할 때 발생하는지}
**증상**: {사용자/시스템이 겪는 현상. 가능하면 실제 에러 메시지 포함}
**해결**: {재발 방지를 위한 구체적 행동 지침}
```

규칙:
- 실제 인시던트 기반만 기록 (가상 시나리오 금지)
- 증상에 실제 에러 메시지나 태스크 ID 포함 권장
- 해결에는 "~하지 말 것" 보다 "~할 것"을 우선 (긍정 지침)

## Step 4: gotchas.md 업데이트

1. 대상 스킬의 `gotchas.md` 읽기
2. 기존 Gotcha 번호 확인 → 다음 번호로 새 항목 추가
3. 중복 확인: 같은 근본 원인의 gotcha가 이미 있으면 기존 항목 보강 (신규 추가 안 함)

## Step 5: 교훈 기록 연계

gotcha 추가 후 아래도 함께 수행:
1. `tasks/lessons.md`에 교훈 기록 (현재 프로젝트에 있을 경우)
2. `skill-evolve` 스킬이 다음 실행 시 이 gotcha를 패턴 분석에 포함하도록 lesson_memory에 기록

## 완료 조건

- [ ] 관련 스킬의 gotchas.md에 새 항목이 추가됨
- [ ] 기존 gotcha와 중복이 아님을 확인함
- [ ] 커밋 메시지에 `gotcha:` 접두사 포함
