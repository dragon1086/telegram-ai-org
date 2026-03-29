"""TaskRepository 단위 테스트 — Phase 2-A.

SQLite :memory: DB를 사용해 각 테스트를 격리합니다.
ENABLE_REPOSITORY_PATTERN=1 환경변수를 autouse fixture에서 설정합니다.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def enable_repository_pattern(monkeypatch):
    """모든 테스트에서 ENABLE_REPOSITORY_PATTERN=1 설정."""
    monkeypatch.setenv("ENABLE_REPOSITORY_PATTERN", "1")


@pytest.fixture
async def repo():
    """각 테스트마다 새로운 in-memory TaskRepository를 생성한다."""
    from core.repositories.task_repository import TaskRepository

    r = TaskRepository(db_path=":memory:")
    await r.initialize()
    return r


def _make_task(**kwargs) -> dict:
    """테스트용 태스크 딕셔너리 팩토리."""
    now = time.time()
    base = {
        "task_id": str(uuid.uuid4()),
        "org_id": "dev",
        "description": "테스트 태스크",
        "status": "pending",
        "created_at": now,
        "updated_at": now,
        "result": None,
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# initialize()
# ---------------------------------------------------------------------------


async def test_initialize_creates_table(repo) -> None:
    """initialize() 호출 후 tasks 테이블이 존재해야 한다."""
    import aiosqlite

    async with aiosqlite.connect(":memory:") as db:
        from core.repositories.task_repository import TaskRepository
        r = TaskRepository(db_path=":memory:")
        await r.initialize()
        # initialize 성공 후 save가 가능한지 확인
        task = _make_task()
        await r.save(task)
        result = await r.get(task["task_id"])
        assert result is not None


# ---------------------------------------------------------------------------
# save() / get()
# ---------------------------------------------------------------------------


async def test_save_and_get_task(repo) -> None:
    """save() 후 get()으로 동일 데이터를 조회할 수 있어야 한다."""
    task = _make_task(description="저장 테스트")
    await repo.save(task)

    result = await repo.get(task["task_id"])
    assert result is not None
    assert result["task_id"] == task["task_id"]
    assert result["description"] == "저장 테스트"
    assert result["status"] == "pending"
    assert result["org_id"] == "dev"


async def test_get_nonexistent_returns_none(repo) -> None:
    """존재하지 않는 task_id 조회 시 None을 반환해야 한다."""
    result = await repo.get("nonexistent-id-12345")
    assert result is None


async def test_save_upsert_behavior(repo) -> None:
    """같은 task_id로 두 번 save() 시 최신 데이터로 덮어써야 한다."""
    task = _make_task(description="초기 설명")
    await repo.save(task)

    updated = {**task, "description": "수정된 설명", "status": "in_progress"}
    await repo.save(updated)

    result = await repo.get(task["task_id"])
    assert result is not None
    assert result["description"] == "수정된 설명"
    assert result["status"] == "in_progress"


# ---------------------------------------------------------------------------
# update_status()
# ---------------------------------------------------------------------------


async def test_update_status_success(repo) -> None:
    """존재하는 태스크의 상태를 업데이트하면 True를 반환해야 한다."""
    task = _make_task()
    await repo.save(task)

    updated = await repo.update_status(task["task_id"], "done", result="완료")
    assert updated is True

    result = await repo.get(task["task_id"])
    assert result is not None
    assert result["status"] == "done"
    assert result["result"] == "완료"


async def test_update_status_nonexistent(repo) -> None:
    """존재하지 않는 task_id 업데이트 시 False를 반환해야 한다."""
    updated = await repo.update_status("nonexistent-xyz", "done")
    assert updated is False


# ---------------------------------------------------------------------------
# list_by_status()
# ---------------------------------------------------------------------------


async def test_list_by_status_filters_correctly(repo) -> None:
    """pending/done 혼재 시 list_by_status('pending')이 pending만 반환해야 한다."""
    pending1 = _make_task(status="pending")
    pending2 = _make_task(status="pending")
    done_task = _make_task(status="done")

    await repo.save(pending1)
    await repo.save(pending2)
    await repo.save(done_task)

    results = await repo.list_by_status("pending")
    assert len(results) == 2
    assert all(t["status"] == "pending" for t in results)


async def test_list_by_status_empty(repo) -> None:
    """해당 상태의 태스크가 없으면 빈 리스트를 반환해야 한다."""
    results = await repo.list_by_status("done")
    assert results == []


# ---------------------------------------------------------------------------
# list_all()
# ---------------------------------------------------------------------------


async def test_list_all_returns_all_tasks(repo) -> None:
    """list_all()은 상태에 관계없이 모든 태스크를 반환해야 한다."""
    for s in ["pending", "done", "failed"]:
        await repo.save(_make_task(status=s))

    results = await repo.list_all()
    assert len(results) == 3


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------


async def test_delete_removes_task(repo) -> None:
    """delete() 후 get()으로 조회하면 None이 반환되어야 한다."""
    task = _make_task()
    await repo.save(task)

    await repo.delete(task["task_id"])
    result = await repo.get(task["task_id"])
    assert result is None


async def test_delete_nonexistent_no_error(repo) -> None:
    """존재하지 않는 task_id를 delete() 해도 에러가 발생하지 않아야 한다."""
    await repo.delete("nonexistent-abc")  # 예외 없이 통과
