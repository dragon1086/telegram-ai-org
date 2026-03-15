"""레포 내장 스크립트/CLI 표면을 작업 성격에 맞게 추천한다."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BuiltinSurface:
    name: str
    command: str
    purpose: str


_BASE_SURFACES = [
    BuiltinSurface(
        name="orchestration_cli",
        command="./.venv/bin/python tools/orchestration_cli.py validate-config",
        purpose="오케스트레이션 설정 검증과 조직/런북 상태 확인",
    ),
    BuiltinSurface(
        name="bot_control",
        command="bash scripts/bot_control.sh status all",
        purpose="봇 프로세스 상태 확인과 재기동",
    ),
    BuiltinSurface(
        name="conversation_review",
        command="./.venv/bin/python scripts/review_recent_conversations.py --hours 6 --engine claude-code",
        purpose="최근 대화/작업 로그 품질 점검",
    ),
]


def recommend_builtin_surfaces(task: str, org_id: str = "global") -> list[BuiltinSurface]:
    lowered = (task or "").lower()
    selected: list[BuiltinSurface] = []

    def add(name: str) -> None:
        for surface in _BASE_SURFACES:
            if surface.name == name and surface not in selected:
                selected.append(surface)

    add("orchestration_cli")
    if any(token in lowered for token in ("bot", "봇", "restart", "재시작", "status", "상태", "process", "세션")):
        add("bot_control")
    if any(token in lowered for token in ("review", "audit", "평가", "검토", "recent", "대화", "로그")):
        add("conversation_review")

    if not selected:
        selected = _BASE_SURFACES[:1]

    return selected
