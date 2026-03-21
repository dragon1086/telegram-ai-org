"""코드 건강도 모니터 — 파일 크기, 에러 빈도, 모듈 복잡도 측정.

매일 새벽 실행하여 improvement_bus로 신호를 보낸다.

사용법:
    monitor = CodeHealthMonitor()
    report = monitor.scan()
    print(report.summary())
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger


@dataclass
class FileHealthEntry:
    path: str
    size_kb: float
    status: str     # "ok" | "warn" | "critical"
    note: str = ""


@dataclass
class CodeHealthReport:
    scanned_at: str
    file_entries: list[FileHealthEntry]
    top_error_categories: list[tuple[str, int]]
    total_files: int
    warn_count: int
    critical_count: int

    def summary(self) -> str:
        lines = [
            "🏥 *코드 건강 리포트*",
            f"스캔: {self.total_files}개 파일 | ⚠️ {self.warn_count} | 🔴 {self.critical_count}",
            "",
        ]
        criticals = [e for e in self.file_entries if e.status == "critical"]
        if criticals:
            lines.append("🔴 *크리티컬 파일:*")
            for e in criticals[:5]:
                lines.append(f"  • {e.path} ({e.size_kb:.0f}KB) — {e.note}")
        if self.top_error_categories:
            lines.append("\n📋 *반복 에러 패턴:*")
            for cat, cnt in self.top_error_categories[:3]:
                lines.append(f"  • {cat}: {cnt}회")
        return "\n".join(lines)


WARN_KB = 80.0
CRITICAL_KB = 150.0


class CodeHealthMonitor:
    """core/ 디렉토리 파일 크기 + lesson_memory 에러 빈도 스캔."""

    def __init__(self, core_dir: Path | None = None) -> None:
        self._core_dir = core_dir or Path(__file__).parent

    def scan(self) -> CodeHealthReport:
        file_entries = self._scan_files()
        error_categories = self._scan_error_categories()

        warn_count = sum(1 for e in file_entries if e.status == "warn")
        critical_count = sum(1 for e in file_entries if e.status == "critical")

        report = CodeHealthReport(
            scanned_at=datetime.now(timezone.utc).isoformat(),
            file_entries=file_entries,
            top_error_categories=error_categories,
            total_files=len(file_entries),
            warn_count=warn_count,
            critical_count=critical_count,
        )
        logger.info(
            f"[CodeHealthMonitor] 스캔 완료 — {len(file_entries)}파일, "
            f"warn={warn_count}, critical={critical_count}"
        )
        return report

    def _scan_files(self) -> list[FileHealthEntry]:
        entries = []
        for py_file in sorted(self._core_dir.glob("*.py")):
            size_kb = py_file.stat().st_size / 1024
            if size_kb >= CRITICAL_KB:
                status = "critical"
                note = f"분리 권장 (>{CRITICAL_KB:.0f}KB)"
            elif size_kb >= WARN_KB:
                status = "warn"
                note = f"성장 추세 모니터링 ({WARN_KB:.0f}KB 초과)"
            else:
                status = "ok"
                note = ""
            entries.append(FileHealthEntry(
                path=f"core/{py_file.name}",
                size_kb=round(size_kb, 1),
                status=status,
                note=note,
            ))
        return entries

    def _scan_error_categories(self) -> list[tuple[str, int]]:
        """lesson_memory에서 최근 30일 에러 카테고리 빈도 반환."""
        try:
            from core.lesson_memory import LessonMemory
            lm = LessonMemory()
            stats = lm.get_category_stats()
            return sorted(stats.items(), key=lambda x: x[1], reverse=True)
        except Exception as e:
            logger.debug(f"[CodeHealthMonitor] lesson_memory 조회 실패: {e}")
            return []

    def emit_signals(self) -> list:
        """scan 결과를 ImprovementSignal 목록으로 반환."""
        from core.improvement_bus import ImprovementSignal, SignalKind
        report = self.scan()
        signals = []
        for entry in report.file_entries:
            if entry.status in ("warn", "critical"):
                priority = 6 if entry.status == "critical" else 3
                signals.append(ImprovementSignal(
                    kind=SignalKind.CODE_SMELL,
                    priority=priority,
                    target=f"code:{entry.path}",
                    evidence={"size_kb": entry.size_kb, "status": entry.status},
                    suggested_action=f"{entry.path} ({entry.size_kb:.0f}KB) — {entry.note}",
                ))
        return signals
