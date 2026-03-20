"""교훈 기록 시스템 — 실패 + 성공 패턴 기록, pre-task briefing 제공."""
from __future__ import annotations

import asyncio
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
    "approach",
    "tool_usage",
    "communication",
    "other",
]

OUTCOMES = ["failure", "success", "partial"]

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
    outcome: str = "failure"         # failure | success | partial
    effectiveness_score: float = 0.0  # 0.0~1.0, 이 교훈 적용 후 성과 변화
    applied_count: int = 0            # briefing에 주입된 횟수

class LessonMemory:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
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
            # 마이그레이션: 새 컬럼 추가 (이미 존재하면 무시)
            for col, default in [
                ("outcome TEXT", "'failure'"),
                ("effectiveness_score REAL", "0.0"),
                ("applied_count INTEGER", "0"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE lessons ADD COLUMN {col} DEFAULT {default}")
                except sqlite3.OperationalError as e:
                    if "duplicate column" not in str(e).lower():
                        raise

    # ------------------------------------------------------------------
    # Private sync helpers — contain the actual sqlite3 work.
    # Call these directly from sync code, or via run_in_executor from async.
    # ------------------------------------------------------------------

    def _sync_record(self, lesson: "Lesson") -> None:
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute(
                "INSERT INTO lessons (id, task_description, category, what_went_wrong,"
                " how_to_prevent, worker, created_at, resolved, outcome,"
                " effectiveness_score, applied_count) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (lesson.id, lesson.task_description, lesson.category,
                 lesson.what_went_wrong, lesson.how_to_prevent,
                 lesson.worker, lesson.created_at, int(lesson.resolved),
                 lesson.outcome, lesson.effectiveness_score, lesson.applied_count)
            )

    def _sync_get_relevant(self, task_description: str, limit: int) -> list["Lesson"]:
        keywords = set(task_description.lower().split())
        with sqlite3.connect(self.db_path, timeout=10) as conn:
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

    def _sync_get_recent_failures(self, days: int) -> list["Lesson"]:
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            rows = conn.execute(
                "SELECT * FROM lessons WHERE created_at > ? AND resolved=0 AND outcome='failure' ORDER BY created_at DESC",
                (cutoff,)
            ).fetchall()
        return [self._row_to_lesson(r) for r in rows]

    def _sync_get_category_stats(self) -> dict[str, int]:
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            rows = conn.execute(
                "SELECT category, COUNT(*) FROM lessons WHERE resolved=0 GROUP BY category"
            ).fetchall()
        return dict(rows)

    def _sync_mark_resolved(self, lesson_id: str) -> None:
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute("UPDATE lessons SET resolved=1 WHERE id=?", (lesson_id,))

    # ------------------------------------------------------------------
    # Public API — sync; safe to call from sync or via run_in_executor
    # from async contexts to avoid blocking the event loop.
    # ------------------------------------------------------------------

    def record(self, task_description: str, category: str,
               what_went_wrong: str, how_to_prevent: str,
               worker: str = "", outcome: str = "failure") -> Lesson:
        lesson = Lesson(
            id=str(uuid.uuid4())[:8],
            task_description=task_description,
            category=category if category in CATEGORIES else "other",
            what_went_wrong=what_went_wrong,
            how_to_prevent=how_to_prevent,
            worker=worker,
            outcome=outcome if outcome in OUTCOMES else "failure",
        )
        self._sync_record(lesson)
        return lesson

    def record_success(self, task_description: str, category: str,
                       what_went_well: str, reuse_tip: str,
                       worker: str = "") -> Lesson:
        """성공 패턴 기록. what_went_well → what_went_wrong 필드에 저장."""
        return self.record(
            task_description=task_description,
            category=category,
            what_went_wrong=what_went_well,   # 성공 시: "잘 된 점"
            how_to_prevent=reuse_tip,          # 성공 시: "재사용 팁"
            worker=worker,
            outcome="success",
        )

    def get_relevant(self, task_description: str, limit: int = 3) -> list[Lesson]:
        return self._sync_get_relevant(task_description, limit)

    def get_recent_failures(self, days: int = 7) -> list[Lesson]:
        return self._sync_get_recent_failures(days)

    def get_category_stats(self) -> dict[str, int]:
        return self._sync_get_category_stats()

    def mark_resolved(self, lesson_id: str):
        self._sync_mark_resolved(lesson_id)

    def get_briefing(self, task_description: str, worker: str = "",
                     limit: int = 5) -> str:
        """Pre-task briefing 텍스트 생성. 관련 교훈(실패+성공)을 요약."""
        lessons = self._sync_get_relevant(task_description, limit)
        if not lessons:
            return ""
        parts = ["## 관련 과거 교훈"]
        for l in lessons:
            if l.outcome == "success":
                parts.append(f"- [성공/{l.category}] {l.what_went_wrong} → 팁: {l.how_to_prevent}")
            else:
                parts.append(f"- [실패/{l.category}] {l.what_went_wrong} → 방지: {l.how_to_prevent}")
        # 적용 횟수 일괄 증가
        self._sync_increment_applied_batch([l.id for l in lessons])
        return "\n".join(parts)

    def _sync_increment_applied_batch(self, lesson_ids: list[str]) -> None:
        if not lesson_ids:
            return
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.executemany(
                "UPDATE lessons SET applied_count = applied_count + 1 WHERE id=?",
                [(lid,) for lid in lesson_ids],
            )

    def update_effectiveness(self, worker: str, task_description: str,
                             success: bool) -> None:
        """태스크 완료 후, 적용된 교훈의 effectiveness_score를 업데이트.

        최근 briefing에서 주입된 교훈(applied_count > 0) 중
        이 태스크와 관련된 교훈의 점수를 조정한다.
        성공 시 +0.1, 실패 시 -0.05 (0.0~1.0 범위 유지).
        """
        keywords = set(task_description.lower().split())
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            rows = conn.execute(
                "SELECT id, task_description, what_went_wrong, effectiveness_score "
                "FROM lessons WHERE applied_count > 0 AND resolved=0"
            ).fetchall()
            delta = 0.1 if success else -0.05
            updated = []
            for row in rows:
                text = (row[1] + " " + row[2]).lower()
                if sum(1 for kw in keywords if kw in text) > 0:
                    new_score = max(0.0, min(1.0, row[3] + delta))
                    updated.append((new_score, row[0]))
            if updated:
                conn.executemany(
                    "UPDATE lessons SET effectiveness_score=? WHERE id=?",
                    updated,
                )

    async def aupdate_effectiveness(self, worker: str, task_description: str,
                                    success: bool) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None, lambda: self.update_effectiveness(worker, task_description, success),
        )

    def _row_to_lesson(self, row) -> Lesson:
        return Lesson(
            id=row[0], task_description=row[1], category=row[2],
            what_went_wrong=row[3], how_to_prevent=row[4],
            worker=row[5], created_at=row[6], resolved=bool(row[7]),
            outcome=row[8] if len(row) > 8 else "failure",
            effectiveness_score=row[9] if len(row) > 9 else 0.0,
            applied_count=row[10] if len(row) > 10 else 0,
        )

    # ------------------------------------------------------------------
    # Async API — wrappers around sync helpers via run_in_executor.
    # Preferred for calling from async contexts.
    # ------------------------------------------------------------------

    async def arecord(
        self, task_description: str, category: str,
        what_went_wrong: str, how_to_prevent: str,
        worker: str = "", outcome: str = "failure",
    ) -> "Lesson":
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.record(
                task_description, category, what_went_wrong,
                how_to_prevent, worker, outcome,
            ),
        )

    async def arecord_success(
        self, task_description: str, category: str,
        what_went_well: str, reuse_tip: str, worker: str = "",
    ) -> "Lesson":
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.record_success(
                task_description, category, what_went_well, reuse_tip, worker,
            ),
        )

    async def aget_briefing(
        self, task_description: str, worker: str = "", limit: int = 5,
    ) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, lambda: self.get_briefing(task_description, worker, limit),
        )

    async def aget_relevant(self, task_description: str, limit: int = 3) -> list["Lesson"]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get_relevant, task_description, limit)

    async def aget_recent_failures(self, days: int = 7) -> list["Lesson"]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get_recent_failures, days)

    async def aget_category_stats(self) -> dict[str, int]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.get_category_stats)

    async def amark_resolved(self, lesson_id: str) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.mark_resolved, lesson_id)
