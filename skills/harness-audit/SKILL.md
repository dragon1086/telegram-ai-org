---
name: harness-audit
description: "Use to audit the overall health of the AI organization harness — bot status, skill inventory, dependencies, and doc freshness. Triggers: 'harness audit', '하네스 감사', 'system audit', 'reliability check', 'health check', weekly or when system issues are suspected"
---

# Harness Audit (하네스 감사)

everything-claude-code의 `/harness-audit` 패턴 적용. 시스템 전체의 신뢰성을 정기 감사한다.

## 감사 영역

### 1. 봇 상태 확인
- 모든 봇이 응답 가능한 상태인가
- 환경변수/토큰이 유효한가
- 마지막 성공 실행 시간

### 2. 스킬 인벤토리
- `skills/` 디렉토리의 스킬 목록 vs `organizations.yaml` preferred_skills 정합성
- 사용 중인 스킬과 미사용 스킬 구분

### 3. 의존성 건강도
- `pyproject.toml` vs 실제 설치된 패키지 정합성
- 알려진 취약점 여부 (`pip audit` 가능 시)

### 4. 데이터 파이프라인
- 운영 로그 (`logs/`) 분석: 최근 7일 오류율
- `.ai-org/runs/` 미완료 run 수

### 5. 문서 정합성
- CLAUDE.md, AGENTS.md 최신 상태 여부
- 코드 변경 후 문서 미업데이트 탐지

## 출력 형식
```
🔬 Harness Audit Report — {날짜}
━━━━━━━━━━━━━━━━━━━━━━━━━
봇 상태:        ✅/⚠️/❌
스킬 정합성:    ✅/⚠️/❌
의존성:         ✅/⚠️/❌
데이터 파이프:  ✅/⚠️/❌
문서 정합성:    ✅/⚠️/❌
━━━━━━━━━━━━━━━━━━━━━━━━━
리스크 레벨: LOW/MEDIUM/HIGH
권장 액션: ...
```
저장: `docs/audits/YYYY-MM-DD-harness-audit.md`
