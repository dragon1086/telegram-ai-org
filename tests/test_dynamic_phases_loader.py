"""동적 phase 로더 테스트.

_FALLBACK_DEPTS / _DEFAULT_PHASES 하드코딩 제거 후 동작 검증.
- load_known_depts(): bots/*.yaml 없을 때 빈 dict 반환
- load_default_phases(): bots/*.yaml + default_phases.yaml 정상 로드
- regression: 기존 하드코딩 값과 동적 로드 결과 동일
- edge cases: 잘못된 YAML, phase_templates 없는 YAML, _default 없는 케이스
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.constants import (
    load_default_phases,
    load_known_depts,
)

# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def tmp_bots_dir(tmp_path: Path) -> Path:
    """임시 bots/ 디렉토리."""
    return tmp_path / "bots"


def _write_bot_yaml(bots_dir: Path, org_id: str, extra: dict | None = None) -> Path:
    """간단한 봇 YAML 작성 헬퍼."""
    bots_dir.mkdir(parents=True, exist_ok=True)
    data: dict = {
        "schema_version": 2,
        "org_id": org_id,
        "dept_name": f"{org_id}_dept",
        "engine": "claude-code",
        "role": f"{org_id} role",
        "instruction": f"{org_id} instruction",
        "is_pm": False,
    }
    if extra:
        data.update(extra)
    path = bots_dir / f"{org_id}.yaml"
    path.write_text(yaml.dump(data, allow_unicode=True))
    return path


# ── load_known_depts ──────────────────────────────────────────


class TestLoadKnownDepts:
    """_FALLBACK_DEPTS 제거 후 load_known_depts() 검증."""

    def test_empty_on_missing_dir(self, tmp_path: Path):
        """bots/ 디렉토리 없으면 빈 dict 반환 (하드코딩 없음)."""
        result = load_known_depts(tmp_path / "nonexistent")
        assert result == {}, "하드코딩 fallback 없이 빈 dict 반환해야 함"

    def test_empty_on_empty_dir(self, tmp_bots_dir: Path):
        """bots/ 디렉토리는 있지만 YAML 없으면 빈 dict."""
        tmp_bots_dir.mkdir()
        result = load_known_depts(tmp_bots_dir)
        assert result == {}

    def test_loads_dept_from_yaml(self, tmp_bots_dir: Path):
        """YAML 에서 dept_name 정상 로드."""
        _write_bot_yaml(tmp_bots_dir, "test_bot")
        result = load_known_depts(tmp_bots_dir)
        assert "test_bot" in result
        assert result["test_bot"] == "test_bot_dept"

    def test_excludes_pm_bots(self, tmp_bots_dir: Path):
        """is_pm: true 봇은 제외."""
        _write_bot_yaml(tmp_bots_dir, "pm_bot", {"is_pm": True})
        _write_bot_yaml(tmp_bots_dir, "worker_bot")
        result = load_known_depts(tmp_bots_dir)
        assert "pm_bot" not in result
        assert "worker_bot" in result

    def test_no_aiorg_hardcoding(self, tmp_bots_dir: Path):
        """빈 dir 시 aiorg_* 값이 절대 포함되지 않아야 함."""
        tmp_bots_dir.mkdir()
        result = load_known_depts(tmp_bots_dir)
        aiorg_keys = [k for k in result if k.startswith("aiorg_")]
        assert aiorg_keys == [], f"하드코딩된 aiorg 키 발견: {aiorg_keys}"

    def test_regression_main_bots_dir(self):
        """실제 bots/ 디렉토리 로드 — aiorg 5개 봇 모두 존재해야 함."""
        result = load_known_depts()
        expected = {
            "aiorg_product_bot", "aiorg_engineering_bot",
            "aiorg_design_bot", "aiorg_growth_bot", "aiorg_ops_bot",
        }
        assert expected.issubset(result.keys()), (
            f"누락된 봇: {expected - result.keys()}"
        )


# ── load_default_phases ───────────────────────────────────────


class TestLoadDefaultPhases:
    """_DEFAULT_PHASES 제거 후 load_default_phases() 검증."""

    def test_empty_on_missing_dir(self, tmp_path: Path):
        """bots/ 디렉토리 없으면 빈 dict."""
        result = load_default_phases(tmp_path / "nonexistent")
        assert result == {}

    def test_loads_phase_templates_from_yaml(self, tmp_bots_dir: Path):
        """YAML 의 phase_templates 필드 정상 로드."""
        templates = {
            "simple": [{"name": "구현", "instructions": "구현하세요.", "deliverables": ["코드"]}],
        }
        _write_bot_yaml(tmp_bots_dir, "test_bot", {"phase_templates": templates})
        result = load_default_phases(tmp_bots_dir)
        assert "test_bot" in result
        assert result["test_bot"]["simple"][0]["name"] == "구현"

    def test_bot_without_phase_templates_excluded(self, tmp_bots_dir: Path):
        """phase_templates 없는 봇은 결과에서 제외."""
        _write_bot_yaml(tmp_bots_dir, "no_template_bot")
        result = load_default_phases(tmp_bots_dir)
        assert "no_template_bot" not in result

    def test_loads_default_from_separate_yaml(self, tmp_bots_dir: Path):
        """default_phases.yaml 의 _default 키 로드."""
        tmp_bots_dir.mkdir(parents=True, exist_ok=True)
        default_data = {
            "_default": {
                "simple": [{"name": "실행", "instructions": "실행.", "deliverables": ["결과"]}],
            }
        }
        (tmp_bots_dir / "default_phases.yaml").write_text(
            yaml.dump(default_data, allow_unicode=True)
        )
        result = load_default_phases(tmp_bots_dir)
        assert "_default" in result
        assert result["_default"]["simple"][0]["name"] == "실행"

    def test_invalid_yaml_does_not_crash(self, tmp_bots_dir: Path):
        """default_phases.yaml 이 깨진 YAML 이어도 크래시 없이 빈 _default."""
        tmp_bots_dir.mkdir(parents=True, exist_ok=True)
        (tmp_bots_dir / "default_phases.yaml").write_text("invalid: [yaml: :")
        # Should not raise
        result = load_default_phases(tmp_bots_dir)
        assert "_default" not in result  # graceful: 로드 실패 시 포함 안 됨

    def test_regression_all_aiorg_bots_have_phases(self):
        """실제 bots/*.yaml 로드 — 5개 봇 모두 phase_templates 있어야 함."""
        result = load_default_phases()
        expected_bots = {
            "aiorg_product_bot", "aiorg_engineering_bot",
            "aiorg_design_bot", "aiorg_growth_bot", "aiorg_ops_bot",
        }
        for bot in expected_bots:
            assert bot in result, f"{bot} phase_templates 없음"
            for complexity in ("simple", "moderate", "complex"):
                assert complexity in result[bot], f"{bot}.{complexity} 없음"
                assert len(result[bot][complexity]) >= 1, f"{bot}.{complexity} 비어있음"

    def test_regression_default_key_exists(self):
        """실제 bots/default_phases.yaml — _default 키 존재해야 함."""
        result = load_default_phases()
        assert "_default" in result, "default_phases.yaml 에 _default 키 없음"

    def test_regression_moderate_has_multiple_phases(self):
        """moderate 복잡도는 2개 이상의 phase 를 가져야 함."""
        result = load_default_phases()
        for bot in ("aiorg_engineering_bot", "aiorg_product_bot"):
            assert len(result[bot]["moderate"]) >= 2, (
                f"{bot}.moderate phase 수 부족: {len(result[bot]['moderate'])}"
            )

    def test_regression_complex_has_four_phases(self):
        """complex 복잡도는 4개 phase 를 가져야 함."""
        result = load_default_phases()
        for bot in ("aiorg_engineering_bot", "aiorg_product_bot"):
            assert len(result[bot]["complex"]) >= 4, (
                f"{bot}.complex phase 수 부족: {len(result[bot]['complex'])}"
            )


# ── structured_prompt 통합 ────────────────────────────────────


class TestStructuredPromptIntegration:
    """_DEFAULT_PHASES 제거 후 _template_generate() 동작 검증."""

    @pytest.fixture(autouse=True)
    def _import_gen(self):
        from core.structured_prompt import StructuredPromptGenerator, TaskComplexity
        self.gen = StructuredPromptGenerator()
        self.Complexity = TaskComplexity

    def test_engineering_simple_has_one_phase(self):
        result = self.gen._template_generate(
            "버그 수정", "aiorg_engineering_bot", self.Complexity.SIMPLE, ""
        )
        assert len(result.phases) == 1

    def test_engineering_moderate_has_multiple_phases(self):
        result = self.gen._template_generate(
            "API 구현", "aiorg_engineering_bot", self.Complexity.MODERATE, ""
        )
        assert len(result.phases) >= 2

    def test_engineering_complex_has_four_phases(self):
        result = self.gen._template_generate(
            "아키텍처 설계", "aiorg_engineering_bot", self.Complexity.COMPLEX, ""
        )
        assert len(result.phases) >= 4

    def test_all_depts_have_moderate_templates(self):
        depts = [
            "aiorg_product_bot", "aiorg_engineering_bot",
            "aiorg_design_bot", "aiorg_growth_bot", "aiorg_ops_bot",
        ]
        for dept in depts:
            result = self.gen._template_generate(
                "작업", dept, self.Complexity.MODERATE, ""
            )
            assert len(result.phases) >= 2, f"{dept} moderate phase 부족"

    def test_unknown_dept_uses_default(self):
        result = self.gen._template_generate(
            "작업", "unknown_bot", self.Complexity.SIMPLE, ""
        )
        assert len(result.phases) >= 1

    def test_description_embedded_in_instructions(self):
        result = self.gen._template_generate(
            "로그인 페이지 디자인", "aiorg_design_bot", self.Complexity.MODERATE, ""
        )
        for phase in result.phases:
            assert "로그인 페이지 디자인" in phase.instructions
