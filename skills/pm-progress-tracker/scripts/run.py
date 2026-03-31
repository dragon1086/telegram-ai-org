#!/usr/bin/env python3
"""pm-progress-tracker 스킬 실행 스크립트.

PM 목표 진척 현황을 조회하고 이터레이션 루프를 관리합니다.

사용법:
  python skills/pm-progress-tracker/scripts/run.py [명령] [인자]

명령:
  status            현재 목표 및 진척률 출력 (기본값)
  list              모든 목표 목록 출력
  start <목표명>    새 목표 등록
  done <목표명>     목표를 DONE 처리
  report            진척 보고서 생성

예시:
  python skills/pm-progress-tracker/scripts/run.py status
  python skills/pm-progress-tracker/scripts/run.py start "오픈소스화 패키징"
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

# 메모리 파일 경로: 프로젝트 루트 → Claude 메모리 경로 순으로 폴백
def _resolve_memory_file(filename: str) -> Path:
    """메모리 파일 경로를 결정합니다.

    우선순위:
    1. PROJECT_ROOT/memory/<filename>
    2. ~/.claude/projects/<project_slug>/memory/<filename>
    3. ~/.ai-org/memory/<filename>
    """
    # 1. 프로젝트 루트
    local = PROJECT_ROOT / "memory" / filename
    if local.exists():
        return local

    # 2. Claude 프로젝트 메모리 (~/.claude/projects/<slug>/memory/) — glob으로 탐색
    claude_base = Path.home() / ".claude" / "projects"
    if claude_base.exists():
        for candidate in claude_base.glob(f"*/memory/{filename}"):
            return candidate

    # 3. ~/.ai-org/memory/
    aiorg_mem = Path.home() / ".ai-org" / "memory" / filename
    if aiorg_mem.exists():
        return aiorg_mem

    # 없으면 프로젝트 루트 경로 반환 (쓰기 시 생성)
    return local


GUIDE_FILE = _resolve_memory_file("pm_progress_guide.md")
TASKS_FILE = _resolve_memory_file("project_pending_tasks.md")


def _load_guide() -> str:
    """pm_progress_guide.md 내용을 반환합니다."""
    path = _resolve_memory_file("pm_progress_guide.md")
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _load_tasks() -> str:
    """project_pending_tasks.md 내용을 반환합니다."""
    path = _resolve_memory_file("project_pending_tasks.md")
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def cmd_status() -> None:
    """현재 진척 현황 출력."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    print(f"=== PM Progress Tracker 현황 ({now}) ===\n")

    guide = _load_guide()
    tasks = _load_tasks()

    if not guide and not tasks:
        print("⚠️  memory/pm_progress_guide.md 또는 project_pending_tasks.md 파일이 없습니다.")
        print("   'start <목표명>' 명령으로 새 목표를 등록하세요.")
        return

    if guide:
        print("## 목표 현황 (pm_progress_guide.md)")
        # IN_PROGRESS 항목 추출
        in_progress = [line for line in guide.splitlines() if "IN_PROGRESS" in line or "GOAL-" in line]
        if in_progress:
            for line in in_progress[:10]:
                print(f"  {line.strip()}")
        else:
            print("  (등록된 진행 중 목표 없음)")
        print()

    if tasks:
        print("## 태스크 진척 (project_pending_tasks.md)")
        # pending/in_progress 행 추출
        active = [line for line in tasks.splitlines()
                  if ("pending" in line.lower() or "in_progress" in line.lower())
                  and "|" in line]
        if active:
            print(f"  활성 태스크: {len(active)}개")
            for line in active[:5]:
                print(f"  {line.strip()}")
            if len(active) > 5:
                print(f"  ... 외 {len(active) - 5}개")
        else:
            print("  (활성 태스크 없음)")


def cmd_list() -> None:
    """모든 목표 목록 출력."""
    guide = _load_guide()
    if not guide:
        print("⚠️  pm_progress_guide.md 없음. 목표가 등록되지 않았습니다.")
        return

    print("=== 전체 목표 목록 ===\n")
    goal_lines = [line for line in guide.splitlines() if line.strip().startswith("| GOAL-")]
    if goal_lines:
        print("| ID | 목표명 | 상태 |")
        print("|-----|--------|------|")
        for line in goal_lines:
            print(line)
    else:
        print("(등록된 목표 없음)")


def cmd_start(goal_name: str) -> None:
    """새 목표 등록."""
    GUIDE_FILE.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC).strftime("%Y-%m-%d")

    # 기존 파일에서 마지막 GOAL 번호 파악
    guide = _load_guide()
    goal_nums = []
    for line in guide.splitlines():
        if "| GOAL-" in line:
            try:
                num = int(line.split("GOAL-")[1].split("|")[0].strip())
                goal_nums.append(num)
            except (ValueError, IndexError):
                pass
    next_num = max(goal_nums, default=0) + 1
    goal_id = f"GOAL-{next_num:03d}"

    entry = f"\n| {goal_id} | {goal_name} | IN_PROGRESS | {now} | - | - | - |\n"

    if not GUIDE_FILE.exists():
        GUIDE_FILE.write_text(
            "# PM Progress Guide\n\n"
            "## 목표 테이블\n\n"
            "| ID | 목표명 | 상태 | 시작일 | 완료일 | 담당 | 완료조건 |\n"
            "|-----|--------|------|--------|--------|------|----------|\n"
            + entry,
            encoding="utf-8",
        )
    else:
        with GUIDE_FILE.open("a", encoding="utf-8") as f:
            f.write(entry)

    print(f"✅ 목표 등록 완료: {goal_id} — {goal_name}")
    print(f"   상태: IN_PROGRESS | 시작일: {now}")
    print(f"   파일: {GUIDE_FILE}")


def cmd_done(goal_name: str) -> None:
    """목표를 DONE 처리."""
    if not GUIDE_FILE.exists():
        print("⚠️  pm_progress_guide.md 없음.")
        return

    now = datetime.now(UTC).strftime("%Y-%m-%d")
    content = GUIDE_FILE.read_text(encoding="utf-8")
    updated = content.replace(
        f"| {goal_name} | IN_PROGRESS |",
        f"| {goal_name} | DONE |",
    )
    if updated == content:
        print(f"⚠️  '{goal_name}' 목표를 IN_PROGRESS 상태에서 찾을 수 없습니다.")
        return

    GUIDE_FILE.write_text(updated, encoding="utf-8")
    print(f"✅ 목표 완료 처리: {goal_name} → DONE ({now})")


def cmd_report() -> None:
    """진척 보고서 생성."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    print(f"# PM 진척 보고서\n생성: {now}\n")

    guide = _load_guide()
    tasks = _load_tasks()

    total = done = in_progress = blocked = 0
    for line in (guide + tasks).splitlines():
        if "| GOAL-" in line or ("pending" in line.lower() and "|" in line):
            total += 1
        if "DONE" in line:
            done += 1
        if "IN_PROGRESS" in line or "in_progress" in line:
            in_progress += 1
        if "BLOCKED" in line:
            blocked += 1

    pct = int(done / total * 100) if total > 0 else 0
    print("## 요약")
    print(f"- 전체: {total}개")
    print(f"- 완료: {done}개 ({pct}%)")
    print(f"- 진행 중: {in_progress}개")
    print(f"- 블로킹: {blocked}개")
    print()
    print("## 세부 현황")
    cmd_status()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="PM Progress Tracker — 목표 진척 관리 스킬 실행기"
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="status",
        choices=["status", "list", "start", "done", "report"],
        help="실행할 명령 (기본: status)",
    )
    parser.add_argument("args", nargs="*", help="명령 인자 (예: 목표명)")
    args = parser.parse_args()

    commands = {
        "status": cmd_status,
        "list": cmd_list,
        "report": cmd_report,
    }

    if args.command in commands:
        commands[args.command]()
    elif args.command == "start":
        if not args.args:
            print("❌ 목표명을 입력하세요. 예: run.py start '오픈소스화 패키징'")
            sys.exit(1)
        cmd_start(" ".join(args.args))
    elif args.command == "done":
        if not args.args:
            print("❌ 목표명을 입력하세요. 예: run.py done '오픈소스화 패키징'")
            sys.exit(1)
        cmd_done(" ".join(args.args))


if __name__ == "__main__":
    main()
