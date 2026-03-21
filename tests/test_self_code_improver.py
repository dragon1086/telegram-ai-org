"""SelfCodeImprover 테스트."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import patch
from core.self_code_improver import SelfCodeImprover, FixResult


def test_fix_result_dataclass():
    r = FixResult(
        target="core/foo.py", success=True,
        branch="fix/auto-2026-03-21-foo",
        commit_hash="abc1234", attempts=1,
    )
    assert r.success is True
    assert r.attempts == 1


def test_build_prompt_contains_target():
    imp = SelfCodeImprover(dry_run=True)
    prompt = imp._build_prompt(
        target="core/pm_orchestrator.py",
        error_summary="context_loss 7회 반복",
        related_files=["core/pm_orchestrator.py"],
    )
    assert "core/pm_orchestrator.py" in prompt
    assert "context_loss" in prompt


def test_dry_run_returns_none():
    imp = SelfCodeImprover(dry_run=True)
    with patch("subprocess.run") as mock_run:
        result = imp.fix(
            target="core/foo.py",
            error_summary="test error",
            related_files=["core/foo.py"],
        )
    mock_run.assert_not_called()
    assert result is None


def test_rate_limit_check_passes_initially(tmp_path):
    imp = SelfCodeImprover(dry_run=True)
    imp._rate_limit_file = tmp_path / "rate.json"
    assert imp._check_rate_limit("core/foo.py") is True


def test_rate_limit_blocks_after_3(tmp_path):
    import json
    from datetime import datetime, timezone
    imp = SelfCodeImprover(dry_run=True)
    rate_file = tmp_path / "rate.json"
    imp._rate_limit_file = rate_file
    now = datetime.now(timezone.utc).isoformat()
    rate_file.write_text(json.dumps({"core/foo.py": [now, now, now]}))
    assert imp._check_rate_limit("core/foo.py") is False
