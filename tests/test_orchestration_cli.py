from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.eval_runner import EvalResult
from tools import orchestration_cli


def test_validate_config_includes_ops_validation(capsys) -> None:
    rc = orchestration_cli.cmd_validate_config(argparse.Namespace(strict=False))

    out = capsys.readouterr().out
    payload = json.loads(out)

    assert rc == 0
    assert "validation" in payload
    assert "cron_jobs" in payload["validation"]
    assert "collab_targets" in payload["validation"]
    assert "auto_restart" in payload["validation"]
    assert payload["validation"]["config_path"].endswith("config/ops_rollout.yaml")


def test_skill_eval_report_includes_below_target(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "core.eval_runner.EvalRunner.score_all_skills",
        lambda self: [
            EvalResult(
                skill_name="bot-triage",
                score=7.6,
                baseline=6.5,
                passed=True,
                improved=True,
                scenario_count=1,
                details=[],
            ),
            EvalResult(
                skill_name="pm-task-dispatch",
                score=7.1,
                baseline=7.0,
                passed=True,
                improved=True,
                scenario_count=1,
                details=[],
            ),
        ],
    )

    rc = orchestration_cli.cmd_skill_eval_report(
        argparse.Namespace(target=7.5, strict=False, github_warning=False)
    )

    out = capsys.readouterr().out
    payload = json.loads(out)
    assert rc == 0
    assert payload["status"] == "warn"
    assert payload["below_target"] == [{"skill_name": "pm-task-dispatch", "score": 7.1}]
