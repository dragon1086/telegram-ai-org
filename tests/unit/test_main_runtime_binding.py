from types import SimpleNamespace

import pytest

import main


def test_pm_org_can_use_pm_bot_token_fallback(monkeypatch) -> None:
    monkeypatch.setenv("PM_BOT_TOKEN", "pm-test-token")
    monkeypatch.setenv("TELEGRAM_GROUP_CHAT_ID", "-100123")
    monkeypatch.setattr(main, "load_orchestration_config", lambda force_reload=True: None)

    token, chat_id, engine = main._resolve_runtime_binding("aiorg_pm_bot")

    assert token == "pm-test-token"
    assert chat_id == -100123
    assert engine == "claude-code"


def test_non_pm_org_does_not_reuse_pm_bot_token(monkeypatch) -> None:
    monkeypatch.setenv("PM_BOT_TOKEN", "pm-test-token")
    monkeypatch.setenv("TELEGRAM_GROUP_CHAT_ID", "-100123")

    product_org = SimpleNamespace(token="", chat_id=-100123, preferred_engine="claude-code")
    cfg = SimpleNamespace(get_org=lambda org_id: product_org)
    monkeypatch.setattr(main, "load_orchestration_config", lambda force_reload=True: cfg)

    with pytest.raises(RuntimeError, match="binding is incomplete"):
        main._resolve_runtime_binding("aiorg_product_bot")


def test_non_pm_org_uses_own_token_from_config(monkeypatch) -> None:
    monkeypatch.setenv("PM_BOT_TOKEN", "pm-test-token")
    monkeypatch.setenv("TELEGRAM_GROUP_CHAT_ID", "-100123")

    product_org = SimpleNamespace(
        token="product-test-token",
        chat_id=-100123,
        preferred_engine="claude-code",
    )
    cfg = SimpleNamespace(get_org=lambda org_id: product_org)
    monkeypatch.setattr(main, "load_orchestration_config", lambda force_reload=True: cfg)

    token, chat_id, engine = main._resolve_runtime_binding("aiorg_product_bot")

    assert token == "product-test-token"
    assert chat_id == -100123
    assert engine == "claude-code"
