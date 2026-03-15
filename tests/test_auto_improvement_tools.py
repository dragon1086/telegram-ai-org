from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.auto_improve_recent_conversations import (
    ImprovementAction,
    ImprovementPlan,
    VerificationResult,
    _fallback_plan,
    changed_files_are_safe,
    diff_line_churn,
    validate_plan,
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


def test_validate_plan_rejects_unsafe_files() -> None:
    plan = ImprovementPlan(
        summary="unsafe",
        pr_title="unsafe",
        branch_name="auto/review-unsafe",
        actions=[
            ImprovementAction(
                title="bad",
                rationale="bad",
                files=["organizations.yaml"],
                implementation_prompt="do it",
                verify_commands=["pytest -q tests/test_pm_intercept.py"],
            )
        ],
    )

    try:
        validate_plan(plan, max_actions=1, stamp="20260315-120000")
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe plan should fail")


def test_changed_files_are_safe_allows_planned_and_tests() -> None:
    assert changed_files_are_safe(
        ["core/telegram_relay.py", "tests/test_pm_intercept.py"],
        ["core/telegram_relay.py"],
    ) is True


def test_changed_files_are_safe_blocks_unplanned_config_changes() -> None:
    assert changed_files_are_safe(
        ["organizations.yaml"],
        ["core/telegram_relay.py"],
    ) is False


def test_changed_files_are_safe_blocks_excessive_file_count() -> None:
    changed = [f"core/file_{idx}.py" for idx in range(20)]
    assert changed_files_are_safe(changed, changed) is False


def test_diff_line_churn_counts_added_and_deleted_lines(tmp_path: Path) -> None:
    worktree = tmp_path / "repo"
    worktree.mkdir()
    subprocess = __import__("subprocess")
    subprocess.run(["git", "init"], cwd=str(worktree), check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(worktree), check=True, capture_output=True, text=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(worktree), check=True, capture_output=True, text=True)
    sample = worktree / "sample.txt"
    sample.write_text("a\nb\n", encoding="utf-8")
    subprocess.run(["git", "add", "sample.txt"], cwd=str(worktree), check=True, capture_output=True, text=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(worktree), check=True, capture_output=True, text=True)
    sample.write_text("a\nc\nd\n", encoding="utf-8")

    assert diff_line_churn(worktree_dir=worktree) == 3
