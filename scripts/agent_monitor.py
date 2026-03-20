#!/usr/bin/env python3
"""agent_monitor.py — aiorg Claude agent tmux 세션 감시 + 3단계 자동 처리 데몬.

동작:
  1. 30초마다 aiorg_aiorg_* tmux 세션 모든 창 캡처
  2. 콘텐츠가 STUCK_THRESHOLD(180초)간 변화 없고 입력 대기 감지 시
  3. 3단계 자동 처리:
     a) 안전한 패턴 (y/n, 계속 등) → 규칙 기반 고정 응답 주입
     b) 판단 필요한 질문 → 에이전트 자기 판단 유도 메시지 주입
     c) fresh 세션 (할 일 없음) → HEARTBEAT.md 확인 지시 주입
  4. 텔레그램 알림 + 로그 기록

사용법:
  python scripts/agent_monitor.py           # 포그라운드
  python scripts/agent_monitor.py --daemon  # 백그라운드 (nohup)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# ── 설정 ──────────────────────────────────────────────────────────────────────
POLL_INTERVAL = 30           # 세션 확인 주기 (초)
STUCK_THRESHOLD = 180        # 이 시간(초) 동안 변화 없으면 "stuck" 의심
RESPONSE_COOLDOWN = 300      # 같은 세션에 연속 응답 최소 간격 (초)
SESSION_PREFIX = "aiorg_aiorg_"
STATE_FILE = Path("/tmp/agent-monitor-state.json")
LOG_FILE = Path.home() / ".ai-org" / "agent-monitor.log"
PID_FILE = Path("/tmp/agent-monitor.pid")

# ── 3단계 응답 분류 ───────────────────────────────────────────────────────────
# SAFE: 규칙 기반 고정 응답 (LLM 불필요)
SAFE_PATTERNS: dict[str, str] = {
    "y/n": "y",
    "yes/no": "yes",
    "? (y": "y",
    "[y/n]": "y",
    "[yes/no]": "yes",
    "confirm": "yes",
    "proceed": "yes",
    "계속": "네",
    "진행": "네",
    "확인": "네",
    "실행": "네",
}

# QUESTION: 판단 필요한 질문 패턴 → 에이전트 자기 판단 유도
QUESTION_PATTERNS = [
    "할까요", "하시겠습니까", "하겠습니까", "선택", "입력하세요",
    "would you like", "do you want", "should i", "shall i",
    "재시작", "종료", "삭제",
]

# 에이전트 자기 판단 유도 메시지
NUDGE_MESSAGE = "입력 대기 상태야. 안전한 기본값으로 스스로 판단해서 진행해. 위험한 작업(삭제, 프로덕션 변경)은 하지 마."

# fresh 세션 → HEARTBEAT 확인 지시
FRESH_NUDGE = "HEARTBEAT.md를 읽고 할당된 태스크가 있으면 진행해. 없으면 대기해."

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [monitor] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ── tmux 헬퍼 ─────────────────────────────────────────────────────────────────

def get_aiorg_sessions() -> list[tuple[str, int]]:
    """(session_name, window_index) 목록 반환."""
    try:
        out = subprocess.check_output(
            ["tmux", "list-windows", "-a", "-F", "#{session_name}:#{window_index}"],
            text=True, stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return []
    results = []
    for line in out.strip().splitlines():
        parts = line.rsplit(":", 1)
        if len(parts) == 2 and parts[0].startswith(SESSION_PREFIX):
            try:
                results.append((parts[0], int(parts[1])))
            except ValueError:
                pass
    return results


def capture_pane(session: str, window: int) -> str:
    try:
        return subprocess.check_output(
            ["tmux", "capture-pane", "-t", f"{session}:{window}", "-p", "-S", "-60"],
            text=True, stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return ""


def send_keys(session: str, window: int, text: str) -> None:
    subprocess.run(
        ["tmux", "send-keys", "-t", f"{session}:{window}", text, "Enter"],
        stderr=subprocess.DEVNULL,
    )


# ── 감지 로직 ─────────────────────────────────────────────────────────────────

def extract_meaningful_lines(pane: str) -> list[str]:
    """상태바, 구분선 등 노이즈 제거 후 의미있는 줄만 반환."""
    skip_patterns = ("[OMC", "bypass permissions", "─" * 10, "════")
    lines = []
    for line in pane.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(p in stripped for p in skip_patterns):
            continue
        lines.append(stripped)
    return lines


FRESH_SESSION_MARKERS = ("claude code", "sonnet", "haiku", "opus", "bypass permissions on")


def classify_stuck(pane: str) -> tuple[str, str, str]:
    """stuck 유형 분류. 반환: (action, response, context).

    action 값:
      "none"  — 입력 대기 아님, 무시
      "safe"  — 안전한 패턴 매칭, 고정 응답 주입
      "nudge" — 판단 필요, 자기 판단 유도 메시지 주입
      "fresh" — 새 세션, HEARTBEAT 확인 지시 주입
    """
    lines = extract_meaningful_lines(pane)
    if not lines:
        return "none", "", ""

    last_line = lines[-1]
    at_prompt = last_line in ("❯", "") or last_line.endswith("❯")
    if not at_prompt:
        return "none", "", ""

    recent = "\n".join(lines[-30:]).lower()
    context = "\n".join(lines[-40:])

    # 1) fresh 세션 감지
    is_fresh = len(lines) <= 10 and any(
        marker in recent for marker in FRESH_SESSION_MARKERS
    )
    if is_fresh:
        return "fresh", FRESH_NUDGE, context

    # 2) 안전한 패턴 매칭 (y/n 등)
    for pattern, reply in SAFE_PATTERNS.items():
        if pattern.lower() in recent:
            return "safe", reply, context

    # 3) 판단 필요한 질문 패턴
    if any(p.lower() in recent for p in QUESTION_PATTERNS):
        return "nudge", NUDGE_MESSAGE, context

    return "none", "", ""


# ── Telegram 알림 ─────────────────────────────────────────────────────────────

def send_telegram(msg: str) -> None:
    token = os.environ.get("PM_BOT_TOKEN") or os.environ.get("WATCHDOG_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_GROUP_CHAT_ID") or os.environ.get("WATCHDOG_CHAT_ID", "")
    if not token or not chat_id:
        return
    try:
        subprocess.run(
            ["curl", "-s", "-X", "POST",
             f"https://api.telegram.org/bot{token}/sendMessage",
             "-d", f"chat_id={chat_id}",
             "-d", f"text=🤖 [agent-monitor] {msg}"],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


# ── 상태 관리 ─────────────────────────────────────────────────────────────────

def load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except Exception:
        pass
    return {}


def save_state(state: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except Exception:
        pass


def pane_hash(pane: str) -> str:
    return hashlib.md5(pane.encode()).hexdigest()


# ── 메인 루프 ─────────────────────────────────────────────────────────────────

def monitor_loop(poll_interval: int = POLL_INTERVAL, stuck_threshold: int = STUCK_THRESHOLD) -> None:
    log.info(f"agent_monitor 시작 — 주기: {poll_interval}s, stuck 임계값: {stuck_threshold}s")
    state = load_state()

    while True:
        sessions = get_aiorg_sessions()
        now = time.time()

        for (session, window) in sessions:
            key = f"{session}:{window}"
            pane = capture_pane(session, window)
            if not pane.strip():
                continue

            h = pane_hash(pane)
            sess = state.get(key, {})
            last_hash = sess.get("hash", "")
            last_changed = sess.get("last_changed", now)
            last_responded = sess.get("last_responded", 0)
            responded_hash = sess.get("responded_hash", "")

            if h != last_hash:
                # 내용 변경 → 상태 갱신
                state[key] = {
                    "hash": h,
                    "last_changed": now,
                    "last_responded": last_responded,
                    "responded_hash": responded_hash,
                }
                continue

            # 내용 고정 → stuck 시간 계산
            stuck_secs = now - last_changed
            if stuck_secs < stuck_threshold:
                continue

            # 이미 응답한 컨텍스트인지 확인 (중복 방지)
            context_h = pane_hash(pane[-3000:])
            if context_h == responded_hash:
                continue

            # 응답 쿨다운 확인
            if now - last_responded < RESPONSE_COOLDOWN:
                continue

            action, response, context = classify_stuck(pane)
            if action == "none":
                continue

            # ── 3단계 자동 처리 ──────────────────────────────────────
            stuck_min = int(stuck_secs / 60)
            bot_name = session.replace(SESSION_PREFIX, "")
            short_ctx = context[-150:].strip().replace("\n", "\n  ")

            log.info(f"[{key}] {stuck_min}분 입력 대기 → {action}: {response!r}")

            # send_keys로 응답 주입
            send_keys(session, window, response)

            # 텔레그램 알림
            action_label = {"safe": "자동 응답", "nudge": "자기 판단 유도", "fresh": "HEARTBEAT 확인"}
            send_telegram(
                f"🔒 {bot_name} — {stuck_min}분째 입력 대기\n\n"
                f"📋 컨텍스트:\n  ...{short_ctx}\n\n"
                f"🤖 조치: {action_label.get(action, action)}\n"
                f"💬 주입: {response}"
            )

            # 상태 업데이트
            state[key] = {
                "hash": h,
                "last_changed": now,
                "last_responded": now,
                "responded_hash": context_h,
            }

        save_state(state)
        time.sleep(poll_interval)


# ── 진입점 ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="aiorg agent tmux 세션 모니터")
    parser.add_argument("--daemon", action="store_true", help="백그라운드 데몬으로 실행")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL)
    parser.add_argument("--threshold", type=int, default=STUCK_THRESHOLD)
    args = parser.parse_args()

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    if args.daemon:
        import os as _os
        pid = _os.fork()
        if pid > 0:
            print(f"agent_monitor 데몬 시작 (PID: {pid})")
            PID_FILE.write_text(str(pid))
            sys.exit(0)
        _os.setsid()

    PID_FILE.write_text(str(os.getpid()))
    try:
        monitor_loop(poll_interval=args.interval, stuck_threshold=args.threshold)
    finally:
        PID_FILE.unlink(missing_ok=True)


if __name__ == "__main__":
    # .env 로드
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

    main()
