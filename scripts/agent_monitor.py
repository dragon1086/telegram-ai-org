#!/usr/bin/env python3
"""agent_monitor.py — aiorg Claude agent tmux 세션 감시 + 3단계 자동 처리 데몬.

동작:
  1. 30초마다 aiorg_aiorg_* tmux 세션 모든 창 캡처
  2. 콘텐츠가 STUCK_THRESHOLD(300초)간 변화 없고 입력 대기 감지 시
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
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

# ── 설정 ──────────────────────────────────────────────────────────────────────
POLL_INTERVAL = 30           # 세션 확인 주기 (초)
STUCK_THRESHOLD = 300        # 이 시간(초) 동안 변화 없으면 "stuck" 의심 (BOT_IDLE_TIMEOUT_SEC=300 기준 정렬)
RESPONSE_COOLDOWN = 300      # 같은 세션에 연속 응답 최소 간격 (초)
SESSION_PREFIX = "aiorg_aiorg_"
STATE_FILE = Path("/tmp/agent-monitor-state.json")
LOG_FILE = Path.home() / ".ai-org" / "agent-monitor.log"
PID_FILE = Path("/tmp/agent-monitor.pid")

# ── ContextDB 태스크 조회 (동기) ──────────────────────────────────────────────
CONTEXT_DB_PATH = Path(os.environ.get("CONTEXT_DB_PATH", "~/.ai-org/context.db")).expanduser()


def _session_to_dept_id(session_name: str) -> str:
    """tmux 세션 이름 → ContextDB assigned_dept 변환.

    예: 'aiorg_aiorg_engineering' → 'aiorg_engineering_bot'
    """
    bot_name = session_name.replace(SESSION_PREFIX, "")  # 'engineering'
    return f"aiorg_{bot_name}_bot"


def get_running_task_for_dept(dept_id: str) -> dict | None:
    """해당 부서의 running 태스크 + 부모 태스크 설명 조회 (동기 sqlite3)."""
    if not CONTEXT_DB_PATH.exists():
        return None
    try:
        db = sqlite3.connect(str(CONTEXT_DB_PATH), timeout=5)
        db.row_factory = sqlite3.Row
        # running 태스크 우선, 없으면 assigned
        cursor = db.execute(
            "SELECT id, description, parent_id, metadata "
            "FROM pm_tasks WHERE assigned_dept = ? AND status IN ('running', 'assigned') "
            "ORDER BY CASE status WHEN 'running' THEN 0 ELSE 1 END, updated_at DESC LIMIT 1",
            (dept_id,),
        )
        row = cursor.fetchone()
        if not row:
            db.close()
            return None
        task = dict(row)
        # 부모 태스크 설명 가져오기 (전체 맥락 파악)
        parent_desc = None
        if task.get("parent_id"):
            pcur = db.execute(
                "SELECT description FROM pm_tasks WHERE id = ?",
                (task["parent_id"],),
            )
            prow = pcur.fetchone()
            if prow:
                parent_desc = prow[0]
        task["parent_description"] = parent_desc
        db.close()
        return task
    except Exception as e:
        log.warning(f"ContextDB 조회 실패: {e}")
        return None


def build_context_nudge(session_name: str) -> str | None:
    """세션의 현재 태스크 맥락으로 구체적 넛지 메시지 생성.

    태스크 DB에서 설명을 가져와 봇에게 구체적 방향성을 제시한다.
    태스크가 없으면 None 반환 → 기존 NUDGE_MESSAGE 사용.
    """
    dept_id = _session_to_dept_id(session_name)
    task = get_running_task_for_dept(dept_id)
    if not task or not task.get("description"):
        return None

    desc = task["description"]
    parent_desc = task.get("parent_description")

    # 태스크 설명에서 핵심 지시 추출 (앞부분 500자)
    task_summary = desc[:500].strip()

    # tmux send_keys는 줄바꿈을 Enter로 해석 → 단일 라인으로 구성
    task_oneline = task_summary.replace("\n", " ").replace("  ", " ")
    parts = [f"현재 배정된 태스크가 있어. 이 내용을 바탕으로 진행해: [태스크] {task_oneline}"]
    if parent_desc:
        parent_oneline = parent_desc[:300].strip().replace("\n", " ").replace("  ", " ")
        parts.append(f" [상위 맥락] {parent_oneline}")
    parts.append(" 위 태스크를 기반으로 스스로 판단해서 진행해. 위험한 작업(삭제, 프로덕션 변경)은 하지 마.")

    return "".join(parts)


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
    "계속할까요": "네",
    "진행할까요": "네",
    "확인해주세요": "네",
    "실행할까요": "네",
    "커밋할까요": "네",
    "삭제할까요": "아니오",
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
            text=True, stderr=subprocess.DEVNULL, timeout=10,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
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
            text=True, stderr=subprocess.DEVNULL, timeout=10,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
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

    # 0) idle/대기 상태 감지 — 봇이 할 일 없이 대기 중이면 건드리지 않음
    #    프롬프트 직전 3줄만 검사하여 오탐 최소화
    idle_area = "\n".join(lines[-4:]).lower()
    idle_markers = (
        "대기합니다", "대기 중", "대기하겠", "기다리겠",
        "추가 지시", "waiting for instruction", "standing by",
    )
    if any(m in idle_area for m in idle_markers):
        return "none", "", ""

    # 1) fresh 세션 감지
    is_fresh = len(lines) <= 10 and any(
        marker in recent for marker in FRESH_SESSION_MARKERS
    )
    if is_fresh:
        # fresh 세션에도 태스크 맥락이 있으면 구체적 지시 제공
        return "fresh", FRESH_NUDGE, context

    # 2) 안전한 패턴 매칭 (y/n 등) — 프롬프트 직전 5줄에서만 매칭
    safe_area = "\n".join(lines[-5:]).lower()
    for pattern, reply in SAFE_PATTERNS.items():
        if pattern.lower() in safe_area:
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
        try:
            sessions = get_aiorg_sessions()
        except Exception as _e:
            log.warning(f"세션 목록 조회 실패: {_e}")
            time.sleep(poll_interval)
            continue
        now = time.time()

        for (session, window) in sessions:
            try:
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

                # ── nudge/fresh: 태스크 맥락 기반 응답 생성 ─────────────
                if action in ("nudge", "fresh"):
                    ctx_response = build_context_nudge(session)
                    if ctx_response:
                        response = ctx_response
                        log.info(f"[{key}] 태스크 맥락 기반 {action} 응답 생성 완료")

                # ── 3단계 자동 처리 ──────────────────────────────────────
                stuck_min = int(stuck_secs / 60)
                bot_name = session.replace(SESSION_PREFIX, "")
                short_ctx = context[-150:].strip().replace("\n", "\n  ")

                log.info(f"[{key}] {stuck_min}분 입력 대기 → {action}: {response!r}")

                # send_keys로 응답 주입
                send_keys(session, window, response)

                # 텔레그램 알림 — fresh(세션 재시작)만 알림, safe/nudge는 로그만
                if action == "fresh":
                    send_telegram(
                        f"🔒 {bot_name} — {stuck_min}분째 입력 대기\n\n"
                        f"📋 컨텍스트:\n  ...{short_ctx}\n\n"
                        f"🤖 조치: HEARTBEAT 확인 (세션 재시작)\n"
                        f"💬 주입: {response}"
                    )

                # 상태 업데이트
                state[key] = {
                    "hash": h,
                    "last_changed": now,
                    "last_responded": now,
                    "responded_hash": context_h,
                }
            except Exception as _e:
                log.warning(f"[{session}:{window}] 처리 실패: {_e}")

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
