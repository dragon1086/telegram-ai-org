from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.confidence_scorer import ConfidenceScorer, _decision_clients
from core.pm_identity import PMIdentity


class _FakeDecisionClient:
    async def complete(self, prompt: str, *, system_prompt: str = "", workdir: str | None = None) -> str:
        return "8"


@pytest.mark.asyncio
async def test_confidence_scorer_uses_org_decision_client(monkeypatch) -> None:
    scorer = ConfidenceScorer()
    identity = PMIdentity("global")
    identity._data = {"org_id": "global", "specialties": ["개발", "코딩"]}
    _decision_clients.clear()
    _decision_clients["global"] = _FakeDecisionClient()  # type: ignore[assignment]

    score = await scorer.score("코드 구현을 고쳐줘", identity)

    assert score == 8
