#!/usr/bin/env python3
"""error-gotcha 스킬 실행 스크립트.

에러 수정 후 관련 스킬의 gotchas.md에 재발 방지 항목을 자동 추가합니다.

사용법:
  python skills/error-gotcha/scripts/run.py [--skill SKILL] [--error ERROR_TYPE]
                                              [--file FILE] [--cause CAUSE]
                                              [--fix FIX] [--title TITLE]

예시:
  python skills/error-gotcha/scripts/run.py \\
    --skill quality-gate \\
    --error NameError \\
    --file core/dispatch.py \\
    --cause "변수 선언 전 사용" \\
    --fix "함수 상단에 변수 선언 추가" \\
    --title "변수 선언 순서 오류"

  python skills/error-gotcha/scripts/run.py --list  # 기존 gotcha 목록 출력
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SKILLS_DIR = PROJECT_ROOT / "skills"

# 에러 범주 → 대상 스킬 매핑 (SKILL.md Step 2 기준)
ERROR_TO_SKILL: dict[str, str] = {
    "NameError": "engineering-review",
    "ImportError": "engineering-review",
    "ModuleNotFoundError": "engineering-review",
    "UnboundLocalError": "engineering-review",
    "AttributeError": "engineering-review",
    "TypeError": "engineering-review",
    "AssertionError": "quality-gate",
    "pytest": "quality-gate",
    "test": "quality-gate",
    "deploy": "pm-task-dispatch",
    "restart": "pm-task-dispatch",
    "dispatch": "pm-task-dispatch",
    "routing": "pm-task-dispatch",
    "performance": "engineering-review",
    "blocking": "engineering-review",
    "timeout": "engineering-review",
}


def _get_target_skill(error_type: str, skill_override: str | None) -> str:
    """에러 유형으로 대상 스킬을 결정합니다."""
    if skill_override:
        return skill_override
    error_lower = error_type.lower()
    for key, skill in ERROR_TO_SKILL.items():
        if key.lower() in error_lower:
            return skill
    return "engineering-review"  # 기본값


def _get_next_gotcha_num(gotchas_path: Path) -> int:
    """gotchas.md에서 다음 Gotcha 번호를 반환합니다."""
    if not gotchas_path.exists():
        return 1
    content = gotchas_path.read_text(encoding="utf-8")
    nums = []
    for line in content.splitlines():
        if line.startswith("## Gotcha "):
            try:
                num = int(line.split("## Gotcha ")[1].split(":")[0].strip())
                nums.append(num)
            except (ValueError, IndexError):
                pass
    return max(nums, default=0) + 1


def cmd_add(
    error_type: str,
    file_path: str,
    cause: str,
    fix: str,
    title: str,
    skill_override: str | None,
) -> None:
    """gotchas.md에 새 Gotcha 항목을 추가합니다."""
    target_skill = _get_target_skill(error_type, skill_override)
    gotchas_path = SKILLS_DIR / target_skill / "gotchas.md"

    if not (SKILLS_DIR / target_skill).exists():
        print(f"❌ 스킬 디렉토리 없음: {SKILLS_DIR / target_skill}")
        print(f"   사용 가능한 스킬: {[d.name for d in SKILLS_DIR.iterdir() if d.is_dir() and not d.name.startswith('_')]}")
        sys.exit(1)

    num = _get_next_gotcha_num(gotchas_path)
    now = datetime.now(UTC).strftime("%Y-%m-%d")

    entry = f"""
## Gotcha {num}: {title}
**날짜**: {now}
**에러 유형**: `{error_type}`
**발생 파일**: `{file_path}`
**상황**: {error_type} 오류 발생 시
**증상**: `{error_type}` — {cause}
**해결**: {fix}
"""

    if gotchas_path.exists():
        with gotchas_path.open("a", encoding="utf-8") as f:
            f.write(entry)
    else:
        gotchas_path.write_text(
            f"# {target_skill} Gotchas\n\n재발 방지 항목 목록.\n" + entry,
            encoding="utf-8",
        )

    print(f"✅ Gotcha {num} 추가 완료")
    print(f"   대상 스킬: {target_skill}")
    print(f"   파일: {gotchas_path}")
    print(f"   제목: {title}")


def cmd_list(skill: str | None) -> None:
    """기존 Gotcha 목록을 출력합니다."""
    if skill:
        skills = [skill]
    else:
        skills = [d.name for d in SKILLS_DIR.iterdir()
                  if d.is_dir() and not d.name.startswith("_")]

    found_any = False
    for skill_name in sorted(skills):
        gotchas_path = SKILLS_DIR / skill_name / "gotchas.md"
        if gotchas_path.exists():
            content = gotchas_path.read_text(encoding="utf-8")
            entries = [l for l in content.splitlines() if l.startswith("## Gotcha ")]
            if entries:
                found_any = True
                print(f"\n### {skill_name} ({len(entries)}개)")
                for e in entries:
                    print(f"  {e}")

    if not found_any:
        print("(등록된 Gotcha 없음)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Error Gotcha — 에러 재발 방지 항목 자동 추가 스킬 실행기"
    )
    subparsers = parser.add_subparsers(dest="command")

    # add 명령
    add_parser = subparsers.add_parser("add", help="새 Gotcha 추가")
    add_parser.add_argument("--skill", "-s", help="대상 스킬 이름 (미지정 시 에러 유형으로 자동 매핑)")
    add_parser.add_argument("--error", "-e", required=True, help="에러 유형 (예: NameError)")
    add_parser.add_argument("--file", "-f", default="unknown", help="에러 발생 파일 경로")
    add_parser.add_argument("--cause", "-c", required=True, help="근본 원인 (1줄)")
    add_parser.add_argument("--fix", "-x", required=True, help="수정 내용 (1줄)")
    add_parser.add_argument("--title", "-t", help="Gotcha 제목 (미지정 시 에러+원인으로 자동 생성)")

    # list 명령
    list_parser = subparsers.add_parser("list", help="기존 Gotcha 목록 출력")
    list_parser.add_argument("--skill", "-s", help="특정 스킬만 출력")

    # 인자 없으면 list
    if len(sys.argv) == 1:
        cmd_list(None)
        return

    args = parser.parse_args()

    if args.command == "add":
        title = args.title or f"{args.error}: {args.cause[:40]}"
        cmd_add(
            error_type=args.error,
            file_path=args.file,
            cause=args.cause,
            fix=args.fix,
            title=title,
            skill_override=args.skill,
        )
    elif args.command == "list":
        cmd_list(getattr(args, "skill", None))
    else:
        # 기본: list
        cmd_list(None)


if __name__ == "__main__":
    main()
