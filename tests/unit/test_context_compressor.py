"""Unit tests for core/context_compressor.py (CC-01).

테스트 케이스:
  TestFeatureFlagOff  — flag=off 시 safe no-op 동작
  TestCompress        — 실제 압축 로직 (system 보존, keep_last_n, older truncation, 순서)
  TestEstimateTokens  — 토큰 추정 (flag 무관 항상 동작)
  TestSingleton       — 싱글턴 패턴 / reset_compressor()
"""
from __future__ import annotations

import os
import sys

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reload_compressor(enabled: bool):
    """ENABLE_CONTEXT_COMPRESSOR 환경변수를 설정하고 모듈을 리로드한다."""
    os.environ["ENABLE_CONTEXT_COMPRESSOR"] = "true" if enabled else "false"
    mod_name = "core.context_compressor"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    import core.context_compressor as cc
    cc.reset_compressor()
    return cc


def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content}


# ---------------------------------------------------------------------------
# TestFeatureFlagOff
# ---------------------------------------------------------------------------


class TestFeatureFlagOff:
    """ENABLE_CONTEXT_COMPRESSOR=false 시 모든 연산이 safe no-op이어야 한다."""

    def setup_method(self):
        self.cc = _reload_compressor(enabled=False)

    def test_compress_returns_original_messages(self):
        """flag=off → compress()는 원본 messages를 그대로 반환한다."""
        msgs = [_msg("user", "안녕"), _msg("assistant", "반갑습니다")]
        result = self.cc.get_compressor().compress(msgs, max_tokens=10)
        assert result is msgs, "flag=off 시 원본 리스트를 그대로 반환해야 한다"

    def test_compress_returns_empty_list_unchanged(self):
        """flag=off + 빈 리스트 → 빈 리스트 반환."""
        result = self.cc.get_compressor().compress([], max_tokens=100)
        assert result == []

    def test_estimate_tokens_works_regardless_of_flag(self):
        """estimate_tokens()는 flag=off여도 정상 동작한다."""
        tokens = self.cc.get_compressor().estimate_tokens("hello world")
        assert isinstance(tokens, int)
        assert tokens > 0


# ---------------------------------------------------------------------------
# TestCompress
# ---------------------------------------------------------------------------


class TestCompress:
    """ENABLE_CONTEXT_COMPRESSOR=true 실제 압축 로직 검증."""

    def setup_method(self):
        self.cc = _reload_compressor(enabled=True)
        self.reg = self.cc.get_compressor()

    def test_empty_messages_returns_empty(self):
        """빈 messages → 빈 리스트 반환."""
        assert self.reg.compress([], max_tokens=100) == []

    def test_max_tokens_zero_returns_empty(self):
        """max_tokens=0 → 빈 리스트 반환."""
        msgs = [_msg("user", "테스트")]
        result = self.reg.compress(msgs, max_tokens=0)
        assert result == []

    def test_sufficient_budget_preserves_all_messages(self):
        """토큰 예산이 충분하면 모든 메시지가 보존된다."""
        msgs = [
            _msg("user", "첫 번째"),
            _msg("assistant", "답변 1"),
            _msg("user", "두 번째"),
        ]
        result = self.reg.compress(msgs, max_tokens=10000)
        assert len(result) == 3

    def test_system_message_always_preserved(self):
        """system 메시지는 max_tokens가 작아도 항상 보존된다."""
        msgs = [
            _msg("system", "시스템 지시사항"),
            _msg("user", "msg1"),
            _msg("user", "msg2"),
            _msg("user", "msg3"),
            _msg("user", "msg4"),
            _msg("user", "msg5"),
        ]
        result = self.reg.compress(msgs, max_tokens=5, keep_last_n=2)
        roles = [m["role"] for m in result]
        assert "system" in roles, "system 메시지는 항상 보존되어야 한다"

    def test_keep_last_n_always_preserved(self):
        """keep_last_n 개의 마지막 non-system 메시지는 항상 보존된다."""
        msgs = [
            _msg("user", "old1"),
            _msg("user", "old2"),
            _msg("user", "old3"),
            _msg("user", "keep_me_1"),
            _msg("user", "keep_me_2"),
        ]
        result = self.reg.compress(msgs, max_tokens=5, keep_last_n=2)
        contents = [m["content"] for m in result]
        assert "keep_me_1" in contents, "마지막 2개 중 첫 번째가 보존되어야 함"
        assert "keep_me_2" in contents, "마지막 2개 중 두 번째가 보존되어야 함"

    def test_older_messages_truncated_when_over_budget(self):
        """예산 초과 시 오래된 메시지가 제거된다."""
        # 각 메시지가 약 1~2 토큰인 짧은 메시지 구성
        msgs = [
            _msg("user", "A"),  # older
            _msg("user", "B"),  # older
            _msg("user", "C"),  # keep_last
            _msg("user", "D"),  # keep_last
        ]
        # keep_last=2이면 C, D는 보존. A, B는 예산에 따라 제거 가능
        # max_tokens=2로 A,B 진입 불가 수준으로 설정
        result = self.reg.compress(msgs, max_tokens=2, keep_last_n=2)
        contents = [m["content"] for m in result]
        assert "C" in contents
        assert "D" in contents
        # A, B는 예산 부족으로 일부/전체 제거됨
        assert "A" not in contents or "B" not in contents

    def test_result_maintains_chronological_order(self):
        """압축 결과는 원래 시간 순서를 유지해야 한다."""
        msgs = [
            _msg("system", "sys"),
            _msg("user", "u1"),
            _msg("assistant", "a1"),
            _msg("user", "u2"),
            _msg("assistant", "a2"),
        ]
        result = self.reg.compress(msgs, max_tokens=10000)
        # system이 먼저, 이후 시간순
        assert result[0]["role"] == "system"
        assert result[1]["content"] == "u1"
        assert result[-1]["content"] == "a2"

    def test_keep_last_n_larger_than_messages(self):
        """keep_last_n이 전체 non-system 수보다 크면 모두 보존된다."""
        msgs = [_msg("user", "only_one")]
        result = self.reg.compress(msgs, max_tokens=10000, keep_last_n=10)
        assert len(result) == 1
        assert result[0]["content"] == "only_one"

    def test_only_system_messages(self):
        """non-system 메시지 없이 system만 있으면 그대로 반환된다."""
        msgs = [_msg("system", "지시1"), _msg("system", "지시2")]
        result = self.reg.compress(msgs, max_tokens=10000)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# TestEstimateTokens
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    """estimate_tokens() — feature flag와 무관하게 항상 동작."""

    def setup_method(self):
        self.cc = _reload_compressor(enabled=True)
        self.reg = self.cc.get_compressor()

    def test_english_text_returns_positive(self):
        """영문 텍스트는 양수 토큰 수를 반환한다."""
        tokens = self.reg.estimate_tokens("hello world this is a test")
        assert isinstance(tokens, int)
        assert tokens > 0

    def test_empty_string_returns_zero(self):
        """빈 문자열은 0을 반환한다."""
        assert self.reg.estimate_tokens("") == 0

    def test_korean_text_returns_positive(self):
        """한글 텍스트는 양수 토큰 수를 반환한다."""
        tokens = self.reg.estimate_tokens("안녕하세요 테스트입니다")
        assert isinstance(tokens, int)
        assert tokens > 0

    def test_mixed_text_returns_positive(self):
        """한글+영문 혼합 텍스트도 양수 토큰 수를 반환한다."""
        tokens = self.reg.estimate_tokens("Hello 안녕 world 테스트")
        assert tokens > 0

    def test_longer_text_has_more_tokens(self):
        """더 긴 텍스트는 더 많은 토큰 수를 가진다."""
        short = self.reg.estimate_tokens("hi")
        long_ = self.reg.estimate_tokens("hi " * 50)
        assert long_ > short


# ---------------------------------------------------------------------------
# TestSingleton
# ---------------------------------------------------------------------------


class TestSingleton:
    """싱글턴 패턴 및 reset_compressor() 검증."""

    def setup_method(self):
        self.cc = _reload_compressor(enabled=True)

    def test_get_compressor_returns_same_instance(self):
        """get_compressor() 여러 번 호출 시 동일 인스턴스를 반환한다."""
        c1 = self.cc.get_compressor()
        c2 = self.cc.get_compressor()
        assert c1 is c2

    def test_reset_compressor_returns_new_instance(self):
        """reset_compressor() 호출 후 get_compressor()는 새 인스턴스를 반환한다."""
        c1 = self.cc.get_compressor()
        self.cc.reset_compressor()
        c2 = self.cc.get_compressor()
        assert c1 is not c2

    def test_repr_contains_enabled_state(self):
        """__repr__에 enabled 상태가 포함된다."""
        rep = repr(self.cc.get_compressor())
        assert "ContextCompressor" in rep
        assert "enabled=" in rep
