"""SkillAutoImprover 테스트."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import patch


def test_generate_variants_returns_list():
    from core.skill_auto_improver import SkillAutoImprover
    imp = SkillAutoImprover()
    variants = imp._generate_variants("test skill content", "최근 5개 실패 케이스")
    assert isinstance(variants, list)
    assert len(variants) >= 2


def test_improve_returns_none_without_eval():
    """eval.json 없는 스킬은 None 반환."""
    from core.skill_auto_improver import SkillAutoImprover
    imp = SkillAutoImprover()
    result = imp.improve("nonexistent-skill-xyz")
    assert result is None


def test_improve_returns_none_for_unknown_skill():
    from core.skill_auto_improver import SkillAutoImprover
    imp = SkillAutoImprover()
    result = imp.improve("totally-unknown-skill-xyz-123")
    assert result is None


def test_improvement_result_dataclass():
    from core.skill_auto_improver import ImprovementResult
    r = ImprovementResult(
        skill_name="test", original_score=6.0, best_score=7.5,
        variant_applied="improved content", improved=True,
    )
    assert r.improved is True
    assert r.best_score == 7.5
