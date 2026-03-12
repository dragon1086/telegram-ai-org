#!/usr/bin/env python3
"""telegram-ai-org PM 봇 진입점.

아키텍처: Python봇은 얇은 relay, 진짜 두뇌는 tmux 상주 Claude Code.
진입점: TelegramRelay 사용 (core/pm_bot.py의 PMBot는 DEPRECATED)
"""
import logging
import os
import time
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

    # 조직별 engine 설정 지원: PM_ORG_NAME이 설정되면 organizations.yaml에서 engine을 읽어온다.
    # 없으면 기존 동작 유지 (claude-code 기본값).
    org_id = os.environ.get("PM_ORG_NAME", "global")
    engine = "claude-code"

    pm_org_name = os.environ.get("PM_ORG_NAME")
    if pm_org_name:
        try:
            from pathlib import Path as _Path
            from core.org_registry import OrgRegistry
            _registry = OrgRegistry(_Path(__file__).parent / "organizations.yaml")
            _registry.load()
            _org = _registry.get_org(pm_org_name)
            if _org is not None:
                engine = _org.engine
        except Exception as _e:
            import logging as _logging
            _logging.warning(f"organizations.yaml에서 engine 로드 실패: {_e}")

    session_manager = SessionManager()
    memory_manager = MemoryManager(org_id)

    relay = TelegramRelay(
        token=token,
        allowed_chat_id=chat_id,
        session_manager=session_manager,
        memory_manager=memory_manager,
        org_id=org_id,
        engine=engine,
    )
    max_retries = 15
    for attempt in range(max_retries):
        app = relay.build()  # 매 시도마다 새 Application 생성
        _start = time.time()
        try:
            app.run_polling(drop_pending_updates=True)
        except Exception as _e:
            print(f'[ERROR] 봇 실행 오류: {_e}', flush=True)
            raise
        _elapsed = time.time() - _start
        if _elapsed > 10:
            print(f'[OK] 봇 정상 종료 (실행 {_elapsed:.0f}초)', flush=True)
            break
        wait = 10 * (attempt + 1)
        print(f'[RETRY] Conflict 추정 ({_elapsed:.1f}초), {wait}초 후 재시도 ({attempt+1}/{max_retries})', flush=True)
        time.sleep(wait)
