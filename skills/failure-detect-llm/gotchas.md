# Gotchas — failure-detect-llm

## G1: 짧은 로그로 LLM 호출 시 환각 발생
- **상황**: `recent_logs`가 50줄 미만이거나 스택트레이스만 포함된 경우
- **현상**: LLM이 context 없이 추측하여 confidence 높게 오탐 반환
- **해결**: `recent_logs` 길이 < 200자이면 스킬 호출 생략, 알고리즘 판정 유지

## G2: Flaky test로 인한 new_count 증가 → 회귀 오탐
- **상황**: CI 불안정 환경에서 new_count가 일시적으로 증가
- **현상**: 알고리즘이 회귀로 판정, LLM도 동조 가능
- **해결**: `task_context.failed_count`와 `trigger_type`에 "flaky" 힌트 주입

## G3: API 레이턴시 > 5s 시 파이프라인 블로킹
- **상황**: Gemini API p99 레이턴시 초과
- **현상**: 전체 자가개선 파이프라인 지연
- **해결**: 반드시 `asyncio.wait_for(timeout=5.0)` 래핑, 타임아웃 시 fallback

## G4: 동일 run_id 중복 호출
- **상황**: FeedbackLoopRunner 재시도 시 동일 diff로 반복 호출
- **현상**: 불필요한 비용 발생
- **해결**: rate_limit.per_run_id = 1 — run_id 기준 중복 호출 차단
