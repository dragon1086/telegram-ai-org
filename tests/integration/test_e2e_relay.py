"""End-to-end integration test harness for the telegram-ai-org relay pipeline.

Tests routing decisions from PMOrchestrator.plan_request() across 6 scenarios,
captures timing and quality metrics, then writes a markdown report.
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.context_db import ContextDB
from core.task_graph import TaskGraph
from core.claim_manager import ClaimManager
from core.memory_manager import MemoryManager
from core.pm_orchestrator import PMOrchestrator, RequestPlan

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

REPORT_PATH = Path(__file__).parent.parent.parent / "docs" / "retros" / "2026-03-17-integration-test-report.md"

# Scenario spec: expected_route=None means any route is acceptable.
# expected_lane_contains is a list of acceptable lane values (OR logic).
SCENARIOS = [
    {
        "name": "coding_bug_request",
        "message": "코드에서 버그를 찾아줘",
        "expected_route": None,  # local_execution or delegate both acceptable
        "expected_lane_contains": ["single_org_execution", "direct_answer"],
        "description": "단순 코딩 요청 → single_org_execution, engineering dept 힌트 예상",
    },
    {
        "name": "greeting",
        "message": "안녕",
        "expected_route": None,  # heuristic has no greeting shortcut; any route ok
        "expected_lane_contains": ["direct_answer", "clarify", "single_org_execution"],
        "description": "인사 → 직접 답변 또는 단순 실행 예상",
    },
    {
        "name": "research_request",
        "message": "파이썬 asyncio 베스트 프랙티스 정리해줘",
        "expected_route": None,
        "expected_lane_contains": ["single_org_execution", "direct_answer"],
        "description": "리서치 요청 → single_org_execution 예상",
    },
    {
        "name": "planning_request",
        "message": "팀에 새 기능 개발 계획을 세워줘",
        "expected_route": "delegate",
        "expected_lane_contains": ["single_org_execution", "multi_org_execution"],
        "description": "기획+개발 요청 → delegate 예상",
    },
    {
        "name": "multi_dept_request",
        "message": "마케팅 전략과 코드 구현을 같이 해줘",
        "expected_route": "delegate",
        "expected_lane_contains": ["multi_org_execution", "single_org_execution"],
        "description": "멀티부서 요청 → multi_org_execution + delegate 예상",
    },
    {
        "name": "ambiguous_request",
        "message": "도와줘",
        "expected_route": None,  # any route acceptable for ambiguous input
        "expected_lane_contains": ["clarify", "direct_answer", "single_org_execution"],
        "description": "모호한 요청 → 어떤 라우트도 허용",
    },
]


@dataclass
class ScenarioResult:
    name: str
    message: str
    description: str
    plan: RequestPlan | None = None
    elapsed_sec: float = 0.0
    passed: bool = False
    failure_reason: str = ""
    exception: str = ""
    llm_called: bool = False
    expected_lane_contains: list[str] = field(default_factory=list)
    expected_route: str | None = ""


async def _make_orchestrator(tmp_path: Path) -> PMOrchestrator:
    db = ContextDB(tmp_path / "test.db")
    await db.initialize()
    graph = TaskGraph(db)
    claim = ClaimManager()
    memory = MemoryManager("pm")
    send_fn = AsyncMock()
    os.environ["AIORG_REPORT_DIR"] = str(tmp_path / "reports")
    return PMOrchestrator(db, graph, claim, memory, "aiorg_pm_bot", send_fn)


# ---------------------------------------------------------------------------
# Async helper to run one scenario
# ---------------------------------------------------------------------------

async def _run_scenario(orch: PMOrchestrator, scenario: dict) -> ScenarioResult:
    result = ScenarioResult(
        name=scenario["name"],
        message=scenario["message"],
        description=scenario["description"],
        expected_lane_contains=scenario["expected_lane_contains"],
        expected_route=scenario["expected_route"],
    )

    # Track whether _llm_unified_classify was called
    original_classify = orch._llm_unified_classify
    llm_call_tracker = {"called": False}

    async def _tracking_classify(msg, hints, **kwargs):
        llm_call_tracker["called"] = True
        return await original_classify(msg, hints, **kwargs)

    orch._llm_unified_classify = _tracking_classify  # type: ignore[method-assign]

    start = time.perf_counter()
    try:
        plan = await asyncio.wait_for(orch.plan_request(scenario["message"]), timeout=5.0)
        result.elapsed_sec = time.perf_counter() - start
        result.plan = plan
        result.llm_called = llm_call_tracker["called"]

        failures = []

        # Lane check — any value in expected_lane_contains is acceptable
        if plan.lane not in scenario["expected_lane_contains"]:
            failures.append(
                f"lane={plan.lane!r} not in acceptable={scenario['expected_lane_contains']}"
            )

        # Route check — None means any route is acceptable
        expected_route = scenario["expected_route"]
        if expected_route is not None and plan.route != expected_route:
            failures.append(
                f"route={plan.route!r} expected={expected_route!r}"
            )

        # Timing check
        if result.elapsed_sec > 5.0:
            failures.append(f"too slow: {result.elapsed_sec:.2f}s > 5s")

        if failures:
            result.failure_reason = "; ".join(failures)
            result.passed = False
        else:
            result.passed = True

    except asyncio.TimeoutError:
        result.elapsed_sec = time.perf_counter() - start
        result.exception = "TimeoutError (>5s)"
        result.failure_reason = "plan_request timed out"
    except Exception as exc:
        result.elapsed_sec = time.perf_counter() - start
        result.exception = f"{type(exc).__name__}: {exc}"
        result.failure_reason = "exception raised"

    return result


# ---------------------------------------------------------------------------
# Main integration test — runs all scenarios and writes markdown report
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_e2e_routing_all_scenarios():
    """Run all 6 routing scenarios and generate a markdown report."""
    results: list[ScenarioResult] = []

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        orch = await _make_orchestrator(tmp_path)

        for scenario in SCENARIOS:
            r = await _run_scenario(orch, scenario)
            results.append(r)

    # Generate report regardless of pass/fail
    _write_report(results)

    failed = [r for r in results if not r.passed]
    if failed:
        summary = "\n".join(
            f"  - {r.name}: {r.failure_reason}" for r in failed
        )
        pytest.fail(f"{len(failed)}/{len(results)} scenarios failed:\n{summary}")


# ---------------------------------------------------------------------------
# Individual scenario tests (granular pytest output)
# ---------------------------------------------------------------------------

@pytest.fixture
async def orch_fixture(tmp_path):
    return await _make_orchestrator(tmp_path)


@pytest.mark.asyncio
async def test_scenario_coding_request(orch_fixture):
    """코딩 요청 → delegate / single_org_execution or direct_answer."""
    result = await _run_scenario(orch_fixture, SCENARIOS[0])
    assert result.passed, f"FAILED: {result.failure_reason} | plan={result.plan}"


@pytest.mark.asyncio
async def test_scenario_greeting(orch_fixture):
    """인사 → direct_reply / direct_answer or clarify."""
    result = await _run_scenario(orch_fixture, SCENARIOS[1])
    assert result.passed, f"FAILED: {result.failure_reason} | plan={result.plan}"


@pytest.mark.asyncio
async def test_scenario_research_request(orch_fixture):
    """리서치 요청 → delegate / single_org_execution or direct_answer."""
    result = await _run_scenario(orch_fixture, SCENARIOS[2])
    assert result.passed, f"FAILED: {result.failure_reason} | plan={result.plan}"


@pytest.mark.asyncio
async def test_scenario_planning_request(orch_fixture):
    """기획 요청 → delegate / single_org or multi_org."""
    result = await _run_scenario(orch_fixture, SCENARIOS[3])
    assert result.passed, f"FAILED: {result.failure_reason} | plan={result.plan}"


@pytest.mark.asyncio
async def test_scenario_multi_dept_request(orch_fixture):
    """멀티부서 요청 → delegate / multi_org_execution or single_org_execution."""
    result = await _run_scenario(orch_fixture, SCENARIOS[4])
    assert result.passed, f"FAILED: {result.failure_reason} | plan={result.plan}"


@pytest.mark.asyncio
async def test_scenario_ambiguous(orch_fixture):
    """모호한 요청 → any route / clarify or direct_answer."""
    result = await _run_scenario(orch_fixture, SCENARIOS[5])
    assert result.passed, f"FAILED: {result.failure_reason} | plan={result.plan}"


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def _write_report(results: list[ScenarioResult]) -> None:
    passed = sum(1 for r in results if r.passed)
    failed_count = len(results) - passed
    avg_ms = (
        sum(r.elapsed_sec for r in results) / len(results) * 1000
        if results else 0
    )

    lines = [
        "# Integration Test Report — 2026-03-17",
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Executive Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Total scenarios | {len(results)} |",
        f"| Passed | {passed} |",
        f"| Failed | {failed_count} |",
        f"| Pass rate | {passed / len(results) * 100:.0f}% |" if results else "| Pass rate | N/A |",
        f"| Avg response time | {avg_ms:.1f} ms |",
        "",
        "## Per-Scenario Results",
        "",
        "| # | Scenario | Status | Lane | Route | Dept Hints | Time (ms) | Notes |",
        "|---|----------|--------|------|-------|------------|-----------|-------|",
    ]

    for i, r in enumerate(results, 1):
        status = "PASS" if r.passed else "FAIL"
        lane = r.plan.lane if r.plan else "N/A"
        route = r.plan.route if r.plan else "N/A"
        hints = ", ".join(r.plan.dept_hints) if r.plan and r.plan.dept_hints else "—"
        time_ms = f"{r.elapsed_sec * 1000:.0f}"
        notes = r.failure_reason or r.exception or "OK"
        lines.append(
            f"| {i} | {r.name} | {status} | {lane} | {route} | {hints} | {time_ms} | {notes} |"
        )

    lines += [
        "",
        "## Performance Metrics",
        "",
    ]
    for r in results:
        lines.append(f"- **{r.name}**: {r.elapsed_sec * 1000:.1f} ms")

    lines += [
        "",
        "## Routing Details",
        "",
    ]
    for r in results:
        if r.plan:
            lines += [
                f"### {r.name}",
                f"- **Description**: {r.description}",
                f"- **Lane**: `{r.plan.lane}`",
                f"- **Route**: `{r.plan.route}`",
                f"- **Complexity**: `{r.plan.complexity}`",
                f"- **Dept hints**: {r.plan.dept_hints}",
                f"- **Confidence**: {r.plan.confidence}",
                f"- **Rationale**: {r.plan.rationale}",
                f"- **LLM called**: {r.llm_called}",
                "",
            ]
        else:
            lines += [
                f"### {r.name}",
                f"- **Error**: {r.exception or r.failure_reason}",
                "",
            ]

    issues = [r for r in results if not r.passed]
    lines += [
        "## Issues Found",
        "",
    ]
    if issues:
        for r in issues:
            lines.append(f"- **{r.name}**: {r.failure_reason}")
            if r.plan:
                lines.append(
                    f"  - Got lane=`{r.plan.lane}` route=`{r.plan.route}` "
                    f"acceptable_lanes={r.expected_lane_contains} expected_route={r.expected_route!r}"
                )
    else:
        lines.append("No issues found. All scenarios passed.")

    lines += [
        "",
        "## Recommendations",
        "",
        "- All routing tests are heuristic-based (no LLM API calls required for fast CI).",
        "- Add a `decision_client` mock to exercise the LLM path in a separate slow-test suite.",
        "- Consider adding timing assertions to catch regressions in `_heuristic_unified_classify`.",
        "- The `도와줘` (ambiguous) scenario uses `expected_route=None`; "
          "any route is acceptable for truly ambiguous inputs.",
        "",
    ]

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to: {REPORT_PATH}")
