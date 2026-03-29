"""core.api.rate_limiter — 슬라이딩 윈도우 Rate Limiter (Phase 3-A).

피처 플래그: ENABLE_RATE_LIMITING (기본 false)
Config: RATE_LIMIT_REQUESTS=60, RATE_LIMIT_WINDOW_SECONDS=60

클라이언트 식별: X-API-Key 헤더 → API Key, 없으면 클라이언트 IP.
슬라이딩 윈도우: 인메모리 deque로 타임스탬프 추적.
"""
from __future__ import annotations

import os
import time
from collections import deque
from typing import Deque

from fastapi import HTTPException, Request, status

ENABLE_RATE_LIMITING: bool = os.environ.get("ENABLE_RATE_LIMITING", "false").lower() in ("true", "1")
RATE_LIMIT_REQUESTS: int = int(os.environ.get("RATE_LIMIT_REQUESTS", "60"))
RATE_LIMIT_WINDOW_SECONDS: int = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))

# client_id -> deque of timestamps
_windows: dict[str, Deque[float]] = {}


def _get_client_id(request: Request) -> str:
    """X-API-Key 또는 클라이언트 IP로 식별자를 결정합니다."""
    key = request.headers.get("X-API-Key")
    if key:
        return f"key:{key}"
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


def check_rate_limit(request: Request) -> None:
    """요청이 rate limit를 초과하면 HTTP 429를 발생시킵니다.

    ENABLE_RATE_LIMITING=false 면 즉시 반환합니다.

    Raises:
        HTTPException(429): Rate limit 초과 시.
    """
    if not ENABLE_RATE_LIMITING:
        return

    client_id = _get_client_id(request)
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS

    if client_id not in _windows:
        _windows[client_id] = deque()

    window = _windows[client_id]

    # 윈도우 밖 타임스탬프 제거
    while window and window[0] < window_start:
        window.popleft()

    if len(window) >= RATE_LIMIT_REQUESTS:
        retry_after = int(window[0] + RATE_LIMIT_WINDOW_SECONDS - now) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Retry after {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    window.append(now)


def reset_rate_limit_windows() -> None:
    """테스트 격리용: 모든 rate limit 윈도우를 초기화합니다."""
    _windows.clear()


def get_rate_limit_status(request: Request) -> dict:
    """클라이언트의 현재 rate limit 상태를 반환합니다."""
    client_id = _get_client_id(request)
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS

    window = _windows.get(client_id, deque())
    recent = sum(1 for ts in window if ts >= window_start)

    return {
        "client_id": client_id,
        "requests_in_window": recent,
        "limit": RATE_LIMIT_REQUESTS,
        "window_seconds": RATE_LIMIT_WINDOW_SECONDS,
        "remaining": max(0, RATE_LIMIT_REQUESTS - recent),
    }
