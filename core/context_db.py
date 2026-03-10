"""공유 컨텍스트 DB — 모든 봇이 동일한 맥락 접근."""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import aiosqlite

DEFAULT_DB_PATH = Path(os.environ.get("CONTEXT_DB_PATH", "~/.ai-org/context.db")).expanduser()


class ContextDB:
    """SQLite 기반 공유 컨텍스트 저장소."""

    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        """DB 스키마 초기화."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS context_slots (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    slot_type TEXT NOT NULL,
                    content TEXT NOT NULL,
                    version INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id)
                );

                CREATE TABLE IF NOT EXISTS task_history (
                    id TEXT PRIMARY KEY,
                    project_id TEXT,
                    task_id TEXT NOT NULL,
                    assigned_to TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result TEXT,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_context_project
                    ON context_slots(project_id);
                CREATE INDEX IF NOT EXISTS idx_task_history_task
                    ON task_history(task_id);
            """)
            await db.commit()

    async def create_project(self, project_id: str, name: str, description: str = "") -> None:
        """프로젝트 생성."""
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO projects (id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (project_id, name, description, now, now),
            )
            await db.commit()

    async def write_context(
        self, slot_id: str, project_id: str, slot_type: str, content: str
    ) -> None:
        """컨텍스트 슬롯 저장 (PM만 호출해야 함)."""
        now = datetime.utcnow().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            existing = await db.execute(
                "SELECT version FROM context_slots WHERE id = ?", (slot_id,)
            )
            row = await existing.fetchone()
            if row:
                await db.execute(
                    "UPDATE context_slots SET content=?, version=version+1, updated_at=? WHERE id=?",
                    (content, now, slot_id),
                )
            else:
                await db.execute(
                    "INSERT INTO context_slots (id, project_id, slot_type, content, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (slot_id, project_id, slot_type, content, now, now),
                )
            await db.commit()

    async def read_context(self, slot_id: str) -> dict | None:
        """컨텍스트 슬롯 읽기 (모든 봇 가능)."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id, project_id, slot_type, content, version, updated_at FROM context_slots WHERE id = ?",
                (slot_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "project_id": row[1],
                "slot_type": row[2],
                "content": row[3],
                "version": row[4],
                "updated_at": row[5],
            }

    async def list_project_contexts(self, project_id: str) -> list[dict]:
        """프로젝트의 모든 컨텍스트 슬롯 조회."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id, slot_type, content, version, updated_at FROM context_slots WHERE project_id = ?",
                (project_id,),
            )
            rows = await cursor.fetchall()
            return [
                {"id": r[0], "slot_type": r[1], "content": r[2], "version": r[3], "updated_at": r[4]}
                for r in rows
            ]
