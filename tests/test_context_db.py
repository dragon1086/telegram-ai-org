import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import aiosqlite
import pytest

from core.context_db import ContextDB


@pytest.fixture
async def temp_db(tmp_path):
    db = ContextDB(str(tmp_path / "test.db"))
    await db.initialize()
    return db


@pytest.mark.asyncio
async def test_conversation_messages_table_created(temp_db):
    """conversation_messages 테이블이 생성되는지 확인"""
    async with aiosqlite.connect(temp_db.db_path) as db:
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='conversation_messages'"
        )
        row = await cursor.fetchone()
    assert row is not None


@pytest.mark.asyncio
async def test_insert_and_query_conversation(temp_db):
    """메시지 삽입 및 조회 확인"""
    await temp_db.insert_conversation_message(
        msg_id=123, chat_id="chat1", user_id="user1", bot_id="bot1",
        role="user", is_bot=False, content="안녕하세요", timestamp="2026-03-17T10:00:00"
    )
    rows = await temp_db.get_conversation_messages(chat_id="chat1", user_id="user1", limit=10)
    assert len(rows) == 1
    assert rows[0]["content"] == "안녕하세요"
    assert rows[0]["is_bot"] == 0


@pytest.mark.asyncio
async def test_is_bot_flag(temp_db):
    """봇 메시지와 사람 메시지 구분"""
    await temp_db.insert_conversation_message(
        msg_id=1, chat_id="chat1", user_id="bot_user", bot_id="bot1",
        role="bot", is_bot=True, content="안녕!", timestamp="2026-03-17T10:01:00"
    )
    await temp_db.insert_conversation_message(
        msg_id=2, chat_id="chat1", user_id="human1", bot_id="bot1",
        role="user", is_bot=False, content="반가워", timestamp="2026-03-17T10:02:00"
    )
    human_rows = await temp_db.get_conversation_messages(chat_id="chat1", is_bot=False, limit=10)
    assert len(human_rows) == 1
    assert human_rows[0]["user_id"] == "human1"


@pytest.mark.asyncio
async def test_retention_cleanup(temp_db):
    """30일 이전 메시지 정리 확인"""
    await temp_db.insert_conversation_message(
        msg_id=1, chat_id="chat1", user_id="user1", bot_id="bot1",
        role="user", is_bot=False, content="old message", timestamp="2025-01-01T10:00:00"
    )
    await temp_db.insert_conversation_message(
        msg_id=2, chat_id="chat1", user_id="user1", bot_id="bot1",
        role="user", is_bot=False, content="new message", timestamp="2026-03-17T10:00:00"
    )
    deleted = await temp_db.cleanup_old_conversations(retention_days=30)
    assert deleted >= 1
    rows = await temp_db.get_conversation_messages(chat_id="chat1", limit=10)
    assert all(r["content"] != "old message" for r in rows)
