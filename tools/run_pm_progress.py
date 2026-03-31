#!/usr/bin/env python3
"""pm-progress-tracker 스킬 실행 래퍼.

사용 예시:
    # 현재 IN_PROGRESS 목표 목록 출력
    python tools/run_pm_progress.py --action status

    # 새 목표 등록
    python tools/run_pm_progress.py \\
        --action register \\
        --goal "오픈소스화 패키징" \\
        --dept "개발실" \\
        --condition "setup.sh 실행 후 봇 응답 확인"

    # 목표 상태 갱신
    python tools/run_pm_progress.py --action update --goal-id GOAL-001 --status DONE

동작:
    - status : memory/pm_progress_guide.md 파싱 → IN_PROGRESS 목표 표 형식 출력
    - register: 새 목표를 pm_progress_guide.md에 추가
    - update  : 특정 목표의 현재상태 갱신
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_PM_GUIDE_PATH = _PROJECT_ROOT / "memory" / "pm_progress_guide.md"

if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# 파싱 유틸 (단위 테스트 가능하도록 분리)
# ---------------------------------------------------------------------------


def parse_goals(content: str) -> list[dict]:
    """pm_progress_guide.md 에서 목표 항목을 파싱합니다.

    각 목표 블록은 아래 패턴으로 인식합니다:
        ### GOAL-NNN: <제목>
        - 현재상태: TODO | IN_PROGRESS | DONE | BLOCKED
        - 담당부서: ...
        - 완료조건: ...
        - 시작일: YYYY-MM-DD

    Returns:
        list of dict with keys: goal_id, title, status, dept, condition, start_date
    """
    goals: list[dict] = []
    # 목표 블록 시작 매칭
    header_pattern = re.compile(r"^###\s+(GOAL-\w+):\s*(.+)$", re.MULTILINE)
    for m in header_pattern.finditer(content):
        goal_id = m.group(1).strip()
        title = m.group(2).strip()
        # 블록 범위: 다음 ### 또는 파일 끝까지
        block_start = m.end()
        next_header = header_pattern.search(content, block_start)
        block_end = next_header.start() if next_header else len(content)
        block = content[block_start:block_end]

        def _extract(field: str) -> str:
            fm = re.search(rf"^[-*]\s+{re.escape(field)}:\s*(.+)$", block, re.MULTILINE)
            return fm.group(1).strip() if fm else ""

        goals.append(
            {
                "goal_id": goal_id,
                "title": title,
                "status": _extract("현재상태"),
                "dept": _extract("담당부서"),
                "condition": _extract("완료조건"),
                "start_date": _extract("시작일"),
            }
        )
    return goals


def next_goal_id(goals: list[dict]) -> str:
    """기존 목표 목록에서 다음 GOAL-NNN ID를 생성합니다."""
    nums = []
    for g in goals:
        m = re.match(r"GOAL-(\d+)", g["goal_id"])
        if m:
            nums.append(int(m.group(1)))
    next_num = (max(nums) + 1) if nums else 1
    return f"GOAL-{next_num:03d}"


def build_goal_block(goal_id: str, title: str, dept: str, condition: str) -> str:
    """새 목표 블록 마크다운을 생성합니다."""
    today = date.today().isoformat()
    return (
        f"\n### {goal_id}: {title}\n"
        f"- 담당부서: {dept}\n"
        f"- 시작일: {today}\n"
        f"- 완료조건: {condition}\n"
        f"- 현재상태: IN_PROGRESS\n"
        f"- 이터레이션 로그:\n"
        f"  - (이터레이션 항목 여기에 추가)\n"
    )


# ---------------------------------------------------------------------------
# 액션 핸들러
# ---------------------------------------------------------------------------


def action_status(guide_path: Path) -> int:
    """IN_PROGRESS 목표 목록을 출력합니다."""
    if not guide_path.exists():
        print(f"[pm-progress] pm_progress_guide.md 파일 없음: {guide_path}", file=sys.stderr)
        return 1

    content = guide_path.read_text(encoding="utf-8")
    goals = parse_goals(content)
    in_progress = [g for g in goals if g["status"] in ("IN_PROGRESS", "TODO")]

    if not in_progress:
        print("[pm-progress] 현재 IN_PROGRESS / TODO 목표 없음")
        return 0

    col_w = [10, 30, 12, 20]
    header = (
        f"{'GOAL_ID':<{col_w[0]}}  {'제목':<{col_w[1]}}  {'상태':<{col_w[2]}}  {'담당부서':<{col_w[3]}}"
    )
    sep = "-" * (sum(col_w) + 6)
    print(header)
    print(sep)
    for g in in_progress:
        print(
            f"{g['goal_id']:<{col_w[0]}}  "
            f"{g['title'][:col_w[1]]:<{col_w[1]}}  "
            f"{g['status']:<{col_w[2]}}  "
            f"{g['dept'][:col_w[3]]:<{col_w[3]}}"
        )
    print(f"\n총 {len(in_progress)}건")
    return 0


def action_register(guide_path: Path, goal: str, dept: str, condition: str) -> int:
    """새 목표를 pm_progress_guide.md에 추가합니다."""
    if guide_path.exists():
        content = guide_path.read_text(encoding="utf-8")
    else:
        guide_path.parent.mkdir(parents=True, exist_ok=True)
        content = "# PM Progress Guide\n\n## 목표 목록\n"

    goals = parse_goals(content)
    goal_id = next_goal_id(goals)
    block = build_goal_block(goal_id, goal, dept, condition)

    updated = content.rstrip("\n") + "\n" + block
    guide_path.write_text(updated, encoding="utf-8")

    print(f"[pm-progress] ✓ {goal_id} 등록 완료")
    print(f"  제목    : {goal}")
    print(f"  담당부서: {dept}")
    print(f"  완료조건: {condition}")
    print(f"  저장    : {guide_path}")
    return 0


def action_update(guide_path: Path, goal_id: str, new_status: str) -> int:
    """특정 목표의 현재상태를 갱신합니다."""
    if not guide_path.exists():
        print(f"[pm-progress] pm_progress_guide.md 파일 없음: {guide_path}", file=sys.stderr)
        return 1

    content = guide_path.read_text(encoding="utf-8")
    goals = parse_goals(content)
    ids = [g["goal_id"] for g in goals]

    if goal_id not in ids:
        print(f"[pm-progress] {goal_id} 를 찾을 수 없습니다. 등록된 목표: {ids}", file=sys.stderr)
        return 1

    # 해당 GOAL 블록 내 현재상태 라인만 교체
    # 패턴: ### GOAL-NNN: ... (이후 블록) 내 `- 현재상태: XXX`
    header_pat = re.compile(rf"(###\s+{re.escape(goal_id)}:.*?)(\n)", re.DOTALL)
    m = header_pat.search(content)
    if not m:
        print(f"[pm-progress] {goal_id} 헤더 파싱 실패", file=sys.stderr)
        return 1

    block_start = m.start()
    suffix = content[m.end():]
    next_header_m = re.search(r"\n###\s+GOAL-", suffix)
    block_end = (m.end() + next_header_m.start()) if next_header_m else len(content)

    block = content[block_start:block_end]
    updated_block = re.sub(
        r"(^[-*]\s+현재상태:\s*).+$",
        rf"\g<1>{new_status}",
        block,
        flags=re.MULTILINE,
    )
    updated_content = content[:block_start] + updated_block + content[block_end:]
    guide_path.write_text(updated_content, encoding="utf-8")

    print(f"[pm-progress] ✓ {goal_id} 상태 변경 → {new_status}")
    print(f"  저장: {guide_path}")
    return 0


# ---------------------------------------------------------------------------
# CLI 진입점
# ---------------------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="pm-progress-tracker 스킬 실행 래퍼",
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["status", "register", "update"],
        help="실행할 액션",
    )
    parser.add_argument("--goal", default="", help="목표명 (register 시 필수)")
    parser.add_argument("--dept", default="", help="담당부서 (register 시 필수)")
    parser.add_argument("--condition", default="", help="완료조건 (register 시 필수)")
    parser.add_argument("--goal-id", default="", dest="goal_id", help="목표 ID (update 시 필수)")
    parser.add_argument("--status", default="", help="변경할 상태 (update 시 필수)")
    parser.add_argument(
        "--guide-path",
        default=str(_PM_GUIDE_PATH),
        help="pm_progress_guide.md 경로 (기본값: memory/pm_progress_guide.md)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    guide_path = Path(args.guide_path)

    if args.action == "status":
        return action_status(guide_path)

    if args.action == "register":
        if not args.goal or not args.dept or not args.condition:
            print("[pm-progress] register 액션에는 --goal, --dept, --condition 이 필요합니다.", file=sys.stderr)
            return 1
        return action_register(guide_path, args.goal, args.dept, args.condition)

    if args.action == "update":
        if not args.goal_id or not args.status:
            print("[pm-progress] update 액션에는 --goal-id, --status 가 필요합니다.", file=sys.stderr)
            return 1
        return action_update(guide_path, args.goal_id, args.status)

    return 0


if __name__ == "__main__":
    sys.exit(main())
