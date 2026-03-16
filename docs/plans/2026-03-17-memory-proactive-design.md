# 메모리 아키텍처 & 프로액티브 시스템 설계

> 작성일: 2026-03-17
> 목표: 대화 이력 완전 보존 + BM25 검색 + 프로액티브 봇 행동

---

## 배경 및 핵심 제약

### 현재 문제
- 원본 대화 메시지가 저장되지 않음 — MemoryManager는 최대 30개 요약만 보관
- MemoryManager 검색이 단순 keyword 교집합 → 동의어/관련어 누락
- 봇이 완전히 수동적 — 사용자가 먼저 말 걸어야만 반응

### 핵심 아키텍처 제약 (Architect 발견)
**tmux-relay 구조**: LLM 호출이 `tmux send-keys`로 Claude Code CLI를 실행하는 방식. 직접 Anthropic API 호출 없음.
- **영향**: Mem0, Graphiti 같은 외부 메모리 라이브러리 (system prompt 주입 방식) **사용 불가**
- **영향**: 기존 `MessageBus` (22개 이벤트 타입 존재) 확장이 올바른 패턴
- **영향**: 기존 `MemoryManager` 업그레이드, 교체 아님

---

## 아키텍처 개요

```
[현재]
메시지 → on_message → 메모리 없음 (요약만)
봇 → 완전 수동 (사용자 메시지 없으면 침묵)

[개선]
메시지 → on_message (조기 리턴 전 캡처) → conversation_messages 테이블
                                          ↓
MemoryManager.build_context() → BM25 검색 (MemoryManager 로그 + conversation_messages 통합)
                                          ↓
MessageBus: INACTIVITY_DETECTED / DAILY_INSIGHT 이벤트
                    ↓
ProactiveHandler → active_hours 확인 → 봇 응답
```

---

## Phase 1: 대화 이력 캡처 (conversation_messages)

**파일:** `core/context_db.py`, `core/telegram_relay.py`

### 설계 결정
- ContextDB (기존 aiosqlite) 에 테이블 추가 — 별도 DB 파일 아님
- 캡처 위치: `on_message` 조기 리턴들(bot check, dept-org check) **이전** — 모든 메시지 캡처
- `is_bot` 컬럼 포함 → 나중에 봇 대 사람 메시지 필터 가능

### 스키마
```sql
CREATE TABLE IF NOT EXISTS conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    msg_id INTEGER,
    chat_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    bot_id TEXT,              -- 어느 봇의 ContextDB인지
    role TEXT NOT NULL,       -- 'user' | 'assistant' | 'bot'
    is_bot BOOLEAN DEFAULT 0,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL   -- ISO 8601
);
CREATE INDEX IF NOT EXISTS idx_conv_chat_user ON conversation_messages(chat_id, user_id);
CREATE INDEX IF NOT EXISTS idx_conv_timestamp ON conversation_messages(timestamp);
```

### 보존 정책
- 기본 30일 보존. 주 1회 자동 정리 (APScheduler via scheduler.py)
- `orchestration.yaml`에 `conversation_history_retention_days: 30` 설정

### ContextDB 연결 패턴 유의
- 현재 ContextDB는 매 작업마다 새 `aiosqlite.connect()` 오픈 — 고빈도 캡처시 contention 위험
- 해결: 캡처 전용 `async with aiosqlite.connect(self.db_path) as db:` 블록 사용 (기존 패턴 유지)
- 향후 필요시 persistent connection pool로 마이그레이션

---

## Phase 2: BM25 검색 업그레이드

**파일:** `core/memory_manager.py`
**의존성:** `rank_bm25` (순수 Python, C 확장 없음)

### 설계 결정
- BM25 인덱스를 **두 소스** 통합: MemoryManager LOG 항목 + conversation_messages 테이블 쿼리 결과
- `search_memories(query, user_id, top_k=5)` 신규 메서드 추가
- 기존 `build_context()` 는 내부적으로 search_memories 호출로 개선
- 인덱스는 쿼리마다 rebuild (최대 30 LOG 항목 + 최근 100 conversation_messages → 성능 충분)

```python
async def search_memories(self, query: str, user_id: str, top_k: int = 5) -> list[str]:
    """BM25로 MemoryManager 로그 + 대화 이력 통합 검색."""
    from rank_bm25 import BM25Okapi
    entries = self._load_log_entries(scope="CORE")  # 최대 30
    # + conversation_messages에서 최근 100개 추가
    conv_entries = await self._load_conversation_entries(user_id, limit=100)
    corpus = entries + conv_entries
    tokenized = [e.split() for e in corpus]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(query.split())
    top_indices = sorted(range(len(corpus)), key=lambda i: scores[i], reverse=True)[:top_k]
    return [corpus[i] for i in top_indices]
```

### rank_bm25 설치 (CLAUDE.md 주의사항)
```bash
# pip install -e . 는 이 프로젝트에서 작동 안 함 (hatchling 설정 미비)
.venv/bin/pip install rank-bm25
```

---

## Phase 3: ProactiveHandler (MessageBus 확장)

**파일:** `core/message_bus.py`, `core/scheduler.py`, `core/proactive_handler.py` (신규)
**wiring:** `main.py` 시작 시 ProactiveHandler 등록

### 신규 이벤트 타입
```python
INACTIVITY_DETECTED = "inactivity_detected"  # N시간 침묵 후
DAILY_INSIGHT = "daily_insight"              # 매일 설정된 시각
```

### ProactiveHandler 위치 및 wiring
- 파일: `core/proactive_handler.py`
- `main.py`의 `start()` 메서드에서 `ProactiveHandler(message_bus, bots).register()` 호출

### 프로액티브 응답 결정 로직
각 봇의 구독 핸들러에서:
1. `active_hours` 범위 확인 (Phase 4)
2. 이벤트 타입에 따라 봇 역할 기반 응답 선택:
   - `INACTIVITY_DETECTED`: 코딩봇 → "현재 진행중인 작업 있나요?" / PM봇 → 팀 상태 요약
   - `DAILY_INSIGHT`: 코딩봇 → 어제 커밋 요약 / PM봇 → 당일 태스크 목록

### APScheduler와 MessageBus.publish (async) 연계
- scheduler.py의 `AsyncIOScheduler` 이미 asyncio 루프 인식
- `scheduler.add_job(lambda: asyncio.create_task(bus.publish(event)), 'interval', hours=N)`

### 비활동 감지 방식
- `conversation_messages` 테이블 최신 타임스탬프 폴링 (1시간마다)
- `orchestration.yaml`에 `inactivity_threshold_hours: 4` 설정

---

## Phase 4: active_hours 설정

**파일:** `bots/*.yaml`, `orchestration.yaml`

```yaml
# bots/cokac.yaml 예시
active_hours:
  start: 9   # 09:00 KST
  end: 22    # 22:00 KST
  timezone: "Asia/Seoul"
```

- **기본값 없을 때**: `active_hours` 미설정 = 24시간 활성 (항상 프로액티브 이벤트 수신)
- 글로벌 fallback: `orchestration.yaml`의 `default_active_hours`

---

## 드롭된 항목 (Architect 발견으로 제외)

| 항목 | 제외 이유 |
|------|-----------|
| Mem0 AsyncMemory | tmux-relay 아키텍처와 incompatible (system prompt 주입 불가) |
| Graphiti/Neo4j | 동일 이유 + over-engineered for current scale |
| BehaviorPredictor ML | active_hours 설정으로 충분, ML overkill |

---

## 테스트 전략

### 단위 테스트 (각 Phase)
- Phase 1: 테이블 생성, insert/query, pagination, is_bot 필터
- Phase 2: BM25 관련 결과 vs keyword mismatch, 두 소스 통합 검색
- Phase 3: 이벤트 발화, 핸들러 수신, active_hours 범위 밖 억제
- Phase 4: YAML 파싱, 기본값 폴리시

### E2E 검증
메시지 캡처 → conversation_messages → BM25 검색 결과에 포함 → INACTIVITY 이벤트 → ProactiveHandler 응답

### GlobalContext 관계 명확화
`core/global_context.py` 와 `conversation_messages` 테이블은 별개 역할:
- GlobalContext: 실시간 in-memory 공유 상태 (빠른 접근)
- conversation_messages: 영속 이력 저장 (검색/분석용)

---

## 구현 우선순위

| 순서 | Phase | 난이도 | 임팩트 |
|------|-------|--------|--------|
| 1 | Phase 1: conversation_messages | 낮음 | 기반 인프라 |
| 2 | Phase 2: BM25 검색 | 중간 | 검색 품질 향상 |
| 3 | Phase 3: ProactiveHandler | 중간 | 사용자 체감 |
| 4 | Phase 4: active_hours | 낮음 | 설정 완성 |
