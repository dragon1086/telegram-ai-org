"""core.dashboard — 실시간 작업 시각화 대시보드 핵심 로직 (Phase 1).

모듈 구성:
    models.py    — TicketStatus 데이터 모델
    aggregator.py — 시간대별 집계 로직
    adapter.py   — 데이터 소스 어댑터 (YAML/DB 폴링)
"""
from core.dashboard.models import TicketStatus, TicketState
from core.dashboard.aggregator import aggregate_by_period, AggregationResult
from core.dashboard.adapter import DataSourceAdapter

__all__ = [
    "TicketStatus",
    "TicketState",
    "aggregate_by_period",
    "AggregationResult",
    "DataSourceAdapter",
]
