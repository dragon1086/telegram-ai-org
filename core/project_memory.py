"""프로젝트 메모리 — PM이 이전 태스크에서 학습하고 맥락 누적.

Enhanced: 중복 제거, TTL/점수 기반 프루닝, RAG 검색, 향상된 워커 스코어링, 원자적 저장.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
from collections import Counter
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
    # 신규 옵셔널 필드 (하위 호환)
    relevance_score: float = 1.0
    duplicate_count: int = 1

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()


class ProjectMemory:
    """프로젝트별 태스크 이력 + 학습 정보 영속 저장.

    저장 위치: ~/.ai-org/memory/<project_id>.json
    """

    BASE_DIR = Path.home() / ".ai-org" / "memory"

    # 프루닝 기본값
    MAX_TASKS = 500
    MIN_SCORE = 0.1
    SCORE_DECAY = 0.95  # 하루당 감쇠율

    def __init__(self, project_id: str = "default") -> None:
        self.project_id = project_id
        self.path = self.BASE_DIR / f"{project_id}.json"
        self.BASE_DIR.mkdir(parents=True, exist_ok=True)
        self._data: dict[str, Any] = self._load()

    # ── 데이터 무결성 ──────────────────────────────────────

    def _validate_data(self, data: dict) -> dict:
        """손상된 파일 로드 시 안전하게 기본값으로 복구."""
        if not isinstance(data, dict):
            logger.warning("메모리 파일 형식 이상 — 기본값으로 초기화")
            return {"tasks": [], "worker_stats": {}, "context_summary": ""}

        if not isinstance(data.get("tasks"), list):
            data["tasks"] = []
        if not isinstance(data.get("worker_stats"), dict):
            data["worker_stats"] = {}
        if not isinstance(data.get("context_summary"), str):
            data["context_summary"] = ""

        # 각 태스크 레코드 필수 필드 검증
        valid_tasks = []
        for t in data["tasks"]:
            if isinstance(t, dict) and "task_id" in t and "description" in t:
                # 신규 필드 기본값 보장
                t.setdefault("relevance_score", 1.0)
                t.setdefault("duplicate_count", 1)
                valid_tasks.append(t)
            else:
                logger.warning(f"손상된 태스크 레코드 제거: {t!r:.80}")
        data["tasks"] = valid_tasks
        return data

    def _load(self) -> dict:
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text())
                return self._validate_data(raw)
            except (json.JSONDecodeError, OSError) as e:
                logger.error(f"메모리 파일 로드 실패 ({self.path}): {e}")
        return {"tasks": [], "worker_stats": {}, "context_summary": ""}

    def _save(self) -> None:
        """원자적 저장 — 임시 파일 → rename으로 데이터 손실 방지."""
        # max_tasks 초과 시 자동 프루닝
        if len(self._data["tasks"]) > self.MAX_TASKS:
            self.prune()

        try:
            fd, tmp_path = tempfile.mkstemp(
                dir=str(self.path.parent), suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, str(self.path))
            except BaseException:
                # 실패 시 임시 파일 정리
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except OSError as e:
            logger.error(f"메모리 저장 실패: {e}")

    # ── 중복 제거 ──────────────────────────────────────────

    def _is_duplicate(self, description: str, window_sec: int = 3600) -> dict | None:
        """최근 window_sec 이내 동일 description 태스크가 있으면 해당 태스크 반환."""
        now = time.time()
        cutoff = now - window_sec
        for task in reversed(self._data["tasks"]):
            ts = task.get("timestamp", 0)
            if ts < cutoff:
                break  # 시간순 정렬 가정, 오래된 건 스킵
            if task.get("description", "").strip() == description.strip():
                return task
        return None

    # ── 점수 계산 ──────────────────────────────────────────

    @staticmethod
    def _calc_relevance_score(timestamp: float, now: float | None = None) -> float:
        """시간 감쇠 기반 relevance_score 계산: 1.0 * (0.95 ^ days_old)."""
        now = now or time.time()
        days_old = (now - timestamp) / 86400
        return 1.0 * (0.95 ** days_old)

    # ── 프루닝 ─────────────────────────────────────────────

    def prune(self, max_tasks: int | None = None, min_score: float | None = None) -> int:
        """TTL/점수 기반 프루닝. 제거된 태스크 수 반환."""
        max_tasks = max_tasks if max_tasks is not None else self.MAX_TASKS
        min_score = min_score if min_score is not None else self.MIN_SCORE
        now = time.time()

        before = len(self._data["tasks"])

        # 점수 업데이트 및 최소 점수 미만 제거
        surviving = []
        for t in self._data["tasks"]:
            score = self._calc_relevance_score(t.get("timestamp", 0), now)
            t["relevance_score"] = score
            if score >= min_score:
                surviving.append(t)

        # max_tasks 초과 시 점수 낮은 순으로 제거
        if len(surviving) > max_tasks:
            surviving.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
            surviving = surviving[:max_tasks]
            # 시간순 복원
            surviving.sort(key=lambda x: x.get("timestamp", 0))

        self._data["tasks"] = surviving
        removed = before - len(surviving)
        if removed > 0:
            logger.info(f"프루닝 완료: {removed}건 제거 (잔여 {len(surviving)}건)")
        return removed

    # ── 핵심 API (기존 호환) ────────────────────────────────

    def record_task(self, record: TaskRecord) -> None:
        """태스크 결과 기록. 중복 시 merge."""
        # 중복 검사
        existing = self._is_duplicate(record.description)
        if existing is not None:
            existing["duplicate_count"] = existing.get("duplicate_count", 1) + 1
            existing["result"] = record.result
            existing["success"] = record.success
            existing["duration_sec"] = record.duration_sec
            existing["timestamp"] = record.timestamp or time.time()
            existing["relevance_score"] = 1.0
            logger.debug(f"중복 태스크 병합: {record.task_id} (count={existing['duplicate_count']})")
        else:
            self._data["tasks"].append(asdict(record))

        # 워커 통계 업데이트
        for worker in record.assigned_to:
            stats = self._data["worker_stats"].setdefault(
                worker, {"done": 0, "fail": 0, "avg_sec": 0.0}
            )
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
        """성공률 + 속도 + 최근성 + 태스크 유사도 기반 최적 워커 선택."""
        if not candidates:
            return None

        now = time.time()
        scored = []
        for w in candidates:
            stats = self._data["worker_stats"].get(w, {})
            done = stats.get("done", 0)
            fail = stats.get("fail", 0)
            total = done + fail
            if total == 0:
                score = 0.5  # 신규 워커 중간 점수
                scored.append((w, score))
                continue

            success_rate = done / total
            speed_bonus = 1.0 / (1.0 + stats.get("avg_sec", 60) / 60)

            # 최근 성과 가중치 — 최근 10개 태스크 성공률
            recent_tasks = [
                t for t in self._data["tasks"]
                if w in t.get("assigned_to", [])
            ][-10:]
            if recent_tasks:
                recent_success = sum(1 for t in recent_tasks if t.get("success")) / len(recent_tasks)
                recency_weight = 0.2
            else:
                recent_success = success_rate
                recency_weight = 0.0

            score = (
                success_rate * (0.5 - recency_weight / 2)
                + speed_bonus * 0.3
                + recent_success * recency_weight
            )
            scored.append((w, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[0][0]

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

    # ── RAG 검색 ───────────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """간단한 키워드 토큰화 (소문자, 2글자 이상)."""
        return {w.lower() for w in re.findall(r"\w+", text or "") if len(w) >= 2}

    def search_relevant(self, query: str, top_k: int = 5) -> list[TaskRecord]:
        """키워드 기반 태스크 검색 — description + result에서 매칭."""
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scored: list[tuple[float, dict]] = []
        now = time.time()
        for t in self._data["tasks"]:
            desc_tokens = self._tokenize(t.get("description", ""))
            result_tokens = self._tokenize(t.get("result", ""))
            all_tokens = desc_tokens | result_tokens
            overlap = len(query_tokens & all_tokens)
            if overlap == 0:
                continue
            # TF 기반 점수 + 시간 감쇠
            tf_score = overlap / len(query_tokens)
            time_score = self._calc_relevance_score(t.get("timestamp", 0), now)
            final = tf_score * 0.7 + time_score * 0.3
            scored.append((final, t))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for _, t in scored[:top_k]:
            results.append(TaskRecord(
                task_id=t.get("task_id", ""),
                description=t.get("description", ""),
                assigned_to=t.get("assigned_to", []),
                result=t.get("result"),
                success=t.get("success", False),
                duration_sec=t.get("duration_sec", 0.0),
                timestamp=t.get("timestamp", 0.0),
                relevance_score=t.get("relevance_score", 1.0),
                duplicate_count=t.get("duplicate_count", 1),
            ))
        return results

    def get_worker_performance(self, worker_name: str) -> dict:
        """워커 상세 성과: success_rate, avg_duration, recent_trend, specialties."""
        stats = self._data["worker_stats"].get(worker_name, {})
        done = stats.get("done", 0)
        fail = stats.get("fail", 0)
        total = done + fail

        if total == 0:
            return {
                "worker": worker_name,
                "total_tasks": 0,
                "success_rate": 0.0,
                "avg_duration": 0.0,
                "recent_trend": [],
                "specialties": [],
            }

        # 해당 워커의 태스크 필터링
        worker_tasks = [
            t for t in self._data["tasks"]
            if worker_name in t.get("assigned_to", [])
        ]

        # 최근 10개 태스크 트렌드
        recent = worker_tasks[-10:]
        recent_trend = [
            {"task_id": t.get("task_id"), "success": t.get("success"), "duration_sec": t.get("duration_sec", 0)}
            for t in recent
        ]

        # 전문 분야 — 태스크 description에서 자주 등장하는 키워드 top 5
        all_words: list[str] = []
        for t in worker_tasks:
            all_words.extend(self._tokenize(t.get("description", "")))
        # 불용어 제거 (한글/영어 기본)
        stopwords = {"the", "is", "to", "and", "of", "in", "for", "on", "작업", "완료", "결과", "태스크"}
        keyword_counts = Counter(w for w in all_words if w not in stopwords)
        specialties = [kw for kw, _ in keyword_counts.most_common(5)]

        return {
            "worker": worker_name,
            "total_tasks": total,
            "success_rate": done / total,
            "avg_duration": stats.get("avg_sec", 0.0),
            "recent_trend": recent_trend,
            "specialties": specialties,
        }

    def get_planning_context(self, task_description: str, n: int = 5) -> str:
        """플래너용 RAG 컨텍스트 — 유사 과거 태스크 + 관련 워커 성과 포맷팅."""
        relevant = self.search_relevant(task_description, top_k=n)
        if not relevant:
            return "[관련 이전 태스크 없음]"

        lines = ["[관련 과거 태스크]"]
        seen_workers: set[str] = set()

        for r in relevant:
            status = "성공" if r.success else "실패"
            workers = ", ".join(r.assigned_to)
            lines.append(f"- [{status}] {r.description[:80]} (담당: {workers}, {r.duration_sec:.0f}s)")
            seen_workers.update(r.assigned_to)

        # 관련 워커 성과 요약
        if seen_workers:
            lines.append("\n[관련 워커 성과]")
            for w in sorted(seen_workers):
                perf = self.get_worker_performance(w)
                if perf["total_tasks"] > 0:
                    rate_pct = perf["success_rate"] * 100
                    specs = ", ".join(perf["specialties"][:3]) if perf["specialties"] else "없음"
                    lines.append(f"- {w}: 성공률 {rate_pct:.0f}%, 평균 {perf['avg_duration']:.0f}s, 전문: {specs}")

        return "\n".join(lines)
