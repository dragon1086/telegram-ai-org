"""tools/design_preflight.py — 디자인 렌더링 환경 pre-flight 체크 스크립트.

config/design-baseline.yaml 을 읽어 PC-D-001 ~ PC-D-012 항목을 검증한다.
error 등급 실패 항목이 있으면 원인 로그를 출력하고 exit(1)로 종료.
warn 등급은 경고 후 계속 진행.

사용법:
    python tools/design_preflight.py
    python tools/design_preflight.py --config config/design-baseline.yaml
    python tools/design_preflight.py --strict          # warn도 실패로 처리
    python tools/design_preflight.py --quiet           # 통과 항목 출력 억제

T-PERM-002: 원인 로그 테스트 (2026-03-27)
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore[import-untyped]
except ImportError:
    yaml = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "design-baseline.yaml"

# PC-D 체크 결과 등급
_LEVEL_PASS = "PASS"
_LEVEL_WARN = "WARN"
_LEVEL_FAIL = "FAIL"


# ---------------------------------------------------------------------------
# YAML 로더
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict[str, Any]:
    """YAML 파일을 읽어 dict 반환."""
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        return yaml.safe_load(text) or {}
    # PyYAML 없을 때 간이 파서 (key: scalar 형태만 지원)
    result: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(0, result)]
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        # 리스트 아이템 무시 (간이 파서 한계)
        if stripped.startswith("- "):
            continue
        if ":" in stripped:
            key, _, raw = stripped.partition(":")
            key = key.strip()
            val_str = raw.split("#")[0].strip().strip('"').strip("'")
            # 부모 컨텍스트 결정
            while len(stack) > 1 and stack[-1][0] >= indent:
                stack.pop()
            parent = stack[-1][1]
            if val_str == "":
                child: dict[str, Any] = {}
                parent[key] = child
                stack.append((indent, child))
            elif val_str.lstrip("-").replace(".", "", 1).isdigit():
                try:
                    parent[key] = int(val_str)
                except ValueError:
                    parent[key] = float(val_str)
            elif val_str.lower() in ("true", "false"):
                parent[key] = val_str.lower() == "true"
            else:
                parent[key] = val_str
    return result


# ---------------------------------------------------------------------------
# 체크 결과 헬퍼
# ---------------------------------------------------------------------------

def _result(
    check_id: str,
    level: str,
    target: str,
    outcome: str,
    cause: str = "",
) -> dict[str, Any]:
    """원인 로그를 포함한 체크 결과 dict 반환.

    Args:
        check_id: PC-D-NNN 형식 식별자
        level:    PASS | WARN | FAIL
        target:   검증 대상 필드 경로 (dot-notation)
        outcome:  결과 한 줄 요약
        cause:    실패/경고 원인 설명 (PASS이면 빈 문자열)
    """
    return {
        "id": check_id,
        "level": level,
        "target": target,
        "outcome": outcome,
        "cause": cause,
    }


# ---------------------------------------------------------------------------
# PC-D 체크 함수 (001 ~ 012)
# ---------------------------------------------------------------------------

def _get_nested(data: dict[str, Any], dotpath: str) -> Any:
    """dot-notation 경로로 중첩 dict 값을 꺼낸다.

    design-baseline.yaml 은 각 필드가 아래 두 형태 중 하나로 정의된다:
      ① 스칼라:  viewport.default_width: 1440
      ② 메타객체: viewport.default_width: {default: 1440, allowed_values: [...], description: "..."}

    메타객체 형태일 때 자동으로 `default` 키의 값을 반환한다.
    """
    parts = dotpath.split(".")
    node: Any = data
    for part in parts:
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    # 메타객체 패턴 감지: dict이고 'default' 키가 있으면 default 값을 추출
    if isinstance(node, dict) and "default" in node:
        return node["default"]
    return node


def check_pc_d_001(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-001: viewport.default_width 허용값 목록 내 여부."""
    target = "viewport.default_width"
    allowed = [375, 768, 1024, 1280, 1440, 1920]
    val = _get_nested(data, target)
    if val is None:
        return _result("PC-D-001", _LEVEL_FAIL, target,
                       "필드 누락",
                       f"'{target}' 필드가 design-baseline.yaml에 없습니다.")
    try:
        val = int(val)
    except (TypeError, ValueError):
        return _result("PC-D-001", _LEVEL_FAIL, target,
                       f"타입 오류: {val!r}",
                       f"정수 값이 아닙니다 (실제 타입: {type(val).__name__}).")
    if val not in allowed:
        return _result("PC-D-001", _LEVEL_FAIL, target,
                       f"비허용값: {val}",
                       f"허용값 목록 {allowed}에 없습니다. "
                       f"비표준 해상도는 와이어프레임 정합성을 깨뜨릴 수 있습니다.")
    return _result("PC-D-001", _LEVEL_PASS, target, f"{val}px ✔")


def check_pc_d_002(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-002: viewport.pixel_ratio 표준 DPR 값 여부 (warn)."""
    target = "viewport.pixel_ratio"
    allowed = [1, 1.5, 2, 3]
    val = _get_nested(data, target)
    if val is None:
        return _result("PC-D-002", _LEVEL_WARN, target,
                       "필드 누락 (경고)",
                       f"'{target}' 필드가 없어 기본값(1) 사용을 가정합니다.")
    try:
        val = float(val)
    except (TypeError, ValueError):
        return _result("PC-D-002", _LEVEL_WARN, target,
                       f"타입 오류: {val!r} (경고)",
                       "숫자 값이 아닙니다. 렌더링 왜곡 가능성이 있습니다.")
    if val not in allowed:
        return _result("PC-D-002", _LEVEL_WARN, target,
                       f"비표준 DPR: {val} (경고)",
                       f"표준 DPR 목록 {allowed}에 없습니다. "
                       f"비표준 값은 렌더링 왜곡 가능성이 있습니다.")
    return _result("PC-D-002", _LEVEL_PASS, target, f"DPR={val} ✔")


def check_pc_d_003(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-003: typography.base_font_size >= 14 (WCAG 1.4.4)."""
    target = "typography.base_font_size"
    val = _get_nested(data, target)
    if val is None:
        return _result("PC-D-003", _LEVEL_FAIL, target,
                       "필드 누락",
                       f"'{target}' 필드가 없습니다. WCAG 1.4.4 준수를 위해 필수 항목입니다.")
    try:
        val = int(val)
    except (TypeError, ValueError):
        return _result("PC-D-003", _LEVEL_FAIL, target,
                       f"타입 오류: {val!r}",
                       "정수 값이 아닙니다.")
    if val < 14:
        return _result("PC-D-003", _LEVEL_FAIL, target,
                       f"{val}px — 최소 14px 미달",
                       f"현재 {val}px < 14px. "
                       f"WCAG 1.4.4(텍스트 크기 조정) 준수를 위해 최소 14px 이상 필수입니다.")
    return _result("PC-D-003", _LEVEL_PASS, target, f"{val}px >= 14px ✔ (WCAG 1.4.4)")


def check_pc_d_004(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-004: typography.font_family_primary 허용 목록 내 여부 (warn)."""
    target = "typography.font_family_primary"
    allowed = ["Pretendard", "Inter", "Noto Sans KR", "system-ui"]
    val = _get_nested(data, target)
    if val is None:
        return _result("PC-D-004", _LEVEL_WARN, target,
                       "필드 누락 (경고)",
                       f"'{target}' 필드가 없습니다. 디자인 시스템 폰트를 명시해 주세요.")
    if str(val) not in allowed:
        return _result("PC-D-004", _LEVEL_WARN, target,
                       f"비승인 폰트: {val!r} (경고)",
                       f"승인 폰트 목록 {allowed}에 없습니다. "
                       f"한국어 대응 시 Pretendard 또는 Noto Sans KR을 권장합니다.")
    return _result("PC-D-004", _LEVEL_PASS, target, f'"{val}" ✔')


def check_pc_d_005(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-005: theme.contrast_ratio_min >= 4.5 (WCAG 1.4.3)."""
    target = "theme.contrast_ratio_min"
    val = _get_nested(data, target)
    if val is None:
        return _result("PC-D-005", _LEVEL_FAIL, target,
                       "필드 누락",
                       f"'{target}' 필드가 없습니다. WCAG 1.4.3(텍스트 대비) 필수 항목입니다.")
    try:
        val = float(val)
    except (TypeError, ValueError):
        return _result("PC-D-005", _LEVEL_FAIL, target,
                       f"타입 오류: {val!r}",
                       "숫자 값이 아닙니다.")
    if val < 4.5:
        return _result("PC-D-005", _LEVEL_FAIL, target,
                       f"대비율 {val}:1 — WCAG AA 기준(4.5:1) 미달",
                       f"현재 {val}:1 < 4.5:1. "
                       f"WCAG 1.4.3 AA 준수를 위해 최소 4.5:1 이상 필수입니다. "
                       f"(대형 텍스트 18pt+ 는 3.0:1 허용, AAA는 7.0:1 요구)")
    return _result("PC-D-005", _LEVEL_PASS, target, f"대비율 {val}:1 >= 4.5:1 ✔ (WCAG 1.4.3)")


def check_pc_d_006(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-006: theme.wcag_level AA 또는 AAA."""
    target = "theme.wcag_level"
    allowed = ["AA", "AAA"]
    val = _get_nested(data, target)
    if val is None:
        return _result("PC-D-006", _LEVEL_FAIL, target,
                       "필드 누락",
                       f"'{target}' 필드가 없습니다. 최소 AA 등급 설정이 필수입니다.")
    if str(val) not in allowed:
        return _result("PC-D-006", _LEVEL_FAIL, target,
                       f"등급 {val!r} — AA/AAA 아님",
                       f"현재 등급 {val!r}는 허용 목록 {allowed}에 없습니다. "
                       f"'A' 단독 설정은 금지됩니다. 최소 'AA'로 상향 필요.")
    return _result("PC-D-006", _LEVEL_PASS, target, f"WCAG {val} ✔")


def check_pc_d_007(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-007: theme.active_mode 허용값 내."""
    target = "theme.active_mode"
    allowed = ["light", "dark", "system"]
    val = _get_nested(data, target)
    if val is None:
        return _result("PC-D-007", _LEVEL_FAIL, target,
                       "필드 누락",
                       f"'{target}' 필드가 없습니다. 색상 모드(light/dark/system)를 명시해야 합니다.")
    if str(val) not in allowed:
        return _result("PC-D-007", _LEVEL_FAIL, target,
                       f"모드 {val!r} — 허용값 아님",
                       f"허용 모드 {allowed} 외의 값 {val!r}입니다. "
                       f"OS 미디어 쿼리 연동 시 'system'을 사용하세요.")
    return _result("PC-D-007", _LEVEL_PASS, target, f"모드={val!r} ✔")


def check_pc_d_008(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-008: theme.focus_visible_outline 빈 값 금지 (WCAG 2.4.7)."""
    target = "theme.focus_visible_outline"
    val = _get_nested(data, target)
    if val is None or str(val).strip() == "":
        cause = (
            f"'{target}' 필드가 없거나 빈 값입니다. "
            f"WCAG 2.4.7(포커스 가시성)은 키보드 탐색 시 포커스 표시를 의무화합니다. "
            f"예: '2px solid #2563EB'"
        )
        return _result("PC-D-008", _LEVEL_FAIL, target, "포커스 스타일 미정의", cause)
    return _result("PC-D-008", _LEVEL_PASS, target, f'"{val}" ✔ (WCAG 2.4.7)')


def check_pc_d_009(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-009: typography.rendering_engine 허용 목록 내 여부 (warn)."""
    target = "typography.rendering_engine"
    allowed = ["auto", "antialiased", "subpixel-antialiased", "none"]
    val = _get_nested(data, target)
    if val is None:
        return _result("PC-D-009", _LEVEL_WARN, target,
                       "필드 누락 (경고)",
                       f"'{target}' 필드가 없습니다. "
                       f"macOS/iOS는 'antialiased', Windows는 'subpixel-antialiased'를 권장합니다.")
    if str(val) not in allowed:
        return _result("PC-D-009", _LEVEL_WARN, target,
                       f"비허용 렌더링 엔진: {val!r} (경고)",
                       f"허용 목록 {allowed}에 없습니다. 폰트 렌더링 품질이 저하될 수 있습니다.")
    return _result("PC-D-009", _LEVEL_PASS, target, f'렌더링 엔진="{val}" ✔')


def check_pc_d_010(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-010: theme.color_token_version vX.Y 형식 여부 (warn)."""
    target = "theme.color_token_version"
    val = _get_nested(data, target)
    if val is None:
        return _result("PC-D-010", _LEVEL_WARN, target,
                       "필드 누락 (경고)",
                       f"'{target}' 필드가 없습니다. 이상치 발생 시 토큰 버전 추적이 불가능합니다.")
    if not re.match(r"^v\d+\.\d+$", str(val)):
        return _result("PC-D-010", _LEVEL_WARN, target,
                       f"형식 오류: {val!r} (경고)",
                       f"vX.Y 형식이 아닙니다 (예: 'v1.0', 'v2.3'). "
                       f"버전 형식 불일치 시 이상치 추적 자동화가 실패할 수 있습니다.")
    return _result("PC-D-010", _LEVEL_PASS, target, f"color_token_version={val!r} ✔")


def check_pc_d_011(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-011: typography.line_height_base >= 1.5 (WCAG 1.4.8, warn)."""
    target = "typography.line_height_base"
    val = _get_nested(data, target)
    if val is None:
        return _result("PC-D-011", _LEVEL_WARN, target,
                       "필드 누락 (경고)",
                       f"'{target}' 필드가 없습니다. WCAG 1.4.8 권고에 따라 1.5 이상을 명시해 주세요.")
    try:
        val = float(val)
    except (TypeError, ValueError):
        return _result("PC-D-011", _LEVEL_WARN, target,
                       f"타입 오류: {val!r} (경고)",
                       "숫자 값이 아닙니다.")
    if val < 1.5:
        return _result("PC-D-011", _LEVEL_WARN, target,
                       f"줄 높이 {val} < 1.5 (경고)",
                       f"현재 {val} < 1.5. "
                       f"WCAG 1.4.8 시각적 표현 권고를 충족하려면 1.5 이상을 사용하세요.")
    return _result("PC-D-011", _LEVEL_PASS, target, f"line_height={val} >= 1.5 ✔ (WCAG 1.4.8)")


def check_pc_d_012(data: dict[str, Any]) -> dict[str, Any]:
    """PC-D-012: theme.motion_safe == true (WCAG 2.3.3, warn)."""
    target = "theme.motion_safe"
    val = _get_nested(data, target)
    if val is None:
        return _result("PC-D-012", _LEVEL_WARN, target,
                       "필드 누락 (경고)",
                       f"'{target}' 필드가 없습니다. "
                       f"WCAG 2.3.3(애니메이션 유발 금지) 준수 여부를 명시해 주세요.")
    if val is not True and str(val).lower() != "true":
        return _result("PC-D-012", _LEVEL_WARN, target,
                       f"motion_safe={val!r} — false (경고)",
                       f"prefers-reduced-motion 미디어 쿼리를 준수하지 않는 설정입니다. "
                       f"WCAG 2.3.3에 따라 애니메이션 대안 제공이 필수입니다.")
    return _result("PC-D-012", _LEVEL_PASS, target, "motion_safe=true ✔ (WCAG 2.3.3)")


# ---------------------------------------------------------------------------
# 전체 체크 실행
# ---------------------------------------------------------------------------

_ALL_CHECKS = [
    check_pc_d_001,
    check_pc_d_002,
    check_pc_d_003,
    check_pc_d_004,
    check_pc_d_005,
    check_pc_d_006,
    check_pc_d_007,
    check_pc_d_008,
    check_pc_d_009,
    check_pc_d_010,
    check_pc_d_011,
    check_pc_d_012,
]


def run_design_preflight(
    config_path: Path | None = None,
    strict: bool = False,
    quiet: bool = False,
) -> dict[str, Any]:
    """design-baseline.yaml 기반 pre-flight 검증 실행.

    Returns:
        {
          "status":   "PASS" | "WARN" | "FAIL",
          "results":  [... 각 PC-D 결과 ...],
          "errors":   [실패 항목 목록],
          "warnings": [경고 항목 목록],
          "timestamp": ISO 문자열,
          "baseline_version": 파일의 infra_baseline_version 값,
          "schema_version":   파일의 schema_version 값,
        }
    """
    path = config_path or _DEFAULT_CONFIG_PATH

    # 파일 로드
    if not path.exists():
        ts = _now_iso()
        msg = f"design-baseline.yaml을 찾을 수 없습니다: {path}"
        _print_err(msg)
        return {
            "status": _LEVEL_FAIL,
            "results": [],
            "errors": [msg],
            "warnings": [],
            "timestamp": ts,
            "baseline_version": "unknown",
            "schema_version": "unknown",
        }

    try:
        data = _load_yaml(path)
    except Exception as exc:  # noqa: BLE001
        ts = _now_iso()
        msg = f"design-baseline.yaml 파싱 실패: {exc}"
        _print_err(msg)
        return {
            "status": _LEVEL_FAIL,
            "results": [],
            "errors": [msg],
            "warnings": [],
            "timestamp": ts,
            "baseline_version": "unknown",
            "schema_version": "unknown",
        }

    baseline_version = str(data.get("infra_baseline_version", "unknown"))
    schema_version = str(data.get("schema_version", "unknown"))

    if not quiet:
        print(f"\n🎨 design pre-flight 체크 시작 (schema_version={schema_version}, "
              f"infra_baseline={baseline_version})", flush=True)
        print(f"   config: {path}", flush=True)
        print("", flush=True)

    results: list[dict[str, Any]] = []
    errors: list[str] = []
    warnings: list[str] = []

    for fn in _ALL_CHECKS:
        r = fn(data)
        results.append(r)
        level = r["level"]
        check_id = r["id"]
        target = r["target"]
        outcome = r["outcome"]
        cause = r.get("cause", "")

        if level == _LEVEL_PASS:
            if not quiet:
                _print_ok(f"  [{check_id}] {target}: {outcome}")
        elif level == _LEVEL_WARN:
            warnings.append(f"[{check_id}] {target} — {outcome}")
            if not quiet:
                _print_warn(f"  [{check_id}] {target}: {outcome}")
            if cause and not quiet:
                _print_warn(f"           원인: {cause}")
            if strict:
                errors.append(f"[{check_id}] (strict) {target} — {outcome}")
        else:  # FAIL
            errors.append(f"[{check_id}] {target} — {outcome}")
            _print_err(f"  [{check_id}] {target}: {outcome}")
            if cause:
                _print_err(f"           원인: {cause}")

    # 최종 판정
    ts = _now_iso()
    if errors:
        overall = _LEVEL_FAIL
    elif warnings:
        overall = _LEVEL_WARN
    else:
        overall = _LEVEL_PASS

    # 결과 헤더 출력
    print("", flush=True)
    if overall == _LEVEL_PASS:
        print(f"✅ design pre-flight PASS — {ts}", flush=True)
    elif overall == _LEVEL_WARN:
        print(f"⚠️  design pre-flight WARN — {ts} ({len(warnings)}건 경고)", flush=True)
        for w in warnings:
            print(f"   ⚠ {w}", flush=True)
    else:
        print(
            f"\n❌ design pre-flight FAIL — {ts} ({len(errors)}건 오류)",
            file=sys.stderr,
            flush=True,
        )
        for e in errors:
            print(f"   → {e}", file=sys.stderr, flush=True)

    return {
        "status": overall,
        "results": results,
        "errors": errors,
        "warnings": warnings,
        "timestamp": ts,
        "baseline_version": baseline_version,
        "schema_version": schema_version,
    }


# ---------------------------------------------------------------------------
# 출력 헬퍼
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _print_ok(msg: str) -> None:
    print(f"  ✔ {msg}", flush=True)


def _print_warn(msg: str) -> None:
    print(f"  ⚠ {msg}", flush=True)


def _print_err(msg: str) -> None:
    print(f"  ✗ {msg}", file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# CLI 진입점
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="design pre-flight 체크: design-baseline.yaml 기반 렌더링 환경 검증"
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="design-baseline.yaml 경로 (기본: config/design-baseline.yaml)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="warn 항목도 FAIL로 처리",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="PASS 항목 출력 억제",
    )
    args = parser.parse_args()

    report = run_design_preflight(
        config_path=args.config,
        strict=args.strict,
        quiet=args.quiet,
    )
    sys.exit(0 if report["status"] != _LEVEL_FAIL else 1)


if __name__ == "__main__":
    main()
