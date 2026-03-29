"""core.api — AIMesh FastAPI REST API 패키지 (Phase 2-A).

피처 플래그: ENABLE_REST_API=true 시 HTTP API 활성화.
기본값 false — 기존 Telegram 봇 동작에 영향 없음.

사용 예시::

    import os; os.environ["ENABLE_REST_API"] = "true"
    from core.api.app import create_app
    app = create_app()

    # uvicorn으로 실행:
    # uvicorn core.api.app:create_app --factory --host 0.0.0.0 --port 8000
"""

API_VERSION: str = "v1"
"""현재 API 버전 문자열."""
