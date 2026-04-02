from pathlib import Path

import yaml


def _load_compose() -> dict:
    compose_path = Path(__file__).resolve().parents[2] / "docker-compose.yml"
    return yaml.safe_load(compose_path.read_text())


def _dockerfile_text() -> str:
    dockerfile_path = Path(__file__).resolve().parents[2] / "Dockerfile"
    return dockerfile_path.read_text()


def test_compose_keeps_required_runtime_and_bot_services() -> None:
    services = _load_compose()["services"]

    expected = {
        "gemini-runtime",
        "aiorg-pm",
        "aiorg-product-bot",
        "aiorg-design-bot",
        "aiorg-engineering-bot",
        "aiorg-ops-bot",
        "aiorg-growth-bot",
        "aiorg-research-bot",
    }

    assert expected.issubset(services)
    assert "aiorg-redis" not in services


def test_compose_keeps_expected_profiles_per_service() -> None:
    services = _load_compose()["services"]

    assert services["gemini-runtime"]["profiles"] == ["gemini"]

    assert services["aiorg-pm"]["profiles"] == ["gemini"]
    assert services["aiorg-product-bot"]["profiles"] == ["gemini"]
    assert services["aiorg-engineering-bot"]["profiles"] == ["gemini"]
    assert services["aiorg-design-bot"]["profiles"] == ["gemini"]
    assert services["aiorg-ops-bot"]["profiles"] == ["gemini"]
    assert services["aiorg-growth-bot"]["profiles"] == ["gemini"]
    assert services["aiorg-research-bot"]["profiles"] == ["gemini"]


def test_compose_no_longer_injects_redis_sidecar_settings() -> None:
    compose = _load_compose()
    bot_common = compose["x-bot-common"]

    assert "environment" not in bot_common or "REDIS_URL" not in bot_common["environment"]


def test_compose_sets_writable_data_dir_for_container_runtime() -> None:
    compose = _load_compose()
    bot_common = compose["x-bot-common"]

    assert bot_common["environment"]["AI_ORG_DATA_DIR"] == "/app/data"
    assert "${HOME}/.gemini:/gemini-oauth:ro" in bot_common["volumes"]


def test_runtime_services_clear_image_entrypoint_for_sidecar_commands() -> None:
    services = _load_compose()["services"]

    assert services["gemini-runtime"]["entrypoint"] == []


def test_dockerfile_creates_runtime_user_home_directory() -> None:
    dockerfile = _dockerfile_text()

    assert "useradd -m -d /home/aiorg" in dockerfile
    assert 'AIMESH_PROJECT_ROOT="/app"' in dockerfile
    assert 'HOME="/home/aiorg"' in dockerfile
    assert 'COPY docker-entrypoint.sh /app/docker-entrypoint.sh' in dockerfile
    assert 'ENTRYPOINT ["/app/docker-entrypoint.sh"]' in dockerfile


def test_compose_service_images_match_canonical_engine_allocation() -> None:
    services = _load_compose()["services"]

    assert services["aiorg-pm"]["image"] == "telegram-ai-org:gemini"
    assert services["aiorg-product-bot"]["image"] == "telegram-ai-org:gemini"
    assert services["aiorg-engineering-bot"]["image"] == "telegram-ai-org:gemini"
    assert services["aiorg-design-bot"]["image"] == "telegram-ai-org:gemini"
    assert services["aiorg-ops-bot"]["image"] == "telegram-ai-org:gemini"
    assert services["aiorg-growth-bot"]["image"] == "telegram-ai-org:gemini"
    assert services["aiorg-research-bot"]["image"] == "telegram-ai-org:gemini"
