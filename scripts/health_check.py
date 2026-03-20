#!/usr/bin/env python3
"""health_check.py — 모든 봇의 PID 및 heartbeat 상태 확인.

사용법:
    python scripts/health_check.py          # 상태 출력
    python scripts/health_check.py --json   # JSON 출력
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
BOT_IDS = [
    "aiorg_pm_bot",
    "aiorg_engineering_bot",
    "aiorg_design_bot",
    "aiorg_growth_bot",
    "aiorg_product_bot",
    "aiorg_research_bot",
    "aiorg_ops_bot",
]


def _runtime_pid_file(org_id: str) -> Path:
    return Path(f"/tmp/telegram-ai-org-{org_id}.pid")


def _permanent_pid_file(org_id: str) -> Path:
    return Path.home() / ".ai-org" / "bots" / f"{org_id}.pid"


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except Exception:
        return None


def _pid_alive(pid: int | None) -> bool:
    if pid is None:
        return False
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid)],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _scan_live_bot_pids() -> dict[str, list[int]]:
    """ps auxを使って実際に生きているbotプロセスを探す."""
    live: dict[str, list[int]] = {}
    try:
        result = subprocess.run(
            ["ps", "eww", "-ax", "-o", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=10,
        )
        import re
        for line in result.stdout.splitlines():
            line = line.strip()
            pid_text, _, command = line.partition(" ")
            if not pid_text.isdigit() or "main.py" not in command or "PM_ORG_NAME=" not in command:
                continue
            m = re.search(r"PM_ORG_NAME=(\S+)", command)
            if m:
                org_id = m.group(1)
                live.setdefault(org_id, []).append(int(pid_text))
    except Exception:
        pass
    return live


def check_all_bots() -> list[dict]:
    live_pids = _scan_live_bot_pids()
    results = []
    for org_id in BOT_IDS:
        # PID 파일 확인
        runtime_pid = _read_pid(_runtime_pid_file(org_id))
        permanent_pid = _read_pid(_permanent_pid_file(org_id))
        pid_file_alive = _pid_alive(runtime_pid) or _pid_alive(permanent_pid)

        # ps 스캔으로 직접 확인
        ps_pids = live_pids.get(org_id, [])
        ps_alive = bool(ps_pids)

        alive = pid_file_alive or ps_alive
        pid = ps_pids[0] if ps_pids else (runtime_pid or permanent_pid)

        results.append({
            "org_id": org_id,
            "alive": alive,
            "pid": pid,
            "status": "UP" if alive else "DOWN",
        })
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Bot health check")
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    args = parser.parse_args()

    results = check_all_bots()

    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    print(f"{'Bot ID':<35} {'Status':<8} {'PID'}")
    print("-" * 60)
    all_up = True
    for r in results:
        pid_str = str(r["pid"]) if r["pid"] else "-"
        status = r["status"]
        if not r["alive"]:
            all_up = False
        print(f"{r['org_id']:<35} {status:<8} {pid_str}")

    print()
    if all_up:
        print("✅ 모든 봇 정상 동작 중")
    else:
        down = [r["org_id"] for r in results if not r["alive"]]
        print(f"❌ 다운된 봇: {', '.join(down)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
