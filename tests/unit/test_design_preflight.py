"""tests/unit/test_design_preflight.py — design_preflight_check.py 단위 테스트.

RETRO-11: tools/design_preflight_check.py 의 PC-D-001~016 체크 함수 및
run_design_preflight_checks() / build_design_preflight_header_result() 인터페이스 검증.

테스트 범주:
- TestModuleInterface: 모듈 로드 및 run_design_preflight_checks() 표준 인터페이스
- TestPcD001~016: 각 체크 함수 pass/fail 케이스
- TestBuildHeaderResult: conftest.py 헤더 출력용 dict 빌드 검증
- TestSkipBehavior: SKIP_DESIGN_PREFLIGHT / SKIP_PREFLIGHT 환경변수 동작
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

import pytest

# ---------------------------------------------------------------------------
# 모듈 경로
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent.parent
_MODULE_PATH = _PROJECT_ROOT / "tools" / "design_preflight_check.py"


def _load() -> ModuleType:
    """design_preflight_check.py 를 importlib으로 로드."""
    spec = importlib.util.spec_from_file_location("design_preflight_check", _MODULE_PATH)
    assert spec and spec.loader, f"모듈 로드 실패: {_MODULE_PATH}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# 픽스처: 전체 PASS 기준 데이터
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_data() -> dict:
    """PC-D-001~016 전체 PASS 기준 데이터."""
    return {
        "schema_version": 1,
        "baseline_version": "v1.2",
        "infra_baseline_version": "v1.2",
        "viewport": {
            "default_width": 1440,
            "pixel_ratio": 1,
            "device_presets": "desktop",
        },
        "typography": {
            "base_font_size": 16,
            "font_family_primary": "Pretendard",
            "rendering_engine": "antialiased",
            "line_height_base": 1.5,
        },
        "theme": {
            "contrast_ratio_min": 4.5,
            "wcag_level": "AA",
            "active_mode": "light",
            "focus_visible_outline": "2px solid #2563EB",
            "color_token_version": "v1.0",
            "motion_safe": True,
        },
        "component_library": {
            "version": "1.4.2",
            "package_name": "@aiorg/design-system",
        },
        "design_tools": {
            "figma": {"version": "116.x"},
            "storybook": {"version": "7.6.17"},
        },
        "retry_policy": {
            "max_retries": 2,
        },
    }


@pytest.fixture
def valid_yaml(tmp_path, valid_data) -> Path:
    """유효한 design-baseline.yaml 임시 파일."""
    try:
        import yaml
        content = yaml.dump(valid_data, allow_unicode=True)
    except ImportError:
        # PyYAML 없으면 간이 직렬화
        lines = [
            "schema_version: 1",
            "baseline_version: v1.2",
            "infra_baseline_version: v1.2",
            "viewport:",
            "  default_width: 1440",
            "  pixel_ratio: 1",
            "  device_presets: desktop",
            "typography:",
            "  base_font_size: 16",
            "  font_family_primary: Pretendard",
            "  rendering_engine: antialiased",
            "  line_height_base: 1.5",
            "theme:",
            "  contrast_ratio_min: 4.5",
            "  wcag_level: AA",
            "  active_mode: light",
            "  focus_visible_outline: 2px solid #2563EB",
            "  color_token_version: v1.0",
            "  motion_safe: true",
            "component_library:",
            "  version: 1.4.2",
            "  package_name: '@aiorg/design-system'",
            "design_tools:",
            "  figma:",
            "    version: 116.x",
            "  storybook:",
            "    version: 7.6.17",
            "retry_policy:",
            "  max_retries: 2",
        ]
        content = "\n".join(lines)
    path = tmp_path / "design-baseline.yaml"
    path.write_text(content, encoding="utf-8")
    return path


# ===========================================================================
# 1. 모듈 인터페이스
# ===========================================================================

class TestModuleInterface:
    def test_module_loads(self):
        """모듈이 에러 없이 로드된다."""
        mod = _load()
        assert mod is not None

    def test_run_design_preflight_checks_exists(self):
        """run_design_preflight_checks 함수가 존재한다."""
        mod = _load()
        assert callable(getattr(mod, "run_design_preflight_checks", None))

    def test_build_design_preflight_header_result_exists(self):
        """build_design_preflight_header_result 함수가 존재한다."""
        mod = _load()
        assert callable(getattr(mod, "build_design_preflight_header_result", None))

    def test_returns_dict(self, valid_yaml):
        """run_design_preflight_checks() 가 dict를 반환한다."""
        mod = _load()
        result = mod.run_design_preflight_checks(
            baseline_path=str(valid_yaml), exit_on_fail=False
        )
        assert isinstance(result, dict)

    def test_required_keys_present(self, valid_yaml):
        """반환 dict에 RETRO-11 표준 키가 모두 있다."""
        mod = _load()
        result = mod.run_design_preflight_checks(
            baseline_path=str(valid_yaml), exit_on_fail=False
        )
        for key in (
            "passed", "blocking_results", "warning_results",
            "info_results", "design_baseline_version", "checked_at",
        ):
            assert key in result, f"필수 키 '{key}' 없음"

    def test_passed_is_bool(self, valid_yaml):
        """passed 값이 bool이다."""
        mod = _load()
        result = mod.run_design_preflight_checks(
            baseline_path=str(valid_yaml), exit_on_fail=False
        )
        assert isinstance(result["passed"], bool)

    def test_results_are_lists(self, valid_yaml):
        """blocking/warning/info_results 가 모두 list다."""
        mod = _load()
        result = mod.run_design_preflight_checks(
            baseline_path=str(valid_yaml), exit_on_fail=False
        )
        assert isinstance(result["blocking_results"], list)
        assert isinstance(result["warning_results"], list)
        assert isinstance(result["info_results"], list)

    def test_valid_data_passes(self, valid_yaml):
        """유효한 baseline으로 passed=True를 반환한다."""
        mod = _load()
        result = mod.run_design_preflight_checks(
            baseline_path=str(valid_yaml), exit_on_fail=False
        )
        assert result["passed"] is True, (
            f"유효한 데이터로 passed=False: "
            f"{[r for r in result['blocking_results'] if not r['passed']]}"
        )

    def test_file_not_found_returns_fail(self, tmp_path):
        """파일 없으면 passed=False 반환."""
        mod = _load()
        result = mod.run_design_preflight_checks(
            baseline_path=str(tmp_path / "nonexistent.yaml"),
            exit_on_fail=False,
        )
        assert result["passed"] is False

    def test_blocking_count_is_six(self, valid_yaml):
        """blocking 체크 항목은 6개 (PC-D-001/003/005/006/007/008)."""
        mod = _load()
        result = mod.run_design_preflight_checks(
            baseline_path=str(valid_yaml), exit_on_fail=False
        )
        assert len(result["blocking_results"]) == 6, (
            f"blocking 체크 수가 6이 아님: {len(result['blocking_results'])}"
        )

    def test_warning_count_is_eight(self, valid_yaml):
        """warning 체크 항목은 8개 (PC-D-002/004/009/010/011/012/013/016)."""
        mod = _load()
        result = mod.run_design_preflight_checks(
            baseline_path=str(valid_yaml), exit_on_fail=False
        )
        assert len(result["warning_results"]) == 8, (
            f"warning 체크 수가 8이 아님: {len(result['warning_results'])}"
        )

    def test_info_count_is_two(self, valid_yaml):
        """info 체크 항목은 2개 (PC-D-014/015)."""
        mod = _load()
        result = mod.run_design_preflight_checks(
            baseline_path=str(valid_yaml), exit_on_fail=False
        )
        assert len(result["info_results"]) == 2, (
            f"info 체크 수가 2가 아님: {len(result['info_results'])}"
        )

    def test_baseline_version_extracted(self, valid_yaml):
        """design_baseline_version이 파일에서 올바르게 추출된다."""
        mod = _load()
        result = mod.run_design_preflight_checks(
            baseline_path=str(valid_yaml), exit_on_fail=False
        )
        assert result["design_baseline_version"] != "unknown"

    def test_actual_config_file_passes(self):
        """실제 config/design-baseline.yaml로 passed=True 또는 WARN이어야 함."""
        config_path = _PROJECT_ROOT / "config" / "design-baseline.yaml"
        if not config_path.exists():
            pytest.skip("config/design-baseline.yaml 없음")
        mod = _load()
        result = mod.run_design_preflight_checks(
            baseline_path=str(config_path), exit_on_fail=False
        )
        assert result["passed"] is True, (
            f"실제 baseline이 blocking 실패: "
            f"{[r for r in result['blocking_results'] if not r['passed']]}"
        )


# ===========================================================================
# 2. PC-D-001 viewport.default_width (blocking)
# ===========================================================================

class TestPcD001:
    @pytest.mark.parametrize("width", [375, 768, 1024, 1280, 1440, 1920])
    def test_pass_allowed_widths(self, valid_data, width):
        mod = _load()
        valid_data["viewport"]["default_width"] = width
        r = mod.check_pc_d_001(valid_data)
        assert r["passed"] is True
        assert r["severity"] == "blocking"

    def test_fail_nonstandard_width(self, valid_data):
        mod = _load()
        valid_data["viewport"]["default_width"] = 999
        r = mod.check_pc_d_001(valid_data)
        assert r["passed"] is False
        assert "999" in r["cause"] or "999" in r["outcome"]
        assert "허용값" in r["cause"] or "비허용값" in r["outcome"]

    def test_fail_missing_field(self, valid_data):
        mod = _load()
        del valid_data["viewport"]["default_width"]
        r = mod.check_pc_d_001(valid_data)
        assert r["passed"] is False
        assert "누락" in r["outcome"] or "누락" in r["cause"]

    def test_fail_id_and_severity(self, valid_data):
        mod = _load()
        valid_data["viewport"]["default_width"] = 100
        r = mod.check_pc_d_001(valid_data)
        assert r["id"] == "PC-D-001"
        assert r["severity"] == "blocking"


# ===========================================================================
# 3. PC-D-002 viewport.pixel_ratio (warning)
# ===========================================================================

class TestPcD002:
    @pytest.mark.parametrize("dpr", [1, 1.5, 2, 3])
    def test_pass_standard_dprs(self, valid_data, dpr):
        mod = _load()
        valid_data["viewport"]["pixel_ratio"] = dpr
        r = mod.check_pc_d_002(valid_data)
        assert r["passed"] is True
        assert r["severity"] == "warning"

    def test_warn_nonstandard_dpr(self, valid_data):
        mod = _load()
        valid_data["viewport"]["pixel_ratio"] = 4
        r = mod.check_pc_d_002(valid_data)
        assert r["passed"] is False
        assert "렌더링" in r["cause"]

    def test_warn_missing_field(self, valid_data):
        mod = _load()
        del valid_data["viewport"]["pixel_ratio"]
        r = mod.check_pc_d_002(valid_data)
        assert r["passed"] is False
        assert r["severity"] == "warning"


# ===========================================================================
# 4. PC-D-003 typography.base_font_size (blocking, WCAG 1.4.4)
# ===========================================================================

class TestPcD003:
    def test_pass_16px(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_003(valid_data)
        assert r["passed"] is True
        assert "WCAG 1.4.4" in r["outcome"]

    def test_fail_below_14px(self, valid_data):
        mod = _load()
        valid_data["typography"]["base_font_size"] = 12
        r = mod.check_pc_d_003(valid_data)
        assert r["passed"] is False
        assert "WCAG 1.4.4" in r["cause"]
        assert "12" in r["cause"]
        assert "14" in r["cause"]

    def test_pass_exactly_14px(self, valid_data):
        mod = _load()
        valid_data["typography"]["base_font_size"] = 14
        r = mod.check_pc_d_003(valid_data)
        assert r["passed"] is True

    def test_fail_13px(self, valid_data):
        mod = _load()
        valid_data["typography"]["base_font_size"] = 13
        r = mod.check_pc_d_003(valid_data)
        assert r["passed"] is False

    def test_fail_missing(self, valid_data):
        mod = _load()
        del valid_data["typography"]["base_font_size"]
        r = mod.check_pc_d_003(valid_data)
        assert r["passed"] is False
        assert "WCAG 1.4.4" in r["cause"]

    def test_severity_blocking(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_003(valid_data)
        assert r["severity"] == "blocking"


# ===========================================================================
# 5. PC-D-004 typography.font_family_primary (warning)
# ===========================================================================

class TestPcD004:
    @pytest.mark.parametrize("font", ["Pretendard", "Inter", "Noto Sans KR", "system-ui"])
    def test_pass_approved_fonts(self, valid_data, font):
        mod = _load()
        valid_data["typography"]["font_family_primary"] = font
        r = mod.check_pc_d_004(valid_data)
        assert r["passed"] is True

    def test_warn_unapproved_font(self, valid_data):
        mod = _load()
        valid_data["typography"]["font_family_primary"] = "Comic Sans MS"
        r = mod.check_pc_d_004(valid_data)
        assert r["passed"] is False
        assert "Pretendard" in r["cause"] or "승인" in r["cause"]
        assert r["severity"] == "warning"


# ===========================================================================
# 6. PC-D-005 theme.contrast_ratio_min (blocking, WCAG 1.4.3)
# ===========================================================================

class TestPcD005:
    def test_pass_4_5(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_005(valid_data)
        assert r["passed"] is True
        assert "WCAG 1.4.3" in r["outcome"]

    def test_fail_below_4_5(self, valid_data):
        mod = _load()
        valid_data["theme"]["contrast_ratio_min"] = 3.0
        r = mod.check_pc_d_005(valid_data)
        assert r["passed"] is False
        assert "WCAG 1.4.3" in r["cause"]
        assert "4.5" in r["cause"]

    def test_pass_7_0(self, valid_data):
        mod = _load()
        valid_data["theme"]["contrast_ratio_min"] = 7.0
        r = mod.check_pc_d_005(valid_data)
        assert r["passed"] is True

    def test_fail_missing(self, valid_data):
        mod = _load()
        del valid_data["theme"]["contrast_ratio_min"]
        r = mod.check_pc_d_005(valid_data)
        assert r["passed"] is False
        assert "WCAG 1.4.3" in r["cause"]


# ===========================================================================
# 7. PC-D-006 theme.wcag_level (blocking)
# ===========================================================================

class TestPcD006:
    @pytest.mark.parametrize("level", ["AA", "AAA"])
    def test_pass_allowed_levels(self, valid_data, level):
        mod = _load()
        valid_data["theme"]["wcag_level"] = level
        r = mod.check_pc_d_006(valid_data)
        assert r["passed"] is True

    def test_fail_level_a(self, valid_data):
        mod = _load()
        valid_data["theme"]["wcag_level"] = "A"
        r = mod.check_pc_d_006(valid_data)
        assert r["passed"] is False
        assert "금지" in r["cause"] or "AA" in r["cause"]

    def test_fail_invalid_value(self, valid_data):
        mod = _load()
        valid_data["theme"]["wcag_level"] = "BRONZE"
        r = mod.check_pc_d_006(valid_data)
        assert r["passed"] is False

    def test_fail_missing(self, valid_data):
        mod = _load()
        del valid_data["theme"]["wcag_level"]
        r = mod.check_pc_d_006(valid_data)
        assert r["passed"] is False
        assert r["severity"] == "blocking"


# ===========================================================================
# 8. PC-D-007 theme.active_mode (blocking)
# ===========================================================================

class TestPcD007:
    @pytest.mark.parametrize("mode", ["light", "dark", "system"])
    def test_pass_allowed_modes(self, valid_data, mode):
        mod = _load()
        valid_data["theme"]["active_mode"] = mode
        r = mod.check_pc_d_007(valid_data)
        assert r["passed"] is True

    def test_fail_unknown_mode(self, valid_data):
        mod = _load()
        valid_data["theme"]["active_mode"] = "auto"
        r = mod.check_pc_d_007(valid_data)
        assert r["passed"] is False
        assert "auto" in r["cause"] or "auto" in r["outcome"]

    def test_fail_missing(self, valid_data):
        mod = _load()
        del valid_data["theme"]["active_mode"]
        r = mod.check_pc_d_007(valid_data)
        assert r["passed"] is False
        assert "색상 모드" in r["cause"]


# ===========================================================================
# 9. PC-D-008 theme.focus_visible_outline (blocking, WCAG 2.4.7)
# ===========================================================================

class TestPcD008:
    def test_pass_defined_outline(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_008(valid_data)
        assert r["passed"] is True
        assert "WCAG 2.4.7" in r["outcome"]

    def test_fail_empty_string(self, valid_data):
        mod = _load()
        valid_data["theme"]["focus_visible_outline"] = ""
        r = mod.check_pc_d_008(valid_data)
        assert r["passed"] is False
        assert "WCAG 2.4.7" in r["cause"]

    def test_fail_none_value(self, valid_data):
        mod = _load()
        valid_data["theme"]["focus_visible_outline"] = None
        r = mod.check_pc_d_008(valid_data)
        assert r["passed"] is False
        assert "WCAG 2.4.7" in r["cause"]

    def test_fail_missing(self, valid_data):
        mod = _load()
        del valid_data["theme"]["focus_visible_outline"]
        r = mod.check_pc_d_008(valid_data)
        assert r["passed"] is False
        assert "WCAG 2.4.7" in r["cause"]

    def test_pass_custom_outline(self, valid_data):
        mod = _load()
        valid_data["theme"]["focus_visible_outline"] = "3px dashed #FF6600"
        r = mod.check_pc_d_008(valid_data)
        assert r["passed"] is True


# ===========================================================================
# 10. PC-D-009 typography.rendering_engine (warning)
# ===========================================================================

class TestPcD009:
    @pytest.mark.parametrize("engine", ["auto", "antialiased", "subpixel-antialiased", "none"])
    def test_pass_allowed_engines(self, valid_data, engine):
        mod = _load()
        valid_data["typography"]["rendering_engine"] = engine
        r = mod.check_pc_d_009(valid_data)
        assert r["passed"] is True

    def test_warn_unknown_engine(self, valid_data):
        mod = _load()
        valid_data["typography"]["rendering_engine"] = "crisp-edges"
        r = mod.check_pc_d_009(valid_data)
        assert r["passed"] is False
        assert "렌더링" in r["cause"]
        assert r["severity"] == "warning"


# ===========================================================================
# 11. PC-D-010 theme.color_token_version (warning)
# ===========================================================================

class TestPcD010:
    @pytest.mark.parametrize("ver", ["v1.0", "v2.3", "v10.99"])
    def test_pass_valid_versions(self, valid_data, ver):
        mod = _load()
        valid_data["theme"]["color_token_version"] = ver
        r = mod.check_pc_d_010(valid_data)
        assert r["passed"] is True

    def test_warn_no_v_prefix(self, valid_data):
        mod = _load()
        valid_data["theme"]["color_token_version"] = "1.0"
        r = mod.check_pc_d_010(valid_data)
        assert r["passed"] is False
        assert "vX.Y" in r["cause"]

    def test_warn_word_version(self, valid_data):
        mod = _load()
        valid_data["theme"]["color_token_version"] = "latest"
        r = mod.check_pc_d_010(valid_data)
        assert r["passed"] is False
        assert "이상치 추적" in r["cause"]

    def test_warn_missing(self, valid_data):
        mod = _load()
        del valid_data["theme"]["color_token_version"]
        r = mod.check_pc_d_010(valid_data)
        assert r["passed"] is False
        assert r["severity"] == "warning"


# ===========================================================================
# 12. PC-D-011 typography.line_height_base (warning, WCAG 1.4.8)
# ===========================================================================

class TestPcD011:
    def test_pass_1_5(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_011(valid_data)
        assert r["passed"] is True
        assert "WCAG 1.4.8" in r["outcome"]

    def test_warn_below_1_5(self, valid_data):
        mod = _load()
        valid_data["typography"]["line_height_base"] = 1.2
        r = mod.check_pc_d_011(valid_data)
        assert r["passed"] is False
        assert "1.5" in r["cause"]
        assert "WCAG 1.4.8" in r["cause"]

    def test_pass_1_75(self, valid_data):
        mod = _load()
        valid_data["typography"]["line_height_base"] = 1.75
        r = mod.check_pc_d_011(valid_data)
        assert r["passed"] is True

    def test_warn_missing(self, valid_data):
        mod = _load()
        del valid_data["typography"]["line_height_base"]
        r = mod.check_pc_d_011(valid_data)
        assert r["passed"] is False
        assert "WCAG 1.4.8" in r["cause"]


# ===========================================================================
# 13. PC-D-012 theme.motion_safe (warning, WCAG 2.3.3)
# ===========================================================================

class TestPcD012:
    def test_pass_true(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_012(valid_data)
        assert r["passed"] is True
        assert "WCAG 2.3.3" in r["outcome"]

    def test_warn_false(self, valid_data):
        mod = _load()
        valid_data["theme"]["motion_safe"] = False
        r = mod.check_pc_d_012(valid_data)
        assert r["passed"] is False
        assert "WCAG 2.3.3" in r["cause"]
        assert "prefers-reduced-motion" in r["cause"]

    def test_warn_missing(self, valid_data):
        mod = _load()
        del valid_data["theme"]["motion_safe"]
        r = mod.check_pc_d_012(valid_data)
        assert r["passed"] is False
        assert "WCAG 2.3.3" in r["cause"]


# ===========================================================================
# 14. PC-D-013 component_library.version (warning, SemVer)
# ===========================================================================

class TestPcD013:
    @pytest.mark.parametrize("ver", ["1.4.2", "0.1.0", "10.20.300"])
    def test_pass_semver(self, valid_data, ver):
        mod = _load()
        valid_data["component_library"]["version"] = ver
        r = mod.check_pc_d_013(valid_data)
        assert r["passed"] is True

    def test_warn_non_semver(self, valid_data):
        mod = _load()
        valid_data["component_library"]["version"] = "1.4"
        r = mod.check_pc_d_013(valid_data)
        assert r["passed"] is False
        assert r["severity"] == "warning"

    def test_warn_missing(self, valid_data):
        mod = _load()
        del valid_data["component_library"]["version"]
        r = mod.check_pc_d_013(valid_data)
        assert r["passed"] is False

    def test_warn_no_component_lib_section(self, valid_data):
        mod = _load()
        del valid_data["component_library"]
        r = mod.check_pc_d_013(valid_data)
        assert r["passed"] is False


# ===========================================================================
# 15. PC-D-014 design_tools.figma.version (info)
# ===========================================================================

class TestPcD014:
    def test_pass_figma_version_set(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_014(valid_data)
        assert r["passed"] is True
        assert r["severity"] == "info"

    def test_warn_missing_figma_version(self, valid_data):
        mod = _load()
        valid_data["design_tools"]["figma"]["version"] = None
        r = mod.check_pc_d_014(valid_data)
        assert r["passed"] is False

    def test_warn_no_design_tools(self, valid_data):
        mod = _load()
        del valid_data["design_tools"]
        r = mod.check_pc_d_014(valid_data)
        assert r["passed"] is False
        assert r["severity"] == "info"


# ===========================================================================
# 16. PC-D-015 design_tools.storybook.version (info)
# ===========================================================================

class TestPcD015:
    def test_pass_storybook_version_set(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_015(valid_data)
        assert r["passed"] is True
        assert r["severity"] == "info"

    def test_warn_missing_storybook_version(self, valid_data):
        mod = _load()
        valid_data["design_tools"]["storybook"]["version"] = ""
        r = mod.check_pc_d_015(valid_data)
        assert r["passed"] is False


# ===========================================================================
# 17. PC-D-016 retry_policy.max_retries (warning)
# ===========================================================================

class TestPcD016:
    @pytest.mark.parametrize("v", [1, 2, 3, 4, 5])
    def test_pass_valid_range(self, valid_data, v):
        mod = _load()
        valid_data["retry_policy"]["max_retries"] = v
        r = mod.check_pc_d_016(valid_data)
        assert r["passed"] is True

    def test_warn_zero(self, valid_data):
        mod = _load()
        valid_data["retry_policy"]["max_retries"] = 0
        r = mod.check_pc_d_016(valid_data)
        assert r["passed"] is False
        assert r["severity"] == "warning"

    def test_warn_exceeds_max(self, valid_data):
        mod = _load()
        valid_data["retry_policy"]["max_retries"] = 10
        r = mod.check_pc_d_016(valid_data)
        assert r["passed"] is False
        assert "무한 재시도" in r["cause"]

    def test_warn_missing(self, valid_data):
        mod = _load()
        del valid_data["retry_policy"]["max_retries"]
        r = mod.check_pc_d_016(valid_data)
        assert r["passed"] is False

    def test_warn_no_retry_policy(self, valid_data):
        mod = _load()
        del valid_data["retry_policy"]
        r = mod.check_pc_d_016(valid_data)
        assert r["passed"] is False


# ===========================================================================
# 18. build_design_preflight_header_result
# ===========================================================================

class TestBuildHeaderResult:
    def test_returns_dict_with_required_keys(self, valid_yaml):
        mod = _load()
        check_result = mod.run_design_preflight_checks(
            baseline_path=str(valid_yaml), exit_on_fail=False
        )
        header = mod.build_design_preflight_header_result(check_result)
        assert isinstance(header, dict)
        for key in (
            "design_baseline_version", "viewport", "font", "theme",
            "token_version", "component_lib_version",
            "blocking_pass", "blocking_total",
            "warning_pass", "warning_total",
            "checked_at", "status",
        ):
            assert key in header, f"헤더 키 '{key}' 없음"

    def test_status_pass_on_valid(self, valid_yaml):
        mod = _load()
        check_result = mod.run_design_preflight_checks(
            baseline_path=str(valid_yaml), exit_on_fail=False
        )
        header = mod.build_design_preflight_header_result(check_result)
        assert header["status"] == "PASS"

    def test_blocking_counts_match(self, valid_yaml):
        mod = _load()
        check_result = mod.run_design_preflight_checks(
            baseline_path=str(valid_yaml), exit_on_fail=False
        )
        header = mod.build_design_preflight_header_result(check_result)
        assert header["blocking_pass"] == header["blocking_total"] == 6

    def test_warning_counts_match(self, valid_yaml):
        mod = _load()
        check_result = mod.run_design_preflight_checks(
            baseline_path=str(valid_yaml), exit_on_fail=False
        )
        header = mod.build_design_preflight_header_result(check_result)
        assert header["warning_total"] == 8

    def test_status_fail_on_blocking_fail(self, tmp_path):
        """blocking 실패 시 status=FAIL."""
        mod = _load()
        # base_font_size=10 → PC-D-003 blocking FAIL
        content = (
            "schema_version: 1\n"
            "baseline_version: v1.2\n"
            "viewport:\n"
            "  default_width: 1440\n"
            "typography:\n"
            "  base_font_size: 10\n"
            "theme:\n"
            "  contrast_ratio_min: 4.5\n"
            "  wcag_level: AA\n"
            "  active_mode: light\n"
            "  focus_visible_outline: 2px solid #2563EB\n"
        )
        cfg = tmp_path / "design-baseline.yaml"
        cfg.write_text(content, encoding="utf-8")
        check_result = mod.run_design_preflight_checks(
            baseline_path=str(cfg), exit_on_fail=False
        )
        header = mod.build_design_preflight_header_result(check_result)
        assert header["status"] == "FAIL"

    def test_viewport_string_contains_px(self, valid_yaml):
        """viewport 표시 문자열에 'px' 포함."""
        mod = _load()
        check_result = mod.run_design_preflight_checks(
            baseline_path=str(valid_yaml), exit_on_fail=False
        )
        header = mod.build_design_preflight_header_result(check_result)
        assert "px" in str(header["viewport"])

    def test_font_string_contains_family(self, valid_yaml):
        """font 표시 문자열에 Pretendard 포함."""
        mod = _load()
        check_result = mod.run_design_preflight_checks(
            baseline_path=str(valid_yaml), exit_on_fail=False
        )
        header = mod.build_design_preflight_header_result(check_result)
        assert "Pretendard" in header["font"]


# ===========================================================================
# 19. SKIP 환경변수 동작
# ===========================================================================

class TestSkipBehavior:
    def test_skip_design_preflight(self, monkeypatch, tmp_path):
        """SKIP_DESIGN_PREFLIGHT=1 이면 skipped=True 반환."""
        monkeypatch.setenv("SKIP_DESIGN_PREFLIGHT", "1")
        mod = _load()
        result = mod.run_design_preflight_checks(
            baseline_path=str(tmp_path / "nonexistent.yaml"),
            exit_on_fail=False,
        )
        assert result.get("skipped") is True
        assert result["passed"] is True

    def test_skip_preflight_does_not_affect_module_directly(self, monkeypatch, tmp_path):
        """SKIP_PREFLIGHT=1은 conftest.py 레벨에서 처리 — 모듈 직접 호출 시 영향 없음."""
        monkeypatch.setenv("SKIP_PREFLIGHT", "1")
        monkeypatch.delenv("SKIP_DESIGN_PREFLIGHT", raising=False)
        mod = _load()
        # 파일 없으면 passed=False (skipped 아님 — SKIP_PREFLIGHT는 conftest 전용)
        result = mod.run_design_preflight_checks(
            baseline_path=str(tmp_path / "nonexistent.yaml"),
            exit_on_fail=False,
        )
        # SKIP_DESIGN_PREFLIGHT가 아닌 SKIP_PREFLIGHT → 모듈은 정상 실행, 파일 없으면 fail
        assert result["passed"] is False

    def test_skip_false_by_default(self, valid_yaml, monkeypatch):
        """환경변수 없으면 skipped 없음."""
        monkeypatch.delenv("SKIP_DESIGN_PREFLIGHT", raising=False)
        monkeypatch.delenv("SKIP_PREFLIGHT", raising=False)
        mod = _load()
        result = mod.run_design_preflight_checks(
            baseline_path=str(valid_yaml), exit_on_fail=False
        )
        assert not result.get("skipped", False)
