"""tests/conftest.py — 루트 레벨 pytest 공통 fixture.

이 파일은 모든 테스트(unit/integration/e2e)에 공통 적용된다.
E2E 전용 fixture는 tests/e2e/conftest.py 에 별도 정의되어 있다.

RETRO-01: pre-flight 체크 자동화 (2026-03-29)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Pre-flight check fixture (RETRO-01)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=False)
def preflight_check():
    """세션 레벨 pre-flight 인프라 검증 fixture.

    E2E 실행 전 timeout/filter/env 파라미터를 검증한다.
    개별 테스트에서 명시적으로 요청 시 결과 dict를 반환한다.

    사용 예::

        def test_something(preflight_check):
            assert preflight_check["passed"], preflight_check["errors"]

    SKIP_PREFLIGHT=1 환경변수로 우회 가능 (CI 디버깅 한정).

    Returns
    -------
    dict
        {
            "passed": bool,
            "timeout": {"ok": bool, "msg": str, "value": int | None},
            "filter":  {"ok": bool, "msg": str, "value": str | None},
            "env":     {"ok": bool, "missing_required": list, "missing_optional": list},
            "errors":  list[str],
        }
    """
    if os.environ.get("SKIP_PREFLIGHT", "").lower() in ("1", "true", "yes"):
        return {
            "passed": True,
            "skipped": True,
            "errors": [],
            "timeout": {},
            "filter": {},
            "env": {},
        }

    _here = Path(__file__).parent
    _e2e_preflight_mod = _here / "e2e" / "preflight_check.py"

    if not _e2e_preflight_mod.exists():
        pytest.skip(f"preflight_check.py 없음: {_e2e_preflight_mod}")

    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("e2e_preflight", _e2e_preflight_mod)
    if spec is None or spec.loader is None:
        pytest.skip("preflight_check.py 로드 실패")

    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    result: dict[str, Any] = mod.run_preflight_checks(exit_on_fail=False)

    if not result.get("passed", True):
        errors = result.get("errors", [])
        _missing_required = (result.get("env") or {}).get("missing_required", [])
        if _missing_required:
            # 필수 환경변수 누락 — pytest.fail로 명확한 메시지 제공
            missing_str = ", ".join(_missing_required)
            pytest.fail(
                f"Pre-flight check failed: 필수 환경변수 누락 — {missing_str}\n"
                "힌트: cp .env.example .env 후 값 설정\n"
                "우회: SKIP_PREFLIGHT=1",
                pytrace=False,
            )
        elif errors:
            pytest.fail(
                "Pre-flight check failed:\n" + "\n".join(f"  - {e}" for e in errors),
                pytrace=False,
            )

    return result
