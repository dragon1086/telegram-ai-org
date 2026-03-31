# PRD: error-gotcha 스킬 실행코드

**문서 ID**: PRD-SKILL-001
**버전**: v1.0
**작성일**: 2026-03-31
**작성자**: 기획실 (PM)
**상태**: DRAFT
**관련 명세**: hermes-integration-spec.md

---

## 1. 개요

### 1.1 배경

`skills/error-gotcha/scripts/run.py`는 에러 수정 후 관련 스킬의 `gotchas.md`에 재발 방지 항목을 자동 추가하는 CLI 스크립트다. 현재 구현은 완전한 파일 기반 동작(CLI `add`/`list` 명령)을 갖추고 있으나, 다음 두 가지 연결이 누락된 **껍데기 상태**다:

1. **Hermes ToolRegistry 미연결**: 텔레그램 `/error-gotcha` 명령 수신 시 ToolRegistry를 통한 도구 조회·실행 경로가 없음
2. **PlatformAdapter 미연결**: 텔레그램 Update 객체를 정규화된 `InboundMessage`로 변환하는 경로 없음

### 1.2 목적

이 PRD는 `error-gotcha` 스킬이 다음을 달성하도록 Phase 2 구현 요구사항을 정의한다:

- 텔레그램 메시지 → Hermes PlatformAdapter 정규화 → error-gotcha 핸들러 실행
- ToolRegistry에 `error_gotcha_add` / `error_gotcha_list` 도구 등록
- BotStateRepository와 선택적 상태 동기화

### 1.3 범위

**포함**:
- `run.py` CLI의 Hermes ToolRegistry 연동
- PlatformAdapter를 통한 텔레그램 입력 정규화
- BotStateRepository 선택적 상태 동기화

**제외**:
- `gotchas.md` 파일 형식 변경
- `skills/` 디렉토리 구조 변경
- 다른 스킬의 gotcha 자동 탐지 로직

### 1.4 관련 모듈

| 모듈 | 경로 | 역할 |
|------|------|------|
| ToolRegistry | `core/tool_registry.py` | 스킬 핸들러 등록·디스패치 |
| PlatformAdapter | `core/platform_adapter.py` | 텔레그램 이벤트 정규화 |
| ContextCompressor | `core/context_compressor.py` | (선택) gotcha 본문 생성 시 컨텍스트 압축 |
| BotStateRepository | `core/repositories/bot_state_repository.py` | gotcha 통계 상태 저장 |
| HermesRuntime | `core/hermes_integration.py` | 3개 모듈 통합 진입점 |

---

## 2. 입력 스펙

### 2.1 CLI 입력 파라미터 (현재 구현)

#### `add` 명령

| 파라미터 | 타입 | 필수 | 기본값 | 유효성 검증 |
|---------|------|------|--------|------------|
| `--error` / `-e` | `str` | ✅ | - | 비어있지 않은 문자열 |
| `--cause` / `-c` | `str` | ✅ | - | 비어있지 않은 문자열 |
| `--fix` / `-x` | `str` | ✅ | - | 비어있지 않은 문자열 |
| `--file` / `-f` | `str` | ❌ | `"unknown"` | 임의 문자열 허용 |
| `--skill` / `-s` | `str` | ❌ | None (auto-detect) | `skills/` 하위 디렉토리명이어야 함 |
| `--title` / `-t` | `str` | ❌ | `"{error}: {cause[:40]}"` | 임의 문자열 허용 |

#### `list` 명령

| 파라미터 | 타입 | 필수 | 기본값 | 유효성 검증 |
|---------|------|------|--------|------------|
| `--skill` / `-s` | `str` | ❌ | None (전체) | `skills/` 하위 디렉토리명이어야 함 |

### 2.2 Hermes ToolRegistry 입력 스펙 (Phase 2 신규)

#### `error_gotcha_add` 도구

```json
{
  "type": "object",
  "properties": {
    "error_type":  {"type": "string", "description": "예외 클래스명 (예: NameError)"},
    "file_path":   {"type": "string", "description": "에러 발생 파일 경로", "default": "unknown"},
    "cause":       {"type": "string", "description": "근본 원인 (1줄)"},
    "fix":         {"type": "string", "description": "수정 내용 (1줄)"},
    "title":       {"type": "string", "description": "Gotcha 제목 (미지정 시 자동 생성)"},
    "skill":       {"type": "string", "description": "대상 스킬명 (미지정 시 error_type으로 자동 매핑)"}
  },
  "required": ["error_type", "cause", "fix"]
}
```

#### `error_gotcha_list` 도구

```json
{
  "type": "object",
  "properties": {
    "skill": {"type": "string", "description": "특정 스킬만 조회 (미지정 시 전체)"}
  },
  "required": []
}
```

### 2.3 PlatformAdapter 정규화 입력

텔레그램 사용자가 다음 형식으로 메시지를 보낼 때 PlatformAdapter가 `InboundMessage`로 변환:

```
/error-gotcha add --error NameError --cause "변수 미선언" --fix "함수 상단 선언 추가"
```

`InboundMessage.text` 파싱 규칙:
- `--error` → `error_type`
- `--cause` → `cause`
- `--fix` → `fix`
- `--skill` → `skill` (선택)
- `--file` → `file_path` (선택)

---

## 3. 출력 스펙

### 3.1 성공 응답 구조

#### `add` 명령 성공

```python
{
    "status": "success",
    "gotcha_num": int,          # 추가된 Gotcha 번호 (예: 3)
    "target_skill": str,        # 대상 스킬명 (예: "engineering-review")
    "gotchas_path": str,        # gotchas.md 파일 경로
    "title": str,               # Gotcha 제목
    "message": str,             # 사용자 표시 메시지 (예: "✅ Gotcha 3 추가 완료")
}
```

#### `list` 명령 성공

```python
{
    "status": "success",
    "total_count": int,         # 전체 Gotcha 수
    "by_skill": {               # 스킬별 Gotcha 목록
        "engineering-review": ["## Gotcha 1: ...", "## Gotcha 2: ..."],
        "quality-gate": ["## Gotcha 1: ..."],
    }
}
```

### 3.2 오류 응답 구조

| 에러 코드 | 메시지 | 복구 힌트 |
|---------|--------|---------|
| `ERR_SKILL_NOT_FOUND` | `"스킬 디렉토리 없음: {skill_name}"` | 사용 가능한 스킬 목록 출력 |
| `ERR_MISSING_REQUIRED` | `"필수 파라미터 누락: {param_name}"` | 사용법 예시 출력 |
| `ERR_FILE_WRITE` | `"gotchas.md 쓰기 실패: {path}"` | 권한 확인 안내 |
| `ERR_REGISTRY_DISABLED` | `"ToolRegistry 비활성화 (ENABLE_TOOL_REGISTRY=false)"` | 환경변수 확인 안내 |
| `ERR_ADAPTER_DISABLED` | `"PlatformAdapter 비활성화"` | 환경변수 확인 안내 |

---

## 4. 트리거 조건

### 4.1 사용자 명령 기반

| 트리거 | 입력 형식 | 처리 경로 |
|--------|---------|---------|
| 텔레그램 `/error-gotcha add ...` | PlatformAdapter → ToolRegistry → handler | Hermes 연동 경로 |
| Claude 에이전트 `[skill:error-gotcha]` | SKILL.md 절차 → `run.py add ...` | 직접 CLI 실행 |
| 직접 CLI 실행 | `python run.py add ...` | 직접 CLI 실행 |

### 4.2 자동 트리거 (이벤트 기반)

| 트리거 | 조건 | 처리 |
|--------|------|------|
| 런타임 에러 발생 후 | `NameError` / `ImportError` / `UnboundLocalError` / `AttributeError` 수정 완료 | 에러 수정 직후 에이전트가 자동 실행 |
| 같은 에러 재발 | 동일 에러 타입 2회 이상 발생 | 에이전트가 gotcha 추가 권고 |
| 봇 crash 수정 후 | 봇 재시작 완료 + 원인 파악 | `bot-triage` 스킬 완료 후 체이닝 |

### 4.3 스킬 체이닝

| 선행 스킬 | 체이닝 조건 | 이후 처리 |
|---------|-----------|---------|
| `quality-gate` FAIL | 코드 수정 후 재통과 | 원인 에러 gotcha 자동 추가 |
| `bot-triage` | 봇 장애 원인 분석 완료 | 원인별 gotcha 추가 |
| `engineering-review` | 에러 수정 완료 보고 | gotcha 추가 권고 |

---

## 5. 실패 처리 정책

| 항목 | 값 | 비고 |
|------|-----|------|
| 타임아웃 | 10초 | CLI 실행 기준 |
| 재시도 횟수 | 0회 (재시도 없음) | 파일 쓰기 실패는 즉시 오류 보고 |
| 폴백 동작 | stdout 출력 후 `sys.exit(1)` | Hermes 미연결 시 CLI 직접 실행으로 폴백 |
| 에러 로깅 레벨 | 스킬 미존재: `ERROR` / 파일 쓰기: `ERROR` / flag off: `DEBUG` | |
| 사용자 알림 | stdout에 `❌ 에러 메시지` 출력 | 텔레그램 경유 시 `OutboundMessage`로 전달 |

---

## 6. 기능 요구사항 (FR)

### Must Have

| ID | 요구사항 | 분류 |
|----|---------|------|
| FR-001 | `add` 명령: `error_type`, `cause`, `fix` 필수 파라미터 검증 후 gotchas.md에 항목 추가 | Must Have |
| FR-002 | `error_type`으로 대상 스킬 자동 매핑 (ERROR_TO_SKILL 테이블 사용) | Must Have |
| FR-003 | 중복 gotcha 방지: 동일 근본 원인 gotcha 존재 시 신규 추가 안 함 | Must Have |
| FR-004 | `list` 명령: 전체 또는 특정 스킬의 gotcha 목록 출력 | Must Have |
| FR-005 | ToolRegistry에 `error_gotcha_add` / `error_gotcha_list` 도구 등록 | Must Have |
| FR-006 | PlatformAdapter를 통한 텔레그램 메시지 정규화 후 핸들러 연결 | Must Have |

### Should Have

| ID | 요구사항 | 분류 |
|----|---------|------|
| FR-007 | `--skill` 미지정 시 `error_type`으로 자동 스킬 매핑 | Should Have |
| FR-008 | 대상 스킬 디렉토리 미존재 시 사용 가능한 스킬 목록 제안 | Should Have |
| FR-009 | BotStateRepository에 `last_gotcha_at` / `gotcha_count` 갱신 | Should Have |

### Nice to Have

| ID | 요구사항 | 분류 |
|----|---------|------|
| FR-010 | ContextCompressor로 긴 에러 메시지 본문 4,000 토큰 이내 압축 | Nice to Have |
| FR-011 | `skill-evolve` 스킬과 연계해 gotcha 패턴 분석 | Nice to Have |

---

## 7. 비기능 요구사항

| 항목 | 요구사항 |
|------|---------|
| 응답시간 SLA | CLI: 3초 이내 / Hermes ToolRegistry 경유: 5초 이내 |
| 동시 호출 한도 | 단일 프로세스 기준 동시성 없음 (CLI 순차 실행) |
| 로그 보존 기간 | gotchas.md 영구 보존 / BotStateRepository 90일 |
| 보안 요구사항 | gotchas.md 파일 시스템 쓰기는 PROJECT_ROOT 내부로 한정 |
| 호환성 | Python 3.11+ / Python 3.14 호환 (타입 힌트 `list[dict]` 사용) |

---

## 8. Hermes 연동 요구사항

### 8.1 ToolRegistry 연동

**등록 인터페이스**:
```python
registry.register(
    name="error_gotcha_add",
    description="에러 수정 후 관련 스킬 gotchas.md에 재발 방지 항목 추가",
    handler=error_gotcha_add_handler,  # Phase 2: cmd_add() 래핑 함수
    tags={"skill", "error-gotcha", "add"},
    schema=ERROR_GOTCHA_ADD_SCHEMA,
    enabled=True,
)
```

**handler 계약**:
- `**kwargs` 형식으로 `error_type`, `cause`, `fix`, `file_path`, `skill`, `title` 수신
- 성공 시 `dict` 반환 (3.1 출력 스펙)
- 실패 시 예외 발생 (ToolRegistry가 `error` 로그 후 재발생)

### 8.2 PlatformAdapter 연동

**정규화 흐름**:
```
telegram.Update
    → runtime.on_message(update)
    → TelegramPlatformAdapter.normalize_inbound()
    → InboundMessage(text="/error-gotcha add --error NameError ...")
    → 파서: text 파싱 → kwargs 추출
    → registry.dispatch("error_gotcha_add", **kwargs)
```

**계약 조건**:
- `HermesRuntime.on_init(bot_sender=...)` 봇 시작 시 1회 호출 필수
- `InboundMessage.text`가 None이거나 빈 문자열이면 처리 skip

### 8.3 ContextCompressor 연동 (선택)

```python
compressor = get_compressor()
compressed_messages = compressor.compress(
    messages=conversation_history,
    max_tokens=4000,
    keep_last_n=4,
)
```

**트리거 조건**: 에러 메시지 본문이 1,000 tokens 초과 시

---

## 9. BotStateRepository 상태 동기화

| 시점 | 메서드 | 저장 내용 |
|------|--------|---------|
| `add` 명령 성공 후 | `update_state(bot_id, {...})` | `{"last_gotcha_at": ISO8601, "gotcha_count": N, "last_gotcha_skill": "engineering-review"}` |
| `list` 명령 실행 | 없음 (읽기 전용 조작) | - |
| `add` 명령 실패 시 | 없음 (상태 미변경) | - |

---

## 10. 예외 및 엣지케이스

| # | 케이스 | 기대 동작 |
|---|--------|---------|
| EC-01 | `--skill` 지정했으나 해당 디렉토리 없음 | `ERR_SKILL_NOT_FOUND` 오류 + 사용 가능 스킬 목록 출력 |
| EC-02 | gotchas.md 파일 없음 (최초 실행) | 파일 자동 생성 후 항목 추가 |
| EC-03 | 동일 근본 원인 gotcha 이미 존재 | 신규 추가 안 함 + 기존 항목 번호 출력 |
| EC-04 | `ENABLE_TOOL_REGISTRY=false` | CLI 직접 실행 폴백 (ToolRegistry 없이 동작) |
| EC-05 | `ENABLE_PLATFORM_ADAPTER=false` | CLI 직접 실행 폴백 |
| EC-06 | `cause` 또는 `fix` 파라미터 누락 | argparse 오류 메시지 + sys.exit(1) |
| EC-07 | PROJECT_ROOT 외부 경로로 gotchas.md 접근 시도 | 경로 검증 실패 → 오류 반환 |
| EC-08 | HermesRuntime.on_init() 미호출 상태에서 dispatch 시도 | `on_message()` None 반환 → CLI 폴백 |

---

## 11. 수용 기준 (Acceptance Criteria)

### FR-001: add 명령 gotcha 추가

**Given** 사용자가 `add --error NameError --cause "변수 미선언" --fix "함수 상단 선언"` 실행 시
**When** run.py가 실행되면
**Then** `skills/engineering-review/gotchas.md`에 `## Gotcha N:` 형식 항목이 추가되고 "✅ Gotcha N 추가 완료" 출력

### FR-003: 중복 방지

**Given** `cause`가 동일한 gotcha가 이미 존재할 때
**When** 동일 `cause`로 add 명령 실행 시
**Then** 새 항목이 추가되지 않고 기존 Gotcha 번호를 출력

### FR-005: ToolRegistry 등록

**Given** `HermesRuntime.on_init()` 호출 후
**When** `registry.get("error_gotcha_add")` 호출 시
**Then** `ToolEntry.handler is not None` (Phase 2 완료 기준)

### FR-006: PlatformAdapter 연동

**Given** 텔레그램 Update 객체가 `/error-gotcha add --error NameError --cause "X" --fix "Y"` 텍스트를 포함할 때
**When** `runtime.on_message(update)` 호출 시
**Then** `InboundMessage.text`가 올바르게 파싱되고 `registry.dispatch("error_gotcha_add", ...)` 호출됨

---

## 12. 미결 사항 (Open Questions)

| # | 질문 | 영향 |
|---|------|------|
| OQ-1 | 중복 감지 기준: `cause` 완전 일치인가, 유사도 임계값인가? | FR-003 구현 방식 |
| OQ-2 | `error_gotcha_add` handler가 async여야 하는가? BotStateRepository가 async임 | 핸들러 구현 복잡도 |
| OQ-3 | 텔레그램 명령 파서를 별도 모듈로 분리할 것인가? | 재사용성 |

## 13. 의존성 목록

| 의존 항목 | 유형 | 상태 |
|---------|------|------|
| `core/tool_registry.py` | 내부 모듈 | ✅ 구현 완료 |
| `core/platform_adapter.py` | 내부 모듈 | ✅ 구현 완료 |
| `core/hermes_integration.py` | 내부 모듈 | ⚠️ handler=None 스텁 |
| `core/repositories/bot_state_repository.py` | 내부 모듈 | ✅ 구현 완료 |
| `aiosqlite` | 외부 패키지 | ✅ 설치됨 |
| `skills/*/gotchas.md` | 파일 시스템 | ✅ 존재 |
