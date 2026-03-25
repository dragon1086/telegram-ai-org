#!/usr/bin/env python3
"""Periodic deployment healthcheck for all organization bots."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = PROJECT_ROOT / "reports" / "ops" / "bot-deploy-healthcheck.json"
WATCHDOG_PID_FILE = Path("/tmp/bot-watchdog.pid")
WATCHDOG_LOG_FILE = Path.home() / ".ai-org" / "bot-watchdog.log"
LAUNCH_AGENT_FILE = Path.home() / "Library" / "LaunchAgents" / "ai.telegram-ai-org.bot-watchdog.plist"
SYSTEMD_UNIT_FILE = Path.home() / ".config" / "systemd" / "user" / "telegram-ai-org-watchdog.service"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


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


def _read_pid() -> int | None:
    try:
        return int(WATCHDOG_PID_FILE.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def _watchdog_status() -> dict:
    pid = _read_pid()
    running = _pid_alive(pid)
    last_log_line = ""
    if WATCHDOG_LOG_FILE.exists():
        try:
            lines = WATCHDOG_LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
            last_log_line = lines[-1] if lines else ""
        except Exception:
            last_log_line = ""

    return {
        "enabled": True,
        "pid": pid,
        "running": running,
        "pid_file_exists": WATCHDOG_PID_FILE.exists(),
        "log_exists": WATCHDOG_LOG_FILE.exists(),
        "launch_agent_exists": LAUNCH_AGENT_FILE.exists(),
        "systemd_unit_exists": SYSTEMD_UNIT_FILE.exists(),
        "last_log_line": last_log_line,
    }


def main() -> int:
    from scripts.health_check import check_all_bots

    bots = check_all_bots()
    watchdog = _watchdog_status()
    payload = {
        "checked_at": datetime.now(UTC).isoformat(),
        "bots": bots,
        "down_bots": [bot["org_id"] for bot in bots if not bot["alive"]],
        "watchdog": watchdog,
        "status": "ok",
    }

    if payload["down_bots"] or not watchdog["running"]:
        payload["status"] = "fail"

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(payload, ensure_ascii=False))
    return 0 if payload["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
