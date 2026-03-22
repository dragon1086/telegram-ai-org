---
name: safe-modify
description: >
  실패 감지 코드(failure-detect) 및 고위험 코드 수정 시 부작용을 최소화하는 안전 개발 방법론 스킬.
  2026년 3월 기준 업계 Best Practice(Google/Shopify/Netflix/OWASP)를 녹인 수정 안전 체크리스트.
  Triggers: 'safe modify', '안전 수정', 'failure detect 수정', 'safe code change',
  'scope restriction', '스코프 제한', '부작용 최소화', 'failure-detect-llm 수정',
  '실패감지 코드 변경', '고위험 코드 수정', 'minimal footprint'
---

# safe-modify — 안전 코드 수정 스킬

실패 감지 / 고위험 경로 코드를 수정할 때 부작용을 최소화하기 위한 표준 절차.
아래 **6개 방법론**을 순서대로 적용한다.

---

## 0. 수정 전 필수 확인 (Pre-flight Checklist)

```
[ ] 현재 테스트 커버리지 확인 → pytest --cov 실행
[ ] 수정 대상 함수의 CRAP 점수 추정 (복잡도 × 미커버리지)
[ ] 변경 범위(Scope) 명시: 파일명, 함수명, 라인 범위
[ ] 롤백 계획 확인: git stash 또는 feature flag OFF 경로 존재하는가
[ ] quality-gate PASS 상태인가 (수정 전 기준선 확보)
```

---

## 1. Defensive Programming / Fail-Safe Defaults

> **원칙**: 코드는 예상치 못한 입력·상태에서도 안전한 기본값으로 복귀해야 한다.

### 규칙

- **Guard Clause 우선**: 함수 진입 시 조건 불만족이면 즉시 early return (중첩 if 금지)
- **Fail-Safe Default**: 불확실 상황에서는 보수적 판정 반환 (실패보다 "불확실"이 낫다)
- **Precondition Assert**: 함수 입력 검증은 함수 상단에 집중

```python
# ✅ Good — Guard Clause + Fail-Safe Default
def detect_failure(scan_diff: dict) -> dict:
    if not scan_diff:                           # Guard: 입력 검증
        return {"is_failure": False, "reason": "no_data", "confidence": 0.0}
    if scan_diff.get("status") == "error":      # Guard: 에러 상태
        return {"is_failure": False, "reason": "pipeline_error", "confidence": 0.0}
    # 이후 로직

# ❌ Bad — 중첩 if, 예외 무시
def detect_failure(scan_diff):
    if scan_diff:
        if scan_diff["status"] != "error":
            try:
                ...
            except:
                pass  # 예외 삼킴
```

```typescript
// TypeScript: never 타입으로 exhaustive check
function handleStatus(status: "improved" | "regressed" | "unchanged"): string {
  switch (status) {
    case "improved": return "pass";
    case "regressed": return "fail";
    case "unchanged": return "warn";
    default:
      const _exhaustive: never = status;  // 컴파일 타임 안전망
      return "unknown";
  }
}
```

### 실패 감지 코드 전용 규칙

- `FailureCondition.check()` 수정 시: **fallback 경로가 항상 존재**해야 한다
- LLM 호출 실패 시 반드시 `algorithm_verdict`로 fallback (failure-detect-llm 기존 설계 유지)
- confidence < 0.60 구간에서는 절대 LLM 단독 판정 금지

---

## 2. Minimal Footprint / Scope Restriction

> **원칙**: 변경은 목적 달성에 필요한 최소 범위로 제한한다.

### 규칙

- **파일당 변경 제한**: 실패 감지 관련 수정은 1 PR당 최대 3개 파일
- **함수 분리**: 기존 함수를 수정하기 전에 새 함수로 분리한 뒤 교체 (Strangler Fig 패턴)
- **사이드 이펙트 금지**: 수정 함수는 I/O·DB·외부 API 호출을 새로 추가하지 않는다
- **시그니처 유지**: public 함수의 매개변수·반환 타입 변경 금지 (내부 로직만 수정)

```python
# Strangler Fig 패턴 — 기존 로직 보존하며 신규 로직 병행
def check_failure_v2(scan_diff: dict) -> bool:
    """신규 로직 (검증 중)"""
    ...

def check_failure(scan_diff: dict) -> bool:
    """기존 함수 — v2로 점진 교체"""
    if FEATURE_FLAGS.get("failure_check_v2"):
        return check_failure_v2(scan_diff)
    return _legacy_check(scan_diff)  # 기존 로직 보존
```

### 스코프 체크리스트

```
[ ] 변경하는 파일: _____ (3개 이하인가?)
[ ] 기존 public API 시그니처 변경 없음
[ ] 새로운 I/O 호출 없음 (DB/외부API/파일쓰기)
[ ] 타깃 함수 외 리팩터링 없음
```

---

## 3. Feature Flags / Guard Clause

> **원칙**: 새 실패 감지 로직은 Feature Flag 뒤에 감추고 단계적으로 롤아웃한다.

### Feature Flag 적용 기준

| 변경 규모 | Feature Flag 필요 여부 |
|-----------|----------------------|
| 버그픽스 (동작 보존) | 불필요 |
| 판정 로직 변경 | **필수** |
| 새 confidence 임계값 | **필수** |
| 새 외부 의존성 추가 | **필수** |

### 구현 패턴

```python
# orchestration.yaml 또는 환경변수 기반 Feature Flag
FEATURE_FLAGS = {
    "failure_check_v2": os.getenv("FF_FAILURE_CHECK_V2", "false").lower() == "true",
    "llm_override_enabled": os.getenv("FF_LLM_OVERRIDE", "true").lower() == "true",
}

def get_feature_flag(flag_name: str, default: bool = False) -> bool:
    """Fail-safe: 플래그 조회 실패 시 보수적 기본값 반환"""
    return FEATURE_FLAGS.get(flag_name, default)
```

### Guard Clause 필수 적용 위치

실패 감지 함수 진입 시 다음 순서로 Guard Clause 적용:
1. 입력 데이터 null/empty 체크
2. 에러 상태 우선 처리
3. rate_limit 초과 여부 확인
4. 이후 핵심 로직 진행

### Cyclomatic Complexity 제한

- 실패 감지 함수의 cyclomatic complexity ≤ 10
- 분기가 10을 넘으면 서브함수로 분리

---

## 4. Idempotency 보장

> **원칙**: 동일한 실패 감지 요청을 여러 번 실행해도 동일한 결과가 나와야 한다.

### 규칙

- **순수 함수 지향**: `detect_failure(scan_diff)` → 같은 입력이면 반드시 같은 출력
- **상태 기반 판정 주의**: 외부 상태(DB, 캐시)에 의존하면 멱등성이 깨짐 → 입력에 상태를 포함시키거나 명시적으로 문서화
- **재시도 안전**: 실패 감지 함수는 재시도 시 side effect 없어야 함

```python
# ✅ Idempotent — 동일 입력 → 동일 출력
def check_failure(scan_diff: dict, algorithm_verdict: dict) -> dict:
    # 외부 상태 참조 없음, 순수 계산만 수행
    improvement_rate = scan_diff.get("improvement_rate", 0.0)
    if improvement_rate < 0.5:
        return {"is_failure": True, "reason": "low_improvement"}
    return {"is_failure": False, "reason": "sufficient_improvement"}

# ❌ Non-idempotent — 같은 입력이어도 호출 시점에 따라 결과 다름
def check_failure(scan_diff: dict) -> dict:
    now = datetime.now()  # 시간 의존 → 멱등성 파괴
    recent_count = db.count_failures_today(scan_diff["run_id"])  # 외부 상태 의존
    ...
```

### Idempotency Key 패턴 (상태 저장이 필요한 경우)

```python
def record_failure_verdict(run_id: str, verdict: dict) -> bool:
    """멱등성 보장: 동일 run_id 재호출 시 기존 결과 반환"""
    existing = db.get_verdict(run_id)
    if existing:
        return existing  # 중복 처리 방지
    return db.save_verdict(run_id, verdict)
```

---

## 5. CRAP 점수 기반 우선순위 결정

> **원칙**: CRAP(Change Risk Anti-Patterns) 점수가 높은 코드는 수정 전 반드시 테스트를 추가한다.

### CRAP 점수 계산

```
CRAP = cyclomatic_complexity² × (1 - test_coverage)²
```

| CRAP 점수 | 위험도 | 조치 |
|-----------|--------|------|
| < 5 | 낮음 🟢 | 직접 수정 가능 |
| 5~30 | 중간 🟡 | 커버리지 70% 이상 확보 후 수정 |
| > 30 | 높음 🔴 | **테스트 먼저 추가, 함수 분리 후 수정** |

### 실패 감지 코드 CRAP 확인 방법

```bash
# cyclomatic complexity 측정
.venv/bin/python -m radon cc core/failure_condition.py -a

# 커버리지 확인
.venv/bin/pytest --cov=core.failure_condition --cov-report=term-missing -q
```

### 리팩터링 우선순위 규칙

1. CRAP > 30이면 수정 금지 → 테스트 추가 먼저
2. 함수가 20줄 초과이면 서브함수 분리 후 수정
3. 중복 로직이 있으면 추출 후 수정

---

## 6. 산업 표준 체크리스트 (Google/Shopify/Netflix)

> **근거**: Google Engineering Practices, Shopify Production Checklist, Netflix Chaos Engineering 원칙에서 공통 추출

### Google Engineering Practices 채용 항목

- [ ] **2-reviewer rule**: 실패 감지 판정 로직 변경 시 최소 2명 리뷰 (AI 에이전트 맥락: PM + 개발실 교차 검토)
- [ ] **테스트 없는 코드 머지 금지**: 새 판정 경로에는 반드시 테스트 추가
- [ ] **Readability**: 판정 근거가 코드에서 즉시 읽혀야 함 (주석 필수)

### Shopify Production Checklist 채용 항목

- [ ] **Dark Launch**: 새 판정 로직은 결과를 로그로만 기록하며 실제 판정에 미반영하여 검증
- [ ] **Rollback 경로**: feature flag OFF 또는 git revert로 30초 내 롤백 가능한가
- [ ] **Alert 설정**: 새 로직 배포 후 에러율/판정 변화율 모니터링 알림 설정

### Netflix Chaos Engineering 채용 항목

- [ ] **실패 주입 테스트**: 실패 감지 코드 수정 후 의도적 실패 시나리오로 테스트
  ```python
  # 실패 주입 예시: scan_diff에 극단값 주입
  assert detect_failure({"status": "error", "new_count": 999})["is_failure"] == False
  assert detect_failure({})["is_failure"] == False  # empty input
  assert detect_failure(None)  # None input도 안전 처리
  ```
- [ ] **Blast Radius 최소화**: 실패 감지 오판이 미치는 범위를 명시하고 격리

---

## 수정 완료 후 검증 순서

```
1. pytest -q (회귀 테스트)
2. pytest --cov=<변경모듈> (커버리지 확인)
3. quality-gate 스킬 실행
4. 실패 주입 테스트 (경계값, null, error 상태)
5. feature flag OFF 상태 동작 확인 (기존 로직 보존 검증)
6. engineering-review 스킬 실행
```

---

## 기법 간 시너지 조합

| 조합 | 시너지 |
|------|--------|
| Feature Flag + Idempotency | 새 로직을 켜도/꺼도 동일 입력 → 동일 출력 보장 |
| Minimal Footprint + Guard Clause | 범위를 좁히고 진입 조건을 명확히 → 변경 파급 최소 |
| CRAP 측정 + Defensive Programming | 복잡도 높은 코드를 먼저 단순화 → 안전한 수정 기반 확보 |
| Dark Launch + Idempotency | 신규 로직 실험 중에도 멱등성 유지 → 안전한 A/B |

---

## ⚠️ 절대 금지 (Anti-patterns)

- **예외 삼킴 금지**: `except: pass` — 실패 감지가 스스로 실패를 숨기면 안 됨
- **전역 상태 변경 금지**: 실패 감지 함수가 모듈 레벨 변수를 수정하면 멱등성 파괴
- **테스트 없는 confidence 임계값 변경 금지**: 0.85, 0.60 등 판정 기준 숫자 변경은 반드시 테스트 먼저
- **한 번에 여러 판정 경로 수정 금지**: 한 PR에서 하나의 판정 경로만 수정
- **fallback 제거 금지**: LLM 호출 실패 시 알고리즘 fallback은 영구 보존
