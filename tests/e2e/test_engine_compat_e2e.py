"""E2E: 3개 엔진(claude-code, codex, gemini-cli) 호환성 스모크 테스트.

system-overview.html Layer 4: 엔진 호환성 검증.
각 엔진이 정상 인스턴스화되고 RunContext를 받을 수 있는지 확인한다.
실제 CLI를 호출하지 않고 runner 객체 생성 및 인터페이스만 검증.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.base_runner import (
    BaseRunner,
    RunContext,
    RunnerAuthError,
    RunnerError,
    RunnerFactory,
    RunnerRateLimitError,
    RunnerTimeoutError,
)


class TestEngineInstantiation:
    """3개 엔진 러너 인스턴스화 테스트."""

    def test_claude_code_runner_creates(self) -> None:
        """claude-code 엔진 러너 생성 성공."""
        runner = RunnerFactory.create("claude-code")
        assert runner is not None
        assert isinstance(runner, BaseRunner)

    def test_codex_runner_creates(self) -> None:
        """codex 엔진 러너 생성 성공."""
        runner = RunnerFactory.create("codex")
        assert runner is not None
        assert isinstance(runner, BaseRunner)

    def test_gemini_cli_runner_creates(self) -> None:
        """gemini-cli 엔진 러너 생성 성공."""
        runner = RunnerFactory.create("gemini-cli")
        assert runner is not None
        assert isinstance(runner, BaseRunner)

    def test_invalid_engine_raises(self) -> None:
        """잘못된 엔진명은 ValueError를 발생시킨다."""
        with pytest.raises((ValueError, ImportError)):
            RunnerFactory.create("unknown-engine-xyz")


class TestRunContextInterface:
    """모든 엔진이 RunContext 인터페이스를 공유하는지 검증."""

    def test_run_context_creation(self) -> None:
        """RunContext 생성 성공."""
        ctx = RunContext(
            prompt="테스트 프롬프트",
            workdir="/tmp",
            system_prompt="시스템 프롬프트",
            engine_config={"model": "test-model"},
        )
        assert ctx.prompt == "테스트 프롬프트"
        assert ctx.workdir == "/tmp"
        assert ctx.engine_config == {"model": "test-model"}

    def test_run_context_defaults(self) -> None:
        """RunContext 기본값 검증."""
        ctx = RunContext(prompt="테스트")
        assert ctx.workdir is None
        assert ctx.system_prompt is None
        assert ctx.progress_callback is None
        assert ctx.engine_config == {}

    @pytest.mark.parametrize("engine", ["claude-code", "codex", "gemini-cli"])
    def test_runner_has_run_method(self, engine: str) -> None:
        """모든 엔진 러너가 run() 메서드를 가진다."""
        runner = RunnerFactory.create(engine)
        assert hasattr(runner, "run")
        assert callable(runner.run)

    @pytest.mark.parametrize("engine", ["claude-code", "codex", "gemini-cli"])
    def test_runner_has_get_last_metrics(self, engine: str) -> None:
        """모든 엔진 러너가 get_last_metrics() 메서드를 가진다."""
        runner = RunnerFactory.create(engine)
        assert hasattr(runner, "get_last_metrics")
        metrics = runner.get_last_metrics()
        assert isinstance(metrics, dict)

    @pytest.mark.parametrize("engine", ["claude-code", "codex", "gemini-cli"])
    def test_runner_has_capabilities(self, engine: str) -> None:
        """모든 엔진 러너가 capabilities() 메서드를 가진다."""
        runner = RunnerFactory.create(engine)
        assert hasattr(runner, "capabilities")
        caps = runner.capabilities()
        assert isinstance(caps, set)


class TestGeminiCLISpecific:
    """Gemini CLI 특화 테스트."""

    def test_gemini_cli_runner_import(self) -> None:
        """GeminiCLIRunner 임포트 성공."""
        from tools.gemini_cli_runner import GeminiCLIRunner  # noqa: F401

    def test_gemini_cli_sanitize_output(self) -> None:
        """Gemini CLI stdout 노이즈 제거 함수 동작 확인."""
        from tools.gemini_cli_runner import _sanitize_output

        raw = "loaded cached credentials\nActual response here\nWarning: something"
        result = _sanitize_output(raw)
        assert "loaded cached credentials" not in result.lower()
        assert "Actual response here" in result

    def test_gemini_cli_extract_json_block(self) -> None:
        """JSON 블록 추출 함수 동작 확인."""
        from tools.gemini_cli_runner import _extract_json_block

        text = 'some prefix {"response": "hello", "stats": {}}'
        result = _extract_json_block(text)
        assert result.startswith("{")

    def test_gemini_cli_default_model_is_correct(self) -> None:
        """기본 모델이 gemini-2.5-flash (deprecated 아님)."""
        from tools.gemini_runner import GeminiRunner

        # GeminiRunner의 기본 모델 확인 (gemini-2.0-flash 사용 금지)
        import inspect
        source = inspect.getsource(GeminiRunner.run)
        assert "gemini-2.0-flash" not in source, (
            "gemini-2.0-flash는 2026-06-01 서비스 종료 예정 — gemini-2.5-flash 사용"
        )


class TestBotEngineAssignment:
    """organizations.yaml 엔진 배정 정합성 테스트."""

    def test_engine_assignments_valid(self) -> None:
        """모든 봇의 엔진이 유효한 값으로 설정되어 있는지 확인."""
        import yaml
        from pathlib import Path

        config_path = Path(__file__).parent.parent.parent / "organizations.yaml"
        if not config_path.exists():
            pytest.skip("organizations.yaml not found")

        with open(config_path) as f:
            config = yaml.safe_load(f)

        valid_engines = {"claude-code", "codex", "gemini-cli", "gemini"}

        for org in config.get("organizations", []):
            org_id = org.get("id", "unknown")
            execution = org.get("execution", {})
            preferred = execution.get("preferred_engine", "")
            fallback = execution.get("fallback_engine", "")

            assert preferred in valid_engines, (
                f"{org_id}: preferred_engine '{preferred}' 는 유효하지 않은 엔진"
            )
            assert fallback in valid_engines, (
                f"{org_id}: fallback_engine '{fallback}' 는 유효하지 않은 엔진"
            )

    def test_research_and_growth_use_gemini(self) -> None:
        """리서치실과 성장실은 gemini-cli 엔진을 사용해야 한다."""
        import yaml
        from pathlib import Path

        config_path = Path(__file__).parent.parent.parent / "organizations.yaml"
        if not config_path.exists():
            pytest.skip("organizations.yaml not found")

        with open(config_path) as f:
            config = yaml.safe_load(f)

        gemini_orgs = {"aiorg_research_bot", "aiorg_growth_bot"}

        for org in config.get("organizations", []):
            org_id = org.get("id", "")
            if org_id in gemini_orgs:
                engine = org.get("execution", {}).get("preferred_engine", "")
                assert engine == "gemini-cli", (
                    f"{org_id}: 리서치/성장실은 gemini-cli 사용 필수 (현재: {engine})"
                )

    def test_ops_uses_codex(self) -> None:
        """운영실은 codex 엔진을 사용해야 한다."""
        import yaml
        from pathlib import Path

        config_path = Path(__file__).parent.parent.parent / "organizations.yaml"
        if not config_path.exists():
            pytest.skip("organizations.yaml not found")

        with open(config_path) as f:
            config = yaml.safe_load(f)

        for org in config.get("organizations", []):
            if org.get("id") == "aiorg_ops_bot":
                engine = org.get("execution", {}).get("preferred_engine", "")
                assert engine == "codex", (
                    f"운영실은 codex 엔진 사용 필수 (현재: {engine})"
                )
                break


# ---------------------------------------------------------------------------
# Phase 4 추가: 커버리지 보완 — 3엔진 × 4 시나리오
# ---------------------------------------------------------------------------


class _ConcreteRunner(BaseRunner):
    """테스트용 최소 구현 러너 — 실제 CLI 없이 로직만 검증."""

    def __init__(self, response: str = "ok") -> None:
        self._response = response
        self._last_metrics: dict = {}

    async def run(self, ctx: RunContext) -> str:
        self._last_metrics = {"chars": len(self._response)}
        return self._response

    def get_last_metrics(self) -> dict:
        return self._last_metrics

    def capabilities(self) -> set:
        return {"streaming", "tools"}


class TestBaseRunnerMethods:
    """BaseRunner 추가 메서드 커버리지 (run_single, run_task)."""

    async def test_run_single_delegates_to_run(self) -> None:
        """run_single()은 run()에 위임한다."""
        runner = _ConcreteRunner(response="single-result")
        ctx = RunContext(prompt="테스트 프롬프트")
        result = await runner.run_single(ctx)
        assert result == "single-result"

    async def test_run_task_with_system_prompt_merged(self) -> None:
        """run_task()는 system_prompt가 있으면 프롬프트에 병합하여 run()을 호출한다."""
        received_prompts: list[str] = []

        class TrackingRunner(_ConcreteRunner):
            async def run(self, ctx: RunContext) -> str:
                received_prompts.append(ctx.prompt)
                return "tracked"

        runner = TrackingRunner()
        ctx = RunContext(prompt="사용자 요청", system_prompt="시스템 지침")
        result = await runner.run_task(ctx)
        assert result == "tracked"
        assert len(received_prompts) == 1
        assert "시스템 지침" in received_prompts[0]
        assert "사용자 요청" in received_prompts[0]

    async def test_run_task_without_system_prompt_passes_through(self) -> None:
        """run_task()는 system_prompt가 없으면 원본 ctx로 run()을 호출한다."""
        received_prompts: list[str] = []

        class TrackingRunner(_ConcreteRunner):
            async def run(self, ctx: RunContext) -> str:
                received_prompts.append(ctx.prompt)
                return "pass-through"

        runner = TrackingRunner()
        ctx = RunContext(prompt="직접 요청")
        result = await runner.run_task(ctx)
        assert result == "pass-through"
        assert received_prompts[0] == "직접 요청"

    def test_get_last_metrics_returns_dict(self) -> None:
        """get_last_metrics()는 dict를 반환한다."""
        runner = _ConcreteRunner()
        assert isinstance(runner.get_last_metrics(), dict)

    def test_capabilities_returns_set(self) -> None:
        """capabilities()는 set을 반환한다."""
        runner = _ConcreteRunner()
        caps = runner.capabilities()
        assert isinstance(caps, set)
        assert "streaming" in caps


class TestRunnerErrorHierarchy:
    """RunnerError 계층 구조 테스트."""

    def test_runner_error_is_exception(self) -> None:
        """RunnerError는 Exception의 서브클래스다."""
        assert issubclass(RunnerError, Exception)

    def test_auth_error_is_runner_error(self) -> None:
        """RunnerAuthError는 RunnerError의 서브클래스다."""
        assert issubclass(RunnerAuthError, RunnerError)

    def test_rate_limit_error_is_runner_error(self) -> None:
        """RunnerRateLimitError는 RunnerError의 서브클래스다."""
        assert issubclass(RunnerRateLimitError, RunnerError)

    def test_timeout_error_is_runner_error(self) -> None:
        """RunnerTimeoutError는 RunnerError의 서브클래스다."""
        assert issubclass(RunnerTimeoutError, RunnerError)

    def test_runner_error_can_be_raised(self) -> None:
        """RunnerError를 raise/catch할 수 있다."""
        with pytest.raises(RunnerError, match="테스트 에러"):
            raise RunnerError("테스트 에러")

    def test_auth_error_caught_as_runner_error(self) -> None:
        """RunnerAuthError는 RunnerError로 catch 가능하다."""
        with pytest.raises(RunnerError):
            raise RunnerAuthError("인증 실패")


class TestRunnerFactoryExtended:
    """RunnerFactory 레지스트리/추가 엔진 커버리지."""

    def test_register_and_create_custom_engine(self) -> None:
        """커스텀 엔진 등록 후 create()로 생성 가능하다."""
        RunnerFactory.register("test-custom-engine", _ConcreteRunner)
        runner = RunnerFactory.create("test-custom-engine")
        assert isinstance(runner, _ConcreteRunner)
        # 정리
        del RunnerFactory._registry["test-custom-engine"]

    def test_create_gemini_api_runner(self) -> None:
        """gemini API 러너는 GeminiRunner를 반환한다."""
        from tools.gemini_runner import GeminiRunner
        runner = RunnerFactory.create("gemini")
        assert isinstance(runner, GeminiRunner)

    def test_claude_runner_fallback_to_subprocess(self) -> None:
        """ClaudeAgentRunner import 실패 시 ClaudeSubprocessRunner로 폴백한다."""
        with patch("tools.base_runner.RunnerFactory._create_claude_runner") as mock_create:
            from tools.claude_subprocess_runner import ClaudeSubprocessRunner
            mock_create.return_value = ClaudeSubprocessRunner()
            runner = RunnerFactory.create("claude-code")
            assert runner is not None

    def test_create_claude_runner_actual_fallback(self) -> None:
        """ClaudeAgentRunner 임포트 실패 시 ClaudeSubprocessRunner로 폴백한다."""
        import sys

        # sys.modules에 None 을 주입하면 import 시 ImportError 발생
        original = sys.modules.get("tools.claude_agent_runner", ...)
        sys.modules["tools.claude_agent_runner"] = None  # type: ignore[assignment]
        try:
            runner = RunnerFactory._create_claude_runner()
            from tools.claude_subprocess_runner import ClaudeSubprocessRunner
            assert isinstance(runner, ClaudeSubprocessRunner)
        finally:
            if original is ...:
                del sys.modules["tools.claude_agent_runner"]
            else:
                sys.modules["tools.claude_agent_runner"] = original


class TestGeminiCLIRunnerDispatch:
    """GeminiCLIRunner run() 메서드 — 모의(mock) 기반 디스패치/파싱/에러 핸들링."""

    def _make_mock_proc(
        self,
        returncode: int = 0,
        stdout: bytes = b"",
        stderr: bytes = b"",
    ) -> MagicMock:
        """asyncio.create_subprocess_exec Mock 프로세스 객체 생성 헬퍼."""
        proc = MagicMock()
        proc.returncode = returncode
        proc.communicate = AsyncMock(return_value=(stdout, stderr))
        proc.kill = MagicMock()
        return proc

    async def test_run_returns_json_response(self) -> None:
        """정상 JSON 응답에서 'response' 필드를 반환한다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        payload = json.dumps({"response": "안녕하세요", "stats": {}}).encode()
        mock_proc = self._make_mock_proc(returncode=0, stdout=payload)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = GeminiCLIRunner()
            ctx = RunContext(prompt="인사해줘")
            result = await runner.run(ctx)

        assert result == "안녕하세요"
        metrics = runner.get_last_metrics()
        assert metrics["usage_source"] == "gemini_cli_json"

    async def test_run_fallback_plain_text_on_json_parse_failure(self) -> None:
        """JSON 파싱 실패 시 plain text로 폴백한다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        mock_proc = self._make_mock_proc(returncode=0, stdout=b"not a json response")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = GeminiCLIRunner()
            ctx = RunContext(prompt="테스트")
            result = await runner.run(ctx)

        assert result == "not a json response"
        assert runner.get_last_metrics()["usage_source"] == "gemini_cli_plain"

    async def test_run_raises_runner_error_on_nonzero_return_code(self) -> None:
        """CLI가 0이 아닌 return code를 반환하면 RunnerError를 발생시킨다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        mock_proc = self._make_mock_proc(returncode=1, stderr=b"command failed")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = GeminiCLIRunner()
            ctx = RunContext(prompt="에러 유발")
            with pytest.raises(RunnerError, match="code=1"):
                await runner.run(ctx)

    async def test_run_raises_timeout_error_on_timeout(self) -> None:
        """asyncio.TimeoutError 발생 시 RunnerTimeoutError를 발생시킨다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        proc = MagicMock()
        proc.kill = MagicMock()
        proc.communicate = AsyncMock(return_value=(b"", b""))

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                runner = GeminiCLIRunner()
                runner.timeout = 1
                ctx = RunContext(prompt="느린 작업")
                with pytest.raises(RunnerTimeoutError):
                    await runner.run(ctx)

    async def test_run_raises_runner_error_when_cli_not_found(self) -> None:
        """Gemini CLI 바이너리가 없으면 RunnerError를 발생시킨다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("No such file"),
        ):
            runner = GeminiCLIRunner()
            runner.cli_path = "/nonexistent/gemini"
            ctx = RunContext(prompt="실행 불가")
            with pytest.raises(RunnerError, match="Gemini CLI 없음"):
                await runner.run(ctx)

    async def test_run_with_engine_config_model(self) -> None:
        """engine_config에 model이 있으면 --model 플래그가 cmd에 포함된다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        captured_cmds: list[list[str]] = []
        payload = json.dumps({"response": "모델 설정됨", "stats": {}}).encode()

        async def mock_exec(*args, **kwargs):
            captured_cmds.append(list(args))
            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(payload, b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            runner = GeminiCLIRunner()
            ctx = RunContext(
                prompt="모델 테스트",
                engine_config={"model": "gemini-2.5-flash"},
            )
            result = await runner.run(ctx)

        assert result == "모델 설정됨"
        cmd = captured_cmds[0]
        assert "--model" in cmd
        assert "gemini-2.5-flash" in cmd

    async def test_run_sanitizes_noise_lines(self) -> None:
        """stdout에 노이즈 라인이 있으면 제거 후 파싱한다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        noise_prefix = b"loaded cached credentials\n"
        payload = json.dumps({"response": "클린 응답", "stats": {}}).encode()
        stdout = noise_prefix + payload

        mock_proc = self._make_mock_proc(returncode=0, stdout=stdout)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = GeminiCLIRunner()
            ctx = RunContext(prompt="노이즈 포함")
            result = await runner.run(ctx)

        assert result == "클린 응답"

    async def test_run_empty_response_returns_default(self) -> None:
        """response 필드가 빈 문자열이면 '(결과 없음)'을 반환한다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        payload = json.dumps({"response": "", "stats": {}}).encode()
        mock_proc = self._make_mock_proc(returncode=0, stdout=payload)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = GeminiCLIRunner()
            ctx = RunContext(prompt="빈 응답")
            result = await runner.run(ctx)

        assert result == "(결과 없음)"

    async def test_run_raises_runner_error_on_generic_exception(self) -> None:
        """예상치 못한 예외는 RunnerError로 래핑한다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=OSError("unexpected OS error"),
        ):
            runner = GeminiCLIRunner()
            ctx = RunContext(prompt="제네릭 에러")
            with pytest.raises(RunnerError, match="GeminiCLIRunner 예외"):
                await runner.run(ctx)

    async def test_run_with_token_stats(self) -> None:
        """stats.models 의 tokens.total 합산이 get_last_metrics()에 반영된다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        payload = json.dumps({
            "response": "토큰 통계 포함",
            "stats": {
                "models": {
                    "gemini-2.5-flash": {"tokens": {"total": 150}},
                    "embedding": {"tokens": {"total": 50}},
                }
            },
        }).encode()
        mock_proc = self._make_mock_proc(returncode=0, stdout=payload)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = GeminiCLIRunner()
            ctx = RunContext(prompt="토큰 통계 테스트")
            await runner.run(ctx)

        metrics = runner.get_last_metrics()
        assert metrics["total_tokens"] == 200
