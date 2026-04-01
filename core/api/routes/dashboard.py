"""core.api.routes.dashboard — 대시보드 데이터 REST API (Phase 2-B).

엔드포인트:
    GET /api/v1/dashboard/summary    — 전체 요약 (인증 불필요)
    GET /api/v1/dashboard/goals      — 목표 목록 (인증 불필요)
    GET /api/v1/dashboard/tasks      — 최근 태스크 목록 (인증 불필요)
    GET /api/v1/dashboard/task-graph — 태스크 계층 그래프 nodes+edges (인증 불필요)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
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


@router.get("/goals-hierarchy")
async def get_goals_hierarchy(limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
    """목표를 장기목표 / 수명업무(회고·주간회의·감사)로 분류해 반환합니다.

    Returns:
        long_term: 장기 프로젝트 목표 목록
        recurring: {retro, weekly, audit, other} 수명업무 분류
    """
    rows = await _query(
        """
        SELECT id, title, status, iteration, max_iterations, last_progress, updated_at, meta_json
        FROM pm_goals
        ORDER BY
            CASE WHEN status IN ('active','in_progress') THEN 0 ELSE 1 END,
            updated_at DESC
        LIMIT ?
        """,
        (limit,),
    )

    long_term: list[dict[str, Any]] = []
    retro:     list[dict[str, Any]] = []
    weekly:    list[dict[str, Any]] = []
    audit:     list[dict[str, Any]] = []
    other_rec: list[dict[str, Any]] = []

    for row in rows:
        title = (row.get("title") or row.get("description") or "").strip()
        tl = title.lower()
        if (
            tl.startswith("[daily_retro")
            or tl.startswith("[일일회고")
            or "daily_retro" in tl
        ):
            retro.append(row)
        elif tl.startswith("[주간회의") or "주간회의" in tl:
            weekly.append(row)
        elif "harness-audit" in tl or "harness audit" in tl:
            audit.append(row)
        elif title.startswith("["):
            other_rec.append(row)
        else:
            long_term.append(row)

    return {
        "long_term": long_term,
        "recurring": {
            "retro":  retro,
            "weekly": weekly,
            "audit":  audit,
            "other":  other_rec,
        },
    }


@router.get("/task-graph")
async def get_task_graph(
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=80, ge=1, le=300),
) -> dict[str, Any]:
    """태스크 계층 그래프 데이터(nodes + edges)를 반환합니다.

    D3.js force-directed 그래프용.
    root 태스크(parent_id IS NULL)와 그 자식 태스크를 함께 반환.

    Args:
        days: 최근 N일 이내 root 태스크만 포함 (기본 7일).
        limit: root 태스크 최대 개수 (기본 80).

    Returns:
        nodes: [{id, label, dept, status, depth}]
        edges: [{source, target}]
        stats: status별 노드 카운트
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    root_tasks = await _query(
        """
        SELECT id, description, assigned_dept, status, updated_at
        FROM pm_tasks
        WHERE parent_id IS NULL AND updated_at >= ?
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (cutoff, limit),
    )

    if not root_tasks:
        return {"nodes": [], "edges": [], "stats": {}}

    root_ids = [r["id"] for r in root_tasks]
    placeholders = ",".join("?" * len(root_ids))

    child_tasks = await _query(
        f"""
        SELECT id, description, assigned_dept, status, parent_id, updated_at
        FROM pm_tasks
        WHERE parent_id IN ({placeholders})
        ORDER BY updated_at DESC
        """,
        tuple(root_ids),
    )

    def _label(text: str, max_len: int = 35) -> str:
        return text[:max_len] + "…" if len(text) > max_len else text

    def _task_type(task_id: str, description: str) -> str:
        tid = (task_id or "").lower()
        desc = (description or "").lower()
        if "retro" in tid or "daily_retro" in desc or "[daily_retro" in desc:
            return "retro"
        if "주간회의" in desc or "weekly" in tid:
            return "weekly"
        if "harness" in tid or "harness" in desc:
            return "audit"
        return "project"

    nodes: list[dict[str, Any]] = []
    stats: dict[str, int] = {}
    edges: list[dict[str, Any]] = []

    # Virtual group nodes for RETRO tasks (group by date in ID, fallback to "misc")
    retro_groups: dict[str, dict[str, Any]] = {}
    for t in root_tasks:
        ttype = _task_type(t["id"], t["description"])
        if ttype == "retro":
            # Extract date from ID like RETRO-daily_retro-20260331-xxx
            parts = t["id"].split("-")
            date_key = next((p for p in parts if p.isdigit() and len(p) == 8), None)
            group_key = date_key if date_key else "misc"
            if group_key not in retro_groups:
                vnode_id = f"RETRO-GROUP-{group_key}"
                if date_key:
                    fmt_date = f"{date_key[:4]}-{date_key[4:6]}-{date_key[6:]}"
                    label = f"일일회고 {fmt_date}"
                else:
                    label = "수명업무 태스크"
                retro_groups[group_key] = {
                    "id": vnode_id,
                    "label": label,
                    "dept": "pm",
                    "status": "done",
                    "depth": 0,
                    "task_type": "retro",
                    "virtual": True,
                }

    # Add virtual retro group nodes
    for vnode in retro_groups.values():
        nodes.append(vnode)
        stats[vnode["status"]] = stats.get(vnode["status"], 0) + 1

    # Add real root tasks
    for t in root_tasks:
        ttype = _task_type(t["id"], t["description"])
        nodes.append({
            "id": t["id"],
            "label": _label(t["description"]),
            "dept": t["assigned_dept"] or "pm",
            "status": t["status"],
            "depth": 0 if ttype not in ("retro",) else 1,
            "task_type": ttype,
        })
        stats[t["status"]] = stats.get(t["status"], 0) + 1

        # Wire retro tasks to their virtual group parent
        if ttype == "retro":
            parts = t["id"].split("-")
            date_key = next((p for p in parts if p.isdigit() and len(p) == 8), None)
            group_key = date_key if date_key else "misc"
            if group_key in retro_groups:
                edges.append({
                    "source": retro_groups[group_key]["id"],
                    "target": t["id"],
                })

    for t in child_tasks:
        ttype = _task_type(t["id"], t["description"])
        nodes.append({
            "id": t["id"],
            "label": _label(t["description"]),
            "dept": t["assigned_dept"] or "pm",
            "status": t["status"],
            "depth": 2 if ttype == "retro" else 1,
            "task_type": ttype,
        })
        stats[t["status"]] = stats.get(t["status"], 0) + 1
        edges.append({"source": t["parent_id"], "target": t["id"]})

    return {"nodes": nodes, "edges": edges, "stats": stats}


# dept → orgId mapping
_DEPT_TO_ORG = {
    "engineering": "aiorg_engineering_bot",
    "design":      "aiorg_design_bot",
    "ops":         "aiorg_ops_bot",
    "product":     "aiorg_product_bot",
    "growth":      "aiorg_growth_bot",
    "research":    "aiorg_research_bot",
    "pm":          "aiorg_pm_bot",
}

_ORG_META = {
    "aiorg_engineering_bot": {"name": "개발실",  "emoji": "🦾", "color": "#0057FF"},
    "aiorg_design_bot":      {"name": "디자인실", "emoji": "🎨", "color": "#9B00FF"},
    "aiorg_ops_bot":         {"name": "운영실",  "emoji": "⚙️", "color": "#00C851"},
    "aiorg_product_bot":     {"name": "기획실",  "emoji": "📋", "color": "#FF6B00"},
    "aiorg_growth_bot":      {"name": "성장실",  "emoji": "📈", "color": "#FF3B3F"},
    "aiorg_research_bot":    {"name": "리서치실", "emoji": "🔬", "color": "#00B8D4"},
    "aiorg_pm_bot":          {"name": "PM",      "emoji": "🎯", "color": "#FFD600"},
}


async def _compute_throughput(hours: float) -> dict[str, Any]:
    """주어진 시간(hours) 내 완료된 태스크 수와 처리량을 계산합니다."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = await _query(
        "SELECT COUNT(*) as cnt FROM pm_tasks WHERE status='done' AND updated_at >= ?",
        (cutoff,),
    )
    completed = rows[0]["cnt"] if rows else 0
    return {
        "completed": completed,
        "throughput": round(completed / hours, 3),
        "period_hours": hours,
    }


@router.get("/snapshot")
async def get_snapshot() -> dict[str, Any]:
    """봇별 활성 태스크 기반 캐릭터 상태 + 전체 카운트 스냅샷."""
    # pusher 미초기화 시에도 DB에서 직접 읽어 응답 (pusher는 SSE 전용)

    # 최근 2시간 태스크 가져오기
    rows = await _query(
        """
        SELECT assigned_dept, status, description
        FROM pm_tasks
        WHERE updated_at >= datetime('now', '-2 hours')
        ORDER BY updated_at DESC
        """
    )

    # dept별로 그룹핑
    dept_tasks: dict[str, list[dict]] = {}
    for row in rows:
        dept = (row.get("assigned_dept") or "pm").strip()
        dept_tasks.setdefault(dept, []).append(row)

    # 각 봇 캐릭터 상태 계산
    characters = []
    for dept, org_id in _DEPT_TO_ORG.items():
        tasks = dept_tasks.get(dept, [])
        active  = [t for t in tasks if t["status"] == "in_progress"]
        blocked = [t for t in tasks if t["status"] == "blocked"]

        if blocked:
            severity, emotion, hp = "critical", "alert", 25
        elif len(active) > 5:
            severity, emotion, hp = "critical", "alert", 30
        elif len(active) > 2:
            severity, emotion, hp = "warning", "alert", 55
        elif active:
            severity, emotion, hp = "info", "working", 80
        else:
            severity, emotion, hp = "info", "idle", 85

        current_task: str | None = None
        if active:
            desc = active[0]["description"] or ""
            current_task = desc[:60] + ("…" if len(desc) > 60 else "")

        meta = _ORG_META.get(org_id, {})
        characters.append({
            "orgId":         org_id,
            "name":          meta.get("name", org_id),
            "emoji":         meta.get("emoji", "🤖"),
            "color":         meta.get("color", "#888"),
            "severity":      severity,
            "emotion":       emotion,
            "hp":            hp,
            "level":         1,
            "active_count":  len(active),
            "blocked_count": len(blocked),
            "current_task":  current_task,
            "animationTrigger": "none",
            "lastUpdated":   datetime.now(timezone.utc).isoformat(),
        })

    # 전체 카운트 (pending/in_progress/done/blocked 기본값 포함)
    count_rows = await _query(
        "SELECT status, COUNT(*) as cnt FROM pm_tasks GROUP BY status"
    )
    counts: dict[str, int] = {"pending": 0, "in_progress": 0, "done": 0, "blocked": 0}
    for r in count_rows:
        status = r["status"]
        counts[status] = r["cnt"]

    # 시간대별 처리량 집계
    aggregations = {
        "1h":  await _compute_throughput(1.0),
        "6h":  await _compute_throughput(6.0),
        "24h": await _compute_throughput(24.0),
    }

    return {
        "characters":   characters,
        "counts":       counts,
        "aggregations": aggregations,
        "thresholds":   {},
        "ts":           datetime.now(timezone.utc).isoformat(),
    }


@router.get("/characters")
async def get_characters() -> dict[str, Any]:
    """봇별 캐릭터 상태를 반환합니다.

    Returns:
        dict: orgId → {emoji, name, color, severity, hp, emotion, active_count, blocked_count}
    """
    # 최근 2시간 태스크 가져오기
    rows = await _query(
        """
        SELECT assigned_dept, status, description
        FROM pm_tasks
        WHERE updated_at >= datetime('now', '-2 hours')
        ORDER BY updated_at DESC
        """
    )

    # dept별로 그룹핑
    dept_tasks: dict[str, list[dict]] = {}
    for row in rows:
        dept = (row.get("assigned_dept") or "pm").strip()
        dept_tasks.setdefault(dept, []).append(row)

    result: dict[str, Any] = {}
    for dept, org_id in _DEPT_TO_ORG.items():
        tasks = dept_tasks.get(dept, [])
        active  = [t for t in tasks if t["status"] == "in_progress"]
        blocked = [t for t in tasks if t["status"] == "blocked"]

        if blocked:
            severity, emotion, hp = "critical", "alert", 25
        elif len(active) > 5:
            severity, emotion, hp = "critical", "alert", 30
        elif len(active) > 2:
            severity, emotion, hp = "warning", "alert", 55
        elif active:
            severity, emotion, hp = "info", "working", 80
        else:
            severity, emotion, hp = "info", "idle", 85

        meta = _ORG_META.get(org_id, {})
        result[org_id] = {
            "emoji":         meta.get("emoji", "🤖"),
            "name":          meta.get("name", org_id),
            "color":         meta.get("color", "#888"),
            "severity":      severity,
            "hp":            hp,
            "emotion":       emotion,
            "active_count":  len(active),
            "blocked_count": len(blocked),
        }

    return result
