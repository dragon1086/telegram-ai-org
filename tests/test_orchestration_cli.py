from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tools import orchestration_cli


def test_validate_config_includes_ops_validation(capsys) -> None:
    rc = orchestration_cli.cmd_validate_config(argparse.Namespace(strict=False))

    out = capsys.readouterr().out
    payload = json.loads(out)

    assert rc == 0
    assert "validation" in payload
    assert "cron_jobs" in payload["validation"]
    assert "collab_targets" in payload["validation"]
    assert payload["validation"]["config_path"].endswith("config/ops_rollout.yaml")
