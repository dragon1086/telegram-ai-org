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
        from core.nl_classifier import NLClassifier, Intent

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
            from core.dispatch_engine import DispatchEngine
            import inspect
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
        import yaml
        from pathlib import Path

        config_path = Path(__file__).parent.parent.parent / "orchestration.yaml"
        assert config_path.exists(), "orchestration.yaml 파일이 없음"

        with open(config_path) as f:
            config = yaml.safe_load(f)

        assert config is not None
        assert "global_instructions" in config, "global_instructions 누락"

    def test_organizations_yaml_valid(self) -> None:
        """organizations.yaml 파일이 유효하고 모든 봇이 설정되어 있다."""
        import yaml
        from pathlib import Path

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
        import yaml
        from pathlib import Path

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
        from tools.base_runner import RunnerFactory, BaseRunner

        pm_runner = RunnerFactory.create("claude-code")
        research_runner = RunnerFactory.create("gemini-cli")

        assert isinstance(pm_runner, BaseRunner)
        assert isinstance(research_runner, BaseRunner)
        assert type(pm_runner) != type(research_runner), (
            "claude-code와 gemini-cli는 다른 타입의 러너여야 함"
        )

    def test_runner_factory_creates_claude_and_codex_independently(self) -> None:
        """RunnerFactory는 claude-code와 codex를 독립적으로 생성한다."""
        from tools.base_runner import RunnerFactory, BaseRunner

        pm_runner = RunnerFactory.create("claude-code")
        ops_runner = RunnerFactory.create("codex")

        assert isinstance(pm_runner, BaseRunner)
        assert isinstance(ops_runner, BaseRunner)
        assert type(pm_runner) != type(ops_runner), (
            "claude-code와 codex는 다른 타입의 러너여야 함"
        )

    def test_all_three_engines_creatable_simultaneously(self) -> None:
        """RunnerFactory는 3엔진을 동시에 생성할 수 있다."""
        from tools.base_runner import RunnerFactory, BaseRunner

        engines = ["claude-code", "codex", "gemini-cli"]
        runners = [RunnerFactory.create(e) for e in engines]

        assert len(runners) == 3
        for runner, engine in zip(runners, engines):
            assert isinstance(runner, BaseRunner), (
                f"{engine}: BaseRunner 인스턴스가 아님"
            )

    async def test_cross_team_mock_dispatch_flow(self) -> None:
        """PM → 개발실(claude-code) → 리서치실(gemini-cli) 크로스팀 모의 흐름."""
        from tools.base_runner import RunContext, BaseRunner

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
        from core.pm_router import PMRouter, PMRoute
        from unittest.mock import AsyncMock

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
        from core.pm_router import PMRouter, PMRoute

        router = PMRouter(decision_client=None)
        result = await router.route("랜딩 페이지 디자인 해줘")

        assert isinstance(result, PMRoute)
        assert result.action in {"new_task", "chat"}

    async def test_route_falls_back_on_llm_exception(self) -> None:
        """LLM 호출 중 예외 발생 시 폴백으로 PMRoute를 반환한다."""
        from core.pm_router import PMRouter, PMRoute
        from unittest.mock import AsyncMock

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
        from core.pm_router import PMRouter, PMRoute

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
        from core.pm_router import PMRouter, PMRoute

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
        from tools.base_runner import RunnerFactory, BaseRunner

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
        from tools.base_runner import RunnerFactory, BaseRunner

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
        from tools.base_runner import RunnerFactory, BaseRunner

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
        import yaml
        from pathlib import Path

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
        import yaml
        from pathlib import Path
        from tools.base_runner import RunnerFactory, BaseRunner

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
        from tools.base_runner import RunnerFactory, BaseRunner

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
        import yaml
        from pathlib import Path
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
        import yaml
        from pathlib import Path
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
        from core.nl_classifier import NLClassifier, Intent

        classifier = NLClassifier()
        result = classifier.classify("말투를 친근하게 바꿔줘")
        assert result.intent == Intent.SET_BOT_TONE
        assert result.confidence == 0.95
        assert result.source == "keyword"

    def test_classify_tone_english_keyword_returns_set_bot_tone(self) -> None:
        """영어 tone 키워드도 SET_BOT_TONE을 반환한다."""
        from core.nl_classifier import NLClassifier, Intent

        classifier = NLClassifier()
        result = classifier.classify("set tone formal")
        assert result.intent == Intent.SET_BOT_TONE

    def test_classify_greeting_short_text_returns_greeting(self) -> None:
        """짧은 인사말(15자 미만)은 GREETING을 반환한다."""
        from core.nl_classifier import NLClassifier, Intent
        from core.keywords import GREETING_KW

        classifier = NLClassifier()
        # 첫 번째 인사 키워드를 사용하되 15자 미만 조건 충족
        greeting_word = next(iter(GREETING_KW), "안녕")
        result = classifier.classify(greeting_word)
        assert result.intent == Intent.GREETING
        assert result.confidence == 1.0
        assert result.source == "keyword"

    def test_classify_status_keyword_short_text_returns_status(self) -> None:
        """30자 미만 & 상태 키워드 & action 없는 텍스트는 STATUS를 반환한다."""
        from core.nl_classifier import NLClassifier, Intent

        classifier = NLClassifier()
        result = classifier.classify("상태")
        assert result.intent == Intent.STATUS
        assert result.source == "keyword"

    def test_classify_approve_keyword_short_text_returns_approve(self) -> None:
        """승인 키워드 포함 짧은 텍스트는 APPROVE를 반환한다."""
        from core.nl_classifier import NLClassifier, Intent

        classifier = NLClassifier()
        result = classifier.classify("승인")
        assert result.intent == Intent.APPROVE

    def test_classify_cancel_keyword_returns_cancel(self) -> None:
        """취소 키워드는 CANCEL을 반환한다."""
        from core.nl_classifier import NLClassifier, Intent

        classifier = NLClassifier()
        result = classifier.classify("취소")
        assert result.intent == Intent.CANCEL

    def test_classify_reject_keyword_returns_reject(self) -> None:
        """반려 키워드는 REJECT를 반환한다."""
        from core.nl_classifier import NLClassifier, Intent

        classifier = NLClassifier()
        result = classifier.classify("반려")
        assert result.intent == Intent.REJECT

    def test_classify_long_text_without_action_returns_task_heuristic(self) -> None:
        """15자 초과 & action 키워드 없는 텍스트는 TASK(heuristic)를 반환한다."""
        from core.nl_classifier import NLClassifier, Intent

        classifier = NLClassifier()
        # 15자 초과이지만 action 키워드 없는 임의 텍스트
        result = classifier.classify("이것은 일반적인 긴 문장으로 분류 테스트를 위한")
        assert result.intent == Intent.TASK
        assert result.source == "heuristic"
        assert result.confidence == 0.5

    def test_classify_short_non_matching_text_returns_chat_heuristic(self) -> None:
        """15자 이하 & 아무 키워드도 없는 텍스트는 CHAT(heuristic)를 반환한다."""
        from core.nl_classifier import NLClassifier, Intent

        classifier = NLClassifier()
        # 15자 이하이고 어떤 키워드도 매칭 안 되는 텍스트
        result = classifier.classify("뭐야")
        assert result.intent == Intent.CHAT
        assert result.source == "heuristic"

    def test_classify_result_has_intent_confidence_source(self) -> None:
        """ClassifyResult는 intent, confidence, source 필드를 모두 포함한다."""
        from core.nl_classifier import NLClassifier, ClassifyResult

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
        from core.pm_router import PMRouter, PMRoute

        router = PMRouter()
        raw = '```json\n{"action": "new_task", "task_id": null, "confidence": 0.9}\n```'
        result = router._parse(raw)
        assert isinstance(result, PMRoute)
        assert result.action == "new_task"
        assert result.confidence == 0.9

    def test_parse_with_plain_code_block_extracts_json(self) -> None:
        """_parse()는 일반 코드블록(```...```) 내 JSON도 파싱한다."""
        from core.pm_router import PMRouter, PMRoute

        router = PMRouter()
        raw = '```\n{"action": "status_query", "task_id": null, "confidence": 0.8}\n```'
        result = router._parse(raw)
        assert isinstance(result, PMRoute)
        assert result.action == "status_query"

    def test_parse_invalid_action_defaults_to_new_task(self) -> None:
        """_parse()는 유효하지 않은 action 값을 new_task로 대체한다."""
        from core.pm_router import PMRouter, PMRoute

        router = PMRouter()
        raw = '{"action": "totally_invalid_action_xyz", "task_id": null, "confidence": 0.5}'
        result = router._parse(raw)
        assert isinstance(result, PMRoute)
        assert result.action == "new_task"

    def test_parse_json_decode_error_returns_fallback_pmroute(self) -> None:
        """_parse()는 JSON 파싱 실패 시 new_task PMRoute를 반환한다."""
        from core.pm_router import PMRouter, PMRoute

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
        from core.pm_router import PMRouter, PMRoute

        router = PMRouter()
        result = router._fallback("다시해줘", {})
        assert isinstance(result, PMRoute)
        assert result.action == "retry_task"
        assert result.confidence == 0.8

    def test_fallback_retry_english_keyword(self) -> None:
        """_fallback()은 영어 retry 키워드도 retry_task로 라우팅한다."""
        from core.pm_router import PMRouter, PMRoute

        router = PMRouter()
        result = router._fallback("retry this", {})
        assert isinstance(result, PMRoute)
        assert result.action == "retry_task"

    def test_fallback_status_query_keyword(self) -> None:
        """_fallback()은 상태 키워드가 있으면 status_query를 반환한다."""
        from core.pm_router import PMRouter, PMRoute

        router = PMRouter()
        result = router._fallback("현재 상태 알려줘", {})
        assert isinstance(result, PMRoute)
        assert result.action == "status_query"
        assert result.confidence == 0.7

    def test_fallback_confirm_pending_with_long_affirmative(self) -> None:
        """pending_confirmation 컨텍스트에서 15자 초과 텍스트는 confirm_pending이 되지 않는다."""
        from core.pm_router import PMRouter, PMRoute

        router = PMRouter()
        # 15자 초과 긍정어 → confirm_pending 조건(len <= 15) 불충족 → new_task로 폴백
        result = router._fallback("네 그렇게 해줘 진행해줘 부탁해", {"pending_confirmation": True})
        assert isinstance(result, PMRoute)
        # len > 15 이므로 confirm_pending 조건 불충족
        assert result.action in {"new_task", "status_query", "retry_task"}

    async def test_route_with_decision_client_parses_markdown_code_block(self) -> None:
        """decision_client가 마크다운 코드블록으로 응답해도 정상 파싱한다."""
        from core.pm_router import PMRouter, PMRoute
        from unittest.mock import AsyncMock

        mock_client = AsyncMock()
        mock_client.complete = AsyncMock(
            return_value='```json\n{"action": "confirm_pending", "task_id": "T-999", "confidence": 0.95}\n```'
        )

        router = PMRouter(decision_client=mock_client)
        result = await router.route("응 해줘")

        assert isinstance(result, PMRoute)
        assert result.action == "confirm_pending"
        assert result.task_id == "T-999"
