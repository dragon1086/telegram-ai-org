---
name: quality-gate
description: "Use before merging code or deploying to production. Runs ruff lint + pytest + import validation and reports PASS/WARN/FAIL. Triggers: 'quality gate', 'quality check', '품질검사', 'QA gate', 'pre-merge check', 'pre-deploy', before any git merge or deploy"
---

# Quality Gate (품질 게이트)

everything-claude-code 하네스 패턴 적용. 코드 병합/배포 전 자동 품질 검사.

## 검사 항목

### 1. 린트 (Ruff)
```bash
.venv/bin/ruff check . --exit-zero
```
오류 수 집계 및 보고.

### 2. 테스트 (pytest)
```bash
.venv/bin/pytest -q --tb=short 2>&1 | tail -20
```
통과/실패 수 및 실패 테스트 목록.

### 3. Import 검증
```bash
.venv/bin/python -c "import core; print('OK')"
```

### 4. 환경변수 확인
필수 환경변수 존재 여부 체크 (토큰, API 키 등).

## When to Run First

다음 상황에서는 **다른 스킬보다 quality-gate를 먼저 실행**해야 한다:

| 상황 | quality-gate 실행 시점 |
|------|----------------------|
| 코드 변경 완료 후 | pm-task-dispatch 또는 engineering-review 전 |
| PR/머지 전 | git merge 명령 실행 전 |
| 배포 전 | 어떤 배포 스크립트보다 먼저 |
| engineering-review 요청 전 | 리뷰어에게 할당하기 전 |
| 주간회의(weekly-review) 보고 전 | 이번주 코드 변경이 있었다면 |

```
강제 실행 규칙:
- quality-gate FAIL 상태에서 병합/배포 진행 금지
- WARN 상태는 팀장(PM) 승인 후 진행 가능
- 훅(PreToolUse)이 비활성화된 환경에서도 이 지침을 수동으로 따른다
```

## 판정 기준
- ✅ PASS: 테스트 100% 통과 + 린트 오류 0
- ⚠️ WARN: 테스트 통과 + 린트 경고만 있음
- ❌ FAIL: 테스트 실패 또는 린트 오류 있음

## 출력 형식
```
🔍 Quality Gate 결과
━━━━━━━━━━━━━━━━━
린트:    ✅/❌ (오류 N개)
테스트:  ✅/❌ (N passed, N failed)
Import:  ✅/❌
━━━━━━━━━━━━━━━━━
판정: PASS/WARN/FAIL
```
