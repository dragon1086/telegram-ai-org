"""TaskPoller 테스트 — 부서봇 ContextDB 폴링."""
from __future__ import annotations

import asyncio
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context_db import ContextDB
from core.task_graph import TaskGraph
from core.task_poller import TaskPoller


@pytest.fixture
async def db():
    with tempfile.TemporaryDirectory() as tmp:
        cdb = ContextDB(Path(tmp) / "test.db")
        await cdb.initialize()
        yield cdb


@pytest.fixture
def on_task():
    return AsyncMock()


class TestTaskPollerBasic:

    @pytest.mark.asyncio
    async def test_start_stop(self, db, on_task):
        poller = TaskPoller(db, "aiorg_engineering_bot", on_task, poll_interval=0.05)
        poller.start()
        assert poller._running is True
        await asyncio.sleep(0.01)
        poller.stop()
        assert poller._running is False

    @pytest.mark.asyncio
    async def test_double_start(self, db, on_task):
        """start() 중복 호출 시 무시."""
        poller = TaskPoller(db, "aiorg_engineering_bot", on_task, poll_interval=0.05)
        poller.start()
        poller.start()  # 두 번째 호출은 무시
        assert poller._running is True
        poller.stop()

    @pytest.mark.asyncio
    async def test_detects_assigned_task(self, db, on_task):
        """assigned 상태 태스크를 감지하고 콜백 실행."""
        dept = "aiorg_engineering_bot"
        await db.create_pm_task("T-1", "코드 구현", dept, "pm")
        await db.update_pm_task_status("T-1", "assigned")

        poller = TaskPoller(db, dept, on_task, poll_interval=0.05)
        poller.start()
        await asyncio.sleep(0.15)  # 폴링 2-3회
        poller.stop()

        on_task.assert_called_once()
        called_task = on_task.call_args[0][0]
        assert called_task["id"] == "T-1"
        assert called_task["description"] == "코드 구현"

    @pytest.mark.asyncio
    async def test_ignores_other_dept_tasks(self, db, on_task):
        """다른 부서에 배정된 태스크는 무시."""
        await db.create_pm_task("T-1", "디자인 작업", "aiorg_design_bot", "pm")
        await db.update_pm_task_status("T-1", "assigned")

        poller = TaskPoller(db, "aiorg_engineering_bot", on_task, poll_interval=0.05)
        poller.start()
        await asyncio.sleep(0.15)
        poller.stop()

        on_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_pending_with_unmet_dependencies(self, db, on_task):
        """의존성이 남은 pending 태스크는 무시."""
        dept = "aiorg_engineering_bot"
        tg = TaskGraph(db)
        await db.create_pm_task("T-0", "선행 태스크", "aiorg_product_bot", "pm")
        await db.create_pm_task("T-1", "태스크", dept, "pm")
        await tg.add_task("T-0")
        await tg.add_task("T-1", depends_on=["T-0"])

        poller = TaskPoller(db, dept, on_task, poll_interval=0.05)
        poller.start()
        await asyncio.sleep(0.15)
        poller.stop()

        on_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_duplicate_execution(self, db, on_task):
        """같은 태스크를 중복 실행하지 않음."""
        dept = "aiorg_engineering_bot"
        await db.create_pm_task("T-1", "중복 테스트", dept, "pm")
        await db.update_pm_task_status("T-1", "assigned")

        # 콜백이 느리게 실행되도록 시뮬레이션
        async def slow_callback(task):
            await asyncio.sleep(0.3)

        on_task.side_effect = slow_callback

        poller = TaskPoller(db, dept, on_task, poll_interval=0.05)
        poller.start()
        await asyncio.sleep(0.25)  # 폴링 여러 번
        poller.stop()

        # 한 번만 호출됨 (processing set에 의해 중복 방지)
        assert on_task.call_count == 1

    @pytest.mark.asyncio
    async def test_processing_cleared_after_completion(self, db, on_task):
        """태스크 실행 완료 후 processing set에서 제거 → 재실행 가능."""
        dept = "aiorg_engineering_bot"
        await db.create_pm_task("T-1", "재실행 테스트", dept, "pm")
        await db.update_pm_task_status("T-1", "assigned")

        poller = TaskPoller(db, dept, on_task, poll_interval=0.05)
        poller.start()
        await asyncio.sleep(0.15)
        poller.stop()

        assert on_task.call_count == 1
        # processing set에서 제거됨
        assert "T-1" not in poller._processing

    @pytest.mark.asyncio
    async def test_callback_error_doesnt_crash_poller(self, db, on_task):
        """콜백 에러가 폴러를 중단시키지 않음."""
        dept = "aiorg_engineering_bot"
        await db.create_pm_task("T-1", "에러 태스크", dept, "pm")
        await db.update_pm_task_status("T-1", "assigned")

        on_task.side_effect = RuntimeError("boom")

        poller = TaskPoller(db, dept, on_task, poll_interval=0.05)
        poller.start()
        await asyncio.sleep(0.15)
        poller.stop()

        # 에러에도 불구하고 폴러 정상 작동, 콜백은 호출됨
        on_task.assert_called_once()
        # processing에서 제거됨 (finally 블록)
        assert "T-1" not in poller._processing

    @pytest.mark.asyncio
    async def test_multiple_tasks(self, db, on_task):
        """여러 태스크를 동시에 감지·실행."""
        dept = "aiorg_engineering_bot"
        for i in range(3):
            await db.create_pm_task(f"T-{i}", f"태스크{i}", dept, "pm")
            await db.update_pm_task_status(f"T-{i}", "assigned")

        poller = TaskPoller(db, dept, on_task, poll_interval=0.05)
        poller.start()
        await asyncio.sleep(0.2)
        poller.stop()

        assert on_task.call_count == 3

    @pytest.mark.asyncio
    async def test_claims_stale_running_task(self, db, on_task):
        dept = "aiorg_engineering_bot"
        await db.create_pm_task(
            "T-stale",
            "stale task",
            dept,
            "pm",
            metadata={
                "lease_owner": "other",
                "lease_expires_at": (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            },
        )
        await db.update_pm_task_status("T-stale", "running")

        poller = TaskPoller(db, dept, on_task, poll_interval=0.05, heartbeat_interval_sec=0.05, lease_ttl_sec=0.2)
        poller.start()
        await asyncio.sleep(0.15)
        poller.stop()

        on_task.assert_called_once()
        task = await db.get_pm_task("T-stale")
        assert task is not None
        assert task["metadata"].get("lease_owner") is None

    @pytest.mark.asyncio
    async def test_heartbeat_keeps_lease_current(self, db, on_task):
        dept = "aiorg_engineering_bot"
        await db.create_pm_task("T-heartbeat", "heartbeat task", dept, "pm")
        await db.update_pm_task_status("T-heartbeat", "assigned")

        async def slow_callback(task):
            await asyncio.sleep(0.22)

        on_task.side_effect = slow_callback

        poller = TaskPoller(db, dept, on_task, poll_interval=0.05, heartbeat_interval_sec=0.05, lease_ttl_sec=0.12)
        poller.start()
        await asyncio.sleep(0.18)
        task = await db.get_pm_task("T-heartbeat")
        poller.stop()

        assert task is not None
        assert task["metadata"].get("lease_owner")
        assert on_task.call_count == 1
