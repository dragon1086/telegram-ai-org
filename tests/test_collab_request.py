from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.collab_request import (
    is_placeholder_collab,
    make_collab_request_v2,
    parse_collab_request,
)


def test_collab_request_v2_roundtrip() -> None:
    text = make_collab_request_v2(
        "디자인 리뷰 필요",
        "aiorg_engineering_bot",
        context="로그인 화면 개선",
        requester_mention="@rocky",
        from_org_mention="@aiorg_engineering_bot",
        target_mentions=["@aiorg_design_bot"],
    )
    parsed = parse_collab_request(text)

    assert parsed["from_org"] == "aiorg_engineering_bot"
    assert parsed["task"] == "디자인 리뷰 필요"
    assert parsed["context"] == "로그인 화면 개선"
    assert parsed["requester_mention"] == "@rocky"
    assert parsed["from_org_mention"] == "@aiorg_engineering_bot"
    assert parsed["target_mentions"] == ["@aiorg_design_bot"]


def test_placeholder_collab_examples_are_ignored() -> None:
    assert is_placeholder_collab("구체적 작업 설명", "현재 작업 요약") is True
    assert is_placeholder_collab("출시 홍보 카피 3개 필요", "Python JWT 로그인 라이브러리 v1.0, B2B 타겟") is True
    assert is_placeholder_collab("디자인 리뷰 필요", "로그인 화면 개선") is False
