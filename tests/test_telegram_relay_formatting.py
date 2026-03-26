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


def _make_relay_stub():
    """_format_team_header 호출에 필요한 최소 stub 인스턴스를 반환한다.

    _format_team_header는 인스턴스 메서드이므로 self._team_builder가 있는 stub이 필요하다.
    """
    from core.dynamic_team_builder import DynamicTeamBuilder
    from core.telegram_relay import TelegramRelay
    stub = MagicMock()
    stub._team_builder = DynamicTeamBuilder()
    stub._format_team_header = TelegramRelay._format_team_header.__get__(stub, type(stub))
    return stub


def test_format_team_header_contains_team_tag() -> None:
    """_format_team_header 결과 첫 줄에 [TEAM:...] 태그가 있어야 한다."""
    stub = _make_relay_stub()
    # 실제 페르소나명은 이름 해소 없이 그대로 유지되어야 한다
    config = _make_team_config(["engineering-senior-developer", "testing-api-tester"])
    header = stub._format_team_header(config)

    first_line = header.splitlines()[0]
    assert first_line.startswith("[TEAM:")
    assert "engineering-senior-developer" in first_line
    assert "testing-api-tester" in first_line


def test_format_team_header_empty_agents_returns_empty() -> None:
    """에이전트 없는 team_config이면 빈 문자열을 반환해야 한다."""
    stub = _make_relay_stub()
    config = _make_team_config([])
    assert stub._format_team_header(config) == ""


def test_format_team_header_none_returns_empty() -> None:
    """team_config이 None이면 빈 문자열을 반환해야 한다."""
    stub = _make_relay_stub()
    assert stub._format_team_header(None) == ""


def test_format_team_header_counts_duplicates() -> None:
    """추상 역할명(executor)이 실제 페르소나명으로 해소되어 ×2 표기가 있어야 한다."""
    stub = _make_relay_stub()
    config = _make_team_config(["executor", "executor", "analyst"])
    header = stub._format_team_header(config)

    assert "×2" in header
    # executor → engineering-senior-developer 로 해소되어야 함
    assert "engineering-senior-developer" in header
