"""
Collab + Discussion 모드 Telegram E2E 테스트.
Rocky 계정(MTProto/Telethon)으로 그룹에 메시지를 보내고
봇 응답을 수집해 다각도로 평가한다.

평가 차원:
  - 자연스러운 흐름 (flow)
  - 응답 효율성 (elapsed_sec, bot_count)
  - 최초 질문 목적 부합성 (relevance)
  - 모드 트리거 여부 (mode_triggered)
"""
from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, events

load_dotenv(Path(__file__).parent.parent / ".env")

API_ID   = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
PHONE    = os.environ["TELEGRAM_PHONE"]
CHAT_ID  = int(os.environ["TELEGRAM_GROUP_CHAT_ID"])

SESSION_FILE = Path(__file__).parent.parent / ".e2e_session"

_TS = datetime.now().strftime("%H%M%S")

# ── 시나리오 정의 ─────────────────────────────────────────────────────────────
SCENARIOS: list[dict] = [
    # ── 베이스라인: 단순 delegate ──────────────────────────────────────────────
    {
        "id":          "baseline_delegate",
        "mode":        "delegate",
        "message":     f"파이썬 asyncio 이벤트 루프가 뭔지 한 문단으로 설명해줘 [{_TS}]",
        "description": "단순 위임 → 코딩봇 단독 응답 (베이스라인)",
        "timeout":     120,
        "eval": {
            "relevance_kw": ["asyncio", "이벤트", "루프", "비동기", "coroutine"],
            "mode_kw":      [],          # 특정 모드 트리거 불필요
            "min_length":   80,
        },
    },
    # ── Collab 모드 ────────────────────────────────────────────────────────────
    {
        "id":          "collab_multi_dept",
        "mode":        "collab",
        "message":     (
            f"새 AI SaaS 제품 MVP를 만들려고 해. "
            f"엔지니어링팀과 그로스팀이 협업해서 기술 스택 + 초기 마케팅 채널을 같이 제안해줘 [{_TS}]"
        ),
        "description": "Collab 모드 — 엔지니어링+그로스 협업 후 PM이 합성 답변 전송",
        "timeout":     300,
        "eval": {
            "relevance_kw": ["기술", "스택", "마케팅", "채널", "MVP", "서비스"],
            "mode_kw":      ["collab", "협업", "합성", "종합"],
            "min_length":   150,
        },
    },
    # ── Discussion 모드 ────────────────────────────────────────────────────────
    {
        "id":          "discussion_strategy",
        "mode":        "discussion",
        "message":     (
            f"AI 스타트업이 B2B vs B2C 중 어디를 먼저 공략해야 할지 "
            f"봇들끼리 얘기해봐 [{_TS}]"
        ),
        "description": "Discussion 모드 — 자유 토론 후 PM이 중립 요약 전송",
        "timeout":     300,
        "eval": {
            "relevance_kw": ["B2B", "B2C", "스타트업", "전략", "공략", "시장"],
            "mode_kw":      ["토론", "요약", "의견", "관점"],
            "min_length":   100,
        },
    },
]

# ── 결과 모델 ─────────────────────────────────────────────────────────────────
@dataclass
class BotMessage:
    bot: str
    text: str
    ts: float


@dataclass
class ScenarioResult:
    scenario_id: str
    mode: str
    description: str
    message_sent: str
    responses: list[BotMessage] = field(default_factory=list)
    elapsed_sec: float = 0.0
    # 평가 결과
    mode_triggered: bool = False
    relevance_ok: bool = False
    flow_ok: bool = False
    efficiency_note: str = ""
    eval_notes: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.relevance_ok and bool(self.responses)


# ── 평가 함수 ─────────────────────────────────────────────────────────────────
def evaluate(result: ScenarioResult, spec: dict) -> None:
    ev = spec["eval"]
    all_text = " ".join(m.text for m in result.responses).lower()

    # 1. 응답 존재
    if not result.responses:
        result.eval_notes.append("❌ 봇 응답 없음")
        return

    # 2. 관련성 (질문 목적 부합)
    matched_kw = [kw for kw in ev["relevance_kw"] if kw.lower() in all_text]
    result.relevance_ok = len(matched_kw) >= max(1, len(ev["relevance_kw"]) // 2)
    result.eval_notes.append(
        f"{'✅' if result.relevance_ok else '⚠️'} 관련성: "
        f"{len(matched_kw)}/{len(ev['relevance_kw'])} 키워드 일치 {matched_kw}"
    )

    # 3. 모드 트리거
    if ev["mode_kw"]:
        mode_matched = [kw for kw in ev["mode_kw"] if kw.lower() in all_text]
        result.mode_triggered = bool(mode_matched)
        result.eval_notes.append(
            f"{'✅' if result.mode_triggered else '⚠️'} 모드 트리거: "
            f"{mode_matched if mode_matched else '미감지'}"
        )
    else:
        result.mode_triggered = True  # 베이스라인은 모드 불필요

    # 4. 응답 길이 (품질 프록시)
    total_len = sum(len(m.text) for m in result.responses)
    min_len = ev["min_length"]
    len_ok = total_len >= min_len
    result.eval_notes.append(
        f"{'✅' if len_ok else '⚠️'} 응답 총 길이: {total_len}자 (기준 {min_len}자)"
    )

    # 5. 흐름 — 응답 봇 수 & 간격
    bots = list({m.bot for m in result.responses})
    if spec["mode"] == "collab":
        result.flow_ok = len(bots) >= 2
        result.eval_notes.append(
            f"{'✅' if result.flow_ok else '⚠️'} 흐름: {len(bots)}개 봇 참여 {bots} "
            f"(collab은 2개+ 기대)"
        )
    elif spec["mode"] == "discussion":
        result.flow_ok = len(bots) >= 1  # PM이 요약 전송하면 OK
        result.eval_notes.append(
            f"{'✅' if result.flow_ok else '⚠️'} 흐름: {len(bots)}개 봇 참여 {bots} "
            f"(PM 요약 포함)"
        )
    else:
        result.flow_ok = len(bots) >= 1
        result.eval_notes.append(f"✅ 흐름: {len(bots)}개 봇 응답")

    # 6. 효율성
    result.efficiency_note = (
        f"{result.elapsed_sec:.1f}초 / {len(result.responses)}개 메시지 / {len(bots)}개 봇"
    )


# ── 메인 ──────────────────────────────────────────────────────────────────────
async def run() -> None:
    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    await client.start(phone=PHONE)
    chat_entity = await client.get_entity(CHAT_ID)
    print(f"\n✅ Rocky 계정 연결 — 그룹 {chat_entity.id}\n{'='*60}")

    results: list[ScenarioResult] = []

    for scenario in SCENARIOS:
        sid      = scenario["id"]
        mode     = scenario["mode"]
        msg      = scenario["message"]
        timeout  = scenario["timeout"]

        print(f"\n📤 [{sid}] {scenario['description']}")
        print(f"   메시지: {msg}")
        print(f"   ⏳ 최대 {timeout}초 대기…")

        # 리스너 초기화 시점의 최신 메시지 ID 기록 — cross-contamination 방지
        _latest = await client.get_messages(chat_entity, limit=1)
        min_id: int = _latest[0].id if _latest else 0

        collected: list[BotMessage] = []
        stop = [False]

        async def handler(event, _c=collected, _s=stop, _min_id=min_id):
            if _s[0]:
                return
            if event.message.id <= _min_id:  # 초기화 이전 메시지 skip (cross-contamination 방지)
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
                print(f"   📨 [{entry.bot}] {text[:160]}")

        client.add_event_handler(handler, events.NewMessage(chats=chat_entity))
        client.add_event_handler(handler, events.MessageEdited(chats=chat_entity))

        t0 = time.time()
        await client.send_message(CHAT_ID, msg)
        await asyncio.sleep(timeout)
        stop[0] = True
        elapsed = time.time() - t0

        client.remove_event_handler(handler, events.NewMessage(chats=chat_entity))
        client.remove_event_handler(handler, events.MessageEdited(chats=chat_entity))

        result = ScenarioResult(
            scenario_id=sid,
            mode=mode,
            description=scenario["description"],
            message_sent=msg,
            responses=list(collected),
            elapsed_sec=elapsed,
        )
        evaluate(result, scenario)
        results.append(result)

        status = "PASS ✅" if result.passed else "FAIL ❌"
        print(f"\n   결과: {status} | 효율: {result.efficiency_note}")
        for note in result.eval_notes:
            print(f"   {note}")

        if scenario is not SCENARIOS[-1]:
            print("\n   💤 다음 시나리오까지 15초 쿨다운…")
            await asyncio.sleep(15)

    await client.disconnect()
    _write_report(results)


def _write_report(results: list[ScenarioResult]) -> None:
    passed = sum(1 for r in results if r.passed)
    total  = len(results)
    now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# Collab + Discussion E2E 테스트 리포트\n",
        f"생성: {now}\n",
        "## 요약\n",
        f"| 항목 | 값 |\n|------|----|\n"
        f"| 총 시나리오 | {total} |\n"
        f"| 통과 | {passed} |\n"
        f"| 실패 | {total - passed} |\n"
        f"| 통과율 | {passed/total*100:.0f}% |\n",
        "\n## 다각도 평가\n",
        "| 시나리오 | 모드 | 관련성 | 모드 트리거 | 흐름 | 효율 | 종합 |",
        "|----------|------|--------|------------|------|------|------|",
    ]
    for r in results:
        lines.append(
            f"| {r.scenario_id} | {r.mode} "
            f"| {'✅' if r.relevance_ok else '❌'} "
            f"| {'✅' if r.mode_triggered else '❌'} "
            f"| {'✅' if r.flow_ok else '❌'} "
            f"| {r.efficiency_note} "
            f"| {'PASS ✅' if r.passed else 'FAIL ❌'} |"
        )

    lines.append("\n## 시나리오별 상세\n")
    for r in results:
        status = "PASS ✅" if r.passed else "FAIL ❌"
        lines += [
            f"### {r.scenario_id} — {status}",
            f"- **모드**: {r.mode}",
            f"- **설명**: {r.description}",
            f"- **전송 메시지**: `{r.message_sent[:120]}`",
            f"- **소요시간**: {r.elapsed_sec:.1f}s",
            f"- **효율**: {r.efficiency_note}",
            "- **평가**:",
        ]
        for note in r.eval_notes:
            lines.append(f"  - {note}")
        if r.responses:
            lines.append("- **봇 응답**:")
            for m in r.responses:
                lines.append(f"  - `{m.bot}` (+{m.ts - r.responses[0].ts:.1f}s): {m.text[:300]}")
        else:
            lines.append("- **봇 응답**: 없음")
        lines.append("")

    # 종합 평가 섹션
    lines += [
        "## 종합 평가\n",
        "### 자연스러운 흐름",
    ]
    for r in results:
        flow_note = next((n for n in r.eval_notes if "흐름" in n), "")
        lines.append(f"- **{r.scenario_id}**: {flow_note}")

    lines += ["", "### 효율성"]
    for r in results:
        lines.append(f"- **{r.scenario_id}**: {r.efficiency_note}")

    lines += ["", "### 질문 목적 부합성"]
    for r in results:
        rel_note = next((n for n in r.eval_notes if "관련성" in n), "")
        lines.append(f"- **{r.scenario_id}**: {rel_note}")

    report_path = (
        Path(__file__).parent.parent
        / "docs" / "retros"
        / "2026-03-17-collab-discussion-e2e-report.md"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"📊 E2E 결과: {passed}/{total} 통과 ({passed/total*100:.0f}%)")
    print(f"📄 리포트: {report_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run())
