#!/usr/bin/env python3
"""telegram-ai-org PM 봇 진입점.

아키텍처: Python봇은 얇은 relay, 진짜 두뇌는 tmux 상주 Claude Code.
진입점: TelegramRelay 사용 (core/pm_bot.py의 PMBot는 DEPRECATED)
"""
import logging
import os
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())


for _env_path in (Path.home() / ".ai-org" / "config.yaml", PROJECT_ROOT / ".env"):
    _load_env_file(_env_path)

from core.message_bus import MessageBus
from core.session_manager import SessionManager
from core.memory_manager import MemoryManager
from core.telegram_relay import TelegramRelay
from core.pm_orchestrator import ENABLE_PM_ORCHESTRATOR
from core.orchestration_config import load_orchestration_config


def _resolve_runtime_binding(org_id: str) -> tuple[str, int, str]:
    token = os.environ.get("PM_BOT_TOKEN", "")
    chat_id_raw = os.environ.get("TELEGRAM_GROUP_CHAT_ID", "")
    engine = "claude-code"

    try:
        cfg = load_orchestration_config(force_reload=True)
        org = cfg.get_org(org_id)
    except Exception:
        org = None

    if org is not None:
        if not token:
            token = org.token
        if not chat_id_raw and org.chat_id is not None:
            chat_id_raw = str(org.chat_id)
        engine = org.preferred_engine or engine

    if not token or not chat_id_raw:
        raise RuntimeError(f"org '{org_id}' binding is incomplete")
    return token, int(chat_id_raw), engine

if __name__ == "__main__":
    # ── PID lock (중복 실행 방지) ─────────────────────────────────────────
    import fcntl
    _pid_file = Path(f"/tmp/telegram-ai-org-{os.environ.get('PM_ORG_NAME', 'global')}.pid")
    _lock_fh = open(_pid_file, "w")
    try:
        fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _pid_file.write_text(str(os.getpid()))
    except IOError:
        existing = _pid_file.read_text().strip() if _pid_file.exists() else "?"
        print(f"[ABORT] 이미 실행 중인 인스턴스 있음 (PID {existing}). 종료.", flush=True)
        import sys; sys.exit(1)
    # ─────────────────────────────────────────────────────────────────────

    org_id = os.environ.get("PM_ORG_NAME", "global")
    token, chat_id, engine = _resolve_runtime_binding(org_id)

    session_manager = SessionManager()
    memory_manager = MemoryManager(org_id)
    bus = MessageBus()

    # PM 오케스트레이터 모드: ContextDB 초기화
    context_db = None
    if ENABLE_PM_ORCHESTRATOR:
        import asyncio as _aio
        from core.context_db import ContextDB
        context_db = ContextDB()
        _aio.run(context_db.initialize())

    relay = TelegramRelay(
        token=token,
        allowed_chat_id=chat_id,
        session_manager=session_manager,
        memory_manager=memory_manager,
        org_id=org_id,
        engine=engine,
        bus=bus,
        context_db=context_db,
    )
    max_retries = 10
    CONFLICT_WAIT = 70  # Telegram 서버 long-polling timeout(60s) + 여유

    for attempt in range(max_retries):
        app = relay.build()  # 매 시도마다 새 Application 생성
        _start = time.time()
        try:
            app.run_polling(drop_pending_updates=True)
        except Exception as _e:
            err_str = str(_e)
            print(f'[ERROR] 봇 실행 오류: {_e}', flush=True)
            if 'Conflict' in err_str or 'conflict' in err_str:
                # Application 완전 종료 후 충분히 대기
                try:
                    import asyncio
                    asyncio.run(app.shutdown())
                except Exception:
                    pass
                print(f'[CONFLICT] Telegram 서버 연결 만료 대기 ({CONFLICT_WAIT}초)...', flush=True)
                time.sleep(CONFLICT_WAIT)
                continue  # 재시도
            else:
                raise
        _elapsed = time.time() - _start
        if _elapsed > 10:
            print(f'[OK] 봇 정상 종료 (실행 {_elapsed:.0f}초)', flush=True)
            break
        wait = CONFLICT_WAIT
        print(f'[RETRY] 빠른 종료 ({_elapsed:.1f}초), {wait}초 후 재시도 ({attempt+1}/{max_retries})', flush=True)
        time.sleep(wait)
