from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dataclasses import dataclass, field
from unittest.mock import MagicMock

from core.telegram_formatting import _CONTINUATION, split_message


def test_split_message_prefers_paragraph_boundaries() -> None:
    text = (
        "첫 문단입니다.\n\n"
        "둘째 문단은 조금 더 길게 작성해서 문단 경계에서 잘 끊기는지 확인합니다.\n\n"
        "셋째 문단도 이어집니다."
    )

    chunks = split_message(text, 60)

    assert len(chunks) >= 2
    # 중간 청크에는 _CONTINUATION 접미사가 붙음
    assert "확인합니다." in chunks[0]
    assert chunks[1].startswith("셋째 문단")


def test_split_message_falls_back_when_no_good_breakpoint() -> None:
    text = "A" * 120

    chunks = split_message(text, 50)

    # effective_len = 50 - len(_CONTINUATION), 마지막 청크는 접미사 없음
    eff = 50 - len(_CONTINUATION)
    last = 120 - eff * 2
    assert chunks == ["A" * eff + _CONTINUATION, "A" * eff + _CONTINUATION, "A" * last]


# ── Change 3: _format_team_header 팀 구성 헤더 ──────────────────────────────

def _make_team_config(agent_names: list[str]):
    """테스트용 최소 TeamConfig 구사체를 생성한다."""
    @dataclass
    class _FakePersona:
        name: str

    @dataclass
    class _FakeTeamConfig:
        agents: list = field(default_factory=list)

    return _FakeTeamConfig(agents=[_FakePersona(name=n) for n in agent_names])


def test_format_team_header_contains_team_tag() -> None:
    """_format_team_header 결과 첫 줄에 [TEAM:...] 태그가 있어야 한다."""
    # TelegramRelay의 static method만 테스트 — 클래스 인스턴스 불필요
    from core.telegram_relay import TelegramRelay

    config = _make_team_config(["engineering-senior-developer", "testing-api-tester"])
    header = TelegramRelay._format_team_header(config)

    first_line = header.splitlines()[0]
    assert first_line.startswith("[TEAM:")
    assert "engineering-senior-developer" in first_line
    assert "testing-api-tester" in first_line


def test_format_team_header_empty_agents_returns_empty() -> None:
    """에이전트 없는 team_config이면 빈 문자열을 반환해야 한다."""
    from core.telegram_relay import TelegramRelay

    config = _make_team_config([])
    assert TelegramRelay._format_team_header(config) == ""


def test_format_team_header_none_returns_empty() -> None:
    """team_config이 None이면 빈 문자열을 반환해야 한다."""
    from core.telegram_relay import TelegramRelay

    assert TelegramRelay._format_team_header(None) == ""


def test_format_team_header_counts_duplicates() -> None:
    """같은 에이전트가 2회 등장하면 ×2 표기가 있어야 한다."""
    from core.telegram_relay import TelegramRelay

    config = _make_team_config(["executor", "executor", "analyst"])
    header = TelegramRelay._format_team_header(config)

    assert "×2" in header
    assert "executor" in header
    assert "analyst" in header
