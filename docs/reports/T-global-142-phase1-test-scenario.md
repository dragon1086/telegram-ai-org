# Phase 1 검증 보고서 — 순서 강제 동작 테스트 시나리오

**작성일**: 2026-03-22
**담당**: aiorg_ops_bot (운영실)
**대상**: 리서치→개발실→운영실 의존성 체인 순서 강제 로직

---

## 1. 테스트 목적

레이스 컨디션 수정(commit `cf42da4`) 및 글로벌 스콥 원칙(`94f6198`, `f0bafb5`) 적용 후,
순서 강제 동작이 의도대로 차단·허용되는지 검증한다.

---

## 2. 검증 대상 코드 변경

| 커밋 | 변경 내용 |
|------|-----------|
| `cf42da4` | 의존성 사전 등록 — LLM 전 task_ids 생성 + deps 먼저 DB 등록 |
| `94f6198` | 봇별 재기동 과적합 문구 롤백 + PM 글로벌 스콥 원칙 도입 |
| `f0bafb5` | orchestration.yaml global_instructions 스콥 경계 원칙 추가 |
| `921ee77` | Gotcha 6 문구 범용화 (개발실/리서치실 특정 → 전체 specialist) |
| `e640704` | DEPENDS 체인 순서 강제 및 레이스 컨디션 수정 단위 테스트 추가 |

---

## 3. 테스트 시나리오

### SC-01: 정상 순서 — 리서치 → 개발 → 운영 (기대: 허용)

```
SubTask[0]: 시장조사     → aiorg_research_bot    (DEPENDS: none)
SubTask[1]: 코드구현     → aiorg_engineering_bot  (DEPENDS: 0)
SubTask[2]: 배포         → aiorg_ops_bot          (DEPENDS: 1)
```

**검증 포인트**:
- Wave 1: 리서치만 발송, 개발실·운영실 미발송
- Wave 2: 리서치 완료 후 개발실만 발송, 운영실 미발송
- Wave 3: 개발 완료 후 운영실만 발송

### SC-02: 비정상 경로 — 개발이 먼저 시도 (기대: 차단)

```
TaskPoller가 리서치 완료 전 개발실 태스크(DEPENDS:0 미충족)를 조기 수신 시도
```

**검증 포인트**:
- `get_tasks_for_dept`에서 deps_ready=False → 태스크 반환 안 함
- `[ORDER-GUARD]` 경고 로그 출력
- 레이스 컨디션 발생 안 함

### SC-03: 비정상 경로 — 운영이 개발 전 시도 (기대: 차단)

```
TaskPoller가 개발 완료 전 운영실 태스크(DEPENDS:1 미충족)를 조기 수신 시도
```

**검증 포인트**:
- `[ORDER-GUARD]` 경고 로그 출력
- 개발 완료 전까지 운영실 차단

### SC-04: 의존성 없는 병렬 태스크 (기대: 허용)

```
SubTask[0]: 리서치A  → aiorg_research_bot     (DEPENDS: none)
SubTask[1]: 리서치B  → aiorg_research_bot     (DEPENDS: none)
```

**검증 포인트**:
- Wave 1: 리서치A·B 동시 발송 (의도적 병렬)

---

## 4. 스테이징 실행 결과

**실행 명령**:
```bash
cd /Users/rocky/telegram-ai-org
.venv/bin/python -m pytest \
  tests/test_pm_orchestrator.py \
  tests/test_task_graph.py \
  tests/test_task_poller.py \
  tests/test_dispatch_engine.py \
  tests/test_context_db.py \
  tests/test_llm_decompose.py \
  -v --tb=short
```

**결과**: **70 passed, 1 warning in 3.87s** ✅

핵심 테스트: `test_dispatch_sequential_research_eng_ops` → PASSED

---

## 5. 순서 강제 동작 일치/불일치 대조표

| 시나리오 | 기대 동작 | 실제 동작 | 일치 여부 |
|----------|-----------|-----------|-----------|
| SC-01 Wave1: 리서치만 발송 | 허용 | 허용 (assert 통과) | ✅ 일치 |
| SC-01 Wave1: 개발실 미발송 | 차단 | 차단 (assert 통과) | ✅ 일치 |
| SC-01 Wave1: 운영실 미발송 | 차단 | 차단 (assert 통과) | ✅ 일치 |
| SC-01 Wave2: 리서치 완료 후 개발실 발송 | 허용 | 허용 (assert 통과) | ✅ 일치 |
| SC-01 Wave2: 운영실 미발송 | 차단 | 차단 (assert 통과) | ✅ 일치 |
| SC-01 Wave3: 개발 완료 후 운영실 발송 | 허용 | 허용 (assert 통과) | ✅ 일치 |
| SC-02 deps 미충족 조기 수신 차단 | 차단 | get_tasks_for_dept 필터링 | ✅ 일치 |
| SC-03 운영실 조기 수신 차단 | 차단 | get_tasks_for_dept 필터링 | ✅ 일치 |
| SC-04 의도적 병렬 허용 | 허용 | 허용 | ✅ 일치 |

**불일치 항목**: 없음 ✅

---

## 6. 추가된 모니터링

`core/context_db.py` `get_tasks_for_dept()` 내에 순서 위반 차단 감지 로그 추가:

```python
logger.warning(
    f"[ORDER-GUARD] 태스크 {task_id} ({dept_id}) 차단: "
    f"의존 태스크 {blocking_dep} 상태={blocking_status} (미완료). "
    "레이스 컨디션 차단 정상 동작."
)
```

운영 중 이 로그가 발생하면 → 순서 위반 시도가 있었으나 정상 차단된 것.
이상 빈도(1분 이내 3회 이상) 시 → 레이스 컨디션 재발 의심.
