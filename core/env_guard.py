"""core/env_guard.py — 환경변수 방어 코드 모듈.

필수 환경변수 누락 시 즉시 ValueError를 발생시키거나,
timeout 기본값 사용 시 경고 로그를 출력한다.

사용:
    from core.env_guard import require_env, warn_default_timeout

    token = require_env("TELEGRAM_BOT_TOKEN")
    warn_default_timeout(timeout_val, default=120, param_name="E2E_TIMEOUT")
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# 기본 timeout 값 (infra-baseline.yaml 기준)
_PREFLIGHT_DEFAULT_TIMEOUT = 120


def require_env(var_name: str, *, context: str = "") -> str:
    """환경변수를 읽어 반환한다. 비어있으면 ValueError를 발생시킨다.

    Parameters
    ----------
    var_name:
        읽을 환경변수 이름.
    context:
        오류 메시지에 포함할 호출 맥락 설명 (선택).

    Returns
    -------
    str
        환경변수 값 (비어있지 않음이 보장됨).

    Raises
    ------
    ValueError
        환경변수가 설정되어 있지 않거나 빈 문자열인 경우.
    """
    val = os.environ.get(var_name, "")
    if not val:
        ctx_hint = f" ({context})" if context else ""
        raise ValueError(
            f"필수 환경변수 '{var_name}' 가 설정되지 않았습니다{ctx_hint}. "
            f".env 파일 또는 환경 설정을 확인하세요."
        )
    return val


def get_env_or_warn(var_name: str, default: str = "", *, context: str = "") -> str:
    """환경변수를 읽어 반환한다. 없으면 경고 로그 후 default 반환.

    Parameters
    ----------
    var_name:
        읽을 환경변수 이름.
    default:
        환경변수 없을 때 반환할 기본값.
    context:
        경고 메시지에 포함할 호출 맥락 설명 (선택).

    Returns
    -------
    str
        환경변수 값 또는 default.
    """
    val = os.environ.get(var_name, "")
    if not val:
        ctx_hint = f" [{context}]" if context else ""
        logger.warning(
            "[env_guard] 환경변수 '%s' 가 설정되지 않았습니다%s. "
            "기본값 %r 을 사용합니다.",
            var_name,
            ctx_hint,
            default,
        )
        return default
    return val


def warn_default_timeout(
    timeout_val: int | float | None,
    *,
    default: int = _PREFLIGHT_DEFAULT_TIMEOUT,
    param_name: str = "timeout",
) -> None:
    """timeout이 기본값과 동일할 때 경고 로그를 출력한다.

    infra-baseline.yaml 에서 명시적으로 설정하지 않고 기본값을 그대로 사용하면
    환경에 따라 실제 필요 시간보다 짧거나 길 수 있다.

    Parameters
    ----------
    timeout_val:
        검사할 timeout 값.
    default:
        비교할 기본값 (기본: _PREFLIGHT_DEFAULT_TIMEOUT=120).
    param_name:
        경고 메시지에 포함할 파라미터 이름.
    """
    if timeout_val is None:
        logger.warning(
            "[env_guard] '%s' 값이 None입니다 — timeout 미설정. "
            "infra-baseline.yaml 에서 명시적으로 설정하세요.",
            param_name,
        )
        return
    try:
        val = int(timeout_val)
    except (TypeError, ValueError):
        logger.warning(
            "[env_guard] '%s' 값이 유효한 숫자가 아닙니다: %r",
            param_name,
            timeout_val,
        )
        return
    if val == default:
        logger.warning(
            "[env_guard] '%s=%d' 는 하드코딩 기본값입니다. "
            "infra-baseline.yaml 또는 환경변수에서 명시적으로 설정했는지 확인하세요.",
            param_name,
            val,
        )
