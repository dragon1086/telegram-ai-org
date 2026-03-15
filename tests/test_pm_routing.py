"""LLMRouter 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.llm_router import LLMRouter


SAMPLE_WORKERS = [
    {"name": "cokac", "engine": "claude-code", "description": "코딩, 구현, 리팩토링 전문"},
    {"name": "researcher", "engine": "codex", "description": "분석, 리서치, 데이터 처리"},
]


class _FakeDecisionClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls = 0

    async def complete(self, prompt: str, *, system_prompt: str = "", workdir: str | None = None) -> str:
        self.calls += 1
        return self.response


def _make_router() -> LLMRouter:
    with patch("core.llm_router.AsyncOpenAI"):
        return LLMRouter()


def _mock_response(content: str):
    choice = MagicMock()
    choice.message.content = content
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ---------------------------------------------------------------------------
# route_simple — 올바른 워커 핸들 반환
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_route_simple_returns_worker_handles():
    router = _make_router()
    payload = '{"analysis":"ok","assignments":[{"worker_name":"cokac","instruction":"build","priority":"high"}],"completion_criteria":"done"}'
    router.client.chat.completions.create = AsyncMock(return_value=_mock_response(payload))

    result = await router.route_simple("파이썬 코드 작성해줘", SAMPLE_WORKERS)

    assert result == ["cokac"]


@pytest.mark.asyncio
async def test_route_simple_multiple_workers():
    router = _make_router()
    payload = (
        '{"analysis":"both","assignments":['
        '{"worker_name":"cokac","instruction":"code","priority":"high"},'
        '{"worker_name":"researcher","instruction":"research","priority":"low"}],'
        '"completion_criteria":"done"}'
    )
    router.client.chat.completions.create = AsyncMock(return_value=_mock_response(payload))

    result = await router.route_simple("코드 작성 + 리서치", SAMPLE_WORKERS)

    assert result == ["cokac", "researcher"]


# ---------------------------------------------------------------------------
# LLM 실패 → 빈 assignments 반환 (route_simple은 빈 리스트)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_route_simple_llm_exception_raises():
    router = _make_router()
    router.client.chat.completions.create = AsyncMock(side_effect=Exception("API error"))

    with pytest.raises(Exception, match="API error"):
        await router.route_simple("어떤 작업", SAMPLE_WORKERS)


# ---------------------------------------------------------------------------
# 워커 없을 때 빈 리스트 반환 (LLM 호출 없이)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_route_simple_no_workers_returns_empty():
    router = _make_router()
    router.client.chat.completions.create = AsyncMock()  # 호출되면 안 됨

    result = await router.route_simple("뭔가 해줘", [])

    assert result == []
    router.client.chat.completions.create.assert_not_called()


@pytest.mark.asyncio
async def test_route_simple_prefers_decision_client():
    payload = '{"analysis":"ok","assignments":[{"worker_name":"researcher","instruction":"research","priority":"high"}],"completion_criteria":"done"}'
    client = _FakeDecisionClient(payload)
    router = LLMRouter(decision_client=client)

    result = await router.route_simple("리서치 해줘", SAMPLE_WORKERS)

    assert result == ["researcher"]
    assert client.calls == 1
