"""프로젝트 메모리 테스트 — 중복 제거, 프루닝, RAG 검색, 원자적 저장."""
from __future__ import annotations

import json
import time
import tempfile
from pathlib import Path

import pytest

from core.project_memory import ProjectMemory, TaskRecord


@pytest.fixture
def memory(tmp_path):
    """격리된 임시 디렉토리에 메모리 생성."""
    mem = ProjectMemory(project_id="test")
    mem.BASE_DIR = tmp_path
    mem.path = tmp_path / "test.json"
    mem._data = {"tasks": [], "worker_stats": {}, "context_summary": ""}
    return mem


class TestBasicAPI:
    """기존 API 하위호환 테스트."""

    def test_record_and_total(self, memory):
        record = TaskRecord(
            task_id="T001",
            description="코드 리뷰",
            assigned_to=["w1"],
            result="완료",
            success=True,
            duration_sec=30.0,
        )
        memory.record_task(record)
        assert memory.total_tasks == 1

    def test_worker_stats_updated(self, memory):
        record = TaskRecord(
            task_id="T001",
            description="테스트",
            assigned_to=["w1"],
            result="ok",
            success=True,
            duration_sec=10.0,
        )
        memory.record_task(record)
        assert memory.worker_stats["w1"]["done"] == 1

    def test_get_best_worker(self, memory):
        for i in range(5):
            memory.record_task(TaskRecord(
                task_id=f"T{i:03d}",
                description="task",
                assigned_to=["w1"],
                result="ok",
                success=True,
                duration_sec=10.0,
            ))
        for i in range(5):
            memory.record_task(TaskRecord(
                task_id=f"F{i:03d}",
                description="task",
                assigned_to=["w2"],
                result="fail",
                success=False,
                duration_sec=10.0,
            ))
        best = memory.get_best_worker(["w1", "w2"])
        assert best == "w1"

    def test_get_best_worker_new(self, memory):
        """신규 워커(기록 없음)도 0.5 점수로 참여."""
        best = memory.get_best_worker(["new_worker"])
        assert best == "new_worker"

    def test_get_recent_context(self, memory):
        memory.record_task(TaskRecord(
            task_id="T001",
            description="리뷰 작업",
            assigned_to=["w1"],
            result="ok",
            success=True,
            duration_sec=5.0,
        ))
        ctx = memory.get_recent_context(5)
        assert "리뷰 작업" in ctx
        assert "✅" in ctx

    def test_context_summary(self, memory):
        memory.update_context_summary("프로젝트 요약")
        assert memory.get_context_summary() == "프로젝트 요약"


class TestDeduplication:
    """중복 제거 테스트."""

    def test_duplicate_within_window(self, memory):
        r1 = TaskRecord(
            task_id="T001", description="같은 태스크",
            assigned_to=["w1"], result="ok", success=True, duration_sec=10.0,
        )
        r2 = TaskRecord(
            task_id="T002", description="같은 태스크",
            assigned_to=["w1"], result="updated", success=True, duration_sec=20.0,
        )
        memory.record_task(r1)
        memory.record_task(r2)
        # 중복이므로 태스크 수는 1개
        assert memory.total_tasks == 1
        # 결과는 최신 값으로 업데이트
        assert memory._data["tasks"][0]["result"] == "updated"
        assert memory._data["tasks"][0]["duplicate_count"] == 2

    def test_different_descriptions_not_duplicate(self, memory):
        r1 = TaskRecord(
            task_id="T001", description="태스크 A",
            assigned_to=["w1"], result="ok", success=True, duration_sec=10.0,
        )
        r2 = TaskRecord(
            task_id="T002", description="태스크 B",
            assigned_to=["w1"], result="ok", success=True, duration_sec=10.0,
        )
        memory.record_task(r1)
        memory.record_task(r2)
        assert memory.total_tasks == 2


class TestPruning:
    """TTL/점수 기반 프루닝 테스트."""

    def test_prune_old_tasks(self, memory):
        now = time.time()
        # 100일 전 태스크 추가
        for i in range(10):
            memory._data["tasks"].append({
                "task_id": f"OLD{i}",
                "description": "old task",
                "assigned_to": ["w1"],
                "result": "ok",
                "success": True,
                "duration_sec": 10.0,
                "timestamp": now - 86400 * 100,  # 100일 전
                "relevance_score": 0.01,
                "duplicate_count": 1,
            })
        # 최근 태스크 추가
        memory._data["tasks"].append({
            "task_id": "NEW1",
            "description": "new task",
            "assigned_to": ["w1"],
            "result": "ok",
            "success": True,
            "duration_sec": 5.0,
            "timestamp": now,
            "relevance_score": 1.0,
            "duplicate_count": 1,
        })

        removed = memory.prune(min_score=0.05)
        assert removed == 10
        assert memory.total_tasks == 1
        assert memory._data["tasks"][0]["task_id"] == "NEW1"

    def test_prune_max_tasks(self, memory):
        now = time.time()
        for i in range(20):
            memory._data["tasks"].append({
                "task_id": f"T{i:03d}",
                "description": f"task {i}",
                "assigned_to": ["w1"],
                "result": "ok",
                "success": True,
                "duration_sec": 10.0,
                "timestamp": now - i * 3600,  # 1시간 간격
                "relevance_score": 1.0,
                "duplicate_count": 1,
            })
        removed = memory.prune(max_tasks=5)
        assert memory.total_tasks == 5

    def test_score_calculation(self):
        now = time.time()
        # 0일 → 1.0
        assert abs(ProjectMemory._calc_relevance_score(now, now) - 1.0) < 0.001
        # 1일 → 0.95
        assert abs(ProjectMemory._calc_relevance_score(now - 86400, now) - 0.95) < 0.001
        # 30일 → ~0.215
        score_30d = ProjectMemory._calc_relevance_score(now - 86400 * 30, now)
        assert 0.1 < score_30d < 0.3


class TestRAGSearch:
    """RAG 검색 테스트."""

    def test_search_relevant(self, memory):
        memory.record_task(TaskRecord(
            task_id="T001", description="React 컴포넌트 리팩토링",
            assigned_to=["w1"], result="성공", success=True, duration_sec=60.0,
        ))
        memory.record_task(TaskRecord(
            task_id="T002", description="Python 테스트 작성",
            assigned_to=["w2"], result="완료", success=True, duration_sec=30.0,
        ))
        memory.record_task(TaskRecord(
            task_id="T003", description="React 버그 수정",
            assigned_to=["w1"], result="fixed", success=True, duration_sec=45.0,
        ))

        results = memory.search_relevant("React 관련 작업")
        assert len(results) >= 2
        # React 관련 태스크가 먼저 나와야 함
        descriptions = [r.description for r in results]
        assert any("React" in d for d in descriptions)

    def test_search_no_match(self, memory):
        memory.record_task(TaskRecord(
            task_id="T001", description="코드 리뷰",
            assigned_to=["w1"], result="ok", success=True, duration_sec=10.0,
        ))
        results = memory.search_relevant("zzzzxyzzy_nonexistent")
        assert len(results) == 0

    def test_get_worker_performance(self, memory):
        for i in range(5):
            memory.record_task(TaskRecord(
                task_id=f"T{i:03d}", description="API 개발 작업",
                assigned_to=["w1"], result="ok", success=True, duration_sec=20.0,
            ))
        memory.record_task(TaskRecord(
            task_id="TFAIL", description="API 장애 대응",
            assigned_to=["w1"], result="실패", success=False, duration_sec=120.0,
        ))

        perf = memory.get_worker_performance("w1")
        assert perf["worker"] == "w1"
        assert perf["total_tasks"] == 6
        assert 0.8 < perf["success_rate"] < 0.9
        assert len(perf["recent_trend"]) <= 10
        assert len(perf["specialties"]) > 0

    def test_get_worker_performance_empty(self, memory):
        perf = memory.get_worker_performance("nonexistent")
        assert perf["total_tasks"] == 0

    def test_get_planning_context(self, memory):
        memory.record_task(TaskRecord(
            task_id="T001", description="인증 시스템 구현",
            assigned_to=["w1"], result="JWT 기반 구현 완료", success=True, duration_sec=300.0,
        ))
        ctx = memory.get_planning_context("인증 관련 개선")
        assert "관련 과거 태스크" in ctx
        assert "인증" in ctx

    def test_get_planning_context_empty(self, memory):
        ctx = memory.get_planning_context("아무런 관련 없는 쿼리 xyz")
        assert "관련 이전 태스크 없음" in ctx


class TestDataIntegrity:
    """원자적 저장 + 데이터 검증 테스트."""

    def test_atomic_save(self, memory):
        memory.record_task(TaskRecord(
            task_id="T001", description="test",
            assigned_to=["w1"], result="ok", success=True, duration_sec=1.0,
        ))
        # 파일이 정상 저장되었는지 확인
        assert memory.path.exists()
        data = json.loads(memory.path.read_text())
        assert len(data["tasks"]) == 1

    def test_validate_corrupt_data(self, memory):
        """손상된 데이터 로드 시 안전하게 복구."""
        corrupted = {"tasks": "not_a_list", "worker_stats": 42}
        result = memory._validate_data(corrupted)
        assert isinstance(result["tasks"], list)
        assert isinstance(result["worker_stats"], dict)
        assert isinstance(result["context_summary"], str)

    def test_validate_invalid_task_records(self, memory):
        """필수 필드 없는 태스크 레코드 제거."""
        data = {
            "tasks": [
                {"task_id": "T001", "description": "valid"},
                {"bad": "record"},
                {"task_id": "T002", "description": "also valid"},
            ],
            "worker_stats": {},
            "context_summary": "",
        }
        result = memory._validate_data(data)
        assert len(result["tasks"]) == 2

    def test_auto_prune_on_save(self, memory):
        """MAX_TASKS 초과 시 자동 프루닝."""
        memory.MAX_TASKS = 10
        now = time.time()
        for i in range(15):
            memory._data["tasks"].append({
                "task_id": f"T{i:03d}",
                "description": f"task {i}",
                "assigned_to": ["w1"],
                "result": "ok",
                "success": True,
                "duration_sec": 10.0,
                "timestamp": now - i * 86400,
                "relevance_score": 1.0,
                "duplicate_count": 1,
            })
        memory._save()
        assert memory.total_tasks <= 10
