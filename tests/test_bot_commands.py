from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.bot_commands import get_bot_commands


def test_common_commands_include_verbose() -> None:
    commands = get_bot_commands("specialist")
    names = [command.command for command in commands]

    assert "verbose" in names
