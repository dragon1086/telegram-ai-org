#!/usr/bin/env python3
"""error-gotcha 스킬 실행 래퍼.

사용 예시:
    python tools/run_error_gotcha.py \\
        --skill engineering-review \\
        --error "NameError: name 'x' is not defined" \\
        --file "core/foo.py" \\
        --cause "변수 초기화 누락" \\
        --fix "변수 선언 추가"

동작:
    1. skills/{target_skill}/gotchas.md 읽기
    2. 기존 Gotcha 번호 확인 (## Gotcha N: 패턴)
    3. 새 항목 추가
    4. 파일 저장
    5. 요약 출력
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가 (직접 실행 시 상대 import 지원)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# 핵심 로직 함수 (단위 테스트 가능하도록 분리)
# ---------------------------------------------------------------------------


def get_gotchas_path(skills_root: Path, skill_name: str) -> Path:
    """skill_name에 해당하는 gotchas.md 경로를 반환합니다."""
    return skills_root / skill_name / "gotchas.md"


def parse_next_gotcha_number(content: str) -> int:
    """기존 gotchas.md 내용에서 다음 Gotcha 번호를 결정합니다.

    ## Gotcha N: ... 패턴을 찾아 최대 N + 1 을 반환합니다.
    항목이 없으면 1을 반환합니다.
    """
    matches = re.findall(r"^## Gotcha (\d+):", content, re.MULTILINE)
    if not matches:
        return 1
    return max(int(m) for m in matches) + 1


def build_gotcha_entry(
    number: int,
    error: str,
    file: str,
    cause: str,
    fix: str,
) -> str:
    """새 Gotcha 항목 마크다운 텍스트를 생성합니다."""
    lines = [
        f"\n## Gotcha {number}: {error}",
        "",
        f"- **파일**: `{file}`" if file else "",
        f"- **에러**: `{error}`",
        f"- **원인**: {cause}",
        f"- **해결**: {fix}",
        "",
    ]
    return "\n".join(line for line in lines)


def append_gotcha(
    gotchas_path: Path,
    error: str,
    file: str,
    cause: str,
    fix: str,
) -> tuple[int, str]:
    """gotchas.md에 새 항목을 추가하고 (새 번호, 경로) 튜플을 반환합니다.

    파일이 없으면 헤더와 함께 새로 생성합니다.

    Returns:
        (gotcha_number, str(gotchas_path))
    """
    if gotchas_path.exists():
        existing = gotchas_path.read_text(encoding="utf-8")
    else:
        skill_name = gotchas_path.parent.name
        existing = f"# {skill_name.replace('-', ' ').title()} — Gotchas\n"

    number = parse_next_gotcha_number(existing)
    entry = build_gotcha_entry(number, error, file, cause, fix)

    # 파일 끝에 개행이 없으면 추가
    updated = existing.rstrip("\n") + "\n" + entry
    gotchas_path.write_text(updated, encoding="utf-8")
    return number, str(gotchas_path)


# ---------------------------------------------------------------------------
# CLI 진입점
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="error-gotcha 스킬 실행 래퍼 — gotchas.md에 새 항목을 추가합니다.",
    )
    parser.add_argument(
        "--skill",
        required=True,
        help="대상 스킬 디렉토리 이름 (예: engineering-review)",
    )
    parser.add_argument(
        "--error",
        required=True,
        help="에러 메시지 (예: NameError: name 'x' is not defined)",
    )
    parser.add_argument(
        "--file",
        default="",
        help="에러가 발생한 파일 경로 (선택)",
    )
    parser.add_argument(
        "--cause",
        required=True,
        help="에러 원인 설명",
    )
    parser.add_argument(
        "--fix",
        required=True,
        help="해결 방법 설명",
    )
    parser.add_argument(
        "--skills-root",
        default=str(_PROJECT_ROOT / "skills"),
        help="스킬 루트 경로 (기본: <project_root>/skills)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    skills_root = Path(args.skills_root)
    gotchas_path = get_gotchas_path(skills_root, args.skill)

    if not gotchas_path.parent.exists():
        print(f"[error-gotcha] 스킬 디렉토리를 찾을 수 없습니다: {gotchas_path.parent}", file=sys.stderr)
        return 1

    number, saved_path = append_gotcha(
        gotchas_path=gotchas_path,
        error=args.error,
        file=args.file,
        cause=args.cause,
        fix=args.fix,
    )

    print(f"[error-gotcha] ✓ Gotcha {number} 추가 완료")
    print(f"  스킬  : {args.skill}")
    print(f"  에러  : {args.error}")
    if args.file:
        print(f"  파일  : {args.file}")
    print(f"  원인  : {args.cause}")
    print(f"  해결  : {args.fix}")
    print(f"  저장  : {saved_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
