"""core.api.routes.dashboard — 대시보드 데이터 REST API (Phase 2-B).

엔드포인트:
    GET /api/v1/dashboard/summary  — 전체 요약 (인증 불필요)
    GET /api/v1/dashboard/goals    — 목표 목록 (인증 불필요)
    GET /api/v1/dashboard/tasks    — 최근 태스크 목록 (인증 불필요)
"""
from __future__ import annotations

import os
from typing import Any

import aiosqlite
from fastapi import APIRouter, Query

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])

_DB_PATH = os.path.expanduser("~/.ai-org/context.db")


async def _query(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    """aiosqlite로 쿼리를 실행하고 dict 목록을 반환합니다."""
    if not os.path.exists(_DB_PATH):
        return []
    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(sql, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]


@router.get("/summary")
async def get_summary() -> dict[str, Any]:
    """전체 목표·태스크 현황 요약을 반환합니다.

    Returns:
        goals: status별 목표 카운트, tasks: status별 태스크 카운트.
    """
    goal_rows = await _query(
        "SELECT status, COUNT(*) as cnt FROM pm_goals GROUP BY status"
    )
    task_rows = await _query(
        "SELECT status, COUNT(*) as cnt FROM pm_tasks GROUP BY status"
    )
    goals: dict[str, int] = {r["status"]: r["cnt"] for r in goal_rows}
    tasks: dict[str, int] = {r["status"]: r["cnt"] for r in task_rows}
    return {"goals": goals, "tasks": tasks}


@router.get("/goals")
async def get_goals(limit: int = Query(default=20, ge=1, le=200)) -> list[dict[str, Any]]:
    """pm_goals 목록을 updated_at DESC 순으로 반환합니다.

    Args:
        limit: 최대 반환 개수 (기본 20, 최대 200).

    Returns:
        id, title, status, iteration, max_iterations, last_progress, updated_at 포함 목록.
    """
    return await _query(
        """
        SELECT id, title, status, iteration, max_iterations, last_progress, updated_at
        FROM pm_goals
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (limit,),
    )


@router.get("/tasks")
async def get_tasks(
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict[str, Any]]:
    """pm_tasks 목록을 updated_at DESC 순으로 반환합니다.

    Args:
        status: 필터할 status 값 (None이면 전체).
        limit: 최대 반환 개수 (기본 50, 최대 500).

    Returns:
        id, description, assigned_dept, status, result, updated_at 포함 목록.
    """
    if status:
        return await _query(
            """
            SELECT id, description, assigned_dept, status, result, updated_at
            FROM pm_tasks
            WHERE status = ?
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (status, limit),
        )
    return await _query(
        """
        SELECT id, description, assigned_dept, status, result, updated_at
        FROM pm_tasks
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (limit,),
    )
