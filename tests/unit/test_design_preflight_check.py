"""tests/unit/test_design_preflight_check.py — design pre-flight 원인 로그 테스트.

tools/design_preflight.py 의 PC-D-001 ~ PC-D-012 각 체크 함수의
- 정상 통과(PASS) 케이스
- 실패(FAIL) 케이스 — 원인 로그(cause) 내용 검증
- 경고(WARN) 케이스 — 원인 로그(cause) 내용 검증

T-PERM-002: 원인 로그 테스트 (2026-03-27, 디자인실)
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

# ---------------------------------------------------------------------------
# 모듈 로드
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_DESIGN_PREFLIGHT_PATH = _PROJECT_ROOT / "tools" / "design_preflight.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("design_preflight", _DESIGN_PREFLIGHT_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# 픽스처: 정상 베이스라인 데이터
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_data() -> dict:
    """모든 PC-D 체크가 PASS 되는 기준 데이터."""
    return {
        "schema_version": 1,
        "infra_baseline_version": "v1.0",
        "viewport": {
            "default_width": 1440,
            "pixel_ratio": 1,
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
    }


# ---------------------------------------------------------------------------
# 테스트 1: 모듈 로드 & run_design_preflight 반환 구조
# ---------------------------------------------------------------------------

class TestModuleStructure:
    def test_module_loads(self):
        """모듈이 에러 없이 로드된다."""
        mod = _load()
        assert mod is not None

    def test_run_returns_dict(self, tmp_path):
        """run_design_preflight()가 dict를 반환한다."""
        mod = _load()
        cfg = tmp_path / "design-baseline.yaml"
        cfg.write_text("schema_version: 1\ninfra_baseline_version: v1.0\n")
        report = mod.run_design_preflight(config_path=cfg, quiet=True)
        assert isinstance(report, dict)

    def test_required_keys_present(self, tmp_path):
        """반환 dict에 필수 키가 모두 있다."""
        mod = _load()
        cfg = tmp_path / "design-baseline.yaml"
        cfg.write_text("schema_version: 1\ninfra_baseline_version: v1.0\n")
        report = mod.run_design_preflight(config_path=cfg, quiet=True)
        for key in ("status", "results", "errors", "warnings", "timestamp", "baseline_version"):
            assert key in report, f"필수 키 '{key}' 없음"

    def test_status_values(self, tmp_path):
        """status 값은 PASS/WARN/FAIL 중 하나."""
        mod = _load()
        cfg = tmp_path / "design-baseline.yaml"
        cfg.write_text("schema_version: 1\n")
        report = mod.run_design_preflight(config_path=cfg, quiet=True)
        assert report["status"] in ("PASS", "WARN", "FAIL")

    def test_missing_file_returns_fail(self, tmp_path):
        """파일 없으면 FAIL + 원인 메시지."""
        mod = _load()
        report = mod.run_design_preflight(config_path=tmp_path / "nonexistent.yaml", quiet=True)
        assert report["status"] == "FAIL"
        assert len(report["errors"]) > 0
        # 원인 메시지에 파일명 포함
        assert "nonexistent" in report["errors"][0]


# ---------------------------------------------------------------------------
# 테스트 2: 결과 dict 스키마 (_result 헬퍼)
# ---------------------------------------------------------------------------

class TestResultHelper:
    def test_pass_result_structure(self):
        mod = _load()
        r = mod._result("PC-D-001", "PASS", "viewport.default_width", "1440px ✔")
        assert r["id"] == "PC-D-001"
        assert r["level"] == "PASS"
        assert r["target"] == "viewport.default_width"
        assert r["cause"] == ""

    def test_fail_result_has_cause(self):
        mod = _load()
        r = mod._result("PC-D-003", "FAIL", "typography.base_font_size",
                        "12px — 최소 14px 미달", "현재 12px < 14px. WCAG 1.4.4 위반.")
        assert r["level"] == "FAIL"
        assert "WCAG 1.4.4" in r["cause"]

    def test_warn_result_has_cause(self):
        mod = _load()
        r = mod._result("PC-D-002", "WARN", "viewport.pixel_ratio",
                        "비표준 DPR: 4 (경고)", "표준 DPR 목록에 없습니다.")
        assert r["level"] == "WARN"
        assert len(r["cause"]) > 0


# ---------------------------------------------------------------------------
# 테스트 3: PC-D-001 viewport.default_width
# ---------------------------------------------------------------------------

class TestPcD001:
    def test_pass_allowed_value(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_001(valid_data)
        assert r["level"] == "PASS"
        assert r["cause"] == ""

    def test_fail_nonstandard_width(self, valid_data):
        mod = _load()
        valid_data["viewport"]["default_width"] = 999
        r = mod.check_pc_d_001(valid_data)
        assert r["level"] == "FAIL"
        assert "999" in r["cause"] or "999" in r["outcome"]
        # 원인에 허용값 목록 언급
        assert "허용값" in r["cause"] or "비허용값" in r["outcome"]

    def test_fail_missing_field(self, valid_data):
        mod = _load()
        del valid_data["viewport"]["default_width"]
        r = mod.check_pc_d_001(valid_data)
        assert r["level"] == "FAIL"
        assert "누락" in r["outcome"] or "누락" in r["cause"]

    def test_all_allowed_values_pass(self, valid_data):
        mod = _load()
        for w in [375, 768, 1024, 1280, 1440, 1920]:
            valid_data["viewport"]["default_width"] = w
            r = mod.check_pc_d_001(valid_data)
            assert r["level"] == "PASS", f"width={w} 는 PASS 여야 함"


# ---------------------------------------------------------------------------
# 테스트 4: PC-D-002 viewport.pixel_ratio (warn)
# ---------------------------------------------------------------------------

class TestPcD002:
    def test_pass_standard_dpr(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_002(valid_data)
        assert r["level"] == "PASS"

    def test_warn_nonstandard_dpr(self, valid_data):
        mod = _load()
        valid_data["viewport"]["pixel_ratio"] = 4
        r = mod.check_pc_d_002(valid_data)
        assert r["level"] == "WARN"
        # 원인에 "렌더링 왜곡" 언급
        assert "렌더링" in r["cause"]

    def test_warn_missing_field(self, valid_data):
        mod = _load()
        del valid_data["viewport"]["pixel_ratio"]
        r = mod.check_pc_d_002(valid_data)
        assert r["level"] == "WARN"

    @pytest.mark.parametrize("dpr", [1, 1.5, 2, 3])
    def test_all_standard_dprs_pass(self, valid_data, dpr):
        mod = _load()
        valid_data["viewport"]["pixel_ratio"] = dpr
        r = mod.check_pc_d_002(valid_data)
        assert r["level"] == "PASS", f"DPR={dpr} 는 PASS 여야 함"


# ---------------------------------------------------------------------------
# 테스트 5: PC-D-003 typography.base_font_size (WCAG 1.4.4)
# ---------------------------------------------------------------------------

class TestPcD003:
    def test_pass_16px(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_003(valid_data)
        assert r["level"] == "PASS"
        assert "WCAG 1.4.4" in r["outcome"]

    def test_fail_below_14px(self, valid_data):
        mod = _load()
        valid_data["typography"]["base_font_size"] = 12
        r = mod.check_pc_d_003(valid_data)
        assert r["level"] == "FAIL"
        # 원인에 WCAG 조항 명시
        assert "WCAG 1.4.4" in r["cause"]
        # 원인에 현재 값과 기준값 모두 언급
        assert "12" in r["cause"]
        assert "14" in r["cause"]

    def test_fail_exactly_13px(self, valid_data):
        mod = _load()
        valid_data["typography"]["base_font_size"] = 13
        r = mod.check_pc_d_003(valid_data)
        assert r["level"] == "FAIL"

    def test_pass_exactly_14px(self, valid_data):
        mod = _load()
        valid_data["typography"]["base_font_size"] = 14
        r = mod.check_pc_d_003(valid_data)
        assert r["level"] == "PASS"

    def test_fail_missing_field(self, valid_data):
        mod = _load()
        del valid_data["typography"]["base_font_size"]
        r = mod.check_pc_d_003(valid_data)
        assert r["level"] == "FAIL"
        assert "WCAG 1.4.4" in r["cause"]


# ---------------------------------------------------------------------------
# 테스트 6: PC-D-004 typography.font_family_primary (warn)
# ---------------------------------------------------------------------------

class TestPcD004:
    def test_pass_pretendard(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_004(valid_data)
        assert r["level"] == "PASS"

    def test_warn_unapproved_font(self, valid_data):
        mod = _load()
        valid_data["typography"]["font_family_primary"] = "Comic Sans MS"
        r = mod.check_pc_d_004(valid_data)
        assert r["level"] == "WARN"
        # 원인에 승인 폰트 목록 언급
        assert "Pretendard" in r["cause"] or "승인" in r["cause"]

    @pytest.mark.parametrize("font", ["Pretendard", "Inter", "Noto Sans KR", "system-ui"])
    def test_all_approved_fonts_pass(self, valid_data, font):
        mod = _load()
        valid_data["typography"]["font_family_primary"] = font
        r = mod.check_pc_d_004(valid_data)
        assert r["level"] == "PASS", f"폰트 {font!r} 는 PASS 여야 함"


# ---------------------------------------------------------------------------
# 테스트 7: PC-D-005 theme.contrast_ratio_min (WCAG 1.4.3)
# ---------------------------------------------------------------------------

class TestPcD005:
    def test_pass_4_5(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_005(valid_data)
        assert r["level"] == "PASS"
        assert "WCAG 1.4.3" in r["outcome"]

    def test_fail_below_4_5(self, valid_data):
        mod = _load()
        valid_data["theme"]["contrast_ratio_min"] = 3.0
        r = mod.check_pc_d_005(valid_data)
        assert r["level"] == "FAIL"
        # 원인에 WCAG 조항과 수치 모두 포함
        assert "WCAG 1.4.3" in r["cause"]
        assert "4.5" in r["cause"]

    def test_fail_3_9_boundary(self, valid_data):
        mod = _load()
        valid_data["theme"]["contrast_ratio_min"] = 3.9
        r = mod.check_pc_d_005(valid_data)
        assert r["level"] == "FAIL"

    def test_pass_7_0_aaa(self, valid_data):
        mod = _load()
        valid_data["theme"]["contrast_ratio_min"] = 7.0
        r = mod.check_pc_d_005(valid_data)
        assert r["level"] == "PASS"

    def test_fail_missing(self, valid_data):
        mod = _load()
        del valid_data["theme"]["contrast_ratio_min"]
        r = mod.check_pc_d_005(valid_data)
        assert r["level"] == "FAIL"
        assert "WCAG 1.4.3" in r["cause"]


# ---------------------------------------------------------------------------
# 테스트 8: PC-D-006 theme.wcag_level
# ---------------------------------------------------------------------------

class TestPcD006:
    def test_pass_aa(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_006(valid_data)
        assert r["level"] == "PASS"

    def test_pass_aaa(self, valid_data):
        mod = _load()
        valid_data["theme"]["wcag_level"] = "AAA"
        r = mod.check_pc_d_006(valid_data)
        assert r["level"] == "PASS"

    def test_fail_level_a_only(self, valid_data):
        mod = _load()
        valid_data["theme"]["wcag_level"] = "A"
        r = mod.check_pc_d_006(valid_data)
        assert r["level"] == "FAIL"
        # 원인에 "A" 단독 금지 명시
        assert "금지" in r["cause"] or "AA" in r["cause"]

    def test_fail_invalid_value(self, valid_data):
        mod = _load()
        valid_data["theme"]["wcag_level"] = "BRONZE"
        r = mod.check_pc_d_006(valid_data)
        assert r["level"] == "FAIL"
        assert "BRONZE" in r["cause"] or "BRONZE" in r["outcome"]

    def test_fail_missing(self, valid_data):
        mod = _load()
        del valid_data["theme"]["wcag_level"]
        r = mod.check_pc_d_006(valid_data)
        assert r["level"] == "FAIL"


# ---------------------------------------------------------------------------
# 테스트 9: PC-D-007 theme.active_mode
# ---------------------------------------------------------------------------

class TestPcD007:
    def test_pass_light(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_007(valid_data)
        assert r["level"] == "PASS"

    @pytest.mark.parametrize("mode", ["light", "dark", "system"])
    def test_pass_all_allowed_modes(self, valid_data, mode):
        mod = _load()
        valid_data["theme"]["active_mode"] = mode
        r = mod.check_pc_d_007(valid_data)
        assert r["level"] == "PASS", f"mode={mode!r} 는 PASS 여야 함"

    def test_fail_unknown_mode(self, valid_data):
        mod = _load()
        valid_data["theme"]["active_mode"] = "auto"
        r = mod.check_pc_d_007(valid_data)
        assert r["level"] == "FAIL"
        assert "auto" in r["cause"] or "auto" in r["outcome"]

    def test_fail_missing(self, valid_data):
        mod = _load()
        del valid_data["theme"]["active_mode"]
        r = mod.check_pc_d_007(valid_data)
        assert r["level"] == "FAIL"
        assert "색상 모드" in r["cause"]


# ---------------------------------------------------------------------------
# 테스트 10: PC-D-008 theme.focus_visible_outline (WCAG 2.4.7)
# ---------------------------------------------------------------------------

class TestPcD008:
    def test_pass_defined_outline(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_008(valid_data)
        assert r["level"] == "PASS"
        assert "WCAG 2.4.7" in r["outcome"]

    def test_fail_empty_string(self, valid_data):
        mod = _load()
        valid_data["theme"]["focus_visible_outline"] = ""
        r = mod.check_pc_d_008(valid_data)
        assert r["level"] == "FAIL"
        # 원인에 WCAG 2.4.7 명시
        assert "WCAG 2.4.7" in r["cause"]

    def test_fail_none_value(self, valid_data):
        mod = _load()
        valid_data["theme"]["focus_visible_outline"] = None
        r = mod.check_pc_d_008(valid_data)
        assert r["level"] == "FAIL"
        assert "WCAG 2.4.7" in r["cause"]

    def test_fail_missing_field(self, valid_data):
        mod = _load()
        del valid_data["theme"]["focus_visible_outline"]
        r = mod.check_pc_d_008(valid_data)
        assert r["level"] == "FAIL"
        assert "WCAG 2.4.7" in r["cause"]

    def test_pass_custom_outline(self, valid_data):
        mod = _load()
        valid_data["theme"]["focus_visible_outline"] = "3px dashed #FF6600"
        r = mod.check_pc_d_008(valid_data)
        assert r["level"] == "PASS"


# ---------------------------------------------------------------------------
# 테스트 11: PC-D-009 typography.rendering_engine (warn)
# ---------------------------------------------------------------------------

class TestPcD009:
    def test_pass_antialiased(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_009(valid_data)
        assert r["level"] == "PASS"

    def test_warn_unknown_engine(self, valid_data):
        mod = _load()
        valid_data["typography"]["rendering_engine"] = "crisp-edges"
        r = mod.check_pc_d_009(valid_data)
        assert r["level"] == "WARN"
        assert "렌더링" in r["cause"]

    @pytest.mark.parametrize("engine", ["auto", "antialiased", "subpixel-antialiased", "none"])
    def test_all_allowed_engines_pass(self, valid_data, engine):
        mod = _load()
        valid_data["typography"]["rendering_engine"] = engine
        r = mod.check_pc_d_009(valid_data)
        assert r["level"] == "PASS", f"엔진 {engine!r} 는 PASS 여야 함"


# ---------------------------------------------------------------------------
# 테스트 12: PC-D-010 theme.color_token_version (warn)
# ---------------------------------------------------------------------------

class TestPcD010:
    def test_pass_valid_version(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_010(valid_data)
        assert r["level"] == "PASS"

    @pytest.mark.parametrize("ver", ["v1.0", "v2.3", "v10.99"])
    def test_pass_various_versions(self, valid_data, ver):
        mod = _load()
        valid_data["theme"]["color_token_version"] = ver
        r = mod.check_pc_d_010(valid_data)
        assert r["level"] == "PASS", f"버전 {ver!r} 는 PASS 여야 함"

    def test_warn_invalid_format(self, valid_data):
        mod = _load()
        valid_data["theme"]["color_token_version"] = "1.0"  # v 접두사 없음
        r = mod.check_pc_d_010(valid_data)
        assert r["level"] == "WARN"
        assert "vX.Y" in r["cause"]

    def test_warn_version_word(self, valid_data):
        mod = _load()
        valid_data["theme"]["color_token_version"] = "latest"
        r = mod.check_pc_d_010(valid_data)
        assert r["level"] == "WARN"
        assert "이상치 추적" in r["cause"]

    def test_warn_missing(self, valid_data):
        mod = _load()
        del valid_data["theme"]["color_token_version"]
        r = mod.check_pc_d_010(valid_data)
        assert r["level"] == "WARN"


# ---------------------------------------------------------------------------
# 테스트 13: PC-D-011 typography.line_height_base (WCAG 1.4.8, warn)
# ---------------------------------------------------------------------------

class TestPcD011:
    def test_pass_1_5(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_011(valid_data)
        assert r["level"] == "PASS"
        assert "WCAG 1.4.8" in r["outcome"]

    def test_warn_below_1_5(self, valid_data):
        mod = _load()
        valid_data["typography"]["line_height_base"] = 1.2
        r = mod.check_pc_d_011(valid_data)
        assert r["level"] == "WARN"
        assert "1.5" in r["cause"]
        assert "WCAG 1.4.8" in r["cause"]

    def test_pass_1_75(self, valid_data):
        mod = _load()
        valid_data["typography"]["line_height_base"] = 1.75
        r = mod.check_pc_d_011(valid_data)
        assert r["level"] == "PASS"

    def test_warn_missing(self, valid_data):
        mod = _load()
        del valid_data["typography"]["line_height_base"]
        r = mod.check_pc_d_011(valid_data)
        assert r["level"] == "WARN"
        assert "WCAG 1.4.8" in r["cause"]


# ---------------------------------------------------------------------------
# 테스트 14: PC-D-012 theme.motion_safe (WCAG 2.3.3, warn)
# ---------------------------------------------------------------------------

class TestPcD012:
    def test_pass_true(self, valid_data):
        mod = _load()
        r = mod.check_pc_d_012(valid_data)
        assert r["level"] == "PASS"
        assert "WCAG 2.3.3" in r["outcome"]

    def test_warn_false(self, valid_data):
        mod = _load()
        valid_data["theme"]["motion_safe"] = False
        r = mod.check_pc_d_012(valid_data)
        assert r["level"] == "WARN"
        assert "WCAG 2.3.3" in r["cause"]
        assert "prefers-reduced-motion" in r["cause"]

    def test_warn_missing(self, valid_data):
        mod = _load()
        del valid_data["theme"]["motion_safe"]
        r = mod.check_pc_d_012(valid_data)
        assert r["level"] == "WARN"
        assert "WCAG 2.3.3" in r["cause"]


# ---------------------------------------------------------------------------
# 테스트 15: 통합 — run_design_preflight with actual file
# ---------------------------------------------------------------------------

class TestRunDesignPreflight:
    def test_actual_baseline_passes(self):
        """실제 config/design-baseline.yaml 로드 시 PASS 또는 WARN이어야 함 (FAIL 아님)."""
        mod = _load()
        config_path = _PROJECT_ROOT / "config" / "design-baseline.yaml"
        if not config_path.exists():
            pytest.skip("config/design-baseline.yaml 없음")
        report = mod.run_design_preflight(config_path=config_path, quiet=True)
        assert report["status"] in ("PASS", "WARN"), (
            f"실제 baseline이 FAIL이 됨. 오류: {report['errors']}"
        )

    def test_all_checks_run(self):
        """12개 체크가 모두 실행된다."""
        mod = _load()
        config_path = _PROJECT_ROOT / "config" / "design-baseline.yaml"
        if not config_path.exists():
            pytest.skip("config/design-baseline.yaml 없음")
        report = mod.run_design_preflight(config_path=config_path, quiet=True)
        assert len(report["results"]) == 12, (
            f"체크 수가 12개 아님: {len(report['results'])}개"
        )

    def test_all_result_ids_present(self):
        """PC-D-001 ~ PC-D-012 모든 ID가 결과에 포함된다."""
        mod = _load()
        config_path = _PROJECT_ROOT / "config" / "design-baseline.yaml"
        if not config_path.exists():
            pytest.skip("config/design-baseline.yaml 없음")
        report = mod.run_design_preflight(config_path=config_path, quiet=True)
        ids = {r["id"] for r in report["results"]}
        for i in range(1, 13):
            expected_id = f"PC-D-{i:03d}"
            assert expected_id in ids, f"{expected_id} 결과 없음"

    def test_strict_mode_warns_become_fail(self, tmp_path):
        """--strict 모드에서 WARN 항목이 FAIL로 상향된다."""
        mod = _load()
        # WARN만 발생하는 최소 데이터 (pixel_ratio=4 → warn)
        cfg = tmp_path / "design-baseline.yaml"
        cfg.write_text(
            "schema_version: 1\n"
            "infra_baseline_version: v1.0\n"
            "viewport:\n"
            "  default_width: 1440\n"
            "  pixel_ratio: 4\n"
            "typography:\n"
            "  base_font_size: 16\n"
            "  font_family_primary: Pretendard\n"
            "  rendering_engine: antialiased\n"
            "  line_height_base: 1.5\n"
            "theme:\n"
            "  contrast_ratio_min: 4.5\n"
            "  wcag_level: AA\n"
            "  active_mode: light\n"
            "  focus_visible_outline: 2px solid #2563EB\n"
            "  color_token_version: v1.0\n"
            "  motion_safe: true\n"
        )
        report = mod.run_design_preflight(config_path=cfg, strict=True, quiet=True)
        assert report["status"] == "FAIL", (
            "strict 모드에서 WARN → FAIL 전환이 되어야 함"
        )

    def test_baseline_version_in_report(self):
        """보고서에 infra_baseline_version이 포함된다."""
        mod = _load()
        config_path = _PROJECT_ROOT / "config" / "design-baseline.yaml"
        if not config_path.exists():
            pytest.skip("config/design-baseline.yaml 없음")
        report = mod.run_design_preflight(config_path=config_path, quiet=True)
        assert report["baseline_version"] != "unknown", (
            "infra_baseline_version이 'unknown'이면 이상치 추적 불가"
        )

    def test_cause_present_on_failure(self, tmp_path):
        """실패 항목의 result dict에 cause 필드가 비어있지 않다."""
        mod = _load()
        # PC-D-003 의도적 실패: base_font_size=10
        cfg = tmp_path / "design-baseline.yaml"
        cfg.write_text(
            "schema_version: 1\n"
            "infra_baseline_version: v1.0\n"
            "viewport:\n"
            "  default_width: 1440\n"
            "  pixel_ratio: 1\n"
            "typography:\n"
            "  base_font_size: 10\n"  # ← 의도적 실패
            "  font_family_primary: Pretendard\n"
            "  rendering_engine: antialiased\n"
            "  line_height_base: 1.5\n"
            "theme:\n"
            "  contrast_ratio_min: 4.5\n"
            "  wcag_level: AA\n"
            "  active_mode: light\n"
            "  focus_visible_outline: 2px solid #2563EB\n"
            "  color_token_version: v1.0\n"
            "  motion_safe: true\n"
        )
        report = mod.run_design_preflight(config_path=cfg, quiet=True)
        fail_results = [r for r in report["results"] if r["level"] == "FAIL"]
        assert len(fail_results) > 0, "의도적 실패가 감지되지 않음"
        for r in fail_results:
            assert r["cause"] != "", (
                f"FAIL 항목 {r['id']}의 cause가 비어있음 — 원인 로그 미작성"
            )

    def test_cause_contains_wcag_reference_for_accessibility_checks(self, tmp_path):
        """접근성 관련 실패(PC-D-003/005/006/008)는 cause에 WCAG 조항 번호를 포함한다."""
        mod = _load()
        wcag_checks = {
            "PC-D-003": ("typography.base_font_size", 10, "WCAG 1.4.4"),
            "PC-D-005": ("theme.contrast_ratio_min", 3.0, "WCAG 1.4.3"),
            "PC-D-008": ("theme.focus_visible_outline", "", "WCAG 2.4.7"),
        }

        def _make_data(field: str, val) -> dict:
            parts = field.split(".")
            d = {
                "schema_version": 1,
                "viewport": {"default_width": 1440, "pixel_ratio": 1},
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
            }
            sec, key = parts[0], parts[1]
            d[sec][key] = val
            return d

        for check_id, (field, bad_val, wcag_ref) in wcag_checks.items():
            data = _make_data(field, bad_val)
            # 해당 check 함수 직접 호출
            fn_name = f"check_pc_d_{check_id.split('-')[2]}"
            fn = getattr(mod, fn_name, None)
            assert fn is not None, f"{fn_name} 함수 없음"
            r = fn(data)
            assert r["level"] == "FAIL", f"{check_id} 는 FAIL 여야 함"
            assert wcag_ref in r["cause"], (
                f"{check_id} cause에 {wcag_ref} 미포함: {r['cause']!r}"
            )
