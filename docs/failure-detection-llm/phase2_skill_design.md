# Phase 2: LLM 기반 실패 감지 스킬 설계 문서
## skill: `failure-detect-llm`

> 기준일: 2026-03-22 | Phase 1 결과 반영

---

## 1. 적합성 판단 (결론 먼저)

**✅ 스킬 등록 권고 — 단, 하이브리드 구조 조건부**

| 항목 | 판정 | 근거 |
|------|------|------|
| 알고리즘 대비 가치 | ✅ | Recall +19%p (72%→91%), FN 절반 이하 |
| 레이턴시 허용 가능성 | ⚠️ | 실시간 감지 불필요한 파이프라인에서만 적용 |
| 비용 | ✅ | 10K회/월 기준 최대 $15 — 허용 범위 |
| 현행 아키텍처 적합성 | ✅ | ImprovementBus 신호 체계에 자연스럽게 연결 |
| 단독 LLM만 사용 | ❌ | 알고리즘 1차 필터 후 LLM 2차 심층 분석 필수 |

---

## 2. 트리거 조건

스킬이 호출되어야 하는 이벤트:

```
[1순위 트리거 — 즉시 호출]
- SelfImproveMonitor.is_failure() 반환: (True, reason) → 확인용 LLM 재검증
- ScanDiff.status == "regressed" AND new_count >= 3
- FailureCondition 경계 케이스: survival_rate 0.75~0.85 구간 (알고리즘 불확실 구간)

[2순위 트리거 — 배치 분석]
- FeedbackLoopRunner 반복 루프 3회 후에도 미개선
- improvement_rate < 0.1 AND baseline_issue_count > 5
- 동일 task_id에서 3회 이상 FAILED 상태 전환 (context_db 기준)
```

---

## 3. 입력 스펙 (Input Schema)

```python
# 스킬 호출 시 전달 컨텍스트 구조
{
    "trigger_type": str,          # "algorithm_uncertain" | "regressed" | "repeated_fail"
    "scan_diff": {
        "run_id": str,
        "baseline_issue_count": int,
        "post_run_issue_count": int,
        "resolved_count": int,
        "new_count": int,
        "improvement_rate": float,
        "status": str,            # "improved"|"unchanged"|"regressed"|"error"
        "new_items": list[dict],  # 신규 발생 이슈 (최대 20건)
        "unresolved_items": list[dict]  # 미해소 이슈 (최대 20건)
    },
    "recent_logs": str,           # 최근 500 lines 로그 (선택, 최대 2000 tokens)
    "task_context": {             # 선택
        "task_id": str,
        "org_name": str,
        "failed_count": int
    },
    "algorithm_verdict": {
        "is_failure": bool,
        "reason": str
    }
}
```

**토큰 예산**:
- 입력 최대: 3,000 tokens (scan_diff 500 + logs 2,000 + 메타 500)
- 출력 최대: 300 tokens
- 총 예산: ~3,300 tokens → 호출당 $0.001 미만

---

## 4. 출력 스펙 (Output Schema)

```python
# 스킬 반환 구조
{
    "is_failure": bool,           # 최종 실패 판정
    "confidence": float,          # 0.0~1.0 신뢰도
    "failure_type": str | None,   # "regression"|"no_improvement"|"pipeline_error"|"flaky"|null
    "override_algorithm": bool,   # 알고리즘과 다른 판정 여부
    "reason": str,                # 판정 근거 (1~3문장)
    "recommended_action": str,    # "retry"|"escalate"|"ignore"|"investigate"
    "evidence": list[str]         # 판단 근거 핵심 항목 (최대 3개)
}
```

**판정 우선순위**:
```
if confidence >= 0.85:
    → LLM 판정 채택 (알고리즘 오버라이드 가능)
elif confidence 0.60~0.85:
    → 알고리즘과 LLM 모두 True인 경우만 최종 실패
else:  # confidence < 0.60
    → 알고리즘 판정 유지 (LLM 불확실)
```

---

## 5. 프롬프트 설계 (핵심)

```
system: |
  You are a failure detection specialist for an AI agent pipeline.
  Analyze the given scan diff and determine if this represents a genuine failure
  or a false positive from the rule-based detector.

  Output JSON only. No explanation outside JSON.

user: |
  Algorithm verdict: {algorithm_verdict}

  Scan Diff Summary:
  - baseline issues: {baseline_issue_count}
  - post-run issues: {post_run_issue_count}
  - new issues: {new_count}, resolved: {resolved_count}
  - improvement rate: {improvement_rate:.1%}
  - status: {status}

  New issues (top 5): {new_items[:5]}

  Recent context (if available): {recent_logs[-500:]}

  Is this a genuine failure? Consider: flaky tests, refactoring noise,
  cascade effects, and whether the root cause is actionable.

  Respond: {"is_failure": bool, "confidence": 0.0-1.0, "failure_type": str|null,
  "override_algorithm": bool, "reason": "...", "recommended_action": "...",
  "evidence": [...]}
```

---

## 6. 한계 및 보완 방안

| 한계 | 상황 | 보완 방안 |
|------|------|---------|
| 높은 레이턴시 (p95 4s) | 실시간 감지 필요 시 | 알고리즘 1차 필터 후 비동기 LLM 호출 |
| 환각(Hallucination) | 로그 컨텍스트 없는 경우 | confidence < 0.60 시 알고리즘 판정 유지 |
| API 장애 시 | Gemini API 다운 | fallback: 알고리즘 방식으로 자동 전환 |
| 비용 급증 | 트리거 과다 호출 | rate limit: 동일 run_id 당 1회, 시간당 최대 50회 |
| 긴 스택트레이스 | 토큰 초과 | 로그 truncate + 핵심 오류 라인만 추출 |

**하이브리드 적용 구조**:
```
ScanDiff 생성
    ↓
[Layer 1] FailureCondition.check() — <1ms
    ├── 명확한 실패 (error/regression >3) → 즉시 알림
    ├── 명확한 통과 (improvement > 0.5) → 통과
    └── 불확실 구간 (0.75≤survival≤0.85, borderline)
            ↓
        [Layer 2] LLM 비동기 분석 — 1~4s
            ├── confidence≥0.85 → LLM 판정 채택
            └── confidence<0.85 → 알고리즘 판정 유지
```

---

## 7. 스킬 디렉토리 구조

```
skills/
  failure-detect-llm/
    SKILL.md          ← 스킬 메타데이터 + 트리거 명세
    scripts/
      detect.py       ← LLM 호출 + 판정 로직
    gotchas.md        ← 알려진 오탐 케이스 + 회피법
```

---

## 8. SKILL.md 초안

```yaml
---
name: failure-detect-llm
description: >
  LLM(Gemini 2.5 Flash) 기반 실패 감지 보조 스킬.
  알고리즘 방식이 불확실한 경계 케이스(survival_rate 0.75~0.85, borderline regression)에서
  의미 기반 재검증을 수행한다.
  Triggers: 'failure detect', 'LLM 실패감지', '알고리즘 불확실', 'borderline failure',
  자가개선 파이프라인 완료 후 애매한 판정
model: gemini-2.5-flash
max_tokens_input: 3000
max_tokens_output: 300
fallback: algorithm  # API 장애 시 알고리즘 방식으로 자동 전환
rate_limit:
  per_run_id: 1       # 동일 run_id 1회만
  per_hour: 50        # 시간당 최대 50회
---
```
