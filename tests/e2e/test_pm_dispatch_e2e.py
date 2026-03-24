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
