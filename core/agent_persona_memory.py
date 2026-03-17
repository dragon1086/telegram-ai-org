"""에이전트 페르소나 기억 — 강점/약점/시너지 추적 시스템."""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / ".ai-org" / "agent_persona_memory.db"

# Canonical task_type vocabulary — shared between _infer_task_type (pm_orchestrator)
# and update_from_task (agent_persona_memory). Must stay in sync.
TASK_TYPE_VOCAB: frozenset[str] = frozenset({
    "coding", "design", "research", "planning", "ops", "marketing", "general"
})

STRENGTH_THRESHOLD = 3   # success_patterns에서 N회 이상 → strengths 자동 추가
WEAKNESS_THRESHOLD = 3   # failure_patterns에서 N회 이상 → weaknesses 자동 추가
SYNERGY_ALPHA = 0.2      # EMA 가중치
SYNERGY_DEFAULT = 0.5


@dataclass
class AgentStats:
    agent_id: str
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    failure_patterns: dict[str, int] = field(default_factory=dict)
    success_patterns: dict[str, int] = field(default_factory=dict)
    synergy_scores: dict[str, float] = field(default_factory=dict)
    total_tasks: int = 0
    success_tasks: int = 0
    updated_at: str = ""


class AgentPersonaMemory:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_stats (
                    agent_id        TEXT PRIMARY KEY,
                    strengths       TEXT DEFAULT '[]',
                    weaknesses      TEXT DEFAULT '[]',
                    failure_patterns TEXT DEFAULT '{}',
                    success_patterns TEXT DEFAULT '{}',
                    total_tasks     INTEGER DEFAULT 0,
                    success_tasks   INTEGER DEFAULT 0,
                    updated_at      TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS synergy_scores (
                    agent_a TEXT,
                    agent_b TEXT,
                    score   REAL DEFAULT 0.5,
                    PRIMARY KEY (agent_a, agent_b)
                )
            """)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _pair_key(self, a: str, b: str) -> tuple[str, str]:
        """항상 (작은 id, 큰 id) 순서로 정규화."""
        return (a, b) if a < b else (b, a)

    # ------------------------------------------------------------------
    # Private sync helpers — contain the actual sqlite3 work.
    # Call these directly from sync code, or via run_in_executor from async.
    # ------------------------------------------------------------------

    def _sync_load_stats_row(self, agent_id: str) -> dict:
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            row = conn.execute(
                "SELECT agent_id, strengths, weaknesses, failure_patterns, "
                "success_patterns, total_tasks, success_tasks, updated_at "
                "FROM agent_stats WHERE agent_id=?",
                (agent_id,)
            ).fetchone()
        if row is None:
            return {
                "agent_id": agent_id,
                "strengths": [],
                "weaknesses": [],
                "failure_patterns": {},
                "success_patterns": {},
                "total_tasks": 0,
                "success_tasks": 0,
                "updated_at": "",
            }
        return {
            "agent_id": row[0],
            "strengths": json.loads(row[1]),
            "weaknesses": json.loads(row[2]),
            "failure_patterns": json.loads(row[3]),
            "success_patterns": json.loads(row[4]),
            "total_tasks": row[5],
            "success_tasks": row[6],
            "updated_at": row[7] or "",
        }

    def _sync_save_stats_row(self, data: dict) -> None:
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute("""
                INSERT INTO agent_stats
                    (agent_id, strengths, weaknesses, failure_patterns,
                     success_patterns, total_tasks, success_tasks, updated_at)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    strengths        = excluded.strengths,
                    weaknesses       = excluded.weaknesses,
                    failure_patterns = excluded.failure_patterns,
                    success_patterns = excluded.success_patterns,
                    total_tasks      = excluded.total_tasks,
                    success_tasks    = excluded.success_tasks,
                    updated_at       = excluded.updated_at
            """, (
                data["agent_id"],
                json.dumps(data["strengths"], ensure_ascii=False),
                json.dumps(data["weaknesses"], ensure_ascii=False),
                json.dumps(data["failure_patterns"], ensure_ascii=False),
                json.dumps(data["success_patterns"], ensure_ascii=False),
                data["total_tasks"],
                data["success_tasks"],
                data["updated_at"],
            ))

    def _sync_update_synergy(self, a: str, b: str, new_score: float) -> None:
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute("""
                INSERT INTO synergy_scores (agent_a, agent_b, score)
                VALUES (?,?,?)
                ON CONFLICT(agent_a, agent_b) DO UPDATE SET score = excluded.score
            """, (a, b, new_score))

    def _sync_get_synergy_score(self, a: str, b: str) -> float:
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            row = conn.execute(
                "SELECT score FROM synergy_scores WHERE agent_a=? AND agent_b=?",
                (a, b)
            ).fetchone()
        return row[0] if row else SYNERGY_DEFAULT

    def _sync_recommend_team(self, task_type: str, count: int) -> list[str]:
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            rows = conn.execute(
                "SELECT agent_id, success_patterns, total_tasks, success_tasks "
                "FROM agent_stats"
            ).fetchall()
        candidates: list[tuple[float, str]] = []
        for agent_id, sp_json, total, successes in rows:
            sp: dict[str, int] = json.loads(sp_json)
            if task_type not in sp or sp[task_type] == 0:
                continue
            rate = successes / total if total > 0 else 0.0
            candidates.append((rate, agent_id))
        candidates.sort(reverse=True)
        return [agent_id for _, agent_id in candidates[:count]]

    def _sync_check_agent_exists(self, agent_id: str) -> bool:
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            return conn.execute(
                "SELECT 1 FROM agent_stats WHERE agent_id=?", (agent_id,)
            ).fetchone() is not None

    def _sync_get_synergy_rows(self, agent_id: str) -> list[tuple[str, str, float]]:
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            rows = conn.execute(
                "SELECT agent_a, agent_b, score FROM synergy_scores "
                "WHERE agent_a=? OR agent_b=?",
                (agent_id, agent_id)
            ).fetchall()
        return rows

    def _sync_get_all_agent_ids(self) -> list[str]:
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            rows = conn.execute("SELECT agent_id FROM agent_stats").fetchall()
        return [agent_id for (agent_id,) in rows]

    def _sync_get_top_performers(self, n: int) -> list[tuple[str, float]]:
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            rows = conn.execute(
                "SELECT agent_id, total_tasks, success_tasks FROM agent_stats "
                "WHERE total_tasks > 0"
            ).fetchall()
        ranked = [
            (agent_id, success / total)
            for agent_id, total, success in rows
        ]
        ranked.sort(key=lambda x: x[1], reverse=True)
        return ranked[:n]

    # ------------------------------------------------------------------
    # Public API — sync; safe to call from sync or via run_in_executor
    # from async contexts to avoid blocking the event loop.
    # ------------------------------------------------------------------

    def update_from_task(
        self,
        agent_id: str,
        task_type: str,
        success: bool,
        failure_category: str = "",
        collaborators: list[str] | None = None,
    ) -> None:
        """태스크 완료 후 호출.

        - success → success_patterns[task_type] += 1, strengths 업데이트
        - failure → failure_patterns[category] += 1, weaknesses 업데이트
        - collaborators → synergy_scores EMA 업데이트
        """
        if collaborators is None:
            collaborators = []

        task_type = task_type if task_type in TASK_TYPE_VOCAB else "general"

        data = self._sync_load_stats_row(agent_id)
        data["total_tasks"] += 1

        if success:
            data["success_tasks"] += 1
            sp = data["success_patterns"]
            sp[task_type] = sp.get(task_type, 0) + 1
            data["success_patterns"] = sp
            # 임계값 이상이면 strengths에 추가
            if sp[task_type] >= STRENGTH_THRESHOLD and task_type not in data["strengths"]:
                data["strengths"].append(task_type)
        else:
            category = failure_category or "other"
            fp = data["failure_patterns"]
            fp[category] = fp.get(category, 0) + 1
            data["failure_patterns"] = fp
            # 임계값 이상이면 weaknesses에 추가
            if fp[category] >= WEAKNESS_THRESHOLD and category not in data["weaknesses"]:
                data["weaknesses"].append(category)

        data["updated_at"] = self._now()
        self._sync_save_stats_row(data)

        for partner in collaborators:
            if partner != agent_id:
                self.update_synergy(agent_id, partner, success)

    def update_synergy(self, agent_a: str, agent_b: str, success: bool) -> None:
        """EMA: score = 0.8 * old_score + 0.2 * (1.0 if success else 0.0). 기본값 0.5."""
        a, b = self._pair_key(agent_a, agent_b)
        old_score = self.get_synergy_score(a, b)
        new_score = (1.0 - SYNERGY_ALPHA) * old_score + SYNERGY_ALPHA * (1.0 if success else 0.0)
        self._sync_update_synergy(a, b, new_score)

    def get_synergy_score(self, agent_a: str, agent_b: str) -> float:
        """두 에이전트 시너지 스코어 반환. 기본값 0.5. 양방향 조회."""
        a, b = self._pair_key(agent_a, agent_b)
        return self._sync_get_synergy_score(a, b)

    def recommend_team(self, task_type: str, count: int = 3) -> list[str]:
        """task_type에 success_patterns 있는 에이전트 중 성공률 높은 순서로 반환."""
        return self._sync_recommend_team(task_type, count)

    def get_stats(self, agent_id: str) -> AgentStats | None:
        data = self._sync_load_stats_row(agent_id)
        # 한 번도 기록된 적 없으면 None 반환
        if data["total_tasks"] == 0 and data["updated_at"] == "":
            if not self._sync_check_agent_exists(agent_id):
                return None

        rows = self._sync_get_synergy_rows(agent_id)
        synergy: dict[str, float] = {}
        for a, b, score in rows:
            partner = b if a == agent_id else a
            synergy[partner] = score

        return AgentStats(
            agent_id=data["agent_id"],
            strengths=data["strengths"],
            weaknesses=data["weaknesses"],
            failure_patterns=data["failure_patterns"],
            success_patterns=data["success_patterns"],
            synergy_scores=synergy,
            total_tasks=data["total_tasks"],
            success_tasks=data["success_tasks"],
            updated_at=data["updated_at"],
        )

    def get_all_stats(self) -> list[AgentStats]:
        agent_ids = self._sync_get_all_agent_ids()
        result = []
        for agent_id in agent_ids:
            stats = self.get_stats(agent_id)
            if stats is not None:
                result.append(stats)
        return result

    def get_top_performers(self, n: int = 3) -> list[tuple[str, float]]:
        """성공률 상위 N 에이전트 [(agent_id, success_rate)] 반환."""
        return self._sync_get_top_performers(n)
