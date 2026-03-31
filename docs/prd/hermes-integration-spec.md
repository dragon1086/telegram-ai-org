# Hermes 연동 인터페이스 명세서

**문서 ID**: HERMES-SPEC-v1.0
**작성일**: 2026-03-31
**작성자**: 기획실 (PM)
**상태**: DRAFT
**관련 PRD**: error-gotcha-PRD.md, pm-progress-tracker-PRD.md

---

## 1. 개요

### 1.1 배경

`core/` 하위 3개 Hermes 모듈(ToolRegistry·PlatformAdapter·ContextCompressor)은 코드 구현이 완료되고 feature flag가 `true`로 활성화됐지만, `bots/` 전체 어디에서도 `from core.hermes_integration import ...` 또는 개별 모듈 import가 **전무**하다.

`core/hermes_integration.py`가 연결 레이어로 존재하나, `register_hermes_tools()`에서 등록한 3개 도구는 모두 `handler=None`(Phase 1 스켈레톤)으로, 실제 디스패치 시 아무 동작도 수행하지 않는다.

### 1.2 목적

이 명세서는 다음을 정의한다:

1. Hermes 3개 모듈의 공개 인터페이스(메서드 시그니처·계약 조건)
2. `error-gotcha` 및 `pm-progress-tracker` 스킬 실행코드의 Hermes 연동 포인트
3. Phase 2 구현 시 반드시 충족해야 할 계약(Contract) 조건

### 1.3 모듈 위치

| 모듈명 | 파일 경로 | Feature Flag |
|--------|-----------|--------------|
| ToolRegistry | `core/tool_registry.py` | `ENABLE_TOOL_REGISTRY` (default=true) |
| PlatformAdapter | `core/platform_adapter.py` | `ENABLE_PLATFORM_ADAPTER` (default=true) |
| ContextCompressor | `core/context_compressor.py` | `ENABLE_CONTEXT_COMPRESSOR` (default=true) |
| HermesRuntime | `core/hermes_integration.py` | 위 3개 플래그 의존 |
| BotStateRepository | `core/repositories/bot_state_repository.py` | `ENABLE_REPOSITORY_PATTERN` (default=1) |

---

## 2. ToolRegistry 인터페이스 명세

### 2.1 클래스: `ToolRegistry`

**싱글턴 접근**: `from core.tool_registry import get_registry`

#### 2.1.1 `register()`

```python
def register(
    self,
    name: str,               # 필수 — 고유 도구 식별자
    description: str,        # 필수 — 1줄 설명
    handler: Optional[Callable[..., Any]] = None,  # 실행 함수 (Phase 2: 필수)
    tags: Optional[Set[str]] = None,               # capability 태그 집합
    schema: Optional[Dict[str, Any]] = None,       # JSON-schema (파라미터 검증용)
    enabled: bool = True,
) -> None
```

**계약 조건**:
- `name`이 빈 문자열이거나 `str`이 아니면 warning 로그 후 skip (예외 미발생)
- 중복 `name` 등록 시 warning 후 덮어씀 (overwrite)
- `ENABLE_TOOL_REGISTRY=false`이면 no-op
- Phase 2에서 스킬 핸들러 등록 시 `handler`는 반드시 callable이어야 함

#### 2.1.2 `dispatch()`

```python
def dispatch(self, name: str, **kwargs: Any) -> Any
```

**계약 조건**:
- flag off → None 반환 (no-op, 예외 없음)
- 도구 미존재 → warning + None 반환
- 도구 disabled → debug + None 반환
- handler=None → warning + None 반환 (현재 Phase 1 스켈레톤 상태)
- handler 예외 → 예외 **재발생** (caller가 처리)
- Phase 2 목표: 스킬 핸들러가 정상 등록된 후 예외를 skill-level로 감싸야 함

#### 2.1.3 `get_tools_by_tag()`

```python
def get_tools_by_tag(self, *tags: str) -> List[ToolEntry]
```

**계약 조건**:
- tags 미지정 시 전체 enabled 도구 반환
- 모든 tag를 포함하는 도구만 반환 (AND 조건)
- 정렬: name 기준 오름차순

#### 2.1.4 `ToolEntry` 데이터 구조

| 필드 | 타입 | 설명 |
|------|------|------|
| `name` | `str` | 고유 식별자 |
| `description` | `str` | 설명 |
| `handler` | `Optional[Callable]` | 실행 함수 (None=스텁) |
| `capability_tags` | `Set[str]` | 능력 태그 |
| `schema` | `Dict[str, Any]` | JSON-schema |
| `enabled` | `bool` | 활성화 여부 |

### 2.2 현재 등록된 Hermes 시스템 도구

| tool_name | tags | handler 상태 | 등록 위치 |
|-----------|------|-------------|-----------|
| `hermes_dispatch` | `{"hermes", "dispatch"}` | None (Phase 1 스텁) | `hermes_integration.py` |
| `hermes_compress_context` | `{"hermes", "compress_context"}` | None (Phase 1 스텁) | `hermes_integration.py` |
| `hermes_normalize_inbound` | `{"hermes", "normalize_inbound"}` | None (Phase 1 스텁) | `hermes_integration.py` |

**Phase 2 필수 작업**: 위 3개 도구의 `handler`를 실제 구현 함수로 교체.

---

## 3. PlatformAdapter 인터페이스 명세

### 3.1 클래스: `TelegramPlatformAdapter`

**싱글턴 접근**: `from core.platform_adapter import get_adapter`

#### 3.1.1 `normalize_inbound()`

```python
def normalize_inbound(self, raw_event: Any) -> Optional[InboundMessage]
```

**입력**: `telegram.Update` 객체 (또는 `.effective_message` / `.message` 속성 보유 객체)

**출력**: `InboundMessage` 또는 `None`

**InboundMessage 필드**:

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `platform` | `str` | ✓ | `"telegram"` |
| `message_id` | `str` | ✓ | 텔레그램 메시지 ID |
| `chat_id` | `str` | ✓ | 채팅방 ID (없으면 None 반환) |
| `sender_id` | `str` | ✓ | 발신자 user ID |
| `text` | `str` | ✓ | 메시지 텍스트 (미디어 전용이면 빈 문자열) |
| `raw` | `Any` | - | 원본 Update 객체 |
| `metadata` | `Dict` | - | 확장 필드 |

**계약 조건**:
- `chat_id` 없으면 `None` 반환
- `raw_event=None` → `None` 반환
- flag off → `None` 반환 (no-op)
- 내부 예외 → warning 로그 후 `None` 반환

#### 3.1.2 `send_message()`

```python
def send_message(self, message: OutboundMessage) -> bool
```

**OutboundMessage 필드**:

| 필드 | 타입 | 기본값 | 설명 |
|------|------|--------|------|
| `chat_id` | `str` | 필수 | 수신자 채팅방 ID |
| `text` | `str` | 필수 | 메시지 본문 |
| `reply_to_message_id` | `Optional[str]` | `None` | 답장 대상 메시지 ID |
| `parse_mode` | `str` | `"HTML"` | 포맷 모드 |
| `metadata` | `Dict` | `{}` | 확장 필드 |

**계약 조건**:
- `chat_id` 또는 `text` 빈 문자열 → warning + `False` 반환
- `bot_sender=None` → warning + `False` 반환 (생성자에 `bot_sender` 주입 필요)
- 전송 예외 → error 로그 + `False` 반환 (예외 미전파)

#### 3.1.3 모듈 레벨 함수

```python
def register_adapter(adapter: PlatformAdapter) -> None
def get_adapter(platform_name: str) -> Optional[PlatformAdapter]  # flag off → None
def list_adapters() -> List[str]  # flag off → []
```

---

## 4. ContextCompressor 인터페이스 명세

### 4.1 클래스: `ContextCompressor`

**싱글턴 접근**: `from core.context_compressor import get_compressor`

#### 4.1.1 `compress()`

```python
def compress(
    self,
    messages: list[dict],   # 필수 — [{"role": "...", "content": "..."}, ...]
    max_tokens: int,         # 필수 — 압축 후 목표 토큰 상한
    keep_last_n: int = 4,    # 선택 — 항상 보존할 최근 non-system 메시지 수
) -> list[dict]
```

**압축 전략 (3계층 우선순위)**:
1. `role=="system"` 메시지 전체 보존 (제거 불가)
2. 마지막 `keep_last_n`개 non-system 메시지 보존
3. 남은 토큰 예산 내에서 older 메시지를 최신순으로 채움

**계약 조건**:
- flag off → 원본 `messages` 그대로 반환 (no-op)
- `messages=[]` → `[]` 반환
- `max_tokens <= 0` → `[]` 반환
- mandatory 합계 > `max_tokens` → mandatory만 반환 (보존 우선)
- 반환 순서: 원본 시간순 유지

**트리거 임계값 (PRD 정의)**:
| 트리거 유형 | 조건 | 기본값 |
|------------|------|--------|
| 토큰 임계값 | 누적 토큰 >= max_tokens | 8,000 tokens |
| 메시지 수 | non-system 메시지 >= N | 20개 |
| 수동 호출 | 스킬 내부에서 직접 호출 | - |

#### 4.1.2 `estimate_tokens()`

```python
def estimate_tokens(self, text: str) -> int
```

- feature flag와 무관하게 항상 동작
- tiktoken 사용 가능 시 정확한 값, 없으면 CJK/ASCII 휴리스틱 사용

---

## 5. HermesRuntime 인터페이스 명세

### 5.1 클래스: `HermesRuntime`

**싱글턴 접근**: `from core.hermes_integration import get_hermes_runtime`

#### 5.1.1 `on_init()`

```python
def on_init(self, bot_sender: Optional[Callable[..., Any]] = None) -> None
```

**계약 조건**:
- ToolRegistry 초기화 + Hermes 시스템 도구 3개 등록
- TelegramPlatformAdapter 인스턴스화 + `register_adapter()` 호출
- `bot_sender`: `send_message(chat_id, text, parse_mode, reply_to_message_id)` 시그니처 callable
- 실패해도 예외 전파 없음 (no-op 안전)

#### 5.1.2 `on_message()`

```python
def on_message(self, raw_event: Any) -> Optional[InboundMessage]
```

**계약 조건**:
- `on_init()` 미호출 시 → None 반환
- 내부적으로 `TelegramPlatformAdapter.normalize_inbound()` 위임

#### 5.1.3 `on_teardown()`

```python
def on_teardown(self) -> None
```

**계약 조건**:
- `adapter.on_shutdown()` 호출
- `_initialized = False`, `_registry = None`, `_adapter = None` 리셋

---

## 6. BotStateRepository 인터페이스 명세

### 6.1 클래스: `BotStateRepository`

**Feature Flag**: `ENABLE_REPOSITORY_PATTERN` (기본값 `"1"`)

**DB 스키마**:
```sql
CREATE TABLE IF NOT EXISTS bot_states (
    bot_id     TEXT    PRIMARY KEY,
    state      TEXT    NOT NULL DEFAULT '{}',  -- JSON
    is_alive   INTEGER NOT NULL DEFAULT 1,
    updated_at REAL    NOT NULL                -- time.time() float
);
```

#### 6.1.1 공개 메서드 요약

| 메서드 | 시그니처 | 반환 | flag off 동작 |
|--------|---------|------|---------------|
| `initialize()` | `async def initialize() -> None` | None | no-op |
| `get_state()` | `async def get_state(bot_id: str) -> dict \| None` | 상태 dict 또는 None | None |
| `update_state()` | `async def update_state(bot_id: str, state: dict) -> None` | None | no-op |
| `get_all_alive()` | `async def get_all_alive() -> list[dict]` | alive 봇 목록 | [] |
| `mark_dead()` | `async def mark_dead(bot_id: str) -> None` | None | no-op |

#### 6.1.2 `get_state()` 반환 구조

```python
{
    "bot_id": str,          # 봇 식별자
    "state": dict,          # JSON 파싱된 상태 딕셔너리
    "is_alive": bool,       # True/False
    "updated_at": float,    # time.time() UNIX timestamp
}
```

#### 6.1.3 스킬과의 상태 동기화 정책

| 스킬 | 호출 전 | 호출 후 | 실패 시 |
|------|---------|---------|---------|
| error-gotcha | 필요 없음 (파일 기반) | 선택 (gotcha_count 증가) | 무시 (비필수) |
| pm-progress-tracker | `get_state()` — 현재 목표 조회 | `update_state()` — 진척률 갱신 | warning 로그, 메모리 파일 폴백 |

---

## 7. 스킬-Hermes 연동 포인트 매핑표

### 7.1 error-gotcha

| Hermes 모듈 | 연동 포인트 | 연동 방식 | Phase 2 구현 필요 |
|-------------|-----------|---------|-----------------|
| ToolRegistry | `add` 명령 진입 시 도구 조회 | `registry.dispatch("hermes_dispatch", ...)` | ✅ handler 구현 필요 |
| PlatformAdapter | 텔레그램 명령 수신 정규화 | `runtime.on_message(update)` → `InboundMessage.text` 파싱 | ✅ on_init 호출 필요 |
| ContextCompressor | gotcha 본문 생성 시 컨텍스트 압축 | `compressor.compress(messages, max_tokens=4000)` | ✅ 선택적 |
| BotStateRepository | gotcha 추가 후 상태 갱신 | `repo.update_state(bot_id, {"last_gotcha": ...})` | 🔵 선택 |

### 7.2 pm-progress-tracker

| Hermes 모듈 | 연동 포인트 | 연동 방식 | Phase 2 구현 필요 |
|-------------|-----------|---------|-----------------|
| ToolRegistry | `start`/`done`/`status` 명령 라우팅 | `registry.dispatch("hermes_dispatch", target_org=...)` | ✅ handler 구현 필요 |
| PlatformAdapter | 텔레그램 목표 수신 정규화 | `runtime.on_message(update)` → `InboundMessage.text` 파싱 | ✅ on_init 호출 필요 |
| ContextCompressor | `report` 명령 시 긴 컨텍스트 압축 | `compressor.compress(messages, max_tokens=8000, keep_last_n=6)` | ✅ 필수 |
| BotStateRepository | `status` 조회 시 현재 봇 상태 반영 | `repo.get_state(bot_id)` → 상태 병합 출력 | ✅ 필수 |

---

## 8. Phase 2 구현 우선순위

| 우선순위 | 작업 | 영향 범위 |
|---------|------|---------|
| 🔴 P1 | `hermes_integration.py` `handler=None` 3개를 실제 함수로 교체 | 전체 Hermes 디스패치 |
| 🔴 P1 | `bots/` 봇 시작 시 `HermesRuntime.on_init(bot_sender=...)` 호출 | 플랫폼 정규화 활성화 |
| 🟡 P2 | `error-gotcha/run.py` ToolRegistry 조회 경로 추가 | error-gotcha 스킬 |
| 🟡 P2 | `pm-progress-tracker/run.py` BotStateRepository 상태 동기화 | pm-progress-tracker 스킬 |
| 🟢 P3 | ContextCompressor `report` 명령 연동 | pm-progress-tracker 스킬 |

---

## 9. 미결 사항 (Open Questions)

| # | 질문 | 영향 결정 |
|---|------|---------|
| OQ-1 | `hermes_dispatch` handler가 실제로 어떤 함수를 래핑해야 하는가? `DispatchService` 스터브인가, 직접 COLLAB 파서인가? | P1 핸들러 구현 설계 |
| OQ-2 | `on_init(bot_sender=...)` 주입 시점: 봇 시작 시 1회인가, 메시지마다인가? | HermesRuntime 수명 주기 |
| OQ-3 | ContextCompressor의 `max_tokens` 기본값: 스킬마다 다르게 설정할 것인가, 글로벌 상수로 통일할 것인가? | 설정 관리 |
| OQ-4 | BotStateRepository `db_path`를 스킬 내부에서 직접 인스턴스화할 것인가, 싱글턴 주입 방식으로 할 것인가? | 의존성 주입 패턴 |
