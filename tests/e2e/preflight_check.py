"""tests/e2e/preflight_check.py — E2E 테스트 전용 pre-flight 검증 모듈.

tools/preflight_check.py 의 핵심 검증 로직을 재사용하되,
테스트 프레임워크에 친화적인 dict 반환 인터페이스를 제공한다.

반환 dict 스키마:
    {
        "passed": bool,
        "timeout": {"ok": bool, "msg": str, "value": int | None},
        "filter":  {"ok": bool, "msg": str, "value": str | None},
        "env":     {"ok": bool, "missing_required": list[str], "missing_optional": list[str]},
        "errors":  list[str],
    }

사용:
    from tests.e2e.preflight_check import run_preflight_checks
    results = run_preflight_checks()       # 실패 시 sys.exit(1)
    results = run_preflight_checks(exit_on_fail=False)  # 실패해도 계속
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 기본 경로
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DEFAULT_BASELINE = _PROJECT_ROOT / "infra-baseline.yaml"

# ---------------------------------------------------------------------------
# YAML 로더 (PyYAML 없을 때 간이 fallback)
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict[str, Any]:
    """YAML → dict. PyYAML 없으면 간이 파서 사용."""
    try:
        import yaml  # type: ignore[import-untyped]
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ImportError:
        pass

    result: dict[str, Any] = {}
    current_section: dict[str, Any] | None = None
    current_key: str | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line.startswith("  - "):
            item = stripped.lstrip("- ").split("#")[0].strip()
            if isinstance(current_section, dict) and current_key:
                lst = current_section.setdefault(current_key, [])
                if isinstance(lst, list):
                    lst.append(item)
            continue
        if ":" in stripped:
            key, _, raw_val = stripped.partition(":")
            key = key.strip()
            val_str = raw_val.split("#")[0].strip().strip('"').strip("'")
            if line.startswith("  "):
                if isinstance(current_section, dict):
                    if val_str == "":
                        current_section[key] = {}
                        current_key = key
                    elif val_str.lstrip("-").isdigit():
                        current_section[key] = int(val_str)
                    else:
                        current_section[key] = val_str
            else:
                if val_str == "":
                    result[key] = {}
                    current_section = result[key]  # type: ignore[assignment]
                    current_key = None
                elif val_str.lstrip("-").isdigit():
                    result[key] = int(val_str)
                    current_section = None
                else:
                    result[key] = val_str
                    current_section = None
    return result


# ---------------------------------------------------------------------------
# 개별 검증 함수
# ---------------------------------------------------------------------------

_DEFAULT_TIMEOUT = 120
_WARN_DEFAULT_TIMEOUT = True  # 기본값 사용 시 경고 출력 여부


def _check_timeout(timeout: Any) -> dict[str, Any]:
    """timeout 검증. 0보다 큰 정수여야 한다."""
    try:
        val = int(timeout)
    except (TypeError, ValueError):
        return {"ok": False, "msg": f"timeout 값이 정수가 아닙니다: {timeout!r}", "value": None}
    if val <= 0:
        return {"ok": False, "msg": f"timeout 값이 0 이하입니다: {val}", "value": val}
    if val == _DEFAULT_TIMEOUT and _WARN_DEFAULT_TIMEOUT:
        import warnings
        warnings.warn(
            f"[pre-flight] timeout={val}s 는 기본값입니다. "
            "infra-baseline.yaml에서 명시적으로 설정했는지 확인하세요.",
            stacklevel=4,
        )
    return {"ok": True, "msg": f"timeout={val}s ✔", "value": val}


def _check_filter(filter_val: Any) -> dict[str, Any]:
    """filter 패턴 검증."""
    if filter_val is None or filter_val == "":
        return {"ok": True, "msg": "filter=<없음> (전체 실행) ✔", "value": ""}
    if not isinstance(filter_val, str):
        return {
            "ok": False,
            "msg": f"filter 값이 문자열이 아닙니다: {type(filter_val).__name__}",
            "value": None,
        }
    if re.search(r"[;&|`$]", filter_val):
        return {
            "ok": False,
            "msg": f"filter 패턴에 허용되지 않는 문자가 포함됩니다: {filter_val!r}",
            "value": filter_val,
        }
    return {"ok": True, "msg": f"filter={filter_val!r} ✔", "value": filter_val}


def _check_env(required: list[str], optional: list[str]) -> dict[str, Any]:
    """환경변수 검증. required 누락 시 errors에 추가."""
    missing_required: list[str] = []
    missing_optional: list[str] = []

    for var in required:
        if not os.environ.get(var, ""):
            missing_required.append(var)

    for var in optional:
        if not os.environ.get(var, ""):
            missing_optional.append(var)

    ok = len(missing_required) == 0
    msg = "env ✔" if ok else f"필수 환경변수 누락: {missing_required}"
    return {
        "ok": ok,
        "msg": msg,
        "missing_required": missing_required,
        "missing_optional": missing_optional,
    }


# ---------------------------------------------------------------------------
# 메인 public 함수
# ---------------------------------------------------------------------------

def run_preflight_checks(
    baseline_path: Path | None = None,
    *,
    exit_on_fail: bool = True,
    quiet: bool = False,
) -> dict[str, Any]:
    """E2E pre-flight 검증 실행.

    Parameters
    ----------
    baseline_path:
        infra-baseline.yaml 경로. None이면 프로젝트 루트 기본값 사용.
    exit_on_fail:
        True(기본)이면 실패 항목이 있을 때 sys.exit(1) 호출.
        False이면 실패해도 dict를 반환하고 계속 진행.
    quiet:
        True이면 통과 항목 출력 억제.

    Returns
    -------
    dict
        검증 결과 dict:
        {
            "passed": bool,
            "timeout": {...},
            "filter": {...},
            "env": {...},
            "errors": [str, ...],
        }
    """
    path = baseline_path or _DEFAULT_BASELINE

    # baseline 파일 로드
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = _load_yaml(path)
        except Exception as exc:  # noqa: BLE001
            _err(f"infra-baseline.yaml 파싱 실패: {exc}")
            if exit_on_fail:
                sys.exit(1)
            return {"passed": False, "errors": [str(exc)], "timeout": {}, "filter": {}, "env": {}}
    else:
        _warn(f"infra-baseline.yaml 없음: {path} — 기본값으로 계속")

    version = data.get("version", "unknown")
    timeout_val = data.get("timeout", _DEFAULT_TIMEOUT)
    filter_val = data.get("filter", "")
    env_section = data.get("env", {})
    required_env: list[str] = (
        env_section.get("required", []) if isinstance(env_section, dict) else []
    )
    optional_env: list[str] = (
        env_section.get("optional", []) if isinstance(env_section, dict) else []
    )

    # --- 개별 검증 ---
    t_result = _check_timeout(timeout_val)
    f_result = _check_filter(filter_val)
    e_result = _check_env(required_env, optional_env)

    if not quiet:
        _log(f"  [1/3] timeout : {t_result['msg']}")
        _log(f"  [2/3] filter  : {f_result['msg']}")
        if e_result["ok"]:
            _log(f"  [3/3] env     : {e_result['msg']}")
        else:
            _err(f"  [3/3] env     : ✗ {e_result['msg']}")
        for opt in e_result.get("missing_optional", []):
            _warn(f"  [3/3] env     : ⚠ 선택 환경변수 없음: {opt}")

    errors: list[str] = []
    if not t_result["ok"]:
        errors.append(t_result["msg"])
    if not f_result["ok"]:
        errors.append(f_result["msg"])
    if not e_result["ok"]:
        errors.extend([f"필수 환경변수 누락: {v}" for v in e_result["missing_required"]])

    passed = len(errors) == 0

    if passed:
        _log(f"✅ pre-flight OK — baseline version: {version}")
    else:
        _err(f"❌ pre-flight FAILED — baseline version: {version}")
        for err in errors:
            _err(f"   → {err}")
        if exit_on_fail:
            sys.exit(1)

    return {
        "passed": passed,
        "timeout": t_result,
        "filter": f_result,
        "env": e_result,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# 출력 헬퍼
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    print(msg, flush=True)


def _warn(msg: str) -> None:
    print(f"[WARN] {msg}", flush=True)


def _err(msg: str) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# CLI 진입점
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("🔍 E2E pre-flight 체크 시작", flush=True)
    run_preflight_checks()
