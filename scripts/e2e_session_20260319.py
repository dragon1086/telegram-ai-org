"""
2026-03-19 세션 변경사항 E2E 테스트
- S-D1: Discussion 멀티라운드 핑퐁 (B2B vs B2C 토론)
- S-D2: Discussion 에러 없는 응답 (클라우드 서비스 토론)
- S-P1: 봇 역할 인식 (성과 데이터 주입 간접 확인)

평가 방식:
- 키워드 카운팅이 아닌 전체 대화 로그 수집
- 에러 패턴 감지 (Traceback, Exception, Error: 등)
- 대화 흐름 평가 (PM 사회, 봇 응답, 라운드 전환, 최종 요약)
- 원본 로그를 보고서에 전부 기록
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, events

# ── 환경 변수 ─────────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).parent.parent / ".env")

API_ID   = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
PHONE    = os.environ["TELEGRAM_PHONE"]
CHAT_ID  = int(os.environ["TELEGRAM_GROUP_CHAT_ID"])

SESSION_FILE = Path(__file__).parent.parent / ".e2e_session_20260319"

_TS = datetime.now().strftime("%H%M%S")


# ── 데이터 모델 ───────────────────────────────────────────────────────────────
@dataclass
class BotMessage:
    bot: str
    text: str
    ts: float


@dataclass
class ScenarioResult:
    scenario_id: str
    priority: str
    description: str
    message_sent: str
    responses: list[BotMessage] = field(default_factory=list)
    elapsed_sec: float = 0.0
    passed: bool = False
    eval_note: str = ""


# ── 에러 패턴 ─────────────────────────────────────────────────────────────────
ERROR_PATTERNS = [
    "traceback",
    "exception",
    "error:",
    "오류가 발생",
    "실패했습니다",
    "cannot",
    "unable to",
    "failed to",
    "undefined",
    "nonetype",
    "attributeerror",
    "keyerror",
    "valueerror",
    "typeerror",
    "syntaxerror",
    "importerror",
]


def _detect_errors(responses: list[BotMessage]) -> list[str]:
    """에러 패턴 감지. 발견된 에러 설명 목록 반환."""
    found = []
    for m in responses:
        text_lower = m.text.lower()
        for pat in ERROR_PATTERNS:
            if pat in text_lower:
                snippet = m.text[:200].replace("\n", " ")
                found.append(f"[{m.bot}] 패턴='{pat}' | {snippet}")
                break
    return found


# ── 평가 함수 ─────────────────────────────────────────────────────────────────
def eval_discussion_multiround(responses: list[BotMessage]) -> tuple[bool, str]:
    """S-D1: Discussion 멀티라운드 핑퐁 질적 평가.

    기준:
    1. 에러 패턴 없음 (필수)
    2. 2개 이상 봇 응답
    3. 각 봇 20자 이상 실질적 의견
    4. PM 요약/정리 메시지 존재
    5. 멀티라운드 신호 감지 (보너스, 필수 아님)
    """
    if not responses:
        return False, "응답 없음"

    # 1. 에러 패턴 감지 (FAIL 조건)
    errors = _detect_errors(responses)
    if errors:
        return False, f"에러 패턴 감지 ({len(errors)}건): {errors[0][:100]}"

    bots = list({m.bot for m in responses})
    all_text = " ".join(m.text for m in responses)
    all_text_lower = all_text.lower()

    issues = []

    # 2. 2개 이상 봇 응답
    if len(bots) < 2:
        issues.append(f"봇 {len(bots)}개만 응답 (2개+ 필요)")

    # 3. 실질적 의견 (20자+ 메시지)
    substantial = [m for m in responses if len(m.text.strip()) >= 20]
    if len(substantial) < 2:
        issues.append(f"실질적 의견 {len(substantial)}개 (2개+ 필요)")

    # 4. PM 요약 키워드
    summary_kw = ["요약", "종합", "결론", "정리", "합의", "summary", "최종"]
    has_summary = any(k in all_text_lower for k in summary_kw)
    if not has_summary:
        issues.append("PM 요약 미감지")

    if issues:
        return False, " | ".join(issues)

    # 보너스: 멀티라운드 신호
    multiround_kw = ["2라운드", "round 2", "추가 의견", "반박", "재논의", "다음 라운드", "라운드 2"]
    has_multiround = any(k in all_text_lower for k in multiround_kw)
    multiround_note = " + 멀티라운드 감지" if has_multiround else ""

    total_len = sum(len(m.text) for m in responses)
    return True, (
        f"PASS — {len(bots)}개 봇 응답 + {len(substantial)}개 실질 의견 "
        f"+ PM 요약 감지 + {total_len}자{multiround_note}"
    )


def eval_discussion_no_error(responses: list[BotMessage]) -> tuple[bool, str]:
    """S-D2: Discussion 에러 없는 응답 확인."""
    if not responses:
        return False, "응답 없음"

    errors = _detect_errors(responses)
    if errors:
        return False, f"에러 패턴 감지 ({len(errors)}건): {errors[0][:100]}"

    bots = list({m.bot for m in responses})
    total_len = sum(len(m.text) for m in responses)

    if total_len < 30:
        return False, f"응답 너무 짧음 ({total_len}자)"

    return True, f"PASS — 에러 없음 + {len(bots)}개 봇 + {total_len}자"


def eval_role_awareness(responses: list[BotMessage]) -> tuple[bool, str]:
    """S-P1: 봇 역할 인식 — PM이 팀 소개/역할 설명을 했는가.

    성과 데이터 주입 간접 확인:
    봇들이 자신의 전문분야를 언급하면 프롬프트 주입이 작동 중.
    """
    if not responses:
        return False, "응답 없음"

    errors = _detect_errors(responses)
    if errors:
        return False, f"에러 패턴 감지: {errors[0][:100]}"

    all_text_lower = " ".join(m.text for m in responses).lower()

    # 역할/전문분야 언급 키워드
    role_kw = [
        "전문", "담당", "역할", "engineering", "엔지니어링", "growth",
        "design", "디자인", "마케팅", "코딩", "개발", "팀",
        "pm", "project", "manager",
    ]
    role_hits = [k for k in role_kw if k in all_text_lower]

    if len(role_hits) < 2:
        return False, f"역할/전문분야 키워드 부족 ({len(role_hits)}/2): {role_hits}"

    total_len = sum(len(m.text) for m in responses)
    return True, f"PASS — 역할 키워드 {len(role_hits)}개: {role_hits[:5]} ({total_len}자)"


# ── 시나리오 정의 ──────────────────────────────────────────────────────────────
SCENARIOS = [
    {
        "id": "S-D1",
        "priority": "P0",
        "message": (
            f"AI 스타트업이 B2B vs B2C 중 어디를 먼저 공략해야 할지 "
            f"봇들끼리 얘기해봐 토론해줘 [STEST-{_TS}]"
        ),
        "description": "Discussion 멀티라운드 핑퐁 (B2B vs B2C 토론)",
        "timeout": 600,
        "eval_fn": eval_discussion_multiround,
    },
    {
        "id": "S-D2",
        "priority": "P1",
        "message": (
            f"클라우드 서비스 선택에 대해 봇들끼리 토론해줘 [STEST-{_TS}]"
        ),
        "description": "Discussion 에러 없는 응답 (클라우드 토론)",
        "timeout": 360,
        "eval_fn": eval_discussion_no_error,
    },
    {
        "id": "S-P1",
        "priority": "P1",
        "message": f"너네 팀은 어떤 전문 분야를 잘 해? [STEST-{_TS}]",
        "description": "봇 역할 인식 (성과 데이터 주입 간접 확인)",
        "timeout": 60,
        "eval_fn": eval_role_awareness,
    },
]


# ── 수집 + 실행 ───────────────────────────────────────────────────────────────
async def run_scenario(
    client: TelegramClient,
    chat_entity,
    scenario: dict,
) -> ScenarioResult:
    sid     = scenario["id"]
    msg     = scenario["message"]
    timeout = scenario["timeout"]
    eval_fn = scenario["eval_fn"]

    print(f"\n[{sid}/{scenario['priority']}] {scenario['description']}")
    print(f"  메시지: {msg[:120]}")
    print(f"  최대 {timeout}초 대기...")

    collected: list[BotMessage] = []
    stop = [False]

    async def handler(event, _c=collected, _s=stop):
        if _s[0]:
            return
        sender = await event.get_sender()
        if sender and getattr(sender, "bot", False):
            text = getattr(event.message, "text", None) or ""
            if not text:
                return
            entry = BotMessage(
                bot=getattr(sender, "username", "unknown"),
                text=text,
                ts=time.time(),
            )
            _c.append(entry)
            elapsed = entry.ts - _start_time[0] if _start_time[0] else 0
            print(f"  +{elapsed:.1f}s [{entry.bot}] {text[:200]}")

    _start_time = [0.0]
    client.add_event_handler(handler, events.NewMessage(chats=chat_entity))
    client.add_event_handler(handler, events.MessageEdited(chats=chat_entity))

    t0 = time.time()
    _start_time[0] = t0
    await client.send_message(CHAT_ID, msg)
    await asyncio.sleep(timeout)
    stop[0] = True
    elapsed = time.time() - t0

    client.remove_event_handler(handler, events.NewMessage(chats=chat_entity))
    client.remove_event_handler(handler, events.MessageEdited(chats=chat_entity))

    passed, eval_note = eval_fn(list(collected))

    result = ScenarioResult(
        scenario_id=sid,
        priority=scenario["priority"],
        description=scenario["description"],
        message_sent=msg,
        responses=list(collected),
        elapsed_sec=elapsed,
        passed=passed,
        eval_note=eval_note,
    )

    status = "PASS" if passed else "FAIL"
    print(f"  결과: {status} | {eval_note} ({elapsed:.1f}s)")
    return result


# ── 보고서 생성 ────────────────────────────────────────────────────────────────
def write_report(results: list[ScenarioResult]) -> Path:
    now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today = datetime.now().strftime("%Y-%m-%d")

    total  = len(results)
    passed = sum(1 for r in results if r.passed)

    lines: list[str] = []

    lines += [
        f"# E2E 세션 테스트 리포트 — 2026-03-19",
        f"",
        f"실행 시각: {now}",
        f"",
        f"## 변경사항 요약",
        f"",
        f"- **A**: `core/pm_identity.py` — AgentPersonaMemory 성과 데이터 → 봇 시스템 프롬프트 주입",
        f"- **B**: `core/pm_orchestrator.py` — Discussion 멀티라운드 핑퐁 (라운드 메타데이터 버그 픽스 + 조기 종료 + follow-up 강화)",
        f"",
        f"## 요약 대시보드",
        f"",
        f"| 항목 | 값 |",
        f"|------|-----|",
        f"| 총 시나리오 | {total} |",
        f"| 통과 | {passed}/{total} |",
        f"| 통과율 | {passed/total*100:.0f}% |",
        f"",
    ]

    # P0 실패 강조
    p0_fails = [r for r in results if r.priority == "P0" and not r.passed]
    if p0_fails:
        lines += [
            "## P0 실패 시나리오 (즉시 수정 필요)",
            "",
        ]
        for r in p0_fails:
            lines += [
                f"### [{r.scenario_id}] {r.description}",
                f"- 평가: {r.eval_note}",
                f"- 소요시간: {r.elapsed_sec:.1f}s",
                f"- 응답 봇: {list({m.bot for m in r.responses}) or ['없음']}",
                "",
            ]
    else:
        lines += ["## P0 시나리오 전부 PASS", ""]

    # 시나리오별 결과 표
    lines += [
        "## 시나리오별 결과",
        "",
        "| ID | Priority | Status | 응답봇 | 응답수 | 소요시간 | 평가 |",
        "|----|----------|--------|--------|--------|---------|------|",
    ]
    for r in results:
        bots = list({m.bot for m in r.responses}) or ["-"]
        status = "PASS" if r.passed else "FAIL"
        lines.append(
            f"| {r.scenario_id} | {r.priority} | {status} "
            f"| {', '.join(bots[:3])} | {len(r.responses)} "
            f"| {r.elapsed_sec:.1f}s | {r.eval_note[:70]} |"
        )
    lines.append("")

    # 시나리오별 상세 + 전체 대화 로그
    lines += ["## 시나리오별 상세 및 전체 대화 로그", ""]

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        lines += [
            f"### [{r.scenario_id}] {r.description} — {status}",
            f"",
            f"- **우선순위**: {r.priority}",
            f"- **전송 메시지**: `{r.message_sent}`",
            f"- **소요시간**: {r.elapsed_sec:.1f}s",
            f"- **평가**: {r.eval_note}",
            f"- **응답 수**: {len(r.responses)}개",
            f"- **응답 봇**: {list({m.bot for m in r.responses}) or ['없음']}",
            f"",
        ]

        # 에러 패턴 상세
        errors = _detect_errors(r.responses)
        if errors:
            lines += [
                f"**에러 패턴 감지됨:**",
                "",
            ]
            for err in errors:
                lines.append(f"- {err}")
            lines.append("")

        # 전체 대화 로그 (원본)
        if r.responses:
            t0 = r.responses[0].ts
            lines += [
                "**전체 대화 로그:**",
                "",
                "```",
            ]
            for m in r.responses:
                elapsed = m.ts - t0
                lines.append(f"+{elapsed:6.1f}s  [{m.bot}]  {m.text}")
            lines.append("```")
        else:
            lines += ["**전체 대화 로그:** 없음"]

        lines.append("")

        # 평가 소견
        lines += [
            "**평가 소견:**",
            "",
        ]
        if r.passed:
            lines.append(f"- 정상 작동 확인: {r.eval_note}")
        else:
            lines.append(f"- 실패 원인: {r.eval_note}")

        # 멀티라운드 분석 (S-D1만)
        if r.scenario_id == "S-D1" and r.responses:
            all_text_lower = " ".join(m.text for m in r.responses).lower()
            multiround_kw = ["2라운드", "round 2", "추가 의견", "반박", "재논의", "다음 라운드", "라운드 2"]
            detected = [k for k in multiround_kw if k in all_text_lower]
            lines.append(f"- 멀티라운드 신호: {'감지됨 — ' + str(detected) if detected else '미감지 (1라운드로 완결됐거나 키워드 없음)'}")
            summary_kw = ["요약", "종합", "결론", "정리", "합의", "최종"]
            summary_detected = [k for k in summary_kw if k in all_text_lower]
            lines.append(f"- PM 요약 키워드: {summary_detected or '없음'}")

        lines.append("")

    # 성공 기준
    p0_ok = all(r.passed for r in results if r.priority == "P0")
    all_p0p1_ok = all(r.passed for r in results if r.priority in ("P0", "P1"))
    lines += [
        "## 성공 기준 평가",
        "",
        "| 레벨 | 기준 | 결과 |",
        "|------|------|------|",
        f"| 최소 합격 (P0 PASS) | S-D1 | {'PASS' if p0_ok else 'FAIL'} |",
        f"| 목표 (P0+P1 PASS) | S-D1, S-D2, S-P1 | {'PASS' if all_p0p1_ok else 'FAIL'} |",
        "",
    ]

    report_path = Path(__file__).parent.parent / "docs" / "retros" / "2026-03-19-e2e-session-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"E2E 결과: {passed}/{total} PASS ({passed/total*100:.0f}%)")
    print(f"리포트: {report_path}")
    print("=" * 60)

    return report_path


# ── 메인 ──────────────────────────────────────────────────────────────────────
async def main() -> None:
    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    await client.start(phone=PHONE)
    chat_entity = await client.get_entity(CHAT_ID)
    print(f"\nRocky 계정 연결 — 그룹 {chat_entity.id}")
    print(f"{len(SCENARIOS)}개 시나리오 시작")
    print("=" * 60)

    results: list[ScenarioResult] = []

    for i, scenario in enumerate(SCENARIOS):
        result = await run_scenario(client, chat_entity, scenario)
        results.append(result)

        if scenario["priority"] == "P0" and not result.passed:
            print(f"\n  P0 FAIL — [{scenario['id']}] 즉시 수정 필요!")

        if i < len(SCENARIOS) - 1:
            cooldown = 20
            print(f"\n  {cooldown}초 쿨다운...")
            await asyncio.sleep(cooldown)

    await client.disconnect()
    write_report(results)

    p0_fails = [r for r in results if r.priority == "P0" and not r.passed]
    if p0_fails:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
