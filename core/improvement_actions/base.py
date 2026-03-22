"""베이스 액션 — 모든 개선 액션의 공통 인터페이스."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class ActionResult:
    """단일 개선 액션 실행 결과."""

    action_name: str
    target: str           # 파일 경로 또는 에러 패턴 명
    success: bool
    message: str
    dry_run: bool = False
    executed_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def __str__(self) -> str:
        status = "✅" if self.success else "❌"
        tag = " [dry_run]" if self.dry_run else ""
        return f"{status} [{self.action_name}]{tag} {self.target}: {self.message}"


class BaseAction:
    """모든 액션이 상속하는 베이스 클래스."""

    name: str = "base_action"

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run

    def run(self, item: "ImprovementItem") -> ActionResult:  # type: ignore[name-defined]
        raise NotImplementedError
