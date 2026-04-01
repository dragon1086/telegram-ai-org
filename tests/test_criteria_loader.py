"""tests/test_criteria_loader.py — CriteriaLoader 단위 테스트.

관련 태스크: RETRO-27
PRD 참조: docs/RETRO-33-criteria-tracking-pipeline-prd.md §5.2 / §5.4
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from tools.criteria_loader import (
    CriteriaFileNotFoundError,
    CriteriaLoader,
    ValidationError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_YAML = textwrap.dedent("""\
    metadata:
      criteria_version: "1.0.0"
      last_updated: "2026-03-31"
      updated_by: "test"
      change_reason: "unit test"

    changelog:
      - version: "1.0.0"
        date: "2026-03-31"
        author: "test"
        summary: "initial"

    thresholds:
      exit_code_143:
        description: "SIGTERM exit code 143 차단 기준"
        block_threshold: 3
        warn_threshold: 1
        unit: "occurrences"
        criteria_version: "1.0.0"
        prd_policy_ref: "test-prd §2.1"
        research_basis:
          decision_weight: "criteria"
          refs:
            - id: "ref-001"
              title: "테스트 레퍼런스"
              weight: "criteria"

      task_timeout_hard:
        description: "태스크 절대 타임아웃"
        block_threshold: 1800
        warn_threshold: 1200
        unit: "seconds"
        criteria_version: "1.0.0"
        prd_policy_ref: "infra-baseline §timeouts"
        research_basis:
          decision_weight: "criteria"
          refs: []

    integrations:
      development:
        auto_validate: true
        validate_on: ["pytest"]
        fail_on_version_mismatch: true
      operations:
        alert_rule_ref: "ALERT-04"
        notify_on_change: true
""")


@pytest.fixture
def criteria_yaml(tmp_path: Path) -> Path:
    """최소 스펙 YAML 파일을 tmp_path에 생성한다."""
    p = tmp_path / "criteria_tracking.yaml"
    p.write_text(MINIMAL_YAML, encoding="utf-8")
    return p


@pytest.fixture
def loader(criteria_yaml: Path) -> CriteriaLoader:
    """tmp_path 기반 CriteriaLoader 인스턴스."""
    return CriteriaLoader(base_dir=criteria_yaml.parent)


# ---------------------------------------------------------------------------
# load() 테스트
# ---------------------------------------------------------------------------

class TestLoad:
    def test_load_returns_dict(self, loader: CriteriaLoader) -> None:
        data = loader.load()
        assert isinstance(data, dict)

    def test_load_contains_metadata(self, loader: CriteriaLoader) -> None:
        data = loader.load()
        assert "metadata" in data
        assert data["metadata"]["criteria_version"] == "1.0.0"

    def test_load_contains_thresholds(self, loader: CriteriaLoader) -> None:
        data = loader.load()
        assert "thresholds" in data
        assert "exit_code_143" in data["thresholds"]

    def test_load_file_not_found_raises(self, tmp_path: Path) -> None:
        """V-01: 파일 없으면 CriteriaFileNotFoundError."""
        loader = CriteriaLoader(base_dir=tmp_path)
        with pytest.raises(CriteriaFileNotFoundError, match="V-01"):
            loader.load()

    def test_load_explicit_path(self, criteria_yaml: Path) -> None:
        loader = CriteriaLoader()
        data = loader.load(path=criteria_yaml)
        assert data["metadata"]["criteria_version"] == "1.0.0"


# ---------------------------------------------------------------------------
# get_threshold() 테스트
# ---------------------------------------------------------------------------

class TestGetThreshold:
    def test_exit_code_143_block_threshold(self, loader: CriteriaLoader) -> None:
        """exit_code_143 block_threshold = 3 (PRD 스펙 확인)."""
        result = loader.get_threshold("exit_code_143")
        assert result["block_threshold"] == 3

    def test_exit_code_143_warn_threshold(self, loader: CriteriaLoader) -> None:
        result = loader.get_threshold("exit_code_143")
        assert result["warn_threshold"] == 1

    def test_exit_code_143_criteria_version(self, loader: CriteriaLoader) -> None:
        result = loader.get_threshold("exit_code_143")
        assert result["criteria_version"] == "1.0.0"

    def test_returns_required_keys(self, loader: CriteriaLoader) -> None:
        result = loader.get_threshold("exit_code_143")
        for key in ("block_threshold", "warn_threshold", "criteria_version",
                    "description", "unit", "prd_policy_ref"):
            assert key in result, f"반환 dict에 '{key}' 키 누락"

    def test_task_timeout_hard_block_threshold(self, loader: CriteriaLoader) -> None:
        result = loader.get_threshold("task_timeout_hard")
        assert result["block_threshold"] == 1800

    def test_unknown_key_raises(self, loader: CriteriaLoader) -> None:
        with pytest.raises(KeyError, match="not found"):
            loader.get_threshold("nonexistent_key")

    def test_auto_load_on_first_call(self, criteria_yaml: Path) -> None:
        """load() 없이 get_threshold() 호출해도 자동 로드."""
        loader = CriteriaLoader(base_dir=criteria_yaml.parent)
        result = loader.get_threshold("exit_code_143")
        assert result["block_threshold"] == 3


# ---------------------------------------------------------------------------
# validate_version() 테스트
# ---------------------------------------------------------------------------

class TestValidateVersion:
    def test_matching_version_returns_true(self, loader: CriteriaLoader) -> None:
        loader.load()
        assert loader.validate_version("1.0.0") is True

    def test_mismatched_version_raises(self, loader: CriteriaLoader) -> None:
        """V-02: 버전 불일치 시 ValidationError."""
        loader.load()
        with pytest.raises(ValidationError, match="V-02"):
            loader.validate_version("2.0.0")

    def test_mismatched_version_error_message_contains_versions(
        self, loader: CriteriaLoader
    ) -> None:
        loader.load()
        with pytest.raises(ValidationError) as exc_info:
            loader.validate_version("9.9.9")
        msg = str(exc_info.value)
        assert "9.9.9" in msg
        assert "1.0.0" in msg

    def test_auto_load_on_validate(self, criteria_yaml: Path) -> None:
        """load() 없이 validate_version() 호출해도 자동 로드."""
        loader = CriteriaLoader(base_dir=criteria_yaml.parent)
        assert loader.validate_version("1.0.0") is True


# ---------------------------------------------------------------------------
# get_research_basis() 테스트
# ---------------------------------------------------------------------------

class TestGetResearchBasis:
    def test_returns_list(self, loader: CriteriaLoader) -> None:
        refs = loader.get_research_basis("exit_code_143")
        assert isinstance(refs, list)

    def test_refs_contain_expected_fields(self, loader: CriteriaLoader) -> None:
        refs = loader.get_research_basis("exit_code_143")
        assert len(refs) >= 1
        ref = refs[0]
        assert "id" in ref
        assert "title" in ref
        assert "weight" in ref

    def test_empty_refs_returns_empty_list(self, loader: CriteriaLoader) -> None:
        refs = loader.get_research_basis("task_timeout_hard")
        assert refs == []

    def test_unknown_key_raises(self, loader: CriteriaLoader) -> None:
        with pytest.raises(KeyError):
            loader.get_research_basis("nonexistent")


# ---------------------------------------------------------------------------
# get_metadata() / get_integration() 테스트
# ---------------------------------------------------------------------------

class TestMetadataAndIntegration:
    def test_get_metadata_criteria_version(self, loader: CriteriaLoader) -> None:
        meta = loader.get_metadata()
        assert meta["criteria_version"] == "1.0.0"

    def test_get_integration_development(self, loader: CriteriaLoader) -> None:
        dev = loader.get_integration("development")
        assert dev["auto_validate"] is True
        assert dev["fail_on_version_mismatch"] is True

    def test_get_integration_unknown_dept_raises(self, loader: CriteriaLoader) -> None:
        with pytest.raises(KeyError, match="not found"):
            loader.get_integration("nonexistent_dept")


# ---------------------------------------------------------------------------
# 실제 criteria_tracking.yaml 연동 (smoke test)
# ---------------------------------------------------------------------------

class TestRealYaml:
    """프로젝트 루트의 실제 criteria_tracking.yaml로 smoke test."""

    def test_real_yaml_loads(self) -> None:
        loader = CriteriaLoader()
        data = loader.load()
        assert data["metadata"]["criteria_version"] == "1.0.0"

    def test_real_yaml_exit_code_143(self) -> None:
        loader = CriteriaLoader()
        result = loader.get_threshold("exit_code_143")
        assert result["block_threshold"] == 3, (
            "exit_code_143 block_threshold는 PRD 스펙(=3)과 일치해야 합니다."
        )

    def test_real_yaml_version_validates(self) -> None:
        loader = CriteriaLoader()
        assert loader.validate_version("1.0.0") is True
