#!/usr/bin/env python3
"""아침 팀 목표 스크립트 — 매일 09:00 KST (UTC 00:00).

어제 회고 결과 로드 → Claude로 오늘 팀 목표 3가지 생성 → Telegram 전송.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── 환경 설정 ──────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
KST = timezone(timedelta(hours=9))


def _load_env() -> None:
    for env_path in (Path.home() / ".ai-org" / "config.yaml", PROJECT_ROOT / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

BOT_TOKEN = os.environ.get("PM_BOT_TOKEN", "")
GROUP_CHAT_ID = int(os.environ.get("TELEGRAM_GROUP_CHAT_ID", "-5203707291"))
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# ── 어제 회고 로드 ─────────────────────────────────────────────────────────

def _load_yesterday_retro() -> str:
    """어제 회고 MD 파일 또는 DB에서 인사이트 로드."""
    yesterday = (datetime.now(KST) - timedelta(days=1)).strftime("%Y-%m-%d")
    retro_dir = PROJECT_ROOT / "logs" / "retro"
    retro_file = retro_dir / f"{yesterday}.md"
    if retro_file.exists():
        content = retro_file.read_text()
        # 핵심 섹션만 추출 (너무 길면 잘라냄)
        return content[:2000]

    # DB에서 시도
    db_path = PROJECT_ROOT / ".ai-org" / "context.db"
    if db_path.exists():
        try:
            import sqlite3
            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    "SELECT content FROM retro_logs WHERE date=? LIMIT 1",
                    (yesterday,)
                ).fetchone()
                if row:
                    return row[0][:2000]
        except Exception:
            pass

    return "어제 회고 데이터 없음 (첫 번째 실행)"


# ── LLM 목표 생성 ──────────────────────────────────────────────────────────

def _generate_goals(yesterday_retro: str) -> str:
    """Claude로 오늘 팀 목표 3가지 생성."""
    if not ANTHROPIC_API_KEY:
        print("[morning_goals] ANTHROPIC_API_KEY 없음 — 기본 목표 사용")
        return _default_goals()

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        today = datetime.now(KST).strftime("%Y-%m-%d (%A)")

        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=600,
            timeout=30,
            messages=[{
                "role": "user",
                "content": f"""당신은 AI 개발팀의 PM입니다. 오늘({today}) 팀의 목표를 설정해주세요.

어제 회고 요약:
{yesterday_retro}

다음 형식으로 정확히 답변해주세요 (다른 설명 없이):
1. [목표1 — 구체적인 행동 중심]
2. [목표2 — 어제 개선점 반영]
3. [목표3 — 실험/도전 과제]

각 목표는 한 줄, 50자 이내."""
            }]
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"[morning_goals] LLM 호출 실패: {e}")
        return _default_goals()


def _default_goals() -> str:
    return (
        "1. 오늘 예정된 태스크 80% 이상 완료\n"
        "2. 에러 발생 시 원인 분석 후 lesson 기록\n"
        "3. 코드 품질 개선 1건 PR 시도"
    )


# ── Telegram 전송 ──────────────────────────────────────────────────────────

async def _send_telegram(text: str) -> None:
    if not BOT_TOKEN:
        print("[morning_goals] PM_BOT_TOKEN 없음 — Telegram 전송 건너뜀")
        print(text)
        return
    try:
        from telegram import Bot
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(
            chat_id=GROUP_CHAT_ID,
            text=text,
            parse_mode="Markdown",
        )
        print("[morning_goals] Telegram 전송 완료")
    except Exception as e:
        print(f"[morning_goals] Telegram 전송 실패: {e}")
        print(text)


# ── 메인 ───────────────────────────────────────────────────────────────────

async def main() -> None:
    today = datetime.now(KST).strftime("%Y년 %m월 %d일 (%A)")
    print(f"[morning_goals] 시작 — {today}")

    yesterday_retro = _load_yesterday_retro()
    goals = _generate_goals(yesterday_retro)

    message = (
        f"☀️ *오늘의 팀 목표* — {today}\n\n"
        f"{goals}\n\n"
        f"_화이팅! 오늘도 한 걸음씩 🚀_"
    )

    await _send_telegram(message)
    print("[morning_goals] 완료")


if __name__ == "__main__":
    asyncio.run(main())
