# Phase 3-A: P2 Priority-2 Feature Design

## Overview

Phase 3-A extends the AIMesh REST API (Phase 2-A) with three production-grade features:
rate limiting, API metrics, and audit logging. All features use feature flags and are
disabled by default to preserve zero-impact on the existing Telegram bot runtime.

---

## Feature List & Rationale

| ID | Feature | Flag | Default | Rationale |
|----|---------|------|---------|-----------|
| P1-5 | Rate Limiting | `ENABLE_RATE_LIMITING` | false | Prevents API abuse; sliding window per client |
| P1-3 | API Metrics | always-on (middleware) | active | Observability for endpoint health and latency |
| P1-8 | Audit Log | `ENABLE_AUDIT_LOG` | false | Compliance and forensic traceability for task mutations |

---

## Interface Specifications

### Rate Limiter (`core/api/rate_limiter.py`)

```
check_rate_limit(request: Request) -> None
    Raises HTTPException(429) when limit exceeded.
    No-op when ENABLE_RATE_LIMITING=false.

get_rate_limit_status(request: Request) -> dict
    Returns: {client_id, requests_in_window, limit, window_seconds, remaining}

reset_rate_limit_windows() -> None
    Test isolation helper. Clears all in-memory windows.
```

**Client identification priority:**
1. `X-API-Key` header → `key:<value>`
2. `X-Forwarded-For` header → `ip:<first IP>`
3. `request.client.host` → `ip:<host>`

**Config env vars:**
- `RATE_LIMIT_REQUESTS` (default: 60)
- `RATE_LIMIT_WINDOW_SECONDS` (default: 60)

### API Metrics (`core/api/metrics.py`)

```
record_request(method, path, status_code, duration_ms) -> None
    Increments in-memory counters for the endpoint key "{METHOD} {path}".

get_metrics_snapshot() -> dict
    Returns: {uptime_seconds, total_requests, endpoints: {key: EndpointMetric.to_dict()}}

reset_metrics() -> None
    Test isolation helper. Resets all counters and start time.
```

**EndpointMetric fields:** `total_requests`, `status_counts` (dict[int, int]), `avg_duration_ms`

### Audit Log (`core/api/audit_log.py`)

```
write_audit_event(action, task_id, org_id, api_key, client_ip, extra, log_path) -> None
    Appends a JSONL event to log_path (default: data/audit.log).
    No-op when ENABLE_AUDIT_LOG=false.

read_audit_events(log_path, limit) -> list[dict]
    Returns the latest `limit` events in reverse-chronological order.
```

**Event schema:**
```json
{
  "timestamp": 1711700000.0,
  "action": "task_created",
  "task_id": "uuid",
  "org_id": "dev",
  "api_key_prefix": "abcdefgh****",
  "client_ip": "127.0.0.1",
  "extra": {}
}
```

**API key masking:** Only the first 8 characters are retained; the rest is replaced with `****`.

### Metrics Route (`core/api/routes/metrics.py`)

```
GET /api/v1/metrics
    No auth required.
    Returns: get_metrics_snapshot()
```

---

## File Changes

| File | Change Type | Description |
|------|-------------|-------------|
| `core/api/rate_limiter.py` | New | Sliding-window rate limiter |
| `core/api/metrics.py` | New | In-memory request counter |
| `core/api/audit_log.py` | New | JSONL audit event writer |
| `core/api/routes/metrics.py` | New | GET /api/v1/metrics endpoint |
| `core/api/app.py` | Modified | HTTP middleware for metrics; include metrics_router |
| `core/api/routes/tasks.py` | Modified | Add rate-limit dependency; add audit log calls |
| `.env.example` | Modified | Add Phase 3-A feature flag documentation |

### app.py changes

- Imports: `record_request`, `metrics_router`
- Added `@app.middleware("http")` to call `record_request()` after every response
- `metrics_router` included unconditionally (metrics do not require ENABLE_REST_API)

### tasks.py changes

- Router `dependencies` extended with `Depends(check_rate_limit)`
- `create_task`: calls `write_audit_event("task_created", ...)`
- `get_task` (404 path): calls `write_audit_event("task_not_found", ...)`
- `cancel_task`: calls `write_audit_event("task_deleted", ...)` after successful delete

---

## Test Coverage Summary

### `tests/test_rate_limiter.py` (9 tests)

| Test | Scenario |
|------|----------|
| `test_rate_limit_disabled_by_default` | Flag=false → no 429 regardless of call count |
| `test_rate_limit_allows_under_limit` | Exactly limit=3 requests all pass |
| `test_rate_limit_blocks_over_limit` | 4th request with limit=3 → HTTP 429 + Retry-After header |
| `test_rate_limit_window_expiry` | Old timestamps expire; requests allowed again after window |
| `test_get_rate_limit_status` | remaining decrements correctly after requests |
| `test_reset_clears_windows` | reset_rate_limit_windows() enables fresh requests |
| `test_client_id_from_api_key` | X-API-Key header → `key:` prefix |
| `test_client_id_from_ip` | No key → `ip:` prefix from client.host |
| `test_client_id_from_forwarded` | X-Forwarded-For → first IP used |

### `tests/test_api_metrics.py` (11 tests)

| Test | Scenario |
|------|----------|
| `test_record_request_increments_count` | Counts accumulate per endpoint |
| `test_get_metrics_snapshot_empty` | Empty state → zero totals |
| `test_get_metrics_snapshot_after_records` | Multi-endpoint aggregation |
| `test_avg_duration_calculation` | Average computed correctly |
| `test_status_code_counting` | Per-status-code counters |
| `test_reset_metrics_clears_all` | reset_metrics() zeroes everything |
| `test_metrics_endpoint_returns_200` | ASGI integration — GET /api/v1/metrics → 200 |
| `test_uptime_increases_over_time` | uptime_seconds grows monotonically |
| `test_endpoint_metric_avg_zero_when_no_requests` | Zero-division guard |
| `test_endpoint_metric_to_dict` | to_dict() shape |

### `tests/test_audit_log.py` (10 tests)

| Test | Scenario |
|------|----------|
| `test_audit_disabled_writes_nothing` | Flag=false → no file created |
| `test_write_audit_event_creates_file` | Flag=true → file is created |
| `test_audit_event_fields` | Required fields present |
| `test_api_key_masking` | 16-char key → 8 chars + **** |
| `test_api_key_short_not_masked` | Short key → stored as-is |
| `test_read_audit_events_empty` | Non-existent file → [] |
| `test_read_audit_events_returns_latest` | limit=3 of 5 events |
| `test_extra_field` | extra dict stored in event |
| `test_jsonl_format` | Each line is valid JSON |
| `test_extra_none_not_in_event` | extra=None → key absent |

**Total: 29 new tests, all passing.**

---

## Implementation Principles

1. **Feature flag at call time** — Each public function reads the env var on every invocation (not at import time), so tests can monkeypatch module-level attributes without restart.
2. **`from __future__ import annotations`** — All new modules use deferred annotation evaluation for forward-compatible typing.
3. **No bot-layer impact** — `telegram_relay.py` and all bot files are untouched. Rate limiting and audit logging are purely in the API layer.
4. **In-memory state** — Both rate limiter windows and metrics counters are in-memory dicts. They reset on process restart. A future Phase could add Redis-backed persistence.
5. **Test isolation** — `reset_rate_limit_windows()` and `reset_metrics()` are provided as helpers and called via `autouse` fixtures.
6. **JSONL for audit** — One JSON object per line; easy to tail, grep, or stream to log aggregators. Files are append-only and parent dirs are auto-created.
7. **API key masking** — Only the first 8 characters are logged to prevent secret leakage in audit files.
