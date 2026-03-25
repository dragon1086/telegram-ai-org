from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts import run_harness_audit


def test_count_collab_usage_includes_recent_dispatch_jsonl(tmp_path, monkeypatch) -> None:
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()

    recent = datetime.now(UTC) - timedelta(days=1)
    stale = datetime.now(UTC) - timedelta(days=10)

    dispatch_log = logs_dir / "collab_dispatch.jsonl"
    dispatch_log.write_text(
        "\n".join(
            [
                json.dumps({"ts": recent.isoformat(), "status": "dispatched"}),
                json.dumps({"ts": recent.isoformat(), "status": "skipped_no_chat_id"}),
                json.dumps({"ts": stale.isoformat(), "status": "dispatched"}),
            ]
        ),
        encoding="utf-8",
    )

    usage_log = logs_dir / "pm.log"
    usage_log.write_text("[COLLAB:최근 협업]\n", encoding="utf-8")

    monkeypatch.setattr(run_harness_audit, "PROJECT_ROOT", tmp_path)

    assert run_harness_audit._count_collab_usage(days=7) == 3
