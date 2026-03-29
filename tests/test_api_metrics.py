"""tests/test_api_metrics.py — API 메트릭 단위 테스트 (Phase 3-A)."""
from __future__ import annotations

import os
import time

import pytest

import core.api.metrics as metrics_module
from core.api.metrics import (
    EndpointMetric,
    get_metrics_snapshot,
    record_request,
    reset_metrics,
)


# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset():
    """각 테스트 전후 메트릭 초기화."""
    reset_metrics()
    yield
    reset_metrics()


# ---------------------------------------------------------------------------
# EndpointMetric 단위 테스트
# ---------------------------------------------------------------------------


def test_record_request_increments_count():
    """record_request 호출 시 카운트가 증가."""
    record_request("GET", "/api/v1/tasks", 200, 12.5)
    record_request("GET", "/api/v1/tasks", 200, 7.3)

    snapshot = get_metrics_snapshot()
    endpoint = snapshot["endpoints"]["GET /api/v1/tasks"]
    assert endpoint["total_requests"] == 2


def test_get_metrics_snapshot_empty():
    """메트릭 없을 때 스냅샷은 total_requests=0."""
    snapshot = get_metrics_snapshot()
    assert snapshot["total_requests"] == 0
    assert snapshot["endpoints"] == {}
    assert snapshot["uptime_seconds"] >= 0


def test_get_metrics_snapshot_after_records():
    """여러 엔드포인트 기록 후 스냅샷 집계."""
    record_request("POST", "/api/v1/tasks", 201, 30.0)
    record_request("GET", "/api/v1/tasks", 200, 10.0)
    record_request("GET", "/api/v1/tasks", 200, 20.0)

    snapshot = get_metrics_snapshot()
    assert snapshot["total_requests"] == 3
    assert "POST /api/v1/tasks" in snapshot["endpoints"]
    assert "GET /api/v1/tasks" in snapshot["endpoints"]


def test_avg_duration_calculation():
    """평균 응답 시간 계산 정확성 검증."""
    record_request("GET", "/health", 200, 10.0)
    record_request("GET", "/health", 200, 20.0)
    record_request("GET", "/health", 200, 30.0)

    snapshot = get_metrics_snapshot()
    avg = snapshot["endpoints"]["GET /health"]["avg_duration_ms"]
    assert avg == pytest.approx(20.0, abs=0.1)


def test_status_code_counting():
    """상태 코드별 카운트 집계."""
    record_request("GET", "/api/v1/tasks/1", 200, 5.0)
    record_request("GET", "/api/v1/tasks/2", 404, 3.0)
    record_request("GET", "/api/v1/tasks/3", 404, 2.0)

    snapshot = get_metrics_snapshot()
    counts_200 = 0
    counts_404 = 0
    for ep_data in snapshot["endpoints"].values():
        counts_200 += ep_data["status_counts"].get(200, 0)
        counts_404 += ep_data["status_counts"].get(404, 0)

    assert counts_200 == 1
    assert counts_404 == 2


def test_reset_metrics_clears_all():
    """reset_metrics() 후 모든 상태 초기화."""
    record_request("DELETE", "/api/v1/tasks/x", 204, 8.0)
    reset_metrics()

    snapshot = get_metrics_snapshot()
    assert snapshot["total_requests"] == 0
    assert snapshot["endpoints"] == {}


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_200():
    """GET /api/v1/metrics 엔드포인트가 200 반환."""
    import os

    os.environ["ENABLE_REST_API"] = "true"
    try:
        from httpx import ASGITransport, AsyncClient

        from core.api.app import create_app

        app = create_app(db_path=":memory:")

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/api/v1/metrics")

        assert resp.status_code == 200
        data = resp.json()
        assert "total_requests" in data
        assert "uptime_seconds" in data
        assert "endpoints" in data
    finally:
        os.environ.pop("ENABLE_REST_API", None)


def test_uptime_increases_over_time():
    """uptime_seconds가 시간이 지날수록 증가."""
    snap1 = get_metrics_snapshot()
    time.sleep(0.05)
    snap2 = get_metrics_snapshot()
    assert snap2["uptime_seconds"] >= snap1["uptime_seconds"]


def test_endpoint_metric_avg_zero_when_no_requests():
    """요청 없는 EndpointMetric의 avg_duration_ms는 0."""
    m = EndpointMetric()
    assert m.avg_duration_ms == 0.0


def test_endpoint_metric_to_dict():
    """to_dict()가 올바른 키를 반환."""
    m = EndpointMetric()
    m.record(200, 15.0)
    d = m.to_dict()
    assert "total_requests" in d
    assert "status_counts" in d
    assert "avg_duration_ms" in d
    assert d["total_requests"] == 1
