"""Orphan Guard 버그 수정 검증 테스트.

수정 위치: core/context_db.py (메인 브랜치 + worktree 공통 적용)
수정 내용:
  - Bug 1: get_tasks_for_dept — 부모 'cancelled' → 자식 픽업 허용 (failed만 스킵)
  - Bug 2: recover_stale_dept_tasks — 부모 'cancelled' → 복구 허용 (failed만 스킵)
  - 안전장치: recover_stale_dept_tasks 24시간 초과 태스크 복구 방지 (좀비 방지)

검증 시나리오:
  ① 부모 cancelled → 자식 픽업 가능 (Orphan Guard 수정 핵심)
  ② 부모 failed → 자식 스킵 (기존 안전 동작 보존)
  ③ 부모 없는 태스크 → 정상 픽업
  ④ 여러 자식 태스크 → 모두 픽업
  ⑤ stale 태스크 + 부모 cancelled → 복구 허용
  ⑥ stale 태스크 + 부모 없음 → 정상 복구
  ⑦ 회귀 방지: 부모 cancelled 시 자식 태스크 DB 상태가 변경되지 않아야 함
     (f9caca3 회귀: auto-cancel 로직이 재도입되는 것을 방지)
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context_db import ContextDB


@pytest.fixture
async def db():
    with tempfile.TemporaryDirectory() as tmp:
        cdb = ContextDB(Path(tmp) / "test.db")
        await cdb.initialize()
        yield cdb


# ──────────────────────────────────────────────
# 의도된 동작: 부모 cancelled여도 자식 픽업 가능
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_child_task_runs_when_parent_cancelled(db):
    """부모 태스크가 cancelled여도 자식 태스크는 픽업되어야 한다 (핵심 수정 검증)."""
    await db.create_pm_task("T-parent-001", "parent task", None, "pm")
    await db.update_pm_task_status("T-parent-001", "cancelled")

    await db.create_pm_task("T-child-001", "child task", "engineering", "pm", parent_id="T-parent-001")
    await db.update_pm_task_status("T-child-001", "assigned")

    tasks = await db.get_tasks_for_dept("engineering")
    task_ids = [t["id"] for t in tasks]

    assert "T-child-001" in task_ids, (
        "부모가 cancelled여도 자식 태스크는 픽업 가능해야 합니다 (Orphan Guard Bug 1 수정)"
    )


@pytest.mark.asyncio
async def test_child_task_runs_without_parent(db):
    """부모 없는 태스크는 정상 픽업되어야 한다."""
    await db.create_pm_task("T-solo-001", "solo task", "engineering", "pm")
    await db.update_pm_task_status("T-solo-001", "assigned")

    tasks = await db.get_tasks_for_dept("engineering")
    task_ids = [t["id"] for t in tasks]

    assert "T-solo-001" in task_ids, "부모 없는 태스크는 정상 픽업되어야 합니다"


@pytest.mark.asyncio
async def test_child_task_pending_runs_when_parent_cancelled(db):
    """부모가 cancelled여도 pending 자식 태스크(의존성 없음)도 픽업되어야 한다."""
    await db.create_pm_task("T-parent-003", "parent task", None, "pm")
    await db.update_pm_task_status("T-parent-003", "cancelled")

    # 자식 태스크 — pending 상태 (의존성 없음)
    await db.create_pm_task(
        "T-child-003", "child pending task", "engineering", "pm", parent_id="T-parent-003"
    )

    tasks = await db.get_tasks_for_dept("engineering")
    task_ids = [t["id"] for t in tasks]

    assert "T-child-003" in task_ids, (
        "부모가 cancelled여도 pending 자식 태스크(deps 없음)는 픽업 가능해야 합니다"
    )


@pytest.mark.asyncio
async def test_multiple_children_with_cancelled_parent_all_run(db):
    """부모 cancelled일 때 여러 자식 태스크 모두 픽업 가능해야 한다."""
    await db.create_pm_task("T-parent-010", "parent task", None, "pm")
    await db.update_pm_task_status("T-parent-010", "cancelled")

    for i in range(3):
        await db.create_pm_task(
            f"T-child-01{i}", f"child task {i}", "engineering", "pm", parent_id="T-parent-010"
        )
        await db.update_pm_task_status(f"T-child-01{i}", "assigned")

    tasks = await db.get_tasks_for_dept("engineering")
    task_ids = [t["id"] for t in tasks]

    for i in range(3):
        assert f"T-child-01{i}" in task_ids, (
            f"T-child-01{i}: 부모가 cancelled여도 자식 태스크 모두 픽업 가능해야 합니다"
        )


# ──────────────────────────────────────────────
# recover_stale_dept_tasks: 부모 cancelled → 복구 허용
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stale_task_recovered_when_parent_cancelled(db):
    """부모가 cancelled여도 stale running 태스크는 복구되어야 한다 (Bug 2 수정 검증)."""
    import json
    import aiosqlite
    from datetime import UTC, datetime, timedelta

    await db.create_pm_task("T-parent-004", "parent task", None, "pm")
    await db.update_pm_task_status("T-parent-004", "cancelled")

    await db.create_pm_task(
        "T-stale-001", "stale task", "engineering", "pm", parent_id="T-parent-004"
    )
    await db.update_pm_task_status("T-stale-001", "running")

    # 타임스탬프를 과거로 조작하여 stale 조건 충족
    old_time = (datetime.now(UTC) - timedelta(seconds=500)).isoformat()
    expired_lease = (datetime.now(UTC) - timedelta(seconds=400)).isoformat()
    meta = json.dumps({"lease_expires_at": expired_lease})
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "UPDATE pm_tasks SET updated_at=?, metadata=? WHERE id=?",
            (old_time, meta, "T-stale-001"),
        )
        await conn.commit()

    recovered = await db.recover_stale_dept_tasks("engineering", stale_seconds=300)

    assert recovered >= 1, (
        "부모가 cancelled여도 stale 태스크는 복구되어야 합니다 (Bug 2 수정 검증)"
    )


@pytest.mark.asyncio
async def test_stale_task_recovered_without_parent(db):
    """부모 없는 stale 태스크는 정상적으로 복구되어야 한다."""
    import json
    import aiosqlite
    from datetime import UTC, datetime, timedelta

    await db.create_pm_task("T-stale-solo", "solo stale task", "engineering", "pm")
    await db.update_pm_task_status("T-stale-solo", "running")

    old_time = (datetime.now(UTC) - timedelta(seconds=500)).isoformat()
    expired_lease = (datetime.now(UTC) - timedelta(seconds=400)).isoformat()
    meta = json.dumps({"lease_expires_at": expired_lease})
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "UPDATE pm_tasks SET updated_at=?, metadata=? WHERE id=?",
            (old_time, meta, "T-stale-solo"),
        )
        await conn.commit()

    recovered = await db.recover_stale_dept_tasks("engineering", stale_seconds=300)
    assert recovered >= 1, "부모 없는 stale 태스크는 정상 복구되어야 합니다"


# ──────────────────────────────────────────────
# 기존 동작 보존: 부모 failed → 자식 스킵
# ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_child_task_skipped_when_parent_failed(db):
    """부모 태스크가 failed이면 자식 태스크는 픽업되면 안 된다 (안전 동작 보존)."""
    await db.create_pm_task("T-parent-fail-001", "parent task", None, "pm")
    await db.update_pm_task_status("T-parent-fail-001", "failed")

    await db.create_pm_task(
        "T-child-fail-001", "child task", "engineering", "pm",
        parent_id="T-parent-fail-001"
    )
    await db.update_pm_task_status("T-child-fail-001", "assigned")

    tasks = await db.get_tasks_for_dept("engineering")
    task_ids = [t["id"] for t in tasks]

    assert "T-child-fail-001" not in task_ids, (
        "부모가 failed이면 자식 태스크는 픽업되면 안 됩니다 (Orphan Guard 안전 동작)"
    )


@pytest.mark.asyncio
async def test_child_task_status_not_modified_when_parent_cancelled(db):
    """[회귀 방지] 부모 cancelled 시 자식 태스크 DB 상태가 'assigned'로 유지되어야 한다.

    f9caca3 회귀 재발 방지:
    get_tasks_for_dept() 호출 후 자식 태스크가 auto-cancel로
    DB에서 'cancelled'로 변경되어서는 안 된다.
    """
    await db.create_pm_task("T-parent-reg-001", "parent task", None, "pm")
    await db.update_pm_task_status("T-parent-reg-001", "cancelled")

    await db.create_pm_task(
        "T-child-reg-001", "child task", "engineering", "pm",
        parent_id="T-parent-reg-001"
    )
    await db.update_pm_task_status("T-child-reg-001", "assigned")

    # 폴러 호출 시뮬레이션
    await db.get_tasks_for_dept("engineering")

    # DB 상태가 변경되지 않았는지 확인 (auto-cancel 회귀 방지)
    task = await db.get_pm_task("T-child-reg-001")
    assert task is not None
    assert task["status"] == "assigned", (
        f"f9caca3 회귀 감지: 자식 태스크 상태가 '{task['status']}'로 변경됨. "
        "'assigned'를 유지해야 합니다. "
        "Orphan Guard가 DB를 직접 수정해서는 안 됩니다."
    )


@pytest.mark.asyncio
async def test_stale_task_not_recovered_when_parent_failed(db):
    """부모가 failed이면 stale 태스크는 복구되면 안 된다 (안전 동작 보존)."""
    import json
    import aiosqlite
    from datetime import UTC, datetime, timedelta

    await db.create_pm_task("T-parent-fail-002", "parent task", None, "pm")
    await db.update_pm_task_status("T-parent-fail-002", "failed")

    await db.create_pm_task(
        "T-stale-fail-001", "stale task", "engineering", "pm",
        parent_id="T-parent-fail-002"
    )
    await db.update_pm_task_status("T-stale-fail-001", "running")

    old_time = (datetime.now(UTC) - timedelta(seconds=500)).isoformat()
    expired_lease = (datetime.now(UTC) - timedelta(seconds=400)).isoformat()
    meta = json.dumps({"lease_expires_at": expired_lease})
    async with aiosqlite.connect(db.db_path) as conn:
        await conn.execute(
            "UPDATE pm_tasks SET updated_at=?, metadata=? WHERE id=?",
            (old_time, meta, "T-stale-fail-001"),
        )
        await conn.commit()

    recovered = await db.recover_stale_dept_tasks("engineering", stale_seconds=300)

    assert recovered == 0, (
        "부모가 failed이면 stale 태스크는 복구되면 안 됩니다 (Orphan Guard 안전 동작)"
    )
