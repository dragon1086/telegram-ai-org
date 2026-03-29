"""core.api.metrics — 인메모리 API 요청 카운터 (Phase 3-A).

피처 플래그: ENABLE_REST_API=true 시 자동 활성화.
메트릭: 엔드포인트별 총 요청수, 상태코드별 카운트, 평균 응답 시간.
"""
from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import DefaultDict


@dataclass
class EndpointMetric:
    """단일 엔드포인트 메트릭."""

    total_requests: int = 0
    status_counts: DefaultDict[int, int] = field(default_factory=lambda: defaultdict(int))
    total_duration_ms: float = 0.0

    @property
    def avg_duration_ms(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return round(self.total_duration_ms / self.total_requests, 2)

    def record(self, status_code: int, duration_ms: float) -> None:
        self.total_requests += 1
        self.status_counts[status_code] += 1
        self.total_duration_ms += duration_ms

    def to_dict(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "status_counts": dict(self.status_counts),
            "avg_duration_ms": self.avg_duration_ms,
        }


# 전역 메트릭 저장소
_metrics: DefaultDict[str, EndpointMetric] = defaultdict(EndpointMetric)
_start_time: float = time.time()


def record_request(method: str, path: str, status_code: int, duration_ms: float) -> None:
    """요청 메트릭을 기록합니다."""
    key = f"{method} {path}"
    _metrics[key].record(status_code, duration_ms)


def get_metrics_snapshot() -> dict:
    """현재 메트릭 스냅샷을 반환합니다."""
    uptime_seconds = round(time.time() - _start_time, 1)
    total = sum(m.total_requests for m in _metrics.values())

    return {
        "uptime_seconds": uptime_seconds,
        "total_requests": total,
        "endpoints": {key: m.to_dict() for key, m in _metrics.items()},
    }


def reset_metrics() -> None:
    """테스트 격리용: 모든 메트릭을 초기화합니다."""
    global _start_time
    _metrics.clear()
    _start_time = time.time()
