"""core.dashboard.aggregator — 시간대별 완료 작업 집계 로직 (Phase 1).

집계 함수:
    aggregate_by_period(tickets, period_hours) → AggregationResult
    compute_throughput(tickets, window_hours)  → float (tickets/hr)

지원 시간대:
    - 1h  : 최근 1시간
    - 6h  : 최근 6시간
    - 24h : 최근 24시간
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Sequence

from core.dashboard.models import TicketStatus, TicketState


# ---------------------------------------------------------------------------
# 집계 결과 데이터클래스
# ---------------------------------------------------------------------------


@dataclass
class AggregationResult:
    """시간대별 집계 결과.

    Attributes:
        period_hours:  집계 기간 (시간)
        completed:     완료된 티켓 수
        throughput:    처리 속도 (tickets/hr)
        avg_duration:  평균 처리 시간 (초, 없으면 None)
        window_start:  집계 시작 시각 (epoch)
        window_end:    집계 종료 시각 (epoch)
    """

    period_hours: float
    completed: int = 0
    throughput: float = 0.0
    avg_duration: float | None = None
    window_start: float = field(default_factory=time.time)
    window_end: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "period_hours": self.period_hours,
            "completed": self.completed,
            "throughput": round(self.throughput, 3),
            "avg_duration_seconds": round(self.avg_duration, 1) if self.avg_duration else None,
            "window_start": self.window_start,
            "window_end": self.window_end,
        }


# ---------------------------------------------------------------------------
# 핵심 집계 함수
# ---------------------------------------------------------------------------


def aggregate_by_period(
    tickets: Sequence[TicketStatus],
    period_hours: float,
    reference_time: float | None = None,
) -> AggregationResult:
    """시간대별 완료 작업 집계.

    Args:
        tickets:        전체 티켓 목록
        period_hours:   집계 기간 (시간). 예: 1, 6, 24
        reference_time: 기준 시각 (epoch). None이면 현재 시각 사용.

    Returns:
        AggregationResult — 해당 기간의 완료 건수·처리 속도

    Example::

        result = aggregate_by_period(tickets, period_hours=1)
        print(f"지난 1시간 완료: {result.completed}건 / {result.throughput:.2f} tickets/hr")
    """
    if period_hours <= 0:
        raise ValueError(f"period_hours는 0보다 커야 합니다. 입력: {period_hours}")

    now = reference_time if reference_time is not None else time.time()
    window_start = now - period_hours * 3600.0
    window_end = now

    # 기간 내 완료된 티켓 필터링 (completed_at 기준)
    completed_tickets = [
        t for t in tickets
        if t.state == TicketState.DONE
        and t.completed_at is not None
        and window_start <= t.completed_at <= window_end
    ]

    completed_count = len(completed_tickets)
    throughput = completed_count / period_hours  # tickets/hr

    # 평균 처리 시간 계산
    durations = [t.duration_seconds for t in completed_tickets if t.duration_seconds is not None]
    avg_duration = sum(durations) / len(durations) if durations else None

    return AggregationResult(
        period_hours=period_hours,
        completed=completed_count,
        throughput=throughput,
        avg_duration=avg_duration,
        window_start=window_start,
        window_end=window_end,
    )


def compute_throughput(
    tickets: Sequence[TicketStatus],
    window_hours: float = 1.0,
    reference_time: float | None = None,
) -> float:
    """처리 속도 계산 (tickets/hr).

    Args:
        tickets:        전체 티켓 목록
        window_hours:   집계 윈도우 (시간)
        reference_time: 기준 시각 (epoch). None이면 현재 시각.

    Returns:
        float — tickets/hr (소수점 3자리 반올림)
    """
    result = aggregate_by_period(tickets, window_hours, reference_time)
    return round(result.throughput, 3)


def aggregate_all_periods(
    tickets: Sequence[TicketStatus],
    reference_time: float | None = None,
) -> dict[str, AggregationResult]:
    """1h / 6h / 24h 세 기간 모두 집계.

    Returns:
        {"1h": AggregationResult, "6h": AggregationResult, "24h": AggregationResult}
    """
    periods = {"1h": 1.0, "6h": 6.0, "24h": 24.0}
    return {
        label: aggregate_by_period(tickets, hours, reference_time)
        for label, hours in periods.items()
    }


# ---------------------------------------------------------------------------
# 상태별 카운트 헬퍼
# ---------------------------------------------------------------------------


def count_by_state(tickets: Sequence[TicketStatus]) -> dict[str, int]:
    """상태별 티켓 수 반환.

    Returns:
        {"pending": N, "in_progress": N, "done": N, "blocked": N}
    """
    counts: dict[str, int] = {state.value: 0 for state in TicketState}
    for ticket in tickets:
        counts[ticket.state.value] += 1
    return counts
