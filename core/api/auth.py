"""core.api.auth — API Key 인증 의존성 (Phase 2-A).

환경변수:
    ENABLE_API_AUTH: "true" / "1" 시 인증 활성화 (기본 false).
    AIMESH_API_KEYS: 유효한 API Key 목록 (콤마 구분).
                     예: "key-abc123,key-def456"

인증 방식:
    HTTP 헤더: X-API-Key: <key>

인증 비활성화(ENABLE_API_AUTH=false) 시 모든 요청이 통과됩니다.
로컬 개발 편의를 위한 설계입니다.
"""
from __future__ import annotations

import os

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

ENABLE_API_AUTH: bool = os.environ.get("ENABLE_API_AUTH", "false").lower() in ("true", "1")
"""True일 때 X-API-Key 헤더 검증을 활성화합니다."""

_raw_keys = os.environ.get("AIMESH_API_KEYS", "")
API_KEYS: frozenset[str] = frozenset(k.strip() for k in _raw_keys.split(",") if k.strip())
"""허용된 API Key 집합. 비어 있으면 인증 비활성 상태에서만 의미가 있습니다."""

# ---------------------------------------------------------------------------
# FastAPI 보안 스키마
# ---------------------------------------------------------------------------

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str | None = Security(_api_key_header)) -> str:
    """API Key 검증 FastAPI 의존성.

    ENABLE_API_AUTH=false → 항상 통과 (빈 문자열 반환).
    ENABLE_API_AUTH=true  → X-API-Key 헤더 없거나 잘못된 값이면 401 반환.

    Returns:
        검증된 API Key 문자열 (인증 비활성 시 빈 문자열).

    Raises:
        HTTPException(401): 인증 활성화 상태에서 키가 없거나 잘못된 경우.
    """
    if not ENABLE_API_AUTH:
        return ""

    if not api_key or api_key not in API_KEYS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 API Key입니다. X-API-Key 헤더를 확인하세요.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key
