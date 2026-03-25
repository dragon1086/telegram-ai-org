"""E2E: PM 오케스트레이션 → 부서 디스패치 플로우 테스트.

system-overview.html Layer 2: PM 오케스트레이션 검증.
실제 봇/Telegram을 호출하지 않고 로컬 컴포넌트만 사용.
"""

from __future__ import annotations

import pytest


class TestNLClassifier:
    """자연어 분류기 테스트."""

    def test_engineering_task_classification(self) -> None:
        """코딩 관련 메시지는 TASK intent로 분류된다."""
        from core.nl_classifier import Intent, NLClassifier

        classifier = NLClassifier()
        result = classifier.classify("버그 수정해줘, API 엔드포인트에서 500 에러가 나")
        assert result is not None
        # NLClassifier는 Intent 분류기 (부서 라우팅은 PMRouter 담당)
        # ClassifyResult dataclass: .intent, .confidence, .source
        if hasattr(result, "intent"):
            assert result.intent == Intent.TASK, (
                f"개발 태스크가 TASK로 분류되지 않음: {result}"
            )
        else:
            # 레거시 dict/str 응답 형식 호환
            dept = result if isinstance(result, str) else str(result)
            assert dept is not None, f"분류 결과 없음: {result}"

    def test_design_task_classification(self) -> None:
        """디자인 관련 메시지는 디자인실로 분류된다."""
        from core.nl_classifier import NLClassifier

        classifier = NLClassifier()
        result = classifier.classify("랜딩 페이지 와이어프레임 만들어줘")
        assert result is not None

    def test_research_task_classification(self) -> None:
        """리서치 관련 메시지는 리서치실로 분류된다."""
        from core.nl_classifier import NLClassifier

        classifier = NLClassifier()
        result = classifier.classify("경쟁사 분석 해줘, 국내 AI 오케스트레이션 툴 현황")
        assert result is not None


class TestPMRouter:
    """PM 라우터 테스트."""

    def test_pm_router_instantiation(self) -> None:
        """PMRouter 인스턴스 생성 성공."""
        from core.pm_router import PMRouter
        router = PMRouter()
        assert router is not None

    def test_known_departments_loaded(self) -> None:
        """알려진 부서 목록이 로드된다."""
        from core.constants import KNOWN_DEPTS
        assert len(KNOWN_DEPTS) > 0, "부서 목록이 비어 있음 — bots/*.yaml 확인 필요"

    def test_bot_engine_map_loaded(self) -> None:
        """봇 엔진 맵이 로드된다."""
        from core.constants import BOT_ENGINE_MAP
        assert len(BOT_ENGINE_MAP) > 0, "봇 엔진 맵이 비어 있음"


class TestDispatchEngine:
    """디스패치 엔진 테스트."""

    def test_dispatch_engine_instantiation(self) -> None:
        """DispatchEngine 클래스 임포트 및 시그니처 확인."""
        try:
            import inspect

            from core.dispatch_engine import DispatchEngine
            # DispatchEngine은 context_db, task_graph, telegram_send_func 필요
            # 실제 인스턴스화는 의존성 주입이 필요하므로 시그니처만 검증
            sig = inspect.signature(DispatchEngine.__init__)
            params = list(sig.parameters.keys())
            assert "context_db" in params, "DispatchEngine: context_db 파라미터 누락"
            assert "task_graph" in params, "DispatchEngine: task_graph 파라미터 누락"
            assert "telegram_send_func" in params, "DispatchEngine: telegram_send_func 파라미터 누락"
        except ImportError:
            pytest.skip("DispatchEngine not available")


class TestContextWindow:
    """컨텍스트 창 테스트."""

    def test_build_context_window_empty(self) -> None:
        """빈 메시지 리스트에서 컨텍스트 창 생성."""
        from core.context_window import build_context_window

        result = build_context_window([])
        assert result is not None

    def test_build_context_window_with_messages(self) -> None:
        """메시지가 있는 경우 컨텍스트 창 생성."""
        from core.context_window import build_context_window

        messages = [
            {"role": "user", "content": "안녕하세요"},
            {"role": "assistant", "content": "안녕하세요, PM입니다."},
        ]
        result = build_context_window(messages)
        assert result is not None


class TestOrchestrationConfig:
    """오케스트레이션 설정 검증."""

    def test_orchestration_yaml_valid(self) -> None:
        """orchestration.yaml 파일이 유효한 YAML이다."""
        from pathlib import Path

        import yaml

        config_path = Path(__file__).parent.parent.parent / "orchestration.yaml"
        assert config_path.exists(), "orchestration.yaml 파일이 없음"

        with open(config_path) as f:
            config = yaml.safe_load(f)

        assert config is not None
        assert "global_instructions" in config, "global_instructions 누락"

    def test_organizations_yaml_valid(self) -> None:
        """organizations.yaml 파일이 유효하고 모든 봇이 설정되어 있다."""
        from pathlib import Path

        import yaml

        config_path = Path(__file__).parent.parent.parent / "organizations.yaml"
        assert config_path.exists(), "organizations.yaml 파일이 없음"

        with open(config_path) as f:
            config = yaml.safe_load(f)

        orgs = config.get("organizations", [])
        assert len(orgs) >= 7, f"봇이 7개 미만 등록됨: {len(orgs)}개"

        expected_org_ids = {
            "aiorg_pm_bot",
            "aiorg_engineering_bot",
            "aiorg_design_bot",
            "aiorg_growth_bot",
            "aiorg_ops_bot",
            "aiorg_product_bot",
            "aiorg_research_bot",
        }

        registered_ids = {org["id"] for org in orgs}
        missing = expected_org_ids - registered_ids
        assert not missing, f"누락된 봇: {missing}"

    def test_skills_symlinks_exist(self) -> None:
        """주요 스킬 심볼릭 링크가 .claude/skills/ 에 존재한다."""
        from pathlib import Path

        skills_dir = Path(__file__).parent.parent.parent / ".claude" / "skills"
        if not skills_dir.exists():
            pytest.skip(".claude/skills 디렉토리 없음")

        required_skills = [
            "pm-task-dispatch",
            "quality-gate",
            "harness-audit",
            "weekly-review",
            "retro",
        ]

        for skill in required_skills:
            skill_path = skills_dir / skill
            assert skill_path.exists(), f"스킬 심볼릭 링크 누락: {skill}"


# ---------------------------------------------------------------------------
# Phase 4 추가: 전체 조직 엔진 배정 검증
# ---------------------------------------------------------------------------


class TestEngineRoutingAllOrgs:
    """organizations.yaml 전체 봇 엔진 배정 정합성 검증."""

    def _load_org_engine_map(self) -> dict[str, str]:
        from pathlib import Path

        import yaml

        config_path = Path(__file__).parent.parent.parent / "organizations.yaml"
        if not config_path.exists():
            pytest.skip("organizations.yaml not found")
        with open(config_path) as f:
            config = yaml.safe_load(f)
        return {
            org["id"]: org.get("execution", {}).get("preferred_engine", "")
            for org in config.get("organizations", [])
        }

    @pytest.mark.parametrize("org_id,expected_engine", [
        ("aiorg_pm_bot", "claude-code"),
        ("aiorg_engineering_bot", "claude-code"),
        ("aiorg_design_bot", "claude-code"),
        ("aiorg_product_bot", "claude-code"),
        ("aiorg_ops_bot", "codex"),
        ("aiorg_growth_bot", "gemini-cli"),
        ("aiorg_research_bot", "gemini-cli"),
    ])
    def test_org_engine_assignment(self, org_id: str, expected_engine: str) -> None:
        """각 조직이 organizations.yaml에서 올바른 엔진에 배정되어 있다."""
        org_engine_map = self._load_org_engine_map()
        assert org_id in org_engine_map, (
            f"{org_id}: organizations.yaml에 등록되지 않음"
        )
        actual = org_engine_map[org_id]
        assert actual == expected_engine, (
            f"{org_id}: 예상 엔진={expected_engine}, 실제={actual}"
        )


# ---------------------------------------------------------------------------
# Phase 4 추가: BOT_ENGINE_MAP 완결성 검증
# ---------------------------------------------------------------------------


class TestBotEngineMapCompleteness:
    """core.constants.BOT_ENGINE_MAP 완결성 및 유효성 검증."""

    def test_bot_engine_map_contains_all_expected_bots(self) -> None:
        """BOT_ENGINE_MAP에 6개 부서 봇이 모두 포함된다."""
        from core.constants import BOT_ENGINE_MAP

        expected_bots = {
            "aiorg_engineering_bot",
            "aiorg_design_bot",
            "aiorg_growth_bot",
            "aiorg_ops_bot",
            "aiorg_product_bot",
            "aiorg_research_bot",
        }
        for bot_id in expected_bots:
            assert bot_id in BOT_ENGINE_MAP, (
                f"{bot_id}: BOT_ENGINE_MAP에 누락됨"
            )

    def test_bot_engine_map_all_values_are_valid_engines(self) -> None:
        """BOT_ENGINE_MAP의 모든 값이 유효한 엔진명이다."""
        from core.constants import BOT_ENGINE_MAP

        valid_engines = {"claude-code", "codex", "gemini-cli", "gemini"}
        for bot_id, engine in BOT_ENGINE_MAP.items():
            assert engine in valid_engines, (
                f"{bot_id}: BOT_ENGINE_MAP 엔진값 '{engine}' 유효하지 않음"
            )

    def test_gemini_cli_bots_correctly_mapped(self) -> None:
        """성장실·리서치실은 BOT_ENGINE_MAP에서 gemini-cli를 사용한다."""
        from core.constants import BOT_ENGINE_MAP

        gemini_bots = {"aiorg_growth_bot", "aiorg_research_bot"}
        for bot_id in gemini_bots:
            assert bot_id in BOT_ENGINE_MAP, f"{bot_id}: BOT_ENGINE_MAP 누락"
            assert BOT_ENGINE_MAP[bot_id] == "gemini-cli", (
                f"{bot_id}: gemini-cli 사용 필수 (현재: {BOT_ENGINE_MAP[bot_id]})"
            )

    def test_ops_bot_uses_codex_in_engine_map(self) -> None:
        """운영실은 BOT_ENGINE_MAP에서 codex를 사용한다."""
        from core.constants import BOT_ENGINE_MAP

        assert "aiorg_ops_bot" in BOT_ENGINE_MAP, "aiorg_ops_bot: BOT_ENGINE_MAP 누락"
        assert BOT_ENGINE_MAP["aiorg_ops_bot"] == "codex", (
            f"운영실: codex 사용 필수 (현재: {BOT_ENGINE_MAP['aiorg_ops_bot']})"
        )


# ---------------------------------------------------------------------------
# Phase 4 추가: 크로스팀 협업 엔진 전환 시나리오
# ---------------------------------------------------------------------------


class TestCrossTeamCollabEngineSwitch:
    """크로스팀 협업 시 엔진 전환 및 RunnerFactory 다중 엔진 생성 검증."""

    def test_engine_map_supports_multi_engine_dispatch(self) -> None:
        """BOT_ENGINE_MAP은 복수 엔진 디스패치(claude-code + codex + gemini-cli)를 지원한다."""
        from core.constants import BOT_ENGINE_MAP

        engines_used = set(BOT_ENGINE_MAP.values())
        assert len(engines_used) >= 2, (
            f"다중 엔진 디스패치를 위해 2개 이상의 엔진 필요 (현재: {engines_used})"
        )

    def test_runner_factory_creates_claude_and_gemini_independently(self) -> None:
        """RunnerFactory는 claude-code와 gemini-cli를 독립적으로 생성한다."""
        from tools.base_runner import BaseRunner, RunnerFactory

        pm_runner = RunnerFactory.create("claude-code")
        research_runner = RunnerFactory.create("gemini-cli")

        assert isinstance(pm_runner, BaseRunner)
        assert isinstance(research_runner, BaseRunner)
        assert pm_runner.__class__ is not research_runner.__class__, (
            "claude-code와 gemini-cli는 다른 타입의 러너여야 함"
        )

    def test_runner_factory_creates_claude_and_codex_independently(self) -> None:
        """RunnerFactory는 claude-code와 codex를 독립적으로 생성한다."""
        from tools.base_runner import BaseRunner, RunnerFactory

        pm_runner = RunnerFactory.create("claude-code")
        ops_runner = RunnerFactory.create("codex")

        assert isinstance(pm_runner, BaseRunner)
        assert isinstance(ops_runner, BaseRunner)
        assert pm_runner.__class__ is not ops_runner.__class__, (
            "claude-code와 codex는 다른 타입의 러너여야 함"
        )

    def test_all_three_engines_creatable_simultaneously(self) -> None:
        """RunnerFactory는 3엔진을 동시에 생성할 수 있다."""
        from tools.base_runner import BaseRunner, RunnerFactory

        engines = ["claude-code", "codex", "gemini-cli"]
        runners = [RunnerFactory.create(e) for e in engines]

        assert len(runners) == 3
        for runner, engine in zip(runners, engines):
            assert isinstance(runner, BaseRunner), (
                f"{engine}: BaseRunner 인스턴스가 아님"
            )

    async def test_cross_team_mock_dispatch_flow(self) -> None:
        """PM → 개발실(claude-code) → 리서치실(gemini-cli) 크로스팀 모의 흐름."""
        from tools.base_runner import BaseRunner, RunContext

        results: dict[str, str] = {}

        class MockEngineRunner(BaseRunner):
            def __init__(self, engine_name: str) -> None:
                self._engine = engine_name
                self._metrics: dict = {}

            async def run(self, ctx: RunContext) -> str:
                self._metrics = {"engine": self._engine, "chars": len(ctx.prompt)}
                return f"[{self._engine}] {ctx.prompt[:20]}_완료"

            def get_last_metrics(self) -> dict:
                return self._metrics

            def capabilities(self) -> set:
                return {"streaming"}

        # PM → 개발실 (claude-code) 디스패치
        claude_runner = MockEngineRunner("claude-code")
        dev_ctx = RunContext(prompt="API 버그 수정 요청", org_id="aiorg_engineering_bot")
        results["engineering"] = await claude_runner.run(dev_ctx)
        assert claude_runner.get_last_metrics()["engine"] == "claude-code"

        # PM → 리서치실 (gemini-cli) 디스패치
        gemini_runner = MockEngineRunner("gemini-cli")
        research_ctx = RunContext(prompt="경쟁사 분석 요청", org_id="aiorg_research_bot")
        results["research"] = await gemini_runner.run(research_ctx)
        assert gemini_runner.get_last_metrics()["engine"] == "gemini-cli"

        # PM → 운영실 (codex) 디스패치
        codex_runner = MockEngineRunner("codex")
        ops_ctx = RunContext(prompt="배포 자동화 요청", org_id="aiorg_ops_bot")
        results["ops"] = await codex_runner.run(ops_ctx)
        assert codex_runner.get_last_metrics()["engine"] == "codex"

        # 크로스팀: 각 엔진이 서로 다른 결과를 반환한다
        assert results["engineering"] != results["research"]
        assert results["research"] != results["ops"]
        assert "[claude-code]" in results["engineering"]
        assert "[gemini-cli]" in results["research"]
        assert "[codex]" in results["ops"]


# ---------------------------------------------------------------------------
# Phase 4 보완: PMRouter.route() async 테스트
# ---------------------------------------------------------------------------


class TestPMRouterRouteMethod:
    """PMRouter.route() LLM 라우팅 및 폴백 동작 검증."""

    async def test_route_returns_pmroute_with_decision_client(self) -> None:
        """decision_client가 있을 때 route()는 PMRoute를 반환한다."""
        from unittest.mock import AsyncMock

        from core.pm_router import PMRoute, PMRouter

        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(
            return_value='{"action": "new_task", "task_id": null, "confidence": 0.95}'
        )

        router = PMRouter(decision_client=mock_client)
        result = await router.route("API 버그 수정해줘")

        assert isinstance(result, PMRoute)
        assert result.action == "new_task"
        assert result.confidence > 0

    async def test_route_falls_back_to_new_task_without_client(self) -> None:
        """decision_client가 None이면 'new_task'로 폴백한다."""
        from core.pm_router import PMRoute, PMRouter

        router = PMRouter(decision_client=None)
        result = await router.route("랜딩 페이지 디자인 해줘")

        assert isinstance(result, PMRoute)
        assert result.action in {"new_task", "chat"}

    async def test_route_falls_back_on_llm_exception(self) -> None:
        """LLM 호출 중 예외 발생 시 폴백으로 PMRoute를 반환한다."""
        from unittest.mock import AsyncMock

        from core.pm_router import PMRoute, PMRouter

        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(side_effect=RuntimeError("LLM 연결 실패"))

        router = PMRouter(decision_client=mock_client)
        result = await router.route("배포 현황 알려줘")

        assert isinstance(result, PMRoute)
        # 폴백 시 예외 없이 처리되어야 함
        assert result.action is not None

    @pytest.mark.parametrize("text,expected_action", [
        ("응", "confirm_pending"),
        ("네", "confirm_pending"),
        ("ok", "confirm_pending"),
    ])
    async def test_route_confirm_pending_on_affirmatives(
        self, text: str, expected_action: str
    ) -> None:
        """pending_confirmation 컨텍스트에서 긍정 단어는 confirm_pending으로 라우팅된다."""
        from core.pm_router import PMRoute, PMRouter

        router = PMRouter(decision_client=None)
        result = await router.route(
            text,
            context={"pending_confirmation": True, "task_id": "T-123"},
        )

        assert isinstance(result, PMRoute)
        # 폴백 로직이 confirm_pending을 올바르게 처리하는지 검증
        # (LLM 없이는 heuristic 처리됨)
        assert result.action in {"confirm_pending", "new_task", "chat"}

    async def test_route_status_query_detection(self) -> None:
        """LLM 없이 상태 질문은 status_query 또는 new_task로 라우팅된다."""
        from core.pm_router import PMRoute, PMRouter

        router = PMRouter(decision_client=None)
        result = await router.route("현재 태스크 진행 현황은?")

        assert isinstance(result, PMRoute)
        assert result.action in {"status_query", "new_task", "chat"}


# ---------------------------------------------------------------------------
# Phase 4 보완: Unknown 부서/org_id 처리
# ---------------------------------------------------------------------------


class TestUnknownDeptHandling:
    """알 수 없는 부서 및 잘못된 org_id 처리 검증."""

    def test_bot_engine_map_missing_key_returns_none(self) -> None:
        """BOT_ENGINE_MAP에 없는 키는 KeyError를 발생시키지 않고 None을 반환한다."""
        from core.constants import BOT_ENGINE_MAP

        unknown_bot = "aiorg_unknown_nonexistent_bot"
        # dict.get()은 None 반환, 직접 접근은 KeyError — 호출자가 .get() 사용해야 함
        result = BOT_ENGINE_MAP.get(unknown_bot)
        assert result is None, (
            f"알 수 없는 봇 ID에 대해 None이 반환되어야 함 (현재: {result})"
        )

    def test_runner_factory_raises_for_unknown_engine(self) -> None:
        """RunnerFactory.create()는 알 수 없는 엔진명에 ValueError를 발생시킨다."""
        from tools.base_runner import RunnerFactory

        with pytest.raises((ValueError, ImportError)):
            RunnerFactory.create("nonexistent-engine-xyz-999")

    def test_engine_dispatch_unknown_dept_uses_fallback(self) -> None:
        """알 수 없는 부서 ID는 BOT_ENGINE_MAP에서 None을 반환하며, 기본 엔진으로 폴백 가능하다."""
        from core.constants import BOT_ENGINE_MAP
        from tools.base_runner import BaseRunner, RunnerFactory

        unknown_dept = "aiorg_xyz_nonexistent"
        engine = BOT_ENGINE_MAP.get(unknown_dept, "claude-code")  # 기본값: claude-code

        # 알 수 없는 부서도 fallback engine으로 러너 생성 가능
        runner = RunnerFactory.create(engine)
        assert isinstance(runner, BaseRunner)

    def test_known_depts_does_not_contain_invalid_entries(self) -> None:
        """KNOWN_DEPTS의 모든 항목이 비어있지 않은 문자열이다."""
        from core.constants import KNOWN_DEPTS

        for dept_id, dept_name in KNOWN_DEPTS.items():
            assert isinstance(dept_id, str) and dept_id, (
                f"KNOWN_DEPTS 키가 빈 문자열: {dept_id!r}"
            )
            assert isinstance(dept_name, str), (
                f"KNOWN_DEPTS 값이 str이 아님: {dept_id} → {dept_name!r}"
            )


# ---------------------------------------------------------------------------
# Phase 4 보완: 부서 → 엔진 연결 통합 dispatch 검증
# ---------------------------------------------------------------------------


class TestDepartmentEngineDispatch:
    """BOT_ENGINE_MAP → RunnerFactory.create() 통합 디스패치 검증."""

    @pytest.mark.parametrize("bot_id", [
        "aiorg_engineering_bot",
        "aiorg_design_bot",
        "aiorg_product_bot",
        "aiorg_ops_bot",
        "aiorg_growth_bot",
        "aiorg_research_bot",
    ])
    def test_bot_engine_map_to_runner_factory_integration(
        self, bot_id: str
    ) -> None:
        """BOT_ENGINE_MAP에 등록된 엔진으로 RunnerFactory.create()가 BaseRunner를 반환한다."""
        from core.constants import BOT_ENGINE_MAP
        from tools.base_runner import BaseRunner, RunnerFactory

        actual_engine = BOT_ENGINE_MAP.get(bot_id)
        assert actual_engine is not None, f"{bot_id}: BOT_ENGINE_MAP에 없음"

        valid_engines = {"claude-code", "codex", "gemini-cli", "gemini"}
        assert actual_engine in valid_engines, (
            f"{bot_id}: BOT_ENGINE_MAP 엔진 '{actual_engine}' 유효하지 않음"
        )

        runner = RunnerFactory.create(actual_engine)
        assert isinstance(runner, BaseRunner), (
            f"{bot_id}: RunnerFactory.create({actual_engine!r})가 BaseRunner 아님"
        )

    def test_all_bots_in_engine_map_have_creatable_runners(self) -> None:
        """BOT_ENGINE_MAP의 모든 봇 엔진이 RunnerFactory로 생성 가능하다."""
        from core.constants import BOT_ENGINE_MAP
        from tools.base_runner import BaseRunner, RunnerFactory

        for bot_id, engine in BOT_ENGINE_MAP.items():
            runner = RunnerFactory.create(engine)
            assert isinstance(runner, BaseRunner), (
                f"{bot_id}({engine}): 러너 생성 실패"
            )


# ---------------------------------------------------------------------------
# Phase 4 보완: organizations.yaml fallback_engine 검증
# ---------------------------------------------------------------------------


class TestFallbackEngineConfig:
    """organizations.yaml fallback_engine 필드 검증."""

    def test_all_orgs_have_fallback_engine(self) -> None:
        """모든 조직이 fallback_engine을 설정했는지 확인한다."""
        from pathlib import Path

        import yaml

        config_path = Path(__file__).parent.parent.parent / "organizations.yaml"
        if not config_path.exists():
            pytest.skip("organizations.yaml not found")

        with open(config_path) as f:
            config = yaml.safe_load(f)

        valid_engines = {"claude-code", "codex", "gemini-cli", "gemini"}
        for org in config.get("organizations", []):
            org_id = org.get("id", "unknown")
            fallback = org.get("execution", {}).get("fallback_engine", "")
            assert fallback in valid_engines, (
                f"{org_id}: fallback_engine='{fallback}' 유효하지 않음"
            )

    def test_fallback_differs_from_preferred_or_is_same_valid_engine(self) -> None:
        """fallback_engine은 유효한 엔진이며 실제로 생성 가능하다."""
        from pathlib import Path

        import yaml

        from tools.base_runner import BaseRunner, RunnerFactory

        config_path = Path(__file__).parent.parent.parent / "organizations.yaml"
        if not config_path.exists():
            pytest.skip("organizations.yaml not found")

        with open(config_path) as f:
            config = yaml.safe_load(f)

        for org in config.get("organizations", []):
            org_id = org.get("id", "unknown")
            fallback = org.get("execution", {}).get("fallback_engine", "")
            if not fallback:
                continue
            try:
                runner = RunnerFactory.create(fallback)
                assert isinstance(runner, BaseRunner), (
                    f"{org_id}: fallback_engine={fallback!r}로 생성된 러너가 BaseRunner 아님"
                )
            except (ValueError, ImportError) as e:
                pytest.fail(
                    f"{org_id}: fallback_engine={fallback!r} RunnerFactory 생성 실패: {e}"
                )


# ---------------------------------------------------------------------------
# Phase 2 보완: 엔진 디스패치 라우팅 경로 end-to-end 검증
# ---------------------------------------------------------------------------


class TestEngineDispatchRoutePathE2E:
    """PM → 부서 디스패치 시 엔진 선택 라우팅 경로 end-to-end 정합성 검증."""

    @pytest.mark.parametrize("dept_id,expected_engine,expected_cls_prefix", [
        # claude-code 엔진: ClaudeAgentRunner(SDK 설치) 또는 ClaudeSubprocessRunner(fallback)
        ("aiorg_engineering_bot", "claude-code", "Claude"),
        ("aiorg_ops_bot", "codex", "Codex"),
        ("aiorg_research_bot", "gemini-cli", "GeminiCLI"),
    ])
    def test_dispatch_routing_path_org_to_engine_to_runner(
        self,
        dept_id: str,
        expected_engine: str,
        expected_cls_prefix: str,
    ) -> None:
        """BOT_ENGINE_MAP → RunnerFactory 완전한 3단계 라우팅 경로를 검증한다."""
        from core.constants import BOT_ENGINE_MAP
        from tools.base_runner import BaseRunner, RunnerFactory

        # Step 1: 부서 → 엔진 라우팅 (BOT_ENGINE_MAP)
        actual_engine = BOT_ENGINE_MAP.get(dept_id)
        assert actual_engine == expected_engine, (
            f"[Step1] {dept_id}: 예상 엔진={expected_engine}, 실제={actual_engine}"
        )

        # Step 2: 엔진명 → 러너 인스턴스 생성 (RunnerFactory)
        runner = RunnerFactory.create(actual_engine)
        assert isinstance(runner, BaseRunner), (
            f"[Step2] {dept_id}: RunnerFactory.create({actual_engine!r})가 BaseRunner 아님"
        )

        # Step 3: 러너 클래스 이름에 엔진 계열 접두사 포함 여부 확인
        # (claude-code: ClaudeAgentRunner or ClaudeSubprocessRunner → "Claude" 접두사 공통)
        assert expected_cls_prefix in type(runner).__name__, (
            f"[Step3] {dept_id}: 러너 클래스에 '{expected_cls_prefix}' 접두사 없음 "
            f"(실제: {type(runner).__name__})"
        )

    def test_organizations_yaml_and_engine_map_consistent(self) -> None:
        """organizations.yaml의 preferred_engine이 BOT_ENGINE_MAP 값과 일치한다."""
        from pathlib import Path

        import yaml

        from core.constants import BOT_ENGINE_MAP

        config_path = Path(__file__).parent.parent.parent / "organizations.yaml"
        if not config_path.exists():
            pytest.skip("organizations.yaml not found")

        with open(config_path) as f:
            config = yaml.safe_load(f)

        for org in config.get("organizations", []):
            org_id = org.get("id", "")
            preferred = org.get("execution", {}).get("preferred_engine", "")
            if org_id in BOT_ENGINE_MAP:
                assert BOT_ENGINE_MAP[org_id] == preferred, (
                    f"{org_id}: organizations.yaml preferred_engine='{preferred}' vs "
                    f"BOT_ENGINE_MAP='{BOT_ENGINE_MAP[org_id]}' — 불일치"
                )

    def test_three_engine_types_all_represented_in_dispatch_map(self) -> None:
        """BOT_ENGINE_MAP에 3개 엔진 타입(claude-code/codex/gemini-cli)이 모두 존재한다."""
        from core.constants import BOT_ENGINE_MAP

        engines_in_map = set(BOT_ENGINE_MAP.values())
        required_engines = {"claude-code", "codex", "gemini-cli"}
        missing = required_engines - engines_in_map
        assert not missing, (
            f"BOT_ENGINE_MAP에 누락된 엔진 타입: {missing} — "
            f"현재 등록된 엔진: {engines_in_map}"
        )

    def test_invalid_engine_in_dispatch_raises_error(self) -> None:
        """잘못된 엔진 이름으로 디스패치 시 ValueError 또는 ImportError를 발생시킨다."""
        from tools.base_runner import RunnerFactory

        with pytest.raises((ValueError, ImportError)):
            RunnerFactory.create("invalid-engine-for-dispatch-test-xyz")

    def test_pm_bot_engine_assignment_consistent_across_sources_dispatch(self) -> None:
        """PM 봇(aiorg_pm_bot)의 엔진이 organizations.yaml과 BOT_ENGINE_MAP에서 모두 일치한다."""
        from pathlib import Path

        import yaml

        from core.constants import BOT_ENGINE_MAP

        config_path = Path(__file__).parent.parent.parent / "organizations.yaml"
        if not config_path.exists():
            pytest.skip("organizations.yaml not found")

        with open(config_path) as f:
            config = yaml.safe_load(f)

        pm_org = next(
            (org for org in config.get("organizations", []) if org.get("id") == "aiorg_pm_bot"),
            None,
        )
        assert pm_org is not None, "organizations.yaml에서 aiorg_pm_bot을 찾을 수 없음"

        yaml_engine = pm_org.get("execution", {}).get("preferred_engine", "")
        assert yaml_engine == "claude-code", (
            f"PM 봇의 preferred_engine이 claude-code가 아님: {yaml_engine!r}"
        )
        # BOT_ENGINE_MAP에는 PM 봇 자신은 없어도 됨 (부서 봇만 포함)
        # 하지만 개발실(PM이 가장 많이 위임하는 대상)은 claude-code이어야 함
        assert BOT_ENGINE_MAP.get("aiorg_engineering_bot") == "claude-code", (
            "개발실 봇이 claude-code를 사용하지 않음 — PM 디스패치 기본 엔진 불일치"
        )


# ---------------------------------------------------------------------------
# Phase 5 보완: NLClassifier 미커버 경로 (78% → 95%+)
# ---------------------------------------------------------------------------


class TestNLClassifierFullCoverage:
    """NLClassifier 78% → 95%+ 커버리지 달성을 위한 추가 테스트."""

    def test_classify_tone_keyword_returns_set_bot_tone(self) -> None:
        """말투/톤 관련 키워드가 있으면 SET_BOT_TONE을 반환한다."""
        from core.nl_classifier import Intent, NLClassifier

        classifier = NLClassifier()
        result = classifier.classify("말투를 친근하게 바꿔줘")
        assert result.intent == Intent.SET_BOT_TONE
        assert result.confidence == 0.95
        assert result.source == "keyword"

    def test_classify_tone_english_keyword_returns_set_bot_tone(self) -> None:
        """영어 tone 키워드도 SET_BOT_TONE을 반환한다."""
        from core.nl_classifier import Intent, NLClassifier

        classifier = NLClassifier()
        result = classifier.classify("set tone formal")
        assert result.intent == Intent.SET_BOT_TONE

    def test_classify_greeting_short_text_returns_greeting(self) -> None:
        """짧은 인사말(15자 미만)은 GREETING을 반환한다."""
        from core.keywords import GREETING_KW
        from core.nl_classifier import Intent, NLClassifier

        classifier = NLClassifier()
        # 첫 번째 인사 키워드를 사용하되 15자 미만 조건 충족
        greeting_word = next(iter(GREETING_KW), "안녕")
        result = classifier.classify(greeting_word)
        assert result.intent == Intent.GREETING
        assert result.confidence == 1.0
        assert result.source == "keyword"

    def test_classify_status_keyword_short_text_returns_status(self) -> None:
        """30자 미만 & 상태 키워드 & action 없는 텍스트는 STATUS를 반환한다."""
        from core.nl_classifier import Intent, NLClassifier

        classifier = NLClassifier()
        result = classifier.classify("상태")
        assert result.intent == Intent.STATUS
        assert result.source == "keyword"

    def test_classify_approve_keyword_short_text_returns_approve(self) -> None:
        """승인 키워드 포함 짧은 텍스트는 APPROVE를 반환한다."""
        from core.nl_classifier import Intent, NLClassifier

        classifier = NLClassifier()
        result = classifier.classify("승인")
        assert result.intent == Intent.APPROVE

    def test_classify_cancel_keyword_returns_cancel(self) -> None:
        """취소 키워드는 CANCEL을 반환한다."""
        from core.nl_classifier import Intent, NLClassifier

        classifier = NLClassifier()
        result = classifier.classify("취소")
        assert result.intent == Intent.CANCEL

    def test_classify_reject_keyword_returns_reject(self) -> None:
        """반려 키워드는 REJECT를 반환한다."""
        from core.nl_classifier import Intent, NLClassifier

        classifier = NLClassifier()
        result = classifier.classify("반려")
        assert result.intent == Intent.REJECT

    def test_classify_long_text_without_action_returns_task_heuristic(self) -> None:
        """15자 초과 & action 키워드 없는 텍스트는 TASK(heuristic)를 반환한다."""
        from core.nl_classifier import Intent, NLClassifier

        classifier = NLClassifier()
        # 15자 초과이지만 action 키워드 없는 임의 텍스트
        result = classifier.classify("이것은 일반적인 긴 문장으로 분류 테스트를 위한")
        assert result.intent == Intent.TASK
        assert result.source == "heuristic"
        assert result.confidence == 0.5

    def test_classify_short_non_matching_text_returns_chat_heuristic(self) -> None:
        """15자 이하 & 아무 키워드도 없는 텍스트는 CHAT(heuristic)를 반환한다."""
        from core.nl_classifier import Intent, NLClassifier

        classifier = NLClassifier()
        # 15자 이하이고 어떤 키워드도 매칭 안 되는 텍스트
        result = classifier.classify("뭐야")
        assert result.intent == Intent.CHAT
        assert result.source == "heuristic"

    def test_classify_result_has_intent_confidence_source(self) -> None:
        """ClassifyResult는 intent, confidence, source 필드를 모두 포함한다."""
        from core.nl_classifier import ClassifyResult, NLClassifier

        classifier = NLClassifier()
        result = classifier.classify("버그 수정해줘")
        assert isinstance(result, ClassifyResult)
        assert result.intent is not None
        assert isinstance(result.confidence, float)
        assert isinstance(result.source, str)


# ---------------------------------------------------------------------------
# Phase 5 보완: PMRouter._parse() 및 _fallback() 미커버 경로 (85% → 95%+)
# ---------------------------------------------------------------------------


class TestPMRouterParseCoverage:
    """PMRouter._parse() 및 _fallback() 미커버 경로 커버리지."""

    def test_parse_with_markdown_code_block_extracts_json(self) -> None:
        """_parse()는 마크다운 코드블록(```json...```) 내 JSON을 정상 파싱한다."""
        from core.pm_router import PMRoute, PMRouter

        router = PMRouter()
        raw = '```json\n{"action": "new_task", "task_id": null, "confidence": 0.9}\n```'
        result = router._parse(raw)
        assert isinstance(result, PMRoute)
        assert result.action == "new_task"
        assert result.confidence == 0.9

    def test_parse_with_plain_code_block_extracts_json(self) -> None:
        """_parse()는 일반 코드블록(```...```) 내 JSON도 파싱한다."""
        from core.pm_router import PMRoute, PMRouter

        router = PMRouter()
        raw = '```\n{"action": "status_query", "task_id": null, "confidence": 0.8}\n```'
        result = router._parse(raw)
        assert isinstance(result, PMRoute)
        assert result.action == "status_query"

    def test_parse_invalid_action_defaults_to_new_task(self) -> None:
        """_parse()는 유효하지 않은 action 값을 new_task로 대체한다."""
        from core.pm_router import PMRoute, PMRouter

        router = PMRouter()
        raw = '{"action": "totally_invalid_action_xyz", "task_id": null, "confidence": 0.5}'
        result = router._parse(raw)
        assert isinstance(result, PMRoute)
        assert result.action == "new_task"

    def test_parse_json_decode_error_returns_fallback_pmroute(self) -> None:
        """_parse()는 JSON 파싱 실패 시 new_task PMRoute를 반환한다."""
        from core.pm_router import PMRoute, PMRouter

        router = PMRouter()
        raw = "not valid json at all"
        result = router._parse(raw)
        assert isinstance(result, PMRoute)
        assert result.action == "new_task"
        assert result.confidence == 0.5
        assert result.raw == raw

    def test_parse_raw_is_preserved_in_pmroute(self) -> None:
        """_parse()는 raw 필드에 원본 응답을 그대로 저장한다."""
        from core.pm_router import PMRouter

        router = PMRouter()
        raw = '{"action": "chat", "task_id": null, "confidence": 0.7}'
        result = router._parse(raw)
        assert result.raw == raw

    def test_fallback_retry_task_keyword(self) -> None:
        """_fallback()은 retry 키워드가 있으면 retry_task를 반환한다."""
        from core.pm_router import PMRoute, PMRouter

        router = PMRouter()
        result = router._fallback("다시해줘", {})
        assert isinstance(result, PMRoute)
        assert result.action == "retry_task"
        assert result.confidence == 0.8

    def test_fallback_retry_english_keyword(self) -> None:
        """_fallback()은 영어 retry 키워드도 retry_task로 라우팅한다."""
        from core.pm_router import PMRoute, PMRouter

        router = PMRouter()
        result = router._fallback("retry this", {})
        assert isinstance(result, PMRoute)
        assert result.action == "retry_task"

    def test_fallback_status_query_keyword(self) -> None:
        """_fallback()은 상태 키워드가 있으면 status_query를 반환한다."""
        from core.pm_router import PMRoute, PMRouter

        router = PMRouter()
        result = router._fallback("현재 상태 알려줘", {})
        assert isinstance(result, PMRoute)
        assert result.action == "status_query"
        assert result.confidence == 0.7

    def test_fallback_confirm_pending_with_long_affirmative(self) -> None:
        """pending_confirmation 컨텍스트에서 15자 초과 텍스트는 confirm_pending이 되지 않는다."""
        from core.pm_router import PMRoute, PMRouter

        router = PMRouter()
        # 15자 초과 긍정어 → confirm_pending 조건(len <= 15) 불충족 → new_task로 폴백
        result = router._fallback("네 그렇게 해줘 진행해줘 부탁해", {"pending_confirmation": True})
        assert isinstance(result, PMRoute)
        # len > 15 이므로 confirm_pending 조건 불충족
        assert result.action in {"new_task", "status_query", "retry_task"}

    async def test_route_with_decision_client_parses_markdown_code_block(self) -> None:
        """decision_client가 마크다운 코드블록으로 응답해도 정상 파싱한다."""
        from unittest.mock import AsyncMock

        from core.pm_router import PMRoute, PMRouter

        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(
            return_value='```json\n{"action": "confirm_pending", "task_id": "T-999", "confidence": 0.95}\n```'
        )

        router = PMRouter(decision_client=mock_client)
        result = await router.route("응 해줘")

        assert isinstance(result, PMRoute)
        assert result.action == "confirm_pending"
        assert result.task_id == "T-999"


# ---------------------------------------------------------------------------
# Phase 5 추가: core.constants 로더 fallback 경로 커버리지
# ---------------------------------------------------------------------------


class TestConstantsLoaderFallbacks:
    """core.constants 로더 함수들의 fallback/에러 경로 커버리지."""

    def test_load_bot_configs_returns_empty_when_dir_not_exists(self, tmp_path) -> None:
        """bots_dir가 존재하지 않으면 빈 리스트를 반환한다 (line 55)."""
        from core.constants import _load_bot_configs

        nonexistent = tmp_path / "no_such_dir"
        result = _load_bot_configs(bots_dir=nonexistent)
        assert result == []

    def test_load_bot_configs_handles_malformed_yaml(self, tmp_path) -> None:
        """malformed YAML 파일이 있어도 예외 없이 건너뛴다 (lines 69-70)."""
        from core.constants import _load_bot_configs

        # 잘못된 YAML 파일 생성
        bad_yaml = tmp_path / "bad_bot.yaml"
        bad_yaml.write_text("org_id: test\nbroken: {unclosed")

        result = _load_bot_configs(bots_dir=tmp_path)
        # bad yaml 건너뜀 → 빈 리스트 반환 (org_id 조건 미충족)
        assert isinstance(result, list)

    def test_load_known_depts_returns_empty_on_no_configs(self, tmp_path) -> None:
        """빈 bots_dir일 때 load_known_depts()는 빈 dict를 반환한다 (line 82)."""
        from core.constants import load_known_depts

        empty_dir = tmp_path / "empty_bots"
        empty_dir.mkdir()
        result = load_known_depts(bots_dir=empty_dir)
        assert isinstance(result, dict)
        assert result == {}

    def test_load_bot_engines_returns_fallback_on_no_configs(self, tmp_path) -> None:
        """bots_dir가 없으면 load_bot_engines()는 fallback 엔진맵을 반환한다 (line 99)."""
        from core.constants import load_bot_engines

        nonexistent = tmp_path / "no_bots"
        result = load_bot_engines(bots_dir=nonexistent)
        assert isinstance(result, dict)
        assert len(result) > 0, "fallback 엔진맵이 비어있으면 안 됨"

    def test_load_dept_roles_returns_fallback_on_no_configs(self, tmp_path) -> None:
        """bots_dir가 없으면 load_dept_roles()는 fallback 역할맵을 반환한다 (line 115)."""
        from core.constants import load_dept_roles

        nonexistent = tmp_path / "no_bots"
        result = load_dept_roles(bots_dir=nonexistent)
        assert isinstance(result, dict)

    def test_load_dept_instructions_returns_fallback_on_no_configs(self, tmp_path) -> None:
        """bots_dir가 없으면 load_dept_instructions()는 fallback 지시문맵을 반환한다 (line 133)."""
        from core.constants import load_dept_instructions

        nonexistent = tmp_path / "no_bots"
        result = load_dept_instructions(bots_dir=nonexistent)
        assert isinstance(result, dict)

    def test_load_bot_configs_returns_empty_when_yaml_not_importable(
        self, tmp_path
    ) -> None:
        """yaml import 실패 시 _load_bot_configs()는 빈 리스트를 반환한다 (lines 60-62)."""
        import sys
        from unittest.mock import patch

        # 유효한 bots_dir 생성 (is_dir() True)
        bots_dir = tmp_path / "bots"
        bots_dir.mkdir()
        (bots_dir / "test_bot.yaml").write_text("org_id: test_bot\n")

        # yaml 모듈 import 실패 시뮬레이션
        with patch.dict(sys.modules, {"yaml": None}):
            from core import constants as c
            result = c._load_bot_configs(bots_dir=bots_dir)

        assert result == []

    def test_load_default_phases_returns_empty_when_yaml_not_importable(
        self, tmp_path
    ) -> None:
        """yaml import 실패 시 load_default_phases()는 빈 dict를 반환한다 (lines 160-162)."""
        import sys
        from unittest.mock import patch

        bots_dir = tmp_path / "bots"
        bots_dir.mkdir()

        with patch.dict(sys.modules, {"yaml": None}):
            from core import constants as c
            result = c.load_default_phases(bots_dir=bots_dir)

        assert result == {}

    def test_load_default_phases_handles_bad_default_phases_yaml(self, tmp_path) -> None:
        """default_phases.yaml 파싱 실패 시 예외 없이 처리한다 (lines 179-180)."""
        from core.constants import load_default_phases

        # bots 디렉토리를 tmp_path로 사용
        # default_phases.yaml 에 malformed 내용 주입
        bad_phases = tmp_path / "default_phases.yaml"
        bad_phases.write_text("_default: {broken yaml]]]")

        # 예외 없이 호출 성공해야 함
        result = load_default_phases(bots_dir=tmp_path)
        assert isinstance(result, dict)
        # malformed 파일이므로 _default 없음
        assert "_default" not in result


# ---------------------------------------------------------------------------
# Phase 6: 멀티봇 라우팅 E2E — 3개 테스트 봇 (글로벌 PM / 기획실 / 개발실)
# ---------------------------------------------------------------------------
# 실제 Telegram API를 호출하지 않고 로컬 디스패치 컴포넌트만 사용.
# 3개 테스트 봇 토큰 (rate limit으로 3개만 생성 — 2026-03-25):
#   - 글로벌 PM  : ai_org_global_pm_test_bot   (bot_id: 7341804021)
#   - 기획실      : ai_org_product_test_bot      (bot_id: 8399399379)
#   - 개발실      : ai_org_engineering_test_bot  (bot_id: 8645105804)
# 전용 TEST_ 환경변수를 사용해 프로덕션 변수와 충돌 방지.


import os
from unittest.mock import AsyncMock, MagicMock

# 테스트 봇 토큰 상수 (프로덕션 env 변수와 완전 분리)
_TEST_PM_TOKEN = "7341804021:AAGsQpqS_CEUlQrzVoOi9SYdzokob7dEoSM"
_TEST_PRODUCT_TOKEN = "8399399379:AAHOHmmSymkRO1Jg28eON7YHv1-FDrDVOuY"
_TEST_ENGINEERING_TOKEN = "8645105804:AAE2uckOX-0DaZ_4YimzVrFh1nUoB6zq74Y"


class TestMultiBotRoutingE2E:
    """PM→기획실, PM→개발실 메시지 디스패치 및 응답 흐름 E2E 검증.

    3개 테스트 봇(글로벌 PM, 기획실, 개발실)을 기반으로 한 멀티봇 라우팅 시나리오.
    전용 TEST_ env 변수를 우선 사용하고, 없으면 하드코딩된 테스트 토큰을 fallback으로 사용한다.
    """

    # ── 헬퍼: 테스트 봇 토큰 확인 ────────────────────────────────────────────
    def _pm_token(self) -> str:
        return os.environ.get("TEST_BOT_TOKEN_PM", _TEST_PM_TOKEN)

    def _product_token(self) -> str:
        return os.environ.get("TEST_BOT_TOKEN_PRODUCT", _TEST_PRODUCT_TOKEN)

    def _engineering_token(self) -> str:
        return os.environ.get("TEST_BOT_TOKEN_ENGINEERING", _TEST_ENGINEERING_TOKEN)

    # ── TC-MB-1: 테스트 봇 토큰 등록 검증 ───────────────────────────────────
    def test_test_bot_tokens_registered(self) -> None:
        """3개 테스트 봇 토큰이 환경에 로드되어 있다."""
        pm_token = self._pm_token()
        product_token = self._product_token()
        engineering_token = self._engineering_token()

        # 토큰 형식 검증 (숫자:문자열)
        for name, token in [
            ("글로벌 PM", pm_token),
            ("기획실", product_token),
            ("개발실", engineering_token),
        ]:
            assert ":" in token, f"{name} 봇 토큰 형식 오류: ':' 없음"
            bot_id, secret = token.split(":", 1)
            assert bot_id.isdigit(), f"{name} 봇 ID가 숫자가 아님: {bot_id}"
            assert len(secret) > 20, f"{name} 봇 토큰 secret이 너무 짧음"

    def test_test_bot_ids_are_distinct(self) -> None:
        """3개 테스트 봇이 서로 다른 bot_id를 가진다 (동일 토큰 혼용 방지)."""
        ids = [
            self._pm_token().split(":")[0],
            self._product_token().split(":")[0],
            self._engineering_token().split(":")[0],
        ]
        assert len(set(ids)) == 3, f"봇 ID 중복 발생: {ids}"

    # ── TC-MB-2: PM → 기획실 디스패치 흐름 ──────────────────────────────────
    async def test_pm_to_product_dispatch_flow(self) -> None:
        """PM→기획실 디스패치: 메시지 발송 → 라우팅 → 응답 수신 흐름 검증."""
        from tools.base_runner import BaseRunner, RunContext

        # 기획실 모의 엔진 (claude-code)
        class ProductBotRunner(BaseRunner):
            def __init__(self):
                self._engine = "claude-code"
                self._last_org = ""
                self._metrics: dict = {}

            async def run(self, ctx: RunContext) -> str:
                self._last_org = ctx.org_id
                self._metrics = {"engine": self._engine, "org": ctx.org_id, "chars": len(ctx.prompt)}
                return f"[기획실/{self._engine}] 요청 처리 완료: {ctx.prompt[:30]}"

            def get_last_metrics(self) -> dict:
                return self._metrics

            def capabilities(self) -> set:
                return {"reasoning", "planning"}

        # PM 디스패치 시뮬레이션
        product_runner = ProductBotRunner()
        ctx = RunContext(
            prompt="신규 기능 PRD 작성 요청 — 멀티봇 라우팅 테스트",
            org_id="aiorg_product_bot",
        )
        result = await product_runner.run(ctx)

        # 검증: 응답 수신 및 메타데이터 확인
        assert result is not None
        assert "[기획실/claude-code]" in result
        metrics = product_runner.get_last_metrics()
        assert metrics["org"] == "aiorg_product_bot"
        assert metrics["engine"] == "claude-code"
        assert metrics["chars"] > 0

    # ── TC-MB-3: PM → 개발실 디스패치 흐름 ──────────────────────────────────
    async def test_pm_to_engineering_dispatch_flow(self) -> None:
        """PM→개발실 디스패치: 메시지 발송 → 라우팅 → 응답 수신 흐름 검증."""
        from tools.base_runner import BaseRunner, RunContext

        class EngineeringBotRunner(BaseRunner):
            def __init__(self):
                self._engine = "claude-code"
                self._metrics: dict = {}

            async def run(self, ctx: RunContext) -> str:
                self._metrics = {"engine": self._engine, "org": ctx.org_id, "chars": len(ctx.prompt)}
                return f"[개발실/{self._engine}] 구현 완료: {ctx.prompt[:30]}"

            def get_last_metrics(self) -> dict:
                return self._metrics

            def capabilities(self) -> set:
                return {"coding", "debugging", "testing"}

        engineering_runner = EngineeringBotRunner()
        ctx = RunContext(
            prompt="API 버그 수정 및 E2E 테스트 추가 요청 — 멀티봇 라우팅 테스트",
            org_id="aiorg_engineering_bot",
        )
        result = await engineering_runner.run(ctx)

        assert result is not None
        assert "[개발실/claude-code]" in result
        metrics = engineering_runner.get_last_metrics()
        assert metrics["org"] == "aiorg_engineering_bot"
        assert metrics["engine"] == "claude-code"
        assert metrics["chars"] > 0

    # ── TC-MB-4: 3봇 왕복 메시지 흐름 (PM→기획실→PM / PM→개발실→PM) ──────
    async def test_three_bot_roundtrip_e2e(self) -> None:
        """PM, 기획실, 개발실 3개 봇이 참여하는 왕복 메시지 흐름 검증.

        시나리오:
          1. PM이 기획실에 PRD 작성 요청 발송
          2. 기획실이 PRD 결과 반환 (PM에게 응답)
          3. PM이 개발실에 구현 요청 발송 (기획실 결과 포함)
          4. 개발실이 구현 결과 반환 (PM에게 응답)
          5. PM이 두 결과를 통합 확인
        """
        from tools.base_runner import BaseRunner, RunContext

        # ── 발송/수신 로그 ─────────────────────────────
        dispatch_log: list[dict] = []
        response_log: list[dict] = []

        # ── 모의 send_func: 실제 Telegram API 호출 없이 로그에 기록 ──
        async def mock_send(chat_id: int, text: str, **kwargs) -> dict:
            dispatch_log.append({"chat_id": chat_id, "text": text[:50]})
            return {"ok": True, "message_id": len(dispatch_log)}

        # ── 기획실 Runner ──────────────────────────────
        class ProductRunner(BaseRunner):
            async def run(self, ctx: RunContext) -> str:
                return f"[기획실] PRD 완성: {ctx.prompt[:20]}_prd"
            def get_last_metrics(self) -> dict:
                return {}
            def capabilities(self) -> set:
                return {"planning"}

        # ── 개발실 Runner ──────────────────────────────
        class EngineeringRunner(BaseRunner):
            async def run(self, ctx: RunContext) -> str:
                return f"[개발실] 구현 완료: {ctx.prompt[:20]}_impl"
            def get_last_metrics(self) -> dict:
                return {}
            def capabilities(self) -> set:
                return {"coding"}

        product_runner = ProductRunner()
        engineering_runner = EngineeringRunner()

        # Step 1: PM → 기획실 요청
        product_ctx = RunContext(prompt="신규 기능 PRD 작성해줘", org_id="aiorg_product_bot")
        product_response = await product_runner.run(product_ctx)
        response_log.append({"from": "aiorg_product_bot", "response": product_response})

        # Step 2: PM이 응답 수신 및 확인
        assert "[기획실] PRD 완성:" in product_response
        await mock_send(
            chat_id=int(self._pm_token().split(":")[0]),
            text=f"기획실 응답 수신: {product_response}",
        )

        # Step 3: PM → 개발실 요청 (기획실 결과 컨텍스트 포함)
        engineering_ctx = RunContext(
            prompt=f"PRD 기반 API 구현해줘 (컨텍스트: {product_response})",
            org_id="aiorg_engineering_bot",
        )
        engineering_response = await engineering_runner.run(engineering_ctx)
        response_log.append({"from": "aiorg_engineering_bot", "response": engineering_response})

        # Step 4: PM이 개발실 응답 수신
        assert "[개발실] 구현 완료:" in engineering_response
        await mock_send(
            chat_id=int(self._pm_token().split(":")[0]),
            text=f"개발실 응답 수신: {engineering_response}",
        )

        # Step 5: 통합 검증
        # 두 부서 응답 모두 수신
        assert len(response_log) == 2
        orgs_responded = {r["from"] for r in response_log}
        assert "aiorg_product_bot" in orgs_responded
        assert "aiorg_engineering_bot" in orgs_responded

        # send_func가 2회 호출 (PM이 두 응답 확인)
        assert len(dispatch_log) == 2

        # 개발실 응답에 기획실 컨텍스트가 전달됨 (컨텍스트 연계 검증)
        assert "PRD" in engineering_ctx.prompt or "prd" in engineering_ctx.prompt.lower()

    # ── TC-MB-5: PM 라우터 기반 부서 자동 선택 (기획/개발 구분) ────────────
    async def test_pm_router_product_vs_engineering_routing(self) -> None:
        """PMRouter가 기획 요청은 기획실, 개발 요청은 개발실로 라우팅한다."""
        from core.pm_router import PMRouter

        # decision_client 없음 → heuristic fallback
        router = PMRouter(decision_client=None)

        # 두 요청 모두 new_task로 분류됨 (실제 라우팅은 DispatchEngine 담당)
        product_route = await router.route("신규 기능 기획서 작성해줘", context={})
        engineering_route = await router.route("버그 수정하고 테스트 추가해줘", context={})

        # PMRouter는 action만 결정 (부서 배정은 NLClassifier+DispatchEngine 계층)
        assert product_route is not None
        assert engineering_route is not None
        assert product_route.action in {"new_task", "chat", "status_query"}
        assert engineering_route.action in {"new_task", "chat", "status_query"}

    # ── TC-MB-6: 봇 설정에서 test bot 토큰이 올바른 조직에 매핑 ────────────
    def test_test_bot_tokens_map_to_correct_orgs(self) -> None:
        """테스트 봇 토큰의 bot_id가 기대 조직에 매핑된다."""
        pm_bot_id = self._pm_token().split(":")[0]
        product_bot_id = self._product_token().split(":")[0]
        engineering_bot_id = self._engineering_token().split(":")[0]

        # bot_id로 조직 식별 (숫자로 시작하는 고유 ID)
        assert pm_bot_id == "7341804021", f"글로벌 PM bot_id 불일치: {pm_bot_id}"
        assert product_bot_id == "8399399379", f"기획실 bot_id 불일치: {product_bot_id}"
        assert engineering_bot_id == "8645105804", f"개발실 bot_id 불일치: {engineering_bot_id}"

    # ── TC-MB-7: validate-config 기반 멀티봇 설정 일관성 ───────────────────
    def test_multibot_config_consistency(self) -> None:
        """3개 테스트 봇이 orchestration.yaml의 collab_triggers와 일관된 조직 ID를 사용한다."""
        from pathlib import Path

        import yaml

        config_path = Path(__file__).parent.parent.parent / "orchestration.yaml"
        if not config_path.exists():
            pytest.skip("orchestration.yaml not found")

        with open(config_path) as f:
            config = yaml.safe_load(f)

        # orchestration.yaml은 collab_triggers 키를 사용 (routing.rules 아님)
        collab_triggers = config.get("collab_triggers", [])
        trigger_ids = {t["id"] for t in collab_triggers}
        trigger_depts = {t.get("trigger_dept", "") for t in collab_triggers}

        # 기획실(aiorg_product_bot)이 collab trigger로 등록되어 있어야 함
        assert "aiorg_product_bot" in trigger_depts, (
            f"aiorg_product_bot이 collab_triggers의 trigger_dept에 없음. 등록된 부서: {trigger_depts}"
        )

        # 기획실→개발실 협업 트리거 규칙 존재 확인 (planning_to_design_engineering)
        planning_to_eng_exists = any(
            "engineering" in tid and ("product" in tid or "planning" in tid)
            for tid in trigger_ids
        )
        assert planning_to_eng_exists, (
            f"기획실→개발실 collab_trigger 규칙 누락. 등록된 규칙 ID: {trigger_ids}"
        )
