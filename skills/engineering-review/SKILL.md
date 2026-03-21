---
name: engineering-review
description: "Use when the engineering bot needs to review code changes before merging. Runs lint, tests, and a structured checklist. Triggers: 'code review', '코드리뷰', 'review code', 'code check', 'PR review', before merging any code change"
---

# Engineering Review (코드리뷰 스킬)

개발실 봇이 코드 변경사항을 체계적으로 검토한다.

## 검토 항목 (체크리스트)
- [ ] 기능 정확성: 요구사항을 충족하는가
- [ ] 테스트: 새 기능에 테스트가 있는가
- [ ] 보안: SQL injection, XSS, 인증 취약점 없는가
- [ ] 성능: N+1 쿼리, 불필요한 반복 없는가
- [ ] 코드 품질: Ruff/pylint 통과, 100자 이하 줄 길이
- [ ] async: 기존 async 패턴 유지하는가
- [ ] 비밀: 하드코딩된 토큰/키 없는가

## Prerequisites

코드 변경이 완료된 후, **engineering-review 전에 quality-gate 스킬을 먼저 실행**하라.

```
실행 순서:
1. quality-gate 스킬 실행 (린트 + 테스트 + import 검증)
2. quality-gate PASS → engineering-review 체크리스트 진행
3. quality-gate FAIL → 수정 후 재실행 (리뷰 진행 불가)
```

> quality-gate는 객관적 자동 검사, engineering-review는 주관적 코드 품질 판단.
> 두 단계를 분리하여 리뷰어가 통과 불가 코드를 검토하는 낭비를 방지한다.

## 자동 실행
```bash
.venv/bin/ruff check .
.venv/bin/pytest -q
```
결과를 요약하여 보고.

## ⚠️ 스코프 경계 (절대 준수)

engineering-review 스킬은 **코드 품질 판단까지만** 담당한다.

| 단계 | 담당 | 비고 |
|------|------|------|
| 린트 / 테스트 실행 | 개발실 ✅ | 자체 수행 가능 |
| 코드 품질 판단·코멘트 | 개발실 ✅ | 자체 수행 가능 |
| 로컬 커밋 (`git commit`) | 개발실 ✅ | 자체 수행 가능 |
| **`git push`** | **운영실 위임 필수** ⛔ | 개발실 자체 수행 금지 |
| **`git merge`** | **운영실 위임 필수** ⛔ | 개발실 자체 수행 금지 |
| **봇 재기동** | **운영실 위임 필수** ⛔ | 개발실 자체 수행 금지 |

리뷰 완료 후 배포·머지·재기동이 필요하면:
```
[COLLAB:머지/푸시/재기동 요청|맥락: engineering-review 완료, 배포 준비됨]
```
