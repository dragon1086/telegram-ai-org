"""텔레그램 전달 대상 해석/검증 유틸리티."""
from __future__ import annotations

from dataclasses import dataclass

from core.orchestration_config import load_orchestration_config


@dataclass(frozen=True)
class TelegramDeliveryTarget:
    org_id: str
    token: str
    chat_id: int


def resolve_delivery_target(org_id: str) -> TelegramDeliveryTarget | None:
    try:
        org = load_orchestration_config(force_reload=True).get_org(org_id)
    except Exception:
        org = None
    if org is None:
        return None
    token = org.token
    chat_id = org.chat_id
    if not token or chat_id is None:
        return None
    return TelegramDeliveryTarget(org_id=org_id, token=token, chat_id=int(chat_id))


def is_expected_delivery_target(org_id: str, token: str, chat_id: int) -> bool:
    target = resolve_delivery_target(org_id)
    if target is None:
        return False
    return target.token == token and target.chat_id == int(chat_id)
