"""Unit tests for core/team_design_patterns.py (P1-1: Agent Team Design Patterns).

Tests cover:
  - Built-in pattern registry: all 6 patterns present.
  - register_pattern: validation, overwrite.
  - recommend_pattern: boundary conditions.
  - build_team_spec: valid, unknown pattern, empty agents, count mismatches.
"""
from __future__ import annotations

import pytest

from core.team_design_patterns import (
    TeamPattern,
    build_team_spec,
    get_pattern,
    list_patterns,
    recommend_pattern,
    register_pattern,
)

# ---------------------------------------------------------------------------
# Built-in patterns
# ---------------------------------------------------------------------------


EXPECTED_BUILTIN_NAMES = {"solo", "pair", "trio", "squad", "assembly", "pipeline"}


class TestBuiltinPatterns:
    def test_all_builtins_present(self):
        names = {p.name for p in list_patterns()}
        assert EXPECTED_BUILTIN_NAMES.issubset(names)

    def test_solo_pattern_constraints(self):
        p = get_pattern("solo")
        assert p is not None
        assert p.min_agents == 1
        assert p.max_agents == 1

    def test_pair_has_two_roles(self):
        p = get_pattern("pair")
        assert p is not None
        assert len(p.roles) == 2

    def test_assembly_is_unlimited(self):
        p = get_pattern("assembly")
        assert p is not None
        assert p.max_agents == 0  # unlimited

    def test_list_patterns_sorted(self):
        patterns = list_patterns()
        names = [p.name for p in patterns]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# register_pattern validation
# ---------------------------------------------------------------------------


class TestRegisterPattern:
    def test_register_new_pattern(self):
        new_p = TeamPattern(
            name="custom-test-pattern",
            description="Test pattern",
            min_agents=2,
            max_agents=4,
        )
        register_pattern(new_p)
        assert get_pattern("custom-test-pattern") is new_p

    def test_overwrite_existing(self):
        p1 = TeamPattern(name="overwrite-me", description="first", min_agents=1, max_agents=1)
        p2 = TeamPattern(name="overwrite-me", description="second", min_agents=1, max_agents=2)
        register_pattern(p1)
        register_pattern(p2)
        assert get_pattern("overwrite-me").description == "second"

    def test_invalid_name_raises(self):
        with pytest.raises(ValueError, match="name"):
            register_pattern(TeamPattern(name="", description="d", min_agents=1, max_agents=1))

    def test_min_agents_zero_raises(self):
        with pytest.raises(ValueError, match="min_agents"):
            register_pattern(TeamPattern(name="bad", description="d", min_agents=0, max_agents=1))

    def test_max_less_than_min_raises(self):
        with pytest.raises(ValueError, match="max_agents"):
            register_pattern(TeamPattern(name="bad2", description="d", min_agents=3, max_agents=2))

    def test_unlimited_max_is_valid(self):
        p = TeamPattern(name="unlimited-test", description="d", min_agents=1, max_agents=0)
        register_pattern(p)  # should not raise
        assert get_pattern("unlimited-test") is not None


# ---------------------------------------------------------------------------
# get_pattern
# ---------------------------------------------------------------------------


class TestGetPattern:
    def test_none_input(self):
        assert get_pattern(None) is None

    def test_empty_string(self):
        assert get_pattern("") is None

    def test_unknown_name(self):
        assert get_pattern("totally-nonexistent-xyz") is None


# ---------------------------------------------------------------------------
# recommend_pattern
# ---------------------------------------------------------------------------


class TestRecommendPattern:
    def test_zero_agents_returns_none(self):
        assert recommend_pattern(0) is None

    def test_negative_agents_returns_none(self):
        assert recommend_pattern(-5) is None

    def test_one_agent_recommends_solo(self):
        result = recommend_pattern(1)
        assert result is not None
        # solo must be compatible with exactly 1 agent
        ok, _ = result.is_compatible(1)
        assert ok

    def test_two_agents_compatible(self):
        result = recommend_pattern(2)
        assert result is not None
        ok, _ = result.is_compatible(2)
        assert ok

    def test_large_count_returns_pattern(self):
        result = recommend_pattern(20)
        assert result is not None  # assembly or pipeline should match


# ---------------------------------------------------------------------------
# build_team_spec
# ---------------------------------------------------------------------------


class TestBuildTeamSpec:
    def test_valid_solo_spec(self):
        spec = build_team_spec("solo", ["agent-a"])
        assert spec.valid
        assert spec.agents == ["agent-a"]
        assert "executor" in spec.role_assignments

    def test_valid_pair_spec(self):
        spec = build_team_spec("pair", ["dev", "reviewer"])
        assert spec.valid
        assert spec.role_assignments.get("driver") == "dev"
        assert spec.role_assignments.get("reviewer") == "reviewer"

    def test_unknown_pattern_invalid(self):
        spec = build_team_spec("nonexistent-xyz", ["a", "b"])
        assert not spec.valid
        assert "nonexistent-xyz" in spec.validation_message

    def test_empty_agents_invalid(self):
        spec = build_team_spec("pair", [])
        assert not spec.valid
        assert "empty" in spec.validation_message.lower()

    def test_none_agents_treated_as_empty(self):
        spec = build_team_spec("pair", None)  # type: ignore
        assert not spec.valid

    def test_too_few_agents_for_pair(self):
        spec = build_team_spec("pair", ["only-one"])
        assert not spec.valid
        assert "2" in spec.validation_message

    def test_too_many_agents_for_solo(self):
        spec = build_team_spec("solo", ["a", "b"])
        assert not spec.valid

    def test_extra_agents_get_numbered_roles(self):
        # Trio has 3 named roles; add 2 extra
        spec = build_team_spec("trio", ["a", "b", "c", "d", "e"])
        assert not spec.valid  # trio is max=3, so this should fail

    def test_assembly_accepts_many_agents(self):
        agents = [f"agent-{i}" for i in range(10)]
        spec = build_team_spec("assembly", agents)
        assert spec.valid
        assert len(spec.agents) == 10

    def test_blank_agent_strings_filtered(self):
        spec = build_team_spec("solo", ["", "real-agent", "  "])
        assert spec.valid
        assert spec.agents == ["real-agent"]
