#!/usr/bin/env python3
"""agent_monitor.py — aiorg Claude agent tmux 세션 감시 + 자동 응답 데몬.

동작:
  1. 30초마다 aiorg_aiorg_* tmux 세션 모든 창 캡처
  2. 콘텐츠가 STUCK_THRESHOLD(180초)간 변화 없고 질문 패턴 감지 시
  3. claude -p (Haiku) 로 자연어 응답 생성 → tmux send-keys 주입
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

# 질문 패턴 (한/영 혼합)
QUESTION_PATTERNS = [
    "할까요", "하시겠습니까", "하겠습니까", "재시작", "종료", "확인",
    "선택", "입력하세요", "계속", "진행", "삭제", "실행",
    "y/n", "yes/no", "? (y", "[y/n]", "[yes/no]",
    "would you like", "do you want", "should i", "shall i",
    "confirm", "proceed",
]

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


def is_waiting_for_input(pane: str) -> tuple[bool, str]:
    """(대기 중 여부, 관련 컨텍스트 텍스트) 반환."""
    lines = extract_meaningful_lines(pane)
    if not lines:
        return False, ""

    last_line = lines[-1]
    # Claude Code 프롬프트(❯)에서 멈춘 상태인지 확인
    at_prompt = last_line in ("❯", "") or last_line.endswith("❯")

    # 최근 30줄에서 질문 패턴 탐색
    recent = "\n".join(lines[-30:]).lower()
    has_question = any(p.lower() in recent for p in QUESTION_PATTERNS)

    # 최근 콘텐츠를 LLM에 넘길 텍스트로
    context = "\n".join(lines[-40:])
    return at_prompt and has_question, context


# ── LLM 응답 생성 ─────────────────────────────────────────────────────────────

def generate_response(session: str, context: str) -> str:
    """claude -p Haiku 로 적절한 응답 생성."""
    bot_name = session.replace(SESSION_PREFIX, "").replace("_", " ")

    prompt = f"""당신은 AI 조직 자율 에이전트 모니터입니다.
아래 tmux 세션의 Claude 코딩 에이전트가 사용자 입력을 기다리고 있습니다.

세션: {session} (봇: {bot_name})
에이전트 최근 출력:
---
{context}
---

규칙:
- 봇 프로세스 재시작 확인 → 현재 상황 파악해 답변 (보통 봇이 이미 실행 중이면 "아니오")
- 위험 작업(데이터 삭제, 프로덕션 DB 수정 등) → 반드시 "아니오"
- 일반 작업 계속/진행 확인 → "네, 계속 진행해"
- 정보 입력 요구 → 상황에 맞는 합리적 기본값 제시
- 불분명한 경우 → "현재 상황 파악 후 안전한 기본값으로 진행해줘"

응답은 짧게 (1-2문장). 설명 없이 답변만 출력."""

    claude_bin = Path.home() / ".local" / "bin" / "claude"
    if not claude_bin.exists():
        claude_bin = Path("claude")

    try:
        result = subprocess.run(
            [str(claude_bin), "-p", "--model", "claude-haiku-4-5-20251001",
             "--dangerously-skip-permissions"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=30,
        )
        response = result.stdout.strip()
        if response:
            return response
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.warning(f"LLM 호출 실패: {e}")

    # 폴백: 안전한 기본값
    return "현재 상황 파악 후 안전한 기본값으로 진행해줘"


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

            waiting, context = is_waiting_for_input(pane)
            if not waiting:
                continue

            # ── 자동 응답 실행 ────────────────────────────────────────
            stuck_min = int(stuck_secs / 60)
            log.info(f"[{key}] {stuck_min}분 입력 대기 감지 → 자동 응답 생성 중...")

            response = generate_response(session, context)
            log.info(f"[{key}] 응답: {response!r}")

            send_keys(session, window, response)

            # 텔레그램 알림
            short_ctx = context[-150:].strip().replace("\n", "\n  ")
            bot_name = session.replace(SESSION_PREFIX, "")
            send_telegram(
                f"🔒 {bot_name} — {stuck_min}분째 블락 감지\n\n"
                f"📋 컨텍스트:\n  ...{short_ctx}\n\n"
                f"💬 자동 응답:\n  {response}"
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
