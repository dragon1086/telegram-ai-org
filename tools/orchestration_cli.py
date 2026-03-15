#!/usr/bin/env python3
"""Canonical orchestration CLI.

This CLI is the stable control surface for config validation and legacy asset export.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.memory_manager import MemoryManager
from core.orchestration_config import load_orchestration_config
from core.orchestration_runbook import OrchestrationRunbook
from core.pm_orchestrator import PMOrchestrator


class _DummyDB:
    db_path = ":memory:"


class _DummyGraph:
    pass


class _DummyClaim:
    pass


async def _noop_send(_chat_id: int, _text: str) -> None:
    return None


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def cmd_validate_config(_args: argparse.Namespace) -> int:
    cfg = load_orchestration_config(force_reload=True)
    summary = {
        "organizations": [org.id for org in cfg.list_orgs()],
        "team_profiles": sorted(cfg.team_profiles.keys()),
        "verification_profiles": sorted(cfg.verification_profiles.keys()),
        "phase_policies": sorted(cfg.phase_policies.keys()),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Orchestration control CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-config")
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

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
