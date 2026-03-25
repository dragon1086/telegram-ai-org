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

**자동 조치**: STALE 탐지 시 → 즉시 pm-progress-tracker 스킬 절차에 따라 iter를 재개한다. 사용자 확인 없이 자율 실행.

```
STALE 탐지 시 자동 실행 체인:
1. 해당 목표의 잔여 TODO 서브태스크 목록 추출
2. 개발실 담당 → [TEAM:engineering-senior-developer] 태그로 즉시 배분
3. 타부서 담당 → [COLLAB:태스크 설명|맥락: 목표ID + 달성률] 태그로 해당 조직에 위임
4. pm_progress_guide.md 이터레이션 로그에 "자동 재개 — harness-audit 트리거" 기록
5. docs/goal_snapshots/YYYY-MM-DD-goal-snapshot.md 업데이트

예시 (GOAL-001 STALE 탐지 시):
[TEAM:engineering-senior-developer]
ST-08 리팩토링 Phase 1을 재개합니다. GOAL-001이 3일 이상 진척 없어 harness-audit이 자동 트리거했습니다.
[COLLAB:ST-11 v1.0.0 릴리스 배포 준비 선행 확인|맥락: GOAL-001 ST-09 완료, ST-11 착수 전 운영실 환경 점검 필요]
```

**COLLAB 활용 건강도 점검**:
- 최근 7일간 [COLLAB:...] 태그 사용 횟수 집계
  ```bash
  grep -r "COLLAB_PREFIX\|🙋 도와줄\|\[COLLAB:" logs/ 2>/dev/null | wc -l
  ```
- 0회 → ⚠️ COLLAB_INACTIVE: 이번 iter에서 COLLAB 태그 **의무** 사용
- 1~3회 → ⚠️ COLLAB_LOW
- 4회 이상 → ✅ COLLAB_HEALTHY

**COLLAB_INACTIVE 자동 조치**:
```
COLLAB_INACTIVE 감지 시 자동 실행:
1. 현재 iter의 다부서 태스크 전부 추출
2. 각 타부서 태스크마다 즉시 [COLLAB:...] 태그 포함한 응답 생성
3. 다음 audit까지 COLLAB 사용 의무화 기록

예시:
[COLLAB:ST-11 v1.0.0 릴리스 배포 준비|맥락: COLLAB_INACTIVE 감지, 의무 사용 발동]
[COLLAB:리서치실에 Docker Hub 모범사례 조사 요청|맥락: ST-05 Docker 지원 선행 리서치 필요]
```

### 7. 자율 협업 프로세스 건강도 (신규)

주간 협업 루틴이 정상 작동하는지 점검한다.

**점검 항목**:
| 프로세스 | 점검 방법 | 판정 기준 |
|----------|-----------|-----------|
| 주간회의 | `logs/weekly_meeting.log` 최근 실행 날짜 | 7일 이내 → ✅ |
| 일일 회고 | `logs/retro.log` 최근 실행 날짜 | 1일 이내 → ✅ |
| 목표 파이프라인 | `logs/goal_pipeline.log` 최근 실행 | 1일 이내 → ✅ |
| harness-audit | `docs/audits/` 최신 파일 날짜 | 7일 이내 → ✅ |

**자동 조치**: 프로세스가 누락된 경우 →
```bash
# 로그 파일 확인
ls -la logs/*.log 2>/dev/null | tail -10
# 마지막 실행 시간 확인
stat -f "%m %N" logs/weekly_meeting.log 2>/dev/null
```

## 출력 형식
```
🔬 Harness Audit Report — {날짜}
━━━━━━━━━━━━━━━━━━━━━━━━━
봇 상태:        ✅/⚠️/❌
스킬 정합성:    ✅/⚠️/❌
의존성:         ✅/⚠️/❌
데이터 파이프:  ✅/⚠️/❌
문서 정합성:    ✅/⚠️/❌
목표 진척률:    ✅/⚠️/❌
  GOAL-001: XX% (iter N, last: YYYY-MM-DD) [ON_TRACK/STALE/BLOCKED]
  GOAL-002: XX% (iter N, last: YYYY-MM-DD) [ON_TRACK/STALE/BLOCKED]
협업 활성도:    ✅/⚠️/❌  (COLLAB 사용 횟수: N회/7일)
협업 프로세스:  ✅/⚠️/❌  (주간회의/일일회고/목표파이프라인)
━━━━━━━━━━━━━━━━━━━━━━━━━
리스크 레벨: LOW/MEDIUM/HIGH
STALE 감지 시: [자동 iter 재개 실행 — 위 체인 즉시 시작]
COLLAB_INACTIVE 감지 시: [다부서 태스크 즉시 COLLAB 태그 발동]
```
저장: `docs/audits/YYYY-MM-DD-harness-audit.md`

## 감사 완료 후 필수 후속 조치

감사가 끝나면 **항상** 다음 순서로 실행한다:

```
1. STALE 목표 있으면:
   → [TEAM:engineering-senior-developer] 개발실 태스크 즉시 착수
   → [COLLAB:운영 관련 태스크|맥락: STALE 자동 재개] 운영실 위임

2. COLLAB_INACTIVE이면:
   → 현재 iter에서 다부서 태스크 COLLAB으로 즉시 전환

3. 협업 프로세스 누락 있으면:
   → [COLLAB:ST-G2-03 주간회의 멀티봇 점검 요청|맥락: weekly_meeting.log 없음] 위임

4. 항상: pm_progress_guide.md 이터레이션 로그에 audit 결과 기록
```

> 이 스킬은 매주 금요일 17:05 KST `run_harness_audit.py` 크론으로 자동 실행됩니다.
