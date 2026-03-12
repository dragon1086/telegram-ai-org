"""NLClassifier 단위 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.nl_classifier import NLClassifier, Intent


@pytest.fixture
def classifier():
    return NLClassifier()


class TestGreeting:
    def test_korean_greeting(self, classifier):
        result = classifier.classify("안녕")
        assert result.intent == Intent.GREETING

    def test_english_greeting(self, classifier):
        result = classifier.classify("hi")
        assert result.intent == Intent.GREETING

    def test_shorthand_greeting(self, classifier):
        result = classifier.classify("ㅎㅇ")
        assert result.intent == Intent.GREETING

    def test_long_text_with_greeting_not_greeting(self, classifier):
        result = classifier.classify("안녕하세요 오늘 날씨가 좋네요 산책갈까요")
        assert result.intent != Intent.GREETING


class TestCommandIntents:
    def test_status_korean(self, classifier):
        result = classifier.classify("상태")
        assert result.intent == Intent.STATUS

    def test_status_english(self, classifier):
        result = classifier.classify("status")
        assert result.intent == Intent.STATUS

    def test_approve_korean(self, classifier):
        result = classifier.classify("승인")
        assert result.intent == Intent.APPROVE

    def test_approve_shorthand(self, classifier):
        result = classifier.classify("ㅇㅋ")
        assert result.intent == Intent.APPROVE

    def test_reject_korean(self, classifier):
        result = classifier.classify("반려")
        assert result.intent == Intent.REJECT

    def test_cancel_korean(self, classifier):
        result = classifier.classify("취소")
        assert result.intent == Intent.CANCEL

    def test_cancel_english(self, classifier):
        result = classifier.classify("cancel")
        assert result.intent == Intent.CANCEL


class TestTask:
    def test_action_keyword(self, classifier):
        result = classifier.classify("JWT 로그인 라이브러리 구현해줘")
        assert result.intent == Intent.TASK

    def test_long_text_is_task(self, classifier):
        result = classifier.classify("이 프로젝트의 아키텍처를 분석하고 개선점을 찾아줘")
        assert result.intent == Intent.TASK


class TestEdgeCases:
    def test_approve_keyword_with_action_is_task(self, classifier):
        result = classifier.classify("승인 관련 기능 구현해줘")
        assert result.intent == Intent.TASK

    def test_status_keyword_with_action_is_task(self, classifier):
        result = classifier.classify("상태 관리 시스템 만들어줘")
        assert result.intent == Intent.TASK


class TestChat:
    def test_short_non_matching_is_chat(self, classifier):
        result = classifier.classify("ㅋㅋ")
        assert result.intent == Intent.CHAT

    def test_emoji_only_is_chat(self, classifier):
        result = classifier.classify("thumbsup")
        assert result.intent == Intent.CHAT


class TestNeedsLlm:
    def test_action_keyword_triggers_task(self, classifier):
        result = classifier.classify("오늘 회의에서 나온 내용을 정리해주면 좋겠는데")
        assert result.intent == Intent.TASK
