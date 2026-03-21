"""OrgScheduler 잡 등록 테스트."""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest


def test_routing_optimizer_job_registered():
    """routing_optimizer_daily 잡이 스케줄러에 등록되어 있어야 한다."""
    from core.scheduler import OrgScheduler
    sched = OrgScheduler(send_text=lambda t: None)
    job_ids = sched.get_job_ids()
    assert "routing_optimizer_daily" in job_ids
