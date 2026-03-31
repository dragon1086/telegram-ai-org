"""FastAPI REST API 엔드포인트 테스트 — Phase 2-A.

httpx.AsyncClient + ASGITransport를 사용해 실제 서버 없이 테스트합니다.
각 테스트마다 :memory: SQLite DB로 격리합니다.
"""
from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def enable_flags(monkeypatch):
    """테스트 환경 피처 플래그 설정."""
    monkeypatch.setenv("ENABLE_REPOSITORY_PATTERN", "1")
    monkeypatch.setenv("ENABLE_REST_API", "true")
    monkeypatch.setenv("ENABLE_API_AUTH", "false")


@pytest.fixture
async def client():
    """각 테스트마다 새로운 FastAPI 앱 + httpx AsyncClient를 생성한다.

    httpx.ASGITransport는 ASGI lifespan을 트리거하지 않으므로
    TaskRepository를 수동으로 초기화하여 app.state에 설정합니다.
    """
    import httpx

    from core.api.app import create_app
    from core.repositories.task_repository import TaskRepository

    app = create_app(db_path=":memory:")

    # lifespan이 트리거되지 않으므로 수동으로 repo 초기화
    repo = TaskRepository(db_path=":memory:")
    await repo.initialize()
    app.state.task_repo = repo

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c

    await repo.close()


# ---------------------------------------------------------------------------
# Health 엔드포인트
# ---------------------------------------------------------------------------


async def test_health_endpoint(client) -> None:
    """GET /api/v1/health → 200, status=ok."""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "v1"


async def test_ready_endpoint(client) -> None:
    """GET /api/v1/ready → 200, ready=True."""
    resp = await client.get("/api/v1/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ready"] is True
    assert "checks" in body


# ---------------------------------------------------------------------------
# POST /api/v1/tasks
# ---------------------------------------------------------------------------


async def test_create_task_returns_201(client) -> None:
    """POST /api/v1/tasks → 201, task_id 포함."""
    resp = await client.post(
        "/api/v1/tasks", json={"description": "테스트 태스크", "org_id": "dev"}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "task_id" in body
    assert body["status"] == "pending"
    assert body["description"] == "테스트 태스크"


async def test_create_task_default_org(client) -> None:
    """org_id 미입력 시 기본값 'dev'가 사용되어야 한다."""
    resp = await client.post("/api/v1/tasks", json={"description": "기본 조직 테스트"})
    assert resp.status_code == 201
    assert resp.json()["org_id"] == "dev"


async def test_create_task_custom_org(client) -> None:
    """org_id 'ops' 지정 시 응답에 반영되어야 한다."""
    resp = await client.post(
        "/api/v1/tasks", json={"description": "운영 태스크", "org_id": "ops"}
    )
    assert resp.status_code == 201
    assert resp.json()["org_id"] == "ops"


async def test_create_task_empty_description_422(client) -> None:
    """빈 description은 422 Unprocessable Entity를 반환해야 한다."""
    resp = await client.post("/api/v1/tasks", json={"description": ""})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /api/v1/tasks/{task_id}
# ---------------------------------------------------------------------------


async def test_get_task_after_create(client) -> None:
    """POST 후 GET으로 동일 task_id를 조회할 수 있어야 한다."""
    create_resp = await client.post(
        "/api/v1/tasks", json={"description": "조회 테스트"}
    )
    task_id = create_resp.json()["task_id"]

    get_resp = await client.get(f"/api/v1/tasks/{task_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["task_id"] == task_id


async def test_get_nonexistent_task_404(client) -> None:
    """존재하지 않는 task_id 조회 시 404를 반환해야 한다."""
    resp = await client.get("/api/v1/tasks/nonexistent-task-id-xyz")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# GET /api/v1/tasks (목록)
# ---------------------------------------------------------------------------


async def test_list_tasks_empty(client) -> None:
    """태스크가 없을 때 빈 목록을 반환해야 한다."""
    resp = await client.get("/api/v1/tasks")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_tasks_after_create(client) -> None:
    """POST 후 목록에 해당 태스크가 포함되어야 한다."""
    await client.post("/api/v1/tasks", json={"description": "목록 테스트"})
    resp = await client.get("/api/v1/tasks")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_list_tasks_filter_by_status(client) -> None:
    """status=pending 필터로 pending 태스크만 반환해야 한다."""
    await client.post("/api/v1/tasks", json={"description": "태스크 A"})
    await client.post("/api/v1/tasks", json={"description": "태스크 B"})

    resp = await client.get("/api/v1/tasks?status=pending")
    assert resp.status_code == 200
    tasks = resp.json()
    assert len(tasks) == 2
    assert all(t["status"] == "pending" for t in tasks)


async def test_list_tasks_filter_done_empty(client) -> None:
    """신규 태스크가 pending 상태이므로 status=done 필터는 빈 목록을 반환해야 한다."""
    await client.post("/api/v1/tasks", json={"description": "태스크"})
    resp = await client.get("/api/v1/tasks?status=done")
    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# DELETE /api/v1/tasks/{task_id}
# ---------------------------------------------------------------------------


async def test_delete_task_returns_204(client) -> None:
    """DELETE → 204, 이후 GET → 404여야 한다."""
    create_resp = await client.post(
        "/api/v1/tasks", json={"description": "삭제 테스트"}
    )
    task_id = create_resp.json()["task_id"]

    del_resp = await client.delete(f"/api/v1/tasks/{task_id}")
    assert del_resp.status_code == 204

    get_resp = await client.get(f"/api/v1/tasks/{task_id}")
    assert get_resp.status_code == 404


async def test_delete_nonexistent_task_404(client) -> None:
    """존재하지 않는 task_id DELETE 시 404를 반환해야 한다."""
    resp = await client.delete("/api/v1/tasks/nonexistent-xyz")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# API Key 인증
# ---------------------------------------------------------------------------


async def test_api_key_auth_required(monkeypatch) -> None:
    """ENABLE_API_AUTH=true 시 X-API-Key 없으면 401을 반환해야 한다."""
    monkeypatch.setenv("ENABLE_API_AUTH", "true")
    monkeypatch.setenv("AIMESH_API_KEYS", "test-key-abc")

    import importlib

    import httpx

    # 모듈 재로드로 환경변수 반영
    import core.api.auth as auth_mod

    importlib.reload(auth_mod)

    from core.api.app import create_app
    from core.repositories.task_repository import TaskRepository

    app = create_app(db_path=":memory:")

    # 수동 repo 초기화 (lifespan 미트리거)
    repo = TaskRepository(db_path=":memory:")
    await repo.initialize()
    app.state.task_repo = repo

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.post("/api/v1/tasks", json={"description": "인증 테스트"})
        assert resp.status_code == 401

        # 올바른 키 포함 시 통과
        resp_ok = await c.post(
            "/api/v1/tasks",
            json={"description": "인증 테스트"},
            headers={"X-API-Key": "test-key-abc"},
        )
        assert resp_ok.status_code == 201

    await repo.close()
    # 원복: monkeypatch 정리 전이라 env var가 여전히 설정돼 있으므로
    # reload 대신 모듈 레벨 변수를 직접 초기화한다.
    auth_mod.ENABLE_API_AUTH = False
    auth_mod.API_KEYS = frozenset()
