"""주간 회고 메모리 — 성공률 추적 + 패턴 리포트."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sqlite3
import uuid
import json
from collections import Counter

from core.lesson_memory import LessonMemory

DB_PATH = Path(__file__).parent.parent / ".ai-org" / "retro_memory.db"


@dataclass
class RetroEntry:
    date: str           # YYYY-MM-DD
    best_thing: str
    failure_summary: str
    experiment: str
    task_count: int = 0
    success_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class RetroReport:
    period: str          # e.g. "2026-W11"
    avg_success_rate: float
    top_lessons: list[str]
    achievements: list[str]
    action_items: list[str]


class RetroMemory:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS retro_entries (
                    date TEXT PRIMARY KEY,
                    best_thing TEXT,
                    failure_summary TEXT,
                    experiment TEXT,
                    task_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    created_at TEXT
                )
            """)

    def save_daily(self, entry: RetroEntry) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR REPLACE INTO retro_entries
                   (date, best_thing, failure_summary, experiment,
                    task_count, success_count, created_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (entry.date, entry.best_thing, entry.failure_summary,
                 entry.experiment, entry.task_count, entry.success_count,
                 entry.created_at)
            )

    def get_week_entries(self, week_offset: int = 0) -> list[RetroEntry]:
        today = datetime.now(timezone.utc).date()
        # Monday of the target week
        week_start = today - timedelta(days=today.weekday()) + timedelta(weeks=week_offset)
        week_end = week_start + timedelta(days=6)
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM retro_entries WHERE date >= ? AND date <= ? ORDER BY date ASC",
                (week_start.isoformat(), week_end.isoformat())
            ).fetchall()
        return [self._row_to_entry(r) for r in rows]

    def generate_weekly_report(self, week_offset: int = 0) -> RetroReport:
        entries = self.get_week_entries(week_offset)

        # Average success rate
        if entries:
            total_tasks = sum(e.task_count for e in entries)
            total_success = sum(e.success_count for e in entries)
            avg_success_rate = (total_success / total_tasks) if total_tasks > 0 else 0.0
        else:
            avg_success_rate = 0.0

        # Top lessons from LessonMemory
        try:
            failures = LessonMemory().get_recent_failures(days=14)
            top_lessons = [
                f"{l.category}: {l.what_went_wrong[:80]}"
                for l in failures[:5]
            ]
        except Exception:
            top_lessons = []

        # Achievements from best_thing (deduplicated, max 5)
        seen: set[str] = set()
        achievements: list[str] = []
        for e in entries:
            if e.best_thing and e.best_thing not in seen:
                seen.add(e.best_thing)
                achievements.append(e.best_thing)
                if len(achievements) >= 5:
                    break

        # Action items derived from most common failure categories
        try:
            failures_for_actions = LessonMemory().get_recent_failures(days=14)
            if failures_for_actions:
                category_counts = Counter(l.category for l in failures_for_actions)
                top_categories = [cat for cat, _ in category_counts.most_common(3)]
                category_actions = {
                    "timeout": "타임아웃 임계값 검토 및 재시도 로직 강화",
                    "logic_error": "핵심 로직에 단위 테스트 추가",
                    "api_failure": "API 오류 핸들링 및 폴백 로직 점검",
                    "missing_error_handler": "누락된 예외 처리 구간 식별 및 보완",
                    "context_loss": "컨텍스트 저장/복원 메커니즘 강화",
                    "incomplete_output": "출력 검증 단계 추가",
                    "other": "미분류 실패 원인 분석 및 카테고리 정리",
                }
                action_items = [
                    category_actions.get(cat, f"{cat} 패턴 개선")
                    for cat in top_categories
                ]
                # Pad to 3 if fewer than 3 categories
                defaults = [
                    "테스트 커버리지 유지",
                    "문서화 습관 강화",
                    "현재 패턴 계속 모니터링",
                ]
                while len(action_items) < 3:
                    for d in defaults:
                        if d not in action_items:
                            action_items.append(d)
                            break
                    else:
                        break
                action_items = action_items[:3]
            else:
                action_items = [
                    "현재 패턴 없음 - 계속 모니터링",
                    "테스트 커버리지 유지",
                    "문서화 습관 강화",
                ]
        except Exception:
            action_items = [
                "현재 패턴 없음 - 계속 모니터링",
                "테스트 커버리지 유지",
                "문서화 습관 강화",
            ]

        # ISO week string e.g. "2026-W11"
        today = datetime.now(timezone.utc).date()
        target_date = today + timedelta(weeks=week_offset)
        iso_year, iso_week, _ = target_date.isocalendar()
        period = f"{iso_year}-W{iso_week:02d}"

        return RetroReport(
            period=period,
            avg_success_rate=avg_success_rate,
            top_lessons=top_lessons,
            achievements=achievements,
            action_items=action_items,
        )

    def format_telegram(self, report: RetroReport) -> str:
        lines = [
            f"📊 *주간 회고 리포트 — {report.period}*",
            f"평균 성공률: {report.avg_success_rate:.0%}",
            "",
        ]

        if report.top_lessons:
            lines.append("💡 *반복 패턴:*")
            for lesson in report.top_lessons:
                lines.append(f"  • {lesson}")
            lines.append("")

        if report.achievements:
            lines.append("🎯 *잘한 것:*")
            for ach in report.achievements:
                lines.append(f"  • {ach}")
            lines.append("")

        if report.action_items:
            lines.append("🔧 *개선 액션:*")
            for item in report.action_items:
                lines.append(f"  • {item}")

        return "\n".join(lines)

    def _row_to_entry(self, row) -> RetroEntry:
        return RetroEntry(
            date=row[0],
            best_thing=row[1],
            failure_summary=row[2],
            experiment=row[3],
            task_count=row[4],
            success_count=row[5],
            created_at=row[6],
        )
