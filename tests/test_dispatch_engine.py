"""DispatchEngine 단위 테스트 — Phase 3 Auto-Dispatch."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context_db import ContextDB
from core.task_graph import TaskGraph
from core.dispatch_engine import DispatchEngine


@pytest.fixture
async def db():
    with tempfile.TemporaryDirectory() as tmp:
        cdb = ContextDB(Path(tmp) / "test.db")
        await cdb.initialize()
        yield cdb


@pytest.fixture
def send_fn():
    return AsyncMock()


async def _setup_linear_chain(db, send_fn):
    """A -> B -> C 선형 체인 설정."""
    tg = TaskGraph(db)
    engine = DispatchEngine(db, tg, send_fn)

    # 부모 태스크
    await db.create_pm_task("T-root", "루트", None, "pm")
    # 서브태스크
    await db.create_pm_task("T-A", "태스크 A", "aiorg_product_bot", "pm", parent_id="T-root")
    await db.create_pm_task("T-B", "태스크 B", "aiorg_engineering_bot", "pm", parent_id="T-root")
    await db.create_pm_task("T-C", "태스크 C", "aiorg_design_bot", "pm", parent_id="T-root")

    # 의존성: A -> B -> C
    await tg.add_task("T-A")
    await tg.add_task("T-B", depends_on=["T-A"])
    await tg.add_task("T-C", depends_on=["T-B"])

    # A를 assigned 상태로
    await db.update_pm_task_status("T-A", "assigned")

    return engine, tg


@pytest.mark.asyncio
async def test_linear_chain_autodispatch(db, send_fn):
    """A 완료 → B 자동 발송."""
    engine, _ = await _setup_linear_chain(db, send_fn)

    dispatched = await engine.on_task_complete("T-A", "A 결과", chat_id=123)
    assert "T-B" in dispatched
    assert "T-C" not in dispatched  # C는 아직 B에 의존

    # B가 assigned로 변경됐는지 확인
    task_b = await db.get_pm_task("T-B")
    assert task_b["status"] == "assigned"


@pytest.mark.asyncio
async def test_linear_chain_full_completion(db, send_fn):
    """A → B → C 전체 체인 자동 완료."""
    engine, _ = await _setup_linear_chain(db, send_fn)

    await engine.on_task_complete("T-A", "A 결과", chat_id=123)
    dispatched_b = await engine.on_task_complete("T-B", "B 결과", chat_id=123)
    assert "T-C" in dispatched_b

    dispatched_c = await engine.on_task_complete("T-C", "C 결과", chat_id=123)
    assert dispatched_c == []  # 더 이상 후속 없음

    # 모두 done
    for tid in ["T-A", "T-B", "T-C"]:
        task = await db.get_pm_task(tid)
        assert task["status"] == "done"


@pytest.mark.asyncio
async def test_parallel_fanout(db, send_fn):
    """A 완료 → B+C 동시 발송 (parallel fan-out)."""
    tg = TaskGraph(db)
    engine = DispatchEngine(db, tg, send_fn)

    await db.create_pm_task("T-root", "루트", None, "pm")
    await db.create_pm_task("T-A", "A", "aiorg_product_bot", "pm", parent_id="T-root")
    await db.create_pm_task("T-B", "B", "aiorg_engineering_bot", "pm", parent_id="T-root")
    await db.create_pm_task("T-C", "C", "aiorg_design_bot", "pm", parent_id="T-root")

    # B,C 모두 A에 의존
    await tg.add_task("T-A")
    await tg.add_task("T-B", depends_on=["T-A"])
    await tg.add_task("T-C", depends_on=["T-A"])
    await db.update_pm_task_status("T-A", "assigned")

    dispatched = await engine.on_task_complete("T-A", "A결과", chat_id=123)
    assert len(dispatched) == 2
    assert set(dispatched) == {"T-B", "T-C"}


@pytest.mark.asyncio
async def test_diamond_dependency(db, send_fn):
    """A → B+C → D 다이아몬드 의존성."""
    tg = TaskGraph(db)
    engine = DispatchEngine(db, tg, send_fn)

    await db.create_pm_task("T-root", "루트", None, "pm")
    await db.create_pm_task("T-A", "A", "aiorg_product_bot", "pm", parent_id="T-root")
    await db.create_pm_task("T-B", "B", "aiorg_engineering_bot", "pm", parent_id="T-root")
    await db.create_pm_task("T-C", "C", "aiorg_design_bot", "pm", parent_id="T-root")
    await db.create_pm_task("T-D", "D", "aiorg_ops_bot", "pm", parent_id="T-root")

    await tg.add_task("T-A")
    await tg.add_task("T-B", depends_on=["T-A"])
    await tg.add_task("T-C", depends_on=["T-A"])
    await tg.add_task("T-D", depends_on=["T-B", "T-C"])
    await db.update_pm_task_status("T-A", "assigned")

    # A 완료 → B+C 발송
    d1 = await engine.on_task_complete("T-A", "A결과", chat_id=123)
    assert set(d1) == {"T-B", "T-C"}

    # B만 완료 → D는 아직 (C 미완료)
    d2 = await engine.on_task_complete("T-B", "B결과", chat_id=123)
    assert "T-D" not in d2

    # C도 완료 → D 발송
    d3 = await engine.on_task_complete("T-C", "C결과", chat_id=123)
    assert "T-D" in d3


@pytest.mark.asyncio
async def test_stalled_tasks_detection(db, send_fn):
    """정체된 태스크 감지."""
    tg = TaskGraph(db)
    engine = DispatchEngine(db, tg, send_fn, stall_minutes=0)  # 즉시 정체 판정

    await db.create_pm_task("T-stall", "정체 태스크", "aiorg_engineering_bot", "pm")
    await db.update_pm_task_status("T-stall", "assigned")

    stalled = await engine.check_stalled_chains()
    assert "T-stall" in stalled


@pytest.mark.asyncio
async def test_no_stall_for_pending(db, send_fn):
    """pending 상태는 정체로 감지하지 않음."""
    tg = TaskGraph(db)
    engine = DispatchEngine(db, tg, send_fn, stall_minutes=0)

    await db.create_pm_task("T-pending", "대기 태스크", "aiorg_engineering_bot", "pm")
    # status=pending (기본값)

    stalled = await engine.check_stalled_chains()
    assert "T-pending" not in stalled


@pytest.mark.asyncio
async def test_status_display(db, send_fn):
    """진행률 표시 생성."""
    tg = TaskGraph(db)
    engine = DispatchEngine(db, tg, send_fn)

    await db.create_pm_task("T-root", "루트", None, "pm")
    await db.create_pm_task("T-1", "태스크 1", "aiorg_product_bot", "pm", parent_id="T-root")
    await db.create_pm_task("T-2", "태스크 2", "aiorg_engineering_bot", "pm", parent_id="T-root")
    await db.update_pm_task_status("T-1", "done", result="완료")

    display = await engine.build_status_display("T-root")
    assert "1/2" in display  # 1개 done / 2개 전체
    assert "✅" in display  # done 아이콘
    assert "⏳" in display  # pending 아이콘


@pytest.mark.asyncio
async def test_telegram_messages_sent(db, send_fn):
    """자동 발송 시 Telegram 메시지가 전송되는지 확인."""
    tg = TaskGraph(db)
    engine = DispatchEngine(db, tg, send_fn)

    await db.create_pm_task("T-root", "루트", None, "pm")
    await db.create_pm_task("T-A", "A", "aiorg_product_bot", "pm", parent_id="T-root")
    await db.create_pm_task("T-B", "B", "aiorg_engineering_bot", "pm", parent_id="T-root")
    await tg.add_task("T-A")
    await tg.add_task("T-B", depends_on=["T-A"])
    await db.update_pm_task_status("T-A", "assigned")

    await engine.on_task_complete("T-A", "A결과", chat_id=123)

    # [PM_TASK:...] 메시지 + 상태 표시 메시지
    assert send_fn.await_count >= 1
    call_args = [str(c) for c in send_fn.call_args_list]
    assert any("PM_TASK:T-B" in a for a in call_args)
