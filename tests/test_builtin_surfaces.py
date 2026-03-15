from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.builtin_surfaces import recommend_builtin_surfaces


def test_recommend_builtin_surfaces_for_status_task() -> None:
    surfaces = recommend_builtin_surfaces("봇 상태 확인하고 재시작해줘", org_id="global")
    commands = [surface.command for surface in surfaces]
    assert any("bot_control.sh status all" in command for command in commands)


def test_recommend_builtin_surfaces_for_review_task() -> None:
    surfaces = recommend_builtin_surfaces("최근 대화 로그를 검토하고 평가해줘", org_id="global")
    commands = [surface.command for surface in surfaces]
    assert any("tools/orchestration_cli.py auto-improve-recent" in command for command in commands)
