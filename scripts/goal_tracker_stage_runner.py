#!/usr/bin/env python3
"""GoalTracker cron stage runner.

hourly openclaw cron jobs call this script with one of:
idle -> evaluate -> replan -> dispatch

Each stage stores a small handoff snapshot so later stages can reuse the
previous stage result without re-reading ambiguous state from logs.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = PROJECT_ROOT / "reports" / "ops" / "goal_tracker_stage_state.json"
MAX_STATE_AGE_SEC = 90 * 60

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_env() -> None:
    for env_path in (Path.home() / ".ai-org" / "config.yaml", PROJECT_ROOT / ".env"):
        if not env_path.exists():
            continue
        for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _read_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _write_state(payload: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _state_is_fresh(state: dict[str, Any], stage: str) -> bool:
    if state.get("stage") != stage:
        return False
    updated_at = state.get("updated_at")
    if not updated_at:
        return False
    try:
        age = (datetime.now(UTC) - datetime.fromisoformat(updated_at)).total_seconds()
    except ValueError:
        return False
    return age <= MAX_STATE_AGE_SEC


async def _noop_send(*_args, **_kwargs) -> None:
    return None


async def _bootstrap_tracker():
    from core.claim_manager import ClaimManager
    from core.context_db import ContextDB
    from core.goal_tracker import GoalTracker
    from core.memory_manager import MemoryManager
    from core.pm_orchestrator import PMOrchestrator
    from core.task_graph import TaskGraph

    db = ContextDB()
    await db.initialize()
    orchestrator = PMOrchestrator(
        context_db=db,
        task_graph=TaskGraph(db),
        claim_manager=ClaimManager(),
        memory=MemoryManager("aiorg_pm_bot"),
        org_id="aiorg_pm_bot",
        telegram_send_func=_noop_send,
    )
    tracker = GoalTracker(
        context_db=db,
        orchestrator=orchestrator,
        telegram_send_func=_noop_send,
        org_id="aiorg_pm_bot",
    )
    return tracker


async def _active_goals(tracker) -> list[dict[str, Any]]:
    goals = await tracker.get_active_goals()
    return [
        {
            "id": goal["id"],
            "title": goal.get("title", ""),
            "chat_id": goal.get("chat_id", 0),
            "iteration": goal.get("iteration", 0),
            "max_iterations": goal.get("max_iterations", 0),
            "status": goal.get("status", ""),
        }
        for goal in goals
    ]


async def _run_idle(tracker) -> int:
    goals = await _active_goals(tracker)
    state = {
        "stage": "idle",
        "updated_at": _now_iso(),
        "active_goals": goals,
    }
    _write_state(state)
    print(f"[goal_tracker_stage] idle active_goals={len(goals)}")
    return 0


async def _evaluate_goals(tracker) -> list[dict[str, Any]]:
    evaluations: list[dict[str, Any]] = []
    for goal in await tracker.get_active_goals():
        status = await tracker.evaluate_progress(goal["id"])
        if status.achieved:
            await tracker.update_goal_status(goal["id"], "achieved")
        evaluations.append(
            {
                "goal_id": goal["id"],
                "title": goal.get("title", ""),
                "chat_id": goal.get("chat_id", 0),
                "achieved": status.achieved,
                "progress_summary": status.progress_summary,
                "remaining_work": status.remaining_work,
                "done_count": status.done_count,
                "total_count": status.total_count,
                "confidence": status.confidence,
            }
        )
    return evaluations


async def _run_evaluate(tracker) -> int:
    evaluations = await _evaluate_goals(tracker)
    state = {
        "stage": "evaluate",
        "updated_at": _now_iso(),
        "evaluations": evaluations,
    }
    _write_state(state)
    pending = sum(1 for item in evaluations if not item["achieved"])
    print(
        f"[goal_tracker_stage] evaluate total={len(evaluations)} pending={pending}"
    )
    return 0


async def _run_replan(tracker) -> int:
    state = _read_state()
    evaluations = state.get("evaluations", []) if _state_is_fresh(state, "evaluate") else []
    if not evaluations:
        evaluations = await _evaluate_goals(tracker)

    queue = [
        {
            "goal_id": item["goal_id"],
            "title": item.get("title", ""),
            "chat_id": item.get("chat_id", 0),
            "remaining_work": item.get("remaining_work", "") or "태스크 재분해 필요",
            "progress_summary": item.get("progress_summary", ""),
            "confidence": item.get("confidence", 0.0),
        }
        for item in evaluations
        if not item.get("achieved")
    ]
    new_state = {
        "stage": "replan",
        "updated_at": _now_iso(),
        "dispatch_queue": queue,
    }
    _write_state(new_state)
    print(f"[goal_tracker_stage] replan queued={len(queue)}")
    return 0


async def _run_dispatch(tracker) -> int:
    state = _read_state()
    queue = state.get("dispatch_queue", []) if _state_is_fresh(state, "replan") else []
    if not queue:
        await _run_replan(tracker)
        state = _read_state()
        queue = state.get("dispatch_queue", [])

    dispatched: list[dict[str, Any]] = []
    for item in queue:
        goal_id = item["goal_id"]
        new_iter, max_iter = await tracker.tick_iteration(goal_id)
        if new_iter > max_iter:
            await tracker.update_goal_status(goal_id, "max_iterations_reached")
            dispatched.append(
                {
                    "goal_id": goal_id,
                    "result": "max_iterations_reached",
                    "iteration": new_iter,
                    "max_iterations": max_iter,
                    "task_count": 0,
                }
            )
            continue

        task_ids = await tracker.replan(
            goal_id=goal_id,
            remaining_work=item.get("remaining_work", ""),
            chat_id=int(item.get("chat_id", 0) or 0),
        )
        dispatched.append(
            {
                "goal_id": goal_id,
                "result": "dispatched" if task_ids else "no_tasks",
                "iteration": new_iter,
                "max_iterations": max_iter,
                "task_count": len(task_ids),
                "task_ids": task_ids,
            }
        )

    new_state = {
        "stage": "dispatch",
        "updated_at": _now_iso(),
        "dispatch_results": dispatched,
    }
    _write_state(new_state)
    total_tasks = sum(item.get("task_count", 0) for item in dispatched)
    print(
        f"[goal_tracker_stage] dispatch goals={len(dispatched)} tasks={total_tasks}"
    )
    return 0


async def _main_async(stage: str) -> int:
    _load_env()
    tracker = await _bootstrap_tracker()
    if stage == "idle":
        return await _run_idle(tracker)
    if stage == "evaluate":
        return await _run_evaluate(tracker)
    if stage == "replan":
        return await _run_replan(tracker)
    if stage == "dispatch":
        return await _run_dispatch(tracker)
    raise ValueError(f"unsupported stage: {stage}")


def main() -> int:
    parser = argparse.ArgumentParser(description="GoalTracker cron stage runner")
    parser.add_argument(
        "--stage",
        required=True,
        choices=("idle", "evaluate", "replan", "dispatch"),
    )
    args = parser.parse_args()
    return asyncio.run(_main_async(args.stage))


if __name__ == "__main__":
    raise SystemExit(main())
