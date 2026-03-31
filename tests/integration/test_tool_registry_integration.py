"""통합 테스트: core/tool_registry.py — ENABLE_TOOL_REGISTRY 활성 흐름 포함.

테스트 케이스 3개:
  1. 플래그 활성 시 register → get → dispatch 전체 흐름
  2. 플래그 활성 시 tag 기반 lookup 정확도
  3. 플래그 비활성(기본값) → 활성 전환 시 registry 상태 초기화 보장
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from core.tool_registry import get_registry, reset_registry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_registry():
    """각 테스트 전후로 레지스트리 상태를 초기화한다."""
    reset_registry()
    yield
    reset_registry()


# ---------------------------------------------------------------------------
# 테스트 케이스 1: ENABLE_TOOL_REGISTRY=true 활성 흐름 — register → get → dispatch
# ---------------------------------------------------------------------------


class TestToolRegistryActiveFlow:
    """ENABLE_TOOL_REGISTRY=true 활성 상태의 전체 흐름 통합 검증."""

    def test_register_get_dispatch_full_flow(self):
        """register → get → dispatch 전 구간이 정상 동작한다 (ENABLE_TOOL_REGISTRY=true)."""
        with patch.dict(os.environ, {"ENABLE_TOOL_REGISTRY": "true"}):
            reset_registry()
            reg = get_registry()

            # register
            reg.register(
                name="sum_tool",
                description="두 수를 더한다",
                handler=lambda a, b: a + b,
                tags={"math", "compute"},
            )

            # get — ToolEntry가 반환되어야 함
            entry = reg.get("sum_tool")
            assert entry is not None, "등록된 툴을 조회할 수 있어야 한다"
            assert entry.name == "sum_tool"
            assert entry.description == "두 수를 더한다"
            assert {"math", "compute"}.issubset(entry.capability_tags)

            # dispatch — 핸들러가 실행되어야 함
            result = reg.dispatch("sum_tool", a=10, b=32)
            assert result == 42, "dispatch 결과가 핸들러 반환값과 일치해야 한다"

            # len — 1개 등록됨
            assert len(reg) == 1


# ---------------------------------------------------------------------------
# 테스트 케이스 2: ENABLE_TOOL_REGISTRY=true — tag 기반 lookup 정확도
# ---------------------------------------------------------------------------


class TestToolRegistryTagLookup:
    """ENABLE_TOOL_REGISTRY=true 상태에서 capability tag 기반 조회 정확도 검증."""

    def test_tag_based_lookup_returns_correct_tools(self):
        """get_tools_by_tag()가 매칭 태그를 가진 툴만 반환한다."""
        with patch.dict(os.environ, {"ENABLE_TOOL_REGISTRY": "true"}):
            reset_registry()
            reg = get_registry()

            reg.register("file_reader", "파일 읽기", tags={"file", "read"})
            reg.register("file_writer", "파일 쓰기", tags={"file", "write"})
            reg.register("network_fetcher", "HTTP 요청", tags={"network", "read"})

            # "file" 태그만 — file_reader + file_writer 반환
            file_tools = reg.get_tools_by_tag("file")
            file_names = {e.name for e in file_tools}
            assert "file_reader" in file_names
            assert "file_writer" in file_names
            assert "network_fetcher" not in file_names

            # "file", "read" 두 태그 모두 — file_reader만 반환
            read_file_tools = reg.get_tools_by_tag("file", "read")
            assert len(read_file_tools) == 1
            assert read_file_tools[0].name == "file_reader"

            # 존재하지 않는 태그 — 빈 리스트
            no_match = reg.get_tools_by_tag("nonexistent_tag")
            assert no_match == []

    def test_disabled_tool_excluded_from_tag_lookup(self):
        """enabled=False 툴은 tag lookup 결과에서 제외된다."""
        with patch.dict(os.environ, {"ENABLE_TOOL_REGISTRY": "true"}):
            reset_registry()
            reg = get_registry()

            reg.register("active_tool", "활성 툴", tags={"io"}, enabled=True)
            reg.register("inactive_tool", "비활성 툴", tags={"io"}, enabled=False)

            results = reg.get_tools_by_tag("io")
            names = {e.name for e in results}
            assert "active_tool" in names
            assert "inactive_tool" not in names


# ---------------------------------------------------------------------------
# 테스트 케이스 3: 플래그 off → on 전환 시 registry 상태 초기화 보장
# ---------------------------------------------------------------------------


class TestToolRegistryFlagTransition:
    """ENABLE_TOOL_REGISTRY off → on 전환 시 상태 격리 보장 검증."""

    def test_flag_off_then_on_registry_is_clean(self):
        """off 상태에서 등록 시도 후 on 전환 시 레지스트리가 빈 상태여야 한다."""
        # ① flag=off: register는 no-op
        with patch.dict(os.environ, {"ENABLE_TOOL_REGISTRY": "false"}):
            reset_registry()
            reg = get_registry()
            reg.register("ghost_tool", "등록 안 됨", handler=lambda: "ghost")
            assert len(reg) == 0, "flag=off 상태에서 register는 no-op이어야 한다"

        # ② flag=on: 이전 no-op 등록 흔적 없이 깨끗한 상태
        with patch.dict(os.environ, {"ENABLE_TOOL_REGISTRY": "true"}):
            reset_registry()
            reg = get_registry()
            assert len(reg) == 0, "flag 전환 후 reset_registry() 호출 시 비어 있어야 한다"

            # 새로 등록하면 정상 동작
            reg.register("real_tool", "실제 툴", handler=lambda: "ok")
            assert len(reg) == 1
            entry = reg.get("real_tool")
            assert entry is not None
            assert reg.dispatch("real_tool") == "ok"

    def test_flag_off_all_operations_are_noop(self):
        """ENABLE_TOOL_REGISTRY=false 시 모든 연산이 안전한 기본값을 반환한다."""
        with patch.dict(os.environ, {"ENABLE_TOOL_REGISTRY": "false"}):
            reset_registry()
            reg = get_registry()

            reg.register("tool", "desc", handler=lambda: "value")
            assert reg.get("tool") is None
            assert reg.dispatch("tool") is None
            assert reg.get_tools_by_tag("any") == []
            assert reg.list_all() == []
            assert reg.all_tags() == set()
            assert len(reg) == 0
            assert reg.unregister("tool") is False


# ---------------------------------------------------------------------------
# 테스트 케이스 4: BOT_ENGINE_MAP 연동 + R-03 회귀 방지
# ---------------------------------------------------------------------------


class TestToolRegistryBotEngineIntegration:
    """ENABLE_TOOL_REGISTRY 플래그와 BOT_ENGINE_MAP 연동 경로 통합 검증.

    R-03 회귀 방지: constants.py BOT_ENGINE_MAP vs MEMORY.md 엔진 배정 불일치.
    2026-03-26 운영실(aiorg_ops_bot) 엔진 전환: codex → gemini-cli.
    이 테스트는 코드베이스가 해당 변경을 반영하고 있음을 보장한다.
    """

    def test_bot_engine_map_ops_bot_is_gemini_cli(self):
        """R-03 회귀 방지: aiorg_ops_bot 엔진이 gemini-cli 이어야 한다.

        2026-03-26 이전 MEMORY.md에는 운영실(aiorg_ops_bot) 엔진이 'codex'로 기재되었으나
        rate limit 대응으로 gemini-cli로 전환됨. constants.py가 이를 정확히 반영해야 한다.
        """
        from core.constants import BOT_ENGINE_MAP
        assert BOT_ENGINE_MAP.get("aiorg_ops_bot") == "gemini-cli", (
            "aiorg_ops_bot 엔진은 gemini-cli이어야 함 — "
            "2026-03-26 전환 이후 codex는 운영실 엔진이 아님"
        )

    def test_bot_engine_map_all_engines_valid(self):
        """모든 봇의 엔진 배정값이 유효한 엔진 식별자여야 한다."""
        from core.constants import BOT_ENGINE_MAP
        valid_engines = {"claude-code", "gemini-cli", "codex"}
        for org_id, engine in BOT_ENGINE_MAP.items():
            assert engine in valid_engines, (
                f"{org_id}의 엔진 '{engine}'이 유효하지 않음. "
                f"허용값: {valid_engines}"
            )

    def test_flag_on_register_tools_per_bot_org(self):
        """플래그 ON: 각 봇 org_id로 툴을 등록하고 엔진별 태그 조회가 동작한다."""
        from core.constants import BOT_ENGINE_MAP

        with patch.dict(os.environ, {"ENABLE_TOOL_REGISTRY": "true"}):
            reset_registry()
            reg = get_registry()

            # 각 봇에 대해 org_id + engine 태그로 툴 등록
            for org_id, engine in BOT_ENGINE_MAP.items():
                reg.register(
                    f"{org_id}_health_check",
                    f"{org_id} 헬스체크",
                    handler=lambda oid=org_id: f"ok:{oid}",
                    tags={org_id, engine, "health"},
                )

            # 전체 등록 수 확인
            assert len(reg) == len(BOT_ENGINE_MAP)

            # gemini-cli 봇들만 조회
            gemini_tools = reg.get_tools_by_tag("gemini-cli")
            gemini_org_ids = {e.name.replace("_health_check", "") for e in gemini_tools}
            expected_gemini = {
                org_id for org_id, eng in BOT_ENGINE_MAP.items() if eng == "gemini-cli"
            }
            assert gemini_org_ids == expected_gemini, (
                "gemini-cli 엔진 봇 목록이 BOT_ENGINE_MAP과 일치해야 함"
            )

            # aiorg_ops_bot은 gemini-cli 결과에 포함되어야 함 (R-03 회귀 방지)
            assert "aiorg_ops_bot" in gemini_org_ids, (
                "aiorg_ops_bot은 gemini-cli 태그 조회에 포함되어야 함"
            )

    def test_flag_off_bot_engine_map_accessible_for_fallback(self):
        """플래그 OFF에서도 BOT_ENGINE_MAP 기반 기존 라우팅이 정상 동작한다.

        레지스트리가 비활성이어도 기존 엔진 디스패치 로직은 상시 가용해야 한다.
        """
        from core.constants import BOT_ENGINE_MAP

        with patch.dict(os.environ, {"ENABLE_TOOL_REGISTRY": "false"}):
            reset_registry()

            # 기존 라우팅: BOT_ENGINE_MAP 딕셔너리 직접 조회 (레지스트리 비의존)
            ops_engine = BOT_ENGINE_MAP.get("aiorg_ops_bot")
            eng_engine = BOT_ENGINE_MAP.get("aiorg_engineering_bot")

            assert ops_engine == "gemini-cli"
            assert eng_engine == "claude-code"

            # 레지스트리는 no-op 상태여야 함
            reg = get_registry()
            reg.register("fallback_test", "폴백 테스트", handler=lambda: None)
            assert len(reg) == 0, "플래그 OFF 상태에서 레지스트리 등록은 no-op"
