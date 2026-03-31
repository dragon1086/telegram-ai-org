"""Phase 1 단위 테스트 — core.interfaces 모듈.

테스트 대상: core/interfaces.py (Protocol 정의 검증)
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Protocol 임포트 검증
# ---------------------------------------------------------------------------

class TestInterfacesImport:
    def test_base_runner_importable(self):
        from core.interfaces import BaseRunner
        assert BaseRunner is not None

    def test_telegram_interface_importable(self):
        from core.interfaces import TelegramInterface
        assert TelegramInterface is not None

    def test_task_repository_interface_importable(self):
        from core.interfaces import TaskRepositoryInterface
        assert TaskRepositoryInterface is not None

    def test_message_repository_interface_importable(self):
        from core.interfaces import MessageRepositoryInterface
        assert MessageRepositoryInterface is not None


# ---------------------------------------------------------------------------
# Protocol 구조 검증
# ---------------------------------------------------------------------------

class TestBaseRunner:
    def test_base_runner_has_engine_name(self):
        from core.interfaces import BaseRunner
        # Protocol 메서드/속성 확인
        annotations = getattr(BaseRunner, '__protocol_attrs__', None) or dir(BaseRunner)
        assert 'engine_name' in str(annotations) or hasattr(BaseRunner, 'engine_name')

    def test_concrete_class_satisfies_base_runner(self):
        """Protocol을 만족하는 구체 클래스를 생성할 수 있어야 한다."""
        from core.interfaces import BaseRunner

        class MockRunner:
            engine_name = "test-engine"

            async def run(self, task: str, persona=None) -> str:
                return "result"

            async def health_check(self) -> bool:
                return True

        runner = MockRunner()
        assert isinstance(runner, BaseRunner)

    def test_class_without_engine_name_fails_check(self):
        """engine_name 없는 클래스는 BaseRunner 프로토콜을 만족하지 않아야 한다."""
        from core.interfaces import BaseRunner

        class BadRunner:
            async def run(self, task: str) -> str:
                return "result"

            async def health_check(self) -> bool:
                return True
        # engine_name 없으면 isinstance 실패
        assert not isinstance(BadRunner(), BaseRunner)

    def test_base_runner_run_method_signature(self):
        """run 메서드가 Protocol에 정의되어 있어야 한다."""
        from core.interfaces import BaseRunner
        assert callable(getattr(BaseRunner, 'run', None)) or 'run' in dir(BaseRunner)


class TestTelegramInterface:
    def test_concrete_class_satisfies_telegram_interface(self):
        from core.interfaces import TelegramInterface

        class MockTelegram:
            async def send_message(self, chat_id: int, text: str, **kwargs) -> None:
                pass

            async def send_document(self, chat_id: int, document: bytes, filename: str) -> None:
                pass

        assert isinstance(MockTelegram(), TelegramInterface)

    def test_missing_send_document_fails(self):
        from core.interfaces import TelegramInterface

        class IncompleteTelegram:
            async def send_message(self, chat_id: int, text: str, **kwargs) -> None:
                pass
        # send_document 없으면 실패해야 한다
        assert not isinstance(IncompleteTelegram(), TelegramInterface)


class TestTaskRepositoryInterface:
    def test_concrete_class_satisfies_task_repository_interface(self):
        from core.interfaces import TaskRepositoryInterface

        class MockRepo:
            async def get(self, task_id: str):
                return None

            async def save(self, task: dict) -> None:
                pass

            async def list_by_status(self, status: str) -> list:
                return []

            async def delete(self, task_id: str) -> None:
                pass

        assert isinstance(MockRepo(), TaskRepositoryInterface)
