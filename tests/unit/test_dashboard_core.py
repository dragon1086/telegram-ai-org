"""tests/unit/test_dashboard_core.py — Phase 1 대시보드 핵심 로직 유닛 테스트.

테스트 대상:
    core/dashboard/models.py     — TicketStatus, TicketState
    core/dashboard/aggregator.py — aggregate_by_period, compute_throughput
    core/dashboard/adapter.py    — DataSourceAdapter (mock 소스)
    core/dashboard/pusher.py     — DashboardPusher
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# core.dashboard.models 테스트
# ---------------------------------------------------------------------------


class TestTicketState:
    def test_enum_values(self):
        from core.dashboard.models import TicketState

        assert TicketState.PENDING.value == "pending"
        assert TicketState.IN_PROGRESS.value == "in_progress"
        assert TicketState.DONE.value == "done"
        assert TicketState.BLOCKED.value == "blocked"

    def test_color_mapping(self):
        from core.dashboard.models import TicketState

        assert TicketState.PENDING.color == "#FFE000"
        assert TicketState.IN_PROGRESS.color == "#0057FF"
        assert TicketState.DONE.color == "#00C851"
        assert TicketState.BLOCKED.color == "#FF3B3F"

    def test_emoji_mapping(self):
        from core.dashboard.models import TicketState

        assert TicketState.PENDING.emoji == "⏳"
        assert TicketState.IN_PROGRESS.emoji == "⚡"
        assert TicketState.DONE.emoji == "✅"
        assert TicketState.BLOCKED.emoji == "🚫"


class TestTicketStatus:
    def test_default_values(self):
        from core.dashboard.models import TicketStatus, TicketState

        ticket = TicketStatus(ticket_id="T-001")
        assert ticket.ticket_id == "T-001"
        assert ticket.state == TicketState.PENDING
        assert ticket.assignee == "unassigned"
        assert ticket.started_at is None
        assert ticket.completed_at is None

    def test_string_state_coercion(self):
        from core.dashboard.models import TicketStatus, TicketState

        ticket = TicketStatus(ticket_id="T-002", state="in_progress")  # type: ignore[arg-type]
        assert ticket.state == TicketState.IN_PROGRESS

    def test_start_transition(self):
        from core.dashboard.models import TicketStatus, TicketState

        ticket = TicketStatus(ticket_id="T-003")
        before = time.time()
        ticket.start()
        after = time.time()

        assert ticket.state == TicketState.IN_PROGRESS
        assert ticket.started_at is not None
        assert before <= ticket.started_at <= after

    def test_complete_transition(self):
        from core.dashboard.models import TicketStatus, TicketState

        ticket = TicketStatus(ticket_id="T-004")
        ticket.start()
        ticket.complete()

        assert ticket.state == TicketState.DONE
        assert ticket.completed_at is not None
        assert ticket.started_at is not None

    def test_block_transition(self):
        from core.dashboard.models import TicketStatus, TicketState

        ticket = TicketStatus(ticket_id="T-005")
        ticket.block()
        assert ticket.state == TicketState.BLOCKED

    def test_duration_seconds(self):
        from core.dashboard.models import TicketStatus

        now = time.time()
        ticket = TicketStatus(
            ticket_id="T-006",
            started_at=now - 120.0,
            completed_at=now,
        )
        duration = ticket.duration_seconds
        assert duration is not None
        assert abs(duration - 120.0) < 0.1

    def test_duration_none_when_incomplete(self):
        from core.dashboard.models import TicketStatus

        ticket = TicketStatus(ticket_id="T-007")
        assert ticket.duration_seconds is None

    def test_to_dict_keys(self):
        from core.dashboard.models import TicketStatus

        ticket = TicketStatus(ticket_id="T-008", title="테스트", org_id="dev")
        d = ticket.to_dict()
        for key in ("ticket_id", "state", "assignee", "created_at", "title", "org_id", "color", "emoji"):
            assert key in d, f"to_dict()에 '{key}' 키 없음"

    def test_from_dict_roundtrip(self):
        from core.dashboard.models import TicketStatus

        original = TicketStatus(ticket_id="T-009", title="roundtrip", assignee="dev_bot")
        d = original.to_dict()
        restored = TicketStatus.from_dict(d)
        assert restored.ticket_id == original.ticket_id
        assert restored.state == original.state
        assert restored.assignee == original.assignee

    def test_is_done_property(self):
        from core.dashboard.models import TicketStatus, TicketState

        ticket = TicketStatus(ticket_id="T-010", state=TicketState.DONE)
        assert ticket.is_done is True
        assert ticket.is_active is False

    def test_is_active_property(self):
        from core.dashboard.models import TicketStatus, TicketState

        ticket = TicketStatus(ticket_id="T-011", state=TicketState.IN_PROGRESS)
        assert ticket.is_active is True
        assert ticket.is_done is False


class TestOrgCharacters:
    def test_known_org(self):
        from core.dashboard.models import get_character

        char = get_character("aiorg_engineering_bot")
        assert "emoji" in char
        assert "name" in char
        assert char["emoji"] == "🦾"

    def test_unknown_org_fallback(self):
        from core.dashboard.models import get_character

        char = get_character("unknown_org")
        assert char["emoji"] == "🤖"


# ---------------------------------------------------------------------------
# core.dashboard.aggregator 테스트
# ---------------------------------------------------------------------------


def _make_done_ticket(ticket_id: str, completed_seconds_ago: float) -> "TicketStatus":
    from core.dashboard.models import TicketStatus, TicketState

    now = time.time()
    completed = now - completed_seconds_ago
    started = completed - 60.0
    return TicketStatus(
        ticket_id=ticket_id,
        state=TicketState.DONE,
        completed_at=completed,
        started_at=started,
    )


def _make_pending_ticket(ticket_id: str) -> "TicketStatus":
    from core.dashboard.models import TicketStatus

    return TicketStatus(ticket_id=ticket_id)


class TestAggregateByPeriod:
    def test_empty_tickets(self):
        from core.dashboard.aggregator import aggregate_by_period

        result = aggregate_by_period([], period_hours=1)
        assert result.completed == 0
        assert result.throughput == 0.0

    def test_completed_within_1h(self):
        from core.dashboard.aggregator import aggregate_by_period

        tickets = [
            _make_done_ticket("T-01", 1800),   # 30분 전 완료
            _make_done_ticket("T-02", 3000),   # 50분 전 완료
            _make_done_ticket("T-03", 7200),   # 2시간 전 완료 (제외)
        ]
        result = aggregate_by_period(tickets, period_hours=1)
        assert result.completed == 2

    def test_throughput_calculation(self):
        from core.dashboard.aggregator import aggregate_by_period

        # 지난 6시간에 6개 완료 → 1 ticket/hr
        tickets = [_make_done_ticket(f"T-{i}", i * 3000) for i in range(1, 7)]
        result = aggregate_by_period(tickets, period_hours=6)
        assert result.completed == 6
        assert abs(result.throughput - 1.0) < 0.01

    def test_period_hours_zero_raises(self):
        from core.dashboard.aggregator import aggregate_by_period

        with pytest.raises(ValueError, match="period_hours"):
            aggregate_by_period([], period_hours=0)

    def test_period_hours_negative_raises(self):
        from core.dashboard.aggregator import aggregate_by_period

        with pytest.raises(ValueError):
            aggregate_by_period([], period_hours=-1)

    def test_avg_duration_calculated(self):
        from core.dashboard.aggregator import aggregate_by_period

        tickets = [_make_done_ticket(f"T-{i}", i * 100) for i in range(1, 4)]
        result = aggregate_by_period(tickets, period_hours=24)
        assert result.avg_duration is not None
        assert result.avg_duration > 0

    def test_pending_tickets_excluded(self):
        from core.dashboard.aggregator import aggregate_by_period

        tickets = [
            _make_done_ticket("T-done", 100),
            _make_pending_ticket("T-pending"),
        ]
        result = aggregate_by_period(tickets, period_hours=1)
        assert result.completed == 1

    def test_to_dict_returns_expected_keys(self):
        from core.dashboard.aggregator import aggregate_by_period

        result = aggregate_by_period([], period_hours=6)
        d = result.to_dict()
        for key in ("period_hours", "completed", "throughput", "window_start", "window_end"):
            assert key in d, f"to_dict()에 '{key}' 키 없음"


class TestComputeThroughput:
    def test_returns_float(self):
        from core.dashboard.aggregator import compute_throughput

        result = compute_throughput([], window_hours=1)
        assert isinstance(result, float)
        assert result == 0.0

    def test_with_done_tickets(self):
        from core.dashboard.aggregator import compute_throughput

        tickets = [_make_done_ticket(f"T-{i}", i * 600) for i in range(1, 5)]  # 4개 in 1h
        result = compute_throughput(tickets, window_hours=1)
        assert result == 4.0


class TestAggregateAllPeriods:
    def test_returns_three_keys(self):
        from core.dashboard.aggregator import aggregate_all_periods

        results = aggregate_all_periods([])
        assert set(results.keys()) == {"1h", "6h", "24h"}

    def test_longer_period_has_more_completed(self):
        from core.dashboard.aggregator import aggregate_all_periods

        tickets = [
            _make_done_ticket("T-1h", 1800),    # 30분 전 → 1h, 6h, 24h 모두 포함
            _make_done_ticket("T-6h", 18000),   # 5시간 전 → 6h, 24h 포함
            _make_done_ticket("T-24h", 72000),  # 20시간 전 → 24h만 포함
        ]
        results = aggregate_all_periods(tickets)
        assert results["1h"].completed == 1
        assert results["6h"].completed == 2
        assert results["24h"].completed == 3


class TestCountByState:
    def test_all_states_present(self):
        from core.dashboard.aggregator import count_by_state
        from core.dashboard.models import TicketStatus, TicketState

        tickets = [
            TicketStatus("T-1", state=TicketState.PENDING),
            TicketStatus("T-2", state=TicketState.IN_PROGRESS),
            TicketStatus("T-3", state=TicketState.DONE),
            TicketStatus("T-4", state=TicketState.BLOCKED),
        ]
        counts = count_by_state(tickets)
        assert counts["pending"] == 1
        assert counts["in_progress"] == 1
        assert counts["done"] == 1
        assert counts["blocked"] == 1

    def test_empty_returns_zeros(self):
        from core.dashboard.aggregator import count_by_state

        counts = count_by_state([])
        assert all(v == 0 for v in counts.values())


# ---------------------------------------------------------------------------
# core.dashboard.adapter 테스트
# ---------------------------------------------------------------------------


class TestDataSourceAdapter:
    @pytest.mark.asyncio
    async def test_fetch_once_returns_list(self):
        from core.dashboard.adapter import DataSourceAdapter

        adapter = DataSourceAdapter(db_path=":nonexistent:", yaml_path="/nonexistent.yaml")
        # 소스 없으므로 mock 데이터 반환
        tickets = await adapter.fetch_once()
        assert isinstance(tickets, list)
        assert len(tickets) > 0

    @pytest.mark.asyncio
    async def test_start_stop(self):
        from core.dashboard.adapter import DataSourceAdapter

        adapter = DataSourceAdapter(poll_interval=9999)  # 폴링은 바로 안 돌게
        await adapter.start()
        assert adapter._running is True
        await adapter.stop()
        assert adapter._running is False

    @pytest.mark.asyncio
    async def test_callback_called_on_update(self):
        from core.dashboard.adapter import DataSourceAdapter
        from core.dashboard.models import TicketStatus

        received = []

        async def callback(tickets):
            received.extend(tickets)

        adapter = DataSourceAdapter(poll_interval=9999, db_path=":nonexistent:", yaml_path="/nonexistent.yaml")
        adapter.on_update(callback)
        tickets = await adapter.fetch_once()
        await adapter._notify(tickets)
        assert len(received) > 0

    def test_last_tickets_initially_empty(self):
        from core.dashboard.adapter import DataSourceAdapter

        adapter = DataSourceAdapter()
        assert adapter.last_tickets == []

    @pytest.mark.asyncio
    async def test_mock_tickets_have_required_fields(self):
        from core.dashboard.adapter import DataSourceAdapter

        adapter = DataSourceAdapter(db_path=":nonexistent:", yaml_path="/nonexistent.yaml")
        tickets = await adapter.fetch_once()
        for t in tickets:
            assert t.ticket_id, "ticket_id 누락"
            assert t.state is not None, "state 누락"
            assert t.assignee, "assignee 누락"

    @pytest.mark.asyncio
    async def test_yaml_load_with_valid_data(self, tmp_path):
        """유효한 YAML 파일에서 티켓 로드."""
        import yaml
        from core.dashboard.adapter import DataSourceAdapter

        data = [
            {"id": "T-yaml-1", "status": "pending", "assignee": "bot1", "title": "YAML 테스트"},
            {"id": "T-yaml-2", "status": "done", "assignee": "bot2", "title": "완료된 작업"},
        ]
        yaml_file = tmp_path / "tasks.yaml"
        yaml_file.write_text(yaml.dump(data), encoding="utf-8")

        adapter = DataSourceAdapter(db_path=":nonexistent:", yaml_path=str(yaml_file))
        tickets = await adapter.fetch_once()
        assert len(tickets) == 2
        assert tickets[0].ticket_id == "T-yaml-1"


# ---------------------------------------------------------------------------
# core.dashboard.pusher 테스트
# ---------------------------------------------------------------------------


class TestDashboardPusher:
    @pytest.mark.asyncio
    async def test_get_snapshot_returns_dict(self):
        from core.dashboard.pusher import DashboardPusher

        pusher = DashboardPusher(poll_interval=9999, db_path=":nonexistent:", yaml_path="/nonexistent.yaml")
        # fetch_once로 초기 데이터 로드
        await pusher._adapter.fetch_once()
        snapshot = pusher.get_snapshot()

        assert "counts" in snapshot
        assert "aggregations" in snapshot
        assert "recent_completed" in snapshot
        assert "timestamp" in snapshot

    @pytest.mark.asyncio
    async def test_start_stop(self):
        from core.dashboard.pusher import DashboardPusher

        pusher = DashboardPusher(poll_interval=9999)
        await pusher.start()
        assert pusher._adapter._running is True
        await pusher.stop()
        assert pusher._adapter._running is False

    @pytest.mark.asyncio
    async def test_on_tickets_updated_publishes_events(self):
        """SSE 이벤트 발행 검증."""
        from core.dashboard.pusher import DashboardPusher
        from core.dashboard.models import TicketStatus, TicketState

        published = []

        def mock_publish(event_type, data):
            published.append((event_type, data))

        tickets = [
            TicketStatus("T-a", state=TicketState.PENDING),
            TicketStatus("T-b", state=TicketState.IN_PROGRESS),
        ]

        # publish_event는 pusher.py 내 로컬 import 경로를 패치
        pusher = DashboardPusher(poll_interval=9999)
        with patch("core.api.routes.events.publish_event", side_effect=mock_publish):
            with patch("core.api.routes.events._subscribers", []):
                await pusher._on_tickets_updated(tickets)

        event_types = [p[0] for p in published]
        assert "ticket_update" in event_types
