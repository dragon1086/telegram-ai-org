from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.review_recent_conversations import (
    collect_recent_log_lines,
    heuristic_review_markdown,
    maybe_upload_report,
    _extract_timestamp,
)


def test_extract_timestamp() -> None:
    ts = _extract_timestamp("2026-03-15 12:34:56.123 | INFO | sample")
    assert ts == datetime(2026, 3, 15, 12, 34, 56)


def test_collect_recent_log_lines(tmp_path: Path, monkeypatch) -> None:
    log_dir = tmp_path
    now = datetime.now()
    recent = now.strftime("%Y-%m-%d %H:%M:%S") + " | INFO | core.telegram_relay:on_message - 텔레그램 수신 [global]: hello"
    old = (now - timedelta(hours=10)).strftime("%Y-%m-%d %H:%M:%S") + " | INFO | old"
    (log_dir / "global.log").write_text(f"{old}\n{recent}\n", encoding="utf-8")
    monkeypatch.setattr("scripts.review_recent_conversations.LOG_DIR", log_dir)

    collected = collect_recent_log_lines(hours=2, limit_lines=20)

    assert "텔레그램 수신" in collected
    assert "old" not in collected


def test_heuristic_review_markdown_contains_sections() -> None:
    transcript = "\n".join([
        "2026-03-15 10:00:00 | INFO | 텔레그램 수신 [global]: hello",
        "2026-03-15 10:00:01 | INFO | [TaskPoller:aiorg_ops_bot] 태스크 감지: T-1",
        "2026-03-15 10:00:02 | INFO | [aiorg_ops_bot] PM_TASK 실행 시작: T-1",
    ])
    report = heuristic_review_markdown(transcript, 2)
    assert "# 최근 2시간 대화/작업 리뷰" in report
    assert "## 주요 관찰" in report
    assert "## 권장 액션" in report


@pytest.mark.asyncio
async def test_maybe_upload_report_uses_org_target(tmp_path: Path, monkeypatch) -> None:
    report = tmp_path / "report.md"
    report.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(
        "scripts.review_recent_conversations.resolve_delivery_target",
        lambda org_id: type("T", (), {"token": "tok", "chat_id": 123, "org_id": org_id})(),
    )

    calls: list[tuple[str, int, str, str]] = []

    async def _fake_upload(token: str, chat_id: int, file_path: str, caption: str = "") -> bool:
        calls.append((token, chat_id, file_path, caption))
        return True

    monkeypatch.setattr("scripts.review_recent_conversations.upload_file", _fake_upload)

    ok = await maybe_upload_report("global", report)

    assert ok is True
    assert calls == [("tok", 123, str(report), f"🧾 global daily conversation review: {report.name}")]
