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
