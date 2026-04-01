"""SkillAutoImprover 테스트."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))



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


def test_improve_keeps_variant_when_crossing_target(monkeypatch, tmp_path):
    import core.skill_auto_improver as skill_auto_improver
    from core.eval_runner import EvalResult
    from core.skill_auto_improver import SkillAutoImprover

    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text("original", encoding="utf-8")

    monkeypatch.setattr(skill_auto_improver, "SKILLS_DIR", tmp_path)
    monkeypatch.setattr(
        "core.eval_runner.EvalRunner.score_skill",
        lambda self, name: EvalResult(
            skill_name=name,
            score=7.2,
            baseline=6.5,
            passed=True,
            improved=True,
            scenario_count=1,
            details=[],
        ),
    )
    monkeypatch.setattr(SkillAutoImprover, "_get_failure_summary", lambda self, name: "요약")
    monkeypatch.setattr(SkillAutoImprover, "_generate_variants", lambda self, content, summary: ["improved"])
    monkeypatch.setattr(SkillAutoImprover, "_score_variant", lambda self, name: 7.6)

    result = SkillAutoImprover().improve("demo-skill", target_score=7.5)

    assert result is not None
    assert result.improved is True
    assert skill_path.read_text(encoding="utf-8") == "improved"
