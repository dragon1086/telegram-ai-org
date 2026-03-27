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
def _run_preflight() -> None:
    if os.environ.get("SKIP_PREFLIGHT", "").lower() in ("1", "true", "yes"):
        print("[pre-flight] SKIP_PREFLIGHT=1 — 체크 생략", flush=True)
        return

    # tests/e2e/preflight_check.py 모듈 방식 우선 사용
    _here = Path(__file__).parent
    _preflight_mod = _here / "preflight_check.py"
    if _preflight_mod.exists():
        # 동일 패키지 내 모듈을 직접 import해서 실행
        import importlib.util as _ilu
        spec = _ilu.spec_from_file_location("e2e_preflight", _preflight_mod)
        if spec and spec.loader:
            mod = _ilu.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            mod.run_preflight_checks(exit_on_fail=True)
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
    result = subprocess.run(
        [sys.executable, str(preflight_script)],
        cwd=str(project_root),
        capture_output=False,
    )
    if result.returncode != 0:
        raise SystemExit(
            "❌ E2E pre-flight 실패 — 환경을 점검 후 재실행하세요.\n"
            f"   스크립트: {preflight_script}\n"
            "   힌트: SKIP_PREFLIGHT=1 로 일시적으로 우회 가능."
        )


_run_preflight()


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
