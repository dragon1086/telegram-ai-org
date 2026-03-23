"""공유 컨텍스트 DB — 모든 봇이 동일한 맥락 접근."""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiosqlite
from loguru import logger

DEFAULT_DB_PATH = Path(os.environ.get("CONTEXT_DB_PATH", "~/.ai-org/context.db")).expanduser()


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


class ContextDB:
    """SQLite 기반 공유 컨텍스트 저장소."""

    def __init__(self, db_path: "Path | str" = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
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

                CREATE TABLE IF NOT EXISTS pm_tasks (
                    id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    description TEXT NOT NULL,
                    assigned_dept TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    result TEXT,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS pm_task_dependencies (
                    task_id TEXT NOT NULL,
                    depends_on TEXT NOT NULL,
                    PRIMARY KEY (task_id, depends_on),
                    FOREIGN KEY (task_id) REFERENCES pm_tasks(id),
                    FOREIGN KEY (depends_on) REFERENCES pm_tasks(id)
                );

                CREATE INDEX IF NOT EXISTS idx_pm_tasks_parent ON pm_tasks(parent_id);
                CREATE INDEX IF NOT EXISTS idx_pm_tasks_status ON pm_tasks(status);
                CREATE INDEX IF NOT EXISTS idx_pm_tasks_dept ON pm_tasks(assigned_dept);

                CREATE TABLE IF NOT EXISTS pm_discussions (
                    id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    parent_task_id TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    participants TEXT NOT NULL,
                    max_rounds INTEGER DEFAULT 3,
                    round_timeout_sec REAL DEFAULT 120.0,
                    current_round INTEGER DEFAULT 1,
                    decision TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pm_discussion_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    discussion_id TEXT NOT NULL,
                    msg_type TEXT NOT NULL,
                    topic TEXT NOT NULL,
                    content TEXT NOT NULL,
                    from_dept TEXT NOT NULL,
                    round_num INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (discussion_id) REFERENCES pm_discussions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_pm_disc_status ON pm_discussions(status);
                CREATE INDEX IF NOT EXISTS idx_pm_disc_msg_disc ON pm_discussion_messages(discussion_id);

                CREATE TABLE IF NOT EXISTS pm_verifications (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    original_dept TEXT NOT NULL,
                    verifier_dept TEXT NOT NULL,
                    original_model TEXT NOT NULL,
                    verifier_model TEXT NOT NULL,
                    verdict TEXT,
                    issues TEXT DEFAULT '[]',
                    suggestions TEXT DEFAULT '[]',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES pm_tasks(id)
                );

                CREATE INDEX IF NOT EXISTS idx_pm_verify_task ON pm_verifications(task_id);
                CREATE INDEX IF NOT EXISTS idx_pm_verify_status ON pm_verifications(status);

                CREATE TABLE IF NOT EXISTS pm_goals (
                    id TEXT PRIMARY KEY,
                    description TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    milestones TEXT DEFAULT '[]',
                    iteration INTEGER DEFAULT 0,
                    max_iterations INTEGER DEFAULT 10,
                    stagnation_count INTEGER DEFAULT 0,
                    last_progress TEXT,
                    chat_id INTEGER,
                    created_by TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_pm_goals_status ON pm_goals(status);

                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    msg_id INTEGER,
                    chat_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    bot_id TEXT,
                    role TEXT NOT NULL,
                    is_bot BOOLEAN DEFAULT 0,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_conv_chat_user
                    ON conversation_messages(chat_id, user_id);
                CREATE INDEX IF NOT EXISTS idx_conv_timestamp
                    ON conversation_messages(timestamp);

                CREATE TABLE IF NOT EXISTS bot_performance (
                    bot_id TEXT NOT NULL,
                    week TEXT NOT NULL,
                    task_count INTEGER DEFAULT 0,
                    success_count INTEGER DEFAULT 0,
                    total_latency_sec REAL DEFAULT 0.0,
                    avg_latency_sec REAL DEFAULT 0.0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (bot_id, week)
                );
                CREATE INDEX IF NOT EXISTS idx_bot_perf_week ON bot_performance(week);

                CREATE TABLE IF NOT EXISTS message_envelopes (
                    telegram_message_id INTEGER PRIMARY KEY,
                    task_id TEXT,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT DEFAULT (datetime('now'))
                );
            """)
            await db.commit()

    async def create_project(self, project_id: str, name: str, description: str = "") -> None:
        """프로젝트 생성."""
        now = _utcnow_iso()
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
        now = _utcnow_iso()
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

    async def delete_context(self, slot_id: str) -> None:
        """컨텍스트 슬롯 삭제."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM context_slots WHERE id = ?", (slot_id,))
            await db.commit()

    async def delete_project_contexts(self, project_id: str) -> None:
        """프로젝트의 모든 컨텍스트 슬롯 삭제."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM context_slots WHERE project_id = ?", (project_id,))
            await db.commit()

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

    async def create_pm_task(self, task_id: str, description: str, assigned_dept: str | None,
                             created_by: str, parent_id: str | None = None,
                             metadata: dict | None = None) -> dict:
        """PM 태스크 생성 (크로스 프로세스 공유)."""
        now = _utcnow_iso()
        meta = json.dumps(metadata or {})
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR IGNORE INTO pm_tasks (id, parent_id, description, assigned_dept, status,
                   created_by, created_at, updated_at, metadata)
                   VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
                (task_id, parent_id, description, assigned_dept, created_by, now, now, meta),
            )
            await db.commit()
        return {"id": task_id, "parent_id": parent_id, "description": description,
                "assigned_dept": assigned_dept, "status": "pending",
                "created_by": created_by, "created_at": now, "updated_at": now,
                "metadata": metadata or {}}

    async def update_pm_task_status(self, task_id: str, status: str,
                                     result: str | None = None) -> dict | None:
        """PM 태스크 상태 업데이트."""
        now = _utcnow_iso()
        async with aiosqlite.connect(self.db_path) as db:
            if result is not None:
                await db.execute(
                    "UPDATE pm_tasks SET status=?, result=?, updated_at=? WHERE id=?",
                    (status, result, now, task_id),
                )
            else:
                await db.execute(
                    "UPDATE pm_tasks SET status=?, updated_at=? WHERE id=?",
                    (status, now, task_id),
                )
            await db.commit()
        return await self.get_pm_task(task_id)

    async def update_pm_task_metadata(self, task_id: str, metadata: dict) -> dict | None:
        """PM 태스크 메타데이터 병합 업데이트."""
        task = await self.get_pm_task(task_id)
        if task is None:
            return None
        merged = dict(task.get("metadata") or {})
        merged.update(metadata)
        now = _utcnow_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE pm_tasks SET metadata=?, updated_at=? WHERE id=?",
                (json.dumps(merged, ensure_ascii=False), now, task_id),
            )
            await db.commit()
        return await self.get_pm_task(task_id)

    async def get_pm_task(self, task_id: str) -> dict | None:
        """PM 태스크 조회."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM pm_tasks WHERE id=?", (task_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            return self._decode_pm_task_row(row)

    async def get_subtasks(self, parent_id: str) -> list[dict]:
        """부모 태스크의 자식 태스크들 조회."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM pm_tasks WHERE parent_id=? ORDER BY created_at",
                (parent_id,),
            )
            rows = await cursor.fetchall()
            return [self._decode_pm_task_row(r) for r in rows]

    async def get_active_parent_tasks(self) -> list[dict]:
        """활성 상태의 루트(부모 없는) 태스크 목록 조회 (StalenessChecker 및 backpressure용)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM pm_tasks WHERE parent_id IS NULL "
                "AND status IN ('running', 'assigned', 'pending') "
                "ORDER BY created_at",
            )
            rows = await cursor.fetchall()
            return [self._decode_pm_task_row(r) for r in rows]

    async def add_dependency(self, task_id: str, depends_on: str) -> None:
        """태스크 의존성 추가."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO pm_task_dependencies (task_id, depends_on) VALUES (?, ?)",
                (task_id, depends_on),
            )
            await db.commit()

    async def get_tasks_depending_on(self, task_id: str) -> list[str]:
        """이 태스크에 직접 의존하는 태스크 ID 목록 (역방향 조회)."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT task_id FROM pm_task_dependencies WHERE depends_on=?",
                (task_id,),
            )
            rows = await cursor.fetchall()
        return [r[0] for r in rows]

    async def get_ready_tasks(self, parent_id: str) -> list[dict]:
        """의존성이 모두 완료된 실행 가능 태스크 조회."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT t.* FROM pm_tasks t
                WHERE t.parent_id = ? AND t.status = 'pending'
                AND NOT EXISTS (
                    SELECT 1 FROM pm_task_dependencies d
                    JOIN pm_tasks dep ON dep.id = d.depends_on
                    WHERE d.task_id = t.id AND dep.status != 'done'
                )
            """, (parent_id,))
            rows = await cursor.fetchall()
            return [self._decode_pm_task_row(r) for r in rows]

    @staticmethod
    def _decode_pm_task_row(row: aiosqlite.Row) -> dict:
        data = dict(row)
        raw_meta = data.get("metadata")
        if isinstance(raw_meta, str):
            try:
                data["metadata"] = json.loads(raw_meta)
            except json.JSONDecodeError:
                data["metadata"] = {}
        elif raw_meta is None:
            data["metadata"] = {}
        return data

    # ── Discussion CRUD ───────────────────────────────────────────────────

    async def create_discussion(self, discussion_id: str, topic: str,
                                 participants: list[str],
                                 parent_task_id: str | None = None,
                                 max_rounds: int = 3,
                                 round_timeout_sec: float = 120.0) -> dict:
        """토론 생성."""
        now = _utcnow_iso()
        parts_json = json.dumps(participants)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO pm_discussions
                   (id, topic, parent_task_id, status, participants,
                    max_rounds, round_timeout_sec, current_round, created_at, updated_at)
                   VALUES (?, ?, ?, 'open', ?, ?, ?, 1, ?, ?)""",
                (discussion_id, topic, parent_task_id, parts_json,
                 max_rounds, round_timeout_sec, now, now),
            )
            await db.commit()
        return {"id": discussion_id, "topic": topic, "parent_task_id": parent_task_id,
                "status": "open", "participants": participants,
                "max_rounds": max_rounds, "round_timeout_sec": round_timeout_sec,
                "current_round": 1, "created_at": now, "updated_at": now}

    async def add_discussion_message(self, discussion_id: str, msg_type: str,
                                      topic: str, content: str,
                                      from_dept: str, round_num: int) -> dict:
        """토론 메시지 추가."""
        now = _utcnow_iso()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """INSERT INTO pm_discussion_messages
                   (discussion_id, msg_type, topic, content, from_dept, round_num, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (discussion_id, msg_type, topic, content, from_dept, round_num, now),
            )
            msg_id = cursor.lastrowid
            await db.commit()
        return {"id": msg_id, "discussion_id": discussion_id, "msg_type": msg_type,
                "topic": topic, "content": content, "from_dept": from_dept,
                "round_num": round_num, "created_at": now}

    async def get_discussion(self, discussion_id: str) -> dict | None:
        """토론 조회."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM pm_discussions WHERE id=?", (discussion_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            d["participants"] = json.loads(d["participants"])
            return d

    async def get_discussion_messages(self, discussion_id: str,
                                       round_num: int | None = None) -> list[dict]:
        """토론 메시지 조회. round_num 지정 시 해당 라운드만."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if round_num is not None:
                cursor = await db.execute(
                    "SELECT * FROM pm_discussion_messages WHERE discussion_id=? AND round_num=? ORDER BY id",
                    (discussion_id, round_num),
                )
            else:
                cursor = await db.execute(
                    "SELECT * FROM pm_discussion_messages WHERE discussion_id=? ORDER BY id",
                    (discussion_id,),
                )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def get_recent_pm_tasks(self, limit: int = 10) -> list[dict]:
        """최근 PM 태스크 이력 조회 (updated_at DESC)."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT id, description, assigned_dept, status, created_at, updated_at "
                "FROM pm_tasks ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]

    async def check_convergence(self, discussion_id: str) -> bool:
        """현재 라운드에 COUNTER 메시지가 없으면 수렴으로 판정."""
        disc = await self.get_discussion(discussion_id)
        if not disc:
            return False
        current_round = disc["current_round"]
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT COUNT(*) FROM pm_discussion_messages
                   WHERE discussion_id=? AND round_num=? AND msg_type='COUNTER'""",
                (discussion_id, current_round),
            )
            row = await cursor.fetchone()
            count = row[0] if row else 0
        # 수렴 조건: 현재 라운드에 메시지가 있고 COUNTER가 없음
        msgs = await self.get_discussion_messages(discussion_id, current_round)
        return len(msgs) > 0 and count == 0

    async def update_discussion_status(self, discussion_id: str, status: str,
                                        decision: str | None = None) -> dict | None:
        """토론 상태 업데이트."""
        now = _utcnow_iso()
        async with aiosqlite.connect(self.db_path) as db:
            if decision is not None:
                await db.execute(
                    "UPDATE pm_discussions SET status=?, decision=?, updated_at=? WHERE id=?",
                    (status, decision, now, discussion_id),
                )
            else:
                await db.execute(
                    "UPDATE pm_discussions SET status=?, updated_at=? WHERE id=?",
                    (status, now, discussion_id),
                )
            await db.commit()
        return await self.get_discussion(discussion_id)

    async def advance_discussion_round(self, discussion_id: str) -> int:
        """토론 라운드 진행. 새 라운드 번호 반환."""
        now = _utcnow_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE pm_discussions SET current_round=current_round+1, updated_at=? WHERE id=?",
                (now, discussion_id),
            )
            await db.commit()
        disc = await self.get_discussion(discussion_id)
        return disc["current_round"] if disc else -1

    async def get_active_discussions(self) -> list[dict]:
        """진행 중인 토론 목록."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM pm_discussions WHERE status='open' ORDER BY created_at"
            )
            rows = await cursor.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["participants"] = json.loads(d["participants"])
                result.append(d)
            return result

    async def get_tasks_for_dept(self, dept_id: str, status: str = "assigned") -> list[dict]:
        """특정 부서에 배정된 태스크 조회 (TaskPoller용).

        'assigned' 태스크 + 의존성이 모두 완료된 'pending' 태스크도 함께 반환.
        pm_orchestrator 알림 없이도 의존성 체인이 자동 해제된다.
        """
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("""
                SELECT * FROM pm_tasks t
                WHERE t.assigned_dept = ?
                  AND t.status NOT IN ('done', 'failed', 'cancelled')
                ORDER BY t.created_at
            """, (dept_id,))
            rows = await cursor.fetchall()
            tasks = [self._decode_pm_task_row(r) for r in rows]
            now = datetime.now(UTC)
            result: list[dict] = []
            for task in tasks:
                metadata = task.get("metadata") or {}
                retry_after = metadata.get("retry_after_at")
                if retry_after:
                    try:
                        if datetime.fromisoformat(retry_after) > now:
                            continue
                    except ValueError:
                        pass
                # ── 부모 태스크가 failed/cancelled면 자식도 자동 cancelled 처리 ──
                parent_id = task.get("parent_id")
                if parent_id:
                    parent_cur = await db.execute(
                        "SELECT status FROM pm_tasks WHERE id = ?", (parent_id,),
                    )
                    parent_row = await parent_cur.fetchone()
                    if parent_row and parent_row["status"] in ("failed", "cancelled"):
                        logger.info(
                            "[ORPHAN-GUARD] 태스크 {} 자동 cancelled: "
                            "부모 {} 상태={}",
                            task["id"], parent_id, parent_row["status"],
                        )
                        await db.execute(
                            "UPDATE pm_tasks SET status = 'cancelled' WHERE id = ?",
                            (task["id"],),
                        )
                        await db.commit()
                        continue
                if task["status"] == "assigned":
                    result.append(task)
                    continue
                if task["status"] == "pending":
                    deps_ready = True
                    async with aiosqlite.connect(self.db_path) as dep_db:
                        dep_cursor = await dep_db.execute(
                            """SELECT d.depends_on, dep.status FROM pm_task_dependencies d
                               JOIN pm_tasks dep ON dep.id = d.depends_on
                               WHERE d.task_id = ? AND dep.status != 'done'
                               LIMIT 1""",
                            (task["id"],),
                        )
                        blocking_row = await dep_cursor.fetchone()
                        deps_ready = blocking_row is None
                    if deps_ready:
                        result.append(task)
                    else:
                        # [ORDER-VIOLATION-GUARD] 순서 위반 방지 — deps 미완료 태스크 차단
                        logger.warning(
                            f"[ORDER-GUARD] 태스크 {task['id']} ({dept_id}) 차단: "
                            f"의존 태스크 {blocking_row[0] if blocking_row else '?'} "
                            f"상태={blocking_row[1] if blocking_row else '?'} (미완료). "
                            "레이스 컨디션 차단 정상 동작."
                        )
                    continue
                if task["status"] != "running":
                    continue
                # ── Expired lease reclaim: attempt 횟수 초과 시 스킵 ──
                attempt_count = metadata.get("attempt_count", 0)
                if attempt_count >= self.MAX_TASK_ATTEMPTS:
                    logger.warning(
                        f"[ContextDB] 태스크 {task['id']} attempt_count={attempt_count} "
                        f">= MAX={self.MAX_TASK_ATTEMPTS} — 봇 재시작 시 recover_stale_dept_tasks로 복구됨"
                    )
                    continue
                lease_until = metadata.get("lease_expires_at")
                if not lease_until:
                    continue
                try:
                    if datetime.fromisoformat(lease_until) < now:
                        result.append(task)
                except ValueError:
                    result.append(task)
            return result

    MAX_TASK_ATTEMPTS = 5  # 최대 lease claim 횟수 — 초과 시 자동 failed 처리
    # 3 → 5 (2026-03-23): 복잡한 장기 태스크(코드 분석·구현·리뷰)에서
    # 봇 재시작·Claude Code 타임아웃으로 attempt_count가 빠르게 소진되어
    # 태스크가 조기 auto-fail되는 문제 해소. recover_stale_dept_tasks가
    # attempt_count를 0으로 리셋하므로 무한루프 위험은 없음.

    async def claim_pm_task_lease(
        self,
        task_id: str,
        owner: str,
        ttl_seconds: float,
    ) -> dict | None:
        """태스크 lease를 획득한다. 이미 유효한 lease가 있으면 None.

        무한 재시작 루프 방지: attempt_count가 MAX_TASK_ATTEMPTS를 초과하면
        태스크를 자동으로 'failed' 상태로 전환하고 None을 반환한다.
        """
        task = await self.get_pm_task(task_id)
        if task is None:
            return None
        metadata = dict(task.get("metadata") or {})
        now = datetime.now(UTC)

        # ── 무한 루프 방지: attempt 횟수 체크 ──
        attempt_count = metadata.get("attempt_count", 0) + 1
        if attempt_count > self.MAX_TASK_ATTEMPTS:
            logger.warning(
                f"[ContextDB] 태스크 {task_id} 최대 시도 횟수 초과 "
                f"({attempt_count}/{self.MAX_TASK_ATTEMPTS}) — 자동 failed 처리"
            )
            metadata["fail_reason"] = (
                f"최대 실행 시도 횟수 초과 ({self.MAX_TASK_ATTEMPTS}회). "
                "무한 재시작 루프 방지를 위해 자동 중단됨."
            )
            now_iso = _utcnow_iso()
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE pm_tasks SET status='failed', metadata=?, updated_at=? WHERE id=?",
                    (json.dumps(metadata, ensure_ascii=False), now_iso, task_id),
                )
                await db.commit()
            return None

        lease_until_raw = metadata.get("lease_expires_at")
        lease_owner = metadata.get("lease_owner")
        if lease_until_raw and lease_owner and lease_owner != owner:
            try:
                lease_until = datetime.fromisoformat(lease_until_raw)
                if lease_until > now:
                    return None
            except ValueError:
                pass
        metadata.update({
            "lease_owner": owner,
            "lease_expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
            "lease_heartbeat_at": now.isoformat(),
            "attempt_count": attempt_count,
        })
        now_iso = _utcnow_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE pm_tasks SET status='running', metadata=?, updated_at=? WHERE id=?",
                (json.dumps(metadata, ensure_ascii=False), now_iso, task_id),
            )
            await db.commit()
        return await self.get_pm_task(task_id)

    async def heartbeat_pm_task_lease(
        self,
        task_id: str,
        owner: str,
        ttl_seconds: float,
    ) -> dict | None:
        task = await self.get_pm_task(task_id)
        if task is None:
            return None
        metadata = dict(task.get("metadata") or {})
        if metadata.get("lease_owner") != owner:
            return None
        now = datetime.now(UTC)
        metadata.update({
            "lease_expires_at": (now + timedelta(seconds=ttl_seconds)).isoformat(),
            "lease_heartbeat_at": now.isoformat(),
        })
        return await self.update_pm_task_metadata(task_id, metadata)

    async def release_pm_task_lease(
        self,
        task_id: str,
        owner: str,
        *,
        requeue_if_running: bool = False,
        retry_delay_seconds: float = 0.0,
    ) -> dict | None:
        task = await self.get_pm_task(task_id)
        if task is None:
            return None
        metadata = dict(task.get("metadata") or {})
        if metadata.get("lease_owner") != owner:
            return task
        metadata.pop("lease_owner", None)
        metadata.pop("lease_expires_at", None)
        metadata.pop("lease_heartbeat_at", None)
        if retry_delay_seconds > 0:
            metadata["retry_after_at"] = (datetime.now(UTC) + timedelta(seconds=retry_delay_seconds)).isoformat()
        else:
            metadata.pop("retry_after_at", None)
        now = _utcnow_iso()
        status = task["status"]
        if requeue_if_running and status == "running":
            status = "assigned"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE pm_tasks SET status=?, metadata=?, updated_at=? WHERE id=?",
                (status, json.dumps(metadata, ensure_ascii=False), now, task_id),
            )
            await db.commit()
        return await self.get_pm_task(task_id)

    # ── Stale Task Recovery ────────────────────────────────────────────────

    RECOVER_MAX_AGE_SECONDS = 86400  # 복구 대상 최대 나이: 24시간

    async def recover_stale_dept_tasks(
        self,
        dept_id: str,
        stale_seconds: float = 300.0,
    ) -> int:
        """봇 재시작 시 stale 'running' 태스크를 'assigned'로 복구.

        lease가 만료되고 attempt_count가 MAX_TASK_ATTEMPTS에 도달하여
        영구 교착 상태에 빠진 태스크를 복구한다.
        attempt_count를 0으로 리셋하여 재실행 가능하게 만든다.

        안전장치:
        - 24시간 이상 된 태스크는 복구하지 않음 (좀비 방지)
        - 부모가 failed인 태스크는 복구하지 않음 (고아 방지)
          ※ 부모가 cancelled여도 자식 부서 태스크는 계속 실행 (Orphan Guard 정책)

        Returns: 복구된 태스크 수.
        """
        now = datetime.now(UTC)
        cutoff = (now - timedelta(seconds=stale_seconds)).isoformat()
        max_age_cutoff = (now - timedelta(seconds=self.RECOVER_MAX_AGE_SECONDS)).isoformat()
        recovered = 0
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT id, metadata, parent_id FROM pm_tasks
                   WHERE assigned_dept = ?
                     AND status = 'running'
                     AND updated_at < ?
                     AND updated_at > ?""",
                (dept_id, cutoff, max_age_cutoff),
            )
            rows = await cursor.fetchall()
            for row in rows:
                task_id = row["id"]
                metadata = json.loads(row["metadata"] or "{}")
                # 부모가 failed면 복구하지 않음 (cancelled는 제외: 부서 태스크는 계속 실행)
                parent_id = row["parent_id"]
                if parent_id:
                    pcur = await db.execute(
                        "SELECT status FROM pm_tasks WHERE id = ?", (parent_id,),
                    )
                    prow = await pcur.fetchone()
                    if prow and prow["status"] in ("failed",):
                        logger.info(
                            f"[RECOVER] 태스크 {task_id} 복구 스킵: "
                            f"부모 {parent_id} 상태={prow['status']}"
                        )
                        continue
                lease_exp = metadata.get("lease_expires_at")
                if lease_exp:
                    try:
                        if datetime.fromisoformat(lease_exp) > now:
                            continue  # lease 아직 유효 — 건드리지 않음
                    except ValueError:
                        pass
                # lease 만료 확인됨 — 복구
                metadata.pop("lease_owner", None)
                metadata.pop("lease_expires_at", None)
                metadata.pop("lease_heartbeat_at", None)
                metadata.pop("retry_after_at", None)
                metadata["attempt_count"] = 0
                metadata["recovered_at"] = now.isoformat()
                now_iso = now.isoformat()
                await db.execute(
                    "UPDATE pm_tasks SET status='assigned', metadata=?, updated_at=? WHERE id=?",
                    (json.dumps(metadata, ensure_ascii=False), now_iso, task_id),
                )
                recovered += 1
                logger.info(
                    f"[ContextDB] stale 태스크 복구: {task_id} (dept={dept_id}, "
                    f"attempt_count 리셋, running→assigned)"
                )
            if recovered:
                await db.commit()
        return recovered

    # ── Auto-Dispatch 헬퍼 ────────────────────────────────────────────────

    async def get_stalled_tasks(self, stall_minutes: int = 30) -> list[str]:
        """지정 시간 이상 진행 없는 태스크 ID 목록 반환."""
        cutoff = (datetime.now(UTC) - timedelta(minutes=stall_minutes)).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """SELECT id FROM pm_tasks
                   WHERE status IN ('assigned', 'in_progress')
                   AND updated_at < ?
                   ORDER BY updated_at""",
                (cutoff,),
            )
            rows = await cursor.fetchall()
            return [r[0] for r in rows]

    # ── Verification CRUD ─────────────────────────────────────────────────

    async def create_verification(
        self,
        task_id: str,
        original_dept: str,
        verifier_dept: str,
        original_model: str,
        verifier_model: str,
    ) -> str:
        """교차 검증 요청 생성. 자동 생성된 ID 반환."""
        now = _utcnow_iso()
        # 고유 ID: V-{task_id}-{counter}
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM pm_verifications WHERE task_id=?",
                (task_id,),
            )
            row = await cursor.fetchone()
            count = (row[0] if row else 0) + 1
            v_id = f"V-{task_id}-{count:03d}"
            await db.execute(
                """INSERT INTO pm_verifications
                   (id, task_id, original_dept, verifier_dept,
                    original_model, verifier_model, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)""",
                (v_id, task_id, original_dept, verifier_dept,
                 original_model, verifier_model, now, now),
            )
            await db.commit()
        return v_id

    async def get_verification(self, verification_id: str) -> dict | None:
        """검증 레코드 조회."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM pm_verifications WHERE id=?",
                (verification_id,),
            )
            row = await cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            d["issues"] = json.loads(d["issues"])
            d["suggestions"] = json.loads(d["suggestions"])
            return d

    async def update_verification(
        self,
        verification_id: str,
        verdict: str,
        issues: list[str] | None = None,
        suggestions: list[str] | None = None,
    ) -> dict | None:
        """검증 결과 업데이트."""
        now = _utcnow_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """UPDATE pm_verifications
                   SET verdict=?, issues=?, suggestions=?, status='completed', updated_at=?
                   WHERE id=?""",
                (verdict, json.dumps(issues or []), json.dumps(suggestions or []),
                 now, verification_id),
            )
            await db.commit()
        return await self.get_verification(verification_id)

    async def get_verifications_for_task(self, task_id: str) -> list[dict]:
        """태스크에 대한 모든 검증 레코드 조회."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM pm_verifications WHERE task_id=? ORDER BY created_at",
                (task_id,),
            )
            rows = await cursor.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["issues"] = json.loads(d["issues"])
                d["suggestions"] = json.loads(d["suggestions"])
                result.append(d)
            return result

    # ── Goal CRUD ──────────────────────────────────────────────────────────

    async def create_goal(self, goal_id: str, description: str,
                          created_by: str, chat_id: int,
                          max_iterations: int = 10) -> dict:
        """PM 목표 생성."""
        now = _utcnow_iso()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO pm_goals
                   (id, description, status, milestones, iteration, max_iterations,
                    stagnation_count, chat_id, created_by, created_at, updated_at)
                   VALUES (?, ?, 'active', '[]', 0, ?, 0, ?, ?, ?, ?)""",
                (goal_id, description, max_iterations, chat_id, created_by, now, now),
            )
            await db.commit()
        return {"id": goal_id, "description": description, "status": "active",
                "milestones": [], "iteration": 0, "max_iterations": max_iterations,
                "stagnation_count": 0, "chat_id": chat_id,
                "created_by": created_by, "created_at": now, "updated_at": now}

    async def get_goal(self, goal_id: str) -> dict | None:
        """PM 목표 조회."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM pm_goals WHERE id=?", (goal_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            d["milestones"] = json.loads(d["milestones"])
            return d

    async def get_active_goals(self) -> list[dict]:
        """활성 목표 목록."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM pm_goals WHERE status='active' ORDER BY created_at"
            )
            rows = await cursor.fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["milestones"] = json.loads(d["milestones"])
                result.append(d)
            return result

    async def _query_max_goal_counter(self, org_id: str) -> int:
        """기존 goal ID에서 최대 카운터 값을 추출. restart-safe ID 생성용."""
        prefix = f"G-{org_id}-"
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT id FROM pm_goals WHERE id LIKE ? ORDER BY id DESC LIMIT 1",
                (f"{prefix}%",),
            )
            row = await cursor.fetchone()
            if not row:
                return 0
            # "G-pm-003" → 3
            try:
                return int(row[0].replace(prefix, ""))
            except (ValueError, IndexError):
                return 0

    async def update_goal(self, goal_id: str, **kwargs) -> dict | None:
        """PM 목표 업데이트. milestones, status, iteration, stagnation_count, last_progress 지원."""
        now = _utcnow_iso()

        # 각 컬럼을 명시적으로 처리 (SQL injection 방지)
        set_parts: list[str] = []
        values: list = []

        if "status" in kwargs:
            set_parts.append("status=?")
            values.append(kwargs["status"])
        if "milestones" in kwargs:
            set_parts.append("milestones=?")
            values.append(json.dumps(kwargs["milestones"]))
        if "iteration" in kwargs:
            set_parts.append("iteration=?")
            values.append(kwargs["iteration"])
        if "stagnation_count" in kwargs:
            set_parts.append("stagnation_count=?")
            values.append(kwargs["stagnation_count"])
        if "last_progress" in kwargs:
            set_parts.append("last_progress=?")
            values.append(kwargs["last_progress"])

        if not set_parts:
            return await self.get_goal(goal_id)

        set_parts.append("updated_at=?")
        values.append(now)
        values.append(goal_id)

        set_clause = ", ".join(set_parts)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE pm_goals SET {set_clause} WHERE id=?",
                values,
            )
            await db.commit()
        return await self.get_goal(goal_id)

    # ── Conversation Messages ──────────────────────────────────────────────

    async def insert_conversation_message(
        self,
        *,
        msg_id: int | None,
        chat_id: str,
        user_id: str,
        bot_id: str | None,
        role: str,
        is_bot: bool,
        content: str,
        timestamp: str,
    ) -> None:
        """대화 메시지 삽입."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO conversation_messages
                   (msg_id, chat_id, user_id, bot_id, role, is_bot, content, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (msg_id, chat_id, user_id, bot_id, role, int(is_bot), content, timestamp),
            )
            await db.commit()

    async def get_conversation_messages(
        self,
        *,
        chat_id: str | None = None,
        user_id: str | None = None,
        is_bot: bool | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """대화 메시지 조회. 필터 조건이 없으면 전체 반환."""
        clauses: list[str] = []
        params: list = []
        if chat_id is not None:
            clauses.append("chat_id = ?")
            params.append(chat_id)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        if is_bot is not None:
            clauses.append("is_bot = ?")
            params.append(int(is_bot))
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"SELECT * FROM conversation_messages {where} ORDER BY timestamp DESC LIMIT ?",
                params,
            )
            rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def cleanup_old_conversations(self, retention_days: int = 30) -> int:
        """retention_days일 이전 메시지를 삭제한다. 삭제된 행 수 반환."""
        from datetime import datetime, timedelta, UTC
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "DELETE FROM conversation_messages WHERE timestamp < ?", (cutoff,)
            )
            await db.commit()
            return cursor.rowcount

    # ── Bot Performance ────────────────────────────────────────────────────

    async def record_bot_task_completion(
        self,
        bot_id: str,
        success: bool,
        latency_sec: float,
        week: str | None = None,
    ) -> None:
        """봇 태스크 완료 시 성과 DB 업데이트. week: ISO week (e.g. '2026-W11').

        Uses atomic INSERT ... ON CONFLICT DO UPDATE to avoid TOCTOU races.
        IMPORTANT: Uses bot_performance.colname in SET clause to reference pre-update values.
        """
        from datetime import datetime, UTC
        if week is None:
            now = datetime.now(UTC)
            week = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"
        now_iso = _utcnow_iso()
        sc_delta = 1 if success else 0
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO bot_performance
                    (bot_id, week, task_count, success_count,
                     total_latency_sec, avg_latency_sec, updated_at)
                VALUES (?, ?, 1, ?, ?, ?, ?)
                ON CONFLICT(bot_id, week) DO UPDATE SET
                    task_count        = bot_performance.task_count + 1,
                    success_count     = bot_performance.success_count + ?,
                    total_latency_sec = bot_performance.total_latency_sec + ?,
                    avg_latency_sec   = (bot_performance.total_latency_sec + ?)
                                        / (bot_performance.task_count + 1),
                    updated_at        = ?
                """,
                (bot_id, week, sc_delta, latency_sec, latency_sec, now_iso,
                 sc_delta, latency_sec, latency_sec, now_iso),
            )
            await db.commit()

    async def get_bot_performance(
        self, bot_id: str, week: str | None = None,
    ) -> dict | None:
        """봇 주간 성과 조회. week 미지정 시 현재 주."""
        from datetime import datetime, UTC
        if week is None:
            now = datetime.now(UTC)
            week = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM bot_performance WHERE bot_id=? AND week=?",
                (bot_id, week),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def get_all_bot_performance(
        self, week: str | None = None,
    ) -> list[dict]:
        """해당 주 전체 봇 성과 조회 (success_count DESC, avg_latency_sec ASC 정렬)."""
        from datetime import datetime, UTC
        if week is None:
            now = datetime.now(UTC)
            week = f"{now.isocalendar()[0]}-W{now.isocalendar()[1]:02d}"
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM bot_performance WHERE week=? "
                "ORDER BY success_count DESC, avg_latency_sec ASC",
                (week,),
            )
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
