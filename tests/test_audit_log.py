"""tests/test_audit_log.py — Audit Log 단위 테스트 (Phase 3-A)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import core.api.audit_log as audit_module
from core.api.audit_log import read_audit_events, write_audit_event

# ---------------------------------------------------------------------------
# 픽스처
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_log(tmp_path: Path) -> Path:
    """임시 감사 로그 파일 경로."""
    return tmp_path / "audit.log"


@pytest.fixture(autouse=True)
def _enable_audit(monkeypatch):
    """각 테스트에서 ENABLE_AUDIT_LOG=True로 설정."""
    monkeypatch.setattr(audit_module, "ENABLE_AUDIT_LOG", True)
    yield


# ---------------------------------------------------------------------------
# 테스트
# ---------------------------------------------------------------------------


def test_audit_disabled_writes_nothing(monkeypatch, tmp_log: Path):
    """ENABLE_AUDIT_LOG=false 시 파일 생성 안 됨."""
    monkeypatch.setattr(audit_module, "ENABLE_AUDIT_LOG", False)
    write_audit_event("task_created", "task-001", log_path=tmp_log)
    assert not tmp_log.exists()


def test_write_audit_event_creates_file(tmp_log: Path):
    """ENABLE_AUDIT_LOG=true 시 파일이 생성됨."""
    write_audit_event("task_created", "task-002", log_path=tmp_log)
    assert tmp_log.exists()


def test_audit_event_fields(tmp_log: Path):
    """이벤트에 필수 필드가 모두 포함됨."""
    write_audit_event(
        action="task_created",
        task_id="task-003",
        org_id="dev",
        api_key="short",
        client_ip="127.0.0.1",
        log_path=tmp_log,
    )
    line = tmp_log.read_text().strip()
    event = json.loads(line)

    assert "timestamp" in event
    assert event["action"] == "task_created"
    assert event["task_id"] == "task-003"
    assert event["org_id"] == "dev"
    assert event["client_ip"] == "127.0.0.1"
    assert "api_key_prefix" in event


def test_api_key_masking(tmp_log: Path):
    """API Key가 8자 초과 시 앞 8자 + **** 로 마스킹됨."""
    long_key = "abcdefghijklmnop"  # 16자
    write_audit_event("task_created", "task-004", api_key=long_key, log_path=tmp_log)

    event = json.loads(tmp_log.read_text().strip())
    assert event["api_key_prefix"] == "abcdefgh****"


def test_api_key_short_not_masked(tmp_log: Path):
    """8자 이하 API Key는 마스킹 없이 그대로 저장됨."""
    short_key = "abc"
    write_audit_event("task_created", "task-005", api_key=short_key, log_path=tmp_log)

    event = json.loads(tmp_log.read_text().strip())
    assert event["api_key_prefix"] == "abc"


def test_read_audit_events_empty(tmp_log: Path):
    """존재하지 않는 파일에서 읽으면 빈 리스트 반환."""
    result = read_audit_events(log_path=tmp_log)
    assert result == []


def test_read_audit_events_returns_latest(tmp_log: Path):
    """여러 이벤트 기록 후 limit 적용하여 최신 N개 반환."""
    for i in range(5):
        write_audit_event(f"action_{i}", f"task-{i:03d}", log_path=tmp_log)

    # limit=3 — 최신 3개
    events = read_audit_events(log_path=tmp_log, limit=3)
    assert len(events) == 3

    # 전체 반환
    all_events = read_audit_events(log_path=tmp_log, limit=100)
    assert len(all_events) == 5


def test_extra_field(tmp_log: Path):
    """extra 딕셔너리가 이벤트에 저장됨."""
    write_audit_event(
        "task_created",
        "task-006",
        extra={"description": "test task", "priority": 1},
        log_path=tmp_log,
    )
    event = json.loads(tmp_log.read_text().strip())
    assert "extra" in event
    assert event["extra"]["description"] == "test task"
    assert event["extra"]["priority"] == 1


def test_jsonl_format(tmp_log: Path):
    """각 라인이 유효한 JSON (JSONL 포맷) 인지 검증."""
    for i in range(3):
        write_audit_event("task_created", f"task-{i:03d}", log_path=tmp_log)

    lines = tmp_log.read_text().strip().splitlines()
    assert len(lines) == 3
    for line in lines:
        parsed = json.loads(line)
        assert isinstance(parsed, dict)


def test_extra_none_not_in_event(tmp_log: Path):
    """extra=None 시 이벤트에 extra 키가 없어야 함."""
    write_audit_event("task_deleted", "task-007", extra=None, log_path=tmp_log)
    event = json.loads(tmp_log.read_text().strip())
    assert "extra" not in event
