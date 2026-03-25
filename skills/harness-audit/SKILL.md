---
name: harness-audit
description: "Use to audit the overall health of the AI organization harness — bot status, skill inventory, dependencies, and doc freshness. Triggers: 'harness audit', '하네스 감사', 'system audit', 'reliability check', 'health check', weekly or when system issues are suspected"
allowed-tools: Bash, Read, Glob, Grep
---

# Harness Audit (하네스 감사)

everything-claude-code의 `/harness-audit` 패턴 적용. 시스템 전체의 신뢰성을 정기 감사한다.

## Scope 선택

`$ARGUMENTS`로 감사 범위를 지정할 수 있다:
- `infra` — 인프라 영역만 (봇 상태, 의존성, 데이터 파이프라인 = 영역 1, 3, 4)
- `code` — 코드 영역만 (스킬 인벤토리, 문서 정합성 = 영역 2, 5)
- `all` 또는 인자 없음 — 전체 영역 (기본값)

```
사용 예:
  harness-audit           → 전체 감사
  harness-audit infra     → 인프라만
  harness-audit code      → 코드만
```

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

### 6. 목표 진척률 (Goal Progress) — 핵심 추가 영역
PM 목표가 실제로 앞으로 가고 있는지 정기 점검한다.

**점검 방법**:
```bash
# 1. pm_progress_guide.md 읽기
cat ~/.claude/projects/-Users-rocky-telegram-ai-org/memory/pm_progress_guide.md

# 2. 목표별 완료 서브태스크 수 집계
grep -c "상태: DONE" 또는 수동 파싱

# 3. 이터레이션 로그에서 최근 진행 날짜 확인
```

**점검 항목**:
- 활성 목표(IN_PROGRESS)별 달성률 (완료 서브태스크 / 전체)
- 마지막 이터레이션 날짜 (3일 이상 경과 시 ⚠️ STALE)
- BLOCKED 목표 목록 및 블로커 원인
- "다음 조치" 항목 중 미착수 항목 수

**판정 기준**:
| 상태 | 기준 |
|------|------|
| ✅ ON_TRACK | 최근 2일 내 진척, 달성률 정상 |
| ⚠️ STALE | 3일 이상 이터레이션 없음 |
| ❌ BLOCKED | 블로커로 인해 미진행 |

**자동 조치**: STALE 탐지 시 pm-progress-tracker 스킬을 호출해 iter 재개

## 출력 형식
```
🔬 Harness Audit Report — {날짜}
━━━━━━━━━━━━━━━━━━━━━━━━━
봇 상태:        ✅/⚠️/❌
스킬 정합성:    ✅/⚠️/❌
의존성:         ✅/⚠️/❌
데이터 파이프:  ✅/⚠️/❌
문서 정합성:    ✅/⚠️/❌
목표 진척률:    ✅/⚠️/❌  ← 신규
  GOAL-001: XX% (iter N, last: YYYY-MM-DD)
  GOAL-002: XX% (iter N, last: YYYY-MM-DD)
━━━━━━━━━━━━━━━━━━━━━━━━━
리스크 레벨: LOW/MEDIUM/HIGH
권장 액션: ...
미착수 다음조치: (STALE 탐지 시 pm-progress-tracker 자동 호출)
```
저장: `docs/audits/YYYY-MM-DD-harness-audit.md`
