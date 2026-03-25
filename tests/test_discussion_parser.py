"""Discussion Parser 단위 테스트 — Task 2.3."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.discussion_parser import (
    is_discussion_message,
    parse_discussion_tags,
    strip_discussion_tags,
)


class TestParseDiscussionTags:

    def test_parse_propose(self):
        text = "[PROPOSE:아키텍처|마이크로서비스 구조를 제안합니다]"
        tags = parse_discussion_tags(text)
        assert len(tags) == 1
        assert tags[0].msg_type == "PROPOSE"
        assert tags[0].topic == "아키텍처"
        assert tags[0].content == "마이크로서비스 구조를 제안합니다"

    def test_parse_counter(self):
        text = "[COUNTER:아키텍처|모놀리스가 더 적합합니다. 팀 규모가 작기 때문.]"
        tags = parse_discussion_tags(text)
        assert len(tags) == 1
        assert tags[0].msg_type == "COUNTER"
        assert "모놀리스" in tags[0].content

    def test_parse_opinion(self):
        text = "[OPINION:배포전략|CI/CD 파이프라인 우선 구축 권장]"
        tags = parse_discussion_tags(text)
        assert len(tags) == 1
        assert tags[0].msg_type == "OPINION"
        assert tags[0].topic == "배포전략"

    def test_parse_revise(self):
        text = "[REVISE:아키텍처|하이브리드 접근: 코어는 모놀리스, 비동기는 마이크로서비스]"
        tags = parse_discussion_tags(text)
        assert len(tags) == 1
        assert tags[0].msg_type == "REVISE"

    def test_parse_decision(self):
        text = "[DECISION:아키텍처|하이브리드 구조로 최종 결정]"
        tags = parse_discussion_tags(text)
        assert len(tags) == 1
        assert tags[0].msg_type == "DECISION"

    def test_parse_multiple_tags(self):
        text = (
            "[PROPOSE:UI|React 사용] 그리고 [COUNTER:UI|Vue가 더 가볍습니다]"
        )
        tags = parse_discussion_tags(text)
        assert len(tags) == 2
        assert tags[0].msg_type == "PROPOSE"
        assert tags[1].msg_type == "COUNTER"

    def test_no_discussion_tags(self):
        text = "일반 메시지입니다. [COLLAB:task] 형식은 무시."
        tags = parse_discussion_tags(text)
        assert len(tags) == 0

    def test_invalid_msg_type_ignored(self):
        text = "[INVALID:topic|content]"
        tags = parse_discussion_tags(text)
        assert len(tags) == 0

    def test_multiline_content(self):
        text = "[PROPOSE:DB설계|1. users 테이블\n2. orders 테이블\n3. products 테이블]"
        tags = parse_discussion_tags(text)
        assert len(tags) == 1
        assert "users" in tags[0].content
        assert "products" in tags[0].content


class TestIsDiscussionMessage:

    def test_true_for_discussion(self):
        assert is_discussion_message("[PROPOSE:topic|content]") is True

    def test_false_for_normal(self):
        assert is_discussion_message("일반 메시지") is False

    def test_false_for_collab(self):
        assert is_discussion_message("[COLLAB:task|context]") is False


class TestStripDiscussionTags:

    def test_strip_single(self):
        text = "시작 [PROPOSE:topic|content] 끝"
        result = strip_discussion_tags(text)
        assert result == "시작  끝"

    def test_strip_multiple(self):
        text = "[PROPOSE:a|b] 중간 [COUNTER:c|d]"
        result = strip_discussion_tags(text)
        assert result == "중간"

    def test_strip_none(self):
        text = "토론 태그 없음"
        result = strip_discussion_tags(text)
        assert result == "토론 태그 없음"
