"""E2E: 3개 엔진(claude-code, codex, gemini-cli) 호환성 스모크 테스트.

system-overview.html Layer 4: 엔진 호환성 검증.
각 엔진이 정상 인스턴스화되고 RunContext를 받을 수 있는지 확인한다.
실제 CLI를 호출하지 않고 runner 객체 생성 및 인터페이스만 검증.
"""

from __future__ import annotations

import pytest

from tools.base_runner import BaseRunner, RunContext, RunnerFactory


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
