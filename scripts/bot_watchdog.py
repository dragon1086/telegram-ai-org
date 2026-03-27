#!/usr/bin/env python3
"""봇 프로세스 watchdog — 죽은 봇 자동 감지 + 재시작 + Telegram 알림.

사용법:
  python scripts/bot_watchdog.py          # 포그라운드 실행
  python scripts/bot_watchdog.py --once   # 1회 점검 후 종료

30초 간격으로 모든 봇 프로세스 생존 여부를 확인하고,
죽은 봇이 있으면 자동 재시작 후 Rocky에게 Telegram 알림을 보낸다.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# ── 설정 ──────────────────────────────────────────────────────────────────────
CHECK_INTERVAL = 30  # 초
MAX_RESTART_PER_BOT = 5  # 연속 재시작 한도 (무한루프 방지)
RESTART_COUNT_RESET_AFTER = 600  # 10분 동안 안정적이면 카운터 리셋
LOG_STALENESS_THRESHOLD = 600  # 10분간 로그 갱신 없으면 hung으로 판단
ORPHAN_CHECK_INTERVAL = 300  # 5분마다 고아 프로세스 점검
ORPHAN_AGE_THRESHOLD = 3600  # 1시간 이상된 고아만 kill (작업중인 프로세스 보호)
AI_ORG_LOG_DIR = Path.home() / ".ai-org"
PID_FILE = Path("/tmp/bot-watchdog.pid")
RESTART_FLAG = Path.home() / ".ai-org" / "restart_requested"

PROJECT_DIR = Path(__file__).parent.parent
# bot-runtime 워크트리 우선 사용
_BOT_RUNTIME = PROJECT_DIR / ".worktrees" / "bot-runtime"
RUNTIME_DIR = _BOT_RUNTIME if (_BOT_RUNTIME / "main.py").exists() else PROJECT_DIR
sys.path.insert(0, str(RUNTIME_DIR))

# ── 환경변수 자동 로드 (nohup 독립 실행 시 env 미상속 대비) ─────────────────
for _env_src in (Path.home() / ".ai-org" / "config.yaml", RUNTIME_DIR / ".env"):
    if _env_src.exists():
        for _line in _env_src.read_text().splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                os.environ.setdefault(_k.strip(), _v.strip())

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | bot_watchdog | %(message)s",
)
log = logging.getLogger("bot_watchdog")

# ── Telegram 알림 ────────────────────────────────────────────────────────────
# 그룹 채팅으로 알림 전송 (개인 DM은 /start 필요 → 403 발생)
ALERT_CHAT_ID = os.environ.get("TELEGRAM_GROUP_CHAT_ID", "-5203707291")


def _load_env_config() -> dict[str, str]:
    """~/.ai-org/config.yaml (.env 형식) 파싱."""
    config_path = Path.home() / ".ai-org" / "config.yaml"
    if not config_path.exists():
        return {}
    result = {}
    for line in config_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            result[k.strip()] = v.strip()
    return result


def _get_admin_token() -> str | None:
    """PM 봇 토큰을 config에서 읽어 알림용으로 사용."""
    cfg = _load_env_config()
    token = cfg.get("PM_BOT_TOKEN")
    if token:
        return token
    return os.environ.get("PM_BOT_TOKEN")


def notify_rocky(message: str) -> None:
    """Telegram으로 Rocky에게 알림 전송."""
    token = _get_admin_token()
    if not token:
        log.warning("알림 토큰 없음 — Telegram 알림 스킵")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": ALERT_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
        log.info("Telegram 알림 전송 완료")
    except Exception as e:
        log.error(f"Telegram 알림 실패: {e}")


# ── 봇 상태 확인 ──────────────────────────────────────────────────────────────
def get_bot_heartbeat_path(org_id: str) -> Path:
    """봇 heartbeat 파일 경로 반환 (~/.ai-org/{org_id}.heartbeat)."""
    return AI_ORG_LOG_DIR / f"{org_id}.heartbeat"


def check_log_hung(org_id: str) -> bool:
    """봇이 hung 상태인지 heartbeat freshness로 판단.

    조건:
      - 프로세스는 살아있지만
      - heartbeat 파일이 LOG_STALENESS_THRESHOLD(10분) 이상 갱신되지 않음
      - heartbeat 파일이 1시간 이내에 존재한 적 있음 (장기 미시작 봇 오판 방지)

    NOTE: 봇은 idle/active 무관하게 60초마다 heartbeat 파일을 touch한다.
    10분 침묵 = asyncio 이벤트 루프 hang (touch 스레드도 멈춤).
    로그 파일은 idle 시 무음이므로 hung 감지에 사용하지 않는다.
    """
    hb_path = get_bot_heartbeat_path(org_id)
    if not hb_path.exists():
        return False
    now = time.time()
    age = now - hb_path.stat().st_mtime
    recently_active = age < 3600  # 1시간 이내 갱신된 적 있어야 hung 의심
    return age > LOG_STALENESS_THRESHOLD and recently_active


def kill_hung_bot(org_id: str) -> None:
    """응답 없는 hung 봇 프로세스를 SIGKILL로 강제 종료."""
    from scripts.bot_manager import _find_live_pids
    pids = _find_live_pids(org_id)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
            log.info(f"hung 봇 강제 종료: {org_id} PID={pid}")
        except OSError as e:
            log.warning(f"봇 {org_id} PID={pid} 종료 실패: {e}")


def get_expected_orgs() -> list[dict]:
    """orchestration config에서 실행되어야 할 봇 목록 로드."""
    try:
        from core.orchestration_config import load_orchestration_config
        cfg = load_orchestration_config(force_reload=True)
        orgs = []
        for org in cfg.list_orgs():
            if org.token and org.chat_id is not None:
                orgs.append({
                    "id": org.id,
                    "token": org.token,
                    "chat_id": org.chat_id,
                })
        return orgs
    except Exception as e:
        log.error(f"orchestration config 로드 실패: {e}")
        return []


def check_bot_alive(org_id: str) -> bool:
    """봇 프로세스가 살아있는지 확인."""
    from scripts.bot_manager import _find_live_pids
    return bool(_find_live_pids(org_id))


def restart_bot(org_id: str, token: str, chat_id: int) -> int | None:
    """죽은 봇을 재시작하고 새 PID 반환."""
    try:
        from scripts.bot_manager import start_bot
        pid = start_bot(token=token, org_id=org_id, chat_id=chat_id)
        log.info(f"봇 재시작 성공: {org_id} (PID={pid})")
        return pid
    except Exception as e:
        log.error(f"봇 재시작 실패: {org_id} — {e}")
        return None


# ── 고아 프로세스 정리 ────────────────────────────────────────────────────────
def cleanup_orphan_agent_processes() -> int:
    """PPID=1인 claude_agent_sdk/codex 고아 프로세스를 찾아 종료.

    봇이 재기동되면 자식 프로세스(claude_agent_sdk, codex)가 PPID=1로 떠서
    영원히 살아있는 문제를 방지한다. ORPHAN_AGE_THRESHOLD(1시간) 이상된 것만 kill.
    """
    import subprocess
    killed = 0
    try:
        # ps로 PPID=1인 claude_agent_sdk/codex 프로세스 조회
        out = subprocess.check_output(
            ["ps", "-eo", "pid,ppid,etimes,command"], text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return 0

    for line in out.splitlines()[1:]:  # 헤더 스킵
        parts = line.split(None, 3)
        if len(parts) < 4:
            continue
        try:
            pid, ppid, elapsed_sec = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            continue
        cmd = parts[3]

        if ppid != 1:
            continue
        if "claude_agent_sdk" not in cmd and "codex" not in cmd:
            continue
        if elapsed_sec < ORPHAN_AGE_THRESHOLD:
            continue

        try:
            os.kill(pid, signal.SIGTERM)
            killed += 1
            log.info(f"고아 프로세스 종료: PID={pid} (경과 {elapsed_sec}초)")
        except OSError as e:
            log.warning(f"고아 PID={pid} 종료 실패: {e}")

    if killed:
        log.info(f"고아 프로세스 {killed}개 정리 완료")
    return killed


# ── 메인 루프 ─────────────────────────────────────────────────────────────────
class BotWatchdog:
    def __init__(self):
        self.restart_counts: dict[str, int] = {}  # org_id -> 연속 재시작 횟수
        self.last_restart_time: dict[str, float] = {}  # org_id -> 마지막 재시작 시각
        self.last_orphan_check: float = 0.0  # 마지막 고아 점검 시각
        self.running = True

    def _handle_signal(self, signum, frame):
        log.info(f"시그널 수신 ({signum}), 종료 중...")
        self.running = False

    def _check_restart_flag(self) -> bool:
        """deferred restart 플래그 확인. 있으면 재기동 실행 후 True 반환."""
        if not RESTART_FLAG.exists():
            return False
        try:
            data = json.loads(RESTART_FLAG.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        RESTART_FLAG.unlink(missing_ok=True)

        target = data.get("target", "all")
        reason = data.get("reason", "")
        requested_by = data.get("requested_by", "unknown")
        log.info(f"재기동 플래그 감지: target={target}, by={requested_by}, reason={reason}")

        import subprocess
        if target == "all":
            restart_script = RUNTIME_DIR / "scripts" / "restart_bots.sh"
            subprocess.run(["bash", str(restart_script)], check=False)
            notify_rocky(
                f"<b>봇 재기동 (deferred)</b>\n"
                f"대상: 전체\n"
                f"요청자: <code>{requested_by}</code>\n"
                f"사유: {reason or '(없음)'}"
            )
        else:
            # 특정 봇만 재시작
            from scripts.bot_manager import start_bot, stop_bot
            orgs = {o["id"]: o for o in get_expected_orgs()}
            if target in orgs:
                stop_bot(target)
                time.sleep(2)
                org = orgs[target]
                start_bot(token=org["token"], org_id=target, chat_id=org["chat_id"])
                notify_rocky(
                    f"<b>봇 재기동 (deferred)</b>\n"
                    f"대상: <code>{target}</code>\n"
                    f"요청자: <code>{requested_by}</code>\n"
                    f"사유: {reason or '(없음)'}"
                )
            else:
                log.warning(f"재기동 대상 {target} 을 찾을 수 없음")
        return True

    def check_and_restart(self) -> list[str]:
        """모든 봇 점검. 재시작한 봇 ID 리스트 반환."""
        orgs = get_expected_orgs()
        if not orgs:
            return []

        restarted = []
        for org in orgs:
            org_id = org["id"]

            # 안정 기간 경과 시 카운터 리셋
            last_time = self.last_restart_time.get(org_id, 0)
            if time.time() - last_time > RESTART_COUNT_RESET_AFTER:
                self.restart_counts[org_id] = 0

            if check_bot_alive(org_id):
                if check_log_hung(org_id):
                    # 프로세스 살아있지만 hung — 강제 종료 후 재시작
                    log.warning(
                        f"봇 {org_id}: 프로세스 alive지만 {LOG_STALENESS_THRESHOLD}초간 "
                        f"로그 갱신 없음 — hung 감지, 강제 재시작"
                    )
                    notify_rocky(
                        f"<b>봇 hung 감지 → 자동 재시작</b>\n"
                        f"봇: <code>{org_id}</code>\n"
                        f"증상: {LOG_STALENESS_THRESHOLD}초 이상 로그 무응답\n"
                        f"(heartbeat 멈춤 = asyncio 이벤트 루프 hang)\n"
                        f"시각: {time.strftime('%H:%M:%S')}"
                    )
                    kill_hung_bot(org_id)
                    time.sleep(2)  # 프로세스 정리 대기
                else:
                    continue  # 정상 동작 중

            # 죽은 봇 (또는 hung으로 강제 종료된 봇) 재시작
            count = self.restart_counts.get(org_id, 0)
            if count >= MAX_RESTART_PER_BOT:
                log.error(
                    f"봇 {org_id}: 연속 {count}회 재시작 한도 초과 — 재시작 중단"
                )
                if count == MAX_RESTART_PER_BOT:  # 최초 한도 초과 시 1회만 알림
                    notify_rocky(
                        f"<b>CRITICAL: 봇 재시작 한도 초과</b>\n"
                        f"봇: <code>{org_id}</code>\n"
                        f"연속 {count}회 재시작 실패 — 수동 점검 필요"
                    )
                    self.restart_counts[org_id] = count + 1  # 알림 중복 방지
                continue

            log.warning(f"봇 {org_id} 프로세스 없음 — 재시작 시도 ({count + 1}/{MAX_RESTART_PER_BOT})")
            pid = restart_bot(org_id, org["token"], org["chat_id"])
            self.restart_counts[org_id] = count + 1
            self.last_restart_time[org_id] = time.time()

            if pid:
                restarted.append(org_id)

        return restarted

    @staticmethod
    def _kill_stale_instances():
        """기존 watchdog 프로세스 모두 종료 (좀비 방지)."""
        import subprocess
        my_pid = os.getpid()
        try:
            out = subprocess.check_output(
                ["pgrep", "-f", "bot_watchdog\\.py"], text=True,
            ).strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return
        for line in out.splitlines():
            pid = int(line.strip())
            if pid == my_pid:
                continue
            try:
                os.kill(pid, signal.SIGKILL)
                log.info(f"좀비 watchdog 종료: PID {pid}")
            except OSError:
                pass

    def run(self, once: bool = False):
        """메인 루프."""
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        # 기존 좀비 watchdog 정리 후 시작
        self._kill_stale_instances()

        # PID 파일 기록
        PID_FILE.write_text(str(os.getpid()))
        log.info(f"봇 watchdog 시작 (PID={os.getpid()}, 간격={CHECK_INTERVAL}s)")

        try:
            while self.running:
                # deferred restart 플래그 우선 처리
                if self._check_restart_flag():
                    time.sleep(CHECK_INTERVAL)
                    continue

                restarted = self.check_and_restart()
                if restarted:
                    notify_rocky(
                        f"<b>봇 자동 재시작</b>\n"
                        f"재시작된 봇: {', '.join(f'<code>{r}</code>' for r in restarted)}\n"
                        f"시각: {time.strftime('%H:%M:%S')}"
                    )

                # 주기적 고아 프로세스 정리 (ORPHAN_CHECK_INTERVAL마다)
                now = time.time()
                if now - self.last_orphan_check >= ORPHAN_CHECK_INTERVAL:
                    killed = cleanup_orphan_agent_processes()
                    self.last_orphan_check = now
                    if killed:
                        notify_rocky(
                            f"<b>고아 프로세스 자동 정리</b>\n"
                            f"종료: {killed}개 (claude_agent_sdk/codex, PPID=1)\n"
                            f"시각: {time.strftime('%H:%M:%S')}"
                        )

                if once:
                    break

                time.sleep(CHECK_INTERVAL)
        finally:
            PID_FILE.unlink(missing_ok=True)
            log.info("봇 watchdog 종료")


if __name__ == "__main__":
    os.chdir(RUNTIME_DIR)
    once = "--once" in sys.argv
    watchdog = BotWatchdog()
    watchdog.run(once=once)
