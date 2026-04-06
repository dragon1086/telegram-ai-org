# Phase 1 기능 테스트 커버리지

Phase 1-B 스캐폴딩 구현에 대한 단위 테스트 현황입니다.

## 테스트 대상 모듈

| 모듈 | 테스트 파일 | 커버 케이스 수 |
|------|-------------|----------------|
| `core/types.py` | `tests/unit/test_phase1_types.py` | 11개 |
| `core/interfaces.py` | `tests/unit/test_phase1_interfaces.py` | 8개 |
| `core/repositories/task_repository.py` | `tests/unit/test_phase1_task_repository.py` | 15개 |
| `core/api/` (health + tasks + auth) | `tests/unit/test_phase1_api.py` | 16개 |

## 테스트 실행 방법

```bash
# Phase 1 단위 테스트만 실행
.venv/bin/python -m pytest tests/unit/test_phase1_*.py -v

# 전체 단위 테스트 실행
.venv/bin/python -m pytest tests/unit/ -v
```

## 테스트 케이스 상세

### core/types.py
- TypeAlias (TaskID, OrgID, BotHandle) 존재 확인
- EngineType Literal 값 검증 (claude-code / codex / gemini-cli)
- TaskStatusLiteral 값 검증 (5가지 상태)
- MessageEnvelope TypedDict 생성 (정상/빈 content 엣지 케이스)
- BotState TypedDict 생성 (is_alive=True/False 경계값)

### core/interfaces.py
- BaseRunner Protocol 구조 검증
- 구체 클래스가 Protocol을 만족하는지 isinstance 검증
- engine_name 없는 클래스가 Protocol 불만족 확인
- TelegramInterface 완전/불완전 구현체 검증
- TaskRepositoryInterface 구현체 검증

### core/repositories/task_repository.py
- save + get (happy path)
- update_status (성공/실패 반환값 검증)
- list_by_status, list_all
- delete (정상/존재하지 않는 ID 모두 커버)
- upsert 동작 (동일 task_id 재저장)
- 빈 result, 최소 필드, 특수문자 ID, 10000자 description
- 피처 플래그 (ENABLE_REPOSITORY_PATTERN 0/1/:memory: 동작)

### core/api/
- GET /api/v1/health → {"status": "ok", "version": "v1"}
- GET /api/v1/ready → DB ok/not_configured
- POST /api/v1/tasks → 201 생성, 빈 description → 422
- GET /api/v1/tasks → 목록, status 필터
- GET /api/v1/tasks/{id} → 200/404
- DELETE /api/v1/tasks/{id} → 204/404
- API Auth 비활성/활성 시 동작 검증
