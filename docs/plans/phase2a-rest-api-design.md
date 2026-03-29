# Phase 2-A REST API 기능 설계 명세서

**작성일**: 2026-03-29
**담당**: 개발실 (aiorg_engineering_bot)
**태스크**: T-aiorg_pm_bot-823 Phase 2-A

---

## 1. 기능 확정 목록

| 우선순위 | 기능명 | 근거 |
|---------|--------|------|
| P0 | **TaskRepository 실제 구현** | Phase 1-B 스캐폴딩 스텁 완성 — REST API 동작의 필수 전제 |
| P1 | **FastAPI REST API 레이어** | Telegram 외 채널 접근 허용 → TAM 10배 확대 (로드맵 P1-1) |

### 선정 근거 (경쟁사 비교)

- **OpenClaw / oh-my-claudecode**: 모두 CLI 전용 또는 Telegram 전용. HTTP API 없음.
- **Sisyphus / opencode**: REST API 없음.
- **AIMesh 기회**: Telegram-native UX를 유지하면서 REST API로 CI/CD, 슬랙봇, 웹 대시보드 등 추가 채널 지원 → 단일 오케스트레이션 레이어로 다채널 지원하는 경쟁사는 없음.

---

## 2. 인터페이스 설계 명세서

### 2.1 TaskRepository

**모듈**: `core/repositories/task_repository.py`
**피처 플래그**: `ENABLE_REPOSITORY_PATTERN=1`

#### 데이터 스키마

```sql
CREATE TABLE IF NOT EXISTS tasks (
    task_id     TEXT    PRIMARY KEY,
    org_id      TEXT    NOT NULL,
    description TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'pending',
    created_at  REAL    NOT NULL,
    updated_at  REAL    NOT NULL,
    result      TEXT
);
```

#### API (메서드)

| 메서드 | 입력 | 출력 | 설명 |
|--------|------|------|------|
| `initialize()` | — | None | DB/테이블 생성 |
| `get(task_id)` | str | dict \| None | 단일 태스크 조회 |
| `save(task)` | dict | None | INSERT OR REPLACE |
| `update_status(task_id, status, result?)` | str, str, str? | bool | 상태 업데이트 |
| `list_by_status(status)` | str | list[dict] | 상태 필터 목록 |
| `delete(task_id)` | str | None | 태스크 삭제 |

#### task dict 스키마

```python
{
    "task_id": str,       # UUID4
    "org_id": str,        # 예: "dev", "ops"
    "description": str,   # 태스크 설명
    "status": str,        # pending | in_progress | done | failed | cancelled
    "created_at": float,  # Unix timestamp
    "updated_at": float,  # Unix timestamp
    "result": str | None, # 실행 결과
}
```

### 2.2 FastAPI REST API

**모듈**: `core/api/`
**피처 플래그**: `ENABLE_REST_API=false`
**인증 플래그**: `ENABLE_API_AUTH=false`
**API 키 환경변수**: `AIMESH_API_KEYS` (콤마 구분)

#### 엔드포인트 목록

| Method | Path | 인증 필요 | 설명 |
|--------|------|-----------|------|
| GET | `/api/v1/health` | ✗ | 헬스체크 |
| GET | `/api/v1/ready` | ✗ | 준비 상태 (DB 포함) |
| POST | `/api/v1/tasks` | ✓ | 태스크 생성 |
| GET | `/api/v1/tasks` | ✓ | 태스크 목록 (status 필터) |
| GET | `/api/v1/tasks/{task_id}` | ✓ | 단일 태스크 조회 |
| DELETE | `/api/v1/tasks/{task_id}` | ✓ | 태스크 취소 |

#### Request/Response 스펙

**POST /api/v1/tasks**
```json
// Request
{"description": "FastAPI 구현 리뷰 요청", "org_id": "dev"}

// Response 201
{
  "task_id": "a1b2c3d4-...",
  "org_id": "dev",
  "description": "FastAPI 구현 리뷰 요청",
  "status": "pending",
  "created_at": 1743206400.0,
  "updated_at": 1743206400.0,
  "result": null
}
```

**GET /api/v1/tasks/{task_id}**
```json
// Response 200 (found)
{"task_id": "...", "org_id": "dev", "status": "pending", ...}

// Response 404 (not found)
{"detail": "Task not found: a1b2c3d4"}
```

#### 데이터 흐름

```
Client (HTTP)
    │
    ▼
FastAPI app (core/api/app.py)
    │  [X-API-Key 헤더 검증]
    ▼
auth.py → 401 if invalid
    │
    ▼
routes/tasks.py (TaskRouter)
    │  [Pydantic 검증]
    ▼
TaskRepository (core/repositories/)
    │
    ▼
SQLite (data/tasks.db)
```

---

## 3. 변경 대상 파일 목록

### 신규 생성

| 파일 | 역할 |
|------|------|
| `core/api/__init__.py` | API 패키지 init, `API_VERSION = "v1"` |
| `core/api/app.py` | FastAPI 앱 팩토리 (`create_app()`) |
| `core/api/auth.py` | API Key 인증 의존성 |
| `core/api/routes/__init__.py` | 라우터 패키지 init |
| `core/api/routes/health.py` | 헬스/레디 엔드포인트 |
| `core/api/routes/tasks.py` | 태스크 CRUD 엔드포인트 |
| `tests/test_task_repository.py` | TaskRepository 단위 테스트 |
| `tests/test_api_app.py` | FastAPI 엔드포인트 테스트 |
| `docs/plans/phase2a-rest-api-design.md` | 이 설계 문서 |

### 수정 (스텁 → 실제 구현)

| 파일 | 변경 내용 |
|------|-----------|
| `core/repositories/task_repository.py` | `NotImplementedError` 스텁 → SQLite 실구현 |
| `core/services/orchestration_service.py` | `get_task_status()` 실구현 (조회 전용) |

### 업데이트 (문서 동기화)

| 파일 | 변경 내용 |
|------|-----------|
| `CLAUDE.md` | REST API 섹션 추가 |
| `AGENTS.md` | REST API 섹션 추가 |
| `GEMINI.md` | REST API 섹션 추가 |

---

## 4. 구현 원칙

- **최소 침습**: `telegram_relay.py` 등 기존 파일 수정 금지
- **피처 플래그**: 모든 신규 기능은 env var로 on/off 가능
- **하위 호환**: 플래그 꺼진 상태에서 기존 시스템 영향 없음
- **테스트 우선**: 각 기능 구현 후 즉시 단위 테스트 작성 + pytest 통과 확인
