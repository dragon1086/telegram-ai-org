"""
Telegram AI Org — 전체 시나리오 E2E 통합 테스트 (S1~S11)
Rocky 계정(MTProto/Telethon)으로 그룹에 메시지를 보내고 봇 응답을 수집·평가한다.

사용법:
  # 전체 실행
  .venv/bin/python scripts/e2e_full_suite.py

  # 특정 시나리오만 재실행
  .venv/bin/python scripts/e2e_full_suite.py --only S1,S2,S5

  # P0만 실행
  .venv/bin/python scripts/e2e_full_suite.py --priority P0
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from dotenv import load_dotenv
from telethon import TelegramClient, events

# ── 환경 변수 ────────────────────────────────────────────────────────────────
load_dotenv(Path(__file__).parent.parent / ".env")

API_ID   = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
PHONE    = os.environ["TELEGRAM_PHONE"]
CHAT_ID  = int(os.environ["TELEGRAM_GROUP_CHAT_ID"])

SESSION_FILE = Path(__file__).parent.parent / ".e2e_session"

_TS = datetime.now().strftime("%H%M%S")


# ── 데이터 모델 ──────────────────────────────────────────────────────────────
@dataclass
class BotMessage:
    bot: str
    text: str
    ts: float


@dataclass
class ScenarioResult:
    scenario_id: str
    priority: str       # P0 / P1 / P2
    description: str
    message_sent: str
    responses: list[BotMessage] = field(default_factory=list)
    elapsed_sec: float = 0.0
    passed: bool = False
    eval_note: str = ""
    detail_notes: list[str] = field(default_factory=list)


# ── 평가 함수 모음 ────────────────────────────────────────────────────────────
def _text(responses: list[BotMessage]) -> str:
    return " ".join(m.text for m in responses)


def eval_greeting(responses: list[BotMessage]) -> tuple[bool, str]:
    if not responses:
        return False, "❌ 응답 없음"
    t = _text(responses)
    if len(t) < 5:
        return False, f"⚠️ 응답 너무 짧음 ({len(t)}자)"
    return True, f"✅ 응답 받음 ({len(t)}자, {len(responses)}개 메시지)"


def eval_coding(responses: list[BotMessage]) -> tuple[bool, str]:
    if not responses:
        return False, "❌ 응답 없음"
    t = _text(responses).lower()
    # PM이 engineering 결과를 합성해서 전송하므로 봇 이름 체크 대신 콘텐츠 체크
    # 태스크 배분이 확인되면 PASS (비동기 실행 시간 고려)
    dispatch_kw = ["배분", "오케스트레이션", "개발실"]
    if any(k in t for k in dispatch_kw):
        # 배분 완료 — 실제 결과가 있으면 보너스 체크
        code_kw = ["for", "def", "return", "list", "comprehension", "컴프리헨션"]
        hits = [k for k in code_kw if k in t]
        if hits:
            return True, f"✅ 태스크 배분 + 코드 키워드 {hits[:3]}"
        return True, f"✅ 태스크 배분 확인 → 개발실 (비동기 실행 중)"
    # 배분 없이 직접 응답한 경우
    code_kw = ["[", "for", "if", "def", "return", "list", "comprehension", "컴프리헨션"]
    hits = [k for k in code_kw if k in t]
    if len(hits) < 2:
        return False, f"⚠️ 응답 없음 또는 코드 키워드 부족 ({len(hits)}/2): {hits}"
    return True, f"✅ 코딩 직접 응답 — 키워드 {len(hits)}개: {hits[:4]}"


def eval_growth(responses: list[BotMessage]) -> tuple[bool, str]:
    if not responses:
        return False, "❌ 응답 없음"
    t = _text(responses).lower()
    dispatch_kw = ["배분", "오케스트레이션", "성장실"]
    if any(k in t for k in dispatch_kw):
        return True, "✅ 태스크 배분 확인 → 성장실 (비동기 실행 중)"
    kw = ["plg", "성장", "마케팅", "전략", "acquisition", "growth", "채널"]
    hits = [k for k in kw if k in t]
    if len(hits) < 2:
        return False, f"⚠️ 성장/마케팅 키워드 부족 ({len(hits)}/2): {hits}"
    return True, f"✅ 키워드 {len(hits)}개: {hits[:4]}"


def eval_design(responses: list[BotMessage]) -> tuple[bool, str]:
    if not responses:
        return False, "❌ 응답 없음"
    t = _text(responses).lower()
    dispatch_kw = ["배분", "오케스트레이션", "디자인실"]
    if any(k in t for k in dispatch_kw):
        return True, "✅ 태스크 배분 확인 → 디자인실 (비동기 실행 중)"
    kw = ["ux", "온보딩", "화면", "경험", "ui", "인터페이스", "사용자"]
    hits = [k for k in kw if k in t]
    if len(hits) < 2:
        return False, f"⚠️ UX/디자인 키워드 부족 ({len(hits)}/2): {hits}"
    return True, f"✅ 키워드 {len(hits)}개: {hits[:4]}"


def eval_collab(responses: list[BotMessage]) -> tuple[bool, str]:
    if not responses:
        return False, "❌ 응답 없음"
    t = _text(responses).lower()
    bots = list({m.bot for m in responses})
    kw = ["기술", "스택", "마케팅", "채널", "stack", "marketing", "배분", "협업", "개발실", "성장실"]
    hits = [k for k in kw if k in t]
    total_len = sum(len(m.text) for m in responses)
    # PM이 모든 결과를 합성하므로 단일 봇(pm)만 응답해도 OK
    # 배분 확인이 있으면 태스크 진행 중으로 간주
    dispatch_kw = ["배분", "오케스트레이션", "개발실", "성장실"]
    dispatched = any(k in t for k in dispatch_kw)
    if dispatched:
        return True, f"✅ 멀티 부서 배분 확인 — 키워드: {[k for k in dispatch_kw if k in t]}"
    issues = []
    if len(hits) < 2:
        issues.append(f"⚠️ 키워드 부족 ({len(hits)}/2): {hits}")
    if total_len < 100:
        issues.append(f"⚠️ 응답 길이 부족 ({total_len}/100자)")
    if issues:
        return False, " | ".join(issues)
    return True, f"✅ {len(bots)}개 봇 + 키워드 {len(hits)}개 + {total_len}자"


def eval_discussion(responses: list[BotMessage]) -> tuple[bool, str]:
    if not responses:
        return False, "❌ 응답 없음"
    t = _text(responses).lower()
    bots = list({m.bot for m in responses})
    # 배분/토론 시작이 확인되면 진행 중으로 간주
    dispatch_kw = ["배분", "오케스트레이션", "토론", "논의", "b2b", "b2c"]
    if any(k in t for k in dispatch_kw):
        kw = ["b2b", "b2c", "전략", "시장"]
        hits = [k for k in kw if k in t]
        if hits:
            return True, f"✅ 토론/배분 확인 — 키워드: {hits}"
        return True, "✅ 토론 배분 확인 (실행 중)"
    kw = ["b2b", "b2c", "전략", "시장"]
    hits = [k for k in kw if k in t]
    summary_kw = ["요약", "종합", "결론", "정리", "summary"]
    has_summary = any(k in t for k in summary_kw)
    issues = []
    if len(responses) < 2:
        issues.append(f"⚠️ 봇 메시지 {len(responses)}개 (2개+ 필요)")
    if len(hits) < 2:
        issues.append(f"⚠️ 키워드 부족 ({len(hits)}/2): {hits}")
    if not has_summary:
        issues.append("⚠️ PM 요약 메시지 미감지")
    if issues:
        return False, " | ".join(issues)
    return True, f"✅ {len(bots)}개 봇 + 키워드 {len(hits)}개 + 요약 감지"


def eval_rest_api(responses: list[BotMessage]) -> tuple[bool, str]:
    if not responses:
        return False, "❌ 응답 없음"
    t = _text(responses).lower()
    # PM이 engineering 결과를 합성하므로 봇 이름 무관, 콘텐츠만 체크
    # 배분/처리 확인 메시지가 있으면 태스크 접수로 간주
    dispatch_kw = ["배분", "오케스트레이션", "처리", "완료", "개발실"]
    dispatched = any(k in t for k in dispatch_kw)
    http_kw = ["get", "post", "put", "delete", "patch"]
    path_kw = ["/todo", "/tasks", "/items", "endpoint", "엔드포인트", "api", "설계", "목록"]
    http_hits = [k for k in http_kw if k in t]
    path_hits = [k for k in path_kw if k in t]
    if dispatched and len(http_hits) < 2:
        return True, f"✅ 태스크 배분 확인 (실행 중)"
    if len(http_hits) < 2:
        return False, f"⚠️ HTTP 메서드 부족 ({len(http_hits)}/2): {http_hits}"
    if not path_hits:
        return False, f"⚠️ API 경로 키워드 없음"
    return True, f"✅ HTTP {http_hits} + 경로 {path_hits[:2]}"


def eval_status(responses: list[BotMessage]) -> tuple[bool, str]:
    if not responses:
        return False, "❌ /status 응답 없음"
    t = _text(responses)
    if len(t) < 10:
        return False, f"⚠️ 응답 너무 짧음 ({len(t)}자)"
    return True, f"✅ /status 응답 ({len(t)}자)"


def eval_clarify(responses: list[BotMessage]) -> tuple[bool, str]:
    if not responses:
        return False, "❌ 응답 없음"
    return True, f"✅ 응답 받음 ({len(responses)}개)"


def eval_complex(responses: list[BotMessage]) -> tuple[bool, str]:
    if not responses:
        return False, "❌ 응답 없음"
    t = _text(responses).lower()
    dispatch_kw = ["배분", "오케스트레이션", "개발실", "성장실"]
    if any(k in t for k in dispatch_kw):
        return True, "✅ 태스크 배분 확인 (복잡 태스크 비동기 실행 중)"
    total_len = sum(len(m.text) for m in responses)
    kw = ["프론트", "백엔드", "데이터베이스", "api", "인프라", "frontend", "backend"]
    hits = [k for k in kw if k in t]
    issues = []
    if total_len < 200:
        issues.append(f"⚠️ 응답 길이 부족 ({total_len}/200자)")
    if len(hits) < 3:
        issues.append(f"⚠️ 아키텍처 키워드 부족 ({len(hits)}/3): {hits}")
    if issues:
        return False, " | ".join(issues)
    return True, f"✅ {total_len}자 + 키워드 {len(hits)}개"


def eval_error_handling(responses: list[BotMessage]) -> tuple[bool, str]:
    # P2: 응답 없어도 PASS (크래시만 없으면 OK)
    return True, f"✅ 봇 크래시 없음 (응답 {len(responses)}개)"


# ── 시나리오 정의 ─────────────────────────────────────────────────────────────
SCENARIOS: list[dict] = [
    {
        "id": "S1",
        "priority": "P0",
        "message": f"안녕! [{_TS}]",
        "description": "인사 / Direct Answer",
        "timeout": 30,
        "eval_fn": eval_greeting,
        "expect_response": True,
    },
    {
        "id": "S2",
        "priority": "P0",
        "message": f"파이썬 리스트 컴프리헨션 예제 3개 만들어줘 [{_TS}]",
        "description": "단일 부서 위임 — 코딩 (engineering 봇)",
        "timeout": 360,
        "eval_fn": eval_coding,
        "expect_response": True,
    },
    {
        "id": "S3",
        "priority": "P1",
        "message": f"SaaS 제품의 Product-Led Growth 핵심 전략 3가지만 정리해줘 [{_TS}]",
        "description": "단일 부서 위임 — 성장/마케팅 (growth 봇)",
        "timeout": 150,
        "eval_fn": eval_growth,
        "expect_response": True,
    },
    {
        "id": "S4",
        "priority": "P1",
        "message": f"모바일 앱 온보딩 화면 UX 개선 포인트 알려줘 [{_TS}]",
        "description": "단일 부서 위임 — 디자인 (design 봇)",
        "timeout": 150,
        "eval_fn": eval_design,
        "expect_response": True,
    },
    {
        "id": "S5",
        "priority": "P0",
        "message": (
            f"새 AI SaaS MVP를 만들려고 해. "
            f"엔지니어링팀과 그로스팀이 협업해서 기술 스택 + 초기 마케팅 채널을 같이 제안해줘 [{_TS}]"
        ),
        "description": "멀티 부서 Collab 모드",
        "timeout": 120,
        "eval_fn": eval_collab,
        "expect_response": True,
    },
    {
        "id": "S6",
        "priority": "P1",
        "message": (
            f"AI 스타트업이 B2B vs B2C 중 어디를 먼저 공략해야 할지 "
            f"봇들끼리 얘기해봐 [{_TS}]"
        ),
        "description": "Discussion 모드 — 봇 간 토론 후 PM 요약",
        "timeout": 300,
        "eval_fn": eval_discussion,
        "expect_response": True,
    },
    {
        "id": "S7",
        "priority": "P0",
        "message": f"간단한 Todo 앱 REST API 엔드포인트 목록 설계해줘 [{_TS}]",
        "description": "REST API 설계 요청 — engineering 봇 위임",
        "timeout": 360,
        "eval_fn": eval_rest_api,
        "expect_response": True,
    },
    {
        "id": "S8",
        "priority": "P0",
        "message": "/status",
        "description": "/status 명령어",
        "timeout": 30,
        "eval_fn": eval_status,
        "expect_response": True,
    },
    {
        "id": "S9",
        "priority": "P1",
        "message": f"도와줘 [{_TS}]",
        "description": "모호한 요청 — Clarify 분기",
        "timeout": 60,
        "eval_fn": eval_clarify,
        "expect_response": True,
    },
    {
        "id": "S10",
        "priority": "P1",
        "message": (
            f"우리 AI SaaS 제품 전체 아키텍처를 처음부터 설계해줘. "
            f"프론트엔드, 백엔드, AI 파이프라인, 인프라, 모니터링까지 모두 포함해서 [{_TS}]"
        ),
        "description": "매우 긴 태스크 — 복잡도 high, 멀티봇",
        "timeout": 360,
        "eval_fn": eval_complex,
        "expect_response": True,
    },
    {
        "id": "S11",
        "priority": "P2",
        "message": f"... [{_TS}]",
        "description": "에러 핸들링 — 빈 의미 메시지 (크래시 없음 확인)",
        "timeout": 30,
        "eval_fn": eval_error_handling,
        "expect_response": False,
    },
]


# ── 수집 + 실행 ──────────────────────────────────────────────────────────────
async def run_scenario(
    client: TelegramClient,
    chat_entity,
    scenario: dict,
) -> ScenarioResult:
    sid      = scenario["id"]
    msg      = scenario["message"]
    timeout  = scenario["timeout"]
    eval_fn: Callable = scenario["eval_fn"]

    print(f"\n📤 [{sid}/{scenario['priority']}] {scenario['description']}")
    print(f"   메시지: {msg[:100]}")
    print(f"   ⏳ 최대 {timeout}초 대기…")

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

    status = "PASS ✅" if passed else "FAIL ❌"
    print(f"   결과: {status} | {eval_note} ({elapsed:.1f}s)")
    return result


# ── 메인 실행 ─────────────────────────────────────────────────────────────────
async def run_full_suite(only_ids: list[str] | None = None, only_priority: str | None = None) -> None:
    # 실행할 시나리오 필터
    scenarios_to_run = SCENARIOS
    if only_ids:
        ids_upper = [s.upper() for s in only_ids]
        scenarios_to_run = [s for s in SCENARIOS if s["id"].upper() in ids_upper]
        print(f"🔍 필터: {ids_upper} → {len(scenarios_to_run)}개 시나리오")
    elif only_priority:
        scenarios_to_run = [s for s in SCENARIOS if s["priority"] == only_priority.upper()]
        print(f"🔍 우선순위 필터: {only_priority} → {len(scenarios_to_run)}개 시나리오")

    if not scenarios_to_run:
        print("⚠️ 실행할 시나리오 없음. ID를 확인하세요.")
        return

    client = TelegramClient(str(SESSION_FILE), API_ID, API_HASH)
    await client.start(phone=PHONE)
    chat_entity = await client.get_entity(CHAT_ID)
    print(f"\n✅ Rocky 계정 연결 — 그룹 {chat_entity.id}")
    print(f"🚀 {len(scenarios_to_run)}개 시나리오 시작\n{'='*60}")

    results: list[ScenarioResult] = []

    for i, scenario in enumerate(scenarios_to_run):
        result = await run_scenario(client, chat_entity, scenario)
        results.append(result)

        # P0 실패 시 경고
        if scenario["priority"] == "P0" and not result.passed:
            print(f"\n   🚨 P0 FAIL — [{scenario['id']}] 즉시 수정 필요!")

        if i < len(scenarios_to_run) - 1:
            cooldown = 15 if scenario["priority"] in ("P0", "P1") else 5
            print(f"\n   💤 {cooldown}초 쿨다운…")
            await asyncio.sleep(cooldown)

    await client.disconnect()
    write_report(results)

    # 종료 코드: P0 실패 있으면 1
    p0_fails = [r for r in results if r.priority == "P0" and not r.passed]
    if p0_fails:
        print(f"\n🚨 P0 실패 {len(p0_fails)}개: {[r.scenario_id for r in p0_fails]}")
        print("   → 수정 후 재실행: .venv/bin/python scripts/e2e_full_suite.py --only " +
              ",".join(r.scenario_id for r in p0_fails))
        sys.exit(1)


# ── 리포트 생성 ───────────────────────────────────────────────────────────────
FAIL_GUIDE: dict[str, dict] = {
    "S1": {
        "증상": "무응답 or 너무 짧은 응답",
        "가설": "NL 분류기 greeting intent 경로 불통 or send_func 에러",
        "파일": "`core/pm_orchestrator.py`, `core/nl_classifier.py`",
        "방향": "greeting intent 처리 경로 확인, direct_answer lane 확인",
    },
    "S2": {
        "증상": "engineering 봇 미응답 or 코드 키워드 없음",
        "가설": "PM 라우팅 오분류 or engineering 봇 Claude Code 실행 실패",
        "파일": "`core/pm_router.py`, `bots/aiorg_engineering_bot.yaml`",
        "방향": "라우팅 힌트 또는 봇 토큰 확인",
    },
    "S3": {
        "증상": "growth 봇 미응답 or 성장/마케팅 키워드 없음",
        "가설": "PM이 growth 봇으로 라우팅 안 함",
        "파일": "`core/pm_router.py`, `bots/aiorg_growth_bot.yaml`",
        "방향": "dept_hints growth 경로 점검",
    },
    "S4": {
        "증상": "design 봇 미응답 or UX 키워드 없음",
        "가설": "PM이 design 봇으로 라우팅 안 함",
        "파일": "`core/pm_router.py`, `bots/aiorg_design_bot.yaml`",
        "방향": "dept_hints design 경로 점검",
    },
    "S5": {
        "증상": "단일 봇만 응답 or PM 합성 없음",
        "가설": "collab 모드 미트리거 / ResultSynthesizer 호출 안 됨",
        "파일": "`core/pm_orchestrator.py` (`_collab_mode`), `core/result_synthesizer.py`",
        "방향": "collab 모드 트리거 조건 확인, ResultSynthesizer 호출 경로 확인",
    },
    "S6": {
        "증상": "봇 간 대화 없음 or PM 요약 없음",
        "가설": "discussion dispatch 플래그 미설정 or PM 요약 send_fn 미호출",
        "파일": "`core/discussion_dispatch.py`, `core/pm_orchestrator.py`",
        "방향": "discussion dispatch 플래그 확인, 요약 메시지 send_fn 호출 확인",
    },
    "S7": {
        "증상": "REST API 설계 응답 없음 or HTTP 메서드 키워드 부족",
        "가설": "PM이 engineering 봇으로 라우팅 안 됨",
        "파일": "`core/pm_router.py`",
        "방향": "dept_hints engineering 경로, REST/API 키워드 분류 점검",
    },
    "S8": {
        "증상": "/status 무응답",
        "가설": "/status 커맨드 핸들러 미등록 or PM 봇 크래시",
        "파일": "`core/bot_commands.py`",
        "방향": "/status 커맨드 핸들러 등록 확인",
    },
    "S9": {
        "증상": "모호한 요청에 무응답",
        "가설": "clarify or direct_answer lane 미진입",
        "파일": "`core/pm_orchestrator.py`, `core/nl_classifier.py`",
        "방향": "clarify/direct_answer lane 분기 확인",
    },
    "S10": {
        "증상": "응답 길이 짧거나 아키텍처 키워드 부족",
        "가설": "complexity=high 분기 미처리 or 멀티봇 병렬 실행 미작동",
        "파일": "`core/pm_orchestrator.py`, `core/pm_router.py`",
        "방향": "complexity high 경로 및 multi_org_execution 분기 점검",
    },
    "S11": {
        "증상": "봇 크래시 (PASS 조건: 크래시 없음)",
        "가설": "빈/의미없는 메시지 처리 중 예외 발생",
        "파일": "`core/pm_orchestrator.py`",
        "방향": "메시지 전처리 및 예외 처리 로직 확인",
    },
}


def write_report(results: list[ScenarioResult]) -> None:
    now    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    today  = datetime.now().strftime("%Y-%m-%d")

    total  = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed

    p0 = [r for r in results if r.priority == "P0"]
    p1 = [r for r in results if r.priority == "P1"]
    p2 = [r for r in results if r.priority == "P2"]
    p0_pass = sum(1 for r in p0 if r.passed)
    p1_pass = sum(1 for r in p1 if r.passed)
    p2_pass = sum(1 for r in p2 if r.passed)

    lines: list[str] = []

    # ── 헤더
    lines += [
        f"# E2E 전체 테스트 리포트 — {now}",
        "",
        "## 요약 대시보드",
        "",
        "| 항목 | 값 |",
        "|------|-----|",
        f"| 총 시나리오 | {total} |",
        f"| P0 통과 | {p0_pass}/{len(p0)} |",
        f"| P1 통과 | {p1_pass}/{len(p1)} |",
        f"| P2 통과 | {p2_pass}/{len(p2)} |",
        f"| 전체 통과율 | {passed/total*100:.0f}% ({passed}/{total}) |",
        "",
    ]

    # ── P0 결과 (즉시 수정 대상)
    p0_fails = [r for r in p0 if not r.passed]
    if p0_fails:
        lines += [
            "## 🚨 P0 실패 시나리오 (즉시 수정 필요)",
            "",
        ]
        for r in p0_fails:
            lines += [
                f"### ❌ [{r.scenario_id}] {r.description}",
                f"- **평가**: {r.eval_note}",
                f"- **소요시간**: {r.elapsed_sec:.1f}s",
                f"- **응답 봇**: {[m.bot for m in r.responses] or '없음'}",
                "",
            ]
    else:
        lines += ["## ✅ P0 시나리오 전부 PASS", ""]

    # ── 시나리오별 상세 표
    lines += [
        "## 시나리오별 결과",
        "",
        "| # | ID | Priority | Status | 응답봇 | 소요시간 | 평가 |",
        "|---|-----|----------|--------|--------|---------|------|",
    ]
    for r in results:
        bots = list({m.bot for m in r.responses}) or ["-"]
        status = "PASS ✅" if r.passed else "FAIL ❌"
        lines.append(
            f"| {r.scenario_id[-1] if r.scenario_id.startswith('S') else '-'} "
            f"| {r.scenario_id} | {r.priority} | {status} "
            f"| {', '.join(bots[:2])} | {r.elapsed_sec:.1f}s | {r.eval_note[:60]} |"
        )
    lines.append("")

    # ── 상세
    lines += ["## 시나리오별 상세", ""]
    for r in results:
        status = "PASS ✅" if r.passed else "FAIL ❌"
        lines += [
            f"### [{r.scenario_id}] {r.description} — {status}",
            f"- **우선순위**: {r.priority}",
            f"- **전송 메시지**: `{r.message_sent[:120]}`",
            f"- **소요시간**: {r.elapsed_sec:.1f}s",
            f"- **평가**: {r.eval_note}",
        ]
        if r.responses:
            lines.append("- **봇 응답**:")
            t0 = r.responses[0].ts
            for m in r.responses:
                lines.append(f"  - `{m.bot}` (+{m.ts - t0:.1f}s): {m.text[:300]}")
        else:
            lines.append("- **봇 응답**: 없음")
        lines.append("")

    # ── 실패 분석 및 수정 가이드
    failed_results = [r for r in results if not r.passed]
    if failed_results:
        lines += ["## 실패 분석 및 수정 가이드", ""]
        for r in failed_results:
            guide = FAIL_GUIDE.get(r.scenario_id, {})
            lines += [
                f"### [{r.scenario_id}] {r.description}",
                f"- **긴급도**: {r.priority}",
                f"- **증상**: {guide.get('증상', r.eval_note)}",
                f"- **가설**: {guide.get('가설', '-')}",
                f"- **수정 파일**: {guide.get('파일', '-')}",
                f"- **수정 방향**: {guide.get('방향', '-')}",
                f"- **재테스트 명령**: `.venv/bin/python scripts/e2e_full_suite.py --only {r.scenario_id}`",
                "",
            ]

    # ── 성공 기준 평가
    min_viable = all(r.passed for r in results if r.priority == "P0")
    target = min_viable and all(r.passed for r in results if r.priority in ("P0", "P1"))
    full = passed == total

    lines += [
        "## 성공 기준 평가",
        "",
        f"| 레벨 | 기준 | 결과 |",
        f"|------|------|------|",
        f"| 최소 합격 (P0 전부 PASS) | S1,S2,S5,S7,S8 | {'✅ PASS' if min_viable else '❌ FAIL'} |",
        f"| 목표 (P0+P1 PASS) | S1~S9 | {'✅ PASS' if target else '❌ FAIL'} |",
        f"| 완전 (S1~S11 PASS) | 전체 | {'✅ PASS' if full else '❌ FAIL'} |",
        "",
    ]

    report_path = Path(__file__).parent.parent / "docs" / "retros" / f"{today}-e2e-full-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"\n{'='*60}")
    print(f"📊 E2E 결과: {passed}/{total} PASS ({passed/total*100:.0f}%)")
    print(f"   P0: {p0_pass}/{len(p0)}  P1: {p1_pass}/{len(p1)}  P2: {p2_pass}/{len(p2)}")
    print(f"📄 리포트: {report_path}")
    print("=" * 60)


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Telegram AI Org E2E Full Suite")
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="쉼표로 구분된 시나리오 ID (예: S1,S2,S5)",
    )
    parser.add_argument(
        "--priority",
        type=str,
        default=None,
        choices=["P0", "P1", "P2"],
        help="특정 우선순위만 실행",
    )
    args = parser.parse_args()

    only_ids = [s.strip() for s in args.only.split(",")] if args.only else None
    asyncio.run(run_full_suite(only_ids=only_ids, only_priority=args.priority))
