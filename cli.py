"""telegram-ai-org CLI 진입점 모음.

PyPI 설치 후 다음 명령어를 사용합니다:
  aiorg-pm       — PM 봇 실행 (python main.py 와 동일)
  aiorg-worker   — 워커 봇 실행
  aiorg-cli      — 오케스트레이션 CLI
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent


def pm() -> None:
    """PM 봇 진입점. `python main.py` 와 동일하게 동작합니다."""
    sys.argv[0] = "aiorg-pm"
    runpy.run_path(str(_PROJECT_ROOT / "main.py"), run_name="__main__")


if __name__ == "__main__":
    pm()
