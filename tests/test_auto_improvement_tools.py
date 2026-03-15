from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.auto_improve_recent_conversations import (
    ImprovementAction,
    ImprovementPlan,
    VerificationResult,
    _fallback_plan,
    write_run_artifacts,
)


def test_fallback_plan_builds_auto_review_branch() -> None:
    plan = _fallback_plan("리뷰 내용", stamp="20260315-120000", max_actions=1)
    assert plan.branch_name.startswith("auto/review-20260315-120000-")
    assert len(plan.actions) == 1
    assert plan.actions[0].verify_commands


def test_write_run_artifacts_creates_summary(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    (worktree / ".git").mkdir()

    plan = ImprovementPlan(
        summary="자동 개선 요약",
        pr_title="Auto improve",
        branch_name="auto/review-demo",
        actions=[
            ImprovementAction(
                title="fix-runtime",
                rationale="사용자 응답 개선",
                files=["core/telegram_relay.py"],
                implementation_prompt="수정",
                verify_commands=["pytest -q tests/test_pm_intercept.py"],
            )
        ],
        verify_commands=["pytest -q tests/test_pm_intercept.py"],
    )
    review_path, summary_path = write_run_artifacts(
        run_dir,
        transcript="sample transcript",
        review_report="# Review",
        plan=plan,
        apply_logs=["done"],
        verification=[VerificationResult(command="pytest -q", exit_code=0, output="ok")],
        worktree_dir=worktree,
    )

    assert review_path.exists()
    assert summary_path.exists()
    content = summary_path.read_text(encoding="utf-8")
    assert "Auto improve" in content
    assert "auto/review-demo" in content
