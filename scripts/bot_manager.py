#!/usr/bin/env python3
"""봇 프로세스 관리 — 시작/중지/목록/전체재시작.

사용법:
  python scripts/bot_manager.py list
  python scripts/bot_manager.py start <token> <org_id> <chat_id>
  python scripts/bot_manager.py stop <org_id>
  python scripts/bot_manager.py restart-all
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent
PID_DIR = Path.home() / ".ai-org" / "bots"


def start_bot(token: str, org_id: str, chat_id: int) -> int:
    """새 봇 프로세스를 시작하고 PID를 반환한다."""
    PID_DIR.mkdir(parents=True, exist_ok=True)
    env = {
        **os.environ,
        "PM_BOT_TOKEN": token,
        "TELEGRAM_GROUP_CHAT_ID": str(chat_id),
        "PM_ORG_NAME": org_id,
    }
    proc = subprocess.Popen(
        [sys.executable, str(PROJECT_DIR / "main.py")],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(PROJECT_DIR),
    )
    (PID_DIR / f"{org_id}.pid").write_text(str(proc.pid))
    # 재시작에 필요한 메타데이터 저장
    meta = {"token": token, "org_id": org_id, "chat_id": chat_id}
    (PID_DIR / f"{org_id}.json").write_text(json.dumps(meta))
    return proc.pid


def stop_bot(org_id: str) -> bool:
    """봇 프로세스를 중지한다. 성공하면 True 반환."""
    pid_file = PID_DIR / f"{org_id}.pid"
    if not pid_file.exists():
        return False
    pid = int(pid_file.read_text().strip())
    try:
        os.kill(pid, signal.SIGTERM)
        pid_file.unlink()
        return True
    except ProcessLookupError:
        pid_file.unlink(missing_ok=True)
        return False


def restart_all_bots() -> None:
    """pm_bot + 모든 조직봇을 순서대로 재시작한다 (Telegram Conflict 방지: 2초 딜레이)."""
    restart_script = PROJECT_DIR / "scripts" / "restart_bots.sh"
    subprocess.run(["bash", str(restart_script)], check=False)


def list_bots() -> list[dict]:
    """실행 중인 봇 목록을 반환한다."""
    if not PID_DIR.exists():
        return []
    bots = []
    for pid_file in sorted(PID_DIR.glob("*.pid")):
        org_id = pid_file.stem
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 0)  # 프로세스 존재 확인 (신호 미발송)
            status = "running"
        except ProcessLookupError:
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
