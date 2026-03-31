# PRD: pm-progress-tracker 스킬 실행코드

**문서 ID**: PRD-SKILL-002
**버전**: v1.0
**작성일**: 2026-03-31
**작성자**: 기획실 (PM)
**상태**: DRAFT
**관련 명세**: hermes-integration-spec.md

---

## 1. 개요

### 1.1 배경

`skills/pm-progress-tracker/scripts/run.py`는 PM 목표 진척 현황을 조회하고 이터레이션 루프를 관리하는 CLI 스크립트다. `status`, `list`, `start`, `done`, `report` 5개 명령을 완전하게 구현하고 있으나, 다음 두 가지 연결이 누락된 **껍데기 상태**다:

1. **Hermes ToolRegistry 미연결**: `start`/`done`/`report` 명령이 다부서 디스패치를 ToolRegistry를 통해 실행하지 않음
2. **BotStateRepository 미연결**: 목표 진척률이 메모리 파일에만 저장되고 BotStateRepository에 동기화되지 않아 봇 재시작 시 컨텍스트 손실

또한 `daily_goal_pipeline` 크론 발동 시 자동 iter 재개가 정의돼 있으나 실제 실행 코드가 없다.

### 1.2 목적

이 PRD는 `pm-progress-tracker` 스킬이 다음을 달성하도록 Phase 2 구현 요구사항을 정의한다:

- ToolRegistry를 통한 `hermes_dispatch` 호출로 다부서 태스크 실행
- PlatformAdapter를 통한 텔레그램 목표 수신·정규화
- ContextCompressor를 통한 긴 진척 보고서 압축
- BotStateRepository와 목표 상태 동기화

### 1.3 범위

**포함**:
- Hermes ToolRegistry `pm_progress_*` 도구 등록
- PlatformAdapter 연동 (텔레그램 명령 → InboundMessage)
- BotStateRepository 상태 동기화 (`start`/`done`/`status`)
- ContextCompressor `report` 명령 연동
- `daily_goal_pipeline` 크론 트리거 연동 스펙

**제외**:
- `memory/pm_progress_guide.md` 파일 형식 변경
- 다른 봇으로의 실제 COLLAB 메시지 전송 구현 (DispatchService 담당)
- quality-gate 스킬 직접 구현

### 1.4 관련 모듈

| 모듈 | 경로 | 역할 |
|------|------|------|
| ToolRegistry | `core/tool_registry.py` | 스킬 핸들러 등록·디스패치 |
| PlatformAdapter | `core/platform_adapter.py` | 텔레그램 이벤트 정규화 |
| ContextCompressor | `core/context_compressor.py` | 긴 보고서 컨텍스트 압축 |
| BotStateRepository | `core/repositories/bot_state_repository.py` | 목표 상태 동기화 |
| HermesRuntime | `core/hermes_integration.py` | 3개 모듈 통합 진입점 |

---

## 2. 입력 스펙

### 2.1 CLI 입력 파라미터 (현재 구현)

| 명령 | 추가 인자 | 필수 | 설명 |
|------|---------|------|------|
| `status` | 없음 | - | 현재 진척 현황 출력 |
| `list` | 없음 | - | 전체 목표 목록 출력 |
| `start` | `<목표명>` | ✅ | 새 목표 등록 (문자열) |
| `done` | `<목표명>` | ✅ | 목표 DONE 처리 (IN_PROGRESS인 목표명과 정확히 일치) |
| `report` | 없음 | - | 진척 보고서 생성 |

**유효성 검증 규칙**:

| 파라미터 | 검증 규칙 |
|---------|---------|
| `start <목표명>` | 비어있지 않은 문자열. 최대 200자 권장. |
| `done <목표명>` | 비어있지 않은 문자열. `pm_progress_guide.md`에서 IN_PROGRESS 상태로 존재해야 함. |

### 2.2 Hermes ToolRegistry 입력 스펙 (Phase 2 신규)

#### `pm_progress_start` 도구

```json
{
  "type": "object",
  "properties": {
    "goal_name":     {"type": "string", "description": "등록할 목표명"},
    "owner":         {"type": "string", "description": "주담당 부서 (예: 개발실)", "default": ""},
    "collaborators": {"type": "array",  "items": {"type": "string"},
                      "description": "협업 부서 목록", "default": []},
    "deadline":      {"type": "string", "description": "완료 목표일 YYYY-MM-DD", "default": ""},
    "done_criteria": {"type": "string", "description": "완료 조건 (검증 가능한 기준)", "default": ""}
  },
  "required": ["goal_name"]
}
```

#### `pm_progress_done` 도구

```json
{
  "type": "object",
  "properties": {
    "goal_name": {"type": "string", "description": "완료 처리할 목표명 (IN_PROGRESS 상태)"}
  },
  "required": ["goal_name"]
}
```

#### `pm_progress_status` 도구

```json
{
  "type": "object",
  "properties": {
    "bot_id": {"type": "string", "description": "조회할 봇 ID (미지정 시 전체)", "default": ""}
  },
  "required": []
}
```

#### `pm_progress_report` 도구

```json
{
  "type": "object",
  "properties": {
    "max_tokens": {"type": "integer", "description": "보고서 최대 토큰 수", "default": 8000},
    "keep_last_n": {"type": "integer", "description": "최근 N개 이터레이션 보존", "default": 6}
  },
  "required": []
}
```

### 2.3 PlatformAdapter 정규화 입력

텔레그램 사용자 메시지 형식:

```
/pm-progress start 오픈소스화 패키징
/pm-progress done 오픈소스화 패키징
/pm-progress status
/pm-progress report
```

`InboundMessage.text` 파싱 규칙:
- `/pm-progress start <나머지>` → `goal_name = 나머지`
- `/pm-progress done <나머지>` → `goal_name = 나머지`
- `/pm-progress status` → `pm_progress_status` 도구 호출
- `/pm-progress report` → `pm_progress_report` 도구 호출

---

## 3. 출력 스펙

### 3.1 성공 응답 구조

#### `start` 명령 성공

```python
{
    "status": "success",
    "goal_id": str,        # 예: "GOAL-003"
    "goal_name": str,      # 등록된 목표명
    "state": "IN_PROGRESS",
    "created_at": str,     # ISO8601 날짜
    "guide_file": str,     # pm_progress_guide.md 경로
    "message": str,        # "✅ 목표 등록 완료: GOAL-003 — 오픈소스화"
}
```

#### `done` 명령 성공

```python
{
    "status": "success",
    "goal_name": str,
    "state": "DONE",
    "completed_at": str,   # ISO8601 날짜
    "message": str,        # "✅ 목표 완료 처리: ... → DONE"
}
```

#### `status` 명령 성공

```python
{
    "status": "success",
    "as_of": str,                    # ISO8601 날짜시간
    "in_progress_goals": list[str],  # 진행 중 목표명 목록
    "active_task_count": int,        # 활성 태스크 수
    "active_tasks": list[str],       # 활성 태스크 목록 (최대 5개)
    "bot_states": list[dict],        # BotStateRepository alive 봇 목록
}
```

#### `report` 명령 성공

```python
{
    "status": "success",
    "generated_at": str,    # ISO8601 날짜시간
    "total": int,
    "done": int,
    "done_pct": int,        # 0~100
    "in_progress": int,
    "blocked": int,
    "report_text": str,     # 최종 보고서 텍스트 (ContextCompressor 적용 후)
    "compressed": bool,     # 압축 적용 여부
}
```

### 3.2 오류 응답 구조

| 에러 코드 | 메시지 | 복구 힌트 |
|---------|--------|---------|
| `ERR_GOAL_NOT_FOUND` | `"목표 '{goal_name}'을 IN_PROGRESS 상태에서 찾을 수 없음"` | `list` 명령으로 현재 목표 목록 확인 |
| `ERR_MISSING_GOAL_NAME` | `"목표명 필수. 예: run.py start '오픈소스화 패키징'"` | 사용법 출력 |
| `ERR_GUIDE_FILE_NOT_FOUND` | `"pm_progress_guide.md 없음"` | `start` 명령으로 첫 목표 등록 |
| `ERR_FILE_WRITE` | `"파일 쓰기 실패: {path}"` | 권한 확인 |
| `ERR_REGISTRY_DISABLED` | `"ToolRegistry 비활성화"` | 환경변수 확인 |
| `ERR_REPO_UNAVAILABLE` | `"BotStateRepository 연결 실패"` | 파일 기반 폴백으로 계속 |

---

## 4. 트리거 조건

### 4.1 사용자 명령 기반

| 트리거 | 입력 형식 | 처리 경로 |
|--------|---------|---------|
| 텔레그램 `/pm-progress start ...` | PlatformAdapter → ToolRegistry → handler | Hermes 연동 경로 |
| Claude 에이전트 `[skill:pm-progress-tracker]` | SKILL.md 절차 → `run.py <명령>` | 직접 CLI 실행 |
| 직접 CLI 실행 | `python run.py <명령>` | 직접 CLI 실행 |

### 4.2 자동 트리거 (크론·이벤트)

| 트리거 | 조건 | 처리 |
|--------|------|------|
| `daily_goal_pipeline` 크론 | 매일 지정 시각 (현재 미구현) | IN_PROGRESS 목표 조회 → 잔여 TODO 배분 |
| STALE 목표 감지 | 3일 이상 진척 없음 | PM 봇에 알림 + 재개 권고 |
| 이터레이션 완료 | 모든 서브태스크 DONE | 완료 조건 검증 → 완료 처리 또는 재루프 |

**크론 스펙** (Phase 2 구현 대상):
```yaml
# orchestration.yaml에 추가 필요
daily_goal_pipeline:
  schedule: "0 9 * * 1-5"    # 평일 09:00 KST
  trigger: pm_progress_status → iterate_remaining_tasks
  timeout: 300s
```

### 4.3 스킬 체이닝

| 선행 스킬 | 체이닝 조건 | 이후 처리 |
|---------|-----------|---------|
| `pm-task-dispatch` | 태스크 배분 완료 | 해당 태스크 IN_PROGRESS → 완료 대기 |
| `quality-gate` PASS | 코드 변경 태스크 | 해당 서브태스크 DONE 처리 |
| `quality-gate` FAIL | 코드 변경 태스크 | 개발실 재배분 후 루프 |
| `error-gotcha` | 에러 수정 완료 | 해당 태스크 진척률 갱신 |

---

## 5. 실패 처리 정책

| 항목 | 값 | 비고 |
|------|-----|------|
| 타임아웃 | 30초 (report 명령) / 10초 (나머지) | ContextCompressor 처리 시간 포함 |
| 재시도 횟수 | 0회 | 즉시 오류 보고 |
| 폴백 동작 | BotStateRepository 실패 시 메모리 파일(pm_progress_guide.md) 기반 동작 유지 | 핵심 기능은 파일 기반으로 항상 동작 보장 |
| 에러 로깅 레벨 | 목표 미존재: `WARNING` / 파일 쓰기: `ERROR` / 상태 동기화 실패: `WARNING` | |
| 사용자 알림 | stdout에 `⚠️` 또는 `❌` 접두사 출력. 텔레그램 경유 시 `OutboundMessage`로 전달 | |

---

## 6. 기능 요구사항 (FR)

### Must Have

| ID | 요구사항 | 분류 |
|----|---------|------|
| FR-001 | `status` 명령: IN_PROGRESS 목표 및 활성 태스크 목록 출력 | Must Have |
| FR-002 | `start` 명령: 새 목표를 GOAL-NNN ID로 pm_progress_guide.md에 등록 | Must Have |
| FR-003 | `done` 명령: 목표 상태를 IN_PROGRESS → DONE 전환 | Must Have |
| FR-004 | `list` 명령: 전체 목표 테이블 출력 | Must Have |
| FR-005 | `report` 명령: 전체/완료/진행/블로킹 카운트 + 세부 현황 출력 | Must Have |
| FR-006 | ToolRegistry에 `pm_progress_start`, `pm_progress_done`, `pm_progress_status`, `pm_progress_report` 4개 도구 등록 | Must Have |
| FR-007 | PlatformAdapter를 통한 텔레그램 명령 정규화 | Must Have |
| FR-008 | BotStateRepository에 목표 상태(`current_goal`, `progress_pct`, `last_updated`) 동기화 | Must Have |

### Should Have

| ID | 요구사항 | 분류 |
|----|---------|------|
| FR-009 | `report` 명령 시 ContextCompressor 적용 (max_tokens=8000, keep_last_n=6) | Should Have |
| FR-010 | STALE 목표 감지 (3일 이상 진척 없음) 및 경고 출력 | Should Have |
| FR-011 | `daily_goal_pipeline` 크론 트리거 연동 (IN_PROGRESS 목표 자동 iter 재개) | Should Have |

### Nice to Have

| ID | 요구사항 | 분류 |
|----|---------|------|
| FR-012 | 목표 완료 시 `quality-gate` 스킬 자동 체이닝 | Nice to Have |
| FR-013 | 여러 PM 목표 동시 추적 (현재 단일 목표만 IN_PROGRESS로 운영) | Nice to Have |

---

## 7. 비기능 요구사항

| 항목 | 요구사항 |
|------|---------|
| 응답시간 SLA | `status`/`list`: 5초 이내 / `report`: 30초 이내 (ContextCompressor 포함) |
| 동시 호출 한도 | 단일 PM 봇 기준 1개 목표 추적 (병렬 처리 없음) |
| 로그 보존 기간 | pm_progress_guide.md 영구 보존 / BotStateRepository 90일 |
| 보안 요구사항 | 메모리 파일 쓰기는 PROJECT_ROOT 또는 `~/.claude/projects/` 내부로 한정 |
| 호환성 | Python 3.11+ / Python 3.14 호환 |
| 가용성 | BotStateRepository 오류 시 파일 기반 폴백으로 무중단 동작 보장 |

---

## 8. Hermes 연동 요구사항

### 8.1 ToolRegistry 연동

**등록 인터페이스 (4개 도구)**:
```python
# pm_progress_start
registry.register(
    name="pm_progress_start",
    description="새 PM 목표 등록 (IN_PROGRESS 상태로 pm_progress_guide.md에 추가)",
    handler=pm_progress_start_handler,  # Phase 2: cmd_start() 래핑
    tags={"skill", "pm-progress-tracker", "start", "goal"},
    schema=PM_PROGRESS_START_SCHEMA,
    enabled=True,
)

# pm_progress_done
registry.register(
    name="pm_progress_done",
    description="PM 목표를 DONE 처리 (IN_PROGRESS → DONE 전환)",
    handler=pm_progress_done_handler,
    tags={"skill", "pm-progress-tracker", "done", "goal"},
    schema=PM_PROGRESS_DONE_SCHEMA,
    enabled=True,
)

# pm_progress_status
registry.register(
    name="pm_progress_status",
    description="현재 IN_PROGRESS 목표 및 활성 태스크 현황 조회",
    handler=pm_progress_status_handler,
    tags={"skill", "pm-progress-tracker", "status", "query"},
    schema=PM_PROGRESS_STATUS_SCHEMA,
    enabled=True,
)

# pm_progress_report
registry.register(
    name="pm_progress_report",
    description="전체 진척 보고서 생성 (ContextCompressor 적용)",
    handler=pm_progress_report_handler,
    tags={"skill", "pm-progress-tracker", "report", "compress"},
    schema=PM_PROGRESS_REPORT_SCHEMA,
    enabled=True,
)
```

**handler 계약**:
- `**kwargs` 형식으로 입력 스펙(2.2) 파라미터 수신
- 성공 시 `dict` 반환 (3.1 출력 스펙)
- 실패 시 예외 발생 (ToolRegistry가 로그 후 재발생)

### 8.2 PlatformAdapter 연동

**정규화 흐름**:
```
telegram.Update (text="/pm-progress start 오픈소스화 패키징")
    → runtime.on_message(update)
    → TelegramPlatformAdapter.normalize_inbound()
    → InboundMessage(platform="telegram", chat_id="...", text="/pm-progress start 오픈소스화 패키징")
    → 파서: "/pm-progress start" → cmd="start", goal_name="오픈소스화 패키징"
    → registry.dispatch("pm_progress_start", goal_name="오픈소스화 패키징")
    → pm_progress_start_handler()
    → OutboundMessage(text="✅ 목표 등록 완료: GOAL-003")
    → adapter.send_message(outbound)
```

**계약 조건**:
- `HermesRuntime.on_init(bot_sender=pm_bot_sender)` 봇 시작 시 1회 호출 필수
- `InboundMessage.text`가 `/pm-progress`로 시작하지 않으면 처리 skip

### 8.3 ContextCompressor 연동 (report 명령)

```python
# pm_progress_report_handler 내부
compressor = get_compressor()
report_messages = [
    {"role": "system", "content": "PM 진척 보고서 생성 컨텍스트"},
    {"role": "user", "content": guide_content},
    {"role": "user", "content": tasks_content},
    *conversation_history,  # 이전 대화 히스토리
]
compressed = compressor.compress(
    messages=report_messages,
    max_tokens=max_tokens,   # 기본 8000
    keep_last_n=keep_last_n, # 기본 6
)
```

**트리거 조건**:
- `report_messages` 누적 토큰 > 8,000
- `non-system` 메시지 수 > 20개
- `report` 명령 실행 시 항상 적용 (압축 필요 여부 무관)

---

## 9. BotStateRepository 상태 동기화

| 명령 | 시점 | 메서드 | 저장 내용 |
|------|------|--------|---------|
| `start` | 목표 등록 성공 후 | `update_state(bot_id, {...})` | `{"current_goal": goal_id, "current_goal_name": goal_name, "progress_pct": 0, "last_updated": ISO8601}` |
| `done` | 목표 완료 처리 후 | `update_state(bot_id, {...})` | `{"current_goal": None, "progress_pct": 100, "last_goal_done": goal_name, "last_updated": ISO8601}` |
| `status` | 조회 전 | `get_state(bot_id)` | 읽기 전용 — 현재 상태 병합 출력 |
| `report` | 보고서 생성 후 | `update_state(bot_id, {...})` | `{"last_report_at": ISO8601, "report_summary": {"total": N, "done": N}}` |
| 실패 시 | 임의 명령 실패 | 없음 | 상태 미변경 |

**폴백 정책**: `BotStateRepository` 오류 시 warning 로그 후 파일 기반(`pm_progress_guide.md`) 동작 유지.

---

## 10. 예외 및 엣지케이스

| # | 케이스 | 기대 동작 |
|---|--------|---------|
| EC-01 | `done <목표명>`에서 해당 목표가 IN_PROGRESS 아님 | `ERR_GOAL_NOT_FOUND` + list 명령 안내 |
| EC-02 | `pm_progress_guide.md` 파일 없음 | `start` 명령 안내. `list`/`status`는 "(등록된 목표 없음)" 출력 |
| EC-03 | `start` 명령에 목표명 미입력 | `ERR_MISSING_GOAL_NAME` + 사용법 출력 |
| EC-04 | BotStateRepository `initialize()` 전 `update_state()` 호출 | warning 로그 후 파일 기반 폴백 |
| EC-05 | ContextCompressor `max_tokens=0` | `[]` 반환 → report 빈 응답 + 경고 출력 |
| EC-06 | STALE 목표 (3일 이상 진척 없음) | `[STALE]` 표시 후 재개 권고 메시지 출력 |
| EC-07 | `ENABLE_TOOL_REGISTRY=false` | CLI 직접 실행 폴백 (ToolRegistry 없이 동작) |
| EC-08 | `ENABLE_CONTEXT_COMPRESSOR=false` | 원본 report_messages 그대로 사용 (압축 없이 동작) |
| EC-09 | `daily_goal_pipeline` 크론 발동 시 IN_PROGRESS 목표 없음 | no-op + 로그 기록 |
| EC-10 | 동일 목표명으로 `start` 중복 호출 | 새 GOAL-NNN ID로 추가 (중복 허용, 기획 결정 필요 — OQ-2) |

---

## 11. 수용 기준 (Acceptance Criteria)

### FR-002: start 명령 목표 등록

**Given** `start '오픈소스화 패키징'` 실행 시
**When** pm_progress_guide.md에 GOAL 항목이 없을 때
**Then** `GOAL-001` ID로 IN_PROGRESS 상태 항목이 추가되고 "✅ 목표 등록 완료" 출력

### FR-003: done 명령 목표 완료

**Given** `GOAL-001` 목표가 IN_PROGRESS 상태일 때
**When** `done '오픈소스화 패키징'` 실행 시
**Then** pm_progress_guide.md에서 `IN_PROGRESS` → `DONE` 전환되고 "✅ 목표 완료 처리" 출력

### FR-006: ToolRegistry 도구 등록

**Given** `HermesRuntime.on_init()` 호출 후 `pm_progress_*` 핸들러 등록 완료 시
**When** `registry.get_tools_by_tag("pm-progress-tracker")` 호출 시
**Then** 4개 `ToolEntry` 반환되고 각 `handler is not None` (Phase 2 완료 기준)

### FR-007: PlatformAdapter 정규화

**Given** 텔레그램 Update에 `/pm-progress start 테스트 목표` 텍스트가 포함될 때
**When** `runtime.on_message(update)` 호출 시
**Then** `InboundMessage.text == "/pm-progress start 테스트 목표"` 이고
`registry.dispatch("pm_progress_start", goal_name="테스트 목표")` 호출됨

### FR-008: BotStateRepository 동기화

**Given** `start '목표A'` 성공 후
**When** `repo.get_state(bot_id)` 호출 시
**Then** `state["current_goal_name"] == "목표A"` 이고 `state["progress_pct"] == 0`

### FR-009: ContextCompressor 적용

**Given** `report_messages` 누적 토큰이 8,000 초과 시
**When** `report` 명령 실행 시
**Then** `compressed=True` 플래그와 함께 8,000 토큰 이내 보고서 반환

---

## 12. 미결 사항 (Open Questions)

| # | 질문 | 영향 |
|---|------|------|
| OQ-1 | `daily_goal_pipeline` 크론 발동 시 자동 iter 재개를 `pm_progress_status` 도구가 처리하는가, 별도 `pm_progress_iterate` 도구로 분리하는가? | 크론 트리거 구현 방식 |
| OQ-2 | 동일 목표명 중복 `start` 허용 여부: 새 ID 생성 vs 기존 항목 활성화? | FR-002 동작 |
| OQ-3 | BotStateRepository `bot_id`: PM 봇 단일 ID(`aiorg_pm_bot`) 고정인가, 목표별 ID 생성인가? | 상태 키 설계 |
| OQ-4 | `report` 명령에서 ContextCompressor 적용 전 원본 저장 필요 여부 | 이력 관리 |
| OQ-5 | `pm_progress_report` 출력이 8,000 토큰 초과 시 분할 전송인가, 잘라내기인가? | 텔레그램 메시지 한도(4096자) 대응 |

## 13. 의존성 목록

| 의존 항목 | 유형 | 상태 |
|---------|------|------|
| `core/tool_registry.py` | 내부 모듈 | ✅ 구현 완료 |
| `core/platform_adapter.py` | 내부 모듈 | ✅ 구현 완료 |
| `core/context_compressor.py` | 내부 모듈 | ✅ 구현 완료 |
| `core/hermes_integration.py` | 내부 모듈 | ⚠️ handler=None 스텁 |
| `core/repositories/bot_state_repository.py` | 내부 모듈 | ✅ 구현 완료 |
| `memory/pm_progress_guide.md` | 파일 시스템 | ✅ 존재 (또는 자동 생성) |
| `memory/project_pending_tasks.md` | 파일 시스템 | ✅ 존재 |
| `aiosqlite` | 외부 패키지 | ✅ 설치됨 |
