# safe-modify — Gotchas

실패 감지 및 고위험 코드 수정 시 실제 발생한 실수와 해결책.

---

## Gotcha 1: CRAP 점수 확인 없이 confidence 임계값 변경

**상황**: `failure-detect-llm`의 `confidence >= 0.85` 임계값을 `0.90`으로 올리면 더 안전할 것이라 판단해 바로 수정.

**증상**: 경계 케이스(confidence 0.86~0.89)에서 기존에 잘 동작하던 LLM 판정이 모두 알고리즘으로 fallback → 실패 미감지 케이스 발생.

**해결**:
1. 임계값 변경 전 `pytest --cov=core.failure_condition` 실행 → 경계 케이스 커버리지 확인
2. 기존 판정 케이스 테스트가 없으면 **테스트 먼저 추가**, 그 후 수정
3. Feature Flag(`FF_CONFIDENCE_THRESHOLD_V2`)로 감싸고 Dark Launch로 검증 후 전환

---

## Gotcha 2: `except: pass`로 예외 삼킴 — 실패 감지 자체가 실패

**상황**: LLM API 호출 실패 시 로그 노이즈를 줄이기 위해 `except Exception: pass` 처리.

**증상**: Gemini API 타임아웃 발생 → 예외 삼킴 → `is_failure` 반환 없이 함수 종료 → 호출부 `None` 참조 오류 → 전체 파이프라인 중단.

**해결**:
```python
# ❌ Bad
try:
    result = call_gemini(prompt)
except Exception:
    pass  # 예외 삼킴 — 절대 금지

# ✅ Good — Fail-Safe Default 반환
try:
    result = call_gemini(prompt)
except Exception as e:
    logger.warning(f"LLM call failed, falling back to algorithm: {e}")
    return algorithm_verdict  # fallback 경로 항상 유지
```

---

## Gotcha 3: Minimal Footprint 위반 — 연관 없는 코드 리팩터링

**상황**: `FailureCondition.check()` 버그 수정 중 옆에 있는 `ScanDiff.compute()` 코드가 지저분해 보여 함께 리팩터링.

**증상**: `ScanDiff.compute()`의 동작이 미묘하게 바뀌어 다른 파이프라인에서 회귀 발생. git blame이 복잡해져 원인 추적 어려움.

**해결**:
- 수정 대상 함수 외에는 **리팩터링 금지**
- "지저분해 보인다" → TODO 주석 남기고 별도 PR로 분리
- PR당 파일 3개 이하 원칙 준수

---

## Gotcha 4: Feature Flag 없이 판정 로직 직접 교체

**상황**: 새 failure detection 알고리즘이 더 정확하다고 판단해 기존 로직을 바로 교체.

**증상**: 새 알고리즘의 엣지케이스 미처리로 프로덕션에서 false-positive 급증 → 롤백 필요. 단순 `git revert`로는 30초 내 복구 불가 (다른 변경과 얽힘).

**해결**:
```python
# Feature Flag로 신규 로직 격리
if get_feature_flag("failure_check_v2", default=False):
    return check_failure_v2(scan_diff)
return check_failure_legacy(scan_diff)
```
- Feature Flag OFF → 즉시 롤백 (코드 배포 없이 환경변수만 변경)
- 판정 로직 변경 시 Feature Flag 필수 (테이블 참조: safe-modify Section 3)

---

## Gotcha 5: Idempotency 파괴 — 외부 상태 의존 추가

**상황**: "이번 실행 전 얼마나 많은 실패가 있었는지"를 고려한 가중치 로직 추가를 위해 `db.count_failures_today()` 호출 삽입.

**증상**: 동일 `scan_diff` 입력이어도 호출 시점(오전/오후)에 따라 판정 결과가 달라짐 → 재시도 시 다른 결과 → 파이프라인 불안정.

**해결**:
- 외부 상태가 필요하면 **입력 파라미터로 명시적 전달**
  ```python
  # ❌ Bad — 내부에서 외부 상태 참조
  def check_failure(scan_diff):
      count = db.count_failures_today(scan_diff["run_id"])
      ...

  # ✅ Good — 호출부에서 상태 주입
  def check_failure(scan_diff: dict, context: dict) -> dict:
      count = context.get("failures_today", 0)
      ...
  ```
- 순수 함수(pure function) 설계 원칙 유지

---

## Gotcha 6: safe-modify 절차 건너뜀 — "작은 변경이라 괜찮다"

**상황**: 로그 문자열 하나 수정이라 safe-modify 절차를 skip.

**증상**: 로그 포맷 변경으로 로그 파서가 failure를 감지 못하게 됨 (파서가 특정 문자열 패턴에 의존했음). 테스트 없어 회귀 미감지.

**해결**:
- **실패 감지 코드 수정은 "작은 변경"이 없다** — 모든 변경에 Pre-flight Checklist 적용
- 로그 포맷도 테스트 대상 (파서 의존성 확인)
- quality-gate는 최소한 항상 실행

---

## Gotcha 7: `override_algorithm: true` 범위 확장

**상황**: LLM이 알고리즘보다 더 정확하다고 판단해 `override_algorithm` 반환 조건을 낮춤 (confidence 0.60 → 0.50으로 하향).

**증상**: confidence 0.50~0.60 구간의 불안정한 LLM 판정이 알고리즘을 override → false-negative 증가 → 실제 실패를 놓침.

**해결**:
- `override_algorithm: true` 조건은 **확장 금지** (더 많은 케이스에서 LLM이 알고리즘을 오버라이드 하게 만들면 안 됨)
- confidence 임계값 변경 시 반드시 테스트 데이터셋으로 검증 후 결정
- 변경 전 현재 판정 분포 통계를 먼저 확인
