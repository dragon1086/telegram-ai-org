# 무한 재시도 루프 버그 — 3-Agent 종합 보고서

**Date:** 2026-03-23
**Agents:** Architect (Opus), Security Reviewer (Sonnet), Critic (Opus)
**Verdict:** 3/3 에이전트 모두 버그 확인, 수정 방향 합의됨

---

## 1. 근본 원인 (3/3 합의)

3개의 독립적 메커니즘이 맞물려 무한 루프 생성:

| # | 위치 | 동작 | 문제 |
|---|------|------|------|
| 1 | `context_db.py:654` claim_pm_task_lease | attempt_count++ → 5회 초과 시 auto-fail | 정상 (안전장치) |
| 2 | `context_db.py:812` recover_stale_dept_tasks | `attempt_count = 0` 리셋 | **안전장치 무력화** |
| 3 | `telegram_relay.py:~3082` _post_init | Raw SQL로 running→assigned (metadata 무시) | **이중 바이패스** |

**주석이 거짓말:** `"attempt_count를 0으로 리셋하므로 무한루프 위험은 없음"` ← 리셋이 무한루프의 **원인**

---

## 2. 보안 리스크 (Security Reviewer)

- **CRITICAL** — 무한 재시도로 Claude API 비용 무한 소모 가능
- **HIGH** — claim_pm_task_lease에 TOCTOU 레이스 컨디션 (read→write 비원자적)
- **HIGH** — _post_init Raw SQL이 lease_owner, orphan guard, MAX_AGE 등 모든 안전장치 바이패스
- **MEDIUM** — fast-fail 태스크에 backoff 없음 (0.3초 실패 → 2초 후 재시도)
- **MEDIUM** — StalenessChecker와 recover_stale가 상태 경합 가능

---

## 3. 수정 옵션 평가 (Critic)

| 옵션 | 평가 | 이유 |
|------|------|------|
| A. attempt_count 리셋 금지 | **Reject** | 정당한 transient failure도 영구 사망 |
| B. total_attempt_count 추가 (리셋 불가) | **Best** | 이중 카운터로 두 관심사 분리 |
| C. recovery_count 제한 | Viable | B보다 열등, 의미 불명확 |
| D. 지수 백오프 | **Reject** | 실제로 멈추지 않음, 추론 복잡 |
| E. _post_init에서 attempt_count 체크 | Partial | 하나의 경로만 막음 |

**Critic 추가 제안:** `first_attempted_at` 타임스탬프 — 시간은 리셋 불가능하므로 24시간 초과 시 자동 중단. 카운터와 병행 사용 가능.

---

## 4. 최종 권장 수정안 (3-Agent 합의)

### Phase 1: 핫픽스 (즉시 배포)

**Change 1: `_post_init` Raw SQL 삭제** (telegram_relay.py:~3082)
```python
# 삭제 대상 (전체 try/except 블록):
cutoff = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
async with _aiosqlite.connect(self.context_db.db_path) as _db:
    result = await _db.execute(
        "UPDATE pm_tasks SET status='assigned' "
        "WHERE status='running' AND assigned_dept=? AND updated_at < ?",
        (self.org_id, cutoff),
    )

# 대체: recover_stale_dept_tasks가 TaskPoller 시작 시 이미 동일 작업 수행
# → 중복 경로 제거, 안전장치 우회 차단
```

**Change 2: `recover_stale_dept_tasks`에 recovery_count 도입** (context_db.py:~790)
```python
MAX_RECOVERY_COUNT = 3

# 기존: metadata["attempt_count"] = 0
# 변경:
recovery_count = metadata.get("recovery_count", 0) + 1
if recovery_count > MAX_RECOVERY_COUNT:
    logger.warning(f"Task {task_id} 최대 복구 횟수 초과 ({recovery_count}), 복구 건너뜀")
    continue
metadata["attempt_count"] = 0
metadata["recovery_count"] = recovery_count
```

**Change 3: 주석 수정** (context_db.py:632)
```python
# OLD: attempt_count를 0으로 리셋하므로 무한루프 위험은 없음.
# NEW: recover_stale_dept_tasks에서 recovery_count로 복구 횟수를 제한하여
#      무한 재시작 루프를 방지한다. MAX_RECOVERY_COUNT(3) × MAX_TASK_ATTEMPTS(5)
#      = 최대 15회 시도 후 영구 중단.
```

### Phase 2: 종합 수정 (테스트 후 배포)

**Change 4: `total_attempt_count` 추가** (context_db.py claim_pm_task_lease)
```python
MAX_TOTAL_ATTEMPTS = 15

# claim_pm_task_lease 내부:
total_attempt_count = metadata.get("total_attempt_count", 0) + 1
if total_attempt_count > MAX_TOTAL_ATTEMPTS:
    # recovery_count와 독립적인 이중 안전장치
    metadata["fail_reason"] = f"총 시도 횟수 초과 ({MAX_TOTAL_ATTEMPTS}회)"
    # → auto-fail
```

**Change 5: fast-failure 감지** (task_poller.py _execute_task)
```python
# 실행 시간 < 2초인 태스크 연속 3회 시 경고 + 백오프
start = time.monotonic()
await self._on_task(task)
elapsed = time.monotonic() - start

if elapsed < 2.0:
    fast_fail_count = metadata.get("fast_fail_count", 0) + 1
    if fast_fail_count >= 3:
        metadata["retry_after_at"] = (now + timedelta(minutes=5)).isoformat()
        logger.warning(f"Fast-fail 감지: {task_id} ({elapsed:.1f}s × {fast_fail_count}회)")
```

**Change 6: TOCTOU 레이스 수정** (context_db.py claim_pm_task_lease)
```python
# read-then-write → atomic CAS UPDATE
async with aiosqlite.connect(self.db_path) as db:
    result = await db.execute(
        """UPDATE pm_tasks SET status='running', metadata=?, updated_at=?
           WHERE id=? AND status='assigned'
           AND (json_extract(metadata, '$.lease_owner') IS NULL
                OR json_extract(metadata, '$.lease_expires_at') < ?)""",
        (json.dumps(new_metadata), now_iso, task_id, now.isoformat()),
    )
    if result.rowcount == 0:
        return None  # 다른 봇이 먼저 claim
```

---

## 5. 마이그레이션 (기존 DB 정리)

```sql
-- 현재 stuck된 태스크 정리 (failed 3건 중 해당되는 것)
UPDATE pm_tasks
SET metadata = json_set(
    metadata,
    '$.recovery_count', 0,
    '$.total_attempt_count', 0,
    '$.permanent_failure', false
)
WHERE status IN ('assigned', 'running')
AND json_extract(metadata, '$.attempt_count') >= 5;
```

---

## 6. 배포 순서

1. **즉시**: Change 1 (Raw SQL 삭제) + Change 2 (recovery_count) + Change 3 (주석)
2. **테스트 후**: Change 4 (total_attempt_count) + Change 5 (fast-fail)
3. **별도 PR**: Change 6 (TOCTOU atomic CAS)
4. **배포 후**: 마이그레이션 SQL 실행

---

## 7. 리스크 매트릭스

| 수정 | 부작용 위험 | 완화책 |
|------|------------|--------|
| Raw SQL 삭제 | _post_init과 TaskPoller 시작 간 간극 | recover_stale가 이미 poll_loop 초기에 실행 |
| recovery_count | 정당한 장기 태스크 사망 | MAX=3 → 총 15회 충분 + 수동 리셋 명령 |
| total_attempt_count | 영구 stuck | MAX=15 + 관리자 리셋 명령어 |
| fast-fail 감지 | 정상 빠른 태스크 오탐 | 2초 임계값 + 연속 3회 조건 |
| TOCTOU 수정 | SQLite json_extract 호환성 | SQLite 3.9+ 필요 (Python 3.14은 충족) |
