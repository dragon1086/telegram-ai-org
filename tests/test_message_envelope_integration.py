"""MessageEnvelope 통합 테스트 — wrap/display 라운드트립, legacy tag, EnvelopeManager."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
import pytest_asyncio

from core.message_envelope import MessageEnvelope, EnvelopeManager


# ---------------------------------------------------------------------------
# wrap → display 라운드트립
# ---------------------------------------------------------------------------

def test_to_display_returns_content():
    env = MessageEnvelope.wrap(content="안녕하세요.", sender_bot="pm_bot", intent="DIRECT_REPLY")
    assert env.to_display() == "안녕하세요."


def test_to_display_strips_legacy_tags():
    env = MessageEnvelope.wrap(
        content="[COLLAB_REQUEST:bot_a] 작업 시작합니다.",
        sender_bot="pm_bot",
        intent="COLLAB_REQUEST",
    )
    assert env.to_display() == "작업 시작합니다."


def test_to_display_strips_multiple_legacy_tags():
    env = MessageEnvelope.wrap(
        content="[TYPE:FOO] [TEAM:dev] 메시지입니다.",
        sender_bot="pm_bot",
        intent="DIRECT_REPLY",
    )
    assert env.to_display() == "메시지입니다."


def test_to_wire_round_trip():
    env = MessageEnvelope.wrap(
        content="테스트",
        sender_bot="eng_bot",
        intent="TASK_ACCEPT",
        task_id="T-001",
    )
    wire = env.to_wire()
    restored = MessageEnvelope.from_wire(wire)
    assert restored.content == env.content
    assert restored.sender_bot == env.sender_bot
    assert restored.intent == env.intent
    assert restored.task_id == env.task_id


def test_extract_legacy_tags_parses_correctly():
    tags = MessageEnvelope.extract_legacy_tags("[COLLAB_REQUEST:bot_a] [TEAM:dev]")
    assert tags == {"COLLAB_REQUEST": "bot_a", "TEAM": "dev"}


def test_extract_legacy_tags_empty_on_no_tags():
    tags = MessageEnvelope.extract_legacy_tags("일반 메시지입니다.")
    assert tags == {}


# ---------------------------------------------------------------------------
# EnvelopeManager — DB CRUD
# ---------------------------------------------------------------------------

class _FakeDB:
    def __init__(self, path: str) -> None:
        self.db_path = path


@pytest_asyncio.fixture
async def tmp_db(tmp_path):
    import aiosqlite
    db_path = str(tmp_path / "test.db")
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS message_envelopes (
                telegram_message_id INTEGER PRIMARY KEY,
                task_id TEXT,
                metadata TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.commit()
    return _FakeDB(db_path)


@pytest.mark.asyncio
async def test_envelope_manager_save_and_load(tmp_db):
    mgr = EnvelopeManager(tmp_db)
    env = MessageEnvelope.wrap(
        content="작업 완료",
        sender_bot="eng_bot",
        intent="TASK_DONE",
        task_id="T-999",
    )
    await mgr.save(message_id=42, envelope=env)
    loaded = await mgr.load(message_id=42)
    assert loaded is not None
    assert loaded.task_id == "T-999"


@pytest.mark.asyncio
async def test_envelope_manager_load_missing_returns_none(tmp_db):
    mgr = EnvelopeManager(tmp_db)
    result = await mgr.load(message_id=9999)
    assert result is None
