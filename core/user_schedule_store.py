"""사용자 정의 스케줄 영속 저장소 — SQLite WAL 모드."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / ".ai-org" / "user_schedules.db"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class UserSchedule:
    id: int
    raw_text: str          # 원본 자연어 ("매일 오전 9시에 AI 뉴스 요약")
    cron_expr: str         # "0 9 * * *"
    task_description: str  # 실제 실행할 태스크 설명
    created_at: str
    enabled: bool = True


class UserScheduleStore:
    """재시작 후에도 유지되는 사용자 정의 스케줄 저장소."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS user_schedules (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raw_text TEXT NOT NULL,
                    cron_expr TEXT NOT NULL,
                    task_description TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1
                )
            """)

    def add(self, raw_text: str, cron_expr: str, task_description: str) -> UserSchedule:
        """새 스케줄 등록. 생성된 UserSchedule 반환."""
        now = _utcnow_iso()
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            cursor = conn.execute(
                """INSERT INTO user_schedules (raw_text, cron_expr, task_description, created_at, enabled)
                   VALUES (?, ?, ?, ?, 1)""",
                (raw_text, cron_expr, task_description, now),
            )
            row_id = cursor.lastrowid
        return UserSchedule(
            id=row_id,
            raw_text=raw_text,
            cron_expr=cron_expr,
            task_description=task_description,
            created_at=now,
            enabled=True,
        )

    def list_all(self) -> list[UserSchedule]:
        """전체 스케줄 목록 (활성 + 비활성)."""
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            rows = conn.execute(
                "SELECT id, raw_text, cron_expr, task_description, created_at, enabled FROM user_schedules ORDER BY id"
            ).fetchall()
        return [self._row_to_schedule(r) for r in rows]

    def get_enabled(self) -> list[UserSchedule]:
        """활성 스케줄만 반환 (재시작 복원용)."""
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            rows = conn.execute(
                "SELECT id, raw_text, cron_expr, task_description, created_at, enabled FROM user_schedules WHERE enabled=1 ORDER BY id"
            ).fetchall()
        return [self._row_to_schedule(r) for r in rows]

    def disable(self, schedule_id: int) -> bool:
        """스케줄 비활성화. 성공 시 True."""
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            cursor = conn.execute(
                "UPDATE user_schedules SET enabled=0 WHERE id=?", (schedule_id,)
            )
            return cursor.rowcount > 0

    def enable(self, schedule_id: int) -> bool:
        """스케줄 재활성화. 성공 시 True."""
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            cursor = conn.execute(
                "UPDATE user_schedules SET enabled=1 WHERE id=?", (schedule_id,)
            )
            return cursor.rowcount > 0

    def delete(self, schedule_id: int) -> bool:
        """스케줄 영구 삭제. 성공 시 True."""
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            cursor = conn.execute(
                "DELETE FROM user_schedules WHERE id=?", (schedule_id,)
            )
            return cursor.rowcount > 0

    def get_by_id(self, schedule_id: int) -> UserSchedule | None:
        """ID로 스케줄 조회."""
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            row = conn.execute(
                "SELECT id, raw_text, cron_expr, task_description, created_at, enabled FROM user_schedules WHERE id=?",
                (schedule_id,),
            ).fetchone()
        return self._row_to_schedule(row) if row else None

    @staticmethod
    def _row_to_schedule(row: tuple) -> UserSchedule:
        return UserSchedule(
            id=row[0],
            raw_text=row[1],
            cron_expr=row[2],
            task_description=row[3],
            created_at=row[4],
            enabled=bool(row[5]),
        )
