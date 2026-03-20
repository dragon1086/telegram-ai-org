# Integration Test Report — 2026-03-17

Generated: 2026-03-20 15:02:26

## Executive Summary

| Metric | Value |
|--------|-------|
| Total scenarios | 6 |
| Passed | 6 |
| Failed | 0 |
| Pass rate | 100% |
| Avg response time | 34.6 ms |

## Per-Scenario Results

| # | Scenario | Status | Lane | Route | Dept Hints | Time (ms) | Notes |
|---|----------|--------|------|-------|------------|-----------|-------|
| 1 | coding_bug_request | PASS | single_org_execution | local_execution | aiorg_engineering_bot | 30 | OK |
| 2 | greeting | PASS | single_org_execution | local_execution | — | 29 | OK |
| 3 | research_request | PASS | single_org_execution | local_execution | aiorg_engineering_bot | 30 | OK |
| 4 | planning_request | PASS | single_org_execution | delegate | aiorg_engineering_bot | 46 | OK |
| 5 | multi_dept_request | PASS | multi_org_execution | delegate | aiorg_engineering_bot, aiorg_growth_bot | 44 | OK |
| 6 | ambiguous_request | PASS | single_org_execution | local_execution | — | 29 | OK |

## Performance Metrics

- **coding_bug_request**: 29.8 ms
- **greeting**: 29.2 ms
- **research_request**: 29.6 ms
- **planning_request**: 45.8 ms
- **multi_dept_request**: 43.9 ms
- **ambiguous_request**: 29.3 ms

## Routing Details

### coding_bug_request
- **Description**: 단순 코딩 요청 → single_org_execution, engineering dept 힌트 예상
- **Lane**: `single_org_execution`
- **Route**: `local_execution`
- **Complexity**: `low`
- **Dept hints**: ['aiorg_engineering_bot']
- **Confidence**: 0.7
- **Rationale**: 집중된 단일 작업이라 PM이 직접 처리하는 편이 더 빠릅니다.
- **LLM called**: True

### greeting
- **Description**: 인사 → 직접 답변 또는 단순 실행 예상
- **Lane**: `single_org_execution`
- **Route**: `local_execution`
- **Complexity**: `low`
- **Dept hints**: []
- **Confidence**: 0.7
- **Rationale**: 집중된 단일 작업이라 PM이 직접 처리하는 편이 더 빠릅니다.
- **LLM called**: True

### research_request
- **Description**: 리서치 요청 → single_org_execution 예상
- **Lane**: `single_org_execution`
- **Route**: `local_execution`
- **Complexity**: `low`
- **Dept hints**: ['aiorg_engineering_bot']
- **Confidence**: 0.7
- **Rationale**: 집중된 단일 작업이라 PM이 직접 처리하는 편이 더 빠릅니다.
- **LLM called**: True

### planning_request
- **Description**: 기획+개발 요청 → delegate 예상
- **Lane**: `single_org_execution`
- **Route**: `delegate`
- **Complexity**: `high`
- **Dept hints**: ['aiorg_engineering_bot']
- **Confidence**: 0.75
- **Rationale**: 복수 조직 협업 또는 다단계 실행이 필요해 보여 조직 오케스트레이션으로 보냅니다.
- **LLM called**: True

### multi_dept_request
- **Description**: 멀티부서 요청 → multi_org_execution + delegate 예상
- **Lane**: `multi_org_execution`
- **Route**: `delegate`
- **Complexity**: `high`
- **Dept hints**: ['aiorg_engineering_bot', 'aiorg_growth_bot']
- **Confidence**: 0.8
- **Rationale**: 복수 조직 협업이 필요한 execution lane입니다.
- **LLM called**: True

### ambiguous_request
- **Description**: 모호한 요청 → 어떤 라우트도 허용
- **Lane**: `single_org_execution`
- **Route**: `local_execution`
- **Complexity**: `low`
- **Dept hints**: []
- **Confidence**: 0.7
- **Rationale**: 집중된 단일 작업이라 PM이 직접 처리하는 편이 더 빠릅니다.
- **LLM called**: True

## Issues Found

No issues found. All scenarios passed.

## Recommendations

- All routing tests are heuristic-based (no LLM API calls required for fast CI).
- Add a `decision_client` mock to exercise the LLM path in a separate slow-test suite.
- Consider adding timing assertions to catch regressions in `_heuristic_unified_classify`.
- The `도와줘` (ambiguous) scenario uses `expected_route=None`; any route is acceptable for truly ambiguous inputs.
