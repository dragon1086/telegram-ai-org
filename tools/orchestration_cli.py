#!/usr/bin/env python3
# ruff: noqa: E402
"""Canonical orchestration CLI.

This CLI is the stable control surface for config validation and legacy asset export.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

import yaml
from apscheduler.triggers.cron import CronTrigger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OPS_ROLLOUT_CONFIG_PATH = PROJECT_ROOT / "config" / "ops_rollout.yaml"
PROGRESS_GUIDE_PATHS = [
    Path.home() / ".claude" / "projects" / "-Users-rocky-telegram-ai-org" / "memory" / "pm_progress_guide.md",
    PROJECT_ROOT / "memory" / "pm_progress_guide.md",
]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.collab_dispatcher import _DEPT_CHAT_ID_ENV
from core.memory_manager import MemoryManager
from core.orchestration_config import load_orchestration_config
from core.orchestration_runbook import OrchestrationRunbook
from core.pm_orchestrator import PMOrchestrator
from core.telegram_delivery import resolve_delivery_target
from tools.telegram_uploader import upload_file


class _DummyDB:
    db_path = ":memory:"


class _DummyGraph:
    pass


class _DummyClaim:
    pass


async def _noop_send(_chat_id: int, _text: str) -> None:
    return None


def _load_runtime_env() -> None:
    for path in (Path.home() / ".ai-org" / "config.yaml", PROJECT_ROOT / ".env"):
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _find_progress_guide() -> Path | None:
    for path in PROGRESS_GUIDE_PATHS:
        if path.exists():
            return path
    return None


def _calc_status(failures: int, warnings: int) -> str:
    if failures:
        return "fail"
    if warnings:
        return "warn"
    return "ok"


def _expand_user_path(path_value: str) -> Path:
    return Path(path_value).expanduser()


def _build_ops_validation(cfg) -> dict[str, Any]:
    ops_cfg = _load_yaml(OPS_ROLLOUT_CONFIG_PATH)
    if not ops_cfg:
        return {
            "config_path": str(OPS_ROLLOUT_CONFIG_PATH),
            "status": "warn",
            "warnings": ["ops_rollout.yaml not found"],
            "cron_jobs": [],
            "collab_targets": [],
            "required_env": [],
            "runbook": {},
        }

    failures = 0
    warnings = 0
    cron_jobs: list[dict[str, Any]] = []
    for job in ops_cfg.get("cron_jobs", []):
        schedule_valid = True
        try:
            CronTrigger.from_crontab(job["schedule"], timezone=job.get("timezone", "UTC"))
        except Exception:
            schedule_valid = False
        script_path = PROJECT_ROOT / job.get("script", "")
        log_path = PROJECT_ROOT / job.get("log_path", "")
        script_args = job.get("script_args", [])
        if not schedule_valid or not script_path.exists() or not log_path.parent.exists():
            failures += 1
        cron_jobs.append({
            "id": job.get("id", ""),
            "schedule": job.get("schedule", ""),
            "timezone": job.get("timezone", "UTC"),
            "schedule_valid": schedule_valid,
            "script_exists": script_path.exists(),
            "log_parent_exists": log_path.parent.exists(),
            "script": str(script_path.relative_to(PROJECT_ROOT)) if script_path.exists() else job.get("script", ""),
            "script_args": script_args,
            "log_path": str(log_path.relative_to(PROJECT_ROOT)),
        })

    collab_targets: list[dict[str, Any]] = []
    for item in ops_cfg.get("collab_targets", []):
        dept_id = item.get("dept_id", "")
        env_key = item.get("chat_id_env", "")
        org_exists = cfg.get_org(dept_id) is not None
        mapping_matches = _DEPT_CHAT_ID_ENV.get(dept_id) == env_key
        env_present = bool(os.environ.get(env_key, ""))
        if not org_exists or not mapping_matches:
            failures += 1
        elif not env_present:
            warnings += 1
        collab_targets.append({
            "dept_id": dept_id,
            "org_exists": org_exists,
            "mapping_matches": mapping_matches,
            "chat_id_env": env_key,
            "env_present": env_present,
        })

    required_env: list[dict[str, Any]] = []
    for env_name in ops_cfg.get("required_env", []):
        present = bool(os.environ.get(env_name, ""))
        if not present:
            warnings += 1
        required_env.append({"name": env_name, "present": present})

    runbook = OrchestrationRunbook(PROJECT_ROOT)
    progress_guide = _find_progress_guide()
    state_root = runbook.state_root
    docs_root = runbook.docs_root
    active_run_count = len([p for p in state_root.iterdir() if p.is_dir()]) if state_root.exists() else 0
    latest_audit = max(
        (PROJECT_ROOT / "docs" / "audits").glob("*.md"),
        key=lambda path: path.stat().st_mtime,
        default=None,
    )
    if progress_guide is None:
        warnings += 1

    auto_restart_cfg = ops_cfg.get("auto_restart", {})
    auto_restart: dict[str, Any] = {
        "enabled": bool(auto_restart_cfg.get("enabled", False)),
        "platform": platform.system().lower(),
        "daemon_installer": "",
        "request_script": "",
        "watchdog_script": "",
        "watchdog_pid_file": "",
        "watchdog_log": "",
        "install_target_exists": False,
        "watchdog_running": False,
    }
    if auto_restart_cfg:
        daemon_installer = PROJECT_ROOT / auto_restart_cfg.get("daemon_installer", "")
        request_script = PROJECT_ROOT / auto_restart_cfg.get("request_script", "")
        watchdog_script = PROJECT_ROOT / auto_restart_cfg.get("watchdog_script", "")
        watchdog_pid_file = _expand_user_path(auto_restart_cfg.get("watchdog_pid_file", ""))
        watchdog_log = _expand_user_path(auto_restart_cfg.get("watchdog_log", ""))
        if auto_restart["platform"] == "darwin":
            install_target = _expand_user_path(auto_restart_cfg.get("launch_agent", ""))
        else:
            install_target = _expand_user_path(auto_restart_cfg.get("systemd_unit", ""))

        pid = None
        try:
            pid = int(watchdog_pid_file.read_text(encoding="utf-8").strip())
        except Exception:
            pid = None

        watchdog_running = False
        if pid is not None:
            try:
                os.kill(pid, 0)
                watchdog_running = True
            except OSError:
                watchdog_running = False

        auto_restart.update({
            "daemon_installer": str(daemon_installer.relative_to(PROJECT_ROOT)) if daemon_installer.exists() else auto_restart_cfg.get("daemon_installer", ""),
            "request_script": str(request_script.relative_to(PROJECT_ROOT)) if request_script.exists() else auto_restart_cfg.get("request_script", ""),
            "watchdog_script": str(watchdog_script.relative_to(PROJECT_ROOT)) if watchdog_script.exists() else auto_restart_cfg.get("watchdog_script", ""),
            "watchdog_pid_file": str(watchdog_pid_file),
            "watchdog_log": str(watchdog_log),
            "install_target": str(install_target),
            "install_target_exists": install_target.exists(),
            "watchdog_running": watchdog_running,
        })

        if not (daemon_installer.exists() and request_script.exists() and watchdog_script.exists()):
            failures += 1
        if not install_target.exists() or not watchdog_running:
            warnings += 1

    return {
        "config_path": str(OPS_ROLLOUT_CONFIG_PATH),
        "status": _calc_status(failures, warnings),
        "cron_jobs": cron_jobs,
        "collab_targets": collab_targets,
        "required_env": required_env,
        "auto_restart": auto_restart,
        "runbook": {
            "state_root": str(state_root.relative_to(PROJECT_ROOT)),
            "docs_root": str(docs_root.relative_to(PROJECT_ROOT)),
            "active_run_count": active_run_count,
            "progress_guide_found": progress_guide is not None,
            "progress_guide_path": str(progress_guide) if progress_guide else "",
            "latest_audit": str(latest_audit.relative_to(PROJECT_ROOT)) if latest_audit else "",
        },
    }


def cmd_validate_config(_args: argparse.Namespace) -> int:
    cfg = load_orchestration_config(force_reload=True)
    ops_validation = _build_ops_validation(cfg)
    summary = {
        "organizations": [org.id for org in cfg.list_orgs()],
        "team_profiles": sorted(cfg.team_profiles.keys()),
        "verification_profiles": sorted(cfg.verification_profiles.keys()),
        "phase_policies": sorted(cfg.phase_policies.keys()),
        "status": ops_validation["status"],
        "validation": ops_validation,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if getattr(_args, "strict", False) and ops_validation["status"] != "ok":
        return 1
    return 0


def cmd_export_legacy_bots(args: argparse.Namespace) -> int:
    cfg = load_orchestration_config(force_reload=True)
    target_dir = Path(args.target_dir or cfg.legacy_exports.get("bots_dir", "bots"))
    for org in cfg.list_orgs():
        export = cfg.export_legacy_bot_yaml(org)
        export.setdefault("comment", "generated from canonical orchestration config")
        _write_yaml(target_dir / f"{org.id}.yaml", export)
    print(f"exported {len(cfg.list_orgs())} bot configs -> {target_dir}")
    return 0


def cmd_export_pm_memory(args: argparse.Namespace) -> int:
    cfg = load_orchestration_config(force_reload=True)
    target_dir = Path(args.target_dir or (Path.home() / ".ai-org" / "memory"))
    target_dir.mkdir(parents=True, exist_ok=True)
    for org in cfg.list_orgs():
        content = (
            "## [CORE] PM 정체성\n"
            f"- 봇명: @{org.username} ({org.id})\n"
            f"- 역할: {org.role}\n"
            f"- 전문분야: {', '.join(org.specialties)}\n"
            f"- 방향성: {org.direction}\n"
        )
        if org.team.get("preferred_agents"):
            content += f"- 선호 에이전트: {', '.join(org.team['preferred_agents'])}\n"
        (target_dir / f"pm_{org.id}.md").write_text(content, encoding="utf-8")
    print(f"exported {len(cfg.list_orgs())} pm identity files -> {target_dir}")
    return 0


def cmd_describe_org(args: argparse.Namespace) -> int:
    cfg = load_orchestration_config(force_reload=True)
    org = cfg.get_org(args.org_id)
    if org is None:
        print(json.dumps({"error": f"unknown org: {args.org_id}"}, ensure_ascii=False))
        return 1
    payload = {
        "id": org.id,
        "kind": org.kind,
        "engine": org.preferred_engine,
        "team": org.team,
        "identity": org.identity,
        "routing": org.routing,
        "execution": org.execution,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def cmd_route_request(args: argparse.Namespace) -> int:
    orch = PMOrchestrator(
        context_db=_DummyDB(),
        task_graph=_DummyGraph(),
        claim_manager=_DummyClaim(),
        memory=MemoryManager("global"),
        org_id="global",
        telegram_send_func=_noop_send,
    )
    plan = asyncio.run(orch.plan_request(args.text))
    print(json.dumps({
        "lane": plan.lane,
        "route": plan.route,
        "complexity": plan.complexity,
        "rationale": plan.rationale,
        "dept_hints": plan.dept_hints,
        "confidence": plan.confidence,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_init_run(args: argparse.Namespace) -> int:
    runbook = OrchestrationRunbook(PROJECT_ROOT)
    state = runbook.create_run(args.org_id, args.request, phase_policy_name=args.phase_policy)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def cmd_advance_phase(args: argparse.Namespace) -> int:
    runbook = OrchestrationRunbook(PROJECT_ROOT)
    state = runbook.advance_phase(args.run_id, note=args.note)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def cmd_run_status(args: argparse.Namespace) -> int:
    runbook = OrchestrationRunbook(PROJECT_ROOT)
    state = runbook.get_state(args.run_id)
    print(json.dumps(state, ensure_ascii=False, indent=2))
    return 0


def cmd_review_recent(args: argparse.Namespace) -> int:
    script = PROJECT_ROOT / "scripts" / "review_recent_conversations.py"
    cmd = [
        sys.executable,
        str(script),
        "--hours", str(args.hours),
        "--engine", args.engine,
        "--org-id", args.org_id,
        "--limit-lines", str(args.limit_lines),
    ]
    if args.upload:
        cmd.append("--upload")
    env = dict(os.environ)
    result = __import__("subprocess").run(cmd, cwd=str(PROJECT_ROOT), env=env)
    return int(result.returncode)


def cmd_auto_improve_recent(args: argparse.Namespace) -> int:
    script = PROJECT_ROOT / "scripts" / "auto_improve_recent_conversations.py"
    cmd = [
        sys.executable,
        str(script),
        "--hours", str(args.hours),
        "--org-id", args.org_id,
        "--review-engine", args.review_engine,
        "--apply-engine", args.apply_engine,
        "--limit-lines", str(args.limit_lines),
        "--max-actions", str(args.max_actions),
    ]
    if args.push_branch:
        cmd.append("--push-branch")
    if args.create_pr:
        cmd.append("--create-pr")
    if args.upload:
        cmd.append("--upload")
    env = dict(os.environ)
    result = __import__("subprocess").run(cmd, cwd=str(PROJECT_ROOT), env=env)
    return int(result.returncode)


def cmd_send_file(args: argparse.Namespace) -> int:
    target = resolve_delivery_target(args.org_id)
    if target is None:
        print(json.dumps({"error": f"unknown or unconfigured org: {args.org_id}"}, ensure_ascii=False))
        return 1
    ok = asyncio.run(upload_file(target.token, target.chat_id, args.path, args.caption or ""))
    print(json.dumps({"ok": ok, "org_id": args.org_id, "path": args.path}, ensure_ascii=False))
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Orchestration control CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-config")
    validate.add_argument("--strict", action="store_true")
    validate.set_defaults(func=cmd_validate_config)

    export_bots = sub.add_parser("export-legacy-bots")
    export_bots.add_argument("--target-dir", default="")
    export_bots.set_defaults(func=cmd_export_legacy_bots)

    export_memory = sub.add_parser("export-pm-memory")
    export_memory.add_argument("--target-dir", default="")
    export_memory.set_defaults(func=cmd_export_pm_memory)

    describe = sub.add_parser("describe-org")
    describe.add_argument("org_id")
    describe.set_defaults(func=cmd_describe_org)

    route = sub.add_parser("route-request")
    route.add_argument("text")
    route.set_defaults(func=cmd_route_request)

    init_run = sub.add_parser("init-run")
    init_run.add_argument("--org-id", required=True)
    init_run.add_argument("--phase-policy", default="default")
    init_run.add_argument("request")
    init_run.set_defaults(func=cmd_init_run)

    advance = sub.add_parser("advance-phase")
    advance.add_argument("run_id")
    advance.add_argument("--note", default="")
    advance.set_defaults(func=cmd_advance_phase)

    run_status = sub.add_parser("run-status")
    run_status.add_argument("run_id")
    run_status.set_defaults(func=cmd_run_status)

    review = sub.add_parser("review-recent")
    review.add_argument("--hours", type=int, default=24)
    review.add_argument("--engine", default="claude-code", choices=["claude-code", "codex"])
    review.add_argument("--org-id", default="global")
    review.add_argument("--limit-lines", type=int, default=400)
    review.add_argument("--upload", action="store_true")
    review.set_defaults(func=cmd_review_recent)

    auto_improve = sub.add_parser("auto-improve-recent")
    auto_improve.add_argument("--hours", type=int, default=24)
    auto_improve.add_argument("--org-id", default="global")
    auto_improve.add_argument("--review-engine", default="claude-code", choices=["claude-code", "codex"])
    auto_improve.add_argument("--apply-engine", default="claude-code", choices=["claude-code", "codex"])
    auto_improve.add_argument("--limit-lines", type=int, default=500)
    auto_improve.add_argument("--max-actions", type=int, default=1)
    auto_improve.add_argument("--push-branch", action="store_true")
    auto_improve.add_argument("--create-pr", action="store_true")
    auto_improve.add_argument("--upload", action="store_true")
    auto_improve.set_defaults(func=cmd_auto_improve_recent)

    send_file = sub.add_parser("send-file")
    send_file.add_argument("--org-id", default="global")
    send_file.add_argument("--caption", default="")
    send_file.add_argument("path")
    send_file.set_defaults(func=cmd_send_file)

    return parser


def main() -> int:
    _load_runtime_env()
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
