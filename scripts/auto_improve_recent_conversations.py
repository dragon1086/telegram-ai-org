#!/usr/bin/env python3
"""최근 대화 리뷰를 자동 코드 개선 파이프라인으로 승격한다.

Flow:
1. 최근 로그 수집 + 리뷰 리포트 생성
2. 리뷰 기반 개선 액션 계획(JSON) 생성
3. git worktree에서 코드 변경 실행
4. 검증 명령 실행
5. 브랜치 푸시 / PR 생성(가능 시) / 텔레그램 업로드용 산출물 저장
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.pm_decision import PMDecisionClient
from core.telegram_delivery import resolve_delivery_target
from scripts.review_recent_conversations import (
    build_report,
    collect_recent_log_lines,
)
from tools.claude_code_runner import ClaudeCodeRunner
from tools.codex_runner import CodexRunner
from tools.telegram_uploader import upload_file


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / ".omx" / "auto-improve"
MAX_FILES_PER_ACTION = 6
MAX_CHANGED_FILES = 12
MAX_DIFF_LINE_CHURN = 600
SAFE_FILE_PREFIXES = ("core/", "scripts/", "tools/", "tests/", "docs/")
SAFE_FILE_EXACT = {"README.md", "ARCHITECTURE.md", "AGENTS.md", "pyproject.toml"}
FORBIDDEN_FILE_PREFIXES = ("bots/", ".ai-org/", ".omx/state/", ".omx/metrics", ".env")
FORBIDDEN_FILE_EXACT = {"organizations.yaml", "agent_hints.yaml", "workers.yaml", "orchestration.yaml"}
SAFE_VERIFY_PREFIXES = (
    "pytest",
    "./.venv/bin/pytest",
    "python -m py_compile",
    "./.venv/bin/python -m py_compile",
    "ruff check",
    "./.venv/bin/ruff check",
)


@dataclass
class ImprovementAction:
    title: str
    rationale: str
    files: list[str] = field(default_factory=list)
    implementation_prompt: str = ""
    verify_commands: list[str] = field(default_factory=list)


@dataclass
class ImprovementPlan:
    summary: str
    pr_title: str
    branch_name: str
    actions: list[ImprovementAction] = field(default_factory=list)
    verify_commands: list[str] = field(default_factory=list)


@dataclass
class VerificationResult:
    command: str
    exit_code: int
    output: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto-improve recent conversation-driven issues.")
    parser.add_argument("--hours", type=int, default=24)
    parser.add_argument("--org-id", default="global")
    parser.add_argument("--review-engine", default="claude-code", choices=["claude-code", "codex"])
    parser.add_argument("--apply-engine", default="claude-code", choices=["claude-code", "codex"])
    parser.add_argument("--limit-lines", type=int, default=500)
    parser.add_argument("--max-actions", type=int, default=1)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--push-branch", action="store_true")
    parser.add_argument("--create-pr", action="store_true")
    parser.add_argument("--upload", action="store_true")
    return parser.parse_args()


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:48] or "auto-improve"


def _fallback_plan(review_report: str, *, stamp: str, max_actions: int) -> ImprovementPlan:
    action = ImprovementAction(
        title="recent-conversation-followup",
        rationale="리뷰 리포트에서 사용자 체감 문제를 줄이는 런타임 개선이 필요함",
        files=[
            "core/telegram_relay.py",
            "core/pm_orchestrator.py",
            "core/pm_identity.py",
        ],
        implementation_prompt=(
            "리뷰 리포트를 바탕으로 최근 대화에서 반복된 사용자 체감 문제를 줄이는 가장 작은 고가치 수정을 "
            "1개 수행하고 테스트를 보강하라."
        ),
        verify_commands=["./.venv/bin/pytest -q tests/test_pm_intercept.py tests/test_pm_orchestrator.py"],
    )
    return ImprovementPlan(
        summary="최근 대화 기반 자동 개선",
        pr_title="Auto-improve conversation-driven UX issues",
        branch_name=f"auto/review-{stamp}-{_slugify('conversation-ux')}",
        actions=[action][:max_actions],
        verify_commands=action.verify_commands,
    )


def _is_safe_repo_path(path: str) -> bool:
    normalized = path.strip().lstrip("./")
    if not normalized:
        return False
    if normalized in FORBIDDEN_FILE_EXACT:
        return False
    if any(normalized.startswith(prefix) for prefix in FORBIDDEN_FILE_PREFIXES):
        return False
    return normalized in SAFE_FILE_EXACT or normalized.startswith(SAFE_FILE_PREFIXES)


def _is_safe_verify_command(command: str) -> bool:
    stripped = command.strip()
    return any(stripped.startswith(prefix) for prefix in SAFE_VERIFY_PREFIXES)


def validate_plan(plan: ImprovementPlan, *, max_actions: int, stamp: str) -> ImprovementPlan:
    actions = plan.actions[:max_actions]
    if not actions:
        raise ValueError("empty actions")
    validated: list[ImprovementAction] = []
    for action in actions:
        files = [path.lstrip("./") for path in action.files if _is_safe_repo_path(path)]
        if not files or len(files) > MAX_FILES_PER_ACTION:
            raise ValueError(f"unsafe files for action: {action.title}")
        verify_commands = [cmd for cmd in action.verify_commands if _is_safe_verify_command(cmd)]
        validated.append(
            ImprovementAction(
                title=action.title,
                rationale=action.rationale,
                files=files,
                implementation_prompt=action.implementation_prompt,
                verify_commands=verify_commands,
            )
        )
    verify_commands = [cmd for cmd in plan.verify_commands if _is_safe_verify_command(cmd)]
    branch = plan.branch_name if plan.branch_name.startswith("auto/review-") else f"auto/review-{stamp}-{_slugify(plan.summary)}"
    return ImprovementPlan(
        summary=plan.summary,
        pr_title=plan.pr_title,
        branch_name=branch,
        actions=validated,
        verify_commands=verify_commands,
    )


async def build_action_plan(
    org_id: str,
    review_report: str,
    *,
    engine: str,
    max_actions: int,
    stamp: str,
) -> ImprovementPlan:
    client = PMDecisionClient(org_id=org_id, engine=engine)
    prompt = (
        "You are planning an automated maintenance/code-improvement cycle.\n"
        "Return JSON only with this exact shape:\n"
        "{"
        "\"summary\":\"...\","
        "\"pr_title\":\"...\","
        "\"branch_name\":\"auto/review-...\","
        "\"verify_commands\":[\"...\"],"
        "\"actions\":["
        "{\"title\":\"...\",\"rationale\":\"...\",\"files\":[\"path\"],"
        "\"implementation_prompt\":\"...\",\"verify_commands\":[\"...\"]}"
        "]}\n\n"
        "Rules:\n"
        "- Choose at most {max_actions} actions.\n"
        "- Keep scope narrow and safe.\n"
        "- Prefer runtime/orchestration/test/doc improvements that are directly justified by the review.\n"
        "- verify_commands must be runnable shell commands from repo root.\n"
        "- branch_name must start with auto/review-\n"
        "- files should be repository-relative paths.\n\n"
        f"[review report]\n{review_report[:9000]}"
    ).format(max_actions=max_actions)
    try:
        raw = await asyncio.wait_for(client.complete(prompt), timeout=90.0)
        data = _parse_json_block(raw)
        actions = [
            ImprovementAction(
                title=str(item.get("title", "")).strip() or "untitled-action",
                rationale=str(item.get("rationale", "")).strip() or "리뷰 기반 개선",
                files=[str(path) for path in item.get("files", []) if str(path).strip()],
                implementation_prompt=str(item.get("implementation_prompt", "")).strip(),
                verify_commands=[str(cmd) for cmd in item.get("verify_commands", []) if str(cmd).strip()],
            )
            for item in data.get("actions", [])
        ][:max_actions]
        if not actions:
            raise ValueError("empty actions")
        branch = str(data.get("branch_name", "")).strip()
        if not branch.startswith("auto/review-"):
            branch = f"auto/review-{stamp}-{_slugify(data.get('summary', 'maintenance'))}"
        return validate_plan(
            ImprovementPlan(
            summary=str(data.get("summary", "")).strip() or "자동 개선",
            pr_title=str(data.get("pr_title", "")).strip() or "Auto-improve recent conversation issues",
            branch_name=branch,
            actions=actions,
            verify_commands=[str(cmd) for cmd in data.get("verify_commands", []) if str(cmd).strip()],
            ),
            max_actions=max_actions,
            stamp=stamp,
        )
    except Exception:
        return validate_plan(_fallback_plan(review_report, stamp=stamp, max_actions=max_actions), max_actions=max_actions, stamp=stamp)


def _parse_json_block(raw: str) -> dict:
    text = raw.strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            text = match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]
    return json.loads(text)


def _run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True, check=True)


def create_worktree(branch_name: str, *, output_root: Path, base_ref: str) -> tuple[Path, str]:
    worktrees_root = output_root / "worktrees"
    worktrees_root.mkdir(parents=True, exist_ok=True)
    worktree_dir = worktrees_root / branch_name.replace("/", "__")
    if worktree_dir.exists():
        shutil.rmtree(worktree_dir)
    final_branch = branch_name
    probe = subprocess.run(["git", "show-ref", "--verify", f"refs/heads/{branch_name}"], cwd=str(PROJECT_ROOT), text=True, capture_output=True, check=False)
    if probe.returncode == 0:
        final_branch = f"{branch_name}-{datetime.now().strftime('%H%M%S')}"
    _run(["git", "worktree", "add", "-b", final_branch, str(worktree_dir), base_ref], cwd=PROJECT_ROOT)
    return worktree_dir, final_branch


async def apply_actions(
    plan: ImprovementPlan,
    *,
    worktree_dir: Path,
    org_id: str,
    engine: str,
    review_report: str,
) -> list[str]:
    logs: list[str] = []
    if engine == "codex":
        runner = CodexRunner(workdir=str(worktree_dir))
    else:
        runner = ClaudeCodeRunner(workdir=str(worktree_dir))
    for index, action in enumerate(plan.actions, start=1):
        files_text = "\n".join(f"- {path}" for path in action.files) or "- no explicit file hints"
        task = (
            f"[Auto improvement action {index}/{len(plan.actions)}]\n"
            f"Title: {action.title}\n"
            f"Rationale: {action.rationale}\n"
            f"Prefer touching these files:\n{files_text}\n\n"
            f"Implementation instructions:\n{action.implementation_prompt}\n\n"
            "Safety rules:\n"
            "- Only edit the planned repo-relative files plus directly related tests/docs.\n"
            "- Do not modify bot configs, org configs, secrets, cron settings, or deployment wiring.\n"
            "- Keep the diff narrowly scoped and reviewable.\n\n"
            f"Source review report:\n{review_report[:6000]}"
        )
        if engine == "codex":
            result = await runner.run(task, workdir=str(worktree_dir), workdir_hint=task)
        else:
            result = await runner.run_task(
                task,
                system_prompt=(
                    "You are running an unattended repository self-improvement job. "
                    "Keep scope narrow, produce reviewable diffs, and do not undo unrelated changes."
                ),
                org_id=org_id,
                workdir=str(worktree_dir),
            )
        logs.append(result)
    return logs


def run_verification(commands: list[str], *, cwd: Path) -> list[VerificationResult]:
    results: list[VerificationResult] = []
    for command in commands:
        if not _is_safe_verify_command(command):
            results.append(VerificationResult(command=command, exit_code=99, output="blocked by safety policy"))
            continue
        proc = subprocess.run(
            ["bash", "-lc", command],
            cwd=str(cwd),
            text=True,
            capture_output=True,
        )
        results.append(
            VerificationResult(
                command=command,
                exit_code=proc.returncode,
                output=(proc.stdout + proc.stderr).strip(),
            )
        )
    return results


def write_run_artifacts(
    run_dir: Path,
    *,
    transcript: str,
    review_report: str,
    plan: ImprovementPlan,
    apply_logs: list[str],
    verification: list[VerificationResult],
    worktree_dir: Path,
) -> tuple[Path, Path]:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "transcript.log").write_text(transcript.strip() + "\n", encoding="utf-8")
    review_path = run_dir / "review.md"
    review_path.write_text(review_report.strip() + "\n", encoding="utf-8")
    (run_dir / "plan.json").write_text(
        json.dumps(asdict(plan), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_dir / "apply.log").write_text("\n\n".join(log.strip() for log in apply_logs).strip() + "\n", encoding="utf-8")
    (run_dir / "verification.json").write_text(
        json.dumps([asdict(item) for item in verification], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    changed_files = subprocess.run(
        ["git", "status", "--short"],
        cwd=str(worktree_dir),
        text=True,
        capture_output=True,
        check=False,
    ).stdout.strip()
    summary_path = run_dir / "pr-ready-summary.md"
    verification_text = "\n".join(
        f"- `{item.command}` -> exit {item.exit_code}" for item in verification
    ) or "- no verification commands"
    summary_path.write_text(
        (
            f"# Auto Improvement Run\n\n"
            f"## Summary\n{plan.summary}\n\n"
            f"## PR Title\n{plan.pr_title}\n\n"
            f"## Branch\n{plan.branch_name}\n\n"
            f"## Changed Files\n```\n{changed_files or '(no changes)'}\n```\n\n"
            f"## Verification\n{verification_text}\n"
        ),
        encoding="utf-8",
    )
    return review_path, summary_path


def collect_changed_files(*, worktree_dir: Path) -> list[str]:
    proc = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=str(worktree_dir),
        text=True,
        capture_output=True,
        check=False,
    )
    changed: list[str] = []
    for raw in proc.stdout.splitlines():
        if len(raw) < 4:
            continue
        path = raw[3:].strip()
        if path:
            changed.append(path)
    return changed


def diff_line_churn(*, worktree_dir: Path) -> int:
    proc = subprocess.run(
        ["git", "diff", "--numstat"],
        cwd=str(worktree_dir),
        text=True,
        capture_output=True,
        check=False,
    )
    churn = 0
    for raw in proc.stdout.splitlines():
        parts = raw.split("\t")
        if len(parts) < 3:
            continue
        added, deleted = parts[0], parts[1]
        if added.isdigit():
            churn += int(added)
        if deleted.isdigit():
            churn += int(deleted)
    return churn


def changed_files_are_safe(changed_files: list[str], planned_files: list[str]) -> bool:
    if len(changed_files) > MAX_CHANGED_FILES:
        return False
    allowed = {path.lstrip("./") for path in planned_files}
    for path in changed_files:
        normalized = path.lstrip("./")
        if not _is_safe_repo_path(normalized):
            return False
        if normalized in allowed:
            continue
        if normalized.startswith(("tests/", "docs/")):
            continue
        if normalized in {"README.md", "ARCHITECTURE.md"}:
            continue
        return False
    return True


def commit_branch(plan: ImprovementPlan, *, worktree_dir: Path) -> str | None:
    changed_files = collect_changed_files(worktree_dir=worktree_dir)
    if not changed_files:
        return None
    planned_files = [path for action in plan.actions for path in action.files]
    if not changed_files_are_safe(changed_files, planned_files):
        return None
    if diff_line_churn(worktree_dir=worktree_dir) > MAX_DIFF_LINE_CHURN:
        return None
    _run(["git", "add", "-A"], cwd=worktree_dir)
    _run(["git", "commit", "-m", f"auto-improve: {plan.pr_title}"], cwd=worktree_dir)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(worktree_dir), text=True, capture_output=True, check=True)
    return head.stdout.strip()


def maybe_push_branch(plan: ImprovementPlan, *, worktree_dir: Path, enabled: bool) -> bool:
    if not enabled:
        return False
    proc = subprocess.run(
        ["git", "push", "-u", "origin", plan.branch_name],
        cwd=str(worktree_dir),
        text=True,
        capture_output=True,
        check=False,
    )
    return proc.returncode == 0


def maybe_create_pr(plan: ImprovementPlan, *, worktree_dir: Path, enabled: bool, summary_path: Path) -> str:
    if not enabled:
        return ""
    if shutil.which("gh") is None:
        return ""
    proc = subprocess.run(
        [
            "gh", "pr", "create",
            "--base", "main",
            "--head", plan.branch_name,
            "--title", plan.pr_title,
            "--body-file", str(summary_path),
        ],
        cwd=str(worktree_dir),
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.strip()


async def maybe_upload_summary(org_id: str, summary_path: Path) -> bool:
    target = resolve_delivery_target(org_id)
    if target is None:
        return False
    caption = f"🛠️ {org_id} auto-improve summary: {summary_path.name}"
    return await upload_file(target.token, target.chat_id, str(summary_path), caption)


async def run_cycle(args: argparse.Namespace) -> int:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    transcript = collect_recent_log_lines(args.hours, args.limit_lines)
    review_report = await build_report(args.org_id, transcript, args.hours, args.review_engine)
    plan = await build_action_plan(
        args.org_id,
        review_report,
        engine=args.review_engine,
        max_actions=args.max_actions,
        stamp=stamp,
    )
    run_dir = args.output_root / stamp
    worktree_dir, final_branch = create_worktree(plan.branch_name, output_root=args.output_root, base_ref=args.base_ref)
    plan.branch_name = final_branch
    try:
        apply_logs = await apply_actions(
            plan,
            worktree_dir=worktree_dir,
            org_id=args.org_id,
            engine=args.apply_engine,
            review_report=review_report,
        )
        verify_commands = plan.verify_commands or [cmd for action in plan.actions for cmd in action.verify_commands]
        if not verify_commands:
            verify_commands = ["./.venv/bin/python -m py_compile core/telegram_relay.py"]
        verification = run_verification(verify_commands, cwd=worktree_dir)
        review_path, summary_path = write_run_artifacts(
            run_dir,
            transcript=transcript,
            review_report=review_report,
            plan=plan,
            apply_logs=apply_logs,
            verification=verification,
            worktree_dir=worktree_dir,
        )
        commit_sha = None
        if all(item.exit_code == 0 for item in verification):
            commit_sha = commit_branch(plan, worktree_dir=worktree_dir)
        if commit_sha:
            maybe_push_branch(plan, worktree_dir=worktree_dir, enabled=args.push_branch)
            pr_url = maybe_create_pr(plan, worktree_dir=worktree_dir, enabled=args.create_pr, summary_path=summary_path)
            if pr_url:
                summary_path.write_text(summary_path.read_text(encoding="utf-8") + f"\n\n## PR\n{pr_url}\n", encoding="utf-8")
        if args.upload:
            await maybe_upload_summary(args.org_id, summary_path)
        print(summary_path)
        return 0
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(worktree_dir)], cwd=str(PROJECT_ROOT), text=True, capture_output=True, check=False)


def main() -> int:
    return asyncio.run(run_cycle(parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
