"""조직 이벤트 → 봇 성격 진화 E2E 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))


from core.agent_persona_memory import AgentPersonaMemory
from core.bot_character_evolution import BotCharacterEvolution
from core.collaboration_tracker import CollaborationTracker


# ---------------------------------------------------------------------------
# TC-A1: coding 성공 3회 → strengths에 'coding' 포함
# ---------------------------------------------------------------------------


def test_tc_a1_coding_success_adds_strength(persona_memory: AgentPersonaMemory) -> None:
    evo = BotCharacterEvolution(persona_memory=persona_memory)

    for _ in range(3):
        persona_memory.update_from_task("bot_a", "coding", success=True)

    result = evo.evolve("bot_a")

    assert "coding" in result["strengths"], f"strengths: {result['strengths']}"


# ---------------------------------------------------------------------------
# TC-A2: timeout 실패 3회 → weaknesses에 'timeout' 포함
# ---------------------------------------------------------------------------


def test_tc_a2_timeout_failure_adds_weakness(persona_memory: AgentPersonaMemory) -> None:
    evo = BotCharacterEvolution(persona_memory=persona_memory)

    for _ in range(3):
        persona_memory.update_from_task(
            "bot_a", "coding", success=False, failure_category="timeout"
        )

    result = evo.evolve("bot_a")

    assert "timeout" in result["weaknesses"], f"weaknesses: {result['weaknesses']}"


# ---------------------------------------------------------------------------
# TC-A3: CollaborationTracker(persona_memory=pm)로 5회 record → best_partner == 'bot_b'
# ---------------------------------------------------------------------------


def test_tc_a3_synergy_via_collaboration_tracker(
    persona_memory: AgentPersonaMemory,
    tmp_path: Path,
) -> None:
    tracker = CollaborationTracker(
        db_path=tmp_path / "collab_a3.db",
        persona_memory=persona_memory,
    )
    evo = BotCharacterEvolution(persona_memory=persona_memory)

    # agent_stats 행이 존재해야 get_stats()가 synergy_scores를 조회할 수 있음
    persona_memory.update_from_task("bot_a", "coding", success=True)

    for i in range(5):
        tracker.record(
            task_id=f"task-{i}",
            participants=["bot_a", "bot_b"],
            task_type="coding",
            success=True,
        )

    result = evo.evolve("bot_a")

    assert result["best_partner"] == "bot_b", f"best_partner: {result['best_partner']}"


# ---------------------------------------------------------------------------
# TC-A4: 2개 봇 stats 기록 후 evolve_all() → list 길이 >= 2
# ---------------------------------------------------------------------------


def test_tc_a4_evolve_all_returns_list(persona_memory: AgentPersonaMemory) -> None:
    evo = BotCharacterEvolution(persona_memory=persona_memory)

    persona_memory.update_from_task("bot_x", "coding", success=True)
    persona_memory.update_from_task("bot_y", "research", success=True)

    results = evo.evolve_all()

    assert len(results) >= 2, f"evolve_all returned {len(results)} items"


# ---------------------------------------------------------------------------
# TC-A5: 성공+실패+시너지 복합 후 evolve() → strengths/weaknesses 모두 존재
# ---------------------------------------------------------------------------


def test_tc_a5_cumulative_evolution(
    persona_memory: AgentPersonaMemory,
    tmp_path: Path,
) -> None:
    tracker = CollaborationTracker(
        db_path=tmp_path / "collab_a5.db",
        persona_memory=persona_memory,
    )
    evo = BotCharacterEvolution(persona_memory=persona_memory)

    # 성공 3회 → strengths
    for _ in range(3):
        persona_memory.update_from_task("bot_a", "coding", success=True)

    # 실패 3회 → weaknesses
    for _ in range(3):
        persona_memory.update_from_task(
            "bot_a", "ops", success=False, failure_category="timeout"
        )

    # 시너지 기록
    for i in range(3):
        tracker.record(
            task_id=f"t-{i}",
            participants=["bot_a", "bot_b"],
            task_type="coding",
            success=True,
        )

    result = evo.evolve("bot_a")

    assert len(result["strengths"]) > 0, "strengths가 비어 있음"
    assert len(result["weaknesses"]) > 0, "weaknesses가 비어 있음"


# ---------------------------------------------------------------------------
# TC-A6: get_evolution_summary('bot_a') → 'bot_a' 포함한 문자열
# ---------------------------------------------------------------------------


def test_tc_a6_evolution_summary_contains_agent_id(
    persona_memory: AgentPersonaMemory,
) -> None:
    evo = BotCharacterEvolution(persona_memory=persona_memory)

    persona_memory.update_from_task("bot_a", "coding", success=True)

    summary = evo.get_evolution_summary("bot_a")

    assert isinstance(summary, str), "summary가 문자열이 아님"
    assert "bot_a" in summary, f"summary에 'bot_a' 없음: {summary!r}"
