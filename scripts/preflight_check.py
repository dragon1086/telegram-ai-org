"""scripts/preflight_check.py — E2E 실행 전 인프라 검증 스크립트 (Python 버전).

사용법:
    .venv/bin/python scripts/preflight_check.py           # 기본 실행
    .venv/bin/python scripts/preflight_check.py --json    # JSON 출력
    .venv/bin/python scripts/preflight_check.py --quiet   # PASS 항목 숨김

출력 형식 (JSON):
    {
        "status": "PASS" | "WARN" | "FAIL",
        "checks": [
            {"name": str, "status": "PASS"|"WARN"|"FAIL", "detail": str},
            ...
        ],
        "summary": str,
        "timestamp": str,
        "baseline_version": str
    }

종료 코드:
    0 — PASS 또는 WARN
    1 — FAIL

RETRO-01: pre-flight 체크 자동화 (2026-03-27)
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 프로젝트 루트
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).parent
_PROJECT_ROOT = _SCRIPT_DIR.parent

# ---------------------------------------------------------------------------
# 체크 결과 헬퍼
# ---------------------------------------------------------------------------

CheckStatus = str  # "PASS" | "WARN" | "FAIL"


def _check_result(name: str, status: CheckStatus, detail: str) -> dict[str, Any]:
    return {"name": name, "status": status, "detail": detail}


# ---------------------------------------------------------------------------
# CHECK 1: Python venv
# ---------------------------------------------------------------------------

def check_venv() -> list[dict[str, Any]]:
    """Python venv 존재 및 활성화 여부."""
    results = []
    venv_path = _PROJECT_ROOT / ".venv"

    if venv_path.exists():
        results.append(_check_result("venv_exists", "PASS", f"venv 존재: {venv_path}"))
    else:
        results.append(_check_result(
            "venv_exists", "FAIL",
            f"venv 없음: {venv_path} — 'python -m venv .venv && .venv/bin/pip install -e .' 실행 필요"
        ))

    python_bin = venv_path / "bin" / "python"
    if python_bin.exists():
        try:
            ver = subprocess.check_output(
                [str(python_bin), "--version"], stderr=subprocess.STDOUT, text=True
            ).strip()
            results.append(_check_result("venv_python_executable", "PASS", f"Python 실행 가능: {ver}"))
        except Exception as exc:
            results.append(_check_result("venv_python_executable", "FAIL", f"Python 실행 실패: {exc}"))
    else:
        results.append(_check_result(
            "venv_python_executable", "FAIL",
            f"Python 바이너리 없음: {python_bin}"
        ))

    virtual_env = os.environ.get("VIRTUAL_ENV", "")
    if virtual_env:
        results.append(_check_result("venv_activated", "PASS", f"venv 활성화됨: {virtual_env}"))
    else:
        results.append(_check_result(
            "venv_activated", "WARN",
            "venv 미활성화 — 'source .venv/bin/activate' 권장 (실행은 가능)"
        ))

    return results


# ---------------------------------------------------------------------------
# CHECK 2: 필수 환경변수
# ---------------------------------------------------------------------------

_REQUIRED_VARS = [
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_GROUP_CHAT_ID",
]
_API_KEY_VARS = [
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
]


def _load_dotenv(env_path: Path) -> dict[str, str]:
    """간이 .env 파서 (python-dotenv 없어도 동작)."""
    result: dict[str, str] = {}
    if not env_path.exists():
        return result
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and val:
                result[key] = val
    return result


def check_env_vars() -> list[dict[str, Any]]:
    """필수/선택 환경변수 존재 확인."""
    results = []

    # .env 로드 (os.environ에 없으면 .env 파일에서 보완)
    env_file = _PROJECT_ROOT / ".env"
    if env_file.exists():
        dotenv_vals = _load_dotenv(env_file)
        for k, v in dotenv_vals.items():
            if k not in os.environ:
                os.environ[k] = v
        results.append(_check_result("dotenv_loaded", "PASS", f".env 로드됨: {env_file}"))
    else:
        results.append(_check_result(
            "dotenv_loaded", "WARN",
            f".env 파일 없음: {env_file} — 'cp .env.example .env' 후 값 설정 필요"
        ))

    for var in _REQUIRED_VARS:
        val = os.environ.get(var, "")
        if val:
            masked = val[:4] + "****"
            results.append(_check_result(f"env_{var}", "PASS", f"{var} 설정됨 ({masked}...)"))
        else:
            results.append(_check_result(
                f"env_{var}", "FAIL",
                f"{var} 미설정 — .env 파일 확인 필요"
            ))

    api_set = any(os.environ.get(v, "") for v in _API_KEY_VARS)
    if api_set:
        set_var = next(v for v in _API_KEY_VARS if os.environ.get(v, ""))
        results.append(_check_result(
            "env_api_key", "PASS",
            f"API 키 설정됨: {set_var}"
        ))
    else:
        results.append(_check_result(
            "env_api_key", "FAIL",
            f"API 키 없음 — {'/'.join(_API_KEY_VARS[:2])} 중 하나 이상 필요"
        ))

    return results


# ---------------------------------------------------------------------------
# CHECK 3: DB 파일
# ---------------------------------------------------------------------------

def check_db_files() -> list[dict[str, Any]]:
    """데이터베이스 파일 존재 확인."""
    results = []
    db_files = ["ai_org.db", "tasks.db"]
    optional_db = ["logs/tasks.db"]

    for db in db_files:
        path = _PROJECT_ROOT / db
        if path.exists():
            size = path.stat().st_size
            results.append(_check_result(
                f"db_{db.replace('/', '_')}", "PASS",
                f"{db} 존재 ({size:,} bytes)"
            ))
        else:
            results.append(_check_result(
                f"db_{db.replace('/', '_')}", "WARN",
                f"{db} 없음 — 첫 실행 시 자동 생성됩니다"
            ))

    for db in optional_db:
        path = _PROJECT_ROOT / db
        if path.exists():
            results.append(_check_result(f"db_optional_{db.replace('/', '_')}", "PASS", f"{db} 존재 (선택)"))
        else:
            results.append(_check_result(
                f"db_optional_{db.replace('/', '_')}", "WARN",
                f"{db} 없음 (선택 파일 — 영향 없음)"
            ))

    return results


# ---------------------------------------------------------------------------
# CHECK 4: 핵심 설정 파일
# ---------------------------------------------------------------------------

def check_config_files() -> list[dict[str, Any]]:
    """핵심 설정 파일 존재 확인."""
    results = []
    required_configs = [
        "orchestration.yaml",
        "organizations.yaml",
        "workers.yaml",
        "agent_hints.yaml",
    ]

    for cfg in required_configs:
        path = _PROJECT_ROOT / cfg
        if path.exists():
            results.append(_check_result(f"config_{cfg}", "PASS", f"{cfg} 존재"))
        else:
            results.append(_check_result(f"config_{cfg}", "FAIL", f"{cfg} 없음 — 설정 파일 누락"))

    config_dir = _PROJECT_ROOT / "config"
    if config_dir.exists():
        yaml_files = list(config_dir.glob("*.yaml")) + list(config_dir.glob("*.json"))
        results.append(_check_result(
            "config_dir",
            "PASS" if yaml_files else "WARN",
            f"config/ 디렉토리: {len(yaml_files)}개 설정 파일"
        ))
    else:
        results.append(_check_result("config_dir", "WARN", "config/ 디렉토리 없음 (선택)"))

    return results


# ---------------------------------------------------------------------------
# CHECK 5: infra-baseline.yaml
# ---------------------------------------------------------------------------

def check_infra_baseline() -> list[dict[str, Any]]:
    """infra-baseline.yaml 존재 및 버전 확인."""
    baseline = _PROJECT_ROOT / "infra-baseline.yaml"
    if baseline.exists():
        content = baseline.read_text(encoding="utf-8")
        version_match = re.search(r"^version:\s*(.+)$", content, re.MULTILINE)
        version = version_match.group(1).strip() if version_match else "unknown"
        return [_check_result(
            "infra_baseline", "PASS",
            f"infra-baseline.yaml 존재 (version: {version})"
        )]
    else:
        return [_check_result(
            "infra_baseline", "FAIL",
            "infra-baseline.yaml 없음 — 인프라 파라미터 기준 미정의 (RETRO-03 참조)"
        )]


# ---------------------------------------------------------------------------
# CHECK 6: Deprecated 모델 탐지
# ---------------------------------------------------------------------------

_DEPRECATED_MODEL = "gemini-2.0-flash"
_SCAN_DIRS = ["core", "scripts", "bots", "tools"]
_SCAN_FILES = ["main.py", "cli.py"]


def check_deprecated_models() -> list[dict[str, Any]]:
    """프로덕션 코드에서 deprecated 모델 버전 탐지."""
    hits: list[str] = []

    def _scan_file(path: Path) -> None:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(content.splitlines(), 1):
                if _DEPRECATED_MODEL in line:
                    hits.append(f"{path.relative_to(_PROJECT_ROOT)}:{i}: {line.strip()}")
        except Exception:
            pass

    # Exclude this script itself from the scan (it contains the pattern as a literal)
    _self_path = Path(__file__).resolve()

    for d in _SCAN_DIRS:
        dir_path = _PROJECT_ROOT / d
        if dir_path.exists():
            for py_file in dir_path.rglob("*.py"):
                if "__pycache__" not in str(py_file) and py_file.resolve() != _self_path:
                    _scan_file(py_file)

    for f in _SCAN_FILES:
        file_path = _PROJECT_ROOT / f
        if file_path.exists():
            _scan_file(file_path)

    if not hits:
        return [_check_result(
            "deprecated_model", "PASS",
            f"프로덕션 코드에 {_DEPRECATED_MODEL} 없음"
        )]
    else:
        sample = "; ".join(hits[:3])
        return [_check_result(
            "deprecated_model", "FAIL",
            f"Deprecated 모델 {len(hits)}건 발견 ({_DEPRECATED_MODEL}) — gemini-2.5-flash로 교체 필요. 예: {sample}"
        )]


# ---------------------------------------------------------------------------
# CHECK 7: TelegramRelay import
# ---------------------------------------------------------------------------

def check_import() -> list[dict[str, Any]]:
    """핵심 모듈 import 테스트."""
    results = []

    modules_to_check = [
        ("core.telegram_relay", "TelegramRelay"),
        ("core.env_guard", None),
        ("core.bot_commands", None),
    ]

    for mod_name, attr in modules_to_check:
        try:
            mod_path = _PROJECT_ROOT / mod_name.replace(".", "/")
            # .py 파일로 직접 로드 (sys.path 오염 방지)
            py_path = Path(str(mod_path) + ".py")
            spec = importlib.util.spec_from_file_location(mod_name, py_path)
            if spec is None or spec.loader is None:
                raise ImportError(f"spec 로드 실패: {py_path}")
            # import 가능 여부만 확인 (실제 exec는 부작용 가능성 있어 생략)
            if py_path.exists():
                results.append(_check_result(
                    f"import_{mod_name.replace('.', '_')}",
                    "PASS",
                    f"{mod_name} 파일 존재 ({py_path.name})"
                ))
            else:
                results.append(_check_result(
                    f"import_{mod_name.replace('.', '_')}",
                    "FAIL",
                    f"{mod_name} 파일 없음: {py_path}"
                ))
        except Exception as exc:
            results.append(_check_result(
                f"import_{mod_name.replace('.', '_')}",
                "WARN",
                f"{mod_name} 체크 실패: {exc}"
            ))

    # subprocess로 실제 import 검증 (가장 확실한 방법)
    venv_python = _PROJECT_ROOT / ".venv" / "bin" / "python"
    if venv_python.exists():
        try:
            proc = subprocess.run(
                [str(venv_python), "-c", "from core.telegram_relay import TelegramRelay; print('ok')"],
                cwd=str(_PROJECT_ROOT),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode == 0 and "ok" in proc.stdout:
                results.append(_check_result(
                    "import_telegram_relay_runtime",
                    "PASS",
                    "core.telegram_relay.TelegramRelay runtime import OK"
                ))
            else:
                err = (proc.stderr or proc.stdout)[:200]
                results.append(_check_result(
                    "import_telegram_relay_runtime",
                    "FAIL",
                    f"TelegramRelay import 실패: {err}"
                ))
        except subprocess.TimeoutExpired:
            results.append(_check_result(
                "import_telegram_relay_runtime", "WARN",
                "import 테스트 timeout (10s)"
            ))
        except Exception as exc:
            results.append(_check_result(
                "import_telegram_relay_runtime", "WARN",
                f"import 테스트 실행 실패: {exc}"
            ))

    return results


# ---------------------------------------------------------------------------
# CHECK 8: Ruff lint
# ---------------------------------------------------------------------------

def check_ruff() -> list[dict[str, Any]]:
    """Ruff lint 체크 (core/ 디렉토리)."""
    venv_python = _PROJECT_ROOT / ".venv" / "bin" / "python"
    core_dir = _PROJECT_ROOT / "core"

    if not core_dir.exists():
        return [_check_result("ruff_lint", "WARN", "core/ 디렉토리 없음")]

    if not venv_python.exists():
        return [_check_result("ruff_lint", "WARN", "venv Python 없음 — ruff 실행 불가")]

    try:
        # ruff 설치 확인
        ver_proc = subprocess.run(
            [str(venv_python), "-m", "ruff", "--version"],
            capture_output=True, text=True, timeout=10
        )
        if ver_proc.returncode != 0:
            return [_check_result("ruff_lint", "WARN", "ruff 미설치 — '.venv/bin/pip install ruff' 권장")]

        # lint 실행
        lint_proc = subprocess.run(
            [str(venv_python), "-m", "ruff", "check", str(core_dir), "--quiet"],
            capture_output=True, text=True, timeout=30
        )
        if lint_proc.returncode == 0:
            return [_check_result("ruff_lint", "PASS", "ruff check core/ — 린트 이슈 없음")]
        else:
            issue_lines = [line for line in lint_proc.stdout.splitlines() if line.strip()]
            count = len(issue_lines)
            return [_check_result(
                "ruff_lint", "WARN",
                f"ruff 린트 이슈 {count}건 — 'ruff check core/' 직접 실행하여 확인"
            )]
    except subprocess.TimeoutExpired:
        return [_check_result("ruff_lint", "WARN", "ruff 실행 timeout (30s)")]
    except Exception as exc:
        return [_check_result("ruff_lint", "WARN", f"ruff 실행 오류: {exc}")]


# ---------------------------------------------------------------------------
# 전체 검증 실행
# ---------------------------------------------------------------------------

def run_all_checks() -> dict[str, Any]:
    """모든 pre-flight 체크를 실행하고 결과를 반환한다."""
    all_checks: list[dict[str, Any]] = []

    check_funcs = [
        ("Python venv", check_venv),
        ("환경변수", check_env_vars),
        ("DB 파일", check_db_files),
        ("설정 파일", check_config_files),
        ("infra-baseline.yaml", check_infra_baseline),
        ("Deprecated 모델", check_deprecated_models),
        ("모듈 import", check_import),
        ("Ruff lint", check_ruff),
    ]

    for _section, func in check_funcs:
        results = func()
        all_checks.extend(results)

    fail_count = sum(1 for c in all_checks if c["status"] == "FAIL")
    warn_count = sum(1 for c in all_checks if c["status"] == "WARN")
    pass_count = sum(1 for c in all_checks if c["status"] == "PASS")

    if fail_count > 0:
        overall = "FAIL"
    elif warn_count > 0:
        overall = "WARN"
    else:
        overall = "PASS"

    # baseline version
    baseline = _PROJECT_ROOT / "infra-baseline.yaml"
    baseline_version = "unknown"
    if baseline.exists():
        m = re.search(r"^version:\s*(.+)$", baseline.read_text(), re.MULTILINE)
        if m:
            baseline_version = m.group(1).strip()

    summary = (
        f"PASS:{pass_count} WARN:{warn_count} FAIL:{fail_count} — "
        f"baseline={baseline_version}"
    )

    return {
        "status": overall,
        "checks": all_checks,
        "summary": summary,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "baseline_version": baseline_version,
    }


# ---------------------------------------------------------------------------
# CLI 출력
# ---------------------------------------------------------------------------

_COLORS = {
    "PASS": "\033[0;32m",
    "WARN": "\033[1;33m",
    "FAIL": "\033[0;31m",
    "RESET": "\033[0m",
    "CYAN": "\033[0;36m",
    "DIM": "\033[2m",
}


def _colored(text: str, color: str) -> str:
    if not sys.stdout.isatty():
        return text
    c = _COLORS.get(color, "")
    reset = _COLORS["RESET"]
    return f"{c}{text}{reset}"


def print_results(result: dict[str, Any], quiet: bool = False) -> None:
    """체크 결과를 사람이 읽기 좋은 형태로 출력한다."""
    print(f"\n{_colored('╔══════════════════════════════════════════════════╗', 'CYAN')}")
    print(f"{_colored('║  telegram-ai-org  Pre-Flight Check (Python)      ║', 'CYAN')}")
    print(f"{_colored('║  ' + result['timestamp'] + '                        ║', 'CYAN')}")
    print(f"{_colored('╚══════════════════════════════════════════════════╝', 'CYAN')}")

    current_section = ""
    for check in result["checks"]:
        name = check["name"]
        status = check["status"]
        detail = check["detail"]

        # 섹션 헤더 (이름 접두어 기준)
        section = name.split("_")[0]
        if section != current_section:
            current_section = section

        if quiet and status == "PASS":
            continue

        color = status
        tag = f"[{status}]".ljust(6)
        print(f"  {_colored(tag, color)}  {detail}")

    print(f"\n{_colored('════════════════════════════════════════════════════', 'CYAN')}")
    overall = result["status"]
    print(f"  {_colored(result['summary'], overall)}")

    if overall == "FAIL":
        print(f"  {_colored('STATUS: FAIL — 위 FAIL 항목 해결 후 재실행', 'FAIL')}")
    elif overall == "WARN":
        print(f"  {_colored('STATUS: WARN — 실행 가능하나 위 경고 항목 확인 권장', 'WARN')}")
    else:
        print(f"  {_colored('STATUS: PASS — 모든 체크 통과', 'PASS')}")

    print(f"{_colored('════════════════════════════════════════════════════', 'CYAN')}\n")


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    use_json = "--json" in sys.argv
    quiet = "--quiet" in sys.argv

    result = run_all_checks()

    if use_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_results(result, quiet=quiet)

    sys.exit(0 if result["status"] in ("PASS", "WARN") else 1)
