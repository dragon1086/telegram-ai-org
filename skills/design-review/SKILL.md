---
name: design-review
description: "Use when reviewing a PRD, design document, or architecture proposal. Validates required sections and gives PASS/FAIL verdict. Triggers: 'design review', '설계 검토', 'PRD 리뷰', 'design check', 'review design', '설계서 검토', when a design doc is submitted for review"
allowed-tools: Read, Glob, Grep
context: |
  !ls /Users/rocky/telegram-ai-org/docs/ 2>/dev/null
  !git -C /Users/rocky/telegram-ai-org log --oneline --since="1 week ago" 2>/dev/null | head -10
---

# Design Review (설계 검토)

PRD, 설계서, ADR 제출 시 5개 필수 섹션 자동 검증 → PASS/FAIL 판정.
Game Studios `/gate-check` 패턴 포팅.

## 언제 사용하나

- PM이 에이전트에게 설계 문서를 검토 요청할 때
- PRD나 기술 설계서를 실행 전 검증할 때
- ADR 작성 후 승인 전 품질 체크 시
- 산출물에 필수 섹션이 있는지 확인이 필요한 경우

## 5개 필수 섹션 체크리스트

### 섹션 1: What (무엇을 하는가)

```
체크:
- [ ] 구현할 기능/변경의 명확한 설명이 있는가?
- [ ] "무엇"이 한 문장으로 요약 가능한가?
- [ ] 기존 시스템과의 차이점이 명시되었는가?
```

**FAIL 조건**: What 섹션 자체가 없거나 1문장 미만

### 섹션 2: Why (왜 하는가)

```
체크:
- [ ] 비즈니스/기술적 근거가 있는가?
- [ ] 지금 해야 하는 이유가 명시되었는가?
- [ ] 상위 목표(OKR/KPI)와 연결되었는가?
```

**FAIL 조건**: Why 없이 바로 How로 넘어간 경우

### 섹션 3: How (어떻게 하는가)

```
체크:
- [ ] 구현 방법이 단계별로 기술되었는가?
- [ ] 변경 대상 파일/모듈이 명시되었는가?
- [ ] 기술 스택/도구 선택이 명시되었는가?
```

**FAIL 조건**: "구현한다"는 선언만 있고 방법이 없는 경우

### 섹션 4: Acceptance Criteria (완료 기준)

```
체크:
- [ ] 측정 가능한 AC가 최소 2개 이상인가?
- [ ] 각 AC가 Pass/Fail 판정 가능한 형식인가?
- [ ] 자동 검증과 수동 검증이 구분되었는가?
```

**FAIL 조건**: AC 없음 또는 "잘 동작하면 완료" 같은 측정 불가 기준

### 섹션 5: 리스크 (위험 요소)

```
체크:
- [ ] 예상 위험 요소가 최소 1개 이상 명시되었는가?
- [ ] 각 위험에 완화 전략이 있는가?
- [ ] 롤백 계획이 있는가? (해당하는 경우)
```

**FAIL 조건**: 리스크 섹션 자체가 없는 경우

---

## 검토 절차

### Step 1: 문서 읽기

```bash
# 문서 경로 확인
ls docs/ 2>/dev/null
```

대상 문서를 Read 도구로 읽는다.

### Step 2: 섹션별 체크 실행

위 5개 체크리스트를 순서대로 적용한다.
각 섹션별로 PASS / FAIL / WARNING 중 하나를 판정한다.

### Step 3: 종합 판정 및 보고

```
## Design Review 결과

| 섹션 | 판정 | 비고 |
|------|------|------|
| What | ✅ PASS / ❌ FAIL / ⚠️ WARN | |
| Why | ✅ PASS / ❌ FAIL / ⚠️ WARN | |
| How | ✅ PASS / ❌ FAIL / ⚠️ WARN | |
| AC | ✅ PASS / ❌ FAIL / ⚠️ WARN | |
| 리스크 | ✅ PASS / ❌ FAIL / ⚠️ WARN | |

**종합 판정**: ✅ PASS / ❌ FAIL

FAIL 항목:
- [섹션명]: [구체적으로 무엇이 부족한가]

→ PASS: 실행 승인. FAIL: 아래 항목 보완 후 재제출.
```

## 판정 기준

| 결과 | 조건 | 조치 |
|------|------|------|
| **PASS** | 5개 섹션 모두 PASS 또는 WARN 이하 | 실행 승인 |
| **CONDITIONAL PASS** | FAIL 0개, WARN 1-2개 | WARN 항목 개선 권고 후 실행 가능 |
| **FAIL** | FAIL 1개 이상 | 보완 후 재제출 필수 |

## Gotchas

- AC 없는 설계서는 무조건 FAIL — 예외 없음
- "추후 결정" 항목은 WARN 처리, FAIL은 아님
- 설계서 길이는 판정 기준이 아님 (짧아도 5섹션 있으면 PASS)
