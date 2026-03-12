"""PMOrchestrator Discussion Integration 테스트 — Task 2.5."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context_db import ContextDB
from core.task_graph import TaskGraph
from core.claim_manager import ClaimManager
from core.memory_manager import MemoryManager
from core.pm_orchestrator import PMOrchestrator, SubTask, DiscussionNeeded
from core.discussion import DiscussionManager


@pytest.fixture
async def db():
    with tempfile.TemporaryDirectory() as tmp:
        cdb = ContextDB(Path(tmp) / "test.db")
        await cdb.initialize()
        yield cdb


@pytest.fixture
def send_fn():
    return AsyncMock()


class TestDetectDiscussionNeeds:

    def test_no_discussion_single_dept(self, send_fn):
        orch = PMOrchestrator(
            context_db=AsyncMock(), task_graph=AsyncMock(),
            claim_manager=ClaimManager(), memory=MemoryManager("pm"),
            org_id="pm", telegram_send_func=send_fn,
        )
        subtasks = [SubTask("개발", "aiorg_engineering_bot")]
        result = orch.detect_discussion_needs("API 개발", subtasks)
        assert result == []

    def test_no_discussion_without_keywords(self, send_fn):
        orch = PMOrchestrator(
            context_db=AsyncMock(), task_graph=AsyncMock(),
            claim_manager=ClaimManager(), memory=MemoryManager("pm"),
            org_id="pm", telegram_send_func=send_fn,
        )
        subtasks = [
            SubTask("기획", "aiorg_product_bot"),
            SubTask("개발", "aiorg_engineering_bot"),
        ]
        result = orch.detect_discussion_needs("기획하고 개발하자", subtasks)
        assert result == []

    def test_discussion_detected_with_keywords(self, send_fn):
        orch = PMOrchestrator(
            context_db=AsyncMock(), task_graph=AsyncMock(),
            claim_manager=ClaimManager(), memory=MemoryManager("pm"),
            org_id="pm", telegram_send_func=send_fn,
        )
        subtasks = [
            SubTask("기획", "aiorg_product_bot"),
            SubTask("개발", "aiorg_engineering_bot"),
        ]
        result = orch.detect_discussion_needs("어떤 방식으로 기획하고 개발할까 논의", subtasks)
        assert len(result) == 1
        assert isinstance(result[0], DiscussionNeeded)
        assert len(result[0].participants) == 2

    def test_discussion_vs_keyword(self, send_fn):
        orch = PMOrchestrator(
            context_db=AsyncMock(), task_graph=AsyncMock(),
            claim_manager=ClaimManager(), memory=MemoryManager("pm"),
            org_id="pm", telegram_send_func=send_fn,
        )
        subtasks = [
            SubTask("디자인", "aiorg_design_bot"),
            SubTask("개발", "aiorg_engineering_bot"),
        ]
        result = orch.detect_discussion_needs("React vs Vue 비교해서 결정", subtasks)
        assert len(result) == 1


class TestStartDiscussions:

    @pytest.mark.asyncio
    async def test_start_discussions(self, db, send_fn):
        disc_mgr = DiscussionManager(db, send_fn, org_id="pm")
        orch = PMOrchestrator(
            context_db=db, task_graph=TaskGraph(db),
            claim_manager=ClaimManager(), memory=MemoryManager("pm"),
            org_id="pm", telegram_send_func=send_fn,
            discussion_manager=disc_mgr,
        )
        discussions = [DiscussionNeeded(
            topic="아키텍처 선택",
            proposal="마이크로서비스 vs 모놀리스",
            participants=["aiorg_engineering_bot", "aiorg_design_bot"],
        )]
        disc_ids = await orch.start_discussions(discussions, "T-pm-001", chat_id=123)
        assert len(disc_ids) == 1
        assert disc_ids[0].startswith("D-pm-")

        # ContextDB에 토론 생성 확인
        disc = await db.get_discussion(disc_ids[0])
        assert disc is not None
        assert disc["status"] == "open"
        assert disc["parent_task_id"] == "T-pm-001"

    @pytest.mark.asyncio
    async def test_start_discussions_no_manager(self, db, send_fn):
        """discussion_manager 없으면 빈 리스트 반환."""
        orch = PMOrchestrator(
            context_db=db, task_graph=TaskGraph(db),
            claim_manager=ClaimManager(), memory=MemoryManager("pm"),
            org_id="pm", telegram_send_func=send_fn,
        )
        discussions = [DiscussionNeeded("t", "p", ["eng"])]
        disc_ids = await orch.start_discussions(discussions, "T-pm-001", chat_id=123)
        assert disc_ids == []

    @pytest.mark.asyncio
    async def test_start_multiple_discussions(self, db, send_fn):
        disc_mgr = DiscussionManager(db, send_fn, org_id="pm")
        orch = PMOrchestrator(
            context_db=db, task_graph=TaskGraph(db),
            claim_manager=ClaimManager(), memory=MemoryManager("pm"),
            org_id="pm", telegram_send_func=send_fn,
            discussion_manager=disc_mgr,
        )
        discussions = [
            DiscussionNeeded("UI 프레임워크", "React 제안", ["eng", "design"]),
            DiscussionNeeded("DB 선택", "PostgreSQL 제안", ["eng", "ops"]),
        ]
        disc_ids = await orch.start_discussions(discussions, "T-pm-002", chat_id=123)
        assert len(disc_ids) == 2
        assert disc_ids[0] != disc_ids[1]
