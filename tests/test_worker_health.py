"""워커 헬스 모니터 테스트 — usefulness 기반 헬스체크, 리트라이, DLQ."""
from __future__ import annotations

import time

from core.worker_health import WorkerHealthMonitor, WorkerStatus


class TestWorkerHealthBasic:
    """기존 API 하위호환 테스트."""

    def test_register_and_get_available(self):
        mon = WorkerHealthMonitor()
        mon.register("w1")
        mon.register("w2")
        available = mon.get_available()
        assert "w1" in available
        assert "w2" in available

    def test_mark_online_busy_done(self):
        mon = WorkerHealthMonitor()
        mon.register("w1")
        mon.mark_online("w1")
        assert mon._health["w1"].status == WorkerStatus.ONLINE

        mon.mark_busy("w1", "T001")
        assert mon._health["w1"].status == WorkerStatus.BUSY
        assert mon._health["w1"].current_task == "T001"

        mon.mark_done("w1", success=True)
        assert mon._health["w1"].status == WorkerStatus.ONLINE
        assert mon._health["w1"].completed_tasks == 1
        assert mon._health["w1"].current_task is None

    def test_mark_offline(self):
        mon = WorkerHealthMonitor()
        mon.register("w1")
        mon.mark_offline("w1")
        assert mon._health["w1"].status == WorkerStatus.OFFLINE
        assert "w1" not in mon.get_available()

    def test_status_report(self):
        mon = WorkerHealthMonitor()
        mon.register("w1")
        mon.mark_online("w1")
        report = mon.get_status_report()
        assert "w1" in report
        assert "📊" in report


class TestSuccessSemantics:
    """연속 실패 → DEGRADED → QUARANTINED 전환 테스트."""

    def test_degraded_after_consecutive_failures(self):
        mon = WorkerHealthMonitor()
        mon.register("w1")
        mon.mark_online("w1")
        # 3회 실패 → 아직 ONLINE
        for _ in range(3):
            mon.mark_done("w1", success=False)
        assert mon._health["w1"].status == WorkerStatus.ONLINE

        # 4회째 실패 → DEGRADED
        mon.mark_done("w1", success=False)
        assert mon._health["w1"].status == WorkerStatus.DEGRADED
        assert mon._health["w1"].consecutive_failures == 4

    def test_quarantined_after_many_failures(self):
        mon = WorkerHealthMonitor()
        mon.register("w1")
        mon.mark_online("w1")
        for _ in range(6):
            mon.mark_done("w1", success=False)
        assert mon._health["w1"].status == WorkerStatus.QUARANTINED

    def test_quarantined_not_in_available(self):
        mon = WorkerHealthMonitor()
        mon.register("w1")
        mon.mark_online("w1")
        for _ in range(6):
            mon.mark_done("w1", success=False)
        assert "w1" not in mon.get_available()

    def test_degraded_in_available_as_fallback(self):
        mon = WorkerHealthMonitor()
        mon.register("w1")
        mon.register("w2")
        mon.mark_online("w1")
        mon.mark_online("w2")
        # w1을 DEGRADED로 만듦
        for _ in range(4):
            mon.mark_done("w1", success=False)
        available = mon.get_available()
        # w2가 먼저, w1(DEGRADED)이 뒤에
        assert available.index("w2") < available.index("w1")

    def test_success_resets_consecutive_failures(self):
        mon = WorkerHealthMonitor()
        mon.register("w1")
        mon.mark_online("w1")
        for _ in range(3):
            mon.mark_done("w1", success=False)
        mon.mark_done("w1", success=True)
        assert mon._health["w1"].consecutive_failures == 0
        assert mon._health["w1"].status == WorkerStatus.ONLINE

    def test_success_rate(self):
        mon = WorkerHealthMonitor()
        mon.register("w1")
        mon.mark_done("w1", success=True)
        mon.mark_done("w1", success=True)
        mon.mark_done("w1", success=False)
        h = mon._health["w1"]
        assert abs(h.success_rate - 2 / 3) < 0.01


class TestResetWorker:
    """격리 해제 테스트."""

    def test_reset_quarantined(self):
        mon = WorkerHealthMonitor()
        mon.register("w1")
        for _ in range(6):
            mon.mark_done("w1", success=False)
        assert mon._health["w1"].status == WorkerStatus.QUARANTINED

        mon.reset_worker("w1")
        assert mon._health["w1"].status == WorkerStatus.ONLINE
        assert mon._health["w1"].consecutive_failures == 0
        assert "w1" in mon.get_available()


class TestRetryAndBackoff:
    """리트라이 시도 추적 + 지수 백오프 테스트."""

    def test_record_attempt(self):
        mon = WorkerHealthMonitor()
        assert mon.get_attempt_count("T001") == 0
        assert mon.record_attempt("T001") == 1
        assert mon.record_attempt("T001") == 2

    def test_should_retry(self):
        mon = WorkerHealthMonitor()
        assert mon.should_retry("T001") is True
        mon.record_attempt("T001")
        mon.record_attempt("T001")
        mon.record_attempt("T001")
        assert mon.should_retry("T001") is False  # 3회 시도 완료

    def test_should_retry_custom_max(self):
        mon = WorkerHealthMonitor()
        mon.record_attempt("T001")
        assert mon.should_retry("T001", max_attempts=1) is False

    def test_retry_delay_exponential(self):
        mon = WorkerHealthMonitor()
        mon.record_attempt("T001")  # 1회
        assert mon.get_retry_delay("T001") == 2.0  # 2^0 * 2

        mon.record_attempt("T001")  # 2회
        assert mon.get_retry_delay("T001") == 4.0  # 2^1 * 2

        mon.record_attempt("T001")  # 3회
        assert mon.get_retry_delay("T001") == 8.0  # 2^2 * 2

    def test_retry_delay_max_cap(self):
        mon = WorkerHealthMonitor()
        for _ in range(20):
            mon.record_attempt("T001")
        assert mon.get_retry_delay("T001") == 120.0  # max cap

    def test_no_attempts_zero_delay(self):
        mon = WorkerHealthMonitor()
        assert mon.get_retry_delay("T001") == 0.0


class TestDLQ:
    """Dead-Letter Queue 테스트."""

    def test_move_to_dlq(self):
        mon = WorkerHealthMonitor()
        mon.record_attempt("T001")
        mon.record_attempt("T001")
        mon.move_to_dlq("T001", "w1", "max attempts exceeded")
        assert mon.dlq_size == 1
        assert mon.get_attempt_count("T001") == 0  # 카운터 정리됨

    def test_dlq_entry_fields(self):
        mon = WorkerHealthMonitor()
        mon.record_attempt("T001")
        mon.move_to_dlq("T001", "w1", "timeout")
        entries = mon.get_dlq()
        assert len(entries) == 1
        assert entries[0].task_id == "T001"
        assert entries[0].worker_name == "w1"
        assert entries[0].reason == "timeout"
        assert entries[0].attempts == 1

    def test_dlq_multiple_entries(self):
        mon = WorkerHealthMonitor()
        mon.move_to_dlq("T001", "w1", "reason1")
        mon.move_to_dlq("T002", "w2", "reason2")
        assert mon.dlq_size == 2


class TestLeaseSystem:
    """리스 갱신 테스트."""

    def test_renew_lease(self):
        mon = WorkerHealthMonitor()
        mon.register("w1")
        mon.mark_online("w1")
        old_lease = mon._health["w1"].lease_expires_at
        time.sleep(0.01)
        mon.renew_lease("w1")
        assert mon._health["w1"].lease_expires_at > old_lease

    def test_lease_expiry_degrades(self):
        mon = WorkerHealthMonitor()
        mon.register("w1")
        mon.mark_online("w1")
        # 리스를 과거로 설정
        mon._health["w1"].lease_expires_at = time.time() - 1
        mon.get_available()
        assert mon._health["w1"].status == WorkerStatus.DEGRADED


class TestMetrics:
    """시스템 메트릭스 테스트."""

    def test_metrics_basic(self):
        mon = WorkerHealthMonitor()
        mon.register("w1")
        mon.register("w2")
        mon.mark_online("w1")
        mon.mark_online("w2")
        mon.mark_busy("w1", "T001")
        mon.mark_done("w1", success=True)
        mon.mark_done("w2", success=False)

        metrics = mon.get_metrics()
        assert metrics["total_processed"] == 2
        assert metrics["total_failed"] == 1
        assert metrics["workers_online"] >= 1
        assert metrics["dlq_size"] == 0

    def test_latency_tracking(self):
        mon = WorkerHealthMonitor()
        mon.register("w1")
        mon.mark_busy("w1", "T001")
        time.sleep(0.05)
        mon.mark_done("w1", success=True)
        assert mon._health["w1"].avg_latency > 0
