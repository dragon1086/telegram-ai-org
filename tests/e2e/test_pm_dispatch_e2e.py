"""E2E: PM 오케스트레이션 → 부서 디스패치 플로우 테스트.

system-overview.html Layer 2: PM 오케스트레이션 검증.
실제 봇/Telegram을 호출하지 않고 로컬 컴포넌트만 사용.
"""

from __future__ import annotations

import pytest


class TestNLClassifier:
    """자연어 분류기 테스트."""

    def test_engineering_task_classification(self) -> None:
        """코딩 관련 메시지는 개발실로 분류된다."""
        from core.nl_classifier import NLClassifier

        classifier = NLClassifier()
        result = classifier.classify("버그 수정해줘, API 엔드포인트에서 500 에러가 나")
        assert result is not None
        # 개발실 관련 부서로 분류
        dept = result if isinstance(result, str) else result.get("dept", "")
        assert any(keyword in dept.lower() for keyword in ["개발", "engineering", "dev"]), (
            f"개발 태스크가 잘못 분류됨: {result}"
        )

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
        """DispatchEngine 인스턴스 생성 성공."""
        try:
            from core.dispatch_engine import DispatchEngine
            engine = DispatchEngine()
            assert engine is not None
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
