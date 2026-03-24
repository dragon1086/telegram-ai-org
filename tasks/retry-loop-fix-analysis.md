# Infinite Retry Loop Fix — Architectural Analysis

**Date:** 2026-03-23
**Author:** Architect Agent
**Status:** Ready for implementation

---

## Summary

The infinite retry loop is caused by `recover_stale_dept_tasks` unconditionally resetting `attempt_count = 0` on every bot restart, which defeats the `MAX_TASK_ATTEMPTS = 5` safety limit in `claim_pm_task_lease`. A secondary contributor is the raw SQL in `_post_init` which resets status without any attempt_count awareness. The fix introduces a `total_attempt_count` (never reset) alongside the existing `attempt_count` (reset per recovery cycle), and caps the number of recovery cycles.

## Root Cause Analysis

### Confirmed: User's analysis is correct

Three mechanisms interact to create the loop:

| Mechanism | Location | Action | Problem |
|-----------|----------|--------|---------|
| `claim_pm_task_lease` | `context_db.py:654` | `attempt_count + 1`; auto-fail at >5 | Correct safety limit |
| `recover_stale_dept_tasks` | `context_db.py:~790` | `metadata["attempt_count"] = 0` | **Resets the safety limit** |
| `_post_init` | `telegram_relay.py:~3082` | Raw SQL `SET status='assigned'` | Resets status; ignores metadata entirely |

### The ironic comment at `context_db.py:632`:
```python
# attempt_count를 0으로 리셋하므로 무한루프 위험은 없음.
```
This comment claims the reset *prevents* infinite loops. In reality, it *enables* them. The author confused "fresh start" with "safety bypass."

### Why it loops infinitely:

1. Task fails 5 times → `claim_pm_task_lease` correctly auto-fails it
2. Bot crashes (frequent due to Python 3.14 + httpcore incompatibility)
3. On restart, `_post_init` runs first: `running → assigned` (raw SQL, no metadata check)
4. Then `TaskPoller.start()` → `recover_stale_dept_tasks`: resets `attempt_count = 0`
5. Task is now `assigned` with `attempt_count = 0` — indistinguishable from a brand new task
6. Cycle repeats indefinitely

### Double-reset problem:

Both `_post_init` AND `recover_stale_dept_tasks` reset stale tasks, but they use different mechanisms:
- `_post_init`: raw SQL, 30-minute cutoff, no metadata awareness
- `recover_stale_dept_tasks`: Python with metadata manipulation, `lease_ttl + 60s` cutoff, resets attempt_count

This means a task can be reset by `_post_init` (status only) and then *also* by `recover_stale_dept_tasks` (status + attempt_count), or just one of them depending on timing.

---

## Proposed Fix

### Design Principles
1. **Never reset the global attempt counter** — use a separate field for per-cycle tracking
2. **Cap recovery cycles** — a task that keeps failing after recovery should eventually stay failed
3. **Consolidate reset logic** — eliminate the `_post_init` raw SQL duplication
4. **Preserve legitimate recovery** — a task interrupted mid-progress (with heartbeats) deserves another chance

### Change 1: Introduce `total_attempt_count` in metadata (context_db.py)

**In `claim_pm_task_lease` (~line 654):**

```python
# Current:
attempt_count = metadata.get("attempt_count", 0) + 1
if attempt_count > self.MAX_TASK_ATTEMPTS:

# Proposed:
attempt_count = metadata.get("attempt_count", 0) + 1
total_attempt_count = metadata.get("total_attempt_count", 0) + 1

if total_attempt_count > self.MAX_TOTAL_ATTEMPTS:
    # Permanent failure — no recovery will help
    metadata["fail_reason"] = (
        f"총 실행 시도 횟수 초과 ({total_attempt_count}/{self.MAX_TOTAL_ATTEMPTS}회). "
        "복구 포함 전체 한도 초과로 영구 중단."
    )
    metadata["permanent_failure"] = True
    # ... set status='failed', return None

if attempt_count > self.MAX_TASK_ATTEMPTS:
    # Per-cycle failure — recoverable but counted
    metadata["fail_reason"] = (
        f"사이클 내 시도 횟수 초과 ({attempt_count}/{self.MAX_TASK_ATTEMPTS}회)."
    )
    # ... set status='failed', return None

# Update both counters
metadata["attempt_count"] = attempt_count
metadata["total_attempt_count"] = total_attempt_count
```

**New constant:**
```python
MAX_TASK_ATTEMPTS = 5       # Per recovery cycle
MAX_TOTAL_ATTEMPTS = 15     # Absolute lifetime limit (3 recovery cycles × 5 attempts)
MAX_RECOVERY_COUNT = 3      # Max times recover_stale_dept_tasks can reset a task
```

### Change 2: Cap recoveries in `recover_stale_dept_tasks` (context_db.py:~790)

```python
# Current:
metadata["attempt_count"] = 0
metadata["recovered_at"] = now.isoformat()

# Proposed:
recovery_count = metadata.get("recovery_count", 0) + 1
if recovery_count > self.MAX_RECOVERY_COUNT:
    logger.warning(
        f"[RECOVER] 태스크 {task_id} 복구 한도 초과 "
        f"(recovery_count={recovery_count}/{self.MAX_RECOVERY_COUNT}) — 복구 스킵"
    )
    # Auto-fail instead of recovering
    metadata["fail_reason"] = (
        f"최대 복구 횟수 초과 ({self.MAX_RECOVERY_COUNT}회). "
        "반복 실패로 영구 중단."
    )
    metadata["permanent_failure"] = True
    await db.execute(
        "UPDATE pm_tasks SET status='failed', metadata=?, updated_at=? WHERE id=?",
        (json.dumps(metadata, ensure_ascii=False), now_iso, task_id),
    )
    continue

metadata["attempt_count"] = 0  # Reset per-cycle counter (OK — capped by recovery_count)
metadata["recovery_count"] = recovery_count
metadata["total_attempt_count"]  # PRESERVE — never reset
metadata["recovered_at"] = now.isoformat()
```

### Change 3: Eliminate `_post_init` raw SQL duplication (telegram_relay.py:~3082)

```python
# Current (DELETE THIS):
async with _aiosqlite.connect(self.context_db.db_path) as _db:
    result = await _db.execute(
        "UPDATE pm_tasks SET status='assigned' "
        "WHERE status='running' AND assigned_dept=? AND updated_at < ?",
        (self.org_id, cutoff),
    )

# Proposed (REPLACE WITH):
# Let recover_stale_dept_tasks handle everything — it already runs
# at TaskPoller startup (task_poller.py:77). Remove the raw SQL entirely.
# The 30-minute cutoff in _post_init is redundant with the
# lease_ttl + 60s cutoff in recover_stale_dept_tasks.
```

**Why remove it:** The raw SQL bypasses all safety checks (attempt_count, recovery_count, parent status, lease validity). It creates a race where a task gets status-reset by `_post_init` but its metadata still has stale lease info, confusing `recover_stale_dept_tasks` which then does a second reset.

### Change 4: Guard `recover_stale_dept_tasks` against permanently failed tasks

```python
# Add at the top of the per-row loop, after parent check:
if metadata.get("permanent_failure"):
    logger.info(
        f"[RECOVER] 태스크 {task_id} 복구 스킵: permanent_failure 플래그"
    )
    # Ensure it's actually failed (in case _post_init reset it before this code ran)
    await db.execute(
        "UPDATE pm_tasks SET status='failed', updated_at=? WHERE id=? AND status != 'failed'",
        (now_iso, task_id),
    )
    continue
```

### Change 5: Add fast-failure detection (optional but recommended)

Tasks completing all 6 phases in 0.3 seconds are clearly not doing real work. Add a minimum execution time check:

```python
# In _execute_task (task_poller.py), after task completion:
elapsed = time.monotonic() - start_time
if elapsed < 2.0 and not task_succeeded:
    metadata = dict(task.get("metadata") or {})
    fast_fail_count = metadata.get("fast_fail_count", 0) + 1
    metadata["fast_fail_count"] = fast_fail_count
    if fast_fail_count >= 3:
        logger.error(
            f"[TaskPoller] 태스크 {task_id} 연속 빠른 실패 {fast_fail_count}회 — 자동 중단"
        )
        await self._db.update_pm_task_status(
            task_id, "failed",
            result="연속 빠른 실패 감지 (< 2초). 구조적 문제로 판단하여 자동 중단."
        )
        return  # Skip requeue
```

---

## Edge Cases and Risks

### Edge Case 1: Legitimate long-running tasks that need many attempts
**Scenario:** A complex code analysis task takes 10 minutes, but the bot crashes at minute 8 due to httpcore issues. After 3 crash cycles × 5 attempts = 15 total attempts, the task permanently fails even though each crash was external.

**Mitigation:** `MAX_TOTAL_ATTEMPTS = 15` gives 3 full recovery cycles. If a task fails 15 times across 3 restarts, there is almost certainly a structural problem. The fix for *this* root cause is fixing the Python 3.14 + httpcore crash, not allowing infinite retries.

### Edge Case 2: Race condition between _post_init removal and TaskPoller startup
**Risk:** If `_post_init` is removed, tasks stuck as `running` with expired leases won't be reset until `TaskPoller.start()` calls `recover_stale_dept_tasks`. Since `_post_init` already calls `TaskPoller.start()` at line ~3098, this is a non-issue — the recovery happens in the same startup sequence.

### Edge Case 3: Existing tasks in DB with no `total_attempt_count`
**Risk:** Tasks created before the migration won't have `total_attempt_count` or `recovery_count` in metadata.

**Mitigation:** All `.get()` calls default to 0, so old tasks will start counting from 0. No migration needed — the fields are added organically on first access.

### Edge Case 4: Task stuck as `running` with `permanent_failure` flag
**Risk:** If `_post_init` ran before this fix was deployed, it may have reset a permanently-failed task to `assigned`. The `permanent_failure` flag in metadata would still be set, but the status would be wrong.

**Mitigation:** Change 4 above includes a guard that re-fails tasks with `permanent_failure` even if their status was incorrectly reset.

### Edge Case 5: Multiple bots recovering the same task simultaneously
**Risk:** Two department bots restart at the same time, both call `recover_stale_dept_tasks`. Since `assigned_dept` is per-bot, this is already partitioned — each bot only recovers its own tasks. No race condition.

---

## Migration Strategy

### Step 1: Immediate hotfix (deploy now)
1. Remove `_post_init` raw SQL (Change 3) — eliminates the double-reset path
2. Add `recovery_count` cap to `recover_stale_dept_tasks` (Change 2) — stops infinite recovery
3. Add `permanent_failure` guard (Change 4) — prevents re-recovery of dead tasks

### Step 2: Comprehensive fix (deploy after testing)
4. Add `total_attempt_count` tracking (Change 1) — absolute lifetime limit
5. Add fast-failure detection (Change 5) — catches 0.3s no-op executions

### Step 3: Clean up currently-stuck tasks
Run this one-time SQL to fail all tasks that have been looping:

```sql
-- Find tasks that have been "recovered" multiple times (evidence of looping)
-- by checking if recovered_at exists and the task is still assigned/running
UPDATE pm_tasks
SET status = 'failed',
    metadata = json_set(
        metadata,
        '$.fail_reason', '무한 루프 감지 — 수동 정리',
        '$.permanent_failure', 1
    )
WHERE status IN ('assigned', 'running')
  AND json_extract(metadata, '$.recovered_at') IS NOT NULL
  AND updated_at < datetime('now', '-1 hour');
```

### Step 4: Fix the comment
```python
# OLD (line 632):
# attempt_count를 0으로 리셋하므로 무한루프 위험은 없음.

# NEW:
# attempt_count는 사이클당 카운터 (recovery 시 리셋됨).
# 무한루프 방지는 recovery_count + total_attempt_count로 보장.
```

---

## Summary of Changes

| File | Line(s) | Change | Effort |
|------|---------|--------|--------|
| `context_db.py` | 628-632 | Add `MAX_TOTAL_ATTEMPTS`, `MAX_RECOVERY_COUNT` constants | Low |
| `context_db.py` | 650-670 | Track `total_attempt_count`, check both limits | Low |
| `context_db.py` | 785-810 | Cap `recovery_count`, guard `permanent_failure` | Medium |
| `telegram_relay.py` | 3082-3093 | Remove raw SQL reset block entirely | Low |
| `task_poller.py` | 95-115 | (Optional) Add fast-failure detection | Low |

**Total estimated effort:** 1-2 hours including testing.

---

## References

- `core/context_db.py:628` — `MAX_TASK_ATTEMPTS = 5` constant and misleading comment
- `core/context_db.py:654` — `attempt_count` increment and auto-fail logic in `claim_pm_task_lease`
- `core/context_db.py:~790` — `metadata["attempt_count"] = 0` in `recover_stale_dept_tasks` (the root cause)
- `core/telegram_relay.py:~3082` — Raw SQL `_post_init` reset (secondary cause)
- `core/task_poller.py:77` — `recover_stale_dept_tasks` called at poller startup
- `core/task_poller.py:95-115` — `_execute_task` with `requeue_if_running` on failure
- `core/staleness_checker.py` — Independent staleness detection (not part of the bug, but related)
