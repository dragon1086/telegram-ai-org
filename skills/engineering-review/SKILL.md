---
name: engineering-review
description: "개발실 봇 전용 코드리뷰 스킬. 변경사항을 체계적으로 검토한다. Triggers: 'code review', '코드리뷰', 'review code', 'code check'"
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

## 자동 실행
```bash
.venv/bin/ruff check .
.venv/bin/pytest -q
```
결과를 요약하여 보고.
