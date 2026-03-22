# 안전 코드 수정 방법론 리서치 보고서
**조사 기준일**: 2026-03-22 | **작성**: aiorg_research_bot (PM 조율)

---

## 1. Executive Summary

**조사 목적**: 실패 감지(failure-detect) 코드 수정 시 부작용을 최소화하기 위한 2026년 최신 개발 방법론 조사 및 스킬 파일 반영.

**주요 발견 3줄 요약**:
1. 2026년 현재 업계 Top 3 접근법은 **Feature Flags + 단계적 롤아웃**, **Guard Clause 기반 Defensive Programming**, **CRAP 점수 기반 리팩터링 우선순위 결정**으로 수렴한다.
2. Google/Shopify/Netflix 세 곳 모두 공통적으로 "변경 범위 최소화 + 실패 주입 테스트 + 즉시 롤백 가능 설계"를 핵심으로 삼는다.
3. 실패 감지 코드에서 가장 흔한 부작용 원인은 **예외 삼킴(silent exception)**, **전역 상태 의존**, **테스트 없는 임계값 변경** 세 가지다.

---

## 2. 주제별 상세 요약

### 2-1. Defensive Programming / Fail-Safe Defaults

**개념 정의**
방어적 프로그래밍(Defensive Programming)은 예상치 못한 입력·상태에서도 프로그램이 안전하게 동작하도록 설계하는 패러다임. Fail-Safe Default는 실패 시 가장 보수적인 기본값으로 복귀하는 원칙이다.

**부작용 최소화 연관성**
실패 감지 코드가 잘못된 입력(null, empty, error 상태)을 받을 때 예외를 삼키거나 잘못된 판정을 반환하면, 시스템 전체가 무음 실패(silent failure)에 빠진다. Guard Clause + Fail-Safe Default가 이를 차단한다.

**실무 적용 방법**

```python
# Python — Guard Clause + Fail-Safe Default
def detect_failure(scan_diff: dict | None) -> dict:
    if not scan_diff:
        return {"is_failure": False, "reason": "no_data", "confidence": 0.0}
    if scan_diff.get("status") == "error":
        return {"is_failure": False, "reason": "pipeline_error", "confidence": 0.0}
    # 이후 실제 판정 로직
```

```typescript
// TypeScript — never 타입으로 컴파일 타임 안전망
function handleStatus(s: "improved" | "regressed" | "unchanged"): string {
  switch (s) {
    case "improved": return "pass";
    case "regressed": return "fail";
    case "unchanged": return "warn";
    default:
      const _: never = s;  // 처리되지 않은 케이스 컴파일 오류
      return "unknown";
  }
}
```

**참고 소스**
- [Defensive Programming — Wikipedia](https://en.wikipedia.org/wiki/Defensive_programming)
- [Defensive Programming in Python — Pluralsight](https://www.pluralsight.com/resources/blog/guides/defensive-programming-in-python)
- [Avoid Errors with Defensive Coding in TypeScript](https://typescript.tv/best-practices/avoid-errors-with-defensive-coding-in-typescript/)

---

### 2-2. Minimal Footprint / Scope Restriction

**개념 정의**
변경(Change)의 영향 반경(blast radius)을 최소화하는 설계 원칙. 단일 책임 원칙(SRP, Single Responsibility Principle)의 실천적 확장이며, Strangler Fig 패턴(기존 로직을 보존하며 신규 로직을 점진적으로 교체)이 대표 구현 패턴이다.

**부작용 최소화 연관성**
변경 범위가 클수록 예상 밖 상호작용(side effect)의 확률이 기하급수적으로 증가한다. Minimal Footprint는 변경 표면적 자체를 줄여 문제 발생 공간을 사전에 차단한다.

**실무 적용 방법**

| 규칙 | 기준 |
|------|------|
| PR당 파일 수 | 실패 감지 관련 수정은 최대 3개 파일 |
| 함수 교체 방식 | 새 함수 분리 → Feature Flag 교체 → 구 함수 제거 (Strangler Fig) |
| 시그니처 보존 | public API 매개변수·반환 타입 변경 금지 |
| 새 I/O 금지 | 수정 함수에서 새로운 DB/외부API 호출 추가 금지 |

**Strangler Fig 패턴 예시**

```python
def check_failure(scan_diff: dict) -> bool:
    """기존 함수 — 점진적으로 v2로 교체"""
    if FEATURE_FLAGS.get("failure_check_v2"):
        return check_failure_v2(scan_diff)  # 신규 로직
    return _legacy_check(scan_diff)         # 기존 로직 보존
```

**참고 소스**
- [Strangler Fig Pattern — Martin Fowler](https://martinfowler.com/bliki/StranglerFigApplication.html)
- [Feature Flag Best Practices — Flagsmith](https://www.flagsmith.com/blog/feature-flags-best-practices)

---

### 2-3. Feature Flags / Guard Clause

**개념 정의**
Feature Flag(Feature Toggle)는 코드 배포와 기능 활성화를 분리하는 기법. Guard Clause는 함수 진입 시 조건 불만족 케이스를 즉시 early return하여 중첩 분기를 제거하는 패턴이다.

**부작용 최소화 연관성**
- Feature Flag: 신규 판정 로직을 프로덕션에 배포하면서도 OFF 상태로 유지 → 안전한 A/B, 즉시 롤백 가능
- Guard Clause: cyclomatic complexity를 낮춰 수정 시 분기 오류 가능성 감소

**2026년 주요 Feature Flag 플랫폼 비교**

| 플랫폼 | 특징 | 오픈소스 |
|--------|------|----------|
| LaunchDarkly | 엔터프라이즈 표준, SDKs 최다 | ❌ |
| Unleash | 셀프호스팅 가능, 보안 친화 | ✅ |
| GrowthBook | A/B 테스트 통합 | ✅ |
| 환경변수 기반 | 이 프로젝트 권장 (의존성 최소) | — |

> **이 프로젝트 권장**: 외부 SaaS 의존 없이 `os.getenv("FF_XXX", "false")` 패턴으로 충분. 플랫폼 도입은 조직 규모 확대 시 검토.

**Guard Clause Cyclomatic Complexity 효과**

```python
# ❌ Before: complexity 6
def check(diff):
    if diff:
        if diff.get("status") != "error":
            if diff.get("new_count", 0) >= 3:
                if diff.get("improvement_rate", 1.0) < 0.5:
                    return True
    return False

# ✅ After Guard Clause: complexity 4
def check(diff):
    if not diff: return False
    if diff.get("status") == "error": return False
    if diff.get("new_count", 0) < 3: return False
    return diff.get("improvement_rate", 1.0) < 0.5
```

**참고 소스**
- [Feature Flags Best Practices 2026 — tggl.io](https://tggl.io/blog/unlock-the-power-of-feature-flags-6-best-practices-you-need-in-2026)
- [Feature Flag Security — Unleash](https://www.getunleash.io/blog/feature-flag-security-best-practices)
- [11 Principles for Feature Flag Systems — Unleash Docs](https://docs.getunleash.io/topics/feature-flags/feature-flag-best-practices)

---

### 2-4. Idempotency 보장

**개념 정의**
동일한 연산을 여러 번 실행해도 결과가 항상 같은 성질. REST API에서는 PUT/DELETE, 메시지 큐에서는 at-least-once 처리, DB에서는 UPSERT가 대표 패턴이다.

**부작용 최소화 연관성**
실패 감지 함수가 비멱등(non-idempotent)이면 재시도 시 판정이 달라지거나 side effect가 누적된다. 특히 LLM 호출을 포함한 실패 감지 스킬에서 멱등성 보장은 신뢰성의 핵심이다.

**실무 적용 패턴**

```python
# 멱등성 체크 패턴 — Idempotency Key
def record_failure_verdict(run_id: str, verdict: dict) -> dict:
    existing = db.get_verdict(run_id)
    if existing:
        return existing           # 중복 호출: 기존 결과 반환
    return db.save_verdict(run_id, verdict)  # 최초 호출: 저장

# 순수 함수 — 외부 상태 없이 항상 동일 결과
def compute_failure(scan_diff: dict) -> bool:
    return scan_diff.get("improvement_rate", 1.0) < 0.5  # 순수 계산만
```

**At-least-once vs Exactly-once**

| 전략 | 적합한 상황 | 실패 감지 적용 |
|------|-------------|---------------|
| At-least-once | 중복 처리 무해한 경우 | `check_failure()` — 멱등 함수면 OK |
| Exactly-once | 상태 변경 수반 | `record_verdict()` — Idempotency Key 필수 |

**참고 소스**
- [Mastering Idempotency — ByteByteGo](https://blog.bytebytego.com/p/mastering-idempotency-building-reliable)
- [Idempotency in Microservices — OneUptime](https://oneuptime.com/blog/post/2026-01-24-idempotency-in-microservices/view)
- [Idempotent Consumer Pattern — microservices.io](https://microservices.io/patterns/communication-style/idempotent-consumer.html)

---

### 2-5. CRAP 점수 (Change Risk Anti-Patterns) 회피

**개념 정의**
CRAP(Change Risk Anti-Patterns) 지수는 코드의 변경 위험도를 수치화한 지표.

```
CRAP = cyclomatic_complexity² × (1 - test_coverage)²
```

복잡도가 높고 테스트 커버리지가 낮을수록 CRAP 점수가 폭발적으로 증가한다.

**부작용 최소화 연관성**
CRAP 점수가 높은 함수는 수정 시 의도치 않은 케이스를 깨뜨릴 확률이 높다. 수정 전 CRAP 측정 → 테스트 추가 → 수정의 순서가 안전하다.

**CRAP 점수 기준표**

| CRAP 점수 | 위험도 | 수정 조건 |
|-----------|--------|-----------|
| < 5 | 낮음 🟢 | 직접 수정 가능 |
| 5~30 | 중간 🟡 | 커버리지 70% 이상 확보 후 수정 |
| > 30 | 높음 🔴 | 테스트 먼저 추가, 함수 분리 후 수정 |

**측정 방법**

```bash
# cyclomatic complexity (radon 사용)
.venv/bin/python -m radon cc core/failure_condition.py -a -s

# 커버리지
.venv/bin/pytest --cov=core.failure_condition --cov-report=term-missing -q
```

**흔한 CRAP 유발 코드 냄새**
- 10개 이상 분기를 가진 단일 함수
- 테스트 없는 예외 처리 경로
- 전역 변수 참조 + 조건 분기 조합
- 중첩 try/except 블록

**참고 소스**
- [CRAP Metric — Alberto Savoia & Charles Sussman](https://www.artima.com/weblogs/viewpost.jsp?thread=215899)
- [Refactoring — Martin Fowler](https://martinfowler.com/books/refactoring.html)

---

### 2-6. 2026년 산업 표준 가이드라인 (Google/Shopify/Netflix)

#### Google Engineering Practices

**핵심 원칙**
- 코드 리뷰 없이 머지 불가 (No merge without review)
- 테스트 없는 코드는 미완성 코드
- 모든 변경은 최소 단위(atomic change)로 유지

**실패 감지 코드에 채용**
- 판정 로직 변경 시 PM + 개발실 교차 검토 (2-reviewer rule)
- 새 판정 경로에 반드시 유닛 테스트 추가

**참고**: [Google Engineering Practices](https://google.github.io/eng-practices/)

#### Shopify Production Checklist 원칙

**핵심 원칙**
- Dark Launch: 새 기능을 먼저 로그만 기록하며 검증
- 30초 내 롤백 가능한 설계
- 배포 후 에러율 알림 설정

**실패 감지 코드에 채용**
- 새 confidence 임계값 적용 전 Dark Launch로 판정 결과 비교
- Feature Flag OFF로 즉시 구 로직 복귀 가능하도록 설계

#### Netflix Chaos Engineering

**핵심 원칙**
- 시스템은 언제든 실패한다고 가정 (Embrace failure)
- 실패를 먼저 주입하여 복원력 사전 검증
- 최소 "steady state" 확인 후 카오스 실험 진행

**실패 감지 코드에 채용**
- 수정 후 의도적 실패 시나리오(null input, API 장애, 극단값) 테스트
- Blast Radius 명시: 실패 감지 오판이 영향을 미치는 컴포넌트 목록 작성

**참고**
- [Netflix Chaos Monkey](https://netflix.github.io/chaosmonkey/)
- [Google Chaos Engineering Guide](https://cloud.google.com/blog/products/devops-sre/getting-started-with-chaos-engineering)

---

## 3. 비교 분석 결과

### 3-1. 기법 간 시너지 다이어그램

```
┌─────────────────────────────────────────────────────┐
│              실패 감지 코드 수정 안전 체계              │
├─────────────────────────────────────────────────────┤
│                                                       │
│  [수정 전]                                            │
│  CRAP 점수 측정 ──→ 테스트 추가 ──→ 기준선 확보        │
│         │                                             │
│         ▼                                             │
│  [수정 중]                                            │
│  Minimal Footprint ──┬──→ Guard Clause               │
│                       │         │                    │
│  Feature Flag ────────┘         ▼                    │
│         │              Defensive Programming         │
│         │                       │                    │
│         └──────────→ Idempotency 검증                │
│                                                       │
│  [수정 후]                                            │
│  실패 주입 테스트 ──→ 품질 게이트 ──→ 롤백 준비 완료    │
│  (Chaos Engineering)   (quality-gate)                │
└─────────────────────────────────────────────────────┘
```

### 3-2. 도입 난이도 × 효과 크기 매트릭스

```
효과 크기
  높음 │ Feature Flags    │ CRAP 점수 기반    │
       │ (중간 난이도)     │ 리팩터링          │
       │                  │ (높은 난이도)     │
  ─────┼──────────────────┼──────────────────┤
  낮음 │ Guard Clause     │ Idempotency Key  │
       │ (낮은 난이도)     │ (중간 난이도)     │
       └──────────────────┴──────────────────
         낮음                 높음
                         도입 난이도
```

**즉시 시작 권장 (낮은 난이도, 높은 효과)**:
1. Guard Clause + Defensive Programming — 코드 스타일 변경만으로 즉시 적용
2. Feature Flag (환경변수 기반) — 외부 의존성 없이 `os.getenv()` 패턴으로 시작
3. CRAP 점수 측정 자동화 (`radon` 추가) — CI 파이프라인에 측정 추가

### 3-3. 업계 Top 3 접근법 (2026년 기준)

| 순위 | 접근법 | 채택 근거 |
|------|--------|-----------|
| **1위** | Feature Flags + 단계적 롤아웃 | Google/Shopify/Netflix 모두 사용. 코드 변경 없이 즉시 롤백 가능 |
| **2위** | Guard Clause 기반 Defensive Programming | 언어 무관, 즉시 적용 가능, cyclomatic complexity 직접 감소 |
| **3위** | CRAP 지수 기반 수정 우선순위 | CI 통합 후 자동 위험도 측정으로 고위험 수정 사전 차단 |

### 3-4. 공통 핵심 원칙 5개

1. **최소 변경 단위 (Atomic Change)**: 한 번에 하나의 동작만 변경
2. **즉시 롤백 가능 설계 (Fast Rollback)**: 변경 전 항상 복귀 경로 확보
3. **실패 먼저 테스트 (Fail-First Testing)**: 정상 케이스보다 실패 케이스를 먼저 작성
4. **투명한 실패 (Transparent Failure)**: 예외를 삼키지 않고 로그·지표로 노출
5. **Dark Launch 검증 (Shadow Mode)**: 새 로직은 결과를 숨기며 먼저 실행해 검증

---

## 4. 2026년 현재 권장 실천 가이드

### 적용 순서 (이 프로젝트 기준)

```
Step 1 (즉시): Guard Clause 리팩터링
  → 기존 failure-detect 함수의 중첩 if → early return 패턴 전환

Step 2 (이번 주): CRAP 측정 자동화
  → radon 설치 + pytest --cov 연동
  → quality-gate 스킬에 CRAP 임계값(> 30) 경고 추가

Step 3 (이번 달): Feature Flag 체계 수립
  → 환경변수 기반 FF 패턴 표준화
  → 판정 로직 변경 PR 템플릿에 FF 필드 추가

Step 4 (분기): Chaos Test 스크립트 작성
  → null/empty/error 입력 실패 주입 테스트 suite 구축
```

### 실무 적용 체크리스트

**수정 전**
```
[ ] CRAP 점수 확인 (> 30이면 테스트 먼저)
[ ] 변경 파일 목록 명시 (3개 이하인가?)
[ ] 롤백 경로 확인 (feature flag OFF or git stash)
[ ] quality-gate PASS 기준선 확인
```

**수정 중**
```
[ ] Guard Clause 우선 적용
[ ] 판정 로직 변경 시 Feature Flag 적용
[ ] 순수 함수 유지 (외부 상태 의존 없음)
[ ] 기존 public API 시그니처 유지
[ ] 예외 처리: except: pass 금지
```

**수정 후**
```
[ ] pytest -q (회귀 테스트 PASS)
[ ] pytest --cov (커버리지 70% 이상)
[ ] 실패 주입 테스트: null/empty/error 케이스
[ ] Feature Flag OFF 상태 동작 확인
[ ] quality-gate 스킬 실행
[ ] engineering-review 스킬 실행 (safe-modify 체크리스트 포함)
```

---

## 5. 한계 및 추가 조사 필요 항목

| 항목 | 현황 | 추가 조사 필요 이유 |
|------|------|-------------------|
| CRAP 자동 측정 CI 통합 | radon 수동 실행 | quality-gate 훅에 자동 통합 방법 확인 필요 |
| Feature Flag 플랫폼 도입 | 환경변수 기반 권장 | 조직 규모 확대 시 LaunchDarkly/Unleash 비교 평가 필요 |
| LLM 기반 코드 리뷰 (AI 코드리뷰) | engineering-review 수동 | Claude/Gemini API 기반 자동 CRAP 감지 스킬 가능성 |
| 카오스 테스트 자동화 | 수동 실패 주입 | pytest-chaos 또는 자체 실패 주입 픽스처 구축 필요 |

---

## 6. 참고문헌 목록

1. [Google Engineering Practices](https://google.github.io/eng-practices/)
2. [Netflix Chaos Monkey](https://netflix.github.io/chaosmonkey/)
3. [Google Cloud Chaos Engineering Guide](https://cloud.google.com/blog/products/devops-sre/getting-started-with-chaos-engineering)
4. [Defensive Programming — Wikipedia](https://en.wikipedia.org/wiki/Defensive_programming)
5. [Defensive Programming in Python — Pluralsight](https://www.pluralsight.com/resources/blog/guides/defensive-programming-in-python)
6. [Avoid Errors with Defensive Coding in TypeScript](https://typescript.tv/best-practices/avoid-errors-with-defensive-coding-in-typescript/)
7. [Feature Flags Best Practices 2026 — tggl.io](https://tggl.io/blog/unlock-the-power-of-feature-flags-6-best-practices-you-need-in-2026)
8. [Feature Flag Security — Unleash](https://www.getunleash.io/blog/feature-flag-security-best-practices)
9. [11 Principles for Feature Flag Systems — Unleash Docs](https://docs.getunleash.io/topics/feature-flags/feature-flag-best-practices)
10. [Feature Flags Guide 2026 — apwide](https://www.apwide.com/what-are-feature-flags-guide/)
11. [Mastering Idempotency — ByteByteGo](https://blog.bytebytego.com/p/mastering-idempotency-building-reliable)
12. [Idempotency in Microservices 2026 — OneUptime](https://oneuptime.com/blog/post/2026-01-24-idempotency-in-microservices/view)
13. [Idempotent Consumer Pattern — microservices.io](https://microservices.io/patterns/communication-style/idempotent-consumer.html)
14. [CRAP Metric — Alberto Savoia](https://www.artima.com/weblogs/viewpost.jsp?thread=215899)
15. [Modern API Design Best Practices 2026 — Xano](https://www.xano.com/blog/modern-api-design-best-practices/)
16. [Strangler Fig Pattern — Martin Fowler](https://martinfowler.com/bliki/StranglerFigApplication.html)
