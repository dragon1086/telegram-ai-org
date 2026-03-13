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

from core.message_bus import MessageBus
from core.session_manager import SessionManager
from core.memory_manager import MemoryManager
from core.telegram_relay import TelegramRelay
from core.pm_orchestrator import ENABLE_PM_ORCHESTRATOR

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

    token = os.environ["PM_BOT_TOKEN"]
    chat_id = int(os.environ["TELEGRAM_GROUP_CHAT_ID"])

    # 조직별 engine 설정 지원: PM_ORG_NAME이 설정되면 organizations.yaml에서 engine을 읽어온다.
    # 없으면 기존 동작 유지 (claude-code 기본값).
    org_id = os.environ.get("PM_ORG_NAME", "global")
    engine = "claude-code"

    pm_org_name = os.environ.get("PM_ORG_NAME")
    if pm_org_name:
        # 1) organizations.yaml에서 시도
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

        # 2) organizations.yaml에 없으면 bots/{org_id}.yaml에서 engine 읽기
        if engine == "claude-code":
            try:
                from pathlib import Path as _Path
                _bot_yaml = _Path(__file__).parent / "bots" / f"{pm_org_name}.yaml"
                if _bot_yaml.exists():
                    import yaml as _yaml
                    with open(_bot_yaml) as _f:
                        _bot_cfg = _yaml.safe_load(_f) or {}
                    if _bot_cfg.get("engine"):
                        engine = _bot_cfg["engine"]
            except Exception as _e2:
                import logging as _logging
                _logging.warning(f"bots/{pm_org_name}.yaml에서 engine 로드 실패: {_e2}")

    session_manager = SessionManager()
    memory_manager = MemoryManager(org_id)
    bus = MessageBus()

    # PM 오케스트레이터 모드: ContextDB 초기화
    context_db = None
    if ENABLE_PM_ORCHESTRATOR:
        import asyncio as _aio
        from core.context_db import ContextDB
        context_db = ContextDB()
        _aio.get_event_loop().run_until_complete(context_db.initialize())

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
                    asyncio.get_event_loop().run_until_complete(app.shutdown())
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
