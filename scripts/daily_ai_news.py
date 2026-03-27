#!/usr/bin/env python3
"""
daily_ai_news.py — 일일 AI 뉴스 리서치 스크립트
=================================================
Usage:
    # 프로젝트 venv 사용 (권장)
    .venv/bin/python3 scripts/daily_ai_news.py

    # 또는 시스템 python3
    python3 scripts/daily_ai_news.py

의존 환경변수 (우선순위 순):
    GEMINI_API_KEY      — Google AI Studio API 키 (REST API 방식)
    GEMINI_CLI_PATH     — gemini CLI 바이너리 경로 (기본: gemini, OAuth 방식 폴백)

출력 경로:
    reports/daily_ai_news/YYYY-MM-DD_daily_ai_news.md

기능:
    - 당일 날짜 기준 AI/오픈소스/에이전트 하네스/스킬시스템/CLI 관련 최신 뉴스 조사
    - telegram-ai-org 프로젝트 적용 가능성 high/medium/low 평가
    - Google Search Grounding 활성화 (API 방식일 때)
    - 인증 방식 자동 선택: GEMINI_API_KEY → gemini-cli OAuth 폴백
"""

from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# ── 환경변수 로드 ──────────────────────────────────────────────────────────────
# 스크립트 위치 기준으로 프로젝트 루트 .env 자동 로드
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
load_dotenv(_PROJECT_ROOT / ".env", override=False)

# ── 설정 ───────────────────────────────────────────────────────────────────────
MODEL_NAME = "gemini-3-flash-preview"
MODEL_FALLBACK = "gemini-2.5-flash"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_CLI_PATH = os.environ.get("GEMINI_CLI_PATH", "gemini")
OUTPUT_DIR = _PROJECT_ROOT / "reports" / "daily_ai_news"
LOG_PATH = _PROJECT_ROOT / "logs" / "daily_ai_news.log"
LOOKBACK_DAYS = 7  # 중복 빈도 집계 기간

RESEARCH_PROMPT_TEMPLATE = """\
오늘 날짜: {date}

당신은 telegram-ai-org 프로젝트 전담 AI 기술 리서처입니다.
telegram-ai-org는 멀티엔진 AI 봇 오케스트레이션 프레임워크로,
claude-code / codex / gemini-cli 3개 엔진을 지원하며
스킬 시스템, 에이전트 하네스, CLI 오케스트레이션이 핵심 기술입니다.

## 태스크
오늘({date}) 기준 최신 기술 뉴스 5~10건을 아래 카테고리에서 조사하세요:
- AI 에이전트 / 멀티에이전트 오케스트레이션
- 오픈소스 LLM / AI 모델 (새 릴리즈, 벤치마크)
- 에이전트 하네스 / 스킬 시스템 / 툴 프레임워크
- CLI 기반 AI 도구 (gemini-cli, claude-code, codex 등)
- AI 봇 / 텔레그램 봇 / 챗봇 인프라
- DevOps / 자동화 관련 AI 적용 사례

## 출력 형식 (반드시 아래 마크다운 구조 준수)
각 항목을 다음 구조로 작성하세요:

### [번호]. [뉴스 제목]
- **출처/링크**: [URL 또는 출처명]
- **요약**: [2~3문장 핵심 요약]
- **적용 가능성**: [high/medium/low] — [telegram-ai-org에 적용 가능한 이유 1~2문장]

## 마지막에 추가
### PM 필터링 요약
- high 항목 [N]건: [제목 나열]
- 즉시 검토 권장 항목: [가장 중요한 1~2건 이유 포함]
"""


def _build_prompt(date_str: str) -> str:
    return RESEARCH_PROMPT_TEMPLATE.format(date=date_str)


# ── 실행 로그 ─────────────────────────────────────────────────────────────────

def _append_log(date_str: str, status: str, duration_sec: float, out_path: str = "", error: str = "") -> None:
    """logs/daily_ai_news.log 에 실행 결과를 JSONL 형태로 기록한다."""
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "date": date_str,
        "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "status": status,          # "success" | "failure"
        "duration_sec": round(duration_sec, 1),
        "out_path": out_path,
        "error": error,
    }
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── 중복 빈도 가중치 ──────────────────────────────────────────────────────────

def _extract_h3_titles(md_text: str) -> list[str]:
    """리포트 마크다운에서 ### N. 제목 패턴의 뉴스 제목을 추출한다."""
    return re.findall(r"^###\s+\d+\.\s+(.+)$", md_text, re.MULTILINE)


def _build_frequency_section(today: str) -> str:
    """최근 LOOKBACK_DAYS일치 리포트를 스캔해 반복 등장 키워드를 집계한다."""
    today_dt = datetime.date.fromisoformat(today)
    keyword_counts: dict[str, int] = {}

    for delta in range(1, LOOKBACK_DAYS + 1):
        past_date = (today_dt - datetime.timedelta(days=delta)).isoformat()
        past_file = OUTPUT_DIR / f"{past_date}_daily_ai_news.md"
        if not past_file.exists():
            continue
        try:
            md = past_file.read_text(encoding="utf-8")
            titles = _extract_h3_titles(md)
            for title in titles:
                # 핵심 키워드만 추출 (30자 이상은 앞 30자 사용)
                kw = title[:40].strip()
                keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
        except Exception:
            continue

    if not keyword_counts:
        return ""

    # 2회 이상 등장한 토픽만 보고
    repeated = sorted(
        [(kw, cnt) for kw, cnt in keyword_counts.items() if cnt >= 2],
        key=lambda x: -x[1],
    )
    if not repeated:
        return ""

    lines = ["### 🔁 반복 등장 토픽 (중요도 가중치)", ""]
    lines.append("| 토픽 | 최근 등장 횟수 | 중요도 신호 |")
    lines.append("|------|--------------|------------|")
    for kw, cnt in repeated[:8]:
        signal = "🔴 높음" if cnt >= 3 else "🟡 중간"
        lines.append(f"| {kw} | {cnt}일 연속 | {signal} |")
    lines.append("")
    lines.append("> 💡 반복 등장 = 업계 주목도 높음. 중복 제거 대상이 아니라 우선 검토 대상입니다.")
    return "\n".join(lines) + "\n\n"


def _call_api(prompt: str, date_str: str) -> str:
    """GEMINI_API_KEY를 사용한 REST API 호출 (Google Search Grounding 포함)."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{MODEL_NAME}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],  # Search Grounding 활성화
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 8192,
        },
    }

    resp = requests.post(url, json=payload, timeout=120)

    # gemini-3-flash-preview가 v1beta에서 지원 안 될 경우 fallback
    if resp.status_code in (400, 404):
        print(f"[WARN] {MODEL_NAME} 모델 접근 실패 (HTTP {resp.status_code}), {MODEL_FALLBACK}로 재시도...", file=sys.stderr)
        fallback_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{MODEL_FALLBACK}:generateContent?key={GEMINI_API_KEY}"
        )
        resp = requests.post(fallback_url, json=payload, timeout=120)

    resp.raise_for_status()
    data = resp.json()

    candidates = data.get("candidates", [])
    if not candidates:
        raise ValueError(f"API 응답에 candidates 없음: {data}")

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts)
    return text.strip()


def _call_cli(prompt: str) -> str:
    """gemini-cli OAuth 방식 폴백 호출."""
    cmd = [
        GEMINI_CLI_PATH,
        "-m", MODEL_NAME,
        "-p", prompt,
        "--output-format", "text",
    ]
    print(f"[INFO] gemini-cli 실행: {' '.join(cmd[:3])} ...", file=sys.stderr)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(_PROJECT_ROOT),
    )
    if result.returncode != 0:
        # CLI도 모델 실패 시 fallback
        if "model" in result.stderr.lower() or "not found" in result.stderr.lower():
            print(f"[WARN] CLI {MODEL_NAME} 실패, {MODEL_FALLBACK} 재시도...", file=sys.stderr)
            cmd[2] = MODEL_FALLBACK
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=180, cwd=str(_PROJECT_ROOT)
            )
        if result.returncode != 0:
            raise RuntimeError(f"gemini-cli 오류:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")

    # 노이즈 라인 제거
    lines = [
        l for l in result.stdout.splitlines()
        if not any(l.lower().strip().startswith(p) for p in (
            "loaded cached credentials", "loaded credentials", "warning:"
        ))
    ]
    return "\n".join(lines).strip()


def generate_report(date_str: str) -> str:
    """AI 뉴스 리포트를 생성하고 마크다운 문자열을 반환한다."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    prompt = _build_prompt(date_str)
    used_model = MODEL_NAME
    method = "unknown"

    # 인증 방식 자동 선택
    if GEMINI_API_KEY:
        print(f"[INFO] GEMINI_API_KEY 방식으로 {MODEL_NAME} 호출...", file=sys.stderr)
        try:
            content = _call_api(prompt, date_str)
            method = "REST API"
        except Exception as e:
            print(f"[WARN] API 호출 실패: {e}\n→ gemini-cli OAuth 폴백 시도...", file=sys.stderr)
            content = _call_cli(prompt)
            method = "gemini-cli (OAuth 폴백)"
    else:
        print(f"[INFO] GEMINI_API_KEY 없음, gemini-cli OAuth 방식 사용...", file=sys.stderr)
        content = _call_cli(prompt)
        method = "gemini-cli (OAuth)"

    # 중복 빈도 가중치 섹션 (이전 리포트 스캔)
    freq_section = _build_frequency_section(date_str)

    # 헤더 조립
    header = textwrap.dedent(f"""\
        # 일일 AI 뉴스 리포트

        | 항목 | 값 |
        |------|-----|
        | 날짜 | {date_str} |
        | 모델 | {MODEL_NAME} |
        | 인증 방식 | {method} |
        | 생성 시각 | {now} |
        | 프로젝트 | telegram-ai-org (멀티엔진 AI 봇 오케스트레이션) |

        ---

    """)

    footer = textwrap.dedent(f"""

        ---
        *자동 생성 — `scripts/daily_ai_news.py` | {now}*
    """)

    return header + (freq_section if freq_section else "") + content + footer


def save_report(date_str: str, content: str) -> Path:
    """리포트를 날짜별 파일로 저장하고 경로를 반환한다."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{date_str}_daily_ai_news.md"
    out_path.write_text(content, encoding="utf-8")
    return out_path


def main() -> None:
    today = datetime.date.today().isoformat()  # YYYY-MM-DD
    print(f"[START] {today} 일일 AI 뉴스 리서치 시작", file=sys.stderr)
    t0 = time.time()

    try:
        report_md = generate_report(today)
        out_path = save_report(today, report_md)
        duration = time.time() - t0
        _append_log(today, "success", duration, str(out_path))
        print(f"[DONE] 리포트 저장 완료: {out_path} ({duration:.1f}s)", file=sys.stderr)
        print(str(out_path))  # stdout: 경로 출력 (크론/파이프라인 연동용)
    except Exception as exc:
        duration = time.time() - t0
        _append_log(today, "failure", duration, error=str(exc))
        print(f"[ERROR] 실행 실패 ({duration:.1f}s): {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
