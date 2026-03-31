"""스캐폴딩 import 스모크 테스트 (Phase 1-B).

모든 신규 스캐폴딩 모듈이 오류 없이 임포트되는지 검증합니다.
"""
from __future__ import annotations


def test_core_types_importable():
    from core import types as _
    assert hasattr(_, "TaskID")
    assert hasattr(_, "OrgID")
    assert hasattr(_, "EngineType")


def test_core_interfaces_importable():
    from core import interfaces as _
    assert hasattr(_, "BaseRunner")
    assert hasattr(_, "TelegramInterface")
    assert hasattr(_, "TaskRepositoryInterface")


def test_repositories_importable():
    from core.repositories import BotStateRepository, MessageRepository, TaskRepository
    assert TaskRepository is not None
    assert MessageRepository is not None
    assert BotStateRepository is not None


def test_services_importable():
    from core.services import DispatchService, OrchestrationService
    assert DispatchService is not None
    assert OrchestrationService is not None


def test_existing_handlers_still_importable():
    from core.bot_dispatcher import dispatch_command
    from core.bot_message_handler import MessageClassifier
    from core.pm_message_handler import handle_bot_message
    assert MessageClassifier is not None
    assert handle_bot_message is not None
    assert dispatch_command is not None
