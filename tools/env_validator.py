#!/usr/bin/env python3
"""
env_validator.py — 런타임 환경변수 검증 모듈

telegram-ai-org 가동 전 필수/권장 환경변수가 올바르게 설정됐는지 검사한다.
setup.sh의 pre-flight 체크와 연동되며, conftest.py 에서도 import 가능하다.

사용법:
    # 직접 실행 (진단 목적)
    python tools/env_validator.py
    python tools/env_validator.py --strict   # 권장 항목 누락 시도 EXIT 1

    # 코드에서 import
    from tools.env_validator import validate_env, EnvValidationError
    validate_env(strict=False)   # 필수 누락 시 EnvValidationError 발생
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


# ─── 검증 레벨 정의 ───────────────────────────────────────────────────────────

class Severity(str, Enum):
    """환경변수 누락 시 심각도."""
    REQUIRED = "REQUIRED"   # 누락 시 봇 기동 불가 — validate_env() raises
    RECOMMENDED = "RECOMMENDED"  # 누락 시 경고 — strict 모드에서만 raise
    OPTIONAL = "OPTIONAL"   # 누락 시 정보성 메시지만


@dataclass
class EnvSpec:
    """단일 환경변수 검증 스펙."""
    key: str
    severity: Severity
    description: str
    example: str = ""
    validator: Optional[object] = None  # callable(value: str) -> bool | None


@dataclass
class ValidationReport:
    """validate_env() 실행 결과 리포트."""
    missing_required: list[str] = field(default_factory=list)
    missing_recommended: list[str] = field(default_factory=list)
    missing_optional: list[str] = field(default_factory=list)
    invalid_values: list[tuple[str, str]] = field(default_factory=list)  # (key, reason)
    present: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """필수 변수 모두 존재하고 유효하면 True."""
        return not self.missing_required and not self.invalid_values

    @property
    def strict_ok(self) -> bool:
        """필수 + 권장 변수 모두 존재하면 True."""
        return self.ok and not self.missing_recommended


class EnvValidationError(RuntimeError):
    """필수 환경변수 누락 또는 값 오류 시 발생."""


# ─── 검증 스펙 정의 ───────────────────────────────────────────────────────────

def _non_empty(value: str) -> bool:
    return bool(value.strip())


def _is_bot_token(value: str) -> bool:
    """Telegram bot token 형식 검사: <digits>:<35chars>."""
    parts = value.strip().split(":")
    if len(parts) != 2:
        return False
    return parts[0].isdigit() and len(parts[1]) >= 30


ENV_SPECS: list[EnvSpec] = [
    # ── Telegram 봇 토큰 ────────────────────────────────────────────────────
    EnvSpec(
        key="PM_BOT_TOKEN",
        severity=Severity.REQUIRED,
        description="PM 봇 Telegram Bot Token (@BotFather 발급)",
        example="123456789:ABCdefGHIjklMNOpqrSTUVwxyz012345678",
        validator=_is_bot_token,
    ),
    EnvSpec(
        key="DEV_BOT_TOKEN",
        severity=Severity.RECOMMENDED,
        description="개발실 워커 봇 Token",
        example="123456789:ABCdefGHIjklMNOpqrSTUVwxyz012345678",
        validator=_is_bot_token,
    ),
    EnvSpec(
        key="DESIGN_BOT_TOKEN",
        severity=Severity.OPTIONAL,
        description="디자인실 워커 봇 Token",
        example="123456789:ABCdefGHIjklMNOpqrSTUVwxyz012345678",
        validator=_is_bot_token,
    ),
    EnvSpec(
        key="PLAN_BOT_TOKEN",
        severity=Severity.OPTIONAL,
        description="기획실 워커 봇 Token",
        example="123456789:ABCdefGHIjklMNOpqrSTUVwxyz012345678",
        validator=_is_bot_token,
    ),
    EnvSpec(
        key="GROWTH_BOT_TOKEN",
        severity=Severity.OPTIONAL,
        description="성장실 워커 봇 Token",
        example="123456789:ABCdefGHIjklMNOpqrSTUVwxyz012345678",
        validator=_is_bot_token,
    ),
    EnvSpec(
        key="RESEARCH_BOT_TOKEN",
        severity=Severity.OPTIONAL,
        description="리서치실 워커 봇 Token",
        example="123456789:ABCdefGHIjklMNOpqrSTUVwxyz012345678",
        validator=_is_bot_token,
    ),
    EnvSpec(
        key="OPS_BOT_TOKEN",
        severity=Severity.OPTIONAL,
        description="운영실 워커 봇 Token",
        example="123456789:ABCdefGHIjklMNOpqrSTUVwxyz012345678",
        validator=_is_bot_token,
    ),
    # ── Telegram Chat ID ────────────────────────────────────────────────────
    EnvSpec(
        key="GROUP_CHAT_ID",
        severity=Severity.REQUIRED,
        description="봇들이 활동할 Telegram 그룹 채팅 ID (음수 정수)",
        example="-1001234567890",
        validator=lambda v: v.strip().lstrip("-").isdigit(),
    ),
    # ── 엔진 경로 (최소 1개 필수) ────────────────────────────────────────────
    EnvSpec(
        key="CLAUDE_PATH",
        severity=Severity.RECOMMENDED,
        description="claude-code CLI 절대 경로",
        example="/usr/local/bin/claude",
        validator=lambda v: Path(v.strip()).exists() if v.strip() else True,
    ),
    EnvSpec(
        key="CODEX_PATH",
        severity=Severity.OPTIONAL,
        description="codex CLI 절대 경로",
        example="/usr/local/bin/codex",
        validator=lambda v: Path(v.strip()).exists() if v.strip() else True,
    ),
    EnvSpec(
        key="GEMINI_CLI_PATH",
        severity=Severity.OPTIONAL,
        description="gemini CLI 절대 경로",
        example="/opt/homebrew/bin/gemini",
        validator=lambda v: Path(v.strip()).exists() if v.strip() else True,
    ),
    # ── 기능 플래그 ─────────────────────────────────────────────────────────
    EnvSpec(
        key="ENABLE_PM_ORCHESTRATOR",
        severity=Severity.OPTIONAL,
        description="PM 오케스트레이터 활성화 (1=활성, 0=비활성)",
        example="1",
        validator=lambda v: v.strip() in ("0", "1"),
    ),
    EnvSpec(
        key="ENABLE_GOAL_TRACKER",
        severity=Severity.OPTIONAL,
        description="GoalTracker 활성화 (1=활성, 0=비활성)",
        example="1",
        validator=lambda v: v.strip() in ("0", "1"),
    ),
]


# ─── 핵심 검증 함수 ───────────────────────────────────────────────────────────

def validate_env(
    specs: Optional[list[EnvSpec]] = None,
    strict: bool = False,
    load_dotenv: bool = True,
) -> ValidationReport:
    """환경변수 검증을 실행하고 ValidationReport를 반환한다.

    Args:
        specs:       검증할 EnvSpec 목록. None이면 ENV_SPECS 전체 사용.
        strict:      True면 RECOMMENDED 누락도 EnvValidationError로 처리.
        load_dotenv: True면 .env 파일을 자동 로드 (python-dotenv 사용).

    Returns:
        ValidationReport — ok 프로퍼티로 통과 여부 확인 가능.

    Raises:
        EnvValidationError: REQUIRED 누락 또는 값 오류 (strict=True면 RECOMMENDED도).
    """
    if load_dotenv:
        try:
            from dotenv import load_dotenv as _load  # type: ignore[import]
            _load(override=False)
        except ImportError:
            pass  # python-dotenv 미설치 환경에서도 동작

    specs = specs or ENV_SPECS
    report = ValidationReport()

    for spec in specs:
        value = os.environ.get(spec.key)

        if value is None or value.strip() == "":
            # 누락
            if spec.severity == Severity.REQUIRED:
                report.missing_required.append(spec.key)
            elif spec.severity == Severity.RECOMMENDED:
                report.missing_recommended.append(spec.key)
            else:
                report.missing_optional.append(spec.key)
            continue

        # 값 존재 → validator 실행
        report.present.append(spec.key)
        if spec.validator is not None:
            try:
                valid = bool(spec.validator(value))  # type: ignore[operator]
            except Exception:
                valid = False
            if not valid:
                report.invalid_values.append((spec.key, f"값 형식 오류: '{value[:30]}'"))

    # 엔진 경로 최소 1개 검사
    engine_keys = {"CLAUDE_PATH", "CODEX_PATH", "GEMINI_CLI_PATH"}
    engine_present = [k for k in engine_keys if os.environ.get(k, "").strip()]
    if not engine_present:
        report.missing_required.append(
            "CLAUDE_PATH|CODEX_PATH|GEMINI_CLI_PATH (최소 1개 필수)"
        )

    # 오류 처리
    if not report.ok:
        msg = (
            "환경변수 검증 실패\n"
            f"  누락(REQUIRED): {report.missing_required}\n"
            f"  값 오류:        {report.invalid_values}"
        )
        raise EnvValidationError(msg)

    if strict and not report.strict_ok:
        msg = (
            "환경변수 검증 실패 (strict 모드)\n"
            f"  누락(RECOMMENDED): {report.missing_recommended}"
        )
        raise EnvValidationError(msg)

    return report


# ─── CLI 진입점 ───────────────────────────────────────────────────────────────

def _print_report(report: ValidationReport, strict: bool) -> None:
    """검증 결과를 사람이 읽기 좋은 형식으로 출력한다."""
    width = 65
    print(f"\n{'=' * width}")
    print("  telegram-ai-org — 환경변수 검증 결과")
    print(f"{'=' * width}")

    if report.present:
        print(f"\n[OK] 설정된 변수 ({len(report.present)}개):")
        for k in report.present:
            print(f"     {k}")

    if report.missing_required:
        print(f"\n[ERROR] 필수 변수 누락 ({len(report.missing_required)}개):")
        for k in report.missing_required:
            print(f"     {k}")

    if report.invalid_values:
        print(f"\n[ERROR] 값 형식 오류 ({len(report.invalid_values)}개):")
        for k, reason in report.invalid_values:
            print(f"     {k}: {reason}")

    if report.missing_recommended:
        level = "[ERROR]" if strict else "[WARN] "
        print(f"\n{level} 권장 변수 누락 ({len(report.missing_recommended)}개):")
        for k in report.missing_recommended:
            print(f"     {k}")

    if report.missing_optional:
        print(f"\n[INFO]  선택 변수 미설정 ({len(report.missing_optional)}개):")
        for k in report.missing_optional:
            print(f"     {k}")

    print(f"\n{'─' * width}")
    overall = "PASS" if (report.strict_ok if strict else report.ok) else "FAIL"
    print(f"  결과: {overall}")
    print(f"{'=' * width}\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="telegram-ai-org 환경변수 검증",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="권장(RECOMMENDED) 변수 누락도 오류로 처리 (exit 1)",
    )
    parser.add_argument(
        "--no-dotenv",
        action="store_true",
        help=".env 파일 자동 로드 비활성화",
    )
    args = parser.parse_args()

    try:
        report = validate_env(strict=args.strict, load_dotenv=not args.no_dotenv)
        _print_report(report, strict=args.strict)
        sys.exit(0)
    except EnvValidationError as exc:
        # report가 있으면 출력하고 종료
        print(f"\n[FAIL] {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
