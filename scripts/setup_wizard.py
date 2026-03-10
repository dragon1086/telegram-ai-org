#!/usr/bin/env python3
"""telegram-ai-org 설치 마법사.

표준 input()만 사용 — 외부 의존성 없음.
실행: python scripts/setup_wizard.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


CONFIG_DIR = Path.home() / ".ai-org"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
WORKERS_FILE = Path("workers.yaml")  # 프로젝트 루트


# ─── 유틸 ────────────────────────────────────────────────────────────────────

def banner(title: str) -> None:
    print(f"\n{'=' * 50}")
    print(f"  {title}")
    print(f"{'=' * 50}")


def step(n: int, total: int, label: str) -> None:
    print(f"\n[{n}/{total}] {label}")
    print("-" * 40)


def ok(msg: str) -> None:
    print(f"  ✅ {msg}")


def warn(msg: str) -> None:
    print(f"  ⚠️  {msg}")


def err(msg: str) -> None:
    print(f"  ❌ {msg}")


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"  {prompt}{suffix}: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n\n취소됨.")
        sys.exit(0)
    return val or default


def ask_yes(prompt: str, default: bool = True) -> bool:
    default_str = "Y/n" if default else "y/N"
    raw = ask(f"{prompt} ({default_str})")
    if not raw:
        return default
    return raw.lower() in ("y", "yes", "예", "ㅇ")


def mask_token(token: str) -> str:
    if len(token) < 8:
        return "****"
    return token[:4] + "****" + token[-4:]


# ─── Telegram API 검증 ────────────────────────────────────────────────────────

def validate_telegram_token(token: str) -> dict | None:
    """Telegram getMe API로 토큰 유효성 검증. 성공 시 bot 정보 반환."""
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read())
            if data.get("ok"):
                return data["result"]
    except Exception:
        pass
    return None


# ─── 바이너리 감지 ────────────────────────────────────────────────────────────

def detect_binaries() -> dict[str, str | None]:
    """claude / codex 바이너리 경로 자동 감지."""
    result: dict[str, str | None] = {}

    for name in ("claude", "codex"):
        env_var = f"{name.upper()}_CLI_PATH"
        path = os.environ.get(env_var) or shutil.which(name)
        result[name] = path

    return result


# ─── 설정 저장 ────────────────────────────────────────────────────────────────

def save_config(pm_token: str, group_chat_id: str, binaries: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    lines = [
        "# telegram-ai-org PM 설정 (setup_wizard.py 생성)\n",
        f"PM_BOT_TOKEN={pm_token}\n",
        f"TELEGRAM_GROUP_CHAT_ID={group_chat_id}\n",
    ]
    if binaries.get("claude"):
        lines.append(f"CLAUDE_CLI_PATH={binaries['claude']}\n")
    if binaries.get("codex"):
        lines.append(f"CODEX_CLI_PATH={binaries['codex']}\n")
    lines.append("CONTEXT_DB_PATH=~/.ai-org/context.db\n")

    CONFIG_FILE.write_text("".join(lines), encoding="utf-8")
    ok(f"설정 저장: {CONFIG_FILE}")


def save_workers(workers: list[dict]) -> None:
    """workers.yaml 생성/갱신."""
    lines = ["# 워커 봇 설정 (setup_wizard.py 생성)\n", "workers:\n"]
    for w in workers:
        lines += [
            f"  - name: {w['name']}\n",
            f"    token: \"{w['token']}\"\n",
            f"    engine: {w['engine']}\n",
            f"    description: \"{w['description']}\"\n",
        ]
    WORKERS_FILE.write_text("".join(lines), encoding="utf-8")
    ok(f"워커 설정 저장: {WORKERS_FILE}")


# ─── 메인 마법사 ──────────────────────────────────────────────────────────────

def wizard_pm() -> tuple[str, str]:
    """PM 봇 설정. (token, group_chat_id) 반환."""
    while True:
        token = ask("PM 봇 텔레그램 토큰을 입력하세요")
        if not token:
            warn("토큰을 입력해주세요.")
            continue

        print("  토큰 검증 중...", end="", flush=True)
        info = validate_telegram_token(token)
        if info:
            print()
            ok(f"PM 봇 연결 확인: @{info.get('username', '?')} ({info.get('first_name', '')})")
            break
        else:
            print()
            warn("토큰 유효성 검증 실패. 오프라인이거나 잘못된 토큰입니다.")
            if not ask_yes("그래도 계속하시겠어요?", default=False):
                continue
            break

    while True:
        chat_id = ask("텔레그램 그룹 채팅방 ID (예: -1001234567890)")
        if chat_id.lstrip("-").isdigit():
            break
        warn("숫자만 입력하세요 (음수 가능).")

    return token, chat_id


def wizard_binaries() -> dict[str, str | None]:
    """실행 엔진 감지 및 확인."""
    binaries = detect_binaries()

    claude_path = binaries.get("claude")
    codex_path = binaries.get("codex")

    if claude_path:
        ok(f"Claude Code 경로: {claude_path}")
    else:
        warn("Claude Code 미감지 (선택사항 — claude-code 엔진 워커에 필요)")

    if codex_path:
        ok(f"Codex 경로: {codex_path}")
    else:
        warn("Codex 미감지 (선택사항 — codex 엔진 워커에 필요)")

    return binaries


ENGINE_MAP = {"1": "claude-code", "2": "codex", "3": "both"}
ENGINE_LABEL = {"claude-code": "Claude Code", "codex": "Codex", "both": "둘 다"}


def wizard_worker() -> dict | None:
    """워커 1개 설정. dict 또는 None(취소) 반환."""
    name = ask("워커 이름 (예: cokac, researcher, writer)").strip()
    if not name:
        return None

    while True:
        token = ask(f"{name} 텔레그램 봇 토큰")
        if not token:
            warn("토큰을 입력해주세요.")
            continue

        print("  토큰 검증 중...", end="", flush=True)
        info = validate_telegram_token(token)
        if info:
            print()
            ok(f"@{info.get('username', '?')} 연결 확인")
            break
        else:
            print()
            warn("토큰 검증 실패.")
            if not ask_yes("그래도 계속하시겠어요?", default=False):
                continue
            break

    print("  실행 엔진:")
    print("    1. Claude Code")
    print("    2. Codex")
    print("    3. 둘 다 (태스크에 따라 PM이 선택)")
    engine_raw = ask("선택", default="1")
    engine = ENGINE_MAP.get(engine_raw, "claude-code")

    description = ask("역할 설명 (예: 코딩, 구현 전문)", default=f"{name} 전문")

    ok(f"{name} 워커 추가됨 (engine={engine})")
    return {"name": name, "token": token, "engine": engine, "description": description}


def wizard_workers() -> list[dict]:
    """워커 목록 수집."""
    workers: list[dict] = []

    while True:
        if not ask_yes("워커를 추가하시겠어요?"):
            break
        print()
        w = wizard_worker()
        if w:
            workers.append(w)
        print()
        if not ask_yes("워커를 더 추가하시겠어요?", default=False):
            break

    return workers


def print_summary(pm_token: str, group_chat_id: str, workers: list[dict], binaries: dict) -> None:
    banner("✅ 설정 완료!")
    print(f"\n저장된 파일:")
    print(f"  {CONFIG_FILE}  (PM 토큰, 그룹 ID)")
    print(f"  {WORKERS_FILE}  (워커 목록)")
    print(f"\n등록된 워커:")
    for w in workers:
        print(f"  • @{w['name']}_bot  ({ENGINE_LABEL[w['engine']]})  — {w['description']}")
    if not workers:
        print("  (없음 — 나중에 workers.yaml을 직접 편집하거나 마법사를 다시 실행하세요)")
    print(f"\n시작 방법:")
    print(f"  source {CONFIG_FILE.parent}/.env  # 또는 .env에 토큰 복사")
    print(f"  bash scripts/start_all.sh")
    print()


def main() -> None:
    banner("🤖 telegram-ai-org 설치 마법사")
    print("\n이 마법사가 PM 봇과 워커 봇을 설정합니다.")
    print("Ctrl+C로 언제든 취소할 수 있습니다.\n")

    total_steps = 3

    step(1, total_steps, "PM 봇 설정")
    pm_token, group_chat_id = wizard_pm()

    step(2, total_steps, "실행 엔진 확인")
    binaries = wizard_binaries()

    step(3, total_steps, "워커 봇 추가")
    workers = wizard_workers()

    # 저장
    save_config(pm_token, group_chat_id, binaries)
    if workers:
        # 토큰을 환경변수 참조 형식으로 변환해서 workers.yaml에 저장
        workers_for_yaml = []
        env_lines = []
        for w in workers:
            env_var = f"{w['name'].upper()}_BOT_TOKEN"
            env_lines.append(f"{env_var}={w['token']}\n")
            workers_for_yaml.append({
                "name": w["name"],
                "token": f"${{{env_var}}}",
                "engine": w["engine"],
                "description": w["description"],
            })
        save_workers(workers_for_yaml)

        # 토큰을 config.yaml에 추가
        with CONFIG_FILE.open("a", encoding="utf-8") as f:
            f.write("\n# 워커 봇 토큰\n")
            f.writelines(env_lines)
        ok(f"워커 토큰을 {CONFIG_FILE}에 저장")

    print_summary(pm_token, group_chat_id, workers, binaries)


if __name__ == "__main__":
    main()
