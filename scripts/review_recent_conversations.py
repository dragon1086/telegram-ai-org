#!/usr/bin/env python3
"""최근 대화/태스크 로그를 분석해 개선 리포트를 생성한다.

cron 예시:
  30 * * * * cd /Users/rocky/telegram-ai-org && ./.venv/bin/python scripts/review_recent_conversations.py --hours 6
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.telegram_delivery import resolve_delivery_target
from core.pm_decision import PMDecisionClient
from core.llm_provider import get_provider
from tools.telegram_uploader import upload_file


LOG_DIR = Path.home() / ".ai-org"
DEFAULT_OUTPUT_DIR = Path(".omx/reviews")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Review recent Telegram AI org conversations.")
    parser.add_argument("--hours", type=int, default=6, help="How many recent hours to inspect.")
    parser.add_argument("--org-id", default="global", help="PM org id for decision engine.")
    parser.add_argument("--engine", default="claude-code", choices=["claude-code", "codex"], help="Decision engine for review generation.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--limit-lines", type=int, default=400)
    parser.add_argument("--upload", action="store_true", help="Upload the generated report to the org's Telegram room.")
    return parser.parse_args()


def collect_recent_log_lines(hours: int, limit_lines: int) -> str:
    cutoff = datetime.now() - timedelta(hours=hours)
    interesting: list[str] = []
    files = sorted(LOG_DIR.glob("*.log"))
    for path in files:
        try:
            for raw in path.read_text(errors="replace").splitlines():
                ts = _extract_timestamp(raw)
                if ts is None or ts < cutoff:
                    continue
                if any(token in raw for token in (
                    "텔레그램 수신",
                    "PM_TASK 실행 시작",
                    "PM_TASK T-",
                    "결과 합성",
                    "태스크 감지",
                    "추가 작업 배분",
                    "auto_upload",
                )):
                    interesting.append(f"[{path.name}] {raw}")
        except Exception:
            continue
    if len(interesting) > limit_lines:
        interesting = interesting[-limit_lines:]
    return "\n".join(interesting)


def heuristic_review_markdown(transcript: str, hours: int) -> str:
    lines = [line for line in transcript.splitlines() if line.strip()]
    receipts = sum("텔레그램 수신" in line for line in lines)
    task_detects = sum("태스크 감지" in line for line in lines)
    task_starts = sum("PM_TASK 실행 시작" in line for line in lines)
    syntheses = sum("결과 합성" in line for line in lines)
    uploads = sum("auto_upload" in line for line in lines)
    return (
        f"# 최근 {hours}시간 대화/작업 리뷰\n\n"
        "## 주요 관찰\n"
        f"- 텔레그램 수신 로그: {receipts}건\n"
        f"- TaskPoller 태스크 감지: {task_detects}건\n"
        f"- PM_TASK 실행 시작: {task_starts}건\n"
        f"- 결과 합성: {syntheses}건\n"
        f"- 자동 업로드 관련 로그: {uploads}건\n\n"
        "## 잠재 이슈\n"
        "- 모델 기반 리뷰 생성이 실패했거나 불안정할 수 있음\n"
        "- 수신/감지/실행 시작 건수 차이를 보고 중복 감지 또는 미완료 체인을 점검할 필요가 있음\n"
        "- auto_upload 로그가 적으면 첨부 전달 체인 검증이 더 필요함\n\n"
        "## 권장 액션\n"
        "- 최신 review 리포트와 봇 로그를 같이 확인해 반복 패턴을 비교할 것\n"
        "- task_poller, synthesis, attachment 관련 로그를 우선 점검할 것\n"
        "- 필요 시 `scripts/review_recent_conversations.py --engine claude-code`를 재실행할 것\n"
    )


def _extract_timestamp(line: str) -> datetime | None:
    match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", line)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


async def build_report(org_id: str, transcript: str, hours: int, engine: str) -> str:
    client = PMDecisionClient(org_id=org_id, engine=engine)
    prompt = (
        f"최근 {hours}시간의 Telegram AI 조직 로그를 검토하라.\n"
        "다음을 한국어 Markdown으로 출력하라.\n"
        "1. 주요 실패/비효율 패턴 5개 이내\n"
        "2. 사용자 체감 품질 문제\n"
        "3. 중복 작업/느린 응답/맥락 손실/첨부 처리 이슈 여부\n"
        "4. 즉시 수정할 코드 액션 5개 이내 (파일 경로 포함)\n"
        "5. cron 또는 운영 자동화로 돌릴 점검 항목\n"
        "불필요한 서론 없이 바로 작성하라.\n\n"
        f"[최근 로그]\n{transcript or '(최근 로그 없음)'}"
    )
    try:
        report = await asyncio.wait_for(client.complete(prompt), timeout=120.0)
        if report.strip().startswith(("❌", "API Error")) or len(report.strip()) < 80:
            return heuristic_review_markdown(transcript, hours)
        return report
    except Exception:
        provider = get_provider()
        if provider is None:
            return heuristic_review_markdown(transcript, hours)
        try:
            report = await asyncio.wait_for(provider.complete(prompt, timeout=30.0), timeout=40.0)
            if report.strip().startswith(("❌", "API Error")) or len(report.strip()) < 80:
                return heuristic_review_markdown(transcript, hours)
            return report
        except Exception:
            return heuristic_review_markdown(transcript, hours)


def save_report(output_dir: Path, content: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = output_dir / f"recent-conversation-review-{stamp}.md"
    target.write_text(content.strip() + "\n", encoding="utf-8")
    return target


async def maybe_upload_report(org_id: str, report_path: Path) -> bool:
    target = resolve_delivery_target(org_id)
    if target is None:
        return False
    caption = f"🧾 {org_id} daily conversation review: {report_path.name}"
    return await upload_file(target.token, target.chat_id, str(report_path), caption)


def main() -> int:
    args = parse_args()
    transcript = collect_recent_log_lines(args.hours, args.limit_lines)
    report = asyncio.run(build_report(args.org_id, transcript, args.hours, args.engine))
    target = save_report(args.output_dir, report)
    if args.upload:
        uploaded = asyncio.run(maybe_upload_report(args.org_id, target))
        if not uploaded:
            print(f"UPLOAD_FAILED {target}")
            return 1
    print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
