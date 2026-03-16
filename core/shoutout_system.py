"""팀원 칭찬 기록 + 자동 MVP 선정 시스템."""
from __future__ import annotations

import logging
import random
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

DB_PATH = Path(__file__).parent.parent / ".ai-org" / "shoutout.db"

logger = logging.getLogger(__name__)


@dataclass
class Shoutout:
    id: str
    from_agent: str
    to_agent: str
    reason: str
    task_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ShoutoutSystem:
    def __init__(self, db_path: Path = DB_PATH, send_telegram_fn: Optional[Callable[[str], None]] = None):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.send_telegram_fn = send_telegram_fn
        self._personas: dict[str, str] = {}
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS shoutouts (
                    id TEXT PRIMARY KEY,
                    from_agent TEXT NOT NULL,
                    to_agent TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    task_id TEXT DEFAULT '',
                    created_at TEXT NOT NULL
                )
            """)

    def load_personas(self, bots_dir: Path) -> None:
        """bots/*.yaml 파일에서 personality/tone 로드. yaml 없으면 무시."""
        try:
            import yaml
        except ImportError:
            return

        for yaml_file in bots_dir.glob("*.yaml"):
            try:
                with open(yaml_file, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if not isinstance(data, dict):
                    continue
                agent_id = data.get("id") or yaml_file.stem
                tone = data.get("personality", {}).get("tone") or data.get("tone")
                if agent_id and tone:
                    self._personas[agent_id] = tone
            except Exception:
                pass

    def give_shoutout(self, from_agent: str, to_agent: str,
                      reason: str, task_id: str = "") -> Shoutout:
        """칭찬 기록 저장 + send_telegram_fn이 있으면 전송."""
        shoutout = Shoutout(
            id=str(uuid.uuid4())[:8],
            from_agent=from_agent,
            to_agent=to_agent,
            reason=reason,
            task_id=task_id,
        )
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute(
                "INSERT INTO shoutouts VALUES (?,?,?,?,?,?)",
                (shoutout.id, shoutout.from_agent, shoutout.to_agent,
                 shoutout.reason, shoutout.task_id, shoutout.created_at)
            )

        tone = self._personas.get(from_agent)
        base_msg = f"🎉 {from_agent}이(가) {to_agent}를 칭찬합니다!\n{reason}"
        message = f"[{tone}] {base_msg}" if tone else base_msg

        if self.send_telegram_fn is not None:
            try:
                self.send_telegram_fn(message)
            except Exception as e:
                logger.warning("send_telegram_fn 호출 실패: %s", e)

        return shoutout

    def auto_shoutout(self, task_id: str, winner: str,
                      reason: str, all_participants: list[str]) -> None:
        """태스크 완료 후 MVP(winner)에게 자동 칭찬."""
        others = [p for p in all_participants if p != winner]
        from_agent = random.choice(others) if others else "system"
        self.give_shoutout(
            from_agent=from_agent,
            to_agent=winner,
            reason=reason,
            task_id=task_id,
        )

    def get_top_recipients(self, days: int = 7) -> list[tuple[str, int]]:
        """최근 N일 칭찬 가장 많이 받은 봇 [(agent_id, count)] 내림차순."""
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            rows = conn.execute(
                "SELECT to_agent, COUNT(*) as cnt FROM shoutouts "
                "WHERE created_at > ? GROUP BY to_agent ORDER BY cnt DESC",
                (cutoff,)
            ).fetchall()
        return [(row[0], row[1]) for row in rows]

    def weekly_mvp(self) -> str | None:
        """이번 주(월~일) 가장 많이 칭찬받은 봇 반환. 없으면 None."""
        now = datetime.now(timezone.utc)
        monday = now - timedelta(days=now.weekday())
        week_start = monday.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            row = conn.execute(
                "SELECT to_agent, COUNT(*) as cnt FROM shoutouts "
                "WHERE created_at >= ? GROUP BY to_agent ORDER BY cnt DESC LIMIT 1",
                (week_start,)
            ).fetchone()
        return row[0] if row else None

    def get_received(self, agent_id: str, limit: int = 10) -> list[Shoutout]:
        """특정 에이전트가 받은 칭찬 최근 limit개."""
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            rows = conn.execute(
                "SELECT id, from_agent, to_agent, reason, task_id, created_at "
                "FROM shoutouts WHERE to_agent=? ORDER BY created_at DESC LIMIT ?",
                (agent_id, limit)
            ).fetchall()
        return [self._row_to_shoutout(r) for r in rows]

    def _row_to_shoutout(self, row) -> Shoutout:
        return Shoutout(
            id=row[0],
            from_agent=row[1],
            to_agent=row[2],
            reason=row[3],
            task_id=row[4],
            created_at=row[5],
        )
