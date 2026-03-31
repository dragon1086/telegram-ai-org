"""Phase 1 단위 테스트 — core.repositories.task_repository 모듈.

테스트 대상: core/repositories/task_repository.py (SQLite CRUD, :memory: DB)
"""
from __future__ import annotations

import asyncio
import time

import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def event_loop():
    """asyncio 이벤트 루프 픽스처."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def repo():
    """초기화된 :memory: TaskRepository를 제공한다."""
    from core.repositories.task_repository import TaskRepository
    r = TaskRepository(db_path=":memory:")
    await r.initialize()
    yield r
    await r.close()


def _make_task(task_id: str = "T-001", org_id: str = "dev", status: str = "pending") -> dict:
    now = time.time()
    return {
        "task_id": task_id,
        "org_id": org_id,
        "description": f"테스트 태스크 {task_id}",
        "status": status,
        "created_at": now,
        "updated_at": now,
        "result": None,
    }


# ---------------------------------------------------------------------------
# Happy Path 테스트
# ---------------------------------------------------------------------------

class TestTaskRepositoryHappyPath:
    @pytest.mark.asyncio
    async def test_save_and_get(self, repo):
        """저장 후 동일 task_id로 조회 시 동일 데이터가 반환돼야 한다."""
        task = _make_task("T-001")
        await repo.save(task)
        result = await repo.get("T-001")
        assert result is not None
        assert result["task_id"] == "T-001"
        assert result["org_id"] == "dev"
        assert result["status"] == "pending"

    @pytest.mark.asyncio
    async def test_save_multiple_tasks(self, repo):
        """여러 태스크 저장 후 list_all 크기가 일치해야 한다."""
        for i in range(3):
            await repo.save(_make_task(f"T-{i:03d}"))
        tasks = await repo.list_all()
        assert len(tasks) == 3

    @pytest.mark.asyncio
    async def test_update_status_happy_path(self, repo):
        """update_status 후 상태가 변경돼야 한다."""
        await repo.save(_make_task("T-002"))
        updated = await repo.update_status("T-002", "done", result="성공")
        assert updated is True
        task = await repo.get("T-002")
        assert task["status"] == "done"
        assert task["result"] == "성공"

    @pytest.mark.asyncio
    async def test_list_by_status(self, repo):
        """list_by_status가 해당 상태만 반환해야 한다."""
        await repo.save(_make_task("T-A", status="pending"))
        await repo.save(_make_task("T-B", status="done"))
        await repo.save(_make_task("T-C", status="pending"))

        pending = await repo.list_by_status("pending")
        done = await repo.list_by_status("done")

        assert len(pending) == 2
        assert len(done) == 1
        assert done[0]["task_id"] == "T-B"

    @pytest.mark.asyncio
    async def test_delete_task(self, repo):
        """삭제 후 get이 None을 반환해야 한다."""
        await repo.save(_make_task("T-DEL"))
        await repo.delete("T-DEL")
        result = await repo.get("T-DEL")
        assert result is None

    @pytest.mark.asyncio
    async def test_save_upsert_behavior(self, repo):
        """동일 task_id로 save 시 덮어쓰기(upsert)가 돼야 한다."""
        task = _make_task("T-UPS")
        await repo.save(task)
        task["description"] = "업데이트된 설명"
        await repo.save(task)
        result = await repo.get("T-UPS")
        assert result["description"] == "업데이트된 설명"


# ---------------------------------------------------------------------------
# 엣지 케이스 / 경계값 테스트
# ---------------------------------------------------------------------------

class TestTaskRepositoryEdgeCases:
    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, repo):
        """존재하지 않는 task_id 조회 시 None을 반환해야 한다."""
        result = await repo.get("NON_EXISTENT_ID")
        assert result is None

    @pytest.mark.asyncio
    async def test_update_status_nonexistent_returns_false(self, repo):
        """존재하지 않는 task_id 업데이트 시 False를 반환해야 한다."""
        result = await repo.update_status("NON_EXISTENT", "done")
        assert result is False

    @pytest.mark.asyncio
    async def test_delete_nonexistent_no_error(self, repo):
        """존재하지 않는 태스크 삭제 시 예외가 발생하지 않아야 한다."""
        await repo.delete("NO_SUCH_TASK")  # 예외 없이 통과

    @pytest.mark.asyncio
    async def test_list_by_status_empty_returns_empty_list(self, repo):
        """해당 상태 태스크가 없으면 빈 리스트를 반환해야 한다."""
        result = await repo.list_by_status("failed")
        assert result == []

    @pytest.mark.asyncio
    async def test_list_all_empty_returns_empty_list(self, repo):
        """태스크가 없으면 list_all이 빈 리스트를 반환해야 한다."""
        result = await repo.list_all()
        assert result == []

    @pytest.mark.asyncio
    async def test_save_task_with_empty_result(self, repo):
        """result 필드가 None인 태스크도 정상 저장돼야 한다."""
        task = _make_task("T-NULL")
        task["result"] = None
        await repo.save(task)
        result = await repo.get("T-NULL")
        assert result is not None
        assert result["result"] is None

    @pytest.mark.asyncio
    async def test_save_task_minimal_fields(self, repo):
        """description과 task_id만 있는 최소 태스크도 저장 가능해야 한다."""
        minimal = {"task_id": "T-MIN", "description": "최소 태스크"}
        await repo.save(minimal)
        result = await repo.get("T-MIN")
        assert result is not None
        assert result["task_id"] == "T-MIN"

    @pytest.mark.asyncio
    async def test_update_status_without_result(self, repo):
        """result 없이 상태만 업데이트해도 동작해야 한다."""
        await repo.save(_make_task("T-NORES"))
        updated = await repo.update_status("T-NORES", "in_progress")
        assert updated is True
        task = await repo.get("T-NORES")
        assert task["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_task_id_with_special_characters(self, repo):
        """특수문자가 포함된 task_id도 정상 처리돼야 한다."""
        special_id = "T-aiorg_pm_bot-824"
        await repo.save({"task_id": special_id, "description": "특수문자 ID 테스트"})
        result = await repo.get(special_id)
        assert result is not None
        assert result["task_id"] == special_id

    @pytest.mark.asyncio
    async def test_large_description(self, repo):
        """매우 긴 description도 정상 저장돼야 한다."""
        long_desc = "A" * 10000
        await repo.save({"task_id": "T-LONG", "description": long_desc})
        result = await repo.get("T-LONG")
        assert result["description"] == long_desc


# ---------------------------------------------------------------------------
# 피처 플래그 테스트
# ---------------------------------------------------------------------------

class TestTaskRepositoryFeatureFlag:
    def test_memory_db_is_always_enabled(self):
        """:memory: DB는 ENABLE_REPOSITORY_PATTERN 무관하게 항상 활성화된다."""
        from core.repositories.task_repository import _is_enabled
        assert _is_enabled(":memory:") is True

    def test_file_db_enabled_by_default(self, tmp_path):
        """파일 DB는 ENABLE_REPOSITORY_PATTERN 미설정 시 기본 활성화(default=1)된다.

        Phase 2a 이후 모든 안전한 enable_* 기본값=1 (2026-03-31 변경).
        """
        import os
        from core.repositories.task_repository import _is_enabled
        os.environ.pop("ENABLE_REPOSITORY_PATTERN", None)
        assert _is_enabled(str(tmp_path / "test.db")) is True

    def test_file_db_disabled_explicitly(self, tmp_path, monkeypatch):
        """ENABLE_REPOSITORY_PATTERN=0이면 파일 DB가 비활성화된다."""
        monkeypatch.setenv("ENABLE_REPOSITORY_PATTERN", "0")
        from core.repositories.task_repository import _is_enabled
        assert _is_enabled(str(tmp_path / "test.db")) is False

    def test_file_db_enabled_when_flag_set(self, tmp_path, monkeypatch):
        """ENABLE_REPOSITORY_PATTERN=1이면 파일 DB도 활성화된다."""
        monkeypatch.setenv("ENABLE_REPOSITORY_PATTERN", "1")
        from core.repositories.task_repository import _is_enabled
        assert _is_enabled(str(tmp_path / "test.db")) is True
