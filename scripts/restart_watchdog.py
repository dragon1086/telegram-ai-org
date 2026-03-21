#!/usr/bin/env python3
"""재기동 플래그 감지 → 봇 재시작.

SelfCodeImprover가 core/ 파일을 수정하면 data/.restart_requested 플래그를 생성한다.
이 스크립트가 해당 플래그를 감지해 start_all.sh를 실행한다.

사용법:
    python scripts/restart_watchdog.py
"""
import subprocess
import time
from pathlib import Path

RESTART_FLAG = Path(__file__).parent.parent / "data" / ".restart_requested"
REPO_ROOT = Path(__file__).parent.parent
START_SCRIPT = REPO_ROOT / "scripts" / "start_all.sh"
POLL_INTERVAL = 10  # seconds


def main() -> None:
    print("[restart_watchdog] 시작 — 재기동 플래그 감지 대기 중")
    while True:
        if RESTART_FLAG.exists():
            print("[restart_watchdog] 재기동 플래그 감지 → 봇 재시작")
            RESTART_FLAG.unlink()
            if START_SCRIPT.exists():
                subprocess.run(["bash", str(START_SCRIPT)], check=False)
            else:
                print(f"[restart_watchdog] {START_SCRIPT} 없음 — 수동 재시작 필요")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
