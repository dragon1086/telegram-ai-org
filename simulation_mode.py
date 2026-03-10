"""시뮬레이션 모드 — 실제 Telegram 없이 AI 조직 로직 테스트."""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

SIM_DIR = Path.home() / ".ai-org"
SIM_RESULTS = SIM_DIR / "sim_results.jsonl"


def _ensure_sim_dir() -> None:
    SIM_DIR.mkdir(parents=True, exist_ok=True)


def _save_result(user_input: str, result: dict) -> None:
    _ensure_sim_dir()
    record = {
        "timestamp": datetime.utcnow().isoformat(),
        "input": user_input,
        "result": result,
    }
    with SIM_RESULTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

# 프로젝트 루트를 path에 추가
sys.path.insert(0, str(Path(__file__).parent))

from core.llm_router import LLMRouter
from core.task_planner import TaskPlanner
from core.worker_registry import WorkerRegistry


BANNER = """
╔══════════════════════════════════════════════════════╗
║      telegram-ai-org  —  시뮬레이션 모드             ║
║  실제 Telegram 없이 PM + 워커 로직을 테스트합니다    ║
╚══════════════════════════════════════════════════════╝
"""


async def run_simulation() -> None:
    print(BANNER)
    _ensure_sim_dir()

    # 워커 레지스트리 로드
    registry = WorkerRegistry()
    workers = registry.load()

    if not workers:
        print("⚠️  workers.yaml에 등록된 워커가 없습니다.")
        print("   먼저 setup_wizard.py를 실행하거나 workers.yaml을 직접 편집하세요.\n")
        # 데모용 가상 워커
        workers = [
            {"name": "cokac", "engine": "claude-code", "description": "코딩, 구현, 리팩토링 전문"},
            {"name": "researcher", "engine": "codex", "description": "분석, 리서치, 데이터 처리"},
        ]
        print("📋 데모용 가상 워커로 진행합니다:")
        for w in workers:
            print(f"   • {w['name']} ({w['engine']}) — {w['description']}")
        print()

    router = LLMRouter()

    print("🤖 PM Bot 준비 완료. 유저 요청을 입력하세요. (종료: quit)\n")

    while True:
        try:
            user_input = input("👤 유저: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 시뮬레이션 종료")
            break

        if user_input.lower() in ("quit", "exit", "q"):
            print("👋 시뮬레이션 종료")
            break

        if not user_input:
            continue

        print("\n⏳ PM이 태스크를 분석 중...\n")

        try:
            result = await router.route(user_input, workers)
        except Exception as e:
            # OpenAI 키 없으면 간단 폴백
            print(f"⚠️  LLM 호출 실패 ({e}). 키워드 매칭 폴백 사용.\n")
            result = _keyword_fallback(user_input, workers)

        print(f"📊 PM 분석: {result.get('analysis', '-')}\n")

        assignments = result.get("assignments", [])
        if not assignments:
            print("❌ 적합한 워커를 찾지 못했습니다.\n")
            continue

        print("📋 태스크 배분:")
        for i, assign in enumerate(assignments, 1):
            worker = assign.get("worker_name", "?")
            instruction = assign.get("instruction", "?")
            priority = assign.get("priority", "medium")
            print(f"  [{i}] → {worker} [{priority}]")
            print(f"       지시: {instruction}")
        print()

        print(f"✅ 완료 기준: {result.get('completion_criteria', '-')}\n")
        print("─" * 54 + "\n")
        _save_result(user_input, result)


def _keyword_fallback(task: str, workers: list[dict]) -> dict:
    """LLM 없을 때 키워드 기반 단순 라우팅."""
    task_lower = task.lower()
    assignments = []

    for w in workers:
        desc_lower = w["description"].lower()
        keywords = [kw.strip() for kw in desc_lower.replace(",", " ").split() if len(kw) > 2]
        if any(kw in task_lower for kw in keywords):
            assignments.append({
                "worker_name": w["name"],
                "instruction": f"다음 태스크를 처리해주세요: {task}",
                "priority": "medium",
            })

    if not assignments and workers:
        assignments.append({
            "worker_name": workers[0]["name"],
            "instruction": f"다음 태스크를 처리해주세요: {task}",
            "priority": "medium",
        })

    return {
        "analysis": "키워드 매칭 기반 분석 (LLM 미사용)",
        "assignments": assignments,
        "completion_criteria": "워커 보고 완료 시",
    }


async def run_planner_demo(workers: list[dict] | None = None) -> None:
    """TaskPlanner 데모 — Phase 분해 결과를 출력."""
    if workers is None:
        workers = [
            {"name": "cokac", "engine": "claude-code", "description": "코딩, 구현, 리팩토링 전문"},
            {"name": "researcher", "engine": "codex", "description": "분석, 리서치, 데이터 처리"},
        ]

    planner = TaskPlanner()
    demo_request = "prism-mobile 다크모드 + 분석 리포트 동시에 만들어줘"

    print(f"\n{'─' * 54}")
    print(f"📋 TaskPlanner 데모")
    print(f"입력: {demo_request}")
    print(f"{'─' * 54}\n")

    try:
        plan = await planner.plan(demo_request, workers)
    except Exception as e:
        print(f"⚠️  LLM 호출 실패 ({e}). 폴백 계획 사용.\n")
        plan = planner._fallback_plan(demo_request, workers)

    print(f"📌 요약: {plan.summary}")
    print(f"🔧 예상 워커: {', '.join(plan.estimated_workers) or '-'}\n")

    for i, phase in enumerate(plan.phases):
        mode = "병렬 ⚡" if phase.parallel else "순차 →"
        print(f"  Phase {i + 1} [{mode}]")
        for j, task in enumerate(phase.tasks):
            dep = f" (의존: {task.depends_on})" if task.depends_on else ""
            print(f"    [{j + 1}] {task.worker_name}: {task.instruction}{dep}")
        print()

    print(f"{'─' * 54}\n")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--planner-demo":
        asyncio.run(run_planner_demo())
    else:
        asyncio.run(run_simulation())
