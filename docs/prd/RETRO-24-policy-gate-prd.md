# PRD: 정책→게이트 연결 파이프라인 (RETRO-24)

**문서 버전**: v1.0
**작성일**: 2026-03-31
**작성 조직**: 기획실 (aiorg_product_bot)
**상태**: APPROVED — 구현 위임 준비
**관련 ACTION**: RETRO-24 (2026-03-30 일일회고 발굴)

---

## 1. 배경 및 문제 정의

### 현재 상태 (As-Is)
- `docs/RETRO-12-automation-policy-spec.md`에 10개 수동 확인 포인트 + 우선순위 매트릭스 완성
- 하지만 정책 문서는 **읽는 것**으로만 존재 — 실행 전 강제 검증 구조 없음
- 결과: 정책 위반 상태에서도 태스크가 dispatch되고 배포가 진행됨
- 실행 전환율: 정책 준수 기준 측정 불가 (게이트 없음)

### 목표 상태 (To-Be)
> **"정책 문서"가 "실행 게이트"가 된다.**

태스크 실행 전, 해당 태스크가 관련 정책 조건을 충족하는지 자동 검증.
미충족 시 실행이 **차단**되고 담당 조직에 remediation ACTION이 자동 생성됨.

---

## 2. 범위

### In-Scope
- GoalTracker dispatch 전 정책 게이트 체크 삽입
- RETRO-12 자동화 정책 스펙 → 게이트 조건 변환 (10개 포인트 → 체크 로직)
- 게이트 미통과 시 자동 remediation 태스크 생성
- 회고 ACTION의 정책 준수 여부 로그 기록

### Out-of-Scope
- CI/CD 파이프라인 직접 제어 (RETRO-22 운영실 담당)
- UI 블로킹 패턴 (RETRO-23 디자인실 담당)
- 인프라 배포 차단 (RETRO-22 범위)

---

## 3. 사용자 스토리

| ID | 역할 | 원하는 것 | 이유 |
|----|------|-----------|------|
| US-01 | PM 봇 | 정책 미준수 태스크를 자동 탐지하고 싶다 | 수동 확인 없이 정책 위반 조기 발견 |
| US-02 | 개발실 | 내 태스크가 정책 조건을 충족하는지 dispatch 전에 알고 싶다 | 사후 수정 비용 최소화 |
| US-03 | 운영실 | 정책 미통과 태스크가 배포 큐에 들어오지 않기를 원한다 | pre-flight 연동 완성 |
| US-04 | PM 봇 | 미통과 사유가 명확한 remediation ACTION이 자동 생성되기를 원한다 | 다음 사이클에 즉시 실행 가능하게 |

---

## 4. 기능 요구사항

### FR-01: PolicyGate 클래스 구현
- **위치**: `goal_tracker/policy_gate.py`
- **인터페이스**:
  ```python
  class PolicyGate:
      async def check(self, action_item: ActionItem) -> PolicyCheckResult

  @dataclass
  class PolicyCheckResult:
      passed: bool
      failed_policies: list[str]   # RETRO-12 정책 ID
      remediation_desc: str         # 미통과 시 자동 생성할 ACTION 설명
  ```

### FR-02: LoopRunner dispatch 전 게이트 삽입
- `goal_tracker/loop_runner.py`의 `_do_dispatch()` 진입 전 PolicyGate.check() 호출
- 미통과 항목 → dispatch 스킵 + remediation ActionItem 자동 생성
- 통과 항목만 dispatch 진행

### FR-03: RETRO-12 정책 → 게이트 조건 매핑
- RETRO-12의 10개 수동 확인 포인트를 코드 기반 체크 조건으로 변환
- 최소 구현 대상 (우선순위 매트릭스 상위 3개):
  1. `pre_flight_passed`: pre-flight 체크 통과 여부
  2. `has_assignee`: 담당 조직(assigned_dept) 명시 여부
  3. `description_complete`: 설명 50자 이상 여부

### FR-04: 게이트 결과 로깅
- GoalTracker `context_db`에 `policy_gate_log` 테이블 기록
- 필드: `task_id`, `checked_at`, `passed`, `failed_policies`, `remediation_created`

### FR-05: Remediation ACTION 자동 생성
- 미통과 시 GoalTracker에 신규 ActionItem 자동 등록
- `tags: ["auto-remediation", 원본_task_id]`
- 담당: 원본 태스크와 동일 org_id

---

## 5. 비기능 요구사항

| 항목 | 기준 |
|------|------|
| 지연 | PolicyGate.check() 1건 ≤ 10ms |
| 가용성 | 체크 실패(예외) 시 PASS 처리 (fail-open) — 게이트 오류가 실행을 막지 않음 |
| 호환성 | 기존 retro_backfill.py, daily_retro.py 코드 변경 없이 연동 |
| 테스트 | `tests/unit/test_policy_gate.py` — 10개 정책 조건 각 단위 테스트 |

---

## 6. 데이터 플로우

```
[daily_retro.py] 회고 실행
  └─ _register_retro_actions(md_content)
       └─ auto_register_from_report() → ActionItem 6개
            └─ registrar.register_from_event() → goal_ids
                 └─ loop_runner.run_meeting_cycle()
                      └─ _do_dispatch() [← 여기에 게이트 삽입]
                           ├─ PolicyGate.check(item) → PolicyCheckResult
                           │    ├─ PASS → dispatch 진행
                           │    └─ FAIL → skip + remediation ACTION 등록
                           └─ dispatch_func(passed_task_ids)
```

---

## 7. 수용 기준 (Acceptance Criteria)

| # | 조건 | 검증 방법 |
|---|------|-----------|
| AC-01 | pre-flight 미완료 ACTION은 dispatch 차단됨 | `test_policy_gate.py::test_preflight_blocks_dispatch` |
| AC-02 | 차단된 ACTION에 대해 remediation ActionItem 자동 생성됨 | GoalTracker DB 조회 |
| AC-03 | `policy_gate_log` 테이블에 체크 결과 기록됨 | DB 직접 확인 |
| AC-04 | PolicyGate 예외 시 PASS 처리 (fail-open) | 예외 주입 테스트 |
| AC-05 | 기존 dry-run 테스트 (`retro_backfill.py --dry-run`) 그대로 통과 | CI 자동 검증 |

---

## 8. 구현 위임 (COLLAB 지시)

### 기획실 완료 항목
- [x] 현행 파이프라인 구조 분석
- [x] PRD v1.0 작성 (본 문서)
- [x] 버그 식별: `run_meeting_cycle()` action_items 미전달 → `담당: 미지정`
- [x] retro_backfill.py 드라이런 검증

### 개발실 구현 요청 항목
1. **버그 수정**: `retro_backfill.py` `_run_loop_cycle()`에 `action_items=action_items` 파라미터 전달
2. **PolicyGate 구현**: `goal_tracker/policy_gate.py` — FR-01~05
3. **LoopRunner 연동**: `_do_dispatch()` 진입 전 PolicyGate 삽입
4. **단위 테스트**: `tests/unit/test_policy_gate.py`
5. **실 실행**: `python scripts/retro_backfill.py` (--dry-run 없이)

---

## 9. 의존성

| 항목 | 담당 | 상태 |
|------|------|------|
| RETRO-12 자동화 정책 스펙 | 기획실 | ✅ 완료 (`docs/RETRO-12-automation-policy-spec.md`) |
| pre-flight 체크 구현 | 개발실 (RETRO-01) | ✅ 완료 |
| GoalTracker DI 버그 수정 | 기획실/개발실 (RETRO-21) | ✅ 완료 (commit 5dfa955) |
| PolicyGate 구현 | 개발실 | 🔲 이 PRD 기반 신규 |

---

*PRD 자동 생성: aiorg_product_bot / 2026-03-31*
