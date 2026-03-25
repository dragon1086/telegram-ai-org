"""COLLAB 자동 트리거 테스트.

orchestration.yaml collab_triggers 파싱 + PMOrchestrator._fire_collab_triggers
동작을 검증한다.
"""
from __future__ import annotations

import sys
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.orchestration_config import CollabTrigger, OrchestrationConfig


# ── CollabTrigger 단위 테스트 ────────────────────────────────────────────────


def _make_trigger(**kwargs) -> CollabTrigger:
    defaults = dict(
        id="test_trigger",
        description="테스트 트리거",
        trigger_dept="aiorg_product_bot",
        trigger_task_types=["기획", "PRD"],
        target_depts=["aiorg_design_bot"],
        message_template="[COLLAB] {source_dept} → {target_role}\n{result_summary}",
        enabled=True,
        dedup_window_minutes=60,
    )
    defaults.update(kwargs)
    return CollabTrigger(**defaults)


class TestCollabTriggerMatches:
    def test_matches_exact_dept_and_type(self):
        t = _make_trigger()
        assert t.matches("aiorg_product_bot", "기획") is True

    def test_no_match_wrong_dept(self):
        t = _make_trigger()
        assert t.matches("aiorg_engineering_bot", "기획") is False

    def test_no_match_wrong_task_type(self):
        t = _make_trigger()
        assert t.matches("aiorg_product_bot", "구현") is False

    def test_empty_task_types_matches_any(self):
        t = _make_trigger(trigger_task_types=[])
        assert t.matches("aiorg_product_bot", "아무거나") is True

    def test_disabled_trigger_never_matches(self):
        t = _make_trigger(enabled=False)
        assert t.matches("aiorg_product_bot", "기획") is False


class TestCollabTriggerRenderMessage:
    def test_render_substitution(self):
        t = _make_trigger(
            message_template="FROM:{source_dept} TASK:{source_task_id} ROLE:{target_role}\n{result_summary}"
        )
        rendered = t.render_message(
            source_dept="기획실",
            source_task_id="T-001",
            result_summary="PRD 완성",
            target_role="개발팀",
        )
        assert "기획실" in rendered
        assert "T-001" in rendered
        assert "개발팀" in rendered
        assert "PRD 완성" in rendered


# ── OrchestrationConfig collab_triggers 파싱 테스트 ─────────────────────────


_ORGS_YAML = textwrap.dedent("""
schema_version: 2
organizations:
  - id: aiorg_product_bot
    enabled: true
    kind: specialist
    description: 기획실
    telegram:
      username: product_bot
      token_env: PROD_TOKEN
      chat_id: 1001
    identity:
      dept_name: 기획실
      role: 기획
      specialties: [기획]
      direction: 요구사항 정리
      instruction: 기획해라
    routing:
      default_handler: false
      can_direct_reply: false
    execution:
      preferred_engine: claude-code
    team: {}
    collaboration: {}
  - id: aiorg_design_bot
    enabled: true
    kind: specialist
    description: 디자인실
    telegram:
      username: design_bot
      token_env: DESIGN_TOKEN
      chat_id: 1002
    identity:
      dept_name: 디자인실
      role: 디자인
      specialties: [UX]
      direction: UX 디자인
      instruction: 디자인해라
    routing:
      default_handler: false
      can_direct_reply: false
    execution:
      preferred_engine: claude-code
    team: {}
    collaboration: {}
  - id: aiorg_engineering_bot
    enabled: true
    kind: specialist
    description: 개발실
    telegram:
      username: engineering_bot
      token_env: ENG_TOKEN
      chat_id: 1003
    identity:
      dept_name: 개발실
      role: 개발
      specialties: [Python]
      direction: 구현
      instruction: 개발해라
    routing:
      default_handler: false
      can_direct_reply: false
    execution:
      preferred_engine: claude-code
    team: {}
    collaboration: {}
""")

_ORCH_YAML_WITH_TRIGGERS = textwrap.dedent("""
schema_version: 1
collab_triggers:
  - id: planning_to_design
    description: "기획 완료 → 디자인 연계"
    trigger_dept: aiorg_product_bot
    trigger_task_types:
      - 기획
      - PRD
    target_depts:
      - aiorg_design_bot
    message_template: |
      [COLLAB] {source_dept} 기획 완료
      태스크: {source_task_id}
      요약: {result_summary}
      역할: {target_role}
    enabled: true
    dedup_window_minutes: 60

  - id: planning_to_engineering
    description: "기획 완료 → 개발 연계"
    trigger_dept: aiorg_product_bot
    trigger_task_types:
      - 기획
    target_depts:
      - aiorg_engineering_bot
    message_template: "[COLLAB] 개발 착수"
    enabled: true
    dedup_window_minutes: 30

  - id: disabled_trigger
    description: "비활성 트리거"
    trigger_dept: aiorg_product_bot
    trigger_task_types:
      - 기획
    target_depts:
      - aiorg_design_bot
    message_template: "절대 안보임"
    enabled: false
    dedup_window_minutes: 10
""")


@pytest.fixture
def config_with_triggers(tmp_path):
    orgs_path = tmp_path / "organizations.yaml"
    orch_path = tmp_path / "orchestration.yaml"
    orgs_path.write_text(_ORGS_YAML, encoding="utf-8")
    orch_path.write_text(_ORCH_YAML_WITH_TRIGGERS, encoding="utf-8")
    cfg = OrchestrationConfig(orgs_path=orgs_path, orchestration_path=orch_path)
    cfg.load()
    return cfg


class TestOrchestrationConfigCollab:
    def test_parses_collab_triggers(self, config_with_triggers):
        cfg = config_with_triggers
        assert len(cfg.collab_triggers) == 3

    def test_active_trigger_count(self, config_with_triggers):
        enabled = [t for t in config_with_triggers.collab_triggers if t.enabled]
        assert len(enabled) == 2

    def test_get_collab_triggers_planning_기획(self, config_with_triggers):
        matches = config_with_triggers.get_collab_triggers("aiorg_product_bot", "기획")
        ids = [t.id for t in matches]
        assert "planning_to_design" in ids
        assert "planning_to_engineering" in ids
        assert "disabled_trigger" not in ids

    def test_get_collab_triggers_prd_only_one(self, config_with_triggers):
        matches = config_with_triggers.get_collab_triggers("aiorg_product_bot", "PRD")
        ids = [t.id for t in matches]
        assert "planning_to_design" in ids
        assert "planning_to_engineering" not in ids   # PRD가 trigger_task_types에 없음

    def test_no_match_wrong_dept(self, config_with_triggers):
        matches = config_with_triggers.get_collab_triggers("aiorg_engineering_bot", "기획")
        assert matches == []

    def test_trigger_attributes(self, config_with_triggers):
        trigger = next(t for t in config_with_triggers.collab_triggers if t.id == "planning_to_design")
        assert trigger.trigger_dept == "aiorg_product_bot"
        assert "aiorg_design_bot" in trigger.target_depts
        assert trigger.dedup_window_minutes == 60


# ── PMOrchestrator._fire_collab_triggers 통합 테스트 ────────────────────────


@pytest.fixture
async def db_with_task(tmp_path):
    from core.context_db import ContextDB
    cdb = ContextDB(tmp_path / "test.db")
    await cdb.initialize()
    await cdb.create_pm_task(
        task_id="T-001",
        description="기획서 작성",
        assigned_dept="aiorg_product_bot",
        created_by="aiorg_pm_bot",
        metadata={"task_type": "기획"},
    )
    await cdb.update_pm_task_status("T-001", "done", result="PRD v1 완성")
    return cdb


@pytest.mark.asyncio
async def test_fire_collab_triggers_creates_tasks(tmp_path, db_with_task):
    """_fire_collab_triggers: 기획 완료 → 디자인·개발 태스크 자동 생성."""
    from core.task_graph import TaskGraph
    from core.claim_manager import ClaimManager
    from core.memory_manager import MemoryManager
    from core.pm_orchestrator import PMOrchestrator

    orgs_path = tmp_path / "organizations.yaml"
    orch_path = tmp_path / "orchestration.yaml"
    orgs_path.write_text(_ORGS_YAML, encoding="utf-8")
    orch_path.write_text(_ORCH_YAML_WITH_TRIGGERS, encoding="utf-8")

    send_fn = AsyncMock()
    tg = TaskGraph(db_with_task)
    claim = ClaimManager()
    memory = MemoryManager(db_with_task)

    orchestrator = PMOrchestrator(
        context_db=db_with_task,
        task_graph=tg,
        claim_manager=claim,
        memory=memory,
        org_id="aiorg_pm_bot",
        telegram_send_func=send_fn,
    )

    with patch(
        "core.pm_orchestrator.load_orchestration_config",
        return_value=OrchestrationConfig(
            orgs_path=orgs_path, orchestration_path=orch_path
        ).load(),
    ):
        await orchestrator._fire_collab_triggers("T-001", "PRD v1 완성", chat_id=999)

    # design + engineering 두 태스크가 생성되어야 함
    # collab_dispatch는 source task_id를 parent_id로 사용해 subtask를 생성
    collab_tasks = await db_with_task.get_subtasks("T-001")
    assert len(collab_tasks) == 2, f"collab 태스크 2개 기대, 실제: {len(collab_tasks)}"

    target_depts = {t["assigned_dept"] for t in collab_tasks}
    assert "aiorg_design_bot" in target_depts
    assert "aiorg_engineering_bot" in target_depts


@pytest.mark.asyncio
async def test_fire_collab_triggers_dedup(tmp_path, db_with_task):
    """같은 (source_task_id, target_dept) 조합은 dedup_window 내 재트리거 억제."""
    from core.task_graph import TaskGraph
    from core.claim_manager import ClaimManager
    from core.memory_manager import MemoryManager
    from core.pm_orchestrator import PMOrchestrator

    orgs_path = tmp_path / "organizations.yaml"
    orch_path = tmp_path / "orchestration.yaml"
    orgs_path.write_text(_ORGS_YAML, encoding="utf-8")
    orch_path.write_text(_ORCH_YAML_WITH_TRIGGERS, encoding="utf-8")

    send_fn = AsyncMock()
    tg = TaskGraph(db_with_task)
    claim = ClaimManager()
    memory = MemoryManager(db_with_task)

    orchestrator = PMOrchestrator(
        context_db=db_with_task,
        task_graph=tg,
        claim_manager=claim,
        memory=memory,
        org_id="aiorg_pm_bot",
        telegram_send_func=send_fn,
    )

    cfg = OrchestrationConfig(
        orgs_path=orgs_path, orchestration_path=orch_path
    ).load()

    with patch("core.pm_orchestrator.load_orchestration_config", return_value=cfg):
        # 1차 발동
        await orchestrator._fire_collab_triggers("T-001", "결과1", chat_id=999)
        first_count = len(await db_with_task.get_subtasks("T-001"))
        # 2차 발동 (dedup 창 내)
        await orchestrator._fire_collab_triggers("T-001", "결과2", chat_id=999)
        second_count = len(await db_with_task.get_subtasks("T-001"))

    # dedup으로 인해 태스크 수 불변
    assert first_count == second_count, (
        f"dedup 미작동: 1차={first_count}, 2차={second_count}"
    )


@pytest.mark.asyncio
async def test_fire_collab_triggers_skips_collab_tasks(tmp_path):
    """이미 collab=True인 태스크 완료 시 순환 트리거 발동 안 함."""
    from core.context_db import ContextDB
    from core.task_graph import TaskGraph
    from core.claim_manager import ClaimManager
    from core.memory_manager import MemoryManager
    from core.pm_orchestrator import PMOrchestrator

    cdb = ContextDB(tmp_path / "test2.db")
    await cdb.initialize()
    await cdb.create_pm_task(
        task_id="T-collab",
        description="collab 태스크",
        assigned_dept="aiorg_product_bot",
        created_by="aiorg_pm_bot",
        metadata={"task_type": "기획", "collab": True},
    )
    await cdb.update_pm_task_status("T-collab", "done", result="완료")

    orgs_path = tmp_path / "organizations.yaml"
    orch_path = tmp_path / "orchestration.yaml"
    orgs_path.write_text(_ORGS_YAML, encoding="utf-8")
    orch_path.write_text(_ORCH_YAML_WITH_TRIGGERS, encoding="utf-8")

    send_fn = AsyncMock()
    orchestrator = PMOrchestrator(
        context_db=cdb,
        task_graph=TaskGraph(cdb),
        claim_manager=ClaimManager(),
        memory=MemoryManager(cdb),
        org_id="aiorg_pm_bot",
        telegram_send_func=send_fn,
    )

    cfg = OrchestrationConfig(
        orgs_path=orgs_path, orchestration_path=orch_path
    ).load()

    with patch("core.pm_orchestrator.load_orchestration_config", return_value=cfg):
        await orchestrator._fire_collab_triggers("T-collab", "결과", chat_id=999)

    # collab 태스크 자체를 parent로 하는 subtask가 없어야 함 (순환 방지)
    new_collab = await cdb.get_subtasks("T-collab")
    assert new_collab == [], f"순환 트리거 발생: {new_collab}"
