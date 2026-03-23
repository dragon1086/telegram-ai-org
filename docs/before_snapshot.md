# Before Snapshot — Harness 배포 전 기준선

> 수집 기준: 2026-03-23 (IMP-1~IMP-7 배포 완료 직후, verification-report 작성 직전)
> 작성자: aiorg_ops_bot (운영실 PM)
> 목적: 검증 보고서 작성을 위한 before 기준값 정의 및 배포 완료 상태 스냅샷

---

## 1. 크론(Cron) 등록 현황

| ID | 스케줄 | 명령어 | 대상 | 상태 |
|----|--------|--------|------|------|
| CRON-01 | `50 7 * * *` (매일 07:50) | `sync_db.sh` | prism-publisher | 외부 프로젝트 (참고) |
| CRON-02 | `10 11 * * *` (매일 11:10) | `sync_db.sh` | prism-publisher | 외부 프로젝트 (참고) |
| CRON-03 | `5 17 * * *` (매일 17:05) | `sync_db.sh` | prism-publisher | 외부 프로젝트 (참고) |
| **CRON-04** | **`15 9 * * *` (매일 09:15)** | **`bash scripts/run_daily_review_job.sh`** | **telegram-ai-org** | **✅ 정상 등록** |

**판정**: telegram-ai-org 전용 크론 CRON-04 1개 정상 등록. `.ai-org/crons/` 별도 크론 디렉토리 없음 (시스템 crontab 단일 관리).

---

## 2. Hooks 등록 현황 (settings.local.json)

| 이벤트 | 훅 파일 | 매처 | 타임아웃 | Async | 상태 |
|--------|---------|------|---------|-------|------|
| `SessionStart` | `session-start.sh` | * | 15s | No | ✅ 등록 |
| `SessionStart` | `detect-gaps.sh` | * | 15s | Yes | ✅ 등록 |
| `PreToolUse` | `validate-dangerous-patterns.sh` | Bash | 10s | No | ✅ 등록 |
| `SubagentStart` | `log-agent.sh` | * | 5s | Yes | ✅ 등록 |
| `PostToolUse` | ruff 자동 린트 (인라인) | Write\|Edit | 30s | No | ✅ 등록 |
| `Stop` | 세션 종료 로그 (인라인) | * | — | Yes | ✅ 등록 |

**훅 이벤트 수: 5종 / 스크립트 파일: 4개**

`scripts/hooks/` 존재 파일:
- `session-start.sh` ✅ 등록됨
- `detect-gaps.sh` ✅ 등록됨 (c9e7a82 커밋)
- `validate-dangerous-patterns.sh` ✅ 등록됨
- `log-agent.sh` ✅ 등록됨

---

## 3. orchestration.yaml 라우팅 구조

| 구성 요소 | 현황 | 상태 |
|----------|------|------|
| 조직 수 | 7개 (design/engineering/growth/ops/pm/product/research) | ✅ |
| Team Profiles | 7개 (design_strategy, engineering_delivery, global_orchestrator 등) | ✅ |
| Verification Profiles | 2개 (orchestrator_default, specialist_default) | ✅ |
| Phase Policies | 1개 (default) | ✅ |
| validate-config | **PASS** | ✅ |

**글로벌 규칙 4개 영역**:
1. PM 업무 스코프 준수 (최우선)
2. 배포·인프라 전담 원칙
3. Git 워크트리 워크플로
4. 현재 시간 사용 원칙

---

## 4. Harness 구성 현황 (IMP-1~IMP-7 적용 후)

| 항목 | Before (IMP 적용 전) | After (IMP 적용 후) |
|------|---------------------|---------------------|
| 훅 등록 수 | 1개 (PreCompact만) | **5종 6개** |
| 위험패턴 차단 | 없음 | PreToolUse로 5종 차단 |
| detect-gaps | 없음 | SessionStart async 등록 |
| 스킬 allowed-tools | 미설정 (2개 미적용) | **6개 전체 적용** |
| Document Templates | 없음 | **6개 템플릿** |
| 태스크 생애주기 스킬 | 없음 | **3개 신설** (task-kickoff, loop-checkpoint, performance-eval) |
| 테스트 통과 수 | 832개 (T-324 기준) | **999개** |

---

## 5. 스킬 현황

| 스킬 ID | 파일 | allowed-tools | gotchas.md |
|---------|------|--------------|------------|
| quality-gate | ✅ | Read, Glob, Bash, Write | ✅ |
| bot-triage | ✅ | Read, Bash, Glob, Grep | ✅ |
| error-gotcha | ✅ | Read, Edit, Glob, Grep | ✅ |
| harness-audit | ✅ | Read, Bash, Glob, Grep | ✅ |
| brainstorming-auto | ✅ | Read, Glob, Grep, Write, Bash | ✅ |
| safe-modify | ✅ | Read, Edit, Bash, Grep | — |
| task-kickoff | ✅ (신규) | — | ✅ |
| loop-checkpoint | ✅ (신규) | — | ✅ |
| performance-eval | ✅ (신규) | — | ✅ |
| + 기타 15개 | ✅ | — | 일부 |

**총 스킬: 24개** (vs 단일 Claude Code 0개)

---

## 6. 테스트 프롬프트 세트 정의 (Before 기준 5종)

아래 5개 프롬프트는 before/after 비교 측정에 사용한다.

| ID | 프롬프트 | 목적 | 예상 라우팅 |
|----|---------|------|------------|
| TP-01 | "신규 기능 아이디어를 브레인스토밍해줘. 봇 성능 모니터링 기능." | 기획 라우팅 검증 | → product/research |
| TP-02 | "core/shared_memory.py에 TTL 파라미터를 추가하고 테스트를 작성해줘." | 개발 라우팅 + 품질 게이트 | → engineering |
| TP-03 | "봇이 응답하지 않아요. 진단해줘." | 운영 라우팅 + bot-triage | → ops |
| TP-04 | "게임 스튜디오 경쟁사 시장조사를 해줘." | 리서치 라우팅 | → research |
| TP-05 | "이번 스프린트 계획을 3팀이 함께 수립해줘." | 멀티팀 조율 | → pm → product+engineering+ops |

---

## 7. Before 지표 기준값 테이블

| KPI | 단일 Claude Code (추정) | 우리 시스템 Before (IMP 전) | 우리 시스템 After (IMP 후) |
|-----|------------------------|--------------------------|--------------------------|
| 훅 이벤트 수 | 0 | 1 | **5** |
| 자동 오류 감지율(ERR-Detection) | 0% | ~20% | **≥70%** (예상) |
| 자동 오류 복구율(ERR-Recovery) | 0% | ~30% | **≥60%** (예상) |
| 테스트 통과 수 | — | 832개 | **999개** |
| 병렬 처리(PPE-MaxParallel) | 1 | 4+ | **6+** |
| 컨텍스트 보존(CTX-CrossSession) | ~30% | ~70% | **≥80%** (예상) |
| Document Templates | 0개 | 0개 | **6개** |
| Gap 자동 탐지 | 없음 | 없음 | **SessionStart 자동** |

---

*이 문서는 docs/verification-report.md와 연동된다.*
