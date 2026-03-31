"""E2E 테스트 공통 fixture."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.agent_persona_memory import AgentPersonaMemory  # noqa: E402
from core.collaboration_tracker import CollaborationTracker  # noqa: E402
from core.pm_orchestrator import PMOrchestrator  # noqa: E402
from core.shoutout_system import ShoutoutSystem  # noqa: E402
from tools.base_runner import RunContext  # noqa: E402


# ---------------------------------------------------------------------------
# E2E pre-flight 체크 — pytest 세션 시작 전 자동 실행
# infra-baseline.yaml 기반으로 timeout/filter/env 환경 유효성을 검사한다.
# SKIP_PREFLIGHT=1 로 건너뛸 수 있다 (CI 디버깅 등 특수 상황 한정).
# ---------------------------------------------------------------------------
def _print_preflight_header(result: dict) -> None:
    """pre-flight 체크 결과를 E2E 로그 최상단 헤더 블록으로 출력한다.

    출력 형식 (RETRO-09/10/22)::

        ╔══════════════════════════════════════════╗
        ║          === PRE-FLIGHT CHECK ===         ║
        ╚══════════════════════════════════════════╝
        baseline_version : v1.2
        timeout          : 120s
        filter           : <없음>
        env_vars         : [TELEGRAM_BOT_TOKEN, ...]
        checked_at       : 2026-03-29T00:00:00+00:00
        status           : PASS
        blocked          : false
        ─────────────────────────────────────────────
    """
    sep = "=" * 50
    thin = "-" * 50
    env_vars = result.get("env_vars", [])
    env_display = (
        ", ".join(env_vars[:5]) + ("..." if len(env_vars) > 5 else "")
        if env_vars
        else "<없음>"
    )
    filter_display = result.get("filter") or "<없음>"
    status = result.get("status", "UNKNOWN")
    status_icon = "✅ PASS" if status == "PASS" else "❌ FAIL"
    # RETRO-22: blocked 필드 — pre-flight 미통과 시 배포 차단 여부를 명시적으로 기록
    blocked = result.get("blocked", status != "PASS")
    blocked_display = "true ⛔" if blocked else "false ✅"

    print(f"\n{sep}", flush=True)
    print("=== PRE-FLIGHT CHECK ===", flush=True)
    print(sep, flush=True)
    print(f"  baseline_version : {result.get('baseline_version', 'unknown')}", flush=True)
    print(f"  timeout          : {result.get('timeout', '?')}s", flush=True)
    print(f"  filter           : {filter_display}", flush=True)
    print(f"  env_vars         : [{env_display}]", flush=True)
    print(f"  checked_at       : {result.get('checked_at', '?')}", flush=True)
    print(f"  status           : {status_icon}", flush=True)
    print(f"  blocked          : {blocked_display}", flush=True)
    print(f"{thin}\n", flush=True)


def _run_preflight() -> None:
    if os.environ.get("SKIP_PREFLIGHT", "").lower() in ("1", "true", "yes"):
        print("[pre-flight] SKIP_PREFLIGHT=1 — 체크 생략", flush=True)
        return

    # tests/e2e/preflight_check.py 모듈 방식 우선 사용
    _here = Path(__file__).parent
    _preflight_mod = _here / "preflight_check.py"
    if _preflight_mod.exists():
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location("e2e_preflight", _preflight_mod)
        if spec and spec.loader:
            mod = _ilu.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            # exit_on_fail=False 로 결과 dict 를 받아 헤더 출력 후 실패 처리
            result = mod.run_preflight_checks(exit_on_fail=False)
            # --- E2E 로그 헤더 자동 삽입 (RETRO-09/10) ---
            # run_preflight_checks 반환값을 run_preflight_dict 형식으로 변환
            # baseline_version: infra-baseline.yaml 직접 읽어서 정확히 반영 (버그 수정 RETRO-10)
            _baseline_version = "unknown"
            try:
                import yaml as _yaml_bv
                _bv_path = Path(__file__).parent.parent.parent / "infra-baseline.yaml"
                if _bv_path.exists():
                    _bv_data = _yaml_bv.safe_load(_bv_path.read_text(encoding="utf-8")) or {}
                    _baseline_version = (
                        _bv_data.get("baseline_version") or _bv_data.get("version", "unknown")
                    )
            except Exception:  # noqa: BLE001
                pass
            _preflight_passed = result.get("passed", False)
            header_result = {
                "baseline_version": _baseline_version,
                "timeout": (result.get("timeout") or {}).get("value", 120),
                "filter": (result.get("filter") or {}).get("value", ""),
                "env_vars": (result.get("env") or {}).get("missing_optional", []),
                "checked_at": __import__("datetime").datetime.now(
                    __import__("datetime").timezone.utc
                ).isoformat(),
                "status": "PASS" if _preflight_passed else "FAIL",
                # RETRO-22: blocked — pre-flight 미통과 시 배포 차단 여부 명시
                "blocked": not _preflight_passed,
            }
            # tools/preflight_check.py 가 있으면 더 정확한 값으로 덮어쓴다
            _project_root = Path(__file__).parent.parent.parent
            _tools_preflight = _project_root / "tools" / "preflight_check.py"
            if _tools_preflight.exists():
                try:
                    import importlib.util as _ilu2
                    spec2 = _ilu2.spec_from_file_location("tools_preflight", _tools_preflight)
                    if spec2 and spec2.loader:
                        mod2 = _ilu2.module_from_spec(spec2)
                        spec2.loader.exec_module(mod2)  # type: ignore[union-attr]
                        rich = mod2.run_preflight_dict()
                        header_result.update({
                            "baseline_version": rich.get("baseline_version", header_result["baseline_version"]),
                            "timeout": rich.get("timeout", header_result["timeout"]),
                            "filter": rich.get("filter", header_result["filter"]),
                            "env_vars": rich.get("env_vars", header_result["env_vars"]),
                            "checked_at": rich.get("checked_at", header_result["checked_at"]),
                        })
                except Exception:  # noqa: BLE001
                    pass  # tools 버전 로드 실패해도 계속
            _print_preflight_header(header_result)
            # --- E2E 로그 파일에 헤더 저장 (RETRO-10) ---
            # logs/ 디렉토리가 없으면 자동 생성
            _logs_dir = Path(__file__).parent.parent.parent / "logs"
            _logs_dir.mkdir(parents=True, exist_ok=True)
            _log_path = _logs_dir / "e2e_preflight_latest.log"
            try:
                import datetime as _dt
                _ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
                _sep = "=" * 50
                _thin = "-" * 50
                _env_vars = header_result.get("env_vars", [])
                _env_display = (
                    ", ".join(_env_vars[:5]) + ("..." if len(_env_vars) > 5 else "")
                    if _env_vars else "<없음>"
                )
                _status = header_result.get("status", "UNKNOWN")
                _blocked = header_result.get("blocked", _status != "PASS")
                _lines = [
                    f"\n{_sep}",
                    "=== PRE-FLIGHT CHECK ===",
                    _sep,
                    f"  baseline_version : {header_result.get('baseline_version', 'unknown')}",
                    f"  timeout          : {header_result.get('timeout', '?')}s",
                    f"  filter           : {header_result.get('filter') or '<없음>'}",
                    f"  env_vars         : [{_env_display}]",
                    f"  checked_at       : {header_result.get('checked_at', '?')}",
                    f"  status           : {'✅ PASS' if _status == 'PASS' else '❌ FAIL'}",
                    # RETRO-22: blocked 필드 — 배포 차단 여부 명시적 기록
                    f"  blocked          : {'true ⛔' if _blocked else 'false ✅'}",
                    f"{_thin}\n",
                ]
                _log_path.write_text("\n".join(_lines), encoding="utf-8")
                # 타임스탬프 포함 이력 파일도 저장
                _ts_path = _logs_dir / f"e2e_preflight_{_ts}.log"
                _ts_path.write_text("\n".join(_lines), encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass  # 로그 저장 실패는 테스트 실행에 영향 없음
            if not result.get("passed", True):
                raise SystemExit(
                    "❌ E2E pre-flight 실패 — 환경을 점검 후 재실행하세요.\n"
                    "   힌트: SKIP_PREFLIGHT=1 로 일시적으로 우회 가능."
                )
            return

    # fallback: tools/preflight_check.py subprocess 방식
    project_root = Path(__file__).parent.parent.parent
    preflight_script = project_root / "tools" / "preflight_check.py"
    if not preflight_script.exists():
        print(
            f"[pre-flight] 스크립트 없음: {preflight_script} — 체크 생략",
            flush=True,
        )
        return
    proc_result = subprocess.run(
        [sys.executable, str(preflight_script)],
        cwd=str(project_root),
        capture_output=False,
    )
    if proc_result.returncode != 0:
        raise SystemExit(
            "❌ E2E pre-flight 실패 — 환경을 점검 후 재실행하세요.\n"
            f"   스크립트: {preflight_script}\n"
            "   힌트: SKIP_PREFLIGHT=1 로 일시적으로 우회 가능."
        )


_run_preflight()


# ---------------------------------------------------------------------------
# 디자인 pre-flight 체크 — RETRO-11
# design-baseline.yaml 기반 렌더링 환경 유효성을 검사한다.
# SKIP_DESIGN_PREFLIGHT=1 또는 SKIP_PREFLIGHT=1 로 건너뛸 수 있다.
# ---------------------------------------------------------------------------

def _print_design_preflight_header(result: dict) -> None:
    """디자인 pre-flight 결과를 E2E 로그 헤더 블록으로 출력.

    Parameters
    ----------
    result : dict
        {
          "design_baseline_version": "v1.2",
          "viewport": "desktop (1024px)",
          "font": "Pretendard / 16px",
          "base_font_size": 16,
          "theme": "light (WCAG AA, 4.5:1)",
          "wcag_level": "AA",
          "token_version": "v1.0",
          "component_lib_version": "@aiorg/design-system@1.4.2",
          "blocking_pass": 6,
          "blocking_total": 6,
          "warning_pass": 8,
          "warning_total": 8,
          "checked_at": "2026-03-29T00:00:00+00:00",
          "status": "PASS"  # "PASS" | "FAIL" | "SKIP"
        }
    """
    sep = "=" * 50
    thin = "-" * 50

    status = result.get("status", "UNKNOWN")
    if status == "SKIP":
        status_icon = "⏭ SKIP"
    elif status == "PASS":
        status_icon = "✅ PASS"
    else:
        status_icon = "❌ FAIL"

    blocking_pass = result.get("blocking_pass", 0)
    blocking_total = result.get("blocking_total", 0)
    warning_pass = result.get("warning_pass", 0)
    warning_total = result.get("warning_total", 0)

    blocking_icon = "✅ PASS" if blocking_pass == blocking_total else "❌ FAIL"
    warning_icon = "✅ PASS" if warning_pass == warning_total else "⚠ WARN"

    print(f"\n{sep}", flush=True)
    print("=== DESIGN PRE-FLIGHT CHECK ===", flush=True)
    print(sep, flush=True)
    print(f"  design_baseline  : {result.get('design_baseline_version', 'unknown')}", flush=True)
    print(f"  viewport         : {result.get('viewport', '?')}", flush=True)
    print(f"  font             : {result.get('font', '?')}", flush=True)
    print(f"  theme            : {result.get('theme', '?')}", flush=True)
    print(f"  token_version    : {result.get('token_version', '?')}", flush=True)
    print(f"  component_lib    : {result.get('component_lib_version', '?')}", flush=True)
    print(
        f"  blocking_checks  : {blocking_pass} / {blocking_total} {blocking_icon}",
        flush=True,
    )
    print(
        f"  warning_checks   : {warning_pass} / {warning_total} {warning_icon}",
        flush=True,
    )
    print(f"  checked_at       : {result.get('checked_at', '?')}", flush=True)
    print(f"  status           : {status_icon}", flush=True)
    print(f"{thin}\n", flush=True)


def _run_design_preflight() -> None:
    """디자인 pre-flight 체크 실행 및 E2E 로그 헤더 출력 (RETRO-11)."""
    if os.environ.get("SKIP_PREFLIGHT", "").lower() in ("1", "true", "yes"):
        return  # 인프라 체크와 함께 통합 skip 됨
    if os.environ.get("SKIP_DESIGN_PREFLIGHT", "").lower() in ("1", "true", "yes"):
        print("[design pre-flight] SKIP_DESIGN_PREFLIGHT=1 — 체크 생략", flush=True)
        return

    _project_root = Path(__file__).parent.parent.parent
    _design_preflight_mod = _project_root / "tools" / "design_preflight_check.py"

    if not _design_preflight_mod.exists():
        print(
            f"[design pre-flight] 모듈 없음: {_design_preflight_mod} — 체크 생략",
            flush=True,
        )
        return

    try:
        import importlib.util as _ilu_d
        spec_d = _ilu_d.spec_from_file_location("design_preflight_check", _design_preflight_mod)
        if spec_d and spec_d.loader:
            mod_d = _ilu_d.module_from_spec(spec_d)
            spec_d.loader.exec_module(mod_d)  # type: ignore[union-attr]
            check_result = mod_d.run_design_preflight_checks(exit_on_fail=False)
            header_result = mod_d.build_design_preflight_header_result(check_result)
            _print_design_preflight_header(header_result)
            # --- design pre-flight 로그 파일 저장 ---
            _logs_dir = _project_root / "logs"
            _logs_dir.mkdir(parents=True, exist_ok=True)
            try:
                import datetime as _dt_d
                _ts_d = _dt_d.datetime.now(_dt_d.timezone.utc).strftime("%Y%m%d_%H%M%S")
                _sep_d = "=" * 50
                _thin_d = "-" * 50
                _status_d = header_result.get("status", "UNKNOWN")
                _b_pass = header_result.get("blocking_pass", 0)
                _b_total = header_result.get("blocking_total", 0)
                _w_pass = header_result.get("warning_pass", 0)
                _w_total = header_result.get("warning_total", 0)
                _lines_d = [
                    f"\n{_sep_d}",
                    "=== DESIGN PRE-FLIGHT CHECK ===",
                    _sep_d,
                    f"  design_baseline  : {header_result.get('design_baseline_version', 'unknown')}",
                    f"  viewport         : {header_result.get('viewport', '?')}",
                    f"  font             : {header_result.get('font', '?')}",
                    f"  theme            : {header_result.get('theme', '?')}",
                    f"  token_version    : {header_result.get('token_version', '?')}",
                    f"  component_lib    : {header_result.get('component_lib_version', '?')}",
                    f"  blocking_checks  : {_b_pass} / {_b_total}",
                    f"  warning_checks   : {_w_pass} / {_w_total}",
                    f"  checked_at       : {header_result.get('checked_at', '?')}",
                    f"  status           : {'✅ PASS' if _status_d == 'PASS' else '❌ FAIL'}",
                    f"{_thin_d}\n",
                ]
                _log_content = "\n".join(_lines_d)
                (_logs_dir / "e2e_design_preflight_latest.log").write_text(
                    _log_content, encoding="utf-8"
                )
                (_logs_dir / f"e2e_design_preflight_{_ts_d}.log").write_text(
                    _log_content, encoding="utf-8"
                )
            except Exception:  # noqa: BLE001
                pass
            if not check_result.get("passed", True) and not check_result.get("skipped"):
                raise SystemExit(
                    "❌ design pre-flight 실패 — 디자인 환경을 점검 후 재실행하세요.\n"
                    "   힌트: SKIP_DESIGN_PREFLIGHT=1 로 일시적으로 우회 가능."
                )
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(f"[design pre-flight] 체크 중 오류 발생 (비중단): {exc}", flush=True)


_run_design_preflight()


# ---------------------------------------------------------------------------
# Telethon 세션 파일 존재 여부 체크 — E2E 세션 시작 전 자동 실행
# .e2e_session 파일이 없으면 명확한 안내 메시지를 출력한다.
# SKIP_SESSION_CHECK=1 로 건너뛸 수 있다.
# ---------------------------------------------------------------------------
_SESSION_FILE = Path(__file__).parent.parent.parent / ".e2e_session"
_SESSION_FILE_SQLITE = Path(str(_SESSION_FILE) + ".session")


def _check_e2e_session_file() -> None:
    """Telethon 세션 파일 존재 여부를 검사하고 없으면 안내 메시지를 출력한다.

    weekly_meeting_multibot.py 의 _collect_dept_responses() 는
    SESSION_FILE.exists() == False 시 즉시 [] 를 반환하므로
    세션 파일이 없으면 부서 응답 수집 전체가 차단된다.

    세션 파일 생성 방법::

        cd ~/telegram-ai-org
        .venv/bin/python scripts/tg_auth.py
        # 전화번호 인증 코드 입력 → .e2e_session.session 자동 생성
    """
    if os.environ.get("SKIP_SESSION_CHECK", "").lower() in ("1", "true", "yes"):
        return

    session_exists = _SESSION_FILE.exists() or _SESSION_FILE_SQLITE.exists()
    if not session_exists:
        msg = (
            "\n"
            "╔══════════════════════════════════════════════════════════════╗\n"
            "║          ⚠️  TELETHON SESSION FILE MISSING  ⚠️               ║\n"
            "╚══════════════════════════════════════════════════════════════╝\n"
            f"  찾는 위치 : {_SESSION_FILE_SQLITE}\n"
            "  상태     : ❌ 파일 없음\n"
            "\n"
            "  📌 주간회의 부서 응답 수집이 완전히 차단됩니다.\n"
            "     (weekly_meeting_multibot.py _collect_dept_responses → 즉시 return [])\n"
            "\n"
            "  ✅ 해결 방법 (Rocky 직접 실행, 최초 1회):\n"
            "     cd ~/telegram-ai-org\n"
            "     .venv/bin/python scripts/tg_auth.py\n"
            "     → 전화번호 인증 코드 입력 후 .e2e_session.session 자동 생성됨\n"
            "\n"
            "  ⏭  세션 체크 건너뛰기: SKIP_SESSION_CHECK=1 pytest ...\n"
            "──────────────────────────────────────────────────────────────\n"
        )
        print(msg, flush=True)
        # Telethon 의존 E2E 테스트는 세션 없이 실행 불가 — 경고만 출력하고 계속 진행
        # (세션이 필요한 개별 테스트는 requires_session fixture 로 skip 처리)


_check_e2e_session_file()


@pytest.fixture(scope="session")
def e2e_session_available() -> bool:
    """Telethon 세션 파일 존재 여부를 반환하는 픽스처.

    세션이 필요한 E2E 테스트에서 조건부 skip 에 활용한다::

        def test_weekly_collab(e2e_session_available):
            if not e2e_session_available:
                pytest.skip("Telethon 세션 없음 — scripts/tg_auth.py 실행 필요")
            ...
    """
    return _SESSION_FILE.exists() or _SESSION_FILE_SQLITE.exists()


@pytest.fixture(scope="session")
def requires_session(e2e_session_available: bool) -> None:
    """세션 파일이 없으면 즉시 pytest.skip() 을 호출하는 픽스처.

    Telethon 의존 테스트에 사용::

        def test_dept_response_collection(requires_session):
            # 세션 없으면 이 줄 이전에 skip 처리됨
            ...
    """
    if not e2e_session_available:
        pytest.skip(
            "Telethon 세션 파일 없음 — 해결: cd ~/telegram-ai-org && "
            ".venv/bin/python scripts/tg_auth.py"
        )


# ---------------------------------------------------------------------------
# preflight_check fixture — E2E 테스트에 자동 적용 (RETRO-01)
# autouse=True: tests/e2e/ 하위 모든 테스트에 자동 실행
# 세션 레벨 _run_preflight()와 함께 이중 검증 구조로 운영.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def preflight_check():
    """E2E pre-flight 검증 결과를 dict로 반환하는 fixture.

    사용 예::

        def test_something(preflight_check):
            assert preflight_check["passed"], preflight_check["errors"]

    SKIP_PREFLIGHT=1 환경변수로 우회 가능 (CI 디버깅 한정).
    """
    if os.environ.get("SKIP_PREFLIGHT", "").lower() in ("1", "true", "yes"):
        return {"passed": True, "skipped": True, "errors": [], "timeout": {}, "filter": {}, "env": {}}

    _here = Path(__file__).parent
    _preflight_mod = _here / "preflight_check.py"

    if not _preflight_mod.exists():
        pytest.skip(f"preflight_check.py 없음: {_preflight_mod}")

    import importlib.util as _ilu
    spec = _ilu.spec_from_file_location("e2e_preflight", _preflight_mod)
    if spec is None or spec.loader is None:
        pytest.skip("preflight_check.py 로드 실패")

    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    result = mod.run_preflight_checks(exit_on_fail=False)

    if not result.get("passed", True):
        pytest.fail(
            "E2E pre-flight 실패:\n" + "\n".join(f"  - {e}" for e in result.get("errors", [])),
            pytrace=False,
        )

    return result


class _FakeOrg:
    def __init__(self, org_id: str, dept_name: str = "", direction: str = ""):
        self.id = org_id
        self.dept_name = dept_name
        self.direction = direction


class _FakeConfig:
    def list_orgs(self):
        return [
            _FakeOrg("aiorg_dev", "개발팀", "소프트웨어 개발"),
            _FakeOrg("aiorg_mkt", "마케팅팀", "마케팅 전략"),
            _FakeOrg("aiorg_ops", "운영팀", "시스템 운영"),
        ]

    def get_org(self, org_id: str):
        for org in self.list_orgs():
            if org.id == org_id:
                return org
        return None


@pytest.fixture
def persona_memory(tmp_path):
    """격리된 SQLite DB를 사용하는 AgentPersonaMemory."""
    return AgentPersonaMemory(db_path=tmp_path / "persona.db")


@pytest.fixture
def collaboration_tracker(tmp_path, persona_memory):
    """persona_memory가 주입된 CollaborationTracker."""
    return CollaborationTracker(
        db_path=tmp_path / "collab.db",
        persona_memory=persona_memory,
    )


@pytest.fixture
def shoutout_system(tmp_path):
    """격리된 SQLite DB를 사용하는 ShoutoutSystem."""
    return ShoutoutSystem(db_path=tmp_path / "shoutout.db")


@pytest.fixture
def fake_config():
    return _FakeConfig()


@pytest.fixture
def make_orchestrator():
    """PMOrchestrator 팩토리 fixture."""
    def _factory(org_id: str = "aiorg_pm"):
        db = MagicMock()
        graph = MagicMock()
        claim = MagicMock()
        memory = MagicMock()
        return PMOrchestrator(
            context_db=db,
            task_graph=graph,
            claim_manager=claim,
            memory=memory,
            org_id=org_id,
            telegram_send_func=AsyncMock(),
            decision_client=None,
        )
    return _factory


# ---------------------------------------------------------------------------
# 3엔진 공통 픽스처 (Phase 2 보완)
# ---------------------------------------------------------------------------

ALL_ENGINES = ["claude-code", "codex", "gemini-cli"]


@pytest.fixture(params=ALL_ENGINES)
def engine_name(request) -> str:
    """3엔진 이름 parametrize 픽스처."""
    return request.param


@pytest.fixture
def make_run_context():
    """RunContext 팩토리 픽스처."""
    def _factory(
        prompt: str = "테스트 프롬프트",
        *,
        workdir: str | None = None,
        system_prompt: str | None = None,
        engine_config: dict | None = None,
        org_id: str | None = None,
    ) -> RunContext:
        return RunContext(
            prompt=prompt,
            workdir=workdir,
            system_prompt=system_prompt,
            engine_config=engine_config or {},
            org_id=org_id,
        )
    return _factory


@pytest.fixture
def mock_proc_factory():
    """asyncio subprocess mock 프로세스 팩토리 픽스처."""
    def _make(
        returncode: int = 0,
        stdout: bytes = b"",
        stderr: bytes = b"",
    ) -> MagicMock:
        proc = MagicMock()
        proc.returncode = returncode
        proc.communicate = AsyncMock(return_value=(stdout, stderr))
        proc.kill = MagicMock()
        proc.wait = AsyncMock()
        proc.stdout = None
        proc.stderr = None
        return proc
    return _make


@pytest.fixture
def gemini_json_response():
    """Gemini CLI 정상 JSON 응답 bytes 픽스처."""
    fixtures_dir = Path(__file__).parent / "fixtures"
    fpath = fixtures_dir / "gemini_cli_mock_response.json"
    if fpath.exists():
        return fpath.read_bytes()
    payload = {"response": "테스트 응답", "stats": {"models": {}}}
    return json.dumps(payload).encode()


@pytest.fixture
def codex_plain_response():
    """Codex CLI 정상 plain text 응답 bytes 픽스처."""
    fixtures_dir = Path(__file__).parent / "fixtures"
    fpath = fixtures_dir / "codex_mock_response.txt"
    if fpath.exists():
        return fpath.read_bytes()
    return "[TEAM:solo]\n## 결론\n작업 완료".encode("utf-8")


@pytest.fixture
def gemini_cli_available() -> bool:
    """Gemini CLI 바이너리 가용 여부."""
    import shutil
    cli_path = os.environ.get("GEMINI_CLI_PATH", "gemini")
    return shutil.which(cli_path) is not None


@pytest.fixture
def codex_available() -> bool:
    """Codex CLI 바이너리 가용 여부."""
    import shutil
    cli_path = os.environ.get("CODEX_CLI_PATH", "codex")
    return shutil.which(cli_path) is not None


def validate_run_result(result: Any) -> None:
    """run() 결과가 표준 인터페이스를 만족하는지 검증하는 헬퍼."""
    assert result is not None, "run() 결과가 None"
    assert isinstance(result, str), f"run() 결과가 str이 아님: {type(result)}"
    assert len(result) > 0, "run() 결과가 빈 문자열"


def validate_metrics(metrics: Any) -> None:
    """get_last_metrics() 결과가 표준 인터페이스를 만족하는지 검증하는 헬퍼."""
    assert metrics is not None, "get_last_metrics() 결과가 None"
    assert isinstance(metrics, dict), f"get_last_metrics() 결과가 dict가 아님: {type(metrics)}"


def skip_if_cli_unavailable(cli_name: str, env_var: str = "") -> None:
    """CLI가 없으면 pytest.skip()으로 우아하게 건너뛴다."""
    import shutil
    path = os.environ.get(env_var, cli_name) if env_var else cli_name
    if not shutil.which(path):
        pytest.skip(f"{cli_name} CLI 미설치 — 실제 엔진 테스트 건너뜀")
