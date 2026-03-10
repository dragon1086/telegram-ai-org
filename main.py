#!/usr/bin/env python3
"""telegram-ai-org PM 봇 진입점."""
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

from core.pm_bot import PMBot

if __name__ == "__main__":
    bot = PMBot()
    app = bot.build()
    app.run_polling(drop_pending_updates=True)
