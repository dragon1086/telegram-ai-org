"""OKR 대시보드 — Telegram용 텍스트 기반 OKR 시각화.

OKR 계층 구조, 진척률, 마감 상태를 한눈에 볼 수 있는
텍스트 대시보드를 생성한다.

출력 형식:
    📊 OKR 대시보드 (2026-04-02)
    ━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    🎯 MAU 10만 달성 [▓▓▓▓▓▓░░░░] 60%  ⏰ D-89
    ├─ 📈 Q2 가입 3만 [▓▓▓▓▓░░░░░] 50%  (15000/30000명)
    │  ├─ 📋 SNS 캠페인 [▓▓▓▓▓▓▓░░░] 70%
    │  │  ├─ ✅ 인스타 광고 [▓▓▓▓▓▓▓▓▓▓] 100%
    │  │  └─ 🔄 틱톡 광고 [▓▓▓▓░░░░░░] 40%
    │  └─ 📋 SEO 개선 [▓▓▓░░░░░░░] 30%
    └─ 📈 리텐션 40% [▓▓▓▓▓▓░░░░] 60%  (32/40%)
"""
from __future__ import annotations

from datetime import datetime, timezone

from core.context_db import ContextDB
from core.goal_tracker import DeadlineChecker, GoalTracker, GoalType


class OKRDashboard:
    """OKR 텍스트 대시보드 생성기."""

    # 진행 바 설정
    BAR_LENGTH = 10
    BAR_FILLED = "▓"
    BAR_EMPTY = "░"

    # 아이콘
    ICONS = {
        "objective": "🎯",
        "key_result": "📈",
        "initiative": "📋",
        "task": "📌",
    }

    STATUS_ICONS = {
        "active": "🔄",
        "achieved": "✅",
        "done": "✅",
        "completed": "✅",
        "cancelled": "❌",
        "stagnated": "⚠️",
    }

    def __init__(
        self,
        context_db: ContextDB,
        goal_tracker: GoalTracker,
    ) -> None:
        self._db = context_db
        self._tracker = goal_tracker
        self._deadline_checker = DeadlineChecker(context_db)

    async def generate_full_dashboard(
        self,
        date: str | None = None,
    ) -> str:
        """전체 OKR 대시보드 생성."""
        if not date:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        objectives = await self._db.get_goals_by_type(
            GoalType.OBJECTIVE.value, status="active",
        )

        if not objectives:
            return f"📊 OKR 대시보드 ({date})\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n등록된 Objective가 없습니다."

        lines = [
            f"📊 OKR 대시보드 ({date})",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "",
        ]

        for i, obj in enumerate(objectives):
            progress = await self._tracker.calculate_progress(obj["id"])
            obj_lines = await self._render_objective(obj, progress, date)
            lines.extend(obj_lines)
            if i < len(objectives) - 1:
                lines.append("")

        # 요약 통계
        lines.append("")
        lines.append(await self._generate_summary(objectives, date))

        return "\n".join(lines)

    async def generate_objective_detail(
        self,
        objective_id: str,
        date: str | None = None,
    ) -> str:
        """특정 Objective 상세 대시보드."""
        if not date:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        obj = await self._db.get_goal(objective_id)
        if not obj:
            return f"❌ Objective를 찾을 수 없습니다: {objective_id}"

        progress = await self._tracker.calculate_progress(objective_id)
        lines = await self._render_objective(obj, progress, date)
        return "\n".join(lines)

    async def _render_objective(
        self,
        obj: dict,
        progress: float,
        date: str,
    ) -> list[str]:
        """Objective + 하위 계층 렌더링."""
        lines = []
        deadline_str = self._format_deadline(obj, date)
        bar = self._progress_bar(progress)
        pct = int(progress * 100)

        lines.append(
            f"🎯 {obj.get('title', obj['id'])} "
            f"{bar} {pct}%  {deadline_str}"
        )

        # KR 하위
        krs = await self._db.get_children_goals(obj["id"])
        for i, kr in enumerate(krs):
            is_last_kr = i == len(krs) - 1
            kr_progress = await self._tracker.calculate_progress(kr["id"])
            kr_lines = await self._render_kr(
                kr, kr_progress, date, is_last_kr,
            )
            lines.extend(kr_lines)

        return lines

    async def _render_kr(
        self,
        kr: dict,
        progress: float,
        date: str,
        is_last: bool,
    ) -> list[str]:
        """Key Result + 하위 렌더링."""
        lines = []
        prefix = "└─" if is_last else "├─"
        child_prefix = "   " if is_last else "│  "

        bar = self._progress_bar(progress)
        pct = int(progress * 100)
        kpi_str = self._format_kpi(kr)

        lines.append(
            f"{prefix} 📈 {kr.get('title', kr['id'])} "
            f"{bar} {pct}%  {kpi_str}"
        )

        # Initiative 하위
        initiatives = await self._db.get_children_goals(kr["id"])
        for i, init in enumerate(initiatives):
            is_last_init = i == len(initiatives) - 1
            init_progress = await self._tracker.calculate_progress(
                init["id"],
            )
            init_lines = await self._render_initiative(
                init, init_progress, child_prefix, is_last_init,
            )
            lines.extend(init_lines)

        return lines

    async def _render_initiative(
        self,
        init: dict,
        progress: float,
        parent_prefix: str,
        is_last: bool,
    ) -> list[str]:
        """Initiative + Task 렌더링."""
        lines = []
        prefix = f"{parent_prefix}└─" if is_last else f"{parent_prefix}├─"
        child_prefix = f"{parent_prefix}   " if is_last else f"{parent_prefix}│  "

        bar = self._progress_bar(progress)
        pct = int(progress * 100)

        lines.append(
            f"{prefix} 📋 {init.get('title', init['id'])} "
            f"{bar} {pct}%"
        )

        # Task 하위
        tasks = await self._db.get_children_goals(init["id"])
        for i, task in enumerate(tasks):
            is_last_task = i == len(tasks) - 1
            task_prefix = (
                f"{child_prefix}└─" if is_last_task
                else f"{child_prefix}├─"
            )
            task_progress = task.get("progress", 0) or 0
            bar = self._progress_bar(task_progress)
            pct = int(task_progress * 100)
            status_icon = self.STATUS_ICONS.get(
                task.get("status", "active"), "🔄",
            )

            lines.append(
                f"{task_prefix} {status_icon} {task.get('title', task['id'])} "
                f"{bar} {pct}%"
            )

        return lines

    def _progress_bar(self, progress: float) -> str:
        """진행 바 생성."""
        filled = int(progress * self.BAR_LENGTH)
        filled = max(0, min(filled, self.BAR_LENGTH))
        empty = self.BAR_LENGTH - filled
        return f"[{self.BAR_FILLED * filled}{self.BAR_EMPTY * empty}]"

    def _format_deadline(self, goal: dict, today: str) -> str:
        """마감일 D-day 포맷."""
        deadline = goal.get("deadline")
        if not deadline:
            return ""
        try:
            deadline_dt = datetime.strptime(deadline, "%Y-%m-%d")
            today_dt = datetime.strptime(today, "%Y-%m-%d")
            days = (deadline_dt - today_dt).days
            if days < 0:
                return f"🚨 D+{abs(days)}"
            if days <= 3:
                return f"⚠️ D-{days}"
            return f"⏰ D-{days}"
        except ValueError:
            return ""

    def _format_kpi(self, goal: dict) -> str:
        """KPI 현황 포맷."""
        metric = goal.get("kpi_metric")
        target = goal.get("kpi_target")
        current = goal.get("kpi_current")
        unit = goal.get("kpi_unit", "")

        if not metric or target is None:
            return ""

        current_val = current if current is not None else 0
        if isinstance(current_val, float) and current_val == int(current_val):
            current_val = int(current_val)
        if isinstance(target, float) and target == int(target):
            target = int(target)

        return f"({current_val}/{target}{unit})"

    async def _generate_summary(
        self,
        objectives: list[dict],
        date: str,
    ) -> str:
        """요약 통계 생성."""
        total_obj = len(objectives)
        total_progress = 0.0

        for obj in objectives:
            total_progress += await self._tracker.calculate_progress(
                obj["id"],
            )

        avg_progress = (
            total_progress / total_obj if total_obj > 0 else 0
        )

        # 마감 알림 수
        now = datetime.strptime(date, "%Y-%m-%d").replace(
            tzinfo=timezone.utc,
        )
        alerts = await self._deadline_checker.check_all_active(now=now)
        critical = sum(
            1 for a in alerts
            if a.severity.value in ("critical", "emergency")
        )

        return (
            f"📊 전체 진척률: {int(avg_progress * 100)}% | "
            f"Objective {total_obj}개 | "
            f"긴급 알림 {critical}건"
        )
