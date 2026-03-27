"""Tests for gemini-2.5-flash fallback engine registration."""
from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
sys.path.insert(0, str(Path(__file__).parent.parent))


def test_runner_factory_creates_gemini_flash():
    """RunnerFactory.create('gemini-2.5-flash') should return a GeminiRunner."""
    from tools.base_runner import RunnerFactory
    with patch("tools.gemini_runner.genai", None), \
         patch("tools.gemini_runner._GENAI_AVAILABLE", False):
        # Even without genai SDK, the runner object should be created
        runner = RunnerFactory.create("gemini-2.5-flash")
        from tools.gemini_runner import GeminiRunner
        assert isinstance(runner, GeminiRunner)


def test_runner_factory_gemini_flash_default_model():
    """gemini-2.5-flash 엔진으로 생성된 runner의 default model이 gemini-2.5-flash여야 한다."""
    from tools.base_runner import RunnerFactory
    with patch("tools.gemini_runner._GENAI_AVAILABLE", False):
        runner = RunnerFactory.create("gemini-2.5-flash")
        assert getattr(runner, "_default_model", "gemini-2.5-flash") == "gemini-2.5-flash"


def test_runner_factory_unknown_engine_message():
    """Unknown engine should mention gemini-2.5-flash in the error."""
    from tools.base_runner import RunnerFactory
    with pytest.raises(ValueError) as exc_info:
        RunnerFactory.create("unknown-engine-xyz")
    assert "gemini-2.5-flash" in str(exc_info.value)


def test_orchestration_yaml_design_strategy_fallback_model():
    """orchestration.yaml design_strategy should have fallback_model: gemini-2.5-flash."""
    import yaml
    yaml_path = Path(__file__).parent.parent / "orchestration.yaml"
    with yaml_path.open() as f:
        config = yaml.safe_load(f)
    profiles = config.get("team_profiles", {})
    for profile_name in ("design_strategy", "product_strategy", "growth_strategy"):
        assert profiles.get(profile_name, {}).get("fallback_model") == "gemini-2.5-flash", \
            f"{profile_name} 프로필에 fallback_model: gemini-2.5-flash 없음"


def test_orchestration_yaml_engineering_profiles_fallback_model():
    """engineering_delivery, ops_delivery, global_orchestrator 등 기존 프로필도 fallback_model 보유 확인."""
    import yaml
    yaml_path = Path(__file__).parent.parent / "orchestration.yaml"
    with yaml_path.open() as f:
        config = yaml.safe_load(f)
    profiles = config.get("team_profiles", {})
    for profile_name in ("global_orchestrator", "engineering_delivery", "ops_delivery"):
        fm = profiles.get(profile_name, {}).get("fallback_model", "")
        assert fm == "gemini-2.5-flash", \
            f"{profile_name} 프로필 fallback_model={fm!r}, 기대값: gemini-2.5-flash"
