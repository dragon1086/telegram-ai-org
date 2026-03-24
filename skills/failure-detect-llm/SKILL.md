---
name: failure-detect-llm
description: "LLM(Gemini 2.5 Flash) 기반 실패 감지 보조 스킬. Triggers: 'failure detect', 'LLM 실패감지', '알고리즘 불확실', 'borderline failure'. Use when survival_rate 0.75~0.85 경계 케이스이거나 알고리즘 판정이 불확실할 때."
model: gemini-2.5-flash
max_tokens_input: 3000
max_tokens_output: 300
fallback: algorithm
rate_limit:
  per_run_id: 1
  per_hour: 50
allowed-tools: Read, Glob, Grep
---

# failure-detect-llm

알고리즘 기반 실패 감지의 보완 스킬. 경계 케이스 및 복합 실패 패턴에서 Gemini 2.5 Flash를 활용해 의미 기반 재검증을 수행한다.

## 적용 대상

- `FailureCondition.check()` 불확실 구간: survival_rate 0.75~0.85
- `ScanDiff.status == "regressed"` AND `new_count >= 3`
- 동일 task_id 3회 이상 FAILED 전환
- `FeedbackLoopRunner` 3회 반복 후 미개선

## 입력 구조

```json
{
  "trigger_type": "algorithm_uncertain | regressed | repeated_fail",
  "scan_diff": {
    "run_id": "string",
    "baseline_issue_count": 0,
    "post_run_issue_count": 0,
    "resolved_count": 0,
    "new_count": 0,
    "improvement_rate": 0.0,
    "status": "improved|unchanged|regressed|error",
    "new_items": [],
    "unresolved_items": []
  },
  "recent_logs": "string (최대 2000 tokens, 선택)",
  "task_context": {
    "task_id": "string",
    "org_name": "string",
    "failed_count": 0
  },
  "algorithm_verdict": {
    "is_failure": false,
    "reason": "string"
  }
}
```

## 출력 구조

```json
{
  "is_failure": false,
  "confidence": 0.0,
  "failure_type": "regression|no_improvement|pipeline_error|flaky|null",
  "override_algorithm": false,
  "reason": "판정 근거 1~3문장",
  "recommended_action": "retry|escalate|ignore|investigate",
  "evidence": ["근거1", "근거2", "근거3"]
}
```

## 판정 우선순위

| confidence | 최종 판정 |
|-----------|---------|
| ≥ 0.85 | LLM 판정 채택 (알고리즘 오버라이드 가능) |
| 0.60~0.85 | 알고리즘 + LLM 모두 True인 경우만 실패 |
| < 0.60 | 알고리즘 판정 유지 |

## 하이브리드 구조

```
[Layer 1] FailureCondition.check() — <1ms
    ├── 명확한 실패/통과 → 즉시 반환
    └── 불확실 구간 → [Layer 2] 이 스킬 호출 (비동기)
```

## fallback

Gemini API 장애 시 알고리즘 판정(`algorithm_verdict`)을 그대로 반환.

## 수정 안전 원칙 (safe-modify 연동 — 2026-03-22)

> 이 스킬의 판정 로직(confidence 임계값, 판정 우선순위, fallback 경로)을 수정할 때는
> **반드시 `skills/safe-modify/SKILL.md` 절차를 따른다.**

### 수정 시 절대 금지
- confidence 임계값(0.85, 0.60) 테스트 없이 변경
- `fallback: algorithm` 경로 제거 또는 우회
- `override_algorithm: true` 반환 조건 확장 (더 많은 케이스에서 오버라이드 허용 금지)
- `per_run_id: 1` rate limit 제거 (중복 LLM 호출 방지 장치 보존 필수)

### 수정 허용 조건
1. 변경 전 기존 판정 케이스 테스트 100% PASS 확인
2. Feature Flag(`FF_FAILURE_DETECT_V2` 등)로 신규 로직 격리
3. Dark Launch: 새 로직 결과를 로그에만 기록하며 실제 판정에 미반영 후 검증
4. 실패 주입 테스트: `status=error`, `scan_diff={}`, `scan_diff=None` 케이스 PASS

### CRAP 점수 관리
`FailureCondition.check()` 및 이 스킬의 LLM 호출 래퍼 함수는
cyclomatic complexity ≤ 8 유지. 초과 시 서브함수 분리 먼저 수행.
