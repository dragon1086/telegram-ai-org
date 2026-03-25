from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

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
