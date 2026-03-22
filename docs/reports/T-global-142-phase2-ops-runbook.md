# Phase 2 운영 배포 보고서 + 런북 최종본

**작성일**: 2026-03-22
**담당**: aiorg_ops_bot (운영실)
**상태**: 운영 환경 반영 완료 ✅

---

## 1. 운영 배포 완료 보고서

### 배포 내역 (이미 main 반영 완료)

| 커밋 | 파일 | 변경 내용 | 배포 일시 |
|------|------|-----------|-----------|
| `cf42da4` | `core/pm_orchestrator.py` | 레이스 컨디션 수정 — 의존성 사전 등록 | 2026-03-21 10:36 |
| `94f6198` | `bots/*/CLAUDE.md`, `orchestration.yaml` | 봇별 과적합 재기동 문구 롤백 | 2026-03-21 |
| `f0bafb5` | `orchestration.yaml` | global_instructions 스콥 경계 원칙 | 2026-03-21 |
| `921ee77` | `skills/*/gotchas.md` | Gotcha 범용화 | 2026-03-21 |
| `e640704` | `tests/test_pm_orchestrator.py` | 순서 강제 단위 테스트 | 2026-03-21 |
| (현재) | `core/context_db.py` | [ORDER-GUARD] 모니터링 로그 추가 | 2026-03-22 |

### 운영 환경 최종 검증

```
test suite: 70 passed, 1 warning in 3.87s
핵심 검증: test_dispatch_sequential_research_eng_ops PASSED
```

---

## 2. 롤백 절차

### 레이스 컨디션 수정(`cf42da4`) 롤백이 필요한 경우

```bash
# 1. 현재 상태 백업
git tag backup/before-rollback-$(date +%Y%m%d)

# 2. pm_orchestrator.py 이전 버전 복원
git revert cf42da4 --no-commit

# 3. 테스트 확인
.venv/bin/python -m pytest tests/test_pm_orchestrator.py -v

# 4. 커밋 및 재기동 요청
git commit -m "revert: cf42da4 레이스컨디션 수정 롤백"
bash scripts/request_restart.sh --reason "cf42da4 롤백"
```

**주의**: 롤백 시 리서치→개발→운영 병렬 실행 버그 재발 가능. 반드시 PM 승인 후 수행.

### global_instructions 롤백이 필요한 경우

```bash
git revert f0bafb5 --no-commit
# orchestration.yaml global_instructions 섹션 제거됨
git commit -m "revert: global_instructions 스콥 원칙 롤백"
bash scripts/request_restart.sh --reason "orchestration.yaml 롤백"
```

---

## 3. 순서 강제 동작 구조 (최종)

```
PM._dispatch_subtasks() 호출 시:

Step 0: task_ids 사전 생성 (LLM 전, 즉시)
   ↓
Step 0b: 모든 deps를 pm_task_dependencies에 먼저 등록
   ↓ (이 시점부터 TaskPoller가 조기 수신해도 deps 미충족으로 차단됨)
Step 1: LLM으로 태스크 생성 (~15-20s/task, 순차)
   ↓
Step 3: get_ready_tasks() → deps 없는 태스크만 Wave 1 발송

TaskPoller.get_tasks_for_dept():
  - "assigned" 태스크 → 즉시 반환
  - "pending" 태스크 → deps 모두 done? → 반환 / 미충족 → [ORDER-GUARD] 로그 후 차단
```

---

## 4. 모니터링 알람 설정

### [ORDER-GUARD] 이벤트 감지

**감지 조건**: `core/context_db.py` get_tasks_for_dept() 내
```
[ORDER-GUARD] 태스크 {id} ({dept}) 차단: ...
```

**알림 수신자**: aiorg_ops_bot (운영실)

**정상 판단**: 이 로그 자체는 정상 차단 동작. 문제는 이 로그가 없어야 할 때 발생 빈도 급증 시.

**이상 판단 기준**:
- 동일 태스크 ID에 대해 1분 이내 ORDER-GUARD 5회 이상 → 레이스 컨디션 재발 의심
- PM_TASK 3개 이상이 동시에 running 상태 (deps 체인인데) → 병렬 실행 의심

**확인 명령**:
```bash
# 운영 DB에서 현재 running 태스크 확인
sqlite3 ~/.ai-org/context.db \
  "SELECT id, assigned_dept, status FROM pm_tasks
   WHERE status='running' ORDER BY created_at DESC LIMIT 20;"

# 특정 parent 하위 태스크 순서 확인
sqlite3 ~/.ai-org/context.db \
  "SELECT t.id, t.assigned_dept, t.status, d.depends_on
   FROM pm_tasks t
   LEFT JOIN pm_task_dependencies d ON d.task_id = t.id
   WHERE t.parent_id='[PARENT_ID]'
   ORDER BY t.created_at;"
```

### 순서 위반 이벤트 모니터링 대시보드 (로그 필터)

```bash
# 실시간 ORDER-GUARD 이벤트 확인 (loguru 출력 필터)
tail -f ~/.ai-org/ops.log | grep "ORDER-GUARD"
```

---

## 5. 운영 환경 최종 검증 시나리오 재현 로그

**실행 일시**: 2026-03-22
**검증 명령**:
```bash
cd /Users/rocky/telegram-ai-org
.venv/bin/python -m pytest \
  tests/test_pm_orchestrator.py::test_dispatch_sequential_research_eng_ops \
  -v --tb=long -s
```

**결과**:
```
PASSED tests/test_pm_orchestrator.py::test_dispatch_sequential_research_eng_ops

검증 내용:
  [Wave 1] aiorg_research_bot 발송 ✅
  [Wave 1] aiorg_engineering_bot 미발송 (차단) ✅
  [Wave 1] aiorg_ops_bot 미발송 (차단) ✅
  [Wave 2] 리서치 완료 → aiorg_engineering_bot 발송 ✅
  [Wave 2] aiorg_ops_bot 미발송 (차단) ✅
  [Wave 3] 개발 완료 → aiorg_ops_bot 발송 ✅
```

**판정**: 순서 강제 동작 100% 일치 ✅

---

## 6. 알림 수신자

| 이벤트 | 알림 대상 |
|--------|-----------|
| ORDER-GUARD 빈발 (5회/분 이상) | aiorg_ops_bot (운영실) → PM에게 즉시 보고 |
| 동시 running 태스크 3개 이상 (deps 체인) | aiorg_ops_bot |
| test suite 실패 | aiorg_ops_bot → aiorg_engineering_bot에 수정 위임 요청 |
