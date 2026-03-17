"""
실제 Telegram E2E 테스트 스크립트.
Rocky 계정(MTProto)으로 그룹에 메시지를 보내고, 봇 응답을 수집해 평가한다.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, events
from telethon.tl.types import PeerChat, PeerChannel

# ── 환경 변수 ────────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).parent.parent / ".env")

API_ID   = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
PHONE    = os.environ["TELEGRAM_PHONE"]
CHAT_ID  = int(os.environ["TELEGRAM_GROUP_CHAT_ID"])  # 음수값

SESSION_FILE = Path(__file__).parent.parent / ".e2e_session"

# ── 테스트 시나리오 ──────────────────────────────────────────────────────────
_TS = datetime.now().strftime("%H%M%S")  # 각 실행마다 고유 suffix → text_hash 중복 방지

SCENARIOS = [
    {
        "id": "greeting",
        "message": f"안녕! 잘 있었어? [{_TS}]",
        "description": "인사 → 직접 답변 또는 간단 응답",
        "expect_response": True,
        "timeout": 60,
        "eval_fn": lambda text: len(text) > 0,
    },
    {
        "id": "coding_task",
        "message": f"파이썬에서 리스트를 딕셔너리로 변환하는 방법 알려줘 [{_TS}]",
        "description": "코딩 지식 질문 → 코딩봇이 응답",
        "expect_response": True,
        "timeout": 200,
        "eval_fn": lambda text: any(kw in text.lower() for kw in ["dict", "딕셔너리", "zip", "{", "comprehension", "컴프리헨션"]),
    },
    {
        "id": "task_delegation",
        "message": f"간단한 todo 앱의 REST API 설계해줘 (엔드포인트 목록만) [{_TS}]",
        "description": "설계 요청 → PM이 위임 후 응답",
        "expect_response": True,
        "timeout": 210,
        "eval_fn": lambda text: any(kw in text.lower() for kw in ["get", "post", "put", "delete", "/todo", "api", "엔드포인트"]),
    },
    {
        "id": "multi_dept",
        "message": f"새 SaaS 제품 론칭을 위한 기술 스택 선정과 초기 마케팅 채널 추천해줘 [{_TS}]",
        "description": "멀티부서 요청 → 엔지니어링 + 그로스봇 협업",
        "expect_response": True,
        "timeout": 150,
        "eval_fn": lambda text: len(text) > 100,
    },
    {
        "id": "performance_check",
        "message": "/status",
        "description": "봇 상태 확인 커맨드",
        "expect_response": True,
        "timeout": 30,
        "eval_fn": lambda text: len(text) > 0,
    },
]

# ── 결과 수집 ────────────────────────────────────────────────────────────────
@dataclass
class ScenarioResult:
    scenario_id: str
    description: str
    message_sent: str
    responses: list[dict] = field(default_factory=list)
    elapsed_sec: float = 0.0
    passed: bool = False
    eval_note: str = ""


async def run_e2e_tests() -> None:
    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    await client.start(phone=PHONE)

    # Telethon peer 해석 — chat_id를 Telethon entity로 resolve
    chat_entity = await client.get_entity(CHAT_ID)
    print(f"\n✅ Telethon 연결 성공 — Rocky 계정으로 {chat_entity.id} 그룹 테스트 시작\n")
    print("=" * 60)

    results: list[ScenarioResult] = []

    # 단일 글로벌 핸들러 — 현재 수집 중인 시나리오 버퍼에 append
    active_collected: list[dict] = []
    active_collecting: bool = False

    async def global_handler(event):
        if not active_collecting:
            return
        sender = await event.get_sender()
        if sender and getattr(sender, "bot", False):
            entry = {
                "bot": getattr(sender, "username", "unknown"),
                "text": event.message.text or "",
                "ts": time.time(),
            }
            active_collected.append(entry)
            print(f"   📨 [{entry['bot']}] {entry['text'][:120]}")

    client.add_event_handler(global_handler, events.NewMessage(chats=chat_entity))

    for scenario in SCENARIOS:
        sid = scenario["id"]
        msg = scenario["message"]
        desc = scenario["description"]
        timeout = scenario["timeout"]
        eval_fn = scenario["eval_fn"]

        print(f"\n📤 [{sid}] {desc}")
        print(f"   보내는 메시지: {msg}")

        result = ScenarioResult(
            scenario_id=sid,
            description=desc,
            message_sent=msg,
        )

        # 수집 버퍼 초기화
        active_collected.clear()
        active_collecting = True  # noqa: F841 — used via closure

        # Python closure workaround: use nonlocal trick via mutable container
        _flag = [True]

        async def _scoped_handler(event, _f=_flag, _c=active_collected):
            if not _f[0]:
                return
            sender = await event.get_sender()
            if sender and getattr(sender, "bot", False):
                entry = {
                    "bot": getattr(sender, "username", "unknown"),
                    "text": event.message.text or "",
                    "ts": time.time(),
                }
                _c.append(entry)
                print(f"   📨 [{entry['bot']}] {entry['text'][:120]}")

        client.remove_event_handler(global_handler)
        client.add_event_handler(_scoped_handler, events.NewMessage(chats=chat_entity))

        t0 = time.time()
        await client.send_message(CHAT_ID, msg)
        print(f"   ⏳ 응답 대기 중 (최대 {timeout}초)…")
        await asyncio.sleep(timeout)
        _flag[0] = False
        result.elapsed_sec = time.time() - t0

        client.remove_event_handler(_scoped_handler)

        result.responses = list(active_collected)

        # 평가
        all_text = " ".join(r["text"] for r in result.responses)
        if not scenario["expect_response"]:
            result.passed = True
            result.eval_note = "응답 불필요"
        elif not result.responses:
            result.passed = False
            result.eval_note = "❌ 응답 없음"
        else:
            passed = eval_fn(all_text)
            result.passed = passed
            result.eval_note = "✅ 기준 충족" if passed else "⚠️ 응답 받았으나 기준 미충족"

        status = "PASS ✅" if result.passed else "FAIL ❌"
        print(f"   결과: {status} — {result.eval_note} ({result.elapsed_sec:.1f}s)")

        results.append(result)

        # 시나리오 간 쿨다운
        if scenario != SCENARIOS[-1]:
            print("   💤 다음 시나리오까지 10초 대기…")
            await asyncio.sleep(10)

    # ── 리포트 생성 ──────────────────────────────────────────────────────────
    await client.disconnect()
    _write_report(results)


def _write_report(results: list[ScenarioResult]) -> None:
    passed = sum(1 for r in results if r.passed)
    total  = len(results)
    now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        "# Telegram E2E 테스트 리포트\n",
        f"생성: {now}\n",
        "## 요약\n",
        f"| 항목 | 값 |\n|------|----|\n"
        f"| 총 시나리오 | {total} |\n"
        f"| 통과 | {passed} |\n"
        f"| 실패 | {total - passed} |\n"
        f"| 통과율 | {passed/total*100:.0f}% |\n",
        "\n## 시나리오별 결과\n",
    ]

    for r in results:
        status = "PASS ✅" if r.passed else "FAIL ❌"
        lines.append(f"\n### {r.scenario_id} — {status}")
        lines.append(f"- **설명**: {r.description}")
        lines.append(f"- **전송**: `{r.message_sent}`")
        lines.append(f"- **소요시간**: {r.elapsed_sec:.1f}s")
        lines.append(f"- **평가**: {r.eval_note}")
        if r.responses:
            lines.append("- **응답**:")
            for resp in r.responses:
                lines.append(f"  - `{resp['bot']}`: {resp['text'][:200]}")
        else:
            lines.append("- **응답**: 없음")

    report_path = Path(__file__).parent.parent / "docs" / "retros" / "2026-03-17-telegram-e2e-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"📊 E2E 결과: {passed}/{total} 통과 ({passed/total*100:.0f}%)")
    print(f"📄 리포트: {report_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_e2e_tests())
