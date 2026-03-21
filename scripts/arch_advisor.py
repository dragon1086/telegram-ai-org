"""아키텍처 어드바이저 — 월간 구조 건강도 리포트 생성.

core/ 파일 크기 추세, 스킬 사용 빈도, 모듈 복잡도를 분석하여
Rocky에게 구조 개선 제안을 Telegram으로 보고한다.

실행:
    python scripts/arch_advisor.py
    python scripts/arch_advisor.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


@dataclass
class ArchReport:
    generated_at: str
    total_core_files: int
    total_core_size_kb: float
    large_files: list[dict]       # size >= WARN_KB
    unused_skills: list[str]      # 스킬 중 활용 데이터 없는 것
    module_notes: list[str]       # 구조 개선 제안
    skill_eval_coverage: dict     # skill -> eval 있음/없음

    def to_markdown(self) -> str:
        lines = [
            "# 월간 아키텍처 건강 리포트",
            f"생성: {self.generated_at}",
            "",
            "## core/ 파일 현황",
            f"- 총 파일: {self.total_core_files}개",
            f"- 총 크기: {self.total_core_size_kb:.0f}KB",
            "",
        ]
        if self.large_files:
            lines.append("### 대형 파일 (주의)")
            for f in self.large_files:
                lines.append(f"- `{f['name']}`: {f['size_kb']:.0f}KB — {f['note']}")
            lines.append("")

        if self.skill_eval_coverage:
            lines.append("## 스킬 Eval 커버리지")
            for skill, has_eval in sorted(self.skill_eval_coverage.items()):
                icon = "✅" if has_eval else "❌"
                lines.append(f"- {icon} {skill}")
            coverage_pct = (
                sum(1 for v in self.skill_eval_coverage.values() if v)
                / len(self.skill_eval_coverage) * 100
            ) if self.skill_eval_coverage else 0
            lines.append(f"\n커버리지: {coverage_pct:.0f}%")
            lines.append("")

        if self.module_notes:
            lines.append("## 구조 개선 제안")
            for note in self.module_notes:
                lines.append(f"- {note}")

        return "\n".join(lines)

    def to_telegram(self) -> str:
        lines = [
            "🏛 *월간 아키텍처 리포트*",
            f"core/ {self.total_core_files}파일 · {self.total_core_size_kb:.0f}KB",
            "",
        ]
        if self.large_files:
            lines.append("⚠️ *대형 파일:*")
            for f in self.large_files[:5]:
                lines.append(f"  • `{f['name']}` {f['size_kb']:.0f}KB")
        if self.module_notes:
            lines.append("\n💡 *제안:*")
            for note in self.module_notes[:3]:
                lines.append(f"  • {note}")
        coverage_count = sum(1 for v in self.skill_eval_coverage.values() if v)
        total_skills = len(self.skill_eval_coverage)
        if total_skills:
            lines.append(f"\n📋 스킬 eval 커버리지: {coverage_count}/{total_skills}")
        return "\n".join(lines)


WARN_KB = 80.0
CRITICAL_KB = 150.0


def scan_core_files() -> list[dict]:
    core_dir = PROJECT_ROOT / "core"
    entries = []
    for f in sorted(core_dir.glob("*.py")):
        size_kb = f.stat().st_size / 1024
        if size_kb >= WARN_KB:
            if size_kb >= CRITICAL_KB:
                note = f"분리 필요 (>{CRITICAL_KB:.0f}KB)"
            else:
                note = f"모니터링 ({WARN_KB:.0f}KB 초과)"
            entries.append({"name": f.name, "size_kb": round(size_kb, 1), "note": note})
    return entries


def scan_skill_eval_coverage() -> dict[str, bool]:
    skills_dir = PROJECT_ROOT / "skills"
    evals_dir = PROJECT_ROOT / "evals" / "skills"
    coverage = {}
    if skills_dir.exists():
        for skill_dir in sorted(skills_dir.iterdir()):
            if skill_dir.is_dir() and not skill_dir.name.startswith("_"):
                has_eval = (evals_dir / skill_dir.name / "eval.json").exists()
                coverage[skill_dir.name] = has_eval
    return coverage


def generate_module_notes(large_files: list[dict]) -> list[str]:
    notes = []
    for f in large_files:
        name = f["name"]
        size = f["size_kb"]
        if size >= CRITICAL_KB:
            if name == "pm_orchestrator.py":
                notes.append(
                    f"pm_orchestrator.py ({size:.0f}KB) — "
                    "PM 상태 머신 / 라우팅 / 대화 처리를 분리하는 것을 검토하세요."
                )
            elif name == "telegram_relay.py":
                notes.append(
                    f"telegram_relay.py ({size:.0f}KB) — "
                    "Telegram 핸들러를 메시지 유형별로 분리하는 것을 검토하세요."
                )
            else:
                notes.append(f"{name} ({size:.0f}KB) — 모듈 분리를 검토하세요.")
    return notes


def run(dry_run: bool = False) -> ArchReport:
    large_files = scan_core_files()
    skill_eval_coverage = scan_skill_eval_coverage()
    module_notes = generate_module_notes(large_files)

    core_dir = PROJECT_ROOT / "core"
    all_py = list(core_dir.glob("*.py"))
    total_size_kb = sum(f.stat().st_size for f in all_py) / 1024

    report = ArchReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        total_core_files=len(all_py),
        total_core_size_kb=round(total_size_kb, 1),
        large_files=large_files,
        unused_skills=[],
        module_notes=module_notes,
        skill_eval_coverage=skill_eval_coverage,
    )

    # 보고서 저장
    out_dir = PROJECT_ROOT / "docs" / "arch"
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m")
    report_path = out_dir / f"{date_str}-arch-report.md"

    if not dry_run:
        report_path.write_text(report.to_markdown(), encoding="utf-8")
        print(f"[ArchAdvisor] 리포트 저장: {report_path}")

    print(report.to_telegram())
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="월간 아키텍처 건강 리포트")
    parser.add_argument("--dry-run", action="store_true", help="파일 저장 없이 출력만")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
