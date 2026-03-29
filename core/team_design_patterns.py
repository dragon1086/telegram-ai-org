"""Team Design Patterns — structured agent team composition patterns.

Inspired by harness's 6 team design patterns (solo, pair, trio, etc.).
Provides a pattern registry with validation, complementing the existing
dynamic_team_builder.py without modifying it.

Design notes:
  - Additive only — dynamic_team_builder.py is not touched.
  - Pattern registry is a module-level singleton dict; no other global state.
  - All patterns are validated before registration.
  - Type hints throughout.

Self-review:
  ① Logic: get_pattern() returns patterns by name; build_team_spec() validates
     agent counts against min/max constraints — correct.
  ② Edge cases: unknown pattern name, empty agent list, too few/many agents.
  ③ Compat: dynamic_team_builder.py unchanged; new callers can opt-in.
  ④ Global state: only _pattern_registry dict in this module.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------


@dataclass
class TeamPattern:
    """Describes an agent team composition pattern.

    Attributes:
        name: Short identifier (e.g. "solo", "pair").
        description: Human-readable description.
        min_agents: Minimum agent count required.
        max_agents: Maximum agent count allowed (0 = unlimited).
        roles: Suggested role labels (e.g. ["driver", "reviewer"]).
        use_cases: Typical scenarios where this pattern fits.
    """

    name: str
    description: str
    min_agents: int
    max_agents: int  # 0 = unlimited
    roles: List[str] = field(default_factory=list)
    use_cases: List[str] = field(default_factory=list)

    def is_compatible(self, agent_count: int) -> Tuple[bool, str]:
        """Check whether *agent_count* satisfies this pattern's constraints.

        Returns:
            (is_ok: bool, reason: str)
        """
        if agent_count < self.min_agents:
            return False, (
                f"Pattern '{self.name}' requires at least {self.min_agents} agents, "
                f"but got {agent_count}."
            )
        if self.max_agents != 0 and agent_count > self.max_agents:
            return False, (
                f"Pattern '{self.name}' allows at most {self.max_agents} agents, "
                f"but got {agent_count}."
            )
        return True, ""


# ---------------------------------------------------------------------------
# Built-in patterns (mirrors harness 6-pattern taxonomy)
# ---------------------------------------------------------------------------

_BUILTIN_PATTERNS: List[TeamPattern] = [
    TeamPattern(
        name="solo",
        description="Single agent handles the entire task independently.",
        min_agents=1,
        max_agents=1,
        roles=["executor"],
        use_cases=["simple tasks", "quick queries", "single-domain work"],
    ),
    TeamPattern(
        name="pair",
        description="Two agents collaborate: a driver and a reviewer.",
        min_agents=2,
        max_agents=2,
        roles=["driver", "reviewer"],
        use_cases=["code review", "document drafting + feedback", "two-step validation"],
    ),
    TeamPattern(
        name="trio",
        description="Three agents: proposer, critic, synthesiser.",
        min_agents=3,
        max_agents=3,
        roles=["proposer", "critic", "synthesiser"],
        use_cases=["brainstorming", "debate-and-conclude", "multi-angle analysis"],
    ),
    TeamPattern(
        name="squad",
        description="4–6 agents split by domain expertise.",
        min_agents=4,
        max_agents=6,
        roles=["lead", "domain-expert", "domain-expert", "integrator"],
        use_cases=["cross-functional projects", "large feature development", "weekly reviews"],
    ),
    TeamPattern(
        name="assembly",
        description="7+ agents organised hierarchically with a coordinator.",
        min_agents=7,
        max_agents=0,  # unlimited
        roles=["coordinator", "sub-lead", "executor", "executor", "executor", "reporter"],
        use_cases=["org-wide initiatives", "multi-phase projects", "all-hands exercises"],
    ),
    TeamPattern(
        name="pipeline",
        description="Agents arranged as a sequential processing chain.",
        min_agents=2,
        max_agents=0,  # unlimited
        roles=["stage-1", "stage-2", "stage-N"],
        use_cases=["ETL workflows", "staged content generation", "multi-pass refinement"],
    ),
]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_pattern_registry: Dict[str, TeamPattern] = {p.name: p for p in _BUILTIN_PATTERNS}


def register_pattern(pattern: TeamPattern) -> None:
    """Add or replace a pattern in the registry.

    Args:
        pattern: The TeamPattern to register.

    Raises:
        ValueError: If the pattern fails basic validation.
    """
    if not pattern.name or not isinstance(pattern.name, str):
        raise ValueError("TeamPattern.name must be a non-empty string")
    if pattern.min_agents < 1:
        raise ValueError(f"TeamPattern.min_agents must be >= 1, got {pattern.min_agents}")
    if pattern.max_agents != 0 and pattern.max_agents < pattern.min_agents:
        raise ValueError(
            f"TeamPattern.max_agents ({pattern.max_agents}) must be >= min_agents "
            f"({pattern.min_agents}) or 0 (unlimited)"
        )
    if pattern.name in _pattern_registry:
        logger.warning("team_design_patterns: overwriting existing pattern '%s'", pattern.name)
    _pattern_registry[pattern.name] = pattern
    logger.debug("team_design_patterns: registered pattern '%s'", pattern.name)


def get_pattern(name: str) -> Optional[TeamPattern]:
    """Return the pattern for *name*, or None if not found."""
    if not name:
        return None
    return _pattern_registry.get(name)


def list_patterns() -> List[TeamPattern]:
    """Return all registered patterns, sorted by name."""
    return sorted(_pattern_registry.values(), key=lambda p: p.name)


def recommend_pattern(agent_count: int) -> Optional[TeamPattern]:
    """Suggest the best-fit pattern for a given agent count.

    Args:
        agent_count: Number of agents available.

    Returns:
        The most suitable TeamPattern, or None if agent_count < 1.

    Edge cases:
        - agent_count <= 0 → returns None.
        - Multiple compatible patterns → returns the first by alphabetical order.
    """
    if agent_count < 1:
        logger.debug("recommend_pattern: agent_count=%d < 1; returning None", agent_count)
        return None

    compatible = [
        p for p in list_patterns()
        if p.is_compatible(agent_count)[0]
    ]
    if not compatible:
        logger.debug("recommend_pattern: no pattern compatible with %d agents", agent_count)
        return None
    return compatible[0]


# ---------------------------------------------------------------------------
# Team spec builder
# ---------------------------------------------------------------------------


@dataclass
class TeamSpec:
    """A concrete team specification built from a pattern + agent list.

    Attributes:
        pattern: The design pattern used.
        agents: Ordered list of agent identifiers.
        role_assignments: Maps role label → agent identifier (best-effort).
        valid: Whether the spec passed pattern validation.
        validation_message: Human-readable validation result.
    """

    pattern: TeamPattern
    agents: List[str]
    role_assignments: Dict[str, str] = field(default_factory=dict)
    valid: bool = True
    validation_message: str = ""


def build_team_spec(
    pattern_name: str,
    agents: List[str],
) -> TeamSpec:
    """Build a validated TeamSpec from a pattern name and agent list.

    Args:
        pattern_name: Name of the registered pattern to use.
        agents: Ordered list of agent identifiers (non-empty strings).

    Returns:
        TeamSpec.  Check .valid and .validation_message for errors.

    Edge cases:
        - Unknown pattern → invalid spec with error message.
        - Empty agents list → invalid spec.
        - Agent count out of range → invalid spec.
    """
    # Clean inputs — remove None, non-strings, and blank/whitespace-only strings
    agents = [a for a in (agents or []) if a and isinstance(a, str) and a.strip()]

    pattern = get_pattern(pattern_name)
    if pattern is None:
        known = [p.name for p in list_patterns()]
        return TeamSpec(
            pattern=TeamPattern(name=pattern_name, description="unknown", min_agents=1, max_agents=0),
            agents=agents,
            valid=False,
            validation_message=(
                f"Unknown pattern '{pattern_name}'. Known patterns: {known}"
            ),
        )

    if not agents:
        return TeamSpec(
            pattern=pattern,
            agents=[],
            valid=False,
            validation_message="Agent list is empty.",
        )

    is_ok, reason = pattern.is_compatible(len(agents))
    if not is_ok:
        return TeamSpec(
            pattern=pattern,
            agents=agents,
            valid=False,
            validation_message=reason,
        )

    # Assign roles (best-effort — roles list may be shorter/longer than agents)
    role_assignments: Dict[str, str] = {}
    for idx, agent in enumerate(agents):
        if idx < len(pattern.roles):
            role_assignments[pattern.roles[idx]] = agent
        else:
            role_assignments[f"agent-{idx + 1}"] = agent

    return TeamSpec(
        pattern=pattern,
        agents=agents,
        role_assignments=role_assignments,
        valid=True,
        validation_message="OK",
    )
