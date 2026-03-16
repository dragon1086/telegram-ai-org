"""실패 패턴 기록 + 재발 방지 시스템."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import uuid

DB_PATH = Path(__file__).parent.parent / ".ai-org" / "lesson_memory.db"

CATEGORIES = [
    "timeout",
    "logic_error",
    "api_failure",
    "missing_error_handler",
    "context_loss",
    "incomplete_output",
    "other",
]

@dataclass
class Lesson:
    id: str
    task_description: str
    category: str
    what_went_wrong: str
    how_to_prevent: str
    worker: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved: bool = False

class LessonMemory:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS lessons (
                    id TEXT PRIMARY KEY,
                    task_description TEXT,
                    category TEXT,
                    what_went_wrong TEXT,
                    how_to_prevent TEXT,
                    worker TEXT DEFAULT "",
                    created_at TEXT,
                    resolved INTEGER DEFAULT 0
                )
            """)

    def record(self, task_description: str, category: str,
               what_went_wrong: str, how_to_prevent: str, worker: str = "") -> Lesson:
        lesson = Lesson(
            id=str(uuid.uuid4())[:8],
            task_description=task_description,
            category=category if category in CATEGORIES else "other",
            what_went_wrong=what_went_wrong,
            how_to_prevent=how_to_prevent,
            worker=worker,
        )
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO lessons VALUES (?,?,?,?,?,?,?,?)",
                (lesson.id, lesson.task_description, lesson.category,
                 lesson.what_went_wrong, lesson.how_to_prevent,
                 lesson.worker, lesson.created_at, 0)
            )
        return lesson

    def get_relevant(self, task_description: str, limit: int = 3) -> list[Lesson]:
        keywords = set(task_description.lower().split())
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM lessons WHERE resolved=0 ORDER BY created_at DESC LIMIT 50"
            ).fetchall()
        scored = []
        for row in rows:
            text = (row[1] + " " + row[3]).lower()
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scored.append((score, row))
        scored.sort(reverse=True)
        return [self._row_to_lesson(r) for _, r in scored[:limit]]

    def get_recent_failures(self, days: int = 7) -> list[Lesson]:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM lessons WHERE created_at > ? AND resolved=0 ORDER BY created_at DESC",
                (cutoff,)
            ).fetchall()
        return [self._row_to_lesson(r) for r in rows]

    def get_category_stats(self) -> dict[str, int]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT category, COUNT(*) FROM lessons GROUP BY category"
            ).fetchall()
        return dict(rows)

    def mark_resolved(self, lesson_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE lessons SET resolved=1 WHERE id=?", (lesson_id,))

    def _row_to_lesson(self, row) -> Lesson:
        return Lesson(
            id=row[0], task_description=row[1], category=row[2],
            what_went_wrong=row[3], how_to_prevent=row[4],
            worker=row[5], created_at=row[6], resolved=bool(row[7])
        )
