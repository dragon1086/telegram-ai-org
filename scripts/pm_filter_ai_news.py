#!/usr/bin/env python3
"""
pm_filter_ai_news.py — PM 필터링 + 텔레그램 보고 스크립트
===========================================================
Usage:
    .venv/bin/python3 scripts/pm_filter_ai_news.py <report_path>

기능:
    1. 리서치 결과(마크다운)를 읽어 high 우선순위 항목 추출
    2. PM 관점 필터링: telegram-ai-org 적용 가능성 high 항목 선별
    3. 텔레그램 봇 API로 Rocky에게 요약 보고 전송

환경변수:
    PM_BOT_TOKEN or TELEGRAM_BOT_TOKEN — 텔레그램 봇 토큰
    ADMIN_CHAT_ID                      — Rocky 채팅 ID
"""

from __future__ import annotations

import datetime
import json
import os
import re
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

# ── 환경변수 로드 ──────────────────────────────────────────────────────────────
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)

# ── 설정 ───────────────────────────────────────────────────────────────────────
BOT_TOKEN = os.environ.get("PM_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")
LOG_PATH = _PROJECT_ROOT / "logs" / "daily_ai_news_cron.log"

# 관련성 키워드 (이 프로젝트 기준)
RELEVANCE_KEYWORDS = [
    "agent", "에이전트", "orchestrat", "오케스트레이션",
    "harness", "하네스", "skill", "스킬",
    "cli", "claude", "gemini", "codex", "openai",
    "llm", "multiagent", "멀티에이전트",
    "telegram", "텔레그램", "bot", "봇",
    "devops", "automation", "자동화",
    "open.source", "오픈소스", "framework", "프레임워크",
]


def _append_log(stage: str, status: str, message: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "date": datetime.date.today().isoformat(),
        "stage": stage,
        "status": status,
        "message": message,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _parse_news_items(md_text: str) -> list[dict]:
    """
    마크다운에서 뉴스 항목 파싱.
    패턴: ### N. 제목 블록을 읽어 적용 가능성 추출.
    """
    items = []
    # 각 ### N. 제목으로 시작하는 블록 분리
    blocks = re.split(r"(?=^###\s+\d+\.)", md_text, flags=re.MULTILINE)

    for block in blocks:
        if not re.match(r"^###\s+\d+\.", block.strip()):
            continue

        # 제목 추출
        title_match = re.match(r"^###\s+\d+\.\s+(.+)$", block.strip(), re.MULTILINE)
        title = title_match.group(1).strip() if title_match else "제목 없음"

        # 요약 추출
        summary_match = re.search(r"\*\*요약\*\*[：:]\s*(.+?)(?=\n-|\n###|\Z)", block, re.DOTALL)
        summary = summary_match.group(1).strip()[:200] if summary_match else ""

        # 적용 가능성 추출
        applicability_match = re.search(
            r"\*\*적용\s*가능성\*\*[：:]\s*\[?(high|medium|low)\]?",
            block, re.IGNORECASE
        )
        applicability = applicability_match.group(1).lower() if applicability_match else "unknown"

        # 적용 이유 추출
        reason_match = re.search(
            r"\*\*적용\s*가능성\*\*[：:]\s*\[?(?:high|medium|low)\]?\s*[—\-–]\s*(.+?)(?=\n|\Z)",
            block, re.IGNORECASE | re.DOTALL
        )
        reason = reason_match.group(1).strip()[:150] if reason_match else ""

        # 관련성 키워드 보정 (파싱 실패 시 키워드로 보조 분류)
        if applicability == "unknown":
            text_lower = (title + summary).lower()
            if any(kw.lower() in text_lower for kw in RELEVANCE_KEYWORDS):
                applicability = "medium"
            else:
                applicability = "low"

        items.append({
            "title": title,
            "summary": summary,
            "applicability": applicability,
            "reason": reason,
        })

    return items


def _build_telegram_message(items: list[dict], report_path: str, date_str: str) -> str:
    """텔레그램 전송용 요약 메시지 생성."""
    high_items = [i for i in items if i["applicability"] == "high"]
    medium_items = [i for i in items if i["applicability"] == "medium"]
    total = len(items)

    lines = [
        f"📡 *일일 AI 뉴스 PM 보고* — {date_str}",
        "",
        f"총 {total}건 수집 | 🔴 HIGH {len(high_items)}건 | 🟡 MEDIUM {len(medium_items)}건",
        "",
    ]

    if high_items:
        lines.append("*🔴 즉시 검토 권장 (HIGH)*")
        for i, item in enumerate(high_items[:5], 1):
            reason_text = f"\n   └ {item['reason']}" if item["reason"] else ""
            lines.append(f"{i}\\. {item['title']}{reason_text}")
        lines.append("")

    if medium_items:
        lines.append("*🟡 관심 항목 (MEDIUM)*")
        for i, item in enumerate(medium_items[:3], 1):
            lines.append(f"{i}\\. {item['title']}")
        lines.append("")

    if not high_items and not medium_items:
        lines.append("_오늘은 telegram\\-ai\\-org 직접 적용 대상 없음_")
        lines.append("")

    lines.append(f"📄 전체 리포트: `{Path(report_path).name}`")
    lines.append("_지시 또는 스킵 여부를 알려주세요_")

    return "\n".join(lines)


def send_telegram(message: str) -> bool:
    """텔레그램 메시지 전송. 성공 시 True 반환."""
    if not BOT_TOKEN:
        print("[WARN] PM_BOT_TOKEN / TELEGRAM_BOT_TOKEN 미설정 — 텔레그램 전송 스킵", file=sys.stderr)
        return False
    if not ADMIN_CHAT_ID:
        print("[WARN] ADMIN_CHAT_ID 미설정 — 텔레그램 전송 스킵", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": ADMIN_CHAT_ID,
        "text": message,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"[ERROR] 텔레그램 전송 실패: {e}", file=sys.stderr)
        return False


def main() -> None:
    if len(sys.argv) < 2:
        print("[ERROR] 사용법: pm_filter_ai_news.py <report_path>", file=sys.stderr)
        sys.exit(1)

    report_path = sys.argv[1].strip()
    if not report_path or not Path(report_path).exists():
        print(f"[ERROR] 리포트 파일 없음: {report_path}", file=sys.stderr)
        _append_log("pm_filter", "failure", f"리포트 파일 없음: {report_path}")
        sys.exit(1)

    date_str = datetime.date.today().isoformat()
    print(f"[PM] {date_str} 리포트 필터링 시작: {report_path}", file=sys.stderr)

    # ── 리포트 파싱 ────────────────────────────────────────────────────────────
    try:
        md_text = Path(report_path).read_text(encoding="utf-8")
        items = _parse_news_items(md_text)
        high_count = sum(1 for i in items if i["applicability"] == "high")
        _append_log("pm_filter", "info", f"파싱 완료: {len(items)}건 (high={high_count})")
        print(f"[PM] 파싱 완료: 총 {len(items)}건 (high={high_count})", file=sys.stderr)
    except Exception as e:
        _append_log("pm_filter", "failure", f"리포트 파싱 실패: {e}")
        print(f"[ERROR] 파싱 실패: {e}", file=sys.stderr)
        sys.exit(1)

    # ── 텔레그램 메시지 생성 및 전송 ──────────────────────────────────────────
    message = _build_telegram_message(items, report_path, date_str)

    if send_telegram(message):
        _append_log("telegram", "success", f"Rocky 보고 전송 완료 (high={high_count})")
        print("[PM] 텔레그램 보고 전송 완료", file=sys.stderr)
    else:
        # 전송 실패는 비치명적 — 리포트는 이미 저장됨
        _append_log("telegram", "skipped", "전송 스킵 (토큰/채팅ID 미설정 또는 API 오류)")
        print("[PM] 텔레그램 전송 스킵 (로그 기록됨)", file=sys.stderr)

    # stdout: 필터링 결과 요약 (크론 로그 캡처용)
    print(f"PM_FILTER_DONE date={date_str} total={len(items)} high={high_count} report={report_path}")


if __name__ == "__main__":
    main()
