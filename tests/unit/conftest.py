"""tests/unit/conftest.py — 단위 테스트 공통 fixture

모듈 레벨 sys.modules 직접 주입 패턴(오염 가능성)을 pytest fixture 범위로
한정하기 위해 이 conftest를 사용한다.

변경 이유 (R-02):
  test_telegram_sender.py 상단에 있던 top-level sys.modules 주입 코드를
  autouse fixture 방식으로 대체. 이렇게 하면:
  - 주입 범위가 'session' 스코프 내로 명확하게 제한됨
  - 실제로 패키지가 설치된 경우에도 다른 테스트를 오염시키지 않음
  - 테스트 수집 순서에 무관하게 동작 보장
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# telegram / aiosqlite — 테스트 환경 미설치 패키지 안전 mock
# ---------------------------------------------------------------------------

_MISSING_PACKAGES = (
    "telegram",
    "telegram.ext",
    "telegram.constants",
    "aiosqlite",
)


def _is_actually_installed(package_top: str) -> bool:
    """패키지가 실제로 설치되어 있는지 확인한다 (importlib 기반)."""
    import importlib.util
    # 최상위 패키지 이름만 검사 (telegram.ext → telegram)
    top = package_top.split(".")[0]
    return importlib.util.find_spec(top) is not None


@pytest.fixture(scope="session", autouse=True)
def mock_missing_packages():
    """테스트 환경에 없는 패키지를 session 스코프 patch.dict 로 격리 주입.

    patch.dict 를 사용하면 teardown 시 자동으로 복원되므로
    다른 테스트 suite 오염을 방지한다.

    실제로 설치된 패키지(aiosqlite 등)는 mock 대상에서 제외한다.
    """
    import sys
    from unittest.mock import patch

    fake_modules = {
        mod: MagicMock()
        for mod in _MISSING_PACKAGES
        if mod not in sys.modules and not _is_actually_installed(mod)
    }
    if not fake_modules:
        yield
        return

    with patch.dict(sys.modules, fake_modules):
        yield
