#!/usr/bin/env python3
"""봇 프로세스 관리 — canonical organizations 기준 프로세스 관리.

사용법:
  python scripts/bot_manager.py list
  python scripts/bot_manager.py start <token> <org_id> <chat_id>
  python scripts/bot_manager.py stop <org_id>
  python scripts/bot_manager.py restart-all
"""
from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
PID_DIR = Path.home() / ".ai-org" / "bots"

# 봇 전용 워크트리 경로 (main 브랜치 고정)
_BOT_RUNTIME_WORKTREE = ".worktrees/bot-runtime"


def _resolve_runtime_dir() -> Path:
    """봇 실행용 디렉토리 결정.

    .worktrees/bot-runtime 워크트리가 존재하면 항상 main 브랜치 코드로 실행.
    없으면 PROJECT_DIR 폴백 (기존 동작).
    """
    candidate = PROJECT_DIR / _BOT_RUNTIME_WORKTREE
    if candidate.is_dir() and (candidate / "main.py").exists():
        return candidate
    return PROJECT_DIR


def _runtime_pid_file(org_id: str) -> Path:
    return Path(f"/tmp/telegram-ai-org-{org_id}.pid")


def _read_pid(path: Path) -> int | None:
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def _process_command(pid: int) -> str:
    try:
        return subprocess.check_output(
            ["ps", "eww", "-p", str(pid), "-o", "command="],
            text=True,
        ).strip()
    except subprocess.CalledProcessError:
        return ""


def _process_matches_org(pid: int, org_id: str) -> bool:
    command = _process_command(pid)
    return bool(command and "main.py" in command and f"PM_ORG_NAME={org_id}" in command)


def _scan_live_bot_pids() -> dict[str, set[int]]:
    try:
        output = subprocess.check_output(
            ["ps", "eww", "-ax", "-o", "pid=,command="],
            text=True,
        )
    except subprocess.CalledProcessError:
        return {}

    live: dict[str, set[int]] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        pid_text, _, command = line.partition(" ")
        if not pid_text.isdigit() or "main.py" not in command or "PM_ORG_NAME=" not in command:
            continue
        match = re.search(r"PM_ORG_NAME=([^\s]+)", command)
        if not match:
            continue
        live.setdefault(match.group(1), set()).add(int(pid_text))
    return live


def _find_live_pids(org_id: str) -> set[int]:
    return set(_scan_live_bot_pids().get(org_id, set()))


def _known_pids_for_org(org_id: str) -> set[int]:
    pids = _find_live_pids(org_id)
    for path in (PID_DIR / f"{org_id}.pid", _runtime_pid_file(org_id)):
        pid = _read_pid(path)
        if pid is not None and _process_matches_org(pid, org_id):
            pids.add(pid)
    return pids


def _cleanup_tracking_files(org_id: str) -> None:
    for path in (
        PID_DIR / f"{org_id}.pid",
        PID_DIR / f"{org_id}.json",
        _runtime_pid_file(org_id),
    ):
        path.unlink(missing_ok=True)


def start_bot(token: str, org_id: str, chat_id: int) -> int:
    """새 봇 프로세스를 시작하고 PID를 반환한다."""
    PID_DIR.mkdir(parents=True, exist_ok=True)
    stop_bot(org_id)
    env = {
        **os.environ,
        "PM_BOT_TOKEN": token,
        "TELEGRAM_GROUP_CHAT_ID": str(chat_id),
        "PM_ORG_NAME": org_id,
    }
    runtime_dir = _resolve_runtime_dir()
    proc = subprocess.Popen(
        [sys.executable, str(runtime_dir / "main.py")],
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=open(Path.home() / ".ai-org" / f"{org_id}.log", "a"),
        stderr=subprocess.STDOUT,
        cwd=str(runtime_dir),
        start_new_session=True,
    )
    (PID_DIR / f"{org_id}.pid").write_text(str(proc.pid))
    meta = {"token": token, "org_id": org_id, "chat_id": chat_id}
    (PID_DIR / f"{org_id}.json").write_text(json.dumps(meta))
    return proc.pid


def stop_bot(org_id: str) -> bool:
    """봇 프로세스를 중지한다. 성공하면 True 반환."""
    had_tracking = any(
        path.exists()
        for path in (
            PID_DIR / f"{org_id}.pid",
            PID_DIR / f"{org_id}.json",
            _runtime_pid_file(org_id),
        )
    )
    pids = _known_pids_for_org(org_id)
    stopped = False

    # Phase 1: Kill entire process groups via SIGTERM.
    # Since start_bot() uses start_new_session=True, each main.py PID is also
    # the PGID (Process Group ID). Killing the process group ensures that child
    # processes (claude_agent_sdk, codex, etc.) are terminated together, preventing
    # orphan processes (PPID=1) that survive after main.py exits.
    for pid in sorted(pids):
        try:
            os.killpg(pid, signal.SIGTERM)
            stopped = True
        except (ProcessLookupError, PermissionError, OSError):
            # Process group may not exist or we lack permission; fall through
            # to per-PID kill below.
            pass

    # Phase 2: Per-PID SIGTERM as fallback for any processes not covered by
    # the process group kill (e.g. if the PID is not a PGID).
    for pid in sorted(pids):
        try:
            os.kill(pid, signal.SIGTERM)
            stopped = True
        except ProcessLookupError:
            continue

    # Phase 3: Wait for graceful shutdown.
    deadline = time.time() + 5.0
    while time.time() < deadline:
        remaining = _find_live_pids(org_id)
        if not remaining:
            break
        time.sleep(0.2)

    # Phase 4: Force-kill any remaining processes (group first, then per-PID).
    for pid in sorted(_find_live_pids(org_id)):
        try:
            os.killpg(pid, signal.SIGKILL)
            stopped = True
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            os.kill(pid, signal.SIGKILL)
            stopped = True
        except ProcessLookupError:
            continue

    _cleanup_tracking_files(org_id)
    return stopped or had_tracking


def restart_all_bots() -> None:
    runtime_dir = _resolve_runtime_dir()
    restart_script = runtime_dir / "scripts" / "restart_bots.sh"
    subprocess.run(["bash", str(restart_script)], check=False)


def list_bots() -> list[dict]:
    tracked_orgs = set()
    if PID_DIR.exists():
        tracked_orgs.update(path.stem for path in PID_DIR.glob("*.pid"))
        tracked_orgs.update(path.stem for path in PID_DIR.glob("*.json"))
    tracked_orgs.update(_scan_live_bot_pids())

    bots = []
    for org_id in sorted(tracked_orgs):
        live_pids = sorted(_find_live_pids(org_id))
        if live_pids:
            pid: int | str = live_pids[0] if len(live_pids) == 1 else ",".join(str(p) for p in live_pids)
            status = "running"
        else:
            pid = _read_pid(PID_DIR / f"{org_id}.pid") or "-"
            status = "dead"
        bots.append({"org_id": org_id, "pid": pid, "status": status})
    return bots


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "list":
        bots = list_bots()
        if not bots:
            print("실행 중인 봇 없음.")
        for b in bots:
            print(f"  {b['org_id']:20s}  PID={b['pid']}  [{b['status']}]")

    elif cmd == "start":
        if len(sys.argv) < 5:
            print("사용법: bot_manager.py start <token> <org_id> <chat_id>")
            sys.exit(1)
        pid = start_bot(token=sys.argv[2], org_id=sys.argv[3], chat_id=int(sys.argv[4]))
        print(f"✅ {sys.argv[3]} 시작됨 (PID={pid})")

    elif cmd == "stop":
        if len(sys.argv) < 3:
            print("사용법: bot_manager.py stop <org_id>")
            sys.exit(1)
        ok = stop_bot(sys.argv[2])
        print(f"{'✅ 중지됨' if ok else '❌ 실패 (PID 파일 없거나 이미 중지됨)'}: {sys.argv[2]}")

    elif cmd == "restart-all":
        restart_all_bots()

    else:
        print(f"알 수 없는 명령: {cmd}")
        sys.exit(1)
