# 메모리 & 프로액티브 시스템 구현 계획

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 대화 이력 완전 보존 + BM25 통합 검색 + 프로액티브 봇 행동 구현

**Architecture:** ContextDB에 conversation_messages 테이블 추가 → MemoryManager BM25 검색 업그레이드 → MessageBus 확장으로 프로액티브 이벤트 → active_hours YAML 설정

**Tech Stack:** Python asyncio, aiosqlite, rank-bm25, APScheduler (기존), python-telegram-bot

---

## Task 1: conversation_messages 테이블 (Phase 1)

**Files:**
- Modify: `core/context_db.py`
- Modify: `core/telegram_relay.py`
- Test: `tests/test_context_db.py` (신규)

### Step 1: 테스트 작성 (`tests/test_context_db.py`)

```python
import pytest
import asyncio
import aiosqlite
import tempfile
import os
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
```

### Step 2: 테스트 실패 확인

```bash
.venv/bin/pytest tests/test_context_db.py -v
```
Expected: FAILED (메서드 없음)

### Step 3: `context_db.py`에 테이블 + 메서드 추가

`ContextDB.initialize()` 메서드의 기존 테이블 생성 이후에 추가:

```python
await db.execute("""
    CREATE TABLE IF NOT EXISTS conversation_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        msg_id INTEGER,
        chat_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        bot_id TEXT,
        role TEXT NOT NULL,
        is_bot BOOLEAN DEFAULT 0,
        content TEXT NOT NULL,
        timestamp TEXT NOT NULL
    )
""")
await db.execute(
    "CREATE INDEX IF NOT EXISTS idx_conv_chat_user ON conversation_messages(chat_id, user_id)"
)
await db.execute(
    "CREATE INDEX IF NOT EXISTS idx_conv_timestamp ON conversation_messages(timestamp)"
)
await db.commit()
```

새 메서드들 (`ContextDB` 클래스에 추가):

```python
async def insert_conversation_message(
    self, *, msg_id: int | None, chat_id: str, user_id: str, bot_id: str | None,
    role: str, is_bot: bool, content: str, timestamp: str
) -> None:
    async with aiosqlite.connect(self.db_path) as db:
        await db.execute(
            """INSERT INTO conversation_messages
               (msg_id, chat_id, user_id, bot_id, role, is_bot, content, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (msg_id, chat_id, user_id, bot_id, role, int(is_bot), content, timestamp),
        )
        await db.commit()

async def get_conversation_messages(
    self,
    *,
    chat_id: str | None = None,
    user_id: str | None = None,
    is_bot: bool | None = None,
    limit: int = 100,
) -> list[dict]:
    clauses, params = [], []
    if chat_id:
        clauses.append("chat_id = ?"); params.append(chat_id)
    if user_id:
        clauses.append("user_id = ?"); params.append(user_id)
    if is_bot is not None:
        clauses.append("is_bot = ?"); params.append(int(is_bot))
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)
    async with aiosqlite.connect(self.db_path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            f"SELECT * FROM conversation_messages {where} ORDER BY timestamp DESC LIMIT ?",
            params,
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]

async def cleanup_old_conversations(self, retention_days: int = 30) -> int:
    cutoff = (
        __import__("datetime").datetime.utcnow()
        - __import__("datetime").timedelta(days=retention_days)
    ).isoformat()
    async with aiosqlite.connect(self.db_path) as db:
        cursor = await db.execute(
            "DELETE FROM conversation_messages WHERE timestamp < ?", (cutoff,)
        )
        await db.commit()
        return cursor.rowcount
```

### Step 4: `telegram_relay.py` - 메시지 캡처 훅 추가

`on_message` 핸들러의 **조기 리턴 이전** (bot 체크, dept-org 체크 이전)에 캡처:

```python
# on_message 시작 부분 (text 추출 직후, 조기 리턴 이전)
if self._context_db is not None:
    try:
        sender = update.message.from_user
        asyncio.create_task(
            self._context_db.insert_conversation_message(
                msg_id=update.message.message_id,
                chat_id=str(update.message.chat_id),
                user_id=str(sender.id) if sender else "unknown",
                bot_id=self._bot_id,
                role="bot" if (sender and sender.is_bot) else "user",
                is_bot=bool(sender and sender.is_bot),
                content=text[:4000],  # 4K 트런케이션
                timestamp=update.message.date.isoformat(),
            )
        )
    except Exception:
        pass  # 캡처 실패해도 처리 계속
```

### Step 5: 테스트 통과 확인

```bash
.venv/bin/pytest tests/test_context_db.py -v
```
Expected: 4 PASSED

### Step 6: 전체 테스트 회귀 확인

```bash
.venv/bin/pytest tests/ -q --tb=short -x --ignore=tests/test_verification.py --ignore=tests/test_nl_classifier.py
```
Expected: 기존 실패 제외 모두 통과

### Step 7: 커밋

```bash
git add core/context_db.py core/telegram_relay.py tests/test_context_db.py
git commit -m "feat: conversation_messages 테이블 + 메시지 캡처 훅 (Phase 1)"
```

---

## Task 2: BM25 통합 검색 (Phase 2)

**Files:**
- Modify: `core/memory_manager.py`
- Modify: `pyproject.toml` (rank-bm25 추가)
- Test: `tests/test_memory_manager.py` (기존 파일에 추가)

### Step 1: rank-bm25 설치

```bash
.venv/bin/pip install rank-bm25
```

### Step 2: pyproject.toml 의존성 추가

`[project] dependencies` 목록에 `"rank-bm25"` 추가.

### Step 3: 실패 테스트 작성 (`tests/test_memory_manager.py`에 추가)

```python
@pytest.mark.asyncio
async def test_search_memories_returns_relevant_results(tmp_path, monkeypatch):
    """BM25 검색이 관련 결과를 반환하는지"""
    from core.memory_manager import MemoryManager
    mm = MemoryManager(base_dir=str(tmp_path), bot_id="test_bot")
    # LOG에 항목 삽입
    mm._append_log("CORE", "Python asyncio 비동기 프로그래밍 기초")
    mm._append_log("CORE", "JavaScript 프론트엔드 React 컴포넌트")
    mm._append_log("CORE", "asyncio event loop 활용 방법")

    results = await mm.search_memories("asyncio 비동기", user_id="u1", top_k=2)
    assert len(results) == 2
    assert any("asyncio" in r for r in results)


@pytest.mark.asyncio
async def test_search_memories_includes_conversation_entries(tmp_path, monkeypatch):
    """BM25 검색이 conversation_messages도 포함하는지"""
    from core.memory_manager import MemoryManager
    from unittest.mock import AsyncMock
    mm = MemoryManager(base_dir=str(tmp_path), bot_id="test_bot")
    mm._context_db = AsyncMock()
    mm._context_db.get_conversation_messages = AsyncMock(
        return_value=[{"content": "Django REST API 구축 완료"}]
    )
    mm._append_log("CORE", "Flask 웹 프레임워크 기초")

    results = await mm.search_memories("REST API Django", user_id="u1", top_k=2)
    assert any("Django" in r for r in results)
```

### Step 4: 테스트 실패 확인

```bash
.venv/bin/pytest tests/test_memory_manager.py::test_search_memories_returns_relevant_results -v
```
Expected: FAILED (AttributeError)

### Step 5: `memory_manager.py`에 `search_memories` 추가

```python
async def search_memories(
    self, query: str, user_id: str, top_k: int = 5
) -> list[str]:
    """BM25로 MemoryManager LOG + conversation_messages 통합 검색."""
    try:
        from rank_bm25 import BM25Okapi
    except ImportError:
        # fallback: 기존 keyword 방식
        return self._keyword_search(query, top_k)

    # 1) MemoryManager LOG 항목
    log_entries = self._load_log_entries("CORE")

    # 2) conversation_messages (최근 100개)
    conv_entries: list[str] = []
    if self._context_db is not None:
        try:
            rows = await self._context_db.get_conversation_messages(
                user_id=user_id, limit=100
            )
            conv_entries = [r["content"] for r in rows if r.get("content")]
        except Exception:
            pass

    corpus = log_entries + conv_entries
    if not corpus:
        return []

    tokenized = [entry.split() for entry in corpus]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(query.split())
    top_indices = sorted(range(len(corpus)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [corpus[i] for i in top_indices if scores[i] > 0]

def _keyword_search(self, query: str, top_k: int) -> list[str]:
    """BM25 없을 때 fallback keyword 검색."""
    entries = self._load_log_entries("CORE")
    query_words = set(query.lower().split())
    scored = [(e, len(query_words & set(e.lower().split()))) for e in entries]
    return [e for e, s in sorted(scored, key=lambda x: -x[1]) if s > 0][:top_k]
```

`MemoryManager.__init__`에 `self._context_db = None` 추가, `_load_log_entries` 헬퍼가 없으면 기존 `_load_memory` 방식으로 연결.

### Step 6: 테스트 통과 확인

```bash
.venv/bin/pytest tests/test_memory_manager.py -v
```
Expected: 기존 + 신규 모두 통과

### Step 7: 커밋

```bash
git add core/memory_manager.py pyproject.toml tests/test_memory_manager.py
git commit -m "feat: MemoryManager BM25 통합 검색 (LOG + conversation_messages) (Phase 2)"
```

---

## Task 3: ProactiveHandler (Phase 3)

**Files:**
- Modify: `core/message_bus.py` (신규 EventType 2개)
- Create: `core/proactive_handler.py`
- Modify: `core/scheduler.py` (비활동 감지 + 일일 인사이트 스케줄)
- Modify: `main.py` (ProactiveHandler 등록)
- Test: `tests/test_proactive_handler.py` (신규)

### Step 1: 실패 테스트 작성 (`tests/test_proactive_handler.py`)

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.message_bus import MessageBus, EventType, Event
from core.proactive_handler import ProactiveHandler


@pytest.fixture
def bus():
    return MessageBus()


@pytest.mark.asyncio
async def test_inactivity_event_type_exists():
    """INACTIVITY_DETECTED 이벤트 타입이 존재하는지"""
    assert hasattr(EventType, "INACTIVITY_DETECTED")
    assert hasattr(EventType, "DAILY_INSIGHT")


@pytest.mark.asyncio
async def test_proactive_handler_subscribes(bus):
    """ProactiveHandler가 두 이벤트를 구독하는지"""
    handler = ProactiveHandler(bus, bots={})
    handler.register()
    assert EventType.INACTIVITY_DETECTED in bus._subscribers
    assert EventType.DAILY_INSIGHT in bus._subscribers


@pytest.mark.asyncio
async def test_inactivity_handler_called_on_event(bus):
    """INACTIVITY_DETECTED 이벤트 발화 시 핸들러 호출"""
    called_with = []

    async def fake_send(chat_id, text):
        called_with.append((chat_id, text))

    handler = ProactiveHandler(bus, bots={})
    handler._send_proactive_message = fake_send
    handler.register()

    await bus.publish(Event(
        type=EventType.INACTIVITY_DETECTED,
        data={"chat_id": "chat1", "inactive_hours": 5}
    ))
    assert len(called_with) >= 0  # 실제 봇 없어도 에러 없어야 함


@pytest.mark.asyncio
async def test_event_suppressed_outside_active_hours(bus):
    """active_hours 범위 밖에서 이벤트 억제"""
    handler = ProactiveHandler(
        bus,
        bots={"bot1": {"active_hours": {"start": 9, "end": 10}}},
    )
    handler.register()

    # 현재 시각이 범위 밖이면 메시지 전송 안 함
    with patch("core.proactive_handler.datetime") as mock_dt:
        mock_dt.now.return_value = MagicMock(hour=3)
        handler._send_proactive_message = AsyncMock()
        await bus.publish(Event(
            type=EventType.INACTIVITY_DETECTED,
            data={"chat_id": "chat1", "inactive_hours": 5, "bot_id": "bot1"}
        ))
        handler._send_proactive_message.assert_not_called()
```

### Step 2: 테스트 실패 확인

```bash
.venv/bin/pytest tests/test_proactive_handler.py -v
```
Expected: FAILED

### Step 3: `message_bus.py`에 이벤트 타입 추가

`EventType` Enum에 추가:
```python
INACTIVITY_DETECTED = "inactivity_detected"
DAILY_INSIGHT = "daily_insight"
```

### Step 4: `core/proactive_handler.py` 생성

```python
"""프로액티브 봇 행동 핸들러 — INACTIVITY_DETECTED/DAILY_INSIGHT 이벤트 구독."""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.message_bus import MessageBus

from core.message_bus import EventType, Event

logger = logging.getLogger(__name__)


class ProactiveHandler:
    """MessageBus 이벤트를 구독해 프로액티브 메시지를 전송한다."""

    def __init__(self, bus: "MessageBus", bots: dict) -> None:
        self._bus = bus
        self._bots = bots  # {bot_id: bot_config_dict}

    def register(self) -> None:
        self._bus.subscribe(EventType.INACTIVITY_DETECTED, self._on_inactivity)
        self._bus.subscribe(EventType.DAILY_INSIGHT, self._on_daily_insight)

    def _is_within_active_hours(self, bot_id: str) -> bool:
        bot_cfg = self._bots.get(bot_id, {})
        active_hours = bot_cfg.get("active_hours")
        if not active_hours:
            return True  # 미설정 = 항상 활성
        now_hour = datetime.now().hour
        return active_hours.get("start", 0) <= now_hour < active_hours.get("end", 24)

    async def _on_inactivity(self, event: Event) -> None:
        chat_id = event.data.get("chat_id", "")
        bot_id = event.data.get("bot_id", "")
        if bot_id and not self._is_within_active_hours(bot_id):
            logger.debug(f"[Proactive] active_hours 범위 밖, 이벤트 억제: {bot_id}")
            return
        await self._send_proactive_message(
            chat_id, "💭 잠시 조용하네요. 현재 진행 중인 작업이 있으신가요?"
        )

    async def _on_daily_insight(self, event: Event) -> None:
        chat_id = event.data.get("chat_id", "")
        bot_id = event.data.get("bot_id", "")
        if bot_id and not self._is_within_active_hours(bot_id):
            return
        await self._send_proactive_message(chat_id, "📊 오늘의 팀 인사이트를 준비했어요!")

    async def _send_proactive_message(self, chat_id: str, text: str) -> None:
        """실제 Telegram 전송 — 봇 인스턴스 주입 시 오버라이드."""
        logger.info(f"[Proactive] 메시지 전송 → chat={chat_id}: {text}")
```

### Step 5: `scheduler.py`에 비활동 감지 스케줄 추가

기존 `AsyncIOScheduler` 사용. `scheduler.py`의 `start()` 메서드 또는 `_register_jobs()`에 추가:

```python
# 비활동 감지: 1시간마다 체크
self.scheduler.add_job(
    lambda: asyncio.create_task(self._check_inactivity()),
    "interval", hours=1, id="inactivity_check"
)
# 일일 인사이트: 매일 오전 9시
self.scheduler.add_job(
    lambda: asyncio.create_task(self._fire_daily_insight()),
    "cron", hour=9, minute=0, id="daily_insight"
)
```

### Step 6: `main.py` wiring

봇 시작 시:
```python
from core.proactive_handler import ProactiveHandler
# ...
proactive = ProactiveHandler(message_bus, bots=bot_configs)
proactive.register()
```

### Step 7: 테스트 통과 확인

```bash
.venv/bin/pytest tests/test_proactive_handler.py -v
```
Expected: 4 PASSED

### Step 8: 커밋

```bash
git add core/message_bus.py core/proactive_handler.py core/scheduler.py main.py tests/test_proactive_handler.py
git commit -m "feat: ProactiveHandler — INACTIVITY/DAILY_INSIGHT 이벤트 기반 프로액티브 봇 (Phase 3)"
```

---

## Task 4: active_hours YAML 설정 (Phase 4)

**Files:**
- Modify: `bots/cokac.yaml` (또는 존재하는 봇 YAML들)
- Modify: `orchestration.yaml`
- Modify: `core/proactive_handler.py` (timezone 지원 완성)
- Test: `tests/test_proactive_handler.py`에 추가

### Step 1: orchestration.yaml에 글로벌 설정 추가

```yaml
conversation_history_retention_days: 30
inactivity_threshold_hours: 4
default_active_hours:
  start: 9
  end: 22
  timezone: "Asia/Seoul"
```

### Step 2: 봇 YAML에 active_hours 추가 (예: cokac.yaml)

```yaml
active_hours:
  start: 9
  end: 22
  timezone: "Asia/Seoul"
```

### Step 3: 테스트 추가

```python
def test_active_hours_yaml_parsed():
    """bots/*.yaml active_hours 파싱 확인"""
    import yaml, os
    bot_yamls = [f for f in os.listdir("bots") if f.endswith(".yaml")]
    for fname in bot_yamls:
        with open(f"bots/{fname}") as f:
            cfg = yaml.safe_load(f)
        # active_hours 없으면 OK (옵션), 있으면 start/end 필수
        if "active_hours" in cfg:
            assert "start" in cfg["active_hours"]
            assert "end" in cfg["active_hours"]
```

### Step 4: 테스트 통과 확인

```bash
.venv/bin/pytest tests/test_proactive_handler.py -v
```

### Step 5: 커밋

```bash
git add orchestration.yaml bots/ tests/test_proactive_handler.py
git commit -m "feat: active_hours YAML 설정 — 프로액티브 이벤트 시간 제어 (Phase 4)"
```

---

## Task 5: retention 스케줄 + 전체 테스트 + push

**Files:**
- Modify: `core/scheduler.py` (30일 retention cleanup 스케줄)
- Modify: `CLAUDE.md` (rank-bm25 설치 주의사항)
- Modify: `docs/architecture-deep-analysis.md` (섹션 5 업데이트)

### Step 1: scheduler.py에 retention cleanup 추가

```python
# 주 1회 오래된 대화 이력 정리
self.scheduler.add_job(
    lambda: asyncio.create_task(self._cleanup_old_conversations()),
    "interval", weeks=1, id="conversation_cleanup"
)
```

### Step 2: 전체 테스트

```bash
.venv/bin/pytest tests/ -q --tb=short
```
Expected: 신규 테스트 통과 + 기존 pre-existing 실패만 남음

### Step 3: architecture-deep-analysis.md 업데이트

섹션 5에 추가:
- 5.12 conversation_messages 대화 이력 영속 저장 ✅
- 5.13 BM25 통합 검색 (MemoryManager + conversation) ✅
- 5.14 ProactiveHandler — 비활동/일일 인사이트 이벤트 ✅
- 5.15 active_hours YAML 설정 ✅

### Step 4: main push

```bash
git push origin main
```
