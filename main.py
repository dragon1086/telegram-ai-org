#!/usr/bin/env python3
"""telegram-ai-org PM 봇 진입점.

아키텍처: Python봇은 얇은 relay, 진짜 두뇌는 tmux 상주 Claude Code.
진입점: TelegramRelay 사용 (core/pm_bot.py의 PMBot는 DEPRECATED)
"""
import os
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent

# ── httpcore/sniffio 호환성 패치 ─────────────────────────────────────────────
# Python 3.14 + httpcore 1.0.9 + sniffio: polling 종료 시 async context 소실로
# AsyncLibraryNotFoundError 발생 → PM봇 반복 재시작. asyncio 기본값으로 fallback.
try:
    import httpcore._synchronization as _hc_sync
    _original_cal = _hc_sync.current_async_library
    def _patched_current_async_library() -> str:
        try:
            return _original_cal()
        except Exception:
            return "asyncio"
    _hc_sync.current_async_library = _patched_current_async_library
except Exception:
    pass


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    # .yaml/.yml 파일은 yaml.safe_load로 파싱 (KEY: value 형식)
    if path.suffix in (".yaml", ".yml"):
        try:
            import yaml
            data = yaml.safe_load(path.read_text()) or {}
            if isinstance(data, dict):
                for k, v in data.items():
                    os.environ.setdefault(str(k).strip(), str(v).strip())
        except Exception:
            pass
        return
    # .env 형식 (KEY=VALUE)
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
    # ── CLI 인수 파싱 ──────────────────────────────────────────────────────
    import argparse
    _parser = argparse.ArgumentParser()
    _parser.add_argument("--org", default=None)
    _args, _ = _parser.parse_known_args()
    if _args.org:
        os.environ["PM_ORG_NAME"] = _args.org
    # ── PID lock (중복 실행 방지) ─────────────────────────────────────────
    import fcntl
    _pid_file = Path(f"/tmp/telegram-ai-org-{os.environ.get('PM_ORG_NAME', 'global')}.pid")
    _lock_fh = open(_pid_file, "w")
    try:
        fcntl.flock(_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_fh.write(str(os.getpid()))
        _lock_fh.flush()
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

    # ProactiveHandler: INACTIVITY_DETECTED / DAILY_INSIGHT 이벤트 구독
    from core.proactive_handler import ProactiveHandler
    _proactive_handler = ProactiveHandler(bus, bots={})
    _proactive_handler.register()

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
    # ── idle heartbeat — watchdog hung 감지용 ────────────────────────────────
    # idle 봇도 60초마다 파일을 touch해 "살아있음"을 알림.
    # 이 파일이 10분 이상 갱신되지 않으면 → asyncio 루프 hang으로 판단.
    import threading
    _hb_file = Path.home() / ".ai-org" / f"{org_id}.heartbeat"
    def _heartbeat_worker() -> None:
        while True:
            try:
                _hb_file.touch()
            except Exception:
                pass
            time.sleep(60)
    threading.Thread(target=_heartbeat_worker, daemon=True, name=f"heartbeat-{org_id}").start()
    # ─────────────────────────────────────────────────────────────────────────

    CONFLICT_WAIT = 70  # Telegram 서버 long-polling timeout(60s) + 여유
    RESTART_WAIT = 5    # 정상 종료 후 자동 재시작 대기

    while True:
        app = relay.build()  # 매 시도마다 새 Application 생성
        _start = time.time()
        try:
            app.run_polling(drop_pending_updates=True)
        except KeyboardInterrupt:
            print('[OK] 봇 종료 (Ctrl+C)', flush=True)
            break
        except SystemExit:
            print('[OK] 봇 종료 (SIGTERM)', flush=True)
            break
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
            elif 'AsyncLibraryNotFoundError' in err_str:
                # httpcore/sniffio 호환성 문제 — 일시적 오류로 재시도
                print(f'[ASYNC-ERR] sniffio 감지 실패, {RESTART_WAIT}초 후 재시도...', flush=True)
                time.sleep(RESTART_WAIT)
                continue
            else:
                raise
        _elapsed = time.time() - _start
        if _elapsed < 10:
            print(f'[RETRY] 빠른 종료 ({_elapsed:.1f}초), {CONFLICT_WAIT}초 후 재시도...', flush=True)
            time.sleep(CONFLICT_WAIT)
        else:
            # Conflict 등으로 run_polling이 정상 리턴한 경우 — 자동 재시작
            # 의도적 종료(SIGTERM/SIGINT)는 위에서 break로 빠진다.
            print(f'[RESTART] 봇 종료 (실행 {_elapsed:.0f}초), {RESTART_WAIT}초 후 자동 재시작...', flush=True)
            time.sleep(RESTART_WAIT)
