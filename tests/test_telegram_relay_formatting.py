from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.telegram_formatting import split_message


def test_split_message_prefers_paragraph_boundaries() -> None:
    text = (
        "첫 문단입니다.\n\n"
        "둘째 문단은 조금 더 길게 작성해서 문단 경계에서 잘 끊기는지 확인합니다.\n\n"
        "셋째 문단도 이어집니다."
    )

    chunks = split_message(text, 60)

    assert len(chunks) >= 2
    assert chunks[0].endswith("확인합니다.")
    assert chunks[1].startswith("셋째 문단")


def test_split_message_falls_back_when_no_good_breakpoint() -> None:
    text = "A" * 120

    chunks = split_message(text, 50)

    assert chunks == ["A" * 50, "A" * 50, "A" * 20]
