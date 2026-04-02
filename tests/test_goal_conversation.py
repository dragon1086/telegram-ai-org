"""GoalConversationEngine 테스트 (Phase 2)."""
import json
import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.context_db import ContextDB
from core.goal_conversation_engine import (
    GoalConversationEngine,
    register_parsed_okr,
)
from core.goal_tracker import GoalTracker


@pytest.fixture
def db(tmp_path):
    return ContextDB(str(tmp_path / "test.db"))


@pytest.fixture
def tracker(db):
    orch = AsyncMock()
    send = AsyncMock()
    return GoalTracker(
        context_db=db, orchestrator=orch,
        telegram_send_func=send, org_id="pm",
    )


class TestRuleBasedParsing:
    """규칙 기반 파싱 테스트 (LLM 없이)."""

    @pytest.mark.asyncio
    async def test_parse_with_number_and_date(self):
        """숫자 + 날짜 추출."""
        engine = GoalConversationEngine()
        result = await engine.parse_goal("2026-06-30까지 MAU 10만 달성")
        assert result["objective"]["title"] == "2026-06-30까지 MAU 10만 달성"
        assert result["objective"]["deadline"] == "2026-06-30"
        kr = result["key_results"][0]
        assert kr["kpi_metric"] == "mau"
        assert kr["kpi_target"] == 100000.0
        assert kr["kpi_unit"] == "만"
        assert result["needs_followup"] is False

    @pytest.mark.asyncio
    async def test_parse_with_quarter(self):
        """분기 표현 파싱."""
        engine = GoalConversationEngine()
        result = await engine.parse_goal("Q2 신규가입 3만명 달성")
        assert "06-30" in result["objective"]["deadline"]
        kr = result["key_results"][0]
        assert kr["kpi_metric"] == "signups"
        assert kr["kpi_target"] == 30000.0

    @pytest.mark.asyncio
    async def test_parse_without_number_needs_followup(self):
        """숫자 없으면 후속 질문 필요."""
        engine = GoalConversationEngine()
        result = await engine.parse_goal("매출 향상시키기")
        assert result["needs_followup"] is True
        assert len(result["followup_questions"]) > 0
        # 매출 키워드 → revenue 지표
        assert result["key_results"][0]["kpi_metric"] == "revenue"

    @pytest.mark.asyncio
    async def test_parse_without_date_needs_followup(self):
        """날짜 없으면 후속 질문 포함."""
        engine = GoalConversationEngine()
        result = await engine.parse_goal("다운로드 5만건")
        assert any("마감" in q for q in result["followup_questions"])
        assert result["key_results"][0]["kpi_metric"] == "downloads"
        assert result["key_results"][0]["kpi_target"] == 50000.0

    @pytest.mark.asyncio
    async def test_parse_retention_metric(self):
        """리텐션 지표 추론."""
        engine = GoalConversationEngine()
        result = await engine.parse_goal("2026-12-31까지 리텐션 80%")
        assert result["key_results"][0]["kpi_metric"] == "retention"
        assert result["key_results"][0]["kpi_target"] == 80.0

    @pytest.mark.asyncio
    async def test_parse_unknown_metric_fallback(self):
        """지표 추론 불가 → completion_rate + 후속 질문."""
        engine = GoalConversationEngine()
        result = await engine.parse_goal("2026-12-31까지 팀 역량 강화 100%")
        assert result["key_results"][0]["kpi_metric"] == "completion_rate"
        assert any("측정" in q for q in result["followup_questions"])


class TestLLMParsing:
    """LLM 기반 파싱 테스트."""

    @pytest.mark.asyncio
    async def test_parse_with_llm(self):
        """LLM 응답 파싱."""
        llm_response = json.dumps({
            "objective": {
                "title": "Q2 사용자 확대",
                "description": "2분기 MAU 10만 달성",
                "deadline": "2026-06-30",
            },
            "key_results": [
                {
                    "title": "신규 가입 3만",
                    "description": "소셜 마케팅",
                    "kpi_metric": "signups",
                    "kpi_target": 30000,
                    "kpi_unit": "명",
                    "deadline": "2026-06-30",
                    "weight": 0.6,
                    "initiatives": [
                        {"title": "인스타 캠페인", "description": "광고",
                         "deadline": "2026-05-31"},
                    ],
                },
                {
                    "title": "리텐션 개선",
                    "description": "D7 리텐션",
                    "kpi_metric": "retention",
                    "kpi_target": 40,
                    "kpi_unit": "%",
                    "deadline": "2026-06-30",
                    "weight": 0.4,
                    "initiatives": [],
                },
            ],
        })

        async def mock_llm(prompt):
            return f"```json\n{llm_response}\n```"

        engine = GoalConversationEngine(llm_func=mock_llm)
        result = await engine.parse_goal("이번 분기 MAU 10만 달성하자")

        assert result["objective"]["title"] == "Q2 사용자 확대"
        assert len(result["key_results"]) == 2
        assert result["key_results"][0]["weight"] == 0.6
        assert len(result["key_results"][0]["initiatives"]) == 1
        assert result["needs_followup"] is False

    @pytest.mark.asyncio
    async def test_llm_failure_fallback(self):
        """LLM 실패 → 규칙 기반 폴백."""
        async def failing_llm(prompt):
            raise RuntimeError("LLM unavailable")

        engine = GoalConversationEngine(llm_func=failing_llm)
        result = await engine.parse_goal("2026-06-30까지 MAU 10만")
        # 규칙 기반으로 정상 파싱
        assert result["objective"]["deadline"] == "2026-06-30"
        assert result["key_results"][0]["kpi_metric"] == "mau"

    @pytest.mark.asyncio
    async def test_llm_invalid_json_fallback(self):
        """LLM이 잘못된 JSON 반환 → 규칙 기반 폴백."""
        async def bad_json_llm(prompt):
            return "여기 OKR입니다: {잘못된 json"

        engine = GoalConversationEngine(llm_func=bad_json_llm)
        result = await engine.parse_goal("2026-12-31까지 매출 10억")
        assert result["key_results"][0]["kpi_metric"] == "revenue"


class TestRegisterParsedOKR:
    """register_parsed_okr 통합 테스트."""

    @pytest.mark.asyncio
    async def test_register_full_okr(self, db, tracker):
        """전체 OKR 구조 등록."""
        await db.initialize()
        parsed = {
            "objective": {
                "title": "Q2 MAU 10만",
                "description": "2분기 사용자 확대",
                "deadline": "2026-06-30",
            },
            "key_results": [
                {
                    "title": "신규 가입 3만",
                    "description": "가입자 확대",
                    "kpi_metric": "signups",
                    "kpi_target": 30000,
                    "kpi_unit": "명",
                    "deadline": "2026-06-30",
                    "weight": 0.7,
                    "initiatives": [
                        {"title": "SNS 캠페인", "description": "소셜 마케팅",
                         "deadline": "2026-05-31"},
                    ],
                },
                {
                    "title": "리텐션 40%",
                    "description": "D7 리텐션 개선",
                    "kpi_metric": "retention",
                    "kpi_target": 40,
                    "kpi_unit": "%",
                    "deadline": "2026-06-30",
                    "weight": 0.3,
                    "initiatives": [],
                },
            ],
        }
        result = await register_parsed_okr(tracker, parsed, chat_id=123)

        assert result["objective_id"].startswith("G-pm-")
        assert len(result["kr_ids"]) == 2
        assert len(result["initiative_ids"]) == 1

        # DB에서 확인
        obj = await db.get_goal(result["objective_id"])
        assert obj["goal_type"] == "objective"
        assert obj["deadline"] == "2026-06-30"

        kr1 = await db.get_goal(result["kr_ids"][0])
        assert kr1["goal_type"] == "key_result"
        assert kr1["parent_goal_id"] == result["objective_id"]
        assert kr1["kpi_target"] == 30000

        init = await db.get_goal(result["initiative_ids"][0])
        assert init["goal_type"] == "initiative"
        assert init["parent_goal_id"] == result["kr_ids"][0]

    @pytest.mark.asyncio
    async def test_end_to_end_parse_and_register(self, db, tracker):
        """자연어 → 파싱 → 등록 E2E."""
        await db.initialize()
        engine = GoalConversationEngine()
        parsed = await engine.parse_goal("2026-06-30까지 MAU 10만 달성")
        result = await register_parsed_okr(tracker, parsed, chat_id=1)

        assert result["objective_id"] is not None
        assert len(result["kr_ids"]) >= 1

        # Objective 조회
        objectives = await tracker.get_objectives()
        assert len(objectives) == 1
