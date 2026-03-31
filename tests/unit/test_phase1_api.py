"""Phase 1 단위 테스트 — core.api 모듈 (FastAPI 엔드포인트).

테스트 대상:
- core/api/routes/health.py — GET /api/v1/health, GET /api/v1/ready
- core/api/routes/tasks.py — POST/GET/GET/{id}/DELETE /api/v1/tasks
- core/api/auth.py — API Key 인증 로직
"""
from __future__ import annotations

import os

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# 앱 팩토리 및 클라이언트 Fixture
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def app_with_repo():
    """:memory: TaskRepository가 주입된 FastAPI 앱.

    주의: db_path=":memory:"를 명시적으로 전달해 module-level DEFAULT_DB_PATH
    캐시 문제를 방지한다. ENABLE_REPOSITORY_PATTERN은 :memory: DB 사용 시
    task_repository._is_enabled()가 자동으로 True를 반환하므로 불필요.
    """
    os.environ["ENABLE_REST_API"] = "true"
    os.environ["ENABLE_API_AUTH"] = "false"
    os.environ["AIMESH_DB_PATH"] = ":memory:"
    os.environ["ENABLE_REPOSITORY_PATTERN"] = "1"

    from core.api.app import create_app
    # module-level DEFAULT_DB_PATH 캐시에 의존하지 않도록 명시적으로 전달
    _app = create_app(db_path=":memory:")

    # lifespan 수동 진입
    async with _app.router.lifespan_context(_app):
        yield _app

    # 테스트 격리: 설정한 env var 복원
    for key in ("ENABLE_REST_API", "ENABLE_API_AUTH", "AIMESH_DB_PATH", "ENABLE_REPOSITORY_PATTERN"):
        os.environ.pop(key, None)


@pytest_asyncio.fixture
async def client(app_with_repo):
    """테스트용 AsyncClient."""
    async with AsyncClient(
        transport=ASGITransport(app=app_with_repo), base_url="http://test"
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# Health 엔드포인트 테스트
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        """GET /api/v1/health 가 {"status": "ok"} 를 반환해야 한다."""
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_health_returns_version(self, client):
        """health 응답에 version 필드가 포함돼야 한다."""
        resp = await client.get("/api/v1/health")
        data = resp.json()
        assert "version" in data
        assert data["version"] == "v1"

    @pytest.mark.asyncio
    async def test_ready_with_repo_returns_ok(self, client):
        """GET /api/v1/ready 가 DB가 있으면 {"ready": true} 를 반환해야 한다."""
        resp = await client.get("/api/v1/ready")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready"] is True
        assert data["checks"]["db"] == "ok"


# ---------------------------------------------------------------------------
# Tasks CRUD 엔드포인트 테스트
# ---------------------------------------------------------------------------

class TestTasksCreate:
    @pytest.mark.asyncio
    async def test_create_task_returns_201(self, client):
        """POST /api/v1/tasks 가 201을 반환하고 task_id를 포함해야 한다."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"description": "테스트 태스크", "org_id": "dev"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "task_id" in data
        assert data["status"] == "pending"
        assert data["org_id"] == "dev"

    @pytest.mark.asyncio
    async def test_create_task_default_org_id(self, client):
        """org_id 생략 시 기본값 'dev'가 사용돼야 한다."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"description": "org_id 없는 태스크"},
        )
        assert resp.status_code == 201
        assert resp.json()["org_id"] == "dev"

    @pytest.mark.asyncio
    async def test_create_task_empty_description_returns_422(self, client):
        """description이 빈 문자열이면 422를 반환해야 한다."""
        resp = await client.post(
            "/api/v1/tasks",
            json={"description": ""},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_task_missing_description_returns_422(self, client):
        """description 필드 자체가 없으면 422를 반환해야 한다."""
        resp = await client.post("/api/v1/tasks", json={})
        assert resp.status_code == 422


class TestTasksRead:
    @pytest.mark.asyncio
    async def test_get_task_by_id(self, client):
        """생성 후 GET /api/v1/tasks/{task_id} 가 200을 반환해야 한다."""
        create_resp = await client.post(
            "/api/v1/tasks",
            json={"description": "조회 테스트 태스크"},
        )
        task_id = create_resp.json()["task_id"]

        resp = await client.get(f"/api/v1/tasks/{task_id}")
        assert resp.status_code == 200
        assert resp.json()["task_id"] == task_id

    @pytest.mark.asyncio
    async def test_get_nonexistent_task_returns_404(self, client):
        """존재하지 않는 task_id 조회 시 404가 반환돼야 한다."""
        resp = await client.get("/api/v1/tasks/DOES_NOT_EXIST")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_tasks_empty(self, client):
        """태스크가 없으면 빈 배열이 반환돼야 한다."""
        resp = await client.get("/api/v1/tasks")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_list_tasks_after_create(self, client):
        """태스크 생성 후 목록이 1개여야 한다."""
        await client.post("/api/v1/tasks", json={"description": "목록 테스트"})
        resp = await client.get("/api/v1/tasks")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    @pytest.mark.asyncio
    async def test_list_tasks_status_filter(self, client):
        """status 쿼리 파라미터로 필터링이 돼야 한다."""
        _ = await client.post("/api/v1/tasks", json={"description": "필터 테스트"})
        # 막 생성된 태스크는 pending 상태
        resp_filtered = await client.get("/api/v1/tasks?status=pending")
        assert resp_filtered.status_code == 200
        tasks = resp_filtered.json()
        assert len(tasks) >= 1
        assert all(t["status"] == "pending" for t in tasks)


class TestTasksDelete:
    @pytest.mark.asyncio
    async def test_cancel_task_returns_204(self, client):
        """DELETE /api/v1/tasks/{task_id} 가 204를 반환해야 한다."""
        create_resp = await client.post(
            "/api/v1/tasks", json={"description": "삭제 테스트"}
        )
        task_id = create_resp.json()["task_id"]

        resp = await client.delete(f"/api/v1/tasks/{task_id}")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_task_returns_404(self, client):
        """존재하지 않는 태스크 삭제 시 404가 반환돼야 한다."""
        resp = await client.delete("/api/v1/tasks/NO_SUCH_TASK")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_cancel_then_get_returns_404(self, client):
        """삭제 후 해당 태스크를 조회하면 404여야 한다."""
        create_resp = await client.post(
            "/api/v1/tasks", json={"description": "삭제 후 조회 테스트"}
        )
        task_id = create_resp.json()["task_id"]
        await client.delete(f"/api/v1/tasks/{task_id}")

        get_resp = await client.get(f"/api/v1/tasks/{task_id}")
        assert get_resp.status_code == 404


# ---------------------------------------------------------------------------
# API 인증 테스트
# ---------------------------------------------------------------------------

class TestApiAuth:
    @pytest.mark.asyncio
    async def test_auth_disabled_no_key_passes(self, client):
        """ENABLE_API_AUTH=false이면 API Key 없이도 통과해야 한다."""
        resp = await client.get("/api/v1/tasks")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_auth_enabled_without_key_returns_401(self, app_with_repo):
        """ENABLE_API_AUTH=true이면 키 없이 요청 시 401이 반환돼야 한다."""
        import core.api.auth as auth_module

        # 인증 활성화 패치
        original = auth_module.ENABLE_API_AUTH
        auth_module.ENABLE_API_AUTH = True
        auth_module.API_KEYS = frozenset(["valid-key-123"])
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app_with_repo), base_url="http://test"
            ) as c:
                resp = await c.get("/api/v1/tasks")
            assert resp.status_code == 401
        finally:
            auth_module.ENABLE_API_AUTH = original
            auth_module.API_KEYS = frozenset()

    @pytest.mark.asyncio
    async def test_auth_enabled_with_valid_key_passes(self, app_with_repo):
        """ENABLE_API_AUTH=true + 유효한 키는 통과해야 한다."""
        import core.api.auth as auth_module

        original = auth_module.ENABLE_API_AUTH
        auth_module.ENABLE_API_AUTH = True
        auth_module.API_KEYS = frozenset(["valid-key-123"])
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app_with_repo), base_url="http://test"
            ) as c:
                resp = await c.get("/api/v1/tasks", headers={"X-API-Key": "valid-key-123"})
            assert resp.status_code == 200
        finally:
            auth_module.ENABLE_API_AUTH = original
            auth_module.API_KEYS = frozenset()
