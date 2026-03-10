"""프로젝트 메모리 — PM이 이전 태스크에서 학습하고 맥락 누적."""
from __future__ import annotations

import json
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Any

from loguru import logger


@dataclass
class TaskRecord:
    task_id: str
    description: str
    assigned_to: list[str]
    result: str | None
    success: bool
    duration_sec: float
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class ProjectMemory:
    """프로젝트별 태스크 이력 + 학습 정보 영속 저장.

    저장 위치: ~/.ai-org/memory/<project_id>.json
    """

    BASE_DIR = Path.home() / ".ai-org" / "memory"

    def __init__(self, project_id: str = "default") -> None:
        self.project_id = project_id
        self.path = self.BASE_DIR / f"{project_id}.json"
        self.BASE_DIR.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text())
            except Exception:
                pass
        return {"tasks": [], "worker_stats": {}, "context_summary": ""}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2))

    def record_task(self, record: TaskRecord) -> None:
        """태스크 결과 기록."""
        self._data["tasks"].append(asdict(record))

        # 워커 통계 업데이트
        for worker in record.assigned_to:
            stats = self._data["worker_stats"].setdefault(worker, {"done": 0, "fail": 0, "avg_sec": 0.0})
            if record.success:
                stats["done"] += 1
            else:
                stats["fail"] += 1
            # 이동 평균
            n = stats["done"] + stats["fail"]
            stats["avg_sec"] = (stats["avg_sec"] * (n - 1) + record.duration_sec) / n

        self._save()
        logger.debug(f"태스크 기록: {record.task_id} ({'성공' if record.success else '실패'})")

    def get_best_worker(self, candidates: list[str]) -> str | None:
        """성공률 + 속도 기반 최적 워커 선택."""
        scored = []
        for w in candidates:
            stats = self._data["worker_stats"].get(w, {})
            done = stats.get("done", 0)
            fail = stats.get("fail", 0)
            total = done + fail
            if total == 0:
                score = 0.5  # 신규 워커 중간 점수
            else:
                success_rate = done / total
                speed_bonus = 1.0 / (1.0 + stats.get("avg_sec", 60) / 60)
                score = success_rate * 0.7 + speed_bonus * 0.3
            scored.append((w, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0] if scored else None

    def get_recent_context(self, n: int = 5) -> str:
        """최근 n개 태스크 요약 (PM이 새 태스크 처리 시 참고)."""
        recent = self._data["tasks"][-n:]
        if not recent:
            return ""
        lines = ["[최근 작업 이력]"]
        for t in recent:
            status = "✅" if t.get("success") else "❌"
            workers = ", ".join(t.get("assigned_to", []))
            desc = t.get("description", "")[:60]
            lines.append(f"{status} [{workers}] {desc}")
        return "\n".join(lines)

    def update_context_summary(self, summary: str) -> None:
        """PM이 주기적으로 전체 프로젝트 맥락 요약 갱신."""
        self._data["context_summary"] = summary
        self._save()

    def get_context_summary(self) -> str:
        return self._data.get("context_summary", "")

    @property
    def total_tasks(self) -> int:
        return len(self._data["tasks"])

    @property
    def worker_stats(self) -> dict:
        return self._data["worker_stats"]
