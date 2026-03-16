"""협업 기록 + 시너지 추적 시스템."""
from __future__ import annotations

import itertools
import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import uuid

DB_PATH = Path(__file__).parent.parent / ".ai-org" / "collaboration.db"


@dataclass
class CollaborationRecord:
    id: str
    task_id: str
    participants: list[str]
    task_type: str
    success: bool
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class CollaborationTracker:
    def __init__(self, db_path: Path = DB_PATH, persona_memory=None):
        self.db_path = db_path
        self.persona_memory = persona_memory
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS collaborations (
                    id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    participants TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    success INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)

    def record(self, task_id: str, participants: list[str],
               task_type: str, success: bool) -> CollaborationRecord:
        """협업 기록 저장. persona_memory가 있으면 모든 참가자 쌍에 update_synergy() 호출."""
        rec = CollaborationRecord(
            id=str(uuid.uuid4())[:8],
            task_id=task_id,
            participants=participants,
            task_type=task_type,
            success=success,
        )
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute(
                "INSERT INTO collaborations VALUES (?,?,?,?,?,?)",
                (rec.id, rec.task_id, json.dumps(rec.participants),
                 rec.task_type, int(rec.success), rec.created_at)
            )
        if self.persona_memory is not None:
            for a, b in itertools.combinations(participants, 2):
                self.persona_memory.update_synergy(a, b, success)
        return rec

    def get_frequent_pairs(self, min_count: int = 2) -> list[tuple[tuple, int]]:
        """자주 함께 일하는 봇 조합 반환 [((a, b), count)] 내림차순."""
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            rows = conn.execute("SELECT participants FROM collaborations").fetchall()
        counter: Counter = Counter()
        for (raw,) in rows:
            parts = json.loads(raw)
            for pair in itertools.combinations(sorted(parts), 2):
                counter[pair] += 1
        return sorted(
            [(pair, cnt) for pair, cnt in counter.items() if cnt >= min_count],
            key=lambda x: x[1],
            reverse=True,
        )

    def get_agent_collaborations(self, agent_id: str, days: int = 30) -> list[CollaborationRecord]:
        """특정 에이전트의 최근 days일 협업 히스토리."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            rows = conn.execute(
                "SELECT * FROM collaborations WHERE created_at > ? ORDER BY created_at DESC",
                (cutoff,)
            ).fetchall()
        return [
            self._row_to_record(r)
            for r in rows
            if agent_id in json.loads(r[2])
        ]

    def get_collaboration_graph(self) -> dict[str, dict[str, int]]:
        """전체 협업 그래프 {agent: {partner: count}}"""
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            rows = conn.execute("SELECT participants FROM collaborations").fetchall()
        graph: dict[str, dict[str, int]] = {}
        for (raw,) in rows:
            parts = json.loads(raw)
            for a, b in itertools.combinations(parts, 2):
                graph.setdefault(a, {}).setdefault(b, 0)
                graph[a][b] += 1
                graph.setdefault(b, {}).setdefault(a, 0)
                graph[b][a] += 1
        return graph

    def _row_to_record(self, row) -> CollaborationRecord:
        return CollaborationRecord(
            id=row[0],
            task_id=row[1],
            participants=json.loads(row[2]),
            task_type=row[3],
            success=bool(row[4]),
            created_at=row[5],
        )
