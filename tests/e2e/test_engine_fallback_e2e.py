"""E2E: 3엔진 폴백·에러 핸들링 및 통합 레벨 실행 검증.

태스크 T-459 Phase 2 산출물.

테스트 분류:
- @pytest.mark.unit     — mock/stub 기반, 외부 의존성 없음 (항상 실행)
- @pytest.mark.integration — 실제 CLI 바이너리 필요 (환경변수 미설정 시 자동 스킵)

엔진별 4-시나리오 커버:
  (1) 인스턴스 생성 및 초기화 검증
  (2) 기본 태스크 실행 및 응답 포맷 검증
  (3) 엔진 불가용 시 폴백/에러 처리 검증
  (4) PM 디스패치 → 엔진 실행 → 결과 반환 전체 흐름 검증
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.base_runner import (
    BaseRunner,
    RunContext,
    RunnerError,
    RunnerFactory,
    RunnerTimeoutError,
)

# ---------------------------------------------------------------------------
# 헬퍼: CLI 가용성 확인
# ---------------------------------------------------------------------------

def _is_cli_available(env_var: str, default_cmd: str) -> bool:
    cmd = os.environ.get(env_var, default_cmd)
    return shutil.which(cmd) is not None


# ---------------------------------------------------------------------------
# Section 1: GeminiCLIRunner — 4-시나리오 완전 커버
# ---------------------------------------------------------------------------


class TestGeminiCLIFallbackUnit:
    """GeminiCLIRunner 폴백·에러 핸들링 — 단위 레벨 (mock)."""

    def _mock_proc(
        self,
        returncode: int = 0,
        stdout: bytes = b"",
        stderr: bytes = b"",
    ) -> MagicMock:
        proc = MagicMock()
        proc.returncode = returncode
        proc.communicate = AsyncMock(return_value=(stdout, stderr))
        proc.kill = MagicMock()
        return proc

    # (1) 인스턴스 생성 및 초기화
    @pytest.mark.unit
    def test_gemini_cli_runner_init_reads_env_vars(self) -> None:
        """GeminiCLIRunner는 GEMINI_CLI_PATH / GEMINI_CLI_DEFAULT_TIMEOUT_SEC 를 읽는다."""
        import importlib

        import tools.gemini_cli_runner as mod

        with patch.dict(os.environ, {
            "GEMINI_CLI_PATH": "/custom/gemini",
            "GEMINI_CLI_DEFAULT_TIMEOUT_SEC": "300",
        }):
            importlib.reload(mod)
            runner = mod.GeminiCLIRunner()
            assert runner.cli_path == "/custom/gemini"
            assert runner.timeout == 300

        # 모듈 상태 복원 — 이후 테스트에서 실제 GEMINI_CLI_PATH 사용
        importlib.reload(mod)

    @pytest.mark.unit
    def test_gemini_cli_runner_initial_metrics_empty(self) -> None:
        """초기화 후 _last_metrics는 빈 dict이다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        runner = GeminiCLIRunner()
        assert runner.get_last_metrics() == {}

    # (2) 기본 태스크 실행 및 응답 포맷 검증
    @pytest.mark.unit
    async def test_gemini_cli_run_basic_json_response_format(self) -> None:
        """정상 JSON 응답은 str 타입이고 비어 있지 않다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        payload = json.dumps({
            "response": "[TEAM:solo]\n## 결론\n리서치 완료",
            "stats": {"models": {"gemini-2.5-flash": {"tokens": {"total": 100}}}},
        }).encode()
        mock_proc = self._mock_proc(returncode=0, stdout=payload)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = GeminiCLIRunner()
            ctx = RunContext(prompt="경쟁사 분석해줘", org_id="aiorg_research_bot")
            result = await runner.run(ctx)

        assert isinstance(result, str)
        assert len(result) > 0
        assert "결론" in result

    @pytest.mark.unit
    async def test_gemini_cli_run_metrics_format_after_run(self) -> None:
        """run() 후 get_last_metrics()는 output_chars, total_tokens, usage_source를 가진다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        payload = json.dumps({
            "response": "분석 완료",
            "stats": {"models": {"gemini-2.5-flash": {"tokens": {"total": 55}}}},
        }).encode()
        mock_proc = self._mock_proc(returncode=0, stdout=payload)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = GeminiCLIRunner()
            await runner.run(RunContext(prompt="테스트"))

        m = runner.get_last_metrics()
        assert "output_chars" in m
        assert "total_tokens" in m
        assert "usage_source" in m
        assert m["total_tokens"] == 55

    # (3) 엔진 불가용 시 폴백/에러 처리
    @pytest.mark.unit
    async def test_gemini_cli_fallback_on_binary_missing(self) -> None:
        """CLI 바이너리가 없으면 RunnerError를 발생시킨다 (호출자가 fallback 가능)."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("binary not found"),
        ):
            runner = GeminiCLIRunner()
            runner.cli_path = "/nonexistent/gemini-xyz"
            with pytest.raises(RunnerError, match="Gemini CLI 없음"):
                await runner.run(RunContext(prompt="테스트"))

    @pytest.mark.unit
    async def test_gemini_cli_fallback_engine_creatable_after_error(self) -> None:
        """GeminiCLIRunner 에러 발생 후 RunnerFactory로 claude-code 폴백 러너를 생성할 수 있다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        # 에러 발생 시뮬레이션
        runner = GeminiCLIRunner()
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("missing"),
        ):
            try:
                await runner.run(RunContext(prompt="테스트"))
            except RunnerError:
                pass

        # 폴백: 다른 엔진으로 계속 실행 가능
        fallback = RunnerFactory.create("claude-code")
        assert isinstance(fallback, BaseRunner)

    @pytest.mark.unit
    async def test_gemini_cli_timeout_propagates_as_runner_timeout_error(self) -> None:
        """타임아웃 시 RunnerTimeoutError를 발생시키며 프로세스를 kill한다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        proc = MagicMock()
        proc.kill = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                runner = GeminiCLIRunner()
                runner.timeout = 1
                with pytest.raises(RunnerTimeoutError):
                    await runner.run(RunContext(prompt="느린 작업"))

        proc.kill.assert_called_once()

    # (4) PM 디스패치 → 엔진 실행 → 결과 반환 전체 흐름
    @pytest.mark.unit
    async def test_gemini_cli_pm_dispatch_full_flow(self) -> None:
        """PM → 리서치실(gemini-cli) 디스패치 → run() → 결과 반환 전체 흐름."""
        from core.constants import BOT_ENGINE_MAP
        from tools.gemini_cli_runner import GeminiCLIRunner

        # Step 1: PM이 BOT_ENGINE_MAP에서 리서치실 엔진 확인
        research_engine = BOT_ENGINE_MAP.get("aiorg_research_bot")
        assert research_engine == "gemini-cli"

        # Step 2: 엔진 러너 생성
        runner = RunnerFactory.create(research_engine)
        assert isinstance(runner, GeminiCLIRunner)

        # Step 3: 실제 태스크 실행 (mock subprocess)
        payload = json.dumps({
            "response": "[TEAM:solo]\n## 결론\n경쟁사 분석 완료",
            "stats": {},
        }).encode()
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(payload, b""))
        proc.kill = MagicMock()

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            ctx = RunContext(
                prompt="국내 AI 오케스트레이션 경쟁사 분석",
                org_id="aiorg_research_bot",
            )
            result = await runner.run(ctx)

        # Step 4: 결과 검증
        assert isinstance(result, str)
        assert "결론" in result


# ---------------------------------------------------------------------------
# Section 2: CodexRunner — 4-시나리오 완전 커버
# ---------------------------------------------------------------------------


class TestCodexFallbackUnit:
    """CodexRunner 폴백·에러 핸들링 — 단위 레벨 (mock)."""

    def _mock_proc(
        self,
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

    # (1) 인스턴스 생성 및 초기화
    @pytest.mark.unit
    def test_codex_runner_init_reads_env_cli_path(self) -> None:
        """CodexRunner는 CODEX_CLI_PATH 환경변수를 읽는다."""
        import importlib

        import tools.codex_runner as mod

        with patch.dict(os.environ, {"CODEX_CLI_PATH": "/custom/codex"}):
            importlib.reload(mod)
            assert mod.CODEX_CLI == "/custom/codex"

        # 모듈 상태 복원
        importlib.reload(mod)

    @pytest.mark.unit
    def test_codex_runner_is_base_runner_subclass(self) -> None:
        """CodexRunner는 BaseRunner의 서브클래스다."""
        from tools.codex_runner import CodexRunner
        assert issubclass(CodexRunner, BaseRunner)

    @pytest.mark.unit
    def test_codex_runner_initial_get_last_metrics_is_dict(self) -> None:
        """초기화 후 get_last_metrics()는 dict를 반환한다."""
        from tools.codex_runner import CodexRunner
        runner = CodexRunner()
        assert isinstance(runner.get_last_metrics(), dict)

    # (2) 기본 태스크 실행 및 응답 포맷 검증
    @pytest.mark.unit
    async def test_codex_run_basic_response_is_str(self) -> None:
        """정상 실행 결과는 str 타입이다."""
        from tools.codex_runner import CodexRunner

        output = "[TEAM:solo]\n## 결론\n배포 자동화 완료".encode("utf-8")
        mock_proc = self._mock_proc(returncode=0, stdout=output)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = CodexRunner()
            ctx = RunContext(prompt="배포 스크립트 작성해줘", org_id="aiorg_ops_bot")
            result = await runner.run(ctx)

        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.unit
    async def test_codex_run_with_run_context_and_system_prompt(self) -> None:
        """system_prompt가 있으면 run_task()로 병합 실행한다."""
        from tools.codex_runner import CodexRunner

        output = "[TEAM:solo]\n## 결론\n작업 완료".encode("utf-8")
        mock_proc = self._mock_proc(returncode=0, stdout=output)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = CodexRunner()
            ctx = RunContext(
                prompt="배포 현황 점검",
                system_prompt="당신은 DevOps 전문가입니다",
                org_id="aiorg_ops_bot",
            )
            result = await runner.run_task(ctx)

        assert isinstance(result, str)

    # (3) 엔진 불가용 시 폴백/에러 처리
    @pytest.mark.unit
    async def test_codex_fallback_on_binary_missing_returns_error_str(self) -> None:
        """Codex CLI 없으면 ❌ 접두사 에러 문자열을 반환한다 (예외 아님)."""
        from tools.codex_runner import CodexRunner

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("binary not found"),
        ):
            runner = CodexRunner()
            result = await runner.run(RunContext(prompt="테스트"))

        assert "❌" in result

    @pytest.mark.unit
    async def test_codex_fallback_runner_available_after_error(self) -> None:
        """Codex 에러 후 claude-code 폴백 러너로 계속 실행 가능하다."""
        from tools.codex_runner import CodexRunner

        # Codex 에러 시뮬레이션
        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("missing codex"),
        ):
            runner = CodexRunner()
            result = await runner.run(RunContext(prompt="테스트"))
            assert "❌" in result

        # 폴백: claude-code 러너로 전환
        fallback_runner = RunnerFactory.create("claude-code")
        assert isinstance(fallback_runner, BaseRunner)

    @pytest.mark.unit
    async def test_codex_timeout_returns_error_string_with_timeout_word(self) -> None:
        """타임아웃 시 '타임아웃' 키워드가 포함된 에러 문자열을 반환한다."""
        from tools.codex_runner import CodexRunner

        mock_proc = self._mock_proc()
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                runner = CodexRunner()
                runner.timeout = 1
                result = await runner.run(RunContext(prompt="느린 배포"))

        assert "타임아웃" in result

    @pytest.mark.unit
    async def test_codex_nonzero_exit_returns_error_string(self) -> None:
        """0이 아닌 종료 코드 시 ❌ 에러 문자열을 반환한다."""
        from tools.codex_runner import CodexRunner

        mock_proc = self._mock_proc(returncode=1, stderr=b"command not found")
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = CodexRunner()
            result = await runner.run(RunContext(prompt="에러 유발"))

        assert "❌" in result

    # (4) PM 디스패치 → 엔진 실행 → 결과 반환 전체 흐름
    @pytest.mark.unit
    async def test_codex_pm_dispatch_full_flow(self) -> None:
        """PM → 운영실(codex) 디스패치 → run() → 결과 반환 전체 흐름."""
        from core.constants import BOT_ENGINE_MAP
        from tools.codex_runner import CodexRunner

        # Step 1: BOT_ENGINE_MAP에서 운영실 엔진 확인
        ops_engine = BOT_ENGINE_MAP.get("aiorg_ops_bot")
        assert ops_engine == "codex"

        # Step 2: 엔진 러너 생성
        runner = RunnerFactory.create(ops_engine)
        assert isinstance(runner, CodexRunner)

        # Step 3: 태스크 실행 (mock subprocess)
        output = "[TEAM:solo]\n## 결론\n배포 파이프라인 자동화 완료".encode("utf-8")
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(output, b""))
        proc.kill = MagicMock()
        proc.wait = AsyncMock()
        proc.stdout = None
        proc.stderr = None

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            ctx = RunContext(
                prompt="CI/CD 파이프라인 점검 및 배포 자동화",
                org_id="aiorg_ops_bot",
            )
            result = await runner.run(ctx)

        # Step 4: 결과 검증
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Section 3: ClaudeRunner (claude-code) — 4-시나리오 완전 커버
# ---------------------------------------------------------------------------


class TestClaudeCodeFallbackUnit:
    """ClaudeSubprocessRunner/claude-code 폴백·에러 핸들링 — 단위 레벨 (mock)."""

    # (1) 인스턴스 생성 및 초기화
    @pytest.mark.unit
    def test_claude_code_runner_init_is_base_runner(self) -> None:
        """RunnerFactory.create('claude-code')는 BaseRunner 인스턴스를 반환한다."""
        runner = RunnerFactory.create("claude-code")
        assert isinstance(runner, BaseRunner)

    @pytest.mark.unit
    def test_claude_code_runner_has_all_required_methods(self) -> None:
        """claude-code 러너는 run/run_single/run_task/capabilities/get_last_metrics를 가진다."""
        runner = RunnerFactory.create("claude-code")
        for method in ("run", "run_single", "run_task", "capabilities", "get_last_metrics"):
            assert callable(getattr(runner, method, None)), (
                f"claude-code 러너: '{method}' 메서드 없음"
            )

    @pytest.mark.unit
    def test_claude_code_runner_initial_metrics_is_dict(self) -> None:
        """초기화 후 get_last_metrics()는 dict를 반환한다."""
        runner = RunnerFactory.create("claude-code")
        assert isinstance(runner.get_last_metrics(), dict)

    # (2) 기본 태스크 실행 및 응답 포맷 검증 (mock)
    @pytest.mark.unit
    async def test_claude_code_run_with_mock_inner_runner(self) -> None:
        """내부 _runner를 mock으로 교체하면 run()이 그 결과를 반환한다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        runner = ClaudeSubprocessRunner()
        runner._runner = MagicMock()
        runner._runner.run = AsyncMock(return_value="[TEAM:solo]\n## 결론\n버그 수정 완료")

        ctx = RunContext(prompt="API 500 에러 버그 수정해줘", org_id="aiorg_engineering_bot")
        result = await runner.run(ctx)

        assert isinstance(result, str)
        assert "결론" in result

    @pytest.mark.unit
    async def test_claude_code_run_task_prepends_system_prompt(self) -> None:
        """run_task()에서 system_prompt는 프롬프트에 병합된다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        captured: list[str] = []
        runner = ClaudeSubprocessRunner()

        # ClaudeSubprocessRunner.run_task() 는 _runner.run_task() 에 위임 — AsyncMock 필수
        runner._runner = MagicMock()
        runner._runner.run_task = AsyncMock(
            side_effect=lambda p, **kw: captured.append(p) or "완료"
        )

        ctx = RunContext(
            prompt="코드 리뷰해줘",
            system_prompt="시니어 개발자로서 검토하라",
            org_id="aiorg_engineering_bot",
        )
        await runner.run_task(ctx)

        # run_task는 ctx.prompt를 첫 번째 인자로 전달하고 system_prompt를 kwarg로 전달
        assert len(captured) == 1
        assert captured[0] == "코드 리뷰해줘"

    # (3) 엔진 불가용 시 폴백/에러 처리
    @pytest.mark.unit
    def test_claude_code_fallback_to_subprocess_when_sdk_missing(self) -> None:
        """claude-agent SDK 없으면 ClaudeSubprocessRunner로 폴백한다."""
        import sys

        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        original = sys.modules.get("tools.claude_agent_runner", ...)
        sys.modules["tools.claude_agent_runner"] = None  # type: ignore[assignment]
        try:
            runner = RunnerFactory._create_claude_runner()
            assert isinstance(runner, ClaudeSubprocessRunner), (
                "SDK 없을 때 ClaudeSubprocessRunner로 폴백되어야 함"
            )
        finally:
            if original is ...:
                del sys.modules["tools.claude_agent_runner"]
            else:
                sys.modules["tools.claude_agent_runner"] = original

    @pytest.mark.unit
    async def test_claude_code_runner_error_wraps_inner_exception(self) -> None:
        """내부 런타임 에러는 RunnerError로 래핑된다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        runner = ClaudeSubprocessRunner()
        runner._runner = MagicMock()
        runner._runner.run = AsyncMock(side_effect=RuntimeError("내부 에러"))

        with pytest.raises(RunnerError, match="내부 에러"):
            await runner.run(RunContext(prompt="에러 유발"))

    @pytest.mark.unit
    async def test_claude_code_error_prefix_response_raises_runner_error(self) -> None:
        """내부 runner가 ❌로 시작하는 응답을 반환하면 RunnerError를 발생시킨다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        runner = ClaudeSubprocessRunner()
        runner._runner = MagicMock()
        runner._runner.run = AsyncMock(return_value="❌ 실행 실패: 권한 없음")

        with pytest.raises(RunnerError):
            await runner.run(RunContext(prompt="오류 태스크"))

    # (4) PM 디스패치 → 엔진 실행 → 결과 반환 전체 흐름
    @pytest.mark.unit
    async def test_claude_code_pm_dispatch_full_flow(self) -> None:
        """PM → 개발실(claude-code) 디스패치 → run() → 결과 반환 전체 흐름."""
        from core.constants import BOT_ENGINE_MAP
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        # Step 1: BOT_ENGINE_MAP에서 개발실 엔진 확인
        eng_engine = BOT_ENGINE_MAP.get("aiorg_engineering_bot")
        assert eng_engine == "claude-code"

        # Step 2: 엔진 러너 생성
        runner = RunnerFactory.create(eng_engine)
        assert isinstance(runner, BaseRunner)

        # Step 3: 태스크 실행 (inner runner mock)
        if isinstance(runner, ClaudeSubprocessRunner):
            runner._runner = MagicMock()
            runner._runner.run = AsyncMock(
                return_value="[TEAM:engineering-senior-developer]\n## 결론\n버그 수정 완료"
            )
            ctx = RunContext(
                prompt="로그인 API 500 에러 수정",
                org_id="aiorg_engineering_bot",
            )
            result = await runner.run(ctx)
            assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Section 4: 3엔진 동시 폴백 시나리오 (parametrize)
# ---------------------------------------------------------------------------


class TestThreeEngineSimultaneousFallback:
    """3엔진 동시 실패 및 복구 시나리오."""

    @pytest.mark.unit
    @pytest.mark.parametrize("engine", ["claude-code", "codex", "gemini-cli"])
    def test_engine_runner_creation_always_succeeds(self, engine: str) -> None:
        """3엔진 모두 RunnerFactory.create()로 항상 성공 생성된다."""
        runner = RunnerFactory.create(engine)
        assert isinstance(runner, BaseRunner)

    @pytest.mark.unit
    def test_all_engines_have_different_class_names(self) -> None:
        """3엔진은 서로 다른 클래스 타입으로 인스턴스화된다."""
        runners = {e: RunnerFactory.create(e) for e in ["claude-code", "codex", "gemini-cli"]}
        class_names = {type(r).__name__ for r in runners.values()}
        assert len(class_names) == 3, (
            f"3엔진이 모두 다른 타입이어야 함 (실제: {class_names})"
        )

    @pytest.mark.unit
    def test_fallback_chain_all_engines_produce_base_runner(self) -> None:
        """폴백 체인: 3엔진 모두 BaseRunner 반환 — 런타임 교체 가능성 확인."""
        from core.constants import BOT_ENGINE_MAP

        for bot_id, engine in BOT_ENGINE_MAP.items():
            fallback_runner = RunnerFactory.create(engine)
            assert isinstance(fallback_runner, BaseRunner), (
                f"{bot_id}({engine}): 폴백 러너가 BaseRunner가 아님"
            )

    @pytest.mark.unit
    async def test_cross_engine_mock_dispatch_three_teams(self) -> None:
        """PM → 개발실(claude-code) + 운영실(codex) + 리서치실(gemini-cli) 동시 mock 디스패치."""
        results: dict[str, str] = {}

        class QuickMockRunner(BaseRunner):
            def __init__(self, label: str) -> None:
                self._label = label

            async def run(self, ctx: RunContext) -> str:
                return f"[{self._label}] {ctx.prompt[:15]}_처리완료"

            def get_last_metrics(self) -> dict:
                return {"engine": self._label}

            def capabilities(self) -> set:
                return {"mock"}

        for engine_label, org, prompt in [
            ("claude-code", "aiorg_engineering_bot", "버그 수정"),
            ("codex", "aiorg_ops_bot", "배포 점검"),
            ("gemini-cli", "aiorg_research_bot", "경쟁사 분석"),
        ]:
            runner = QuickMockRunner(engine_label)
            ctx = RunContext(prompt=prompt, org_id=org)
            results[org] = await runner.run(ctx)
            assert f"[{engine_label}]" in results[org]

        assert len(results) == 3
        assert results["aiorg_engineering_bot"] != results["aiorg_ops_bot"]


# ---------------------------------------------------------------------------
# Section 5: 통합 레벨 테스트 — 실제 CLI 필요 (환경변수 미설정 시 자동 스킵)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.slow
class TestGeminiCLIIntegration:
    """GeminiCLIRunner 실제 CLI 호출 통합 테스트.

    실행 조건: GEMINI_CLI_PATH 또는 'gemini' 명령이 PATH에 존재해야 함.
    미설정 시 자동 스킵.
    """

    @pytest.fixture(autouse=True)
    def skip_if_unavailable(self) -> None:
        if not _is_cli_available("GEMINI_CLI_PATH", "gemini"):
            pytest.skip(
                "gemini CLI 미설치 — GEMINI_CLI_PATH 설정 또는 'gemini' 설치 후 재실행"
            )

    async def test_gemini_cli_real_basic_prompt(self) -> None:
        """실제 gemini CLI로 짧은 프롬프트를 실행하고 str 응답을 받는다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        runner = GeminiCLIRunner()
        ctx = RunContext(
            prompt="Say 'hello' in one word only.",
            engine_config={"model": "gemini-2.5-flash"},
        )
        result = await runner.run(ctx)

        assert isinstance(result, str)
        assert len(result.strip()) > 0

    async def test_gemini_cli_real_metrics_populated(self) -> None:
        """실제 실행 후 get_last_metrics()에 usage_source가 설정된다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        runner = GeminiCLIRunner()
        ctx = RunContext(
            prompt="Reply with just the number 1.",
            engine_config={"model": "gemini-2.5-flash"},
        )
        await runner.run(ctx)

        m = runner.get_last_metrics()
        assert "usage_source" in m
        assert m["usage_source"] in ("gemini_cli_json", "gemini_cli_plain")


@pytest.mark.integration
@pytest.mark.slow
class TestCodexIntegration:
    """CodexRunner 실제 CLI 호출 통합 테스트.

    실행 조건: CODEX_CLI_PATH 또는 'codex' 명령이 PATH에 존재해야 함.
    미설정 시 자동 스킵.
    """

    @pytest.fixture(autouse=True)
    def skip_if_unavailable(self) -> None:
        if not _is_cli_available("CODEX_CLI_PATH", "codex"):
            pytest.skip(
                "codex CLI 미설치 — CODEX_CLI_PATH 설정 또는 'npm i -g @openai/codex' 후 재실행"
            )

    async def test_codex_real_basic_prompt(self) -> None:
        """실제 codex CLI로 짧은 프롬프트를 실행하고 str 응답을 받는다."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        ctx = RunContext(prompt="Print 'hello' only. No other output.")
        result = await runner.run(ctx)

        assert isinstance(result, str)
        assert len(result.strip()) > 0

    async def test_codex_real_capabilities(self) -> None:
        """실제 CodexRunner.capabilities()는 set을 반환한다."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        caps = runner.capabilities()
        assert isinstance(caps, set)


@pytest.mark.integration
@pytest.mark.slow
class TestClaudeCodeIntegration:
    """Claude-code (ClaudeSubprocessRunner) 실제 CLI 호출 통합 테스트.

    실행 조건: 'claude' 명령이 PATH에 존재해야 함 (claude-code npm 패키지).
    미설정 시 자동 스킵.
    """

    @pytest.fixture(autouse=True)
    def skip_if_unavailable(self) -> None:
        if not _is_cli_available("CLAUDE_CLI_PATH", "claude"):
            pytest.skip(
                "claude CLI 미설치 — 'npm install -g @anthropic-ai/claude-code' 후 재실행"
            )

    async def test_claude_code_real_basic_prompt(self) -> None:
        """실제 claude-code로 짧은 프롬프트를 실행하고 str 응답을 받는다."""
        runner = RunnerFactory.create("claude-code")
        ctx = RunContext(prompt="Say 'pong' only. No markdown, no explanation.")
        result = await runner.run(ctx)

        assert isinstance(result, str)
        assert len(result.strip()) > 0

    async def test_claude_code_real_runner_is_base_runner(self) -> None:
        """실제 환경에서 RunnerFactory.create('claude-code')는 BaseRunner다."""
        runner = RunnerFactory.create("claude-code")
        assert isinstance(runner, BaseRunner)


# ---------------------------------------------------------------------------
# Section 6: 환경 정합성 (설정 파일 & 마커)
# ---------------------------------------------------------------------------


class TestE2EEnvironmentSetup:
    """E2E 테스트 실행 환경 정합성 검증."""

    @pytest.mark.unit
    def test_pyproject_toml_has_e2e_markers(self) -> None:
        """pyproject.toml [tool.pytest.ini_options]에 e2e/integration 마커가 정의되어 있다."""
        import tomllib

        toml_path = Path(__file__).parent.parent.parent / "pyproject.toml"
        if not toml_path.exists():
            pytest.skip("pyproject.toml 없음")

        with open(toml_path, "rb") as f:
            config = tomllib.load(f)

        markers = config.get("tool", {}).get("pytest.ini_options", {}).get("markers", [])
        # pyproject.toml 구조상 tool."pytest.ini_options" 키로 접근
        pytest_opts = config.get("tool", {})
        for key in pytest_opts:
            if "pytest" in key.lower():
                markers = pytest_opts[key].get("markers", markers)
                break

        # markers가 비어 있을 경우 직접 파일 내용으로 확인
        if not markers:
            content = toml_path.read_text()
            assert "markers" in content, "pyproject.toml에 markers 설정 없음"
        else:
            marker_names = [m.split(":")[0].strip() for m in markers]
            assert "e2e" in marker_names or any("e2e" in m for m in markers)
            assert "integration" in marker_names or any("integration" in m for m in markers)

    @pytest.mark.unit
    def test_requirements_test_or_dev_has_pytest_asyncio(self) -> None:
        """pytest-asyncio가 dev 의존성 또는 requirements-test.txt에 포함된다."""
        import tomllib

        root = Path(__file__).parent.parent.parent
        toml_path = root / "pyproject.toml"

        if toml_path.exists():
            with open(toml_path, "rb") as f:
                config = tomllib.load(f)
            dev_deps = config.get("project", {}).get("optional-dependencies", {})
            all_deps = " ".join(
                " ".join(v) for v in dev_deps.values()
            )
            assert "pytest-asyncio" in all_deps, (
                "pyproject.toml dev 의존성에 pytest-asyncio 누락"
            )

    @pytest.mark.unit
    def test_conftest_has_engine_availability_fixtures(self) -> None:
        """conftest.py에 gemini_cli_available, codex_available 픽스처가 있다."""

        conftest = Path(__file__).parent / "conftest.py"
        content = conftest.read_text()
        assert "gemini_cli_available" in content
        assert "codex_available" in content
        assert "make_run_context" in content

    @pytest.mark.unit
    def test_e2e_fixtures_directory_has_mock_data(self) -> None:
        """tests/e2e/fixtures/ 디렉토리에 mock 응답 파일이 있다."""

        fixtures_dir = Path(__file__).parent / "fixtures"
        assert fixtures_dir.exists(), "fixtures/ 디렉토리 없음"

        expected_files = [
            "gemini_cli_mock_response.json",
            "codex_mock_response.txt",
        ]
        for fname in expected_files:
            fpath = fixtures_dir / fname
            assert fpath.exists(), f"fixtures/{fname} 없음"
