"""E2E pre-flight 체크 스크립트.

infra-baseline.yaml을 읽어 timeout / filter / env 세 항목을 순서대로 검증한다.
실패 항목이 있으면 에러 메시지와 함께 exit(1)로 종료.
검증 통과 시 "✅ pre-flight OK" 헤더를 출력한다.

사용법:
    python tools/preflight_check.py                        # 기본 (프로젝트 루트 기준)
    python tools/preflight_check.py --baseline /path/to/infra-baseline.yaml
    python tools/preflight_check.py --strict               # optional env도 필수 처리

pytest conftest.py 에서 자동 호출:
    import subprocess, sys
    subprocess.run([sys.executable, "tools/preflight_check.py"], check=True)
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:
    # yaml 없이도 동작하도록 간단한 파서 fallback
    yaml = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# 기본값 (infra-baseline.yaml을 찾지 못할 때 사용)
# ---------------------------------------------------------------------------
_DEFAULT_TIMEOUT = 120
_DEFAULT_FILTER = ""
_DEFAULT_REQUIRED_ENV: list[str] = []
_DEFAULT_OPTIONAL_ENV: list[str] = []

# 프로젝트 루트 기준 기본 baseline 경로
_DEFAULT_BASELINE_PATH = Path(__file__).parent.parent / "infra-baseline.yaml"


# ---------------------------------------------------------------------------
# YAML 로더 (PyYAML 없을 때 간이 fallback)
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict[str, Any]:
    """YAML 파일을 읽어 dict 반환. PyYAML 없으면 간이 파싱."""
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text) or {}
    # 간이 파서: key: value 형태만 지원 (리스트는 '- item' 형식)
    result: dict[str, Any] = {}
    current_section: dict[str, Any] | None = None
    current_key: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line.startswith("  - "):  # 들여쓰기 리스트 항목
            item = stripped.lstrip("- ").split("#")[0].strip()
            if isinstance(current_section, dict) and current_key:
                lst = current_section.setdefault(current_key, [])
                if isinstance(lst, list):
                    lst.append(item)
            continue
        if line.startswith("- "):  # 최상위 리스트 (미사용)
            continue
        if ":" in stripped:
            key, _, raw_val = stripped.partition(":")
            key = key.strip()
            val_str = raw_val.split("#")[0].strip().strip('"').strip("'")
            if line.startswith("  "):
                # 중간 수준 키
                if isinstance(current_section, dict):
                    if val_str == "":
                        current_section[key] = {}
                        current_key = key
                    elif val_str.lstrip("-").isdigit():
                        current_section[key] = int(val_str)
                    else:
                        current_section[key] = val_str
            else:
                # 최상위 키
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
# 검증 함수
# ---------------------------------------------------------------------------

_MIN_E2E_TIMEOUT = 60  # E2E S-P1 기준 최솟값 (infra-baseline.yaml ETC-02 반영)


def _check_timeout(timeout: Any) -> tuple[bool, str]:
    """① timeout 값이 0보다 큰 정수이며 E2E 최솟값(60s) 이상인지 검사."""
    try:
        val = int(timeout)
    except (TypeError, ValueError):
        return False, f"timeout 값이 정수가 아닙니다: {timeout!r}"
    if val <= 0:
        return False, f"timeout 값이 0 이하입니다: {val}"
    if val < _MIN_E2E_TIMEOUT:
        return False, (
            f"timeout={val}s 는 E2E 최솟값({_MIN_E2E_TIMEOUT}s) 미만입니다. "
            "infra-baseline.yaml에서 timeout >= 60 으로 올려주세요."
        )
    return True, f"timeout={val}s ✔"


def _check_filter(filter_val: Any) -> tuple[bool, str]:
    """② filter 패턴이 유효한 문자열인지 검사 (None/공백 허용)."""
    if filter_val is None or filter_val == "":
        return True, "filter=<없음> (전체 실행) ✔"
    if not isinstance(filter_val, str):
        return False, f"filter 값이 문자열이 아닙니다: {type(filter_val).__name__}"
    # 기본적인 pytest -k 패턴 문법 검사 (특수문자 과도 사용 방지)
    if re.search(r"[;&|`$]", filter_val):
        return False, f"filter 패턴에 허용되지 않는 문자가 포함되어 있습니다: {filter_val!r}"
    return True, f"filter={filter_val!r} ✔"


def _check_env(
    required: list[str],
    optional: list[str],
    strict: bool = False,
) -> tuple[bool, list[str], list[str]]:
    """③ 필수/선택 env 변수가 os.environ에 존재하는지 검사.

    Returns:
        (passed, errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    for var in required:
        val = os.environ.get(var, "")
        if not val:
            errors.append(f"필수 환경변수 누락: {var}")

    for var in optional:
        val = os.environ.get(var, "")
        if not val:
            if strict:
                errors.append(f"환경변수 누락 (--strict): {var}")
            else:
                warnings.append(f"선택 환경변수 없음 (기능 제한 가능): {var}")

    passed = len(errors) == 0
    return passed, errors, warnings


# ---------------------------------------------------------------------------
# 메인 실행부
# ---------------------------------------------------------------------------

def run_preflight(
    baseline_path: Path | None = None,
    strict: bool = False,
    quiet: bool = False,
) -> bool:
    """pre-flight 검증 실행. 통과하면 True, 실패하면 False 반환."""
    path = baseline_path or _DEFAULT_BASELINE_PATH

    # baseline 파일 로드
    if not path.exists():
        _err(f"infra-baseline.yaml을 찾을 수 없습니다: {path}")
        _err("기본값으로 계속합니다 (timeout=120, filter='', env=[])")
        data: dict[str, Any] = {}
    else:
        try:
            data = _load_yaml(path)
        except Exception as exc:  # noqa: BLE001
            _err(f"infra-baseline.yaml 파싱 실패: {exc}")
            return False

    version = data.get("version", "unknown")
    timeout_val = data.get("timeout", _DEFAULT_TIMEOUT)
    filter_val = data.get("filter", _DEFAULT_FILTER)
    env_section = data.get("env", {})
    required_env: list[str] = env_section.get("required", _DEFAULT_REQUIRED_ENV) if isinstance(env_section, dict) else []
    optional_env: list[str] = env_section.get("optional", _DEFAULT_OPTIONAL_ENV) if isinstance(env_section, dict) else []

    all_passed = True
    issues: list[str] = []

    # ① timeout 검증
    t_ok, t_msg = _check_timeout(timeout_val)
    if not quiet:
        _log(f"  [1/3] timeout   : {t_msg}")
    if not t_ok:
        all_passed = False
        issues.append(t_msg)

    # ② filter 검증
    f_ok, f_msg = _check_filter(filter_val)
    if not quiet:
        _log(f"  [2/3] filter    : {f_msg}")
    if not f_ok:
        all_passed = False
        issues.append(f_msg)

    # ③ env 검증
    e_ok, e_errors, e_warnings = _check_env(required_env, optional_env, strict=strict)
    if not quiet:
        if e_ok:
            required_label = ", ".join(required_env) if required_env else "<없음>"
            _log(f"  [3/3] env       : required={required_label} ✔")
        for warn in e_warnings:
            _warn(f"  [3/3] env       : ⚠ {warn}")
        for err in e_errors:
            _err(f"  [3/3] env       : ✗ {err}")
    if not e_ok:
        all_passed = False
        issues.extend(e_errors)

    # 결과 출력
    ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if all_passed:
        print(
            f"\n✅ pre-flight OK — {ts} / baseline version: {version}",
            flush=True,
        )
    else:
        print(
            f"\n❌ pre-flight FAILED — {ts} / baseline version: {version}",
            file=sys.stderr,
            flush=True,
        )
        for issue in issues:
            print(f"   → {issue}", file=sys.stderr, flush=True)

    return all_passed


def run_preflight_dict(
    baseline_path: Path | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    """pre-flight 검증 결과를 표준 dict 형태로 반환한다.

    RETRO-09/10: pre-flight 체크 결과를 E2E 로그 헤더에 자동 삽입하기 위한
    구조화된 반환 인터페이스를 제공한다.

    Parameters
    ----------
    baseline_path:
        infra-baseline.yaml 경로. None이면 프로젝트 루트 기본값 사용.
    strict:
        True이면 optional 환경변수도 필수로 검사.

    Returns
    -------
    dict
        검증 결과 dict::

            {
                "baseline_version": str,   # yaml 의 version 필드
                "timeout": int,            # yaml 의 timeout 값
                "filter": str,             # yaml 의 filter 값 (없으면 "")
                "env_vars": list[str],     # optional 환경변수 전체 목록
                "checked_at": str,         # ISO8601 타임스탬프 (UTC)
                "status": "PASS" | "FAIL", # 종합 결과
            }

    체크 실패 시 pytest warning 을 발생시키되 테스트를 중단하지 않는다(soft-fail).
    """
    path = baseline_path or _DEFAULT_BASELINE_PATH

    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = _load_yaml(path)
        except Exception as exc:  # noqa: BLE001
            _err(f"infra-baseline.yaml 파싱 실패: {exc}")
            # soft-fail: try/except 가능하도록 dict 반환
            import warnings
            warnings.warn(
                f"[pre-flight] infra-baseline.yaml 파싱 실패: {exc}",
                stacklevel=2,
            )
            return {
                "baseline_version": "unknown",
                "timeout": _DEFAULT_TIMEOUT,
                "filter": _DEFAULT_FILTER,
                "env_vars": [],
                "checked_at": datetime.now(tz=timezone.utc).isoformat(),
                "status": "FAIL",
            }
    else:
        import warnings
        warnings.warn(
            f"[pre-flight] infra-baseline.yaml 없음: {path} — 기본값 사용",
            stacklevel=2,
        )

    version = data.get("baseline_version") or data.get("version", "unknown")
    timeout_val = int(data.get("timeout", _DEFAULT_TIMEOUT))
    filter_val = str(data.get("filter", _DEFAULT_FILTER) or "")
    env_section = data.get("env", {})
    required_env: list[str] = (
        env_section.get("required", _DEFAULT_REQUIRED_ENV)
        if isinstance(env_section, dict)
        else []
    )
    optional_env: list[str] = (
        env_section.get("optional", _DEFAULT_OPTIONAL_ENV)
        if isinstance(env_section, dict)
        else []
    )
    env_vars: list[str] = list(required_env) + list(optional_env)

    t_ok, _ = _check_timeout(timeout_val)
    f_ok, _ = _check_filter(filter_val)
    e_ok, e_errors, _ = _check_env(required_env, optional_env, strict=strict)

    passed = t_ok and f_ok and e_ok
    if not passed:
        import warnings
        issues = []
        if not t_ok:
            issues.append(f"timeout={timeout_val}s 검증 실패")
        if not f_ok:
            issues.append(f"filter={filter_val!r} 검증 실패")
        if not e_ok:
            issues.extend(e_errors)
        warnings.warn(
            "[pre-flight] 검증 실패 (soft-fail): " + "; ".join(issues),
            stacklevel=2,
        )

    return {
        "baseline_version": str(version),
        "timeout": timeout_val,
        "filter": filter_val,
        "env_vars": env_vars,
        "checked_at": datetime.now(tz=timezone.utc).isoformat(),
        "status": "PASS" if passed else "FAIL",
    }


def _log(msg: str) -> None:
    print(msg, flush=True)


def _warn(msg: str) -> None:
    print(f"[WARN] {msg}", flush=True)


def _err(msg: str) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# CLI 진입점
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="E2E pre-flight 체크: infra-baseline.yaml 기반 환경 유효성 검사"
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=None,
        help="infra-baseline.yaml 경로 (기본: 프로젝트 루트)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="optional 환경변수도 필수로 검사",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="통과 항목 출력 억제 (실패만 출력)",
    )
    args = parser.parse_args()

    print("🔍 E2E pre-flight 체크 시작", flush=True)
    passed = run_preflight(
        baseline_path=args.baseline,
        strict=args.strict,
        quiet=args.quiet,
    )
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
