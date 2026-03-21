"""자가개선 버스 — 신호 수집 → 우선순위 큐 → Improver 라우팅.

데이터 소스(retro_memory, lesson_memory)에서 개선 신호를 수집하고
우선순위에 따라 적절한 개선 동작을 실행한다.

사용법:
    bus = ImprovementBus()
    signals = bus.collect_signals()
    report = bus.run(signals)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from loguru import logger


class SignalKind(str, Enum):
    RETRO_INSIGHT = "retro_insight"       # 회고에서 도출된 개선 사항
    LESSON_LEARNED = "lesson_learned"     # 에러 후 학습된 패턴
    SKILL_STALE = "skill_stale"           # 스킬 오래됨 / eval 미달
    ROUTE_MISS = "route_miss"             # 라우팅 실패 패턴
    CODE_SMELL = "code_smell"             # 코드 파일 크기/복잡도 경고
    PERF_DROP = "perf_drop"              # 봇 성능 하락


@dataclass
class ImprovementSignal:
    kind: SignalKind
    priority: int           # 1(낮음) ~ 10(긴급)
    target: str             # e.g. "skill:pm-task-dispatch", "routing", "code:nl_classifier"
    evidence: dict          # 신호 근거 데이터
    suggested_action: str   # 자연어 개선 제안
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class ImprovementReport:
    collected_at: str
    signal_count: int
    signals: list[ImprovementSignal]
    actions_taken: list[str]
    skipped: list[str]


class ImprovementBus:
    """신호 수집 → 우선순위 큐 → Improver 라우팅."""

    # 반복 실패 임계값: N회 이상이면 신호 발생
    LESSON_REPEAT_THRESHOLD = 3
    # lesson_memory 조회 기간 (일)
    LESSON_LOOKBACK_DAYS = 14

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run

    # ------------------------------------------------------------------
    # 신호 수집
    # ------------------------------------------------------------------

    def collect_signals(self) -> list[ImprovementSignal]:
        """모든 소스에서 신호를 수집하고 priority 내림차순 정렬."""
        signals: list[ImprovementSignal] = []
        signals.extend(self._signals_from_lesson_memory())
        signals.extend(self._signals_from_retro_memory())
        signals.extend(self._signals_from_skill_staleness())
        signals.extend(self._signals_from_code_health())
        signals.sort(key=lambda s: s.priority, reverse=True)
        logger.info(f"[ImprovementBus] {len(signals)}개 신호 수집")
        return signals

    def _signals_from_lesson_memory(self) -> list[ImprovementSignal]:
        signals: list[ImprovementSignal] = []
        try:
            from core.lesson_memory import LessonMemory
            lm = LessonMemory()
            stats = lm.get_category_stats()
            failures = lm.get_recent_failures(days=self.LESSON_LOOKBACK_DAYS)

            # 카테고리별 반복 실패 → 라우팅/코드 개선 신호
            for category, count in stats.items():
                if count >= self.LESSON_REPEAT_THRESHOLD:
                    target = "routing" if category in ("logic_error", "context_loss") else f"code:{category}"
                    signals.append(ImprovementSignal(
                        kind=SignalKind.LESSON_LEARNED,
                        priority=min(10, count + 3),
                        target=target,
                        evidence={"category": category, "count": count},
                        suggested_action=(
                            f"'{category}' 패턴이 {count}회 반복됨. "
                            f"관련 로직/라우팅 규칙 점검 필요."
                        ),
                    ))

            # 반복 실패 패턴에서 스킬 개선 신호
            if len(failures) >= self.LESSON_REPEAT_THRESHOLD:
                signals.append(ImprovementSignal(
                    kind=SignalKind.SKILL_STALE,
                    priority=6,
                    target="skill:pm-task-dispatch",
                    evidence={"recent_failures": len(failures)},
                    suggested_action=(
                        f"최근 {self.LESSON_LOOKBACK_DAYS}일간 {len(failures)}개 실패. "
                        "pm-task-dispatch 스킬 eval 실행 권장."
                    ),
                ))
        except Exception as e:
            logger.warning(f"[ImprovementBus] lesson_memory 신호 수집 실패: {e}")
        return signals

    def _signals_from_retro_memory(self) -> list[ImprovementSignal]:
        signals: list[ImprovementSignal] = []
        try:
            from core.retro_memory import RetroMemory
            rm = RetroMemory()
            report = rm.get_report(week_offset=0)

            # 낮은 성공률 → 봇 성능 개선 신호
            if report.avg_success_rate < 0.70:
                signals.append(ImprovementSignal(
                    kind=SignalKind.PERF_DROP,
                    priority=8,
                    target="bot:all",
                    evidence={"avg_success_rate": report.avg_success_rate},
                    suggested_action=(
                        f"주간 성공률 {report.avg_success_rate:.0%} — 70% 미만. "
                        "performance-eval 스킬 실행 권장."
                    ),
                ))

            # 반복 교훈 → 스킬 업데이트 신호
            if report.top_lessons:
                signals.append(ImprovementSignal(
                    kind=SignalKind.RETRO_INSIGHT,
                    priority=5,
                    target="skill:all",
                    evidence={"lessons": report.top_lessons[:3]},
                    suggested_action=(
                        "회고 반복 패턴: " + "; ".join(report.top_lessons[:3])
                    ),
                ))
        except Exception as e:
            logger.warning(f"[ImprovementBus] retro_memory 신호 수집 실패: {e}")
        return signals

    def _signals_from_skill_staleness(self) -> list[ImprovementSignal]:
        """eval.json이 있는 스킬 중 baseline이 낮은 스킬 감지."""
        signals: list[ImprovementSignal] = []
        try:
            evals_dir = Path(__file__).parent.parent / "evals" / "skills"
            if not evals_dir.exists():
                return signals

            import json
            for skill_eval in evals_dir.glob("*/eval.json"):
                skill_name = skill_eval.parent.name
                data = json.loads(skill_eval.read_text())
                baseline = data.get("baseline", 10.0)
                if baseline < 7.0:
                    signals.append(ImprovementSignal(
                        kind=SignalKind.SKILL_STALE,
                        priority=7,
                        target=f"skill:{skill_name}",
                        evidence={"baseline": baseline, "skill": skill_name},
                        suggested_action=(
                            f"{skill_name} 스킬 eval baseline={baseline:.1f}/10. "
                            "자동 개선 루프 실행 권장."
                        ),
                    ))
        except Exception as e:
            logger.warning(f"[ImprovementBus] skill staleness 신호 수집 실패: {e}")
        return signals

    def _signals_from_code_health(self) -> list[ImprovementSignal]:
        """core/ 파일 크기 경고 신호."""
        signals: list[ImprovementSignal] = []
        try:
            core_dir = Path(__file__).parent
            WARN_KB = 80
            CRITICAL_KB = 150
            for py_file in core_dir.glob("*.py"):
                size_kb = py_file.stat().st_size / 1024
                if size_kb >= CRITICAL_KB:
                    signals.append(ImprovementSignal(
                        kind=SignalKind.CODE_SMELL,
                        priority=6,
                        target=f"code:{py_file.name}",
                        evidence={"file": py_file.name, "size_kb": round(size_kb, 1)},
                        suggested_action=(
                            f"{py_file.name} ({size_kb:.0f}KB) — 분리 또는 리팩토링 권장."
                        ),
                    ))
                elif size_kb >= WARN_KB:
                    signals.append(ImprovementSignal(
                        kind=SignalKind.CODE_SMELL,
                        priority=3,
                        target=f"code:{py_file.name}",
                        evidence={"file": py_file.name, "size_kb": round(size_kb, 1)},
                        suggested_action=(
                            f"{py_file.name} ({size_kb:.0f}KB) — 성장 추세 모니터링 권장."
                        ),
                    ))
        except Exception as e:
            logger.warning(f"[ImprovementBus] code health 신호 수집 실패: {e}")
        return signals

    # ------------------------------------------------------------------
    # 실행
    # ------------------------------------------------------------------

    def run(self, signals: list[ImprovementSignal] | None = None) -> ImprovementReport:
        """신호 수집 → 로그 기록 → 보고서 반환."""
        if signals is None:
            signals = self.collect_signals()

        actions_taken: list[str] = []
        skipped: list[str] = []

        for signal in signals:
            try:
                action = self._dispatch(signal)
                if action:
                    actions_taken.append(action)
                else:
                    skipped.append(f"{signal.kind.value}:{signal.target}")
            except Exception as e:
                logger.error(f"[ImprovementBus] dispatch 실패 {signal.target}: {e}")
                skipped.append(signal.target)

        report = ImprovementReport(
            collected_at=datetime.now(timezone.utc).isoformat(),
            signal_count=len(signals),
            signals=signals,
            actions_taken=actions_taken,
            skipped=skipped,
        )
        self._log_report(report)
        return report

    def _dispatch(self, signal: ImprovementSignal) -> str | None:
        """신호 종류별 처리. dry_run이면 로그만."""
        label = f"[{signal.kind.value}] {signal.target} (priority={signal.priority})"
        logger.info(f"[ImprovementBus] {label}: {signal.suggested_action}")

        if self.dry_run:
            return f"[dry_run] {label}"

        # 실제 action: 현재는 로그 + Telegram 보고용 메시지 생성
        # Phase 3 이후 각 Improver 클래스가 여기서 호출됨
        return label

    def _log_report(self, report: ImprovementReport) -> None:
        summary_lines = [
            f"[ImprovementBus] 실행 완료 — {report.signal_count}개 신호",
            f"  처리: {len(report.actions_taken)}개",
            f"  스킵: {len(report.skipped)}개",
        ]
        for line in summary_lines:
            logger.info(line)

    # ------------------------------------------------------------------
    # Telegram 보고용 텍스트
    # ------------------------------------------------------------------

    def format_report(self, report: ImprovementReport) -> str:
        lines = [
            "🔄 *자가개선 버스 리포트*",
            f"수집 신호: {report.signal_count}개",
            "",
        ]
        if report.signals:
            lines.append("📋 *주요 신호:*")
            for s in report.signals[:5]:
                lines.append(f"  • [{s.priority}] {s.suggested_action}")
            if len(report.signals) > 5:
                lines.append(f"  ... 외 {len(report.signals) - 5}개")
        if report.actions_taken:
            lines.append(f"\n✅ 처리 완료: {len(report.actions_taken)}개")
        if report.skipped:
            lines.append(f"⏭️ 스킵: {len(report.skipped)}개")
        return "\n".join(lines)
