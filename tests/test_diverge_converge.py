"""DivergeConvergeProtocol 단위 테스트 — Phase 4."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context_db import ContextDB
from core.diverge_converge import DivergeConvergeProtocol


@pytest.fixture
async def db():
    with tempfile.TemporaryDirectory() as tmp:
        cdb = ContextDB(Path(tmp) / "test.db")
        await cdb.initialize()
        yield cdb


@pytest.fixture
def send_fn():
    return AsyncMock()


@pytest.mark.asyncio
async def test_diverge_creates_tasks(db, send_fn):
    """diverge가 복수 부서에 태스크를 생성하는지 확인."""
    proto = DivergeConvergeProtocol(db, send_fn)
    await db.create_pm_task("T-parent", "부모", None, "pm")

    task_ids = await proto.diverge(
        parent_task_id="T-parent",
        description="REST API vs GraphQL 비교 구현",
        target_depts=["aiorg_engineering_bot", "aiorg_product_bot"],
        created_by="pm",
        chat_id=123,
    )

    assert len(task_ids) == 2
    for tid in task_ids:
        task = await db.get_pm_task(tid)
        assert task is not None
        assert task["status"] == "assigned"
        assert task["parent_id"] == "T-parent"


@pytest.mark.asyncio
async def test_diverge_requires_two_depts(db, send_fn):
    """최소 2개 부서 필요."""
    proto = DivergeConvergeProtocol(db, send_fn)

    task_ids = await proto.diverge(
        parent_task_id="T-p",
        description="단일 부서",
        target_depts=["aiorg_engineering_bot"],
        created_by="pm",
        chat_id=123,
    )
    assert task_ids == []


@pytest.mark.asyncio
async def test_diverge_telegram_messages(db, send_fn):
    """diverge 시 Telegram 메시지 발송 확인."""
    proto = DivergeConvergeProtocol(db, send_fn)
    await db.create_pm_task("T-p2", "부모", None, "pm")

    await proto.diverge(
        parent_task_id="T-p2",
        description="비교 작업",
        target_depts=["aiorg_engineering_bot", "aiorg_product_bot"],
        created_by="pm",
        chat_id=123,
    )

    assert send_fn.await_count == 2  # 각 부서에 1개씩


@pytest.mark.asyncio
async def test_check_convergence_incomplete(db, send_fn):
    """일부 태스크 미완료 시 convergence False."""
    proto = DivergeConvergeProtocol(db, send_fn)
    await db.create_pm_task("T-p3", "부모", None, "pm")

    task_ids = await proto.diverge(
        parent_task_id="T-p3",
        description="비교",
        target_depts=["aiorg_engineering_bot", "aiorg_product_bot"],
        created_by="pm",
        chat_id=123,
    )

    # 하나만 완료
    await db.update_pm_task_status(task_ids[0], "done", result="결과 A")

    assert await proto.check_convergence(task_ids) is False


@pytest.mark.asyncio
async def test_check_convergence_complete(db, send_fn):
    """모든 태스크 완료 시 convergence True."""
    proto = DivergeConvergeProtocol(db, send_fn)
    await db.create_pm_task("T-p4", "부모", None, "pm")

    task_ids = await proto.diverge(
        parent_task_id="T-p4",
        description="비교",
        target_depts=["aiorg_engineering_bot", "aiorg_product_bot"],
        created_by="pm",
        chat_id=123,
    )

    for tid in task_ids:
        await db.update_pm_task_status(tid, "done", result="결과")

    assert await proto.check_convergence(task_ids) is True


@pytest.mark.asyncio
async def test_converge_agreement(db, send_fn):
    """동일 결과 시 agreement=True."""
    proto = DivergeConvergeProtocol(db, send_fn)
    await db.create_pm_task("T-p5", "부모", None, "pm")

    task_ids = await proto.diverge(
        parent_task_id="T-p5",
        description="비교",
        target_depts=["aiorg_engineering_bot", "aiorg_product_bot"],
        created_by="pm",
        chat_id=123,
    )
    send_fn.reset_mock()

    for tid in task_ids:
        await db.update_pm_task_status(tid, "done", result="REST API 사용")

    result = await proto.converge("T-p5", task_ids, chat_id=123)
    assert result["agreement"] is True
    assert "REST API 사용" in result["merged_result"]


@pytest.mark.asyncio
async def test_converge_disagreement(db, send_fn):
    """다른 결과 시 agreement=False + 병합."""
    proto = DivergeConvergeProtocol(db, send_fn)
    await db.create_pm_task("T-p6", "부모", None, "pm")

    task_ids = await proto.diverge(
        parent_task_id="T-p6",
        description="비교",
        target_depts=["aiorg_engineering_bot", "aiorg_product_bot"],
        created_by="pm",
        chat_id=123,
    )
    send_fn.reset_mock()

    await db.update_pm_task_status(task_ids[0], "done", result="REST API")
    await db.update_pm_task_status(task_ids[1], "done", result="GraphQL")

    result = await proto.converge("T-p6", task_ids, chat_id=123)
    assert result["agreement"] is False
    assert len(result["results"]) == 2
    # 병합 결과에 두 부서 결과 모두 포함
    assert "REST API" in result["merged_result"]
    assert "GraphQL" in result["merged_result"]


@pytest.mark.asyncio
async def test_converge_updates_parent(db, send_fn):
    """converge가 부모 태스크 상태를 done으로 업데이트."""
    proto = DivergeConvergeProtocol(db, send_fn)
    await db.create_pm_task("T-p7", "부모", None, "pm")

    task_ids = await proto.diverge(
        parent_task_id="T-p7",
        description="비교",
        target_depts=["aiorg_engineering_bot", "aiorg_product_bot"],
        created_by="pm",
        chat_id=123,
    )

    for tid in task_ids:
        await db.update_pm_task_status(tid, "done", result="결과")

    await proto.converge("T-p7", task_ids, chat_id=123)

    parent = await db.get_pm_task("T-p7")
    assert parent["status"] == "done"
    assert parent["result"] is not None
