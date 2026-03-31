"""tools/design_preflight_check.py — 디자인 pre-flight 체크 실행 모듈.

RETRO-11: design-baseline.yaml PC-D-001~016 전체 체크 실행 및
E2E 로그 헤더 삽입을 위한 표준 인터페이스를 제공한다.

- run_design_preflight_checks(): RETRO-11 표준 인터페이스 (blocking/warning/info 분류)
- build_design_preflight_header_result(): conftest.py 헤더 출력용 dict 생성

사용법:
    from tools.design_preflight_check import run_design_preflight_checks
    result = run_design_preflight_checks()

    SKIP_DESIGN_PREFLIGHT=1  → 전체 생략
    SKIP_PREFLIGHT=1         → 인프라 + 디자인 모두 생략
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml as _yaml  # type: ignore[import-untyped]
except ImportError:
    _yaml = None  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# 프로젝트 루트 및 기본 경로
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).parent.parent
_DEFAULT_BASELINE_PATH = str(_PROJECT_ROOT / "config" / "design-baseline.yaml")

# severity 상수
_SEV_BLOCKING = "blocking"
_SEV_WARNING = "warning"
_SEV_INFO = "info"

# 허용값 상수 (design-baseline.yaml과 동기화)
_ALLOWED_WIDTHS = [375, 768, 1024, 1280, 1440, 1920]
_ALLOWED_DPRS = [1, 1.5, 2, 3]
_ALLOWED_FONTS = ["Pretendard", "Inter", "Noto Sans KR", "system-ui"]
_ALLOWED_RENDER_ENGINES = ["auto", "antialiased", "subpixel-antialiased", "none"]
_ALLOWED_WCAG_LEVELS = ["AA", "AAA"]
_ALLOWED_ACTIVE_MODES = ["light", "dark", "system"]
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_TOKEN_VER_RE = re.compile(r"^v\d+\.\d+$")


# ---------------------------------------------------------------------------
# 값 추출 헬퍼
# ---------------------------------------------------------------------------

def _val(raw: Any) -> Any:
    """design-baseline.yaml 필드값을 추출한다.

    YAML 구조가 두 가지 형태로 존재한다:
    1. 단순값:   ``default_width: 1440``  → raw = 1440
    2. 중첩 dict: ``default_width:\n  default: 1440\n  allowed_values: [...]``
                                          → raw = {"default": 1440, ...}

    중첩 dict이면 "default" 키 값을 반환하고, 아니면 그대로 반환한다.
    """
    if isinstance(raw, dict):
        return raw.get("default")
    return raw


# ---------------------------------------------------------------------------
# YAML 로더
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict[str, Any]:
    """YAML 파일을 읽어 dict 반환. PyYAML 없으면 간이 파싱."""
    text = path.read_text(encoding="utf-8")
    if _yaml is not None:
        return _yaml.safe_load(text) or {}
    # 간이 파서: 최상위 key: value 형태만 지원
    result: dict[str, Any] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped and not line.startswith(" "):
            key, _, raw_val = stripped.partition(":")
            val = raw_val.split("#")[0].strip().strip('"').strip("'")
            result[key.strip()] = val
    return result


# ---------------------------------------------------------------------------
# 결과 dict 헬퍼
# ---------------------------------------------------------------------------

def _check_result(
    check_id: str,
    severity: str,
    passed: bool,
    outcome: str,
    cause: str = "",
) -> dict[str, Any]:
    """체크 결과 표준 dict를 반환한다."""
    return {
        "id": check_id,
        "severity": severity,
        "passed": passed,
        "outcome": outcome,
        "cause": cause if not passed else "",
    }


# ---------------------------------------------------------------------------
# PC-D-001 ~ PC-D-016 개별 체크
# ---------------------------------------------------------------------------

def check_pc_d_001(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-001: viewport.default_width — 허용값 목록에 포함 여부 (blocking)."""
    val = _val((data.get("viewport") or {}).get("default_width"))
    if val is None:
        return _check_result(
            "PC-D-001", _SEV_BLOCKING, False,
            "viewport.default_width 누락",
            "viewport.default_width 필드가 없습니다. 허용값: " + str(_ALLOWED_WIDTHS),
        )
    if val not in _ALLOWED_WIDTHS:
        return _check_result(
            "PC-D-001", _SEV_BLOCKING, False,
            f"비허용값: {val}px",
            f"viewport.default_width={val}은 허용값 목록에 없습니다: {_ALLOWED_WIDTHS}",
        )
    return _check_result("PC-D-001", _SEV_BLOCKING, True, f"{val}px ✔")


def check_pc_d_002(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-002: viewport.pixel_ratio — 표준 DPR 값 확인 (warning)."""
    val = _val((data.get("viewport") or {}).get("pixel_ratio"))
    if val is None:
        return _check_result(
            "PC-D-002", _SEV_WARNING, False,
            "viewport.pixel_ratio 누락",
            "pixel_ratio 미기재 — 렌더링 환경 추적 불가. 표준 DPR: " + str(_ALLOWED_DPRS),
        )
    if val not in _ALLOWED_DPRS:
        return _check_result(
            "PC-D-002", _SEV_WARNING, False,
            f"비표준 DPR: {val}",
            f"pixel_ratio={val}은 표준 DPR 목록에 없습니다. 비표준 값은 렌더링 왜곡 가능성이 있습니다.",
        )
    return _check_result("PC-D-002", _SEV_WARNING, True, f"DPR={val} ✔")


def check_pc_d_003(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-003: typography.base_font_size >= 14 (blocking, WCAG 1.4.4)."""
    val = _val((data.get("typography") or {}).get("base_font_size"))
    if val is None:
        return _check_result(
            "PC-D-003", _SEV_BLOCKING, False,
            "typography.base_font_size 누락",
            "WCAG 1.4.4: base_font_size 필드가 없습니다. 최소 14px 이상 필수.",
        )
    try:
        v = float(val)
    except (TypeError, ValueError):
        return _check_result(
            "PC-D-003", _SEV_BLOCKING, False,
            f"base_font_size 타입 오류: {val!r}",
            f"WCAG 1.4.4: base_font_size={val!r}은 숫자가 아닙니다.",
        )
    if v < 14:
        return _check_result(
            "PC-D-003", _SEV_BLOCKING, False,
            f"{v}px — 최소 14px 미달",
            f"WCAG 1.4.4: base_font_size={v}px는 최소 기준 14px 미만입니다. "
            "WCAG 1.4.4 텍스트 크기 조정 준수를 위해 14px 이상이 필요합니다.",
        )
    return _check_result("PC-D-003", _SEV_BLOCKING, True, f"{v}px ≥ 14px (WCAG 1.4.4) ✔")


def check_pc_d_004(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-004: typography.font_family_primary — 승인된 폰트 목록 확인 (warning)."""
    val = _val((data.get("typography") or {}).get("font_family_primary"))
    if val is None:
        return _check_result(
            "PC-D-004", _SEV_WARNING, False,
            "typography.font_family_primary 누락",
            f"font_family_primary 미기재. 승인 폰트 목록: {_ALLOWED_FONTS}",
        )
    if val not in _ALLOWED_FONTS:
        return _check_result(
            "PC-D-004", _SEV_WARNING, False,
            f"비승인 폰트: {val!r}",
            f"font_family_primary={val!r}은 디자인 시스템 승인 폰트 목록에 없습니다. "
            f"승인 폰트: {_ALLOWED_FONTS}. Pretendard 권장 (한국어 대응).",
        )
    return _check_result("PC-D-004", _SEV_WARNING, True, f"{val!r} ✔")


def check_pc_d_005(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-005: theme.contrast_ratio_min >= 4.5 (blocking, WCAG 1.4.3)."""
    val = _val((data.get("theme") or {}).get("contrast_ratio_min"))
    if val is None:
        return _check_result(
            "PC-D-005", _SEV_BLOCKING, False,
            "theme.contrast_ratio_min 누락",
            "WCAG 1.4.3: contrast_ratio_min 필드가 없습니다. 최소 4.5:1 이상 필수.",
        )
    try:
        v = float(val)
    except (TypeError, ValueError):
        return _check_result(
            "PC-D-005", _SEV_BLOCKING, False,
            f"contrast_ratio_min 타입 오류: {val!r}",
            f"WCAG 1.4.3: contrast_ratio_min={val!r}은 숫자가 아닙니다.",
        )
    if v < 4.5:
        return _check_result(
            "PC-D-005", _SEV_BLOCKING, False,
            f"대비율 {v}:1 — WCAG AA 4.5:1 미달",
            f"WCAG 1.4.3: contrast_ratio_min={v}는 AA 최솟값 4.5:1 미만입니다. "
            "일반 텍스트 WCAG AA 기준은 4.5:1 이상입니다.",
        )
    return _check_result("PC-D-005", _SEV_BLOCKING, True, f"{v}:1 ≥ 4.5:1 (WCAG 1.4.3) ✔")


def check_pc_d_006(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-006: theme.wcag_level — AA 이상 필수 (blocking)."""
    val = _val((data.get("theme") or {}).get("wcag_level"))
    if val is None:
        return _check_result(
            "PC-D-006", _SEV_BLOCKING, False,
            "theme.wcag_level 누락",
            "wcag_level 미기재. 최소 AA 이상 설정 필요. 'A' 단독 금지.",
        )
    if val not in _ALLOWED_WCAG_LEVELS:
        return _check_result(
            "PC-D-006", _SEV_BLOCKING, False,
            f"허용되지 않는 WCAG 등급: {val!r}",
            f"wcag_level={val!r}은 허용되지 않습니다. AA 미만 등급 설정은 금지입니다. "
            f"허용값: {_ALLOWED_WCAG_LEVELS}",
        )
    return _check_result("PC-D-006", _SEV_BLOCKING, True, f"WCAG {val} ✔")


def check_pc_d_007(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-007: theme.active_mode — 허용값(light/dark/system) 확인 (blocking)."""
    val = _val((data.get("theme") or {}).get("active_mode"))
    if val is None:
        return _check_result(
            "PC-D-007", _SEV_BLOCKING, False,
            "theme.active_mode 누락",
            f"active_mode 미기재. 허용 색상 모드: {_ALLOWED_ACTIVE_MODES}",
        )
    if val not in _ALLOWED_ACTIVE_MODES:
        return _check_result(
            "PC-D-007", _SEV_BLOCKING, False,
            f"허용되지 않는 색상 모드: {val!r}",
            f"active_mode={val!r}은 허용값 목록에 없습니다. "
            f"허용 색상 모드: {_ALLOWED_ACTIVE_MODES}",
        )
    return _check_result("PC-D-007", _SEV_BLOCKING, True, f"mode={val} ✔")


def check_pc_d_008(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-008: theme.focus_visible_outline — null/빈값 금지 (blocking, WCAG 2.4.7)."""
    theme = data.get("theme") or {}
    val = _val(theme.get("focus_visible_outline"))
    if val is None or val == "":
        return _check_result(
            "PC-D-008", _SEV_BLOCKING, False,
            "focus_visible_outline 미정의",
            "WCAG 2.4.7: focus_visible_outline이 null 또는 빈 값입니다. "
            "키보드 포커스 가시성 확보를 위해 반드시 정의되어야 합니다.",
        )
    return _check_result(
        "PC-D-008", _SEV_BLOCKING, True,
        f"{val!r} (WCAG 2.4.7) ✔",
    )


def check_pc_d_009(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-009: typography.rendering_engine — 허용 목록 확인 (warning)."""
    val = _val((data.get("typography") or {}).get("rendering_engine"))
    if val is None:
        return _check_result(
            "PC-D-009", _SEV_WARNING, False,
            "typography.rendering_engine 누락",
            f"rendering_engine 미기재. 허용 렌더링 엔진: {_ALLOWED_RENDER_ENGINES}",
        )
    if val not in _ALLOWED_RENDER_ENGINES:
        return _check_result(
            "PC-D-009", _SEV_WARNING, False,
            f"비허용 렌더링 엔진: {val!r}",
            f"rendering_engine={val!r}은 허용 목록에 없습니다. "
            f"렌더링 일관성을 위해 허용값 사용 권장: {_ALLOWED_RENDER_ENGINES}",
        )
    return _check_result("PC-D-009", _SEV_WARNING, True, f"engine={val} ✔")


def check_pc_d_010(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-010: theme.color_token_version — vX.Y 형식 확인 (warning)."""
    val = _val((data.get("theme") or {}).get("color_token_version"))
    if val is None:
        return _check_result(
            "PC-D-010", _SEV_WARNING, False,
            "theme.color_token_version 누락",
            "color_token_version 미기재 — 이상치 추적 불가. vX.Y 형식 필요.",
        )
    if not _TOKEN_VER_RE.match(str(val)):
        return _check_result(
            "PC-D-010", _SEV_WARNING, False,
            f"형식 오류: {val!r}",
            f"color_token_version={val!r}은 vX.Y 형식이 아닙니다. "
            "이상치 추적을 위해 vX.Y (예: v1.0) 형식으로 기재하세요.",
        )
    return _check_result("PC-D-010", _SEV_WARNING, True, f"token_version={val} ✔")


def check_pc_d_011(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-011: typography.line_height_base >= 1.5 (warning, WCAG 1.4.8)."""
    val = _val((data.get("typography") or {}).get("line_height_base"))
    if val is None:
        return _check_result(
            "PC-D-011", _SEV_WARNING, False,
            "typography.line_height_base 누락",
            "WCAG 1.4.8: line_height_base 미기재. 권장값 1.5 이상.",
        )
    try:
        v = float(val)
    except (TypeError, ValueError):
        return _check_result(
            "PC-D-011", _SEV_WARNING, False,
            f"line_height_base 타입 오류: {val!r}",
            f"WCAG 1.4.8: line_height_base={val!r}은 숫자가 아닙니다.",
        )
    if v < 1.5:
        return _check_result(
            "PC-D-011", _SEV_WARNING, False,
            f"줄 높이 {v} — 권장 1.5 미달",
            f"WCAG 1.4.8: line_height_base={v}는 권장값 1.5 미만입니다. "
            "시각적 표현 가이드라인 준수를 위해 1.5 이상 권장.",
        )
    return _check_result("PC-D-011", _SEV_WARNING, True, f"line_height={v} ≥ 1.5 (WCAG 1.4.8) ✔")


def check_pc_d_012(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-012: theme.motion_safe == true (warning, WCAG 2.3.3)."""
    theme = data.get("theme") or {}
    if "motion_safe" not in theme:
        return _check_result(
            "PC-D-012", _SEV_WARNING, False,
            "theme.motion_safe 누락",
            "WCAG 2.3.3: motion_safe 미기재. prefers-reduced-motion 준수를 위해 true 권장.",
        )
    val = _val(theme["motion_safe"])
    if val is not True and str(val).lower() not in ("true", "1", "yes"):
        return _check_result(
            "PC-D-012", _SEV_WARNING, False,
            f"motion_safe={val!r}",
            f"WCAG 2.3.3: motion_safe={val!r}. prefers-reduced-motion 미디어 쿼리 준수를 위해 "
            "true로 설정하고 애니메이션 대안을 제공해야 합니다.",
        )
    return _check_result("PC-D-012", _SEV_WARNING, True, "motion_safe=true (WCAG 2.3.3) ✔")


def check_pc_d_013(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-013: component_library.version — SemVer(X.Y.Z) 형식 확인 (warning)."""
    val = _val((data.get("component_library") or {}).get("version"))
    if val is None:
        return _check_result(
            "PC-D-013", _SEV_WARNING, False,
            "component_library.version 누락",
            "컴포넌트 라이브러리 버전 미기재. SemVer(X.Y.Z) 형식 필요.",
        )
    if not _SEMVER_RE.match(str(val)):
        return _check_result(
            "PC-D-013", _SEV_WARNING, False,
            f"SemVer 형식 오류: {val!r}",
            f"component_library.version={val!r}은 SemVer(X.Y.Z) 형식이 아닙니다.",
        )
    return _check_result("PC-D-013", _SEV_WARNING, True, f"version={val} (SemVer) ✔")


def check_pc_d_014(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-014: design_tools.figma.version — 미기재 시 정보 경고 (info)."""
    val = _val(((data.get("design_tools") or {}).get("figma") or {}).get("version"))
    if val is None or val == "":
        return _check_result(
            "PC-D-014", _SEV_INFO, False,
            "design_tools.figma.version 누락",
            "Figma 버전 미기재 — 렌더링 환경 추적 불가. 버전 명시 권장.",
        )
    return _check_result("PC-D-014", _SEV_INFO, True, f"figma={val} ✔")


def check_pc_d_015(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-015: design_tools.storybook.version — 미기재 시 정보 경고 (info)."""
    val = _val(((data.get("design_tools") or {}).get("storybook") or {}).get("version"))
    if val is None or val == "":
        return _check_result(
            "PC-D-015", _SEV_INFO, False,
            "design_tools.storybook.version 누락",
            "Storybook 버전 미기재. 버전 명시 권장.",
        )
    return _check_result("PC-D-015", _SEV_INFO, True, f"storybook={val} ✔")


def check_pc_d_016(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-016: retry_policy.max_retries — 1~5 범위 확인 (warning)."""
    val = _val((data.get("retry_policy") or {}).get("max_retries"))
    if val is None:
        return _check_result(
            "PC-D-016", _SEV_WARNING, False,
            "retry_policy.max_retries 누락",
            "retry_policy.max_retries 미기재. 무한 재시도 방지를 위해 1~5 범위 내 설정 필요.",
        )
    try:
        v = int(val)
    except (TypeError, ValueError):
        return _check_result(
            "PC-D-016", _SEV_WARNING, False,
            f"max_retries 타입 오류: {val!r}",
            f"retry_policy.max_retries={val!r}은 정수가 아닙니다.",
        )
    if not (1 <= v <= 5):
        return _check_result(
            "PC-D-016", _SEV_WARNING, False,
            f"max_retries={v} — 허용 범위 1~5 초과",
            f"retry_policy.max_retries={v}은 허용 범위(1~5)를 벗어났습니다. 무한 재시도 방지 정책 위반.",
        )
    return _check_result("PC-D-016", _SEV_WARNING, True, f"max_retries={v} (1~5) ✔")


# ---------------------------------------------------------------------------
# 전체 체크 실행
# ---------------------------------------------------------------------------

_ALL_CHECKS = [
    check_pc_d_001, check_pc_d_002, check_pc_d_003, check_pc_d_004,
    check_pc_d_005, check_pc_d_006, check_pc_d_007, check_pc_d_008,
    check_pc_d_009, check_pc_d_010, check_pc_d_011, check_pc_d_012,
    check_pc_d_013, check_pc_d_014, check_pc_d_015, check_pc_d_016,
]


def run_design_preflight_checks(
    baseline_path: str = _DEFAULT_BASELINE_PATH,
    exit_on_fail: bool = True,
) -> dict[str, Any]:
    """design-baseline.yaml PC-D-001~016 전체 체크 실행.

    RETRO-11 표준 인터페이스.

    Parameters
    ----------
    baseline_path:
        design-baseline.yaml 경로. 기본값은 프로젝트 루트 config/.
    exit_on_fail:
        True이면 blocking 체크 실패 시 sys.exit(1) 호출.
        False이면 결과 dict만 반환 (conftest.py 연동 시 사용).

    Returns
    -------
    dict
        {
          "passed": bool,
          "blocking_results": [...],   # severity=blocking 체크 결과
          "warning_results": [...],    # severity=warning 체크 결과
          "info_results": [...],       # severity=info 체크 결과
          "design_baseline_version": str,
          "checked_at": str,           # ISO8601 UTC
        }
    """
    # SKIP 체크 (SKIP_DESIGN_PREFLIGHT: 모듈 자체 skip)
    # SKIP_PREFLIGHT는 conftest.py에서 처리 — 모듈은 직접 호출 시 항상 실행
    if os.environ.get("SKIP_DESIGN_PREFLIGHT", "").lower() in ("1", "true", "yes"):
        print("[design pre-flight] SKIP_DESIGN_PREFLIGHT=1 — 체크 생략", flush=True)
        return _skipped_result()

    path = Path(baseline_path)
    checked_at = datetime.now(tz=timezone.utc).isoformat()

    # 파일 로드
    if not path.exists():
        print(
            f"[design pre-flight] design-baseline.yaml 없음: {path} — 체크 생략 (WARN)",
            flush=True,
        )
        return _skipped_result()

    try:
        data = _load_yaml(path)
    except Exception as exc:  # noqa: BLE001
        result = {
            "passed": False,
            "blocking_results": [],
            "warning_results": [],
            "info_results": [],
            "design_baseline_version": "unknown",
            "checked_at": checked_at,
            "error": f"design-baseline.yaml 파싱 실패: {exc}",
        }
        if exit_on_fail:
            print(f"❌ design pre-flight FAIL: {result['error']}", file=sys.stderr, flush=True)
            sys.exit(1)
        return result

    design_baseline_version = str(
        data.get("baseline_version") or data.get("infra_baseline_version", "unknown")
    )

    # 체크 실행
    blocking_results: list[dict[str, Any]] = []
    warning_results: list[dict[str, Any]] = []
    info_results: list[dict[str, Any]] = []

    for fn in _ALL_CHECKS:
        r = fn(data)
        if r["severity"] == _SEV_BLOCKING:
            blocking_results.append(r)
        elif r["severity"] == _SEV_WARNING:
            warning_results.append(r)
        else:
            info_results.append(r)

    # 전체 통과 여부: blocking 중 하나라도 실패하면 False
    passed = all(r["passed"] for r in blocking_results)

    result = {
        "passed": passed,
        "blocking_results": blocking_results,
        "warning_results": warning_results,
        "info_results": info_results,
        "design_baseline_version": design_baseline_version,
        "checked_at": checked_at,
        "data": data,  # 헤더 빌드용 원본 데이터
    }

    if not passed and exit_on_fail:
        failed_ids = [r["id"] for r in blocking_results if not r["passed"]]
        print(
            f"❌ design pre-flight FAIL — blocking 체크 실패: {failed_ids}",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)

    return result


def _skipped_result() -> dict[str, Any]:
    """SKIP 환경변수 설정 시 반환하는 결과 dict."""
    return {
        "passed": True,
        "skipped": True,
        "blocking_results": [],
        "warning_results": [],
        "info_results": [],
        "design_baseline_version": "skipped",
        "checked_at": datetime.now(tz=timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# conftest.py 헤더 출력용 dict 빌드
# ---------------------------------------------------------------------------

def build_design_preflight_header_result(
    check_result: dict[str, Any],
) -> dict[str, Any]:
    """run_design_preflight_checks() 반환값을 헤더 출력용 dict로 변환.

    Parameters
    ----------
    check_result:
        run_design_preflight_checks() 반환값

    Returns
    -------
    dict
        _print_design_preflight_header() 인자 형식:
        {
          "design_baseline_version": str,
          "viewport": str,
          "font": str,
          "base_font_size": int,
          "theme": str,
          "wcag_level": str,
          "token_version": str,
          "component_lib_version": str,
          "blocking_pass": int,
          "blocking_total": int,
          "warning_pass": int,
          "warning_total": int,
          "checked_at": str,
          "status": "PASS" | "FAIL",
        }
    """
    data = check_result.get("data") or {}
    blocking = check_result.get("blocking_results", [])
    warning = check_result.get("warning_results", [])

    viewport_data = data.get("viewport") or {}
    typo_data = data.get("typography") or {}
    theme_data = data.get("theme") or {}
    comp_data = data.get("component_library") or {}

    # viewport 표시: device_presets default + width
    device = _val(viewport_data.get("device_presets")) or "desktop"
    width = _val(viewport_data.get("default_width")) or "?"
    viewport_str = f"{device} ({width}px)"

    # font 표시
    font_family = _val(typo_data.get("font_family_primary")) or "?"
    base_size = _val(typo_data.get("base_font_size")) or "?"
    font_str = f"{font_family} / {base_size}px"

    # theme 표시
    active_mode = _val(theme_data.get("active_mode")) or "?"
    wcag_level = _val(theme_data.get("wcag_level")) or "?"
    contrast = _val(theme_data.get("contrast_ratio_min")) or "?"
    theme_str = f"{active_mode} (WCAG {wcag_level}, {contrast}:1)"

    # 컴포넌트 라이브러리
    comp_name = _val(comp_data.get("package_name")) or "@aiorg/design-system"
    comp_ver = _val(comp_data.get("version")) or "?"
    comp_str = f"{comp_name}@{comp_ver}"

    # 통과/전체 카운트
    blocking_pass = sum(1 for r in blocking if r["passed"])
    blocking_total = len(blocking)
    warning_pass = sum(1 for r in warning if r["passed"])
    warning_total = len(warning)

    status = "PASS" if check_result.get("passed", False) else "FAIL"
    if check_result.get("skipped"):
        status = "SKIP"

    return {
        "design_baseline_version": check_result.get("design_baseline_version", "unknown"),
        "viewport": viewport_str,
        "font": font_str,
        "base_font_size": base_size,
        "theme": theme_str,
        "wcag_level": wcag_level,
        "token_version": _val(theme_data.get("color_token_version")) or "?",
        "component_lib_version": comp_str,
        "blocking_pass": blocking_pass,
        "blocking_total": blocking_total,
        "warning_pass": warning_pass,
        "warning_total": warning_total,
        "checked_at": check_result.get("checked_at", "?"),
        "status": status,
    }
