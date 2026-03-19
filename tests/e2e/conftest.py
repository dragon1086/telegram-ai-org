"""E2E 테스트 공통 fixture."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from core.agent_persona_memory import AgentPersonaMemory
from core.collaboration_tracker import CollaborationTracker
from core.shoutout_system import ShoutoutSystem
from core.pm_orchestrator import PMOrchestrator


class _FakeOrg:
    def __init__(self, org_id: str, dept_name: str = "", direction: str = ""):
        self.id = org_id
        self.dept_name = dept_name
        self.direction = direction


class _FakeConfig:
    def list_orgs(self):
        return [
            _FakeOrg("aiorg_dev", "개발팀", "소프트웨어 개발"),
            _FakeOrg("aiorg_mkt", "마케팅팀", "마케팅 전략"),
            _FakeOrg("aiorg_ops", "운영팀", "시스템 운영"),
        ]

    def get_org(self, org_id: str):
        for org in self.list_orgs():
            if org.id == org_id:
                return org
        return None


@pytest.fixture
def persona_memory(tmp_path):
    """격리된 SQLite DB를 사용하는 AgentPersonaMemory."""
    return AgentPersonaMemory(db_path=tmp_path / "persona.db")


@pytest.fixture
def collaboration_tracker(tmp_path, persona_memory):
    """persona_memory가 주입된 CollaborationTracker."""
    return CollaborationTracker(
        db_path=tmp_path / "collab.db",
        persona_memory=persona_memory,
    )


@pytest.fixture
def shoutout_system(tmp_path):
    """격리된 SQLite DB를 사용하는 ShoutoutSystem."""
    return ShoutoutSystem(db_path=tmp_path / "shoutout.db")


@pytest.fixture
def fake_config():
    return _FakeConfig()


@pytest.fixture
def make_orchestrator():
    """PMOrchestrator 팩토리 fixture."""
    def _factory(org_id: str = "aiorg_pm"):
        db = MagicMock()
        graph = MagicMock()
        claim = MagicMock()
        memory = MagicMock()
        return PMOrchestrator(
            context_db=db,
            task_graph=graph,
            claim_manager=claim,
            memory=memory,
            org_id=org_id,
            telegram_send_func=AsyncMock(),
            decision_client=None,
        )
    return _factory
