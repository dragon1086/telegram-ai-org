#!/usr/bin/env python3
"""telegram-ai-org PM 봇 진입점.

아키텍처: Python봇은 얇은 relay, 진짜 두뇌는 tmux 상주 Claude Code.
"""
import os
from pathlib import Path

# .env 로드
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

from core.session_manager import SessionManager
from core.memory_manager import MemoryManager
from core.telegram_relay import TelegramRelay

if __name__ == "__main__":
    token = os.environ["PM_BOT_TOKEN"]
    chat_id = int(os.environ["TELEGRAM_GROUP_CHAT_ID"])

    session_manager = SessionManager()
    memory_manager = MemoryManager("global")

    relay = TelegramRelay(
        token=token,
        allowed_chat_id=chat_id,
        session_manager=session_manager,
        memory_manager=memory_manager,
    )
    app = relay.build()
    app.run_polling(drop_pending_updates=True)
