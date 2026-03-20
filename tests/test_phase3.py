"""Phase 3 — 에이전트 페르소나·협업·칭찬·캐릭터 진화 테스트."""
from __future__ import annotations

import pathlib
import tempfile



# ── AgentPersonaMemory 테스트 ──────────────────────────────────────────────


def test_agent_persona_memory_update_from_task():
    """update_from_task 성공/실패 기본 동작."""
    from core.agent_persona_memory import AgentPersonaMemory

    db = pathlib.Path(tempfile.mktemp(suffix=".db"))
    try:
        apm = AgentPersonaMemory(db_path=db)

        # 성공 케이스
        apm.update_from_task("bot_a", task_type="coding", success=True)
        stats = apm.get_stats("bot_a")
        assert stats is not None
        assert stats.success_tasks == 1
        assert stats.total_tasks == 1
        assert stats.success_patterns.get("coding", 0) == 1

        # 실패 케이스
        apm.update_from_task("bot_a", task_type="coding", success=False, failure_category="timeout")
        stats = apm.get_stats("bot_a")
        assert stats.total_tasks == 2
        assert stats.failure_patterns.get("timeout", 0) == 1
    finally:
        db.unlink(missing_ok=True)


# ── synergy EMA 테스트 ────────────────────────────────────────────────────


def test_synergy_score_ema_update():
    """synergy EMA: 3번 성공 시 0.5보다 높아야 함."""
    from core.agent_persona_memory import AgentPersonaMemory

    db = pathlib.Path(tempfile.mktemp(suffix=".db"))
    try:
        apm = AgentPersonaMemory(db_path=db)

        # 초기값 확인
        initial = apm.get_synergy_score("bot_a", "bot_b")
        assert initial == 0.5

        # 3번 성공으로 EMA 업데이트
        apm.update_synergy("bot_a", "bot_b", success=True)
        apm.update_synergy("bot_a", "bot_b", success=True)
        apm.update_synergy("bot_a", "bot_b", success=True)

        score = apm.get_synergy_score("bot_a", "bot_b")
        assert score > 0.5, f"3번 성공 후 score={score}가 0.5보다 높아야 함"
    finally:
        db.unlink(missing_ok=True)


# ── recommend_team 테스트 ─────────────────────────────────────────────────


def test_recommend_team_by_task_type():
    """task_type에 성공 기록 있는 에이전트 추천."""
    from core.agent_persona_memory import AgentPersonaMemory

    db = pathlib.Path(tempfile.mktemp(suffix=".db"))
    try:
        apm = AgentPersonaMemory(db_path=db)

        # bot_a: coding 성공 2회
        apm.update_from_task("bot_a", task_type="coding", success=True)
        apm.update_from_task("bot_a", task_type="coding", success=True)

        # bot_b: design 성공 1회 (coding 없음)
        apm.update_from_task("bot_b", task_type="design", success=True)

        recommended = apm.recommend_team("coding")
        assert "bot_a" in recommended
        assert "bot_b" not in recommended
    finally:
        db.unlink(missing_ok=True)


# ── CollaborationTracker 테스트 ───────────────────────────────────────────


def test_collaboration_tracker_record_and_pairs():
    """record() 후 get_frequent_pairs() 확인."""
    from core.collaboration_tracker import CollaborationTracker

    db = pathlib.Path(tempfile.mktemp(suffix=".db"))
    try:
        ct = CollaborationTracker(db_path=db, persona_memory=None)

        # 같은 참가자 조합으로 2번 기록
        ct.record("task1", ["bot_a", "bot_b", "bot_c"], task_type="coding", success=True)
        ct.record("task2", ["bot_a", "bot_b", "bot_c"], task_type="coding", success=True)

        pairs = ct.get_frequent_pairs(min_count=2)
        assert len(pairs) > 0

        pair_keys = [p for p, _ in pairs]
        assert ("bot_a", "bot_b") in pair_keys or ("bot_b", "bot_a") in pair_keys
    finally:
        db.unlink(missing_ok=True)


def test_collaboration_graph_structure():
    """get_collaboration_graph() 양방향 포함 확인."""
    from core.collaboration_tracker import CollaborationTracker

    db = pathlib.Path(tempfile.mktemp(suffix=".db"))
    try:
        ct = CollaborationTracker(db_path=db, persona_memory=None)
        ct.record("task1", ["bot_a", "bot_b"], task_type="review", success=True)

        graph = ct.get_collaboration_graph()

        # 양방향으로 모두 존재해야 함
        assert "bot_a" in graph
        assert "bot_b" in graph
        assert "bot_b" in graph["bot_a"]
        assert "bot_a" in graph["bot_b"]
        assert graph["bot_a"]["bot_b"] == 1
        assert graph["bot_b"]["bot_a"] == 1
    finally:
        db.unlink(missing_ok=True)


# ── ShoutoutSystem 테스트 ─────────────────────────────────────────────────


def test_shoutout_give_and_retrieve():
    """give_shoutout() 후 get_received() 반환 확인."""
    from core.shoutout_system import ShoutoutSystem

    db = pathlib.Path(tempfile.mktemp(suffix=".db"))
    try:
        ss = ShoutoutSystem(db_path=db)
        shoutout = ss.give_shoutout(
            from_agent="bot_a",
            to_agent="bot_b",
            reason="훌륭한 코드 리뷰",
            task_id="task_001",
        )
        assert shoutout.id
        assert shoutout.from_agent == "bot_a"
        assert shoutout.to_agent == "bot_b"

        received = ss.get_received("bot_b")
        assert len(received) == 1
        assert received[0].reason == "훌륭한 코드 리뷰"
    finally:
        db.unlink(missing_ok=True)


def test_shoutout_auto_mvp():
    """auto_shoutout() 후 DB에 shoutout 기록 확인."""
    from core.shoutout_system import ShoutoutSystem

    db = pathlib.Path(tempfile.mktemp(suffix=".db"))
    try:
        ss = ShoutoutSystem(db_path=db)
        ss.auto_shoutout(
            task_id="task_auto",
            winner="bot_c",
            reason="최고 성능 달성",
            all_participants=["bot_a", "bot_b", "bot_c"],
        )

        received = ss.get_received("bot_c")
        assert len(received) >= 1
        assert received[0].to_agent == "bot_c"
    finally:
        db.unlink(missing_ok=True)


def test_weekly_mvp_selection():
    """give_shoutout 여러 번 후 weekly_mvp() 반환 확인."""
    from core.shoutout_system import ShoutoutSystem

    db = pathlib.Path(tempfile.mktemp(suffix=".db"))
    try:
        ss = ShoutoutSystem(db_path=db)

        # bot_b에게 3번, bot_a에게 1번 칭찬
        ss.give_shoutout("bot_a", "bot_b", "reason1")
        ss.give_shoutout("bot_c", "bot_b", "reason2")
        ss.give_shoutout("bot_d", "bot_b", "reason3")
        ss.give_shoutout("bot_b", "bot_a", "reason4")

        mvp = ss.weekly_mvp()
        assert mvp == "bot_b"
    finally:
        db.unlink(missing_ok=True)


# ── BotCharacterEvolution 테스트 ──────────────────────────────────────────


def test_bot_character_evolution_strengths():
    """성공 6회(>=5) + 성공률 100% → strengths에 task_type 포함."""
    from core.agent_persona_memory import AgentPersonaMemory
    from core.bot_character_evolution import BotCharacterEvolution

    db = pathlib.Path(tempfile.mktemp(suffix=".db"))
    try:
        apm = AgentPersonaMemory(db_path=db)
        bce = BotCharacterEvolution(persona_memory=apm)

        for _ in range(6):
            apm.update_from_task("bot_evo", task_type="coding", success=True)

        result = bce.evolve("bot_evo")
        assert "coding" in result["strengths"], (
            f"strengths={result['strengths']} — 'coding'이 포함되어야 함"
        )
    finally:
        db.unlink(missing_ok=True)


def test_bot_character_evolution_weaknesses():
    """실패 3회+ → weaknesses에 category 포함."""
    from core.agent_persona_memory import AgentPersonaMemory
    from core.bot_character_evolution import BotCharacterEvolution

    db = pathlib.Path(tempfile.mktemp(suffix=".db"))
    try:
        apm = AgentPersonaMemory(db_path=db)
        bce = BotCharacterEvolution(persona_memory=apm)

        for _ in range(3):
            apm.update_from_task(
                "bot_evo", task_type="coding", success=False, failure_category="timeout"
            )

        result = bce.evolve("bot_evo")
        assert "timeout" in result["weaknesses"], (
            f"weaknesses={result['weaknesses']} — 'timeout'이 포함되어야 함"
        )
    finally:
        db.unlink(missing_ok=True)
