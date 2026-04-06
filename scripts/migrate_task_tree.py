#!/usr/bin/env python3
"""pm_tasks.parent_id가 pm_goals ID(G-로 시작)인 고아 태스크를 수정.

coordinator 태스크를 생성하고 고아 태스크의 parent_id를 coordinator ID로 교체한다.

사용법:
    python scripts/migrate_task_tree.py --dry-run   # 변경 없이 미리보기
    python scripts/migrate_task_tree.py             # 실제 마이그레이션
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import time
from pathlib import Path

DB_PATH = os.environ.get("AIMESH_DB_PATH", str(Path.home() / ".ai-org" / "context.db"))


def _next_id(conn: sqlite3.Connection, org_id: str = "aiorg_pm_bot") -> str:
    cursor = conn.execute(
        "SELECT COUNT(*) FROM pm_tasks WHERE id LIKE ?",
        (f"T-{org_id}-%",),
    )
    count = cursor.fetchone()[0]
    return f"T-{org_id}-coord-{count + 1:03d}"


def migrate(dry_run: bool = True) -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 1. G-로 시작하는 parent_id를 가진 태스크 수집 (그룹별)
    cursor = conn.execute(
        "SELECT DISTINCT parent_id FROM pm_tasks WHERE parent_id LIKE 'G-%'"
    )
    goal_ids = [row[0] for row in cursor.fetchall()]

    if not goal_ids:
        print("✅ 마이그레이션 불필요: G-% parent_id 없음")
        conn.close()
        return

    print(f"{'[DRY-RUN] ' if dry_run else ''}발견된 goal parent 그룹: {len(goal_ids)}개")

    for goal_id in goal_ids:
        # 해당 goal의 subtask 목록
        cursor = conn.execute(
            "SELECT id, status, description FROM pm_tasks WHERE parent_id = ?",
            (goal_id,),
        )
        subtasks = list(cursor.fetchall())
        print(f"\n  Goal {goal_id}: {len(subtasks)}개 subtask")
        for st in subtasks:
            print(f"    [{st['status']}] {st['id']}: {st['description'][:50]}")

        if dry_run:
            print("  → [DRY-RUN] coordinator 태스크 생성 후 parent_id 교체 예정")
            continue

        # goal 정보 조회
        cursor = conn.execute(
            "SELECT title, description FROM pm_goals WHERE id = ?", (goal_id,)
        )
        goal_row = cursor.fetchone()
        goal_title = goal_row["title"] if goal_row else goal_id

        # coordinator ID 생성
        coord_id = _next_id(conn)
        now = time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())

        # coordinator 태스크 INSERT
        conn.execute(
            """INSERT INTO pm_tasks
               (id, parent_id, description, assigned_dept, status, created_by, created_at, updated_at, metadata)
               VALUES (?, ?, ?, NULL, 'pending', 'pm', ?, ?, '{"coordinator":true}')""",
            (coord_id, goal_id, f"[Coordinator] {goal_title}", now, now),
        )
        print(f"  ✅ coordinator {coord_id} 생성")

        # subtask의 parent_id를 coordinator로 교체
        conn.execute(
            "UPDATE pm_tasks SET parent_id = ? WHERE parent_id = ?",
            (coord_id, goal_id),
        )
        print(f"  ✅ {len(subtasks)}개 subtask parent_id → {coord_id}")

    if not dry_run:
        conn.commit()
        print("\n✅ 마이그레이션 완료")
    else:
        print("\n[DRY-RUN] 실제 변경 없음. --dry-run 제거 후 재실행하면 적용됩니다.")

    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Task tree migration: G-% parent_id 수정")
    parser.add_argument("--dry-run", action="store_true", default=False)
    args = parser.parse_args()
    migrate(dry_run=args.dry_run)
