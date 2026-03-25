"""EvalRunner 단위 테스트."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.eval_runner import EvalResult, EvalRunner


class TestEvalRunner:
    def test_score_all_skills_no_crash(self):
        """evals/skills/ 디렉토리가 있으면 크래시 없이 실행."""
        runner = EvalRunner()
        results = runner.score_all_skills()
        assert isinstance(results, list)
        for r in results:
            assert isinstance(r, EvalResult)
            assert 0.0 <= r.score <= 10.0
            assert r.baseline >= 0.0

    def test_score_skill_returns_none_without_eval(self):
        """eval.json 없는 스킬은 None 반환."""
        runner = EvalRunner()
        result = runner.score_skill("nonexistent-skill-xyz")
        assert result is None

    def test_score_skill_with_real_eval(self):
        """실제 pm-task-dispatch eval.json으로 점수 측정."""
        runner = EvalRunner()
        result = runner.score_skill("pm-task-dispatch")
        # eval.json이 있으므로 결과가 있어야 함
        assert result is not None
        assert result.skill_name == "pm-task-dispatch"
        assert 0.0 <= result.score <= 10.0
        assert result.baseline == 7.0
        assert isinstance(result.improved, bool)
        assert isinstance(result.passed, bool)

    def test_eval_result_delta(self):
        r = EvalResult(
            skill_name="test", score=8.5, baseline=7.0,
            passed=True, improved=True,
            scenario_count=5, details=[],
        )
        assert r.delta == pytest.approx(1.5, abs=0.01)

    def test_format_results_no_crash(self):
        runner = EvalRunner()
        results = runner.score_all_skills()
        text = runner.format_results(results)
        assert isinstance(text, str)

    def test_score_routing_empty_cases(self, tmp_path, monkeypatch):
        """routing test_cases.json 없으면 accuracy=0 반환."""
        runner = EvalRunner()
        monkeypatch.setattr(runner, "_routing_dir", tmp_path)
        result = runner.score_routing(lambda msg: "engineering")
        assert result["accuracy"] == 0.0
        assert result["total"] == 0

    def test_score_routing_perfect(self, tmp_path, monkeypatch):
        """모든 답이 맞으면 accuracy=1.0."""
        runner = EvalRunner()
        test_data = {
            "baseline_accuracy": 0.8,
            "test_cases": [
                {"id": "1", "input": "버그 수정", "correct_bot": "engineering"},
                {"id": "2", "input": "디자인", "correct_bot": "design"},
            ],
        }
        routing_dir = tmp_path / "routing"
        routing_dir.mkdir()
        (routing_dir / "test_cases.json").write_text(json.dumps(test_data))
        monkeypatch.setattr(runner, "_routing_dir", routing_dir)

        result = runner.score_routing(lambda msg: "engineering" if "버그" in msg else "design")
        assert result["accuracy"] == 1.0
        assert result["correct"] == 2
        assert result["total"] == 2
