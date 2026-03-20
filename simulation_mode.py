"""시뮬레이션 모드 — 실제 Telegram 없이 AI 조직 로직 테스트."""
from __future__ import annotations

import asyncio
import json
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

from core.worker_registry import WorkerRegistry

try:
    from core.llm_router import LLMRouter
    from core.task_planner import TaskPlanner
    _ROUTER_AVAILABLE = True
except ImportError:
    _ROUTER_AVAILABLE = False

try:
    from core.agent_catalog import AgentCatalog
    from core.dynamic_team_builder import DynamicTeamBuilder, ExecutionMode
    _DYNAMIC_TEAM_AVAILABLE = True
except ImportError:
    _DYNAMIC_TEAM_AVAILABLE = False

try:
    from core.memory_manager import MemoryManager
    _MEMORY_AVAILABLE = True
except ImportError:
    _MEMORY_AVAILABLE = False


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
    print("📋 TaskPlanner 데모")
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


async def run_dynamic_team_demo() -> None:
    """DynamicTeamBuilder 데모 — 팀 구성 및 DRY-RUN 출력."""
    if not _DYNAMIC_TEAM_AVAILABLE:
        print("⚠️  DynamicTeamBuilder 모듈을 불러올 수 없습니다.")
        print("   core/agent_catalog.py 와 core/dynamic_team_builder.py 가 필요합니다.")
        return

    task = "프리즘 인사이트 채널용 주간 시장 분석 보고서 작성해줘"

    print(f"\n{'─' * 54}")
    print("🔍 DynamicTeamBuilder 데모")
    print(f"입력: {task}")
    print(f"{'─' * 54}\n")

    # AgentCatalog 로드
    try:
        catalog = AgentCatalog()
        catalog.load()
    except Exception as e:
        print(f"⚠️  AgentCatalog 로드 실패 ({e}). 기본값으로 진행합니다.\n")
        catalog = None

    # DynamicTeamBuilder 생성
    try:
        team_builder = DynamicTeamBuilder(catalog=catalog)
    except Exception as e:
        print(f"⚠️  DynamicTeamBuilder 초기화 실패 ({e}).")
        return

    # 팀 구성 (LLM 폴백 허용)
    try:
        config = await team_builder.build_team(task)
    except Exception as e:
        print(f"⚠️  build_team 실패 ({e}). 폴백 팀 구성 사용.\n")
        try:
            config = team_builder._fallback_team(task)
        except Exception as e2:
            print(f"❌ 폴백도 실패 ({e2}).")
            return

    # 팀 구성 출력
    agents = getattr(config, "agents", [])
    execution_mode = getattr(config, "execution_mode", "unknown")
    omc_team_format = getattr(config, "omc_team_format", "")

    # ExecutionMode enum 처리
    if hasattr(execution_mode, "value"):
        execution_mode_str = execution_mode.value
    else:
        execution_mode_str = str(execution_mode)

    print("📋 팀 구성:")
    for agent in agents:
        agent_name = getattr(agent, "name", str(agent))
        agent_model = getattr(agent, "model", "claude-sonnet-4-6")
        print(f"  - {agent_name} ({agent_model})")

    print(f"🚀 실행 모드: {execution_mode_str}")

    # 팀 발표 메시지
    try:
        announcement = team_builder.format_team_announcement(config)
        print(f"📡 팀 발표: {announcement}")
    except Exception as e:
        print(f"📡 팀 발표: (format_team_announcement 실패: {e})")

    print()

    # DRY-RUN omc 명령 출력
    if omc_team_format:
        print("[DRY-RUN] 실제 실행 시 명령:")
        print(f"  /team {omc_team_format} {task}")
    else:
        # omc_team_format이 없으면 agents에서 조합
        if agents:
            agent_parts = []
            seen: dict[str, int] = {}
            for agent in agents:
                name = getattr(agent, "name", str(agent))
                seen[name] = seen.get(name, 0) + 1
            fmt = ",".join(f"{count}:{name}" for name, count in seen.items())
            print("[DRY-RUN] 실제 실행 시 명령:")
            print(f"  /team {fmt} {task}")

    print(f"\n{'─' * 54}\n")


async def run_memory_test() -> None:
    """MemoryManager 동작 테스트 — CORE/SUMMARY/LOG 3계층 검증."""
    if not _MEMORY_AVAILABLE:
        print("⚠️  MemoryManager 모듈을 불러올 수 없습니다.")
        return

    print(f"\n{'─' * 54}")
    print("🧠 MemoryManager 테스트")
    print(f"{'─' * 54}\n")

    scope = "sim_test"
    mm = MemoryManager(scope)

    # 1. CORE 추가
    mm.add_core("프리즘 인사이트 = 주식분석 텔레그램 채널 (@stock_ai_ko)")
    mm.add_core("보안 리뷰는 배포 전 필수 (상록 지시)")
    print(f"✅ CORE 추가: {mm.stats()['core']}개")

    # 2. LOG 추가 (LLM 없이 키워드 폴백)
    test_logs = [
        "FastAPI 서버 구축 완료",
        "인증 버그 수정 — JWT 만료 처리",
        "README 업데이트",
        "보안 리뷰 완료 후 배포 진행",
        "단순 파일 정리 작업",
    ]
    for log_content in test_logs:
        importance = await mm.add_log(log_content)  # openai_client=None → 키워드 폴백
        print(f"  LOG [{importance}] {log_content[:40]}")

    stats = mm.stats()
    print(f"\n📊 메모리 통계: CORE={stats['core']}, SUMMARY={stats['summary']}, LOG={stats['log']}")

    # 3. 컨텍스트 생성
    ctx = mm.build_context("보안 배포 작업")
    print(f"\n📋 build_context('보안 배포 작업'):\n{ctx}\n")

    # 4. CORE 승격 감지
    result = await mm.maybe_promote_to_core("꼭 기억해: 다크모드는 항상 사용자 설정 우선")
    print(f"🔔 CORE 자동 승격: {'됨' if result else '안됨'}")

    final_stats = mm.stats()
    print(f"📊 최종 통계: CORE={final_stats['core']}, LOG={final_stats['log']}")

    # 테스트용 파일 정리
    mm.path.unlink(missing_ok=True)
    print("\n🧹 테스트 파일 정리 완료")
    print(f"{'─' * 54}\n")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--dynamic-demo":
        asyncio.run(run_dynamic_team_demo())
    elif len(sys.argv) > 1 and sys.argv[1] == "--planner-demo":
        asyncio.run(run_planner_demo())
    elif len(sys.argv) > 1 and sys.argv[1] == "--memory-test":
        asyncio.run(run_memory_test())
    else:
        asyncio.run(run_simulation())
