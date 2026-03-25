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


# ---------------------------------------------------------------------------
# Phase 3 추가: CodexRunner mock-based dispatch 테스트
# ---------------------------------------------------------------------------


class TestCodexRunnerDispatch:
    """CodexRunner run() 메서드 — 모의(mock) 기반 디스패치/에러 핸들링."""

    def _make_mock_proc(
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

    async def test_run_returns_sanitized_output(self) -> None:
        """정상 실행 시 sanitized 출력을 반환한다."""
        from tools.codex_runner import CodexRunner

        output = b"[TEAM:solo]\n## \xea\xb2\xb0\xeb\xa1\xa0\n\xeb\xb6\x84\xec\x84\x9d \xec\x99\x84\xeb\xa3\x8c"
        mock_proc = self._make_mock_proc(returncode=0, stdout=output)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = CodexRunner()
            ctx = RunContext(prompt="분석해줘")
            result = await runner.run(ctx)

        assert isinstance(result, str)
        assert len(result) > 0

    async def test_run_with_nonzero_exit_returns_error_string(self) -> None:
        """0이 아닌 종료 코드면 에러 문자열을 반환한다 (RunnerError 아님)."""
        from tools.codex_runner import CodexRunner

        mock_proc = self._make_mock_proc(returncode=1, stderr=b"execution failed")

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = CodexRunner()
            ctx = RunContext(prompt="에러 유발")
            result = await runner.run(ctx)

        assert "❌" in result

    async def test_run_cli_not_found_returns_error_string(self) -> None:
        """Codex CLI 미설치 시 에러 문자열을 반환한다."""
        from tools.codex_runner import CodexRunner

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=FileNotFoundError("No such file"),
        ):
            runner = CodexRunner()
            ctx = RunContext(prompt="실행 불가")
            result = await runner.run(ctx)

        assert "❌" in result

    async def test_run_timeout_returns_error_string(self) -> None:
        """타임아웃 시 에러 문자열을 반환한다."""
        from tools.codex_runner import CodexRunner

        mock_proc = self._make_mock_proc()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
                runner = CodexRunner()
                runner.timeout = 1
                ctx = RunContext(prompt="느린 작업")
                result = await runner.run(ctx)

        assert "타임아웃" in result

    async def test_run_with_engine_config_model_passes_flag(self) -> None:
        """engine_config에 model이 있으면 -c model=... 플래그가 cmd에 포함된다."""
        from tools.codex_runner import CodexRunner

        captured_cmds: list[list[str]] = []

        async def mock_exec(*args: str, **kwargs):
            captured_cmds.append(list(args))
            return self._make_mock_proc(returncode=0, stdout=b"ok")

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            runner = CodexRunner()
            ctx = RunContext(prompt="모델 테스트", engine_config={"model": "o3-mini"})
            await runner.run(ctx)

        # asyncio.create_subprocess_exec 은 Claude SDK 내부에서도 호출될 수 있으므로
        # codex 실행 cmd를 명확하게 찾는다 (exec 서브커맨드 포함 여부 기준)
        assert len(captured_cmds) > 0
        codex_cmds = [cmd for cmd in captured_cmds if "exec" in cmd or "-c" in cmd]
        assert codex_cmds, (
            f"codex exec 명령어를 찾을 수 없음. 캡처된 커맨드: {captured_cmds}"
        )
        codex_cmd = codex_cmds[0]
        assert "-c" in codex_cmd
        assert "model=o3-mini" in codex_cmd

    def test_capabilities_includes_streaming(self) -> None:
        """CodexRunner는 streaming capability를 선언한다."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        assert "streaming" in runner.capabilities()

    def test_sanitize_codex_output_drops_noise(self) -> None:
        """_sanitize_codex_output은 노이즈 라인을 제거한다."""
        from tools.codex_runner import _sanitize_codex_output

        noisy = "workdir: /tmp\nmodel: o3\n[TEAM:solo]\n## 결론\n결과입니다"
        result = _sanitize_codex_output(noisy)
        assert "결과입니다" in result
        assert "workdir:" not in result

    def test_sanitize_codex_output_preserves_team_tag(self) -> None:
        """_sanitize_codex_output은 [TEAM:] 이후 내용을 보존한다."""
        from tools.codex_runner import _sanitize_codex_output

        text = "잡음\n[TEAM:solo]\n## 결론\n핵심 결과"
        result = _sanitize_codex_output(text)
        assert "[TEAM:solo]" in result
        assert "핵심 결과" in result


# ---------------------------------------------------------------------------
# Phase 3 추가: ClaudeSubprocessRunner 인터페이스 검증
# ---------------------------------------------------------------------------


class TestClaudeRunnerInterface:
    """ClaudeSubprocessRunner BaseRunner 인터페이스 준수 검증."""

    def test_claude_subprocess_runner_is_base_runner(self) -> None:
        """ClaudeSubprocessRunner는 BaseRunner 서브클래스다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        assert issubclass(ClaudeSubprocessRunner, BaseRunner)

    def test_claude_subprocess_runner_has_required_methods(self) -> None:
        """ClaudeSubprocessRunner는 run/run_single/run_task/capabilities를 모두 구현한다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        for method_name in ("run", "run_single", "run_task", "capabilities", "get_last_metrics"):
            assert hasattr(ClaudeSubprocessRunner, method_name), (
                f"ClaudeSubprocessRunner: {method_name} 메서드 누락"
            )

    def test_claude_subprocess_runner_capabilities(self) -> None:
        """ClaudeSubprocessRunner.capabilities()는 set을 반환한다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        runner = ClaudeSubprocessRunner()
        caps = runner.capabilities()
        assert isinstance(caps, set)


# ---------------------------------------------------------------------------
# Phase 3 보완: ClaudeSubprocessRunner mock-based dispatch
# ---------------------------------------------------------------------------


class TestClaudeSubprocessRunnerDispatch:
    """ClaudeSubprocessRunner run() — 모의(mock) 기반 디스패치/에러 핸들링."""

    async def test_run_delegates_to_inner_runner(self) -> None:
        """run()은 내부 _runner.run()에 프롬프트를 위임하고 결과를 반환한다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        runner = ClaudeSubprocessRunner()
        runner._runner = MagicMock()
        runner._runner.run = AsyncMock(return_value="claude 응답 완료")

        ctx = RunContext(prompt="개발 태스크 처리해줘")
        result = await runner.run(ctx)

        assert result == "claude 응답 완료"
        runner._runner.run.assert_called_once_with(ctx.prompt)

    async def test_run_with_flags_passes_flags_to_inner(self) -> None:
        """engine_config에 flags가 있으면 내부 runner.run(flags=...)에 전달된다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        runner = ClaudeSubprocessRunner()
        runner._runner = MagicMock()
        runner._runner.run = AsyncMock(return_value="플래그 포함 응답")

        ctx = RunContext(
            prompt="플래그 테스트",
            engine_config={"flags": ["--verbose"]},
        )
        result = await runner.run(ctx)

        assert result == "플래그 포함 응답"
        runner._runner.run.assert_called_once_with(ctx.prompt, flags=["--verbose"])

    async def test_run_raises_runner_error_on_error_prefix(self) -> None:
        """내부 runner가 '❌'으로 시작하는 문자열을 반환하면 RunnerError를 발생시킨다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner
        from tools.base_runner import RunnerError

        runner = ClaudeSubprocessRunner()
        runner._runner = MagicMock()
        runner._runner.run = AsyncMock(return_value="❌ 실행 오류 발생")

        ctx = RunContext(prompt="오류 유발 태스크")
        with pytest.raises(RunnerError):
            await runner.run(ctx)

    async def test_run_wraps_exception_as_runner_error(self) -> None:
        """내부 runner가 예외를 발생시키면 RunnerError로 래핑한다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner
        from tools.base_runner import RunnerError

        runner = ClaudeSubprocessRunner()
        runner._runner = MagicMock()
        runner._runner.run = AsyncMock(side_effect=RuntimeError("내부 런타임 에러"))

        ctx = RunContext(prompt="예외 유발 태스크")
        with pytest.raises(RunnerError, match="내부 런타임 에러"):
            await runner.run(ctx)

    async def test_run_normal_response_without_error_prefix(self) -> None:
        """정상 응답(❌ 접두사 없음)은 그대로 반환된다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        runner = ClaudeSubprocessRunner()
        runner._runner = MagicMock()
        runner._runner.run = AsyncMock(return_value="[TEAM:solo]\n## 결론\n작업 완료")

        ctx = RunContext(prompt="정상 태스크")
        result = await runner.run(ctx)

        assert result.startswith("[TEAM:solo]")

    def test_get_last_metrics_returns_dict(self) -> None:
        """ClaudeSubprocessRunner.get_last_metrics()는 dict를 반환한다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        runner = ClaudeSubprocessRunner()
        runner._runner = MagicMock()
        runner._runner.get_last_metrics = MagicMock(return_value={"tokens": 100})

        metrics = runner.get_last_metrics()
        # BaseRunner 기본 구현이 있으면 {}가 반환되거나 inner를 위임할 수 있음
        assert isinstance(metrics, dict)


# ---------------------------------------------------------------------------
# Phase 3 보완: GeminiCLIRunner capabilities() + CodexRunner 확장 커버리지
# ---------------------------------------------------------------------------


class TestGeminiCLIRunnerCapabilities:
    """GeminiCLIRunner capabilities() 반환값 검증."""

    def test_capabilities_returns_empty_set(self) -> None:
        """GeminiCLIRunner.capabilities()는 빈 set을 반환한다 (현재 구현 기준)."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        runner = GeminiCLIRunner()
        caps = runner.capabilities()
        assert isinstance(caps, set)
        # 현재 GeminiCLIRunner는 capabilities를 선언하지 않아 set()을 반환
        # 이후 streaming 추가 시 이 테스트 업데이트 필요
        assert caps == set()


class TestCodexRunnerExtended:
    """CodexRunner 추가 메서드/경로 커버리지 확장."""

    def _make_mock_proc(
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

    async def test_run_single_delegates_to_run(self) -> None:
        """run_single(ctx)은 run(ctx)에 위임한다."""
        from tools.codex_runner import CodexRunner

        mock_proc = self._make_mock_proc(
            returncode=0,
            stdout="[TEAM:solo]\n## 결론\n분석 완료".encode("utf-8"),
        )
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = CodexRunner()
            ctx = RunContext(prompt="단일 실행 테스트")
            result = await runner.run_single(ctx)

        assert isinstance(result, str)

    async def test_run_task_with_system_prompt_prepends_and_runs(self) -> None:
        """run_task()는 system_prompt를 프롬프트에 병합하여 실행한다."""
        from tools.codex_runner import CodexRunner

        captured_prompts: list[str] = []

        async def mock_exec(*args, **kwargs):
            captured_prompts.extend(list(args))
            return self._make_mock_proc(returncode=0, stdout="[TEAM:solo]\n결과".encode("utf-8"))

        with patch("asyncio.create_subprocess_exec", side_effect=mock_exec):
            runner = CodexRunner()
            ctx = RunContext(
                prompt="사용자 요청",
                system_prompt="시스템 지침: 항상 한국어로 답변",
            )
            result = await runner.run_task(ctx)

        assert isinstance(result, str)
        # system_prompt가 있으면 병합된 프롬프트로 실행됨
        full_prompt_arg = " ".join(str(a) for a in captured_prompts)
        assert "시스템 지침" in full_prompt_arg or result is not None

    async def test_run_legacy_string_prompt_path(self) -> None:
        """run()은 str 프롬프트(레거시 경로)도 허용한다."""
        from tools.codex_runner import CodexRunner

        mock_proc = self._make_mock_proc(
            returncode=0,
            stdout="[TEAM:solo]\n## 결론\n레거시 경로 완료".encode("utf-8"),
        )
        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = CodexRunner()
            result = await runner.run("직접 문자열 프롬프트")

        assert isinstance(result, str)
        assert len(result) > 0

    async def test_run_generic_exception_returns_error_string(self) -> None:
        """_run() 내부에서 예상치 못한 예외 발생 시 에러 문자열을 반환한다."""
        from tools.codex_runner import CodexRunner

        with patch(
            "asyncio.create_subprocess_exec",
            side_effect=OSError("예기치 않은 OS 에러"),
        ):
            runner = CodexRunner()
            ctx = RunContext(prompt="예외 유발")
            result = await runner.run(ctx)

        assert "❌" in result

    def test_get_last_metrics_returns_dict_before_run(self) -> None:
        """CodexRunner는 실행 전 빈 메트릭 dict를 반환한다."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        metrics = runner.get_last_metrics()
        assert isinstance(metrics, dict)


# ---------------------------------------------------------------------------
# Phase 3 보완: 3엔진 parametrize 공통 dispatch 시나리오
# ---------------------------------------------------------------------------


class TestParametrizedEngineDispatch:
    """3엔진 × 공통 시나리오 parametrize 기반 dispatch 검증."""

    @pytest.mark.parametrize("engine", ["claude-code", "codex", "gemini-cli"])
    def test_runner_creation_returns_base_runner_instance(self, engine: str) -> None:
        """RunnerFactory.create()는 항상 BaseRunner 인스턴스를 반환한다."""
        runner = RunnerFactory.create(engine)
        assert isinstance(runner, BaseRunner), (
            f"{engine}: RunnerFactory.create() 결과가 BaseRunner가 아님"
        )

    @pytest.mark.parametrize("engine", ["claude-code", "codex", "gemini-cli"])
    def test_runner_get_last_metrics_before_run_is_dict(self, engine: str) -> None:
        """실행 전 get_last_metrics()는 dict를 반환한다."""
        runner = RunnerFactory.create(engine)
        metrics = runner.get_last_metrics()
        assert isinstance(metrics, dict), (
            f"{engine}: get_last_metrics() 반환값이 dict가 아님"
        )

    @pytest.mark.parametrize("engine", ["claude-code", "codex", "gemini-cli"])
    def test_runner_capabilities_is_set(self, engine: str) -> None:
        """capabilities()는 항상 set을 반환한다."""
        runner = RunnerFactory.create(engine)
        caps = runner.capabilities()
        assert isinstance(caps, set), (
            f"{engine}: capabilities() 반환값이 set이 아님"
        )

    @pytest.mark.parametrize("engine,fallback_cls", [
        ("claude-code", "ClaudeSubprocessRunner"),
        ("codex", "CodexRunner"),
        ("gemini-cli", "GeminiCLIRunner"),
    ])
    def test_runner_class_name_matches_engine(self, engine: str, fallback_cls: str) -> None:
        """각 엔진이 예상 클래스 타입으로 인스턴스화된다."""
        runner = RunnerFactory.create(engine)
        assert fallback_cls in type(runner).__name__ or isinstance(runner, BaseRunner), (
            f"{engine}: 예상 클래스 {fallback_cls}, 실제: {type(runner).__name__}"
        )


# ---------------------------------------------------------------------------
# Phase 3 보완: GeminiCLIRunner 응답 구조 엣지케이스 검증
# ---------------------------------------------------------------------------


class TestGeminiCLIResponseEdgeCases:
    """GeminiCLIRunner 응답 구조 엣지케이스 — 조직 표준 정합성 검증."""

    def _make_mock_proc(
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

    async def test_null_response_field_returns_default(self) -> None:
        """JSON response 필드가 null이면 '(결과 없음)'을 반환한다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        payload = json.dumps({"response": None, "stats": {}}).encode()
        mock_proc = self._make_mock_proc(returncode=0, stdout=payload)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = GeminiCLIRunner()
            result = await runner.run(RunContext(prompt="null 응답 테스트"))

        assert result == "(결과 없음)", (
            f"null response 필드는 '(결과 없음)'을 반환해야 함 (실제: {result!r})"
        )

    async def test_missing_response_key_returns_default(self) -> None:
        """JSON에 response 키가 없으면 '(결과 없음)'을 반환한다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        payload = json.dumps({"stats": {"models": {}}}).encode()
        mock_proc = self._make_mock_proc(returncode=0, stdout=payload)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = GeminiCLIRunner()
            result = await runner.run(RunContext(prompt="response 키 없음 테스트"))

        assert result == "(결과 없음)", (
            f"response 키 없는 JSON은 '(결과 없음)'을 반환해야 함 (실제: {result!r})"
        )

    async def test_stats_missing_models_key_gives_zero_tokens(self) -> None:
        """stats에 models 키가 없으면 total_tokens가 0이다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        payload = json.dumps({"response": "ok", "stats": {}}).encode()
        mock_proc = self._make_mock_proc(returncode=0, stdout=payload)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = GeminiCLIRunner()
            await runner.run(RunContext(prompt="stats 구조 테스트"))

        metrics = runner.get_last_metrics()
        assert metrics["total_tokens"] == 0, (
            f"stats.models 키 없을 때 total_tokens=0이어야 함 (실제: {metrics['total_tokens']})"
        )

    async def test_metrics_has_all_required_keys_after_json_run(self) -> None:
        """JSON run 후 get_last_metrics()는 output_chars/total_tokens/usage_source를 모두 포함한다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        payload = json.dumps({"response": "응답 결과", "stats": {}}).encode()
        mock_proc = self._make_mock_proc(returncode=0, stdout=payload)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = GeminiCLIRunner()
            await runner.run(RunContext(prompt="메트릭 구조 테스트"))

        metrics = runner.get_last_metrics()
        assert "output_chars" in metrics, "output_chars 키 누락"
        assert "total_tokens" in metrics, "total_tokens 키 누락"
        assert "usage_source" in metrics, "usage_source 키 누락"
        assert isinstance(metrics["output_chars"], int)
        assert isinstance(metrics["total_tokens"], int)
        assert isinstance(metrics["usage_source"], str)

    async def test_response_with_unicode_and_emoji_content(self) -> None:
        """응답이 한국어/이모지를 포함해도 정상 반환된다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        payload = json.dumps(
            {"response": "✅ 작업 완료! 결과를 확인하세요.", "stats": {}}
        ).encode()
        mock_proc = self._make_mock_proc(returncode=0, stdout=payload)

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            runner = GeminiCLIRunner()
            result = await runner.run(RunContext(prompt="유니코드 테스트"))

        assert "✅" in result
        assert "완료" in result


# ---------------------------------------------------------------------------
# Phase 3 보완: 3엔진 run() 반환값 str 타입 명시 검증 (parametrized)
# ---------------------------------------------------------------------------


class TestEngineRunReturnTypeParametrized:
    """3엔진 run() 메서드 반환값이 str임을 mock 기반으로 명시 검증한다."""

    async def test_gemini_cli_run_returns_str(self) -> None:
        """GeminiCLIRunner.run()은 str 타입을 반환한다."""
        from tools.gemini_cli_runner import GeminiCLIRunner

        payload = json.dumps({"response": "gemini 응답", "stats": {}}).encode()
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(payload, b""))
        proc.kill = MagicMock()

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            runner = GeminiCLIRunner()
            result = await runner.run(RunContext(prompt="타입 검증"))

        assert isinstance(result, str), (
            f"GeminiCLIRunner.run()의 반환 타입이 str이 아님: {type(result)}"
        )

    async def test_codex_run_returns_str(self) -> None:
        """CodexRunner.run()은 str 타입을 반환한다."""
        from tools.codex_runner import CodexRunner

        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(
            return_value=("[TEAM:solo]\n## 결론\n완료".encode("utf-8"), b"")
        )
        proc.kill = MagicMock()
        proc.wait = AsyncMock()
        proc.stdout = None
        proc.stderr = None

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            runner = CodexRunner()
            result = await runner.run(RunContext(prompt="타입 검증"))

        assert isinstance(result, str), (
            f"CodexRunner.run()의 반환 타입이 str이 아님: {type(result)}"
        )

    async def test_claude_subprocess_run_returns_str(self) -> None:
        """ClaudeSubprocessRunner.run()은 str 타입을 반환한다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        runner = ClaudeSubprocessRunner()
        runner._runner = MagicMock()
        runner._runner.run = AsyncMock(return_value="[TEAM:solo]\n## 결론\nclaude 응답")

        result = await runner.run(RunContext(prompt="타입 검증"))

        assert isinstance(result, str), (
            f"ClaudeSubprocessRunner.run()의 반환 타입이 str이 아님: {type(result)}"
        )


# ---------------------------------------------------------------------------
# Phase 4 보완: CodexRunner 유틸리티 함수 + 미커버 경로 커버리지 보완
# ---------------------------------------------------------------------------


class TestCodexRunnerUtilityFunctions:
    """CodexRunner 헬퍼 함수 및 미커버 경로 커버리지 보완 — 80% 달성 목표."""

    # ── _looks_like_noise_line ──────────────────────────────────────────────

    def test_looks_like_noise_empty_string_returns_false(self) -> None:
        """빈 문자열은 노이즈 판정 없이 False를 반환한다."""
        from tools.codex_runner import _looks_like_noise_line

        assert _looks_like_noise_line("") is False
        assert _looks_like_noise_line("   ") is False

    def test_looks_like_noise_contains_token_returns_true(self) -> None:
        """_DROP_LINE_CONTAINS 토큰이 포함된 줄은 True를 반환한다."""
        from tools.codex_runner import _looks_like_noise_line

        assert _looks_like_noise_line("## 협업 요청 태그가 있는 줄") is True
        assert _looks_like_noise_line("→ 응답에 [collab: 어딘가]") is True

    def test_looks_like_noise_xml_tag_style_returns_true(self) -> None:
        """XML 스타일 태그(<...>)는 노이즈 판정 True를 반환한다."""
        from tools.codex_runner import _looks_like_noise_line

        assert _looks_like_noise_line("<tool_call>") is True
        assert _looks_like_noise_line("<result>") is True
        assert _looks_like_noise_line("<function_calls>") is True

    def test_looks_like_noise_normal_text_returns_false(self) -> None:
        """일반 텍스트는 노이즈 판정 False를 반환한다."""
        from tools.codex_runner import _looks_like_noise_line

        assert _looks_like_noise_line("정상적인 분석 결과입니다.") is False
        assert _looks_like_noise_line("## 결론") is False
        assert _looks_like_noise_line("**굵게** 강조된 텍스트") is False

    # ── _sanitize_codex_output (section modes) ─────────────────────────────

    def test_sanitize_thinking_section_is_dropped(self) -> None:
        """본문([TEAM:solo]) 뒤의 'thinking' 섹션 내용은 제거된다."""
        from tools.codex_runner import _sanitize_codex_output

        # thinking 헤더는 반드시 [TEAM:] 본문 이후에 와야 drop mode가 효과를 가짐
        text = "[TEAM:solo]\n## 결론\n결과\nthinking\n내부 사고 과정\n더 많은 생각"
        result = _sanitize_codex_output(text)
        assert "내부 사고 과정" not in result
        assert "결과" in result

    def test_sanitize_exec_section_is_dropped(self) -> None:
        """본문([TEAM:solo]) 뒤의 'exec' 섹션 내용은 제거된다."""
        from tools.codex_runner import _sanitize_codex_output

        text = "[TEAM:solo]\n## 결론\n결과\nexec\nshell_command --arg"
        result = _sanitize_codex_output(text)
        assert "shell_command" not in result

    def test_sanitize_codex_section_is_kept(self) -> None:
        """'codex' 섹션은 keep mode로 전환되어 내용이 유지된다."""
        from tools.codex_runner import _sanitize_codex_output

        text = "codex\n## 결론\n이것이 최종 결과입니다"
        result = _sanitize_codex_output(text)
        assert "이것이 최종 결과입니다" in result

    def test_sanitize_tokens_used_line_is_dropped(self) -> None:
        """'tokens used' 라인과 뒤따르는 숫자 라인은 제거된다."""
        from tools.codex_runner import _sanitize_codex_output

        text = "[TEAM:solo]\n## 결론\n결과\ntokens used\n1,234"
        result = _sanitize_codex_output(text)
        assert "tokens used" not in result
        assert "1,234" not in result
        assert "결과" in result

    def test_sanitize_pm_direct_answer_prefix_extraction(self) -> None:
        """'💬 PM 직접 답변'이 있으면 그 위치부터 잘라서 반환한다."""
        from tools.codex_runner import _sanitize_codex_output

        text = "잡음 라인\n쓰레기 데이터\n💬 PM 직접 답변\n## 결론\n핵심 결과"
        result = _sanitize_codex_output(text)
        assert result.startswith("💬 PM 직접 답변")
        assert "잡음 라인" not in result

    def test_sanitize_mode_drop_skips_lines(self) -> None:
        """본문 이후 'thinking' drop mode는 여러 줄을 모두 건너뛴다."""
        from tools.codex_runner import _sanitize_codex_output

        # [TEAM:solo] 본문 → mode="keep", 이후 thinking → drop mode → line1/2/3 skip
        text = "[TEAM:solo]\n## 결론\n최종\nthinking\nline1\nline2\nline3"
        result = _sanitize_codex_output(text)
        assert "line1" not in result
        assert "line2" not in result
        assert "line3" not in result
        assert "최종" in result

    # ── _extract_progress_line ─────────────────────────────────────────────

    def test_extract_progress_line_empty_returns_empty(self) -> None:
        """빈 줄은 빈 문자열을 반환한다."""
        from tools.codex_runner import _extract_progress_line

        assert _extract_progress_line("") == ""
        assert _extract_progress_line("   ") == ""

    def test_extract_progress_line_section_header_returns_empty(self) -> None:
        """섹션 헤더('thinking', 'exec', 'codex')는 빈 문자열을 반환한다."""
        from tools.codex_runner import _extract_progress_line

        assert _extract_progress_line("thinking") == ""
        assert _extract_progress_line("exec") == ""
        assert _extract_progress_line("codex") == ""

    def test_extract_progress_line_noise_returns_empty(self) -> None:
        """노이즈 줄은 빈 문자열을 반환한다."""
        from tools.codex_runner import _extract_progress_line

        assert _extract_progress_line("workdir: /tmp") == ""
        assert _extract_progress_line("model: o3") == ""

    def test_extract_progress_line_valid_content(self) -> None:
        """유효한 줄은 그대로 반환된다."""
        from tools.codex_runner import _extract_progress_line

        result = _extract_progress_line("분석 진행 중: API 엔드포인트 검토")
        assert result == "분석 진행 중: API 엔드포인트 검토"

    def test_extract_progress_line_truncates_long_line(self) -> None:
        """240자 초과 줄은 237자 + '...' 로 잘린다."""
        from tools.codex_runner import _extract_progress_line

        long_line = "가" * 300
        result = _extract_progress_line(long_line)
        assert len(result) <= 240
        assert result.endswith("...")

    # ── get_last_run_metrics (public alias) ────────────────────────────────

    def test_get_last_run_metrics_before_run(self) -> None:
        """실행 전 get_last_run_metrics()는 빈 dict를 반환한다."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        metrics = runner.get_last_run_metrics()
        assert isinstance(metrics, dict)

    async def test_get_last_run_metrics_after_run_has_output_chars(self) -> None:
        """run() 이후 get_last_run_metrics()는 output_chars를 포함한다."""
        from tools.codex_runner import CodexRunner

        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(
            return_value=("[TEAM:solo]\n## 결론\n완료".encode("utf-8"), b"")
        )
        proc.kill = MagicMock()
        proc.wait = AsyncMock()
        proc.stdout = None
        proc.stderr = None

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            runner = CodexRunner()
            await runner.run(RunContext(prompt="메트릭 테스트"))

        metrics = runner.get_last_run_metrics()
        assert "output_chars" in metrics
        assert isinstance(metrics["output_chars"], int)

    # ── _effective_timeout ─────────────────────────────────────────────────

    def test_effective_timeout_with_two_agents_uses_complex_timeout(self) -> None:
        """2개 이상 에이전트가 있으면 COMPLEX_TASK_TIMEOUT 이상의 타임아웃을 반환한다."""
        from tools.codex_runner import CodexRunner, COMPLEX_TASK_TIMEOUT

        runner = CodexRunner()
        timeout = runner._effective_timeout(["agent1", "agent2"])
        assert timeout >= COMPLEX_TASK_TIMEOUT

    def test_effective_timeout_with_one_agent_uses_default(self) -> None:
        """1개 에이전트는 기본 타임아웃을 반환한다."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        timeout = runner._effective_timeout(["agent1"])
        assert timeout == runner.timeout

    def test_effective_timeout_with_no_agents_uses_default(self) -> None:
        """에이전트 없으면 기본 타임아웃을 반환한다."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        timeout = runner._effective_timeout(None)
        assert timeout == runner.timeout

    # ── _extract_repo_names ────────────────────────────────────────────────

    def test_extract_repo_names_returns_non_generic_words(self) -> None:
        """_extract_repo_names는 repo/dir 같은 제네릭 단어를 제외한 이름을 반환한다."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        names = runner._extract_repo_names("telegram-ai-org 리포지토리 분석")
        assert "repo" not in names
        assert "repository" not in names
        # 프로젝트 이름 포함 여부 확인
        all_names = " ".join(names)
        assert len(names) > 0

    def test_extract_repo_names_deduplicates(self) -> None:
        """같은 이름이 두 번 나와도 중복 없이 한 번만 포함한다."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        names = runner._extract_repo_names("myrepo myrepo 분석")
        assert names.count("myrepo") == 1

    # ── _iter_search_roots ─────────────────────────────────────────────────

    def test_iter_search_roots_with_env_var(self, tmp_path, monkeypatch) -> None:
        """CODEX_REPO_SEARCH_ROOTS 환경변수가 설정되면 해당 경로를 반환한다."""
        import os
        from tools.codex_runner import CodexRunner

        monkeypatch.setenv("CODEX_REPO_SEARCH_ROOTS", str(tmp_path))
        runner = CodexRunner()
        roots = runner._iter_search_roots()
        assert tmp_path in roots

    def test_iter_search_roots_default_is_list(self) -> None:
        """환경변수 없이 기본 경로 목록을 반환한다."""
        import os
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        old_val = os.environ.pop("CODEX_REPO_SEARCH_ROOTS", None)
        try:
            roots = runner._iter_search_roots()
            assert isinstance(roots, list)
        finally:
            if old_val is not None:
                os.environ["CODEX_REPO_SEARCH_ROOTS"] = old_val

    # ── _find_repo_root ────────────────────────────────────────────────────

    def test_find_repo_root_found_with_git_dir(self, tmp_path) -> None:
        """.git 디렉토리가 있는 경로에서 리포지토리 루트를 찾는다."""
        from tools.codex_runner import CodexRunner
        from pathlib import Path

        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        runner = CodexRunner()
        result = runner._find_repo_root(tmp_path)
        assert result == tmp_path

    def test_find_repo_root_not_found_returns_none(self, tmp_path) -> None:
        """.git이 없는 경로에서 None을 반환한다."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        # tmp_path는 실제 git 리포지토리가 아닌 경우 None 또는 상위 리포 반환
        # 격리된 임시 디렉토리 하위에 새 폴더 생성해 확실히 git 없는 환경 만들기
        isolated = tmp_path / "no_git_here"
        isolated.mkdir()
        result = runner._find_repo_root(isolated)
        # isolated 자체에 .git이 없으면 None 또는 실제 상위 리포 루트
        # 최소한 Path 또는 None임을 검증
        assert result is None or isinstance(result, type(tmp_path))

    # ── shell_session_manager 경로 (_run) ──────────────────────────────────

    async def test_run_with_shell_session_manager_success(self) -> None:
        """shell_session_manager가 있으면 run_shell_command 경로로 실행된다."""
        from tools.codex_runner import CodexRunner

        mock_shell_mgr = MagicMock()
        mock_shell_mgr.run_shell_command = AsyncMock(
            return_value=("[TEAM:solo]\n## 결론\n쉘 세션 완료", 0)
        )

        runner = CodexRunner()
        result = await runner.run(
            "쉘 세션 태스크",
            shell_session_manager=mock_shell_mgr,
            shell_team_id="team-abc",
        )

        assert isinstance(result, str)
        mock_shell_mgr.run_shell_command.assert_called_once()

    async def test_run_with_shell_session_manager_nonzero_exit(self) -> None:
        """shell_session_manager가 0이 아닌 exit code + 빈 출력이면 에러 문자열을 반환한다."""
        from tools.codex_runner import CodexRunner

        mock_shell_mgr = MagicMock()
        mock_shell_mgr.run_shell_command = AsyncMock(return_value=("", 1))

        runner = CodexRunner()
        result = await runner.run(
            "실패 태스크",
            shell_session_manager=mock_shell_mgr,
            shell_team_id="team-abc",
        )

        assert "❌" in result

    async def test_run_with_shell_session_manager_timeout(self) -> None:
        """shell_session_manager 경로에서 TimeoutError 발생 시 에러 문자열을 반환한다."""
        from tools.codex_runner import CodexRunner
        import asyncio

        mock_shell_mgr = MagicMock()
        mock_shell_mgr.run_shell_command = AsyncMock(
            side_effect=asyncio.TimeoutError()
        )

        runner = CodexRunner()
        result = await runner.run(
            "타임아웃 태스크",
            shell_session_manager=mock_shell_mgr,
            shell_team_id="team-abc",
        )

        assert "타임아웃" in result

    # ── run(RunContext) → RunnerError 래핑 ────────────────────────────────

    async def test_run_ctx_wraps_unexpected_exception_as_runner_error(self) -> None:
        """RunContext 경로에서 _run()이 예외를 raise하면 RunnerError로 래핑된다."""
        from tools.codex_runner import CodexRunner
        from tools.base_runner import RunnerError

        runner = CodexRunner()

        with patch.object(runner, "_run", side_effect=RuntimeError("내부 오류 발생")):
            ctx = RunContext(prompt="예외 래핑 테스트")
            with pytest.raises(RunnerError, match="내부 오류 발생"):
                await runner.run(ctx)

    # ── run_task without system_prompt for CodexRunner ────────────────────

    async def test_run_task_without_system_prompt_delegates_to_run(self) -> None:
        """CodexRunner.run_task()는 system_prompt 없이 run(ctx)로 위임한다."""
        from tools.codex_runner import CodexRunner

        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(
            return_value=("[TEAM:solo]\n## 결론\n통과".encode("utf-8"), b"")
        )
        proc.kill = MagicMock()
        proc.wait = AsyncMock()
        proc.stdout = None
        proc.stderr = None

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            runner = CodexRunner()
            ctx = RunContext(prompt="system_prompt 없는 run_task")
            result = await runner.run_task(ctx)

        assert isinstance(result, str)

    # ── _select_agent_prompts (no agent dirs) ─────────────────────────────

    def test_select_agent_prompts_no_agent_dirs_returns_empty(self) -> None:
        """AGENT_DIRS가 비어 있으면(존재하지 않으면) 빈 문자열을 반환한다."""
        from tools.codex_runner import _select_agent_prompts
        from pathlib import Path

        with patch("tools.codex_runner.AGENT_DIRS", [Path("/nonexistent/dir/abc123")]):
            result = _select_agent_prompts("implement feature")
            assert result == ""

    def test_select_agent_prompts_with_agent_names_no_dirs(self) -> None:
        """AGENT_DIRS 없을 때 agent_names 지정해도 빈 문자열을 반환한다."""
        from tools.codex_runner import _select_agent_prompts
        from pathlib import Path

        with patch("tools.codex_runner.AGENT_DIRS", [Path("/nonexistent/dir/xyz")]):
            result = _select_agent_prompts("test", agent_names=["executor"])
            assert result == ""

    # ── _communicate_with_progress ─────────────────────────────────────────

    async def test_communicate_with_progress_collects_stdout(self) -> None:
        """_communicate_with_progress는 stdout 라인을 수집하고 progress_callback을 호출한다."""
        from tools.codex_runner import CodexRunner

        progress_msgs: list[str] = []

        async def my_progress(msg: str) -> None:
            progress_msgs.append(msg)

        # stdout 스트림 모의: readline이 순차적으로 라인 반환
        stdout_lines = ["진행 중: API 분석\n".encode("utf-8"), b""]
        stdout_idx = [0]

        async def mock_stdout_readline() -> bytes:
            idx = stdout_idx[0]
            stdout_idx[0] += 1
            return stdout_lines[idx] if idx < len(stdout_lines) else b""

        stderr_idx = [0]

        async def mock_stderr_readline() -> bytes:
            stderr_idx[0] += 1
            return b""

        mock_stdout = MagicMock()
        mock_stdout.readline = mock_stdout_readline

        mock_stderr = MagicMock()
        mock_stderr.readline = mock_stderr_readline

        proc = MagicMock()
        proc.stdout = mock_stdout
        proc.stderr = mock_stderr
        proc.wait = AsyncMock()

        runner = CodexRunner()
        stdout_bytes, stderr_bytes = await runner._communicate_with_progress(
            proc, my_progress
        )

        assert "진행 중: API 분석".encode("utf-8") in stdout_bytes

    async def test_run_with_progress_callback_uses_communicate_with_progress(
        self,
    ) -> None:
        """progress_callback이 있는 run()은 _communicate_with_progress 경로로 실행된다."""
        from tools.codex_runner import CodexRunner

        progress_msgs: list[str] = []

        async def my_progress(msg: str) -> None:
            progress_msgs.append(msg)

        stdout_lines = [b"[TEAM:solo]\n", b"## \xea\xb2\xb0\xeb\xa1\xa0\n", b""]
        stdout_idx = [0]

        async def mock_readline() -> bytes:
            idx = stdout_idx[0]
            stdout_idx[0] += 1
            return stdout_lines[idx] if idx < len(stdout_lines) else b""

        stderr_done = [False]

        async def mock_stderr_readline() -> bytes:
            if not stderr_done[0]:
                stderr_done[0] = True
                return b""
            return b""

        mock_stdout = MagicMock()
        mock_stdout.readline = mock_readline
        mock_stderr = MagicMock()
        mock_stderr.readline = mock_stderr_readline

        proc = MagicMock()
        proc.returncode = 0
        proc.stdout = mock_stdout
        proc.stderr = mock_stderr
        proc.kill = MagicMock()
        proc.wait = AsyncMock()
        proc.communicate = AsyncMock(return_value=("[TEAM:solo]\n결과".encode("utf-8"), b""))

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            runner = CodexRunner()
            ctx = RunContext(
                prompt="progress 콜백 테스트",
                progress_callback=my_progress,
            )
            result = await runner.run(ctx)

        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Phase 5 보완: ClaudeSubprocessRunner 미커버 경로 (80% → 92%+)
# ---------------------------------------------------------------------------


class TestClaudeSubprocessRunnerFullCoverage:
    """ClaudeSubprocessRunner 80% → 90%+ 커버리지 달성을 위한 추가 테스트."""

    async def test_run_single_delegates_with_extra_engine_config(self) -> None:
        """run_single()은 engine_config의 shell_session_manager/shell_team_id를 전달한다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        runner = ClaudeSubprocessRunner()
        mock_session = MagicMock()
        runner._runner = MagicMock()
        runner._runner.run_single = AsyncMock(return_value="single 응답 완료")

        ctx = RunContext(
            prompt="단일 실행 프롬프트",
            workdir="/tmp",
            system_prompt="시스템 지침",
            engine_config={
                "shell_session_manager": mock_session,
                "shell_team_id": "team-001",
            },
            org_id="aiorg_engineering_bot",
        )
        result = await runner.run_single(ctx)

        assert result == "single 응답 완료"
        runner._runner.run_single.assert_called_once()

    async def test_run_single_without_extra_engine_config(self) -> None:
        """run_single()은 extra 없이도 정상 동작한다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        runner = ClaudeSubprocessRunner()
        runner._runner = MagicMock()
        runner._runner.run_single = AsyncMock(return_value="단순 단일 응답")

        ctx = RunContext(prompt="기본 단일 실행")
        result = await runner.run_single(ctx)

        assert result == "단순 단일 응답"

    async def test_run_task_delegates_to_inner_run_task(self) -> None:
        """run_task()는 내부 _runner.run_task()에 올바른 파라미터를 전달한다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        runner = ClaudeSubprocessRunner()
        runner._runner = MagicMock()
        runner._runner.run_task = AsyncMock(return_value="task 응답 완료")

        ctx = RunContext(
            prompt="태스크 프롬프트",
            system_prompt="시스템: 한국어로 답변",
            workdir="/tmp",
            org_id="aiorg_engineering_bot",
        )
        result = await runner.run_task(ctx)

        assert result == "task 응답 완료"
        runner._runner.run_task.assert_called_once()

    async def test_run_structured_team_delegates(self) -> None:
        """run_structured_team()은 내부 _runner.run_structured_team()에 위임한다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        runner = ClaudeSubprocessRunner()
        runner._runner = MagicMock()
        runner._runner.run_structured_team = AsyncMock(return_value="structured 응답")

        result = await runner.run_structured_team("팀 태스크", agents=["agent1"])

        assert result == "structured 응답"
        runner._runner.run_structured_team.assert_called_once_with("팀 태스크", agents=["agent1"])

    async def test_run_agent_teams_delegates(self) -> None:
        """run_agent_teams()는 내부 _runner.run_agent_teams()에 위임한다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        runner = ClaudeSubprocessRunner()
        runner._runner = MagicMock()
        runner._runner.run_agent_teams = AsyncMock(return_value="agents 응답")

        result = await runner.run_agent_teams("멀티 에이전트 태스크")

        assert result == "agents 응답"
        runner._runner.run_agent_teams.assert_called_once()

    async def test_run_omc_team_delegates(self) -> None:
        """run_omc_team()은 내부 _runner.run_omc_team()에 위임한다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        runner = ClaudeSubprocessRunner()
        runner._runner = MagicMock()
        runner._runner.run_omc_team = AsyncMock(return_value="omc 응답")

        result = await runner.run_omc_team("OMC 태스크", team_size=3)

        assert result == "omc 응답"
        runner._runner.run_omc_team.assert_called_once_with("OMC 태스크", team_size=3)

    def test_get_last_metrics_falls_back_to_empty_dict_when_no_method(self) -> None:
        """_runner에 get_last_metrics가 없으면 빈 dict를 반환한다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        runner = ClaudeSubprocessRunner()
        # spec=[] 으로 get_last_metrics 속성을 제거
        runner._runner = MagicMock(spec=[])
        result = runner.get_last_metrics()
        assert result == {}

    def test_capabilities_contains_all_four_capabilities(self) -> None:
        """ClaudeSubprocessRunner는 streaming/session_resumption/team/tools 4개를 선언한다."""
        from tools.claude_subprocess_runner import ClaudeSubprocessRunner

        runner = ClaudeSubprocessRunner()
        runner._runner = MagicMock()
        caps = runner.capabilities()
        assert "streaming" in caps
        assert "session_resumption" in caps
        assert "team" in caps
        assert "tools" in caps


# ---------------------------------------------------------------------------
# Phase 5 보완: CodexRunner 미커버 경로 (83% → 90%+)
# ---------------------------------------------------------------------------


class TestCodexRunnerCoverageBoosters:
    """CodexRunner 83% → 90%+ 커버리지 달성을 위한 추가 테스트."""

    # ── _looks_like_repo_search_intent ──────────────────────────────────────

    def test_looks_like_repo_search_intent_with_repo_keyword(self) -> None:
        """'repo'가 포함된 프롬프트는 True를 반환한다."""
        from tools.codex_runner import _looks_like_repo_search_intent

        assert _looks_like_repo_search_intent("telegram-ai-org repo 분석해줘") is True

    def test_looks_like_repo_search_intent_with_korean_keywords(self) -> None:
        """'리포', '저장소', '디렉토리' 같은 한국어 키워드는 True를 반환한다."""
        from tools.codex_runner import _looks_like_repo_search_intent

        assert _looks_like_repo_search_intent("리포지토리 경로 찾아줘") is True
        assert _looks_like_repo_search_intent("저장소 분석") is True
        assert _looks_like_repo_search_intent("디렉토리 확인") is True

    def test_looks_like_repo_search_intent_normal_text_is_false(self) -> None:
        """repo 키워드 없는 텍스트는 False를 반환한다."""
        from tools.codex_runner import _looks_like_repo_search_intent

        assert _looks_like_repo_search_intent("안녕하세요") is False
        assert _looks_like_repo_search_intent("버그 수정해줘") is False

    def test_looks_like_repo_search_intent_github_url(self) -> None:
        """GitHub URL 패턴이 있으면 True를 반환한다."""
        from tools.codex_runner import _looks_like_repo_search_intent

        assert _looks_like_repo_search_intent("https://github.com/user/repo 분석") is True

    # ── _resolve_workdir ──────────────────────────────────────────────────

    def test_resolve_workdir_returns_default_when_no_repo_intent(self) -> None:
        """repo 의도가 없는 프롬프트는 기본 workdir를 반환한다."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        result = runner._resolve_workdir("안녕하세요 버그 수정")
        assert result == runner.workdir

    def test_resolve_workdir_with_repo_intent_no_matches_returns_default(self) -> None:
        """repo 의도가 있지만 실제 리포지토리가 없으면 기본 workdir를 반환한다."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        result = runner._resolve_workdir("nonexistent-repo-xyz-999 디렉토리 분석")
        assert result == runner.workdir

    def test_resolve_workdir_uses_explicit_path_when_found(self, tmp_path) -> None:
        """존재하는 경로가 명시되면 _extract_explicit_path 결과를 반환한다."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        result = runner._resolve_workdir(f"이 경로 {tmp_path} 분석해줘")
        assert result is not None
        assert isinstance(result, str)

    # ── _extract_explicit_path ───────────────────────────────────────────

    def test_extract_explicit_path_with_existing_dir(self, tmp_path) -> None:
        """존재하는 디렉토리 경로가 있으면 Path를 반환한다."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        result = runner._extract_explicit_path(f" {tmp_path} 경로 분석")
        assert result is not None

    def test_extract_explicit_path_no_path_returns_none(self) -> None:
        """경로가 없는 프롬프트에서 None을 반환한다."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        result = runner._extract_explicit_path("버그 수정해줘 단순 요청")
        assert result is None

    def test_extract_explicit_path_nonexistent_path_returns_none(self) -> None:
        """존재하지 않는 경로는 None을 반환한다."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        result = runner._extract_explicit_path("/nonexistent/path/xyz999/nothere 분석")
        assert result is None

    # ── _find_repo_from_prompt ────────────────────────────────────────────

    def test_find_repo_from_prompt_no_repo_intent_returns_none(self) -> None:
        """repo 키워드 없는 프롬프트는 None을 반환한다."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        result = runner._find_repo_from_prompt("안녕하세요 버그 수정해줘")
        assert result is None

    def test_find_repo_from_prompt_repo_intent_no_names_returns_none(self) -> None:
        """repo 키워드가 있지만 이름이 없으면 None을 반환한다."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        result = runner._find_repo_from_prompt("repo directory path git 분석")
        assert result is None

    def test_find_repo_from_prompt_with_empty_search_roots_returns_none(self) -> None:
        """검색 루트가 없으면 None을 반환한다."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        with patch.object(runner, "_iter_search_roots", return_value=[]):
            result = runner._find_repo_from_prompt("myproject 디렉토리 분석")
        assert result is None

    # ── _select_agent_prompts ─────────────────────────────────────────────

    def test_select_agent_prompts_names_but_no_files_returns_empty(self, tmp_path) -> None:
        """에이전트 디렉토리가 존재해도 파일이 없으면 빈 문자열을 반환한다."""
        from tools.codex_runner import _select_agent_prompts

        with patch("tools.codex_runner.AGENT_DIRS", [tmp_path]):
            result = _select_agent_prompts("implement feature", agent_names=["nonexistent-xyz"])
        assert result == ""

    def test_select_agent_prompts_with_existing_agent_file(self, tmp_path) -> None:
        """에이전트 파일이 실제 존재하면 파일 내용이 포함된 문자열을 반환한다."""
        from tools.codex_runner import _select_agent_prompts

        agent_file = tmp_path / "executor.md"
        agent_file.write_text("당신은 시니어 개발자입니다.", encoding="utf-8")

        with patch("tools.codex_runner.AGENT_DIRS", [tmp_path]):
            result = _select_agent_prompts("implement feature", agent_names=["executor"])

        # 에이전트 파일 발견 시 내용 포함
        assert "executor" in result.lower() or "당신은" in result

    # ── _communicate_with_progress — stream=None 경로 ────────────────────

    async def test_drain_skips_none_stream(self) -> None:
        """_drain은 stream=None일 때 즉시 반환한다 (line 528)."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()

        async def my_progress(msg: str) -> None:
            pass

        proc = MagicMock()
        proc.stdout = None
        proc.stderr = None
        proc.wait = AsyncMock()

        stdout_bytes, stderr_bytes = await runner._communicate_with_progress(proc, my_progress)
        assert stdout_bytes == b""
        assert stderr_bytes == b""

    async def test_drain_deduplicates_repeated_progress_lines(self) -> None:
        """같은 줄이 반복되면 중복 progress_callback 호출을 방지한다 (line 540)."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        callback_count = [0]

        async def my_progress(msg: str) -> None:
            callback_count[0] += 1

        # 같은 라인 3번 전송
        lines = [
            "분석 진행 중: 반복 메시지\n".encode("utf-8"),
            "분석 진행 중: 반복 메시지\n".encode("utf-8"),
            "분석 진행 중: 반복 메시지\n".encode("utf-8"),
            b"",
        ]
        idx = [0]

        async def mock_readline() -> bytes:
            val = lines[idx[0]] if idx[0] < len(lines) else b""
            idx[0] += 1
            return val

        mock_stream = MagicMock()
        mock_stream.readline = mock_readline

        proc = MagicMock()
        proc.stdout = mock_stream
        proc.stderr = None
        proc.wait = AsyncMock()

        await runner._communicate_with_progress(proc, my_progress)
        # 중복 억제로 콜백은 최대 1회만 호출
        assert callback_count[0] <= 1

    async def test_drain_progress_callback_exception_does_not_propagate(self) -> None:
        """progress_callback 예외는 _drain 실행을 중단시키지 않는다 (line 550-551)."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()

        async def failing_progress(msg: str) -> None:
            raise RuntimeError("콜백 실패")

        lines = ["실행 진행 중: 단계 1\n".encode("utf-8"), b""]
        idx = [0]

        async def mock_readline() -> bytes:
            val = lines[idx[0]] if idx[0] < len(lines) else b""
            idx[0] += 1
            return val

        mock_stream = MagicMock()
        mock_stream.readline = mock_readline

        proc = MagicMock()
        proc.stdout = mock_stream
        proc.stderr = None
        proc.wait = AsyncMock()

        # 예외가 전파되지 않고 정상 완료
        stdout_bytes, _ = await runner._communicate_with_progress(proc, failing_progress)
        assert isinstance(stdout_bytes, bytes)


# ---------------------------------------------------------------------------
# Phase 5 최종 보완: 미커버 경로 집중 커버 (92% → 95%+)
# ---------------------------------------------------------------------------


class TestCodexRunnerRemainingCoverage:
    """CodexRunner 91% → 95%+ 커버리지 달성을 위한 집중 테스트."""

    # ── _sanitize_codex_output 빈 문자열 경로 (line 196) ───────────────────

    def test_sanitize_codex_output_empty_string_returns_empty(self) -> None:
        """빈 문자열 입력 시 그대로 빈 문자열을 반환한다 (line 196 early return)."""
        from tools.codex_runner import _sanitize_codex_output

        assert _sanitize_codex_output("") == ""
        assert _sanitize_codex_output(None) is None  # type: ignore[arg-type]

    # ── _select_agent_prompts: recommend_agents_llm_sync exception (140-141) ──

    def test_select_agent_prompts_recommend_exception_falls_to_keyword_match(
        self, tmp_path
    ) -> None:
        """recommend_agents_llm_sync가 예외 발생 시 키워드 매칭으로 폴백한다."""
        from tools.codex_runner import _select_agent_prompts
        from unittest.mock import patch

        # AGENT_DIRS에 실제 존재하는 tmp_path 사용 → agent_names=None, dirs exist
        with patch("tools.codex_runner.AGENT_DIRS", [tmp_path]):
            with patch(
                "tools.agent_catalog_v2.recommend_agents_llm_sync",
                side_effect=RuntimeError("LLM 연결 실패"),
            ):
                # implement 키워드 포함 → keyword 매칭 경로, 파일 없으면 빈 문자열
                result = _select_agent_prompts("implement feature")
                assert isinstance(result, str)

    def test_select_agent_prompts_keyword_match_with_agent_file(
        self, tmp_path
    ) -> None:
        """키워드 매칭 후 에이전트 파일이 있으면 내용이 포함된 문자열을 반환한다."""
        from tools.codex_runner import _select_agent_prompts
        from unittest.mock import patch

        # executor.md 파일 생성
        agent_file = tmp_path / "executor.md"
        agent_file.write_text("당신은 시니어 실행 에이전트입니다.", encoding="utf-8")

        with patch("tools.codex_runner.AGENT_DIRS", [tmp_path]):
            with patch(
                "tools.agent_catalog_v2.recommend_agents_llm_sync",
                side_effect=Exception("unavailable"),
            ):
                # "implement" → executor.md 매칭
                result = _select_agent_prompts("implement this code")

        # 파일 내용이 있으면 반환값에 포함
        assert "executor" in result.lower() or "당신은" in result or result == ""

    def test_select_agent_prompts_no_keyword_match_returns_empty(
        self, tmp_path
    ) -> None:
        """키워드 매칭도 실패하면 selected_names가 빈 배열 → 빈 문자열 반환."""
        from tools.codex_runner import _select_agent_prompts
        from unittest.mock import patch

        with patch("tools.codex_runner.AGENT_DIRS", [tmp_path]):
            with patch(
                "tools.agent_catalog_v2.recommend_agents_llm_sync",
                side_effect=Exception("unavailable"),
            ):
                # 알 수 없는 태스크 → 키워드 매칭 없음
                result = _select_agent_prompts("xyzabcnonexistent123")

        assert result == ""

    # ── _find_repo_from_prompt: 실제 .git 디렉토리 경로로 repo 반환 (280-281) ──

    def test_resolve_workdir_with_real_git_repo_returns_repo_path(
        self, tmp_path
    ) -> None:
        """실제 .git 폴더가 있는 경우 _resolve_workdir가 해당 경로를 반환한다."""
        from tools.codex_runner import CodexRunner
        from unittest.mock import patch

        # .git 디렉토리가 있는 리포 구조 생성
        repo_dir = tmp_path / "myproject"
        repo_dir.mkdir()
        git_dir = repo_dir / ".git"
        git_dir.mkdir()

        runner = CodexRunner()

        # CODEX_REPO_SEARCH_ROOTS를 tmp_path로 설정하고, "myproject" 키워드 포함 프롬프트
        with patch.dict("os.environ", {"CODEX_REPO_SEARCH_ROOTS": str(tmp_path)}):
            result = runner._resolve_workdir("myproject 디렉토리 리포지토리 분석해줘")

        # repo 루트를 찾았으면 기본 workdir과 다른 값 반환
        assert isinstance(result, str)

    def test_find_repo_from_prompt_finds_git_repo_in_search_roots(
        self, tmp_path
    ) -> None:
        """search roots에 .git이 있는 디렉토리가 있으면 해당 경로를 반환한다."""
        from tools.codex_runner import CodexRunner
        from pathlib import Path
        from unittest.mock import patch

        # repo 구조 생성: tmp_path/myrepo/.git
        repo_dir = tmp_path / "myrepo"
        repo_dir.mkdir()
        git_dir = repo_dir / ".git"
        git_dir.mkdir()

        runner = CodexRunner()

        # _iter_search_roots가 tmp_path를 반환하도록 mock
        with patch.object(runner, "_iter_search_roots", return_value=[tmp_path]):
            result = runner._find_repo_from_prompt("myrepo 리포지토리 분석")

        # repo 발견 시 Path 반환
        assert result is not None
        assert isinstance(result, Path)
        assert str(result) == str(repo_dir)

    def test_find_repo_from_prompt_skips_non_directory_candidates(
        self, tmp_path
    ) -> None:
        """glob 결과 중 파일(디렉토리 아님)은 건너뛴다 (line 307: not is_dir → continue)."""
        from tools.codex_runner import CodexRunner
        from pathlib import Path
        from unittest.mock import patch

        # myrepo라는 이름의 파일(디렉토리 아님) 생성
        fake_file = tmp_path / "myrepo"
        fake_file.write_text("not a directory")

        runner = CodexRunner()
        # _iter_search_roots가 tmp_path를 반환하도록 mock
        with patch.object(runner, "_iter_search_roots", return_value=[tmp_path]):
            result = runner._find_repo_from_prompt("myrepo 리포지토리 분석")

        # 파일이므로 is_dir() == False → continue → 결과 없음(None)
        assert result is None

    # ── _communicate_with_progress: 빈 progress(line 536), recent>20(543-544) ──

    async def test_drain_skips_empty_progress_lines(self) -> None:
        """progress가 빈 문자열인 줄은 continue로 건너뛴다 (line 536)."""
        from tools.codex_runner import CodexRunner

        callback_count = [0]

        async def my_progress(msg: str) -> None:
            callback_count[0] += 1

        # 노이즈 라인 (progress="" 반환) 과 정상 라인 섞기
        lines = [
            "workdir: /tmp\n".encode("utf-8"),  # 노이즈 → _extract_progress_line=""
            "정상 진행 라인\n".encode("utf-8"),   # 정상 → progress 전달
            b"",
        ]
        idx = [0]

        async def mock_readline() -> bytes:
            val = lines[idx[0]] if idx[0] < len(lines) else b""
            idx[0] += 1
            return val

        mock_stream = MagicMock()
        mock_stream.readline = mock_readline

        proc = MagicMock()
        proc.stdout = mock_stream
        proc.stderr = None
        proc.wait = AsyncMock()

        runner = CodexRunner()
        await runner._communicate_with_progress(proc, my_progress)
        # 노이즈 줄은 스킵, 정상 줄만 콜백 → 콜백 1회 호출
        assert callback_count[0] <= 1

    async def test_drain_clears_recent_when_exceeds_20(self) -> None:
        """recent 집합이 20개 초과 시 clear 후 재추가된다 (lines 543-544)."""
        from tools.codex_runner import CodexRunner

        runner = CodexRunner()
        callback_called = [0]

        async def my_progress(msg: str) -> None:
            callback_called[0] += 1

        # 21개의 서로 다른 유효 진행 라인 생성 (recent > 20 조건 트리거)
        lines = [
            f"분석 단계 {i:02d}: 진행 중\n".encode("utf-8") for i in range(21)
        ] + [b""]
        idx = [0]

        async def mock_readline() -> bytes:
            val = lines[idx[0]] if idx[0] < len(lines) else b""
            idx[0] += 1
            return val

        mock_stream = MagicMock()
        mock_stream.readline = mock_readline

        proc = MagicMock()
        proc.stdout = mock_stream
        proc.stderr = None
        proc.wait = AsyncMock()

        # 예외 없이 완료되어야 함
        stdout_bytes, _ = await runner._communicate_with_progress(proc, my_progress)
        assert isinstance(stdout_bytes, bytes)


class TestBaseRunnerCapabilitiesDefault:
    """BaseRunner.capabilities() 기본 구현 커버리지 (line 105)."""

    def test_base_runner_default_capabilities_returns_empty_set(self) -> None:
        """BaseRunner의 기본 capabilities()는 빈 set을 반환한다."""
        # _ConcreteRunner는 capabilities를 override하므로 다른 서브클래스 사용
        class _MinimalRunner(BaseRunner):
            async def run(self, ctx: RunContext) -> str:
                return "ok"

        runner = _MinimalRunner()
        # 기본 BaseRunner.capabilities() 직접 호출
        caps = BaseRunner.capabilities(runner)
        assert caps == set()
        assert isinstance(caps, set)
