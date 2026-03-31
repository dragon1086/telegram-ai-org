"""tests/test_rate_limiter.py — Rate Limiter 단위 테스트 (Phase 3-A)."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

import core.api.rate_limiter as rl_module
from core.api.rate_limiter import (
    _get_client_id,
    check_rate_limit,
    get_rate_limit_status,
    reset_rate_limit_windows,
)

# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------


def _make_request(api_key: str = "", ip: str = "127.0.0.1", forwarded: str = "") -> MagicMock:
    """Fake FastAPI Request 객체를 생성합니다."""
    req = MagicMock()
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    if forwarded:
        headers["X-Forwarded-For"] = forwarded
    req.headers = headers
    req.client = MagicMock()
    req.client.host = ip
    return req


# ---------------------------------------------------------------------------
# 테스트
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_windows():
    """각 테스트 전후 윈도우 초기화."""
    reset_rate_limit_windows()
    yield
    reset_rate_limit_windows()


def test_rate_limit_disabled_by_default(monkeypatch):
    """ENABLE_RATE_LIMITING=false 시 429 발생 없이 통과."""
    monkeypatch.setattr(rl_module, "ENABLE_RATE_LIMITING", False)
    req = _make_request(ip="10.0.0.1")
    # 아무리 많이 호출해도 예외 없어야 함
    for _ in range(200):
        check_rate_limit(req)


def test_rate_limit_allows_under_limit(monkeypatch):
    """limit=3 설정 시 3번 요청은 모두 통과."""
    monkeypatch.setattr(rl_module, "ENABLE_RATE_LIMITING", True)
    monkeypatch.setattr(rl_module, "RATE_LIMIT_REQUESTS", 3)
    monkeypatch.setattr(rl_module, "RATE_LIMIT_WINDOW_SECONDS", 60)

    req = _make_request(ip="10.0.0.2")
    for _ in range(3):
        check_rate_limit(req)  # 예외 없어야 함


def test_rate_limit_blocks_over_limit(monkeypatch):
    """limit=3 설정 시 4번째 요청에서 HTTP 429 발생."""
    from fastapi import HTTPException

    monkeypatch.setattr(rl_module, "ENABLE_RATE_LIMITING", True)
    monkeypatch.setattr(rl_module, "RATE_LIMIT_REQUESTS", 3)
    monkeypatch.setattr(rl_module, "RATE_LIMIT_WINDOW_SECONDS", 60)

    req = _make_request(ip="10.0.0.3")
    for _ in range(3):
        check_rate_limit(req)

    with pytest.raises(HTTPException) as exc_info:
        check_rate_limit(req)

    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


def test_rate_limit_window_expiry(monkeypatch):
    """윈도우 만료 후 타임스탬프가 제거되어 다시 통과해야 함."""
    from fastapi import HTTPException

    monkeypatch.setattr(rl_module, "ENABLE_RATE_LIMITING", True)
    monkeypatch.setattr(rl_module, "RATE_LIMIT_REQUESTS", 2)
    monkeypatch.setattr(rl_module, "RATE_LIMIT_WINDOW_SECONDS", 1)

    req = _make_request(ip="10.0.0.4")

    # 2번 요청 채우기
    check_rate_limit(req)
    check_rate_limit(req)

    # 3번째는 429
    with pytest.raises(HTTPException):
        check_rate_limit(req)

    # 윈도우(1초) 경과 후 다시 통과
    time.sleep(1.1)
    check_rate_limit(req)  # 예외 없어야 함


def test_get_rate_limit_status(monkeypatch):
    """요청 후 remaining 카운트가 정확히 감소."""
    monkeypatch.setattr(rl_module, "ENABLE_RATE_LIMITING", True)
    monkeypatch.setattr(rl_module, "RATE_LIMIT_REQUESTS", 10)
    monkeypatch.setattr(rl_module, "RATE_LIMIT_WINDOW_SECONDS", 60)

    req = _make_request(api_key="testkey123")

    # 요청 전 상태
    status_before = get_rate_limit_status(req)
    assert status_before["remaining"] == 10

    # 3번 요청
    check_rate_limit(req)
    check_rate_limit(req)
    check_rate_limit(req)

    status_after = get_rate_limit_status(req)
    assert status_after["requests_in_window"] == 3
    assert status_after["remaining"] == 7
    assert status_after["limit"] == 10


def test_reset_clears_windows(monkeypatch):
    """reset_rate_limit_windows() 호출 시 모든 윈도우 초기화."""
    monkeypatch.setattr(rl_module, "ENABLE_RATE_LIMITING", True)
    monkeypatch.setattr(rl_module, "RATE_LIMIT_REQUESTS", 2)
    monkeypatch.setattr(rl_module, "RATE_LIMIT_WINDOW_SECONDS", 60)

    req = _make_request(ip="10.0.0.5")
    check_rate_limit(req)
    check_rate_limit(req)

    reset_rate_limit_windows()

    # 리셋 후 다시 2번 요청 가능
    check_rate_limit(req)
    check_rate_limit(req)


def test_client_id_from_api_key():
    """X-API-Key 헤더가 있으면 key: 접두사로 식별."""
    req = _make_request(api_key="my-secret-key")
    client_id = _get_client_id(req)
    assert client_id == "key:my-secret-key"


def test_client_id_from_ip():
    """X-API-Key 없으면 클라이언트 IP로 식별."""
    req = _make_request(ip="192.168.1.100")
    client_id = _get_client_id(req)
    assert client_id == "ip:192.168.1.100"


def test_client_id_from_forwarded():
    """X-Forwarded-For 헤더가 있으면 첫 번째 IP 사용."""
    req = _make_request(forwarded="203.0.113.10, 10.0.0.1")
    client_id = _get_client_id(req)
    assert client_id == "ip:203.0.113.10"
