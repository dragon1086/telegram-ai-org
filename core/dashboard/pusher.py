"""core.dashboard.pusher — 실시간 SSE 이벤트 발행기 (Phase 1).

DataSourceAdapter 폴링 결과를 SSE 이벤트로 변환하여 발행한다.

발행 이벤트 타입:
    - ticket_update       : 상태별 카운트 변경
    - task_complete       : 개별 티켓 완료
    - remote_access_change: 접속 클라이언트 수 변경
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from core.dashboard.adapter import DataSourceAdapter
from core.dashboard.aggregator import aggregate_all_periods, count_by_state
from core.dashboard.models import TicketStatus, TicketState

logger = logging.getLogger(__name__)


class DashboardPusher:
    """어댑터 → SSE 이벤트 변환·발행 파이프라인.

    사용 예::

        pusher = DashboardPusher()
        await pusher.start()   # 백그라운드 폴링 + SSE 발행 시작
        ...
        await pusher.stop()
    """

    def __init__(
        self,
        poll_interval: float = 5.0,
        db_path: str | None = None,
        yaml_path: str | None = None,
    ) -> None:
        kwargs: dict = {"poll_interval": poll_interval}
        if db_path:
            kwargs["db_path"] = db_path
        if yaml_path:
            kwargs["yaml_path"] = yaml_path

        self._adapter = DataSourceAdapter(**kwargs)
        self._prev_counts: dict[str, int] = {}
        self._prev_done_ids: set[str] = set()

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """폴링 + SSE 발행 시작."""
        self._adapter.on_update(self._on_tickets_updated)
        await self._adapter.start()
        logger.info("DashboardPusher 시작")

    async def stop(self) -> None:
        """폴링 중단."""
        await self._adapter.stop()
        logger.info("DashboardPusher 중단")

    def get_snapshot(self) -> dict:
        """현재 스냅샷 반환 (초기 로드용)."""
        tickets = self._adapter.last_tickets
        counts = count_by_state(tickets)
        agg = aggregate_all_periods(tickets)
        return {
            "counts": counts,
            "aggregations": {k: v.to_dict() for k, v in agg.items()},
            "recent_completed": [
                t.to_dict()
                for t in tickets
                if t.state == TicketState.DONE
            ][-20:],  # 최신 20건
            "timestamp": time.time(),
        }

    # ------------------------------------------------------------------
    # 내부 이벤트 처리
    # ------------------------------------------------------------------

    async def _on_tickets_updated(self, tickets: list[TicketStatus]) -> None:
        """폴링 콜백 — 변경 감지 후 SSE 이벤트 발행."""
        try:
            from core.api.routes.events import publish_event, _set_pusher
            _set_pusher(self)  # 스냅샷 접근용 참조 등록
        except ImportError:
            logger.debug("events 모듈 없음 — SSE 발행 스킵")
            return

        # Phase 2 ConnectionManager 임포트 (실패해도 계속 진행)
        try:
            from core.dashboard.connection_manager import connection_manager as cm
        except ImportError:
            cm = None

        # 1) 상태별 카운트 변경 감지
        counts = count_by_state(tickets)
        if counts != self._prev_counts:
            agg = aggregate_all_periods(tickets)
            ticket_payload = {
                **counts,
                "aggregations": {k: v.to_dict() for k, v in agg.items()},
                "ts": time.time(),
            }
            # 글로벌 이벤트 발행 (하위 호환 + all 채널)
            publish_event("ticket_update", ticket_payload)
            # tickets 전용 채널 발행 (Phase 2)
            if cm is not None:
                cm.publish("tickets", "ticket_update", ticket_payload)
            self._prev_counts = dict(counts)

        # 2) 새로 완료된 티켓 감지
        done_ids = {t.ticket_id for t in tickets if t.state == TicketState.DONE}
        new_done = done_ids - self._prev_done_ids
        for ticket in tickets:
            if ticket.ticket_id in new_done:
                task_payload = {**ticket.to_dict(), "ts": time.time()}
                publish_event("task_complete", task_payload)
                # completed-tasks 전용 채널 발행 (Phase 2)
                if cm is not None:
                    cm.publish("completed-tasks", "task_complete", task_payload)
        self._prev_done_ids = done_ids

        # 3) 원격 접근 상태 발행 (구독자 수 기반)
        try:
            from core.api.routes.events import _subscribers
            client_count = len(_subscribers)
            remote_payload = {"client_count": client_count, "ts": time.time()}
            publish_event("remote_access_change", remote_payload)
            # remote-access 전용 채널 발행 (Phase 2)
            if cm is not None:
                cm.publish("remote-access", "remote_access_change", {
                    **remote_payload,
                    "channel_stats": cm.get_channel_stats(),
                })
        except ImportError:
            pass
