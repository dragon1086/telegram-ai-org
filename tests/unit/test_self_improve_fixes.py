"""tests/unit/test_self_improve_fixes.py — 자가개선 파이프라인 수정 단위 테스트.

다음 3가지를 커버한다:
1. file_size_critical 이슈 발생 시 SplitLargeFileAction이 플래그 파일을 생성한다
2. 자동 분리 실패 시 ActionResult.success=True (pipeline non-blocking)
3. improvement_thresholds.yaml의 pipeline_blocking 설정이 올바르게 파싱된다
4. dry_run 모드에서는 플래그 파일을 생성하지 않는다
5. 이미 파일이 없는 경우 스킵하고 success=False를 반환한다
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# 프로젝트 루트를 sys.path에 추가
REPO_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ===========================================================================
# 헬퍼: ImprovementItem 생성
# ===========================================================================

def _make_item(file_path: str = "core/large_file.py", size_kb: float = 200.0):
    """테스트용 ImprovementItem 생성."""
    from core.health_report_parser import ImprovementItem
    return ImprovementItem(
        issue_type="file_size_critical",
        file_path=file_path,
        error_pattern=None,
        severity="critical",
        detail={"size_kb": size_kb},
        priority=8,
        suggested_action=f"{file_path} 파일 분리 필요",
    )


# ===========================================================================
# 1. file_size_critical → 플래그 파일 생성 (자동 분리 실패 시)
# ===========================================================================

class TestFlagFileCreation:
    """SplitLargeFileAction 자동 분리 실패 시 플래그 파일 생성 테스트."""

    def test_creates_flag_file_when_auto_split_fails(self, tmp_path):
        """자동 분리(fix) 실패 시 data/.refactor_needed_*.flag 파일이 생성된다."""
        from core.improvement_actions.split_large_file import (
            SplitLargeFileAction,
            _create_refactor_flag,
        )

        flag_path = _create_refactor_flag(
            file_path="core/telegram_relay.py",
            size_kb=850.0,
            reason="자동 분리 실패 (3회 시도)",
        )

        # data/ 디렉토리에 flag 파일이 생성되었는지 확인
        assert flag_path.exists(), f"플래그 파일이 생성되지 않았습니다: {flag_path}"
        assert flag_path.name.startswith(".refactor_needed_"), (
            f"플래그 파일명 형식 오류: {flag_path.name}"
        )

        # 파일 내용 검증
        payload = json.loads(flag_path.read_text())
        assert payload["file_path"] == "core/telegram_relay.py"
        assert payload["size_kb"] == 850.0
        assert payload["status"] == "needs_manual_refactor"
        assert "created_at" in payload

        # 정리
        flag_path.unlink(missing_ok=True)

    def test_flag_file_content_includes_reason(self, tmp_path):
        """플래그 파일에 reason 필드가 포함된다."""
        from core.improvement_actions.split_large_file import _create_refactor_flag

        reason = "자동 분리 실패 (2회 시도)"
        flag_path = _create_refactor_flag(
            file_path="core/pm_orchestrator.py",
            size_kb=320.5,
            reason=reason,
        )

        assert flag_path.exists()
        payload = json.loads(flag_path.read_text())
        assert payload["reason"] == reason

        flag_path.unlink(missing_ok=True)

    def test_flag_filename_sanitizes_path_separators(self):
        """파일 경로의 '/'가 '__'로 변환된다."""
        from core.improvement_actions.split_large_file import _create_refactor_flag

        flag_path = _create_refactor_flag(
            file_path="core/subdir/large_module.py",
            size_kb=180.0,
            reason="테스트",
        )

        assert "__" in flag_path.name, (
            "경로 구분자가 '__'로 변환되지 않았습니다"
        )
        flag_path.unlink(missing_ok=True)


# ===========================================================================
# 2. 자동 분리 실패 시 ActionResult.success=True (pipeline non-blocking)
# ===========================================================================

class TestPipelineNonBlocking:
    """자동 분리 실패 시 파이프라인 blocking이 발생하지 않아야 한다."""

    def test_auto_split_failure_returns_success_true(self):
        """SelfCodeImprover.fix() 실패 시에도 ActionResult.success=True를 반환한다."""
        from core.improvement_actions.split_large_file import SplitLargeFileAction

        # SelfCodeImprover.fix()가 실패(success=False) 반환을 모킹
        mock_fix_result = MagicMock()
        mock_fix_result.success = False
        mock_fix_result.attempts = 3

        item = _make_item("core/telegram_relay.py", 850.0)

        with (
            patch("core.improvement_actions.split_large_file.REPO_ROOT") as mock_root,
            patch("core.self_code_improver.SelfCodeImprover") as mock_improver_cls,
        ):
            # 파일이 존재하는 것처럼 모킹
            mock_abs_path = MagicMock()
            mock_abs_path.exists.return_value = True
            mock_root.__truediv__ = MagicMock(return_value=mock_abs_path)

            mock_improver = MagicMock()
            mock_improver.fix.return_value = mock_fix_result
            mock_improver_cls.return_value = mock_improver

            action = SplitLargeFileAction(dry_run=False)

            with patch(
                "core.improvement_actions.split_large_file._create_refactor_flag"
            ) as mock_flag:
                mock_flag.return_value = Path("/tmp/.refactor_needed_test.flag")
                result = action.run(item)

        # pipeline non-blocking: success=True
        assert result.success is True, (
            "자동 분리 실패 시 pipeline non-blocking을 위해 success=True여야 합니다"
        )
        assert "non-blocking" in result.message.lower() or "플래그" in result.message, (
            "결과 메시지에 non-blocking 또는 플래그 생성 언급이 없습니다"
        )

    def test_dry_run_does_not_create_flag_file(self):
        """dry_run=True 일 때는 플래그 파일을 생성하지 않는다."""
        from core.improvement_actions.split_large_file import SplitLargeFileAction

        item = _make_item("core/large_file.py", 200.0)

        with patch(
            "core.improvement_actions.split_large_file._create_refactor_flag"
        ) as mock_flag:
            action = SplitLargeFileAction(dry_run=True)
            result = action.run(item)

        mock_flag.assert_not_called(), "dry_run 모드에서 플래그 파일이 생성되면 안 됩니다"
        assert result.success is True
        assert result.dry_run is True

    def test_nonexistent_file_returns_success_false(self):
        """파일이 존재하지 않는 경우 success=False를 반환한다 (스킵)."""
        from core.improvement_actions.split_large_file import SplitLargeFileAction

        item = _make_item("core/nonexistent_file_xyz.py", 200.0)

        # REPO_ROOT / file_path → 존재하지 않는 경로
        with patch("core.improvement_actions.split_large_file.REPO_ROOT") as mock_root:
            mock_abs_path = MagicMock()
            mock_abs_path.exists.return_value = False
            mock_root.__truediv__ = MagicMock(return_value=mock_abs_path)

            action = SplitLargeFileAction(dry_run=False)
            result = action.run(item)

        assert result.success is False
        assert "찾을 수 없음" in result.message or "스킵" in result.message


# ===========================================================================
# 3. improvement_thresholds.yaml pipeline_blocking 설정 파싱
# ===========================================================================

class TestImprovementThresholdsConfig:
    """improvement_thresholds.yaml의 pipeline_blocking 설정이 올바르게 파싱된다."""

    def test_pipeline_blocking_section_exists(self):
        """improvement_thresholds.yaml에 pipeline_blocking 섹션이 존재한다."""
        import yaml

        config_path = REPO_ROOT / "improvement_thresholds.yaml"
        assert config_path.exists(), "improvement_thresholds.yaml 파일이 없습니다"

        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}

        assert "pipeline_blocking" in cfg, (
            "improvement_thresholds.yaml에 pipeline_blocking 섹션이 없습니다"
        )

    def test_file_size_critical_is_non_blocking(self):
        """file_size_critical은 pipeline_blocking=false로 설정되어야 한다."""
        import yaml

        config_path = REPO_ROOT / "improvement_thresholds.yaml"
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}

        blocking = cfg.get("pipeline_blocking", {})
        assert blocking.get("file_size_critical") is False, (
            "file_size_critical은 pipeline non-blocking(false)이어야 합니다. "
            f"현재 값: {blocking.get('file_size_critical')}"
        )

    def test_error_pattern_is_blocking(self):
        """error_pattern은 pipeline_blocking=true로 설정되어야 한다."""
        import yaml

        config_path = REPO_ROOT / "improvement_thresholds.yaml"
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}

        blocking = cfg.get("pipeline_blocking", {})
        assert blocking.get("error_pattern") is True, (
            "error_pattern은 pipeline blocking(true)이어야 합니다. "
            f"현재 값: {blocking.get('error_pattern')}"
        )

    def test_auto_actions_still_maps_file_size_critical(self):
        """auto_actions에서 file_size_critical → split_large_file 매핑이 유지된다."""
        import yaml

        config_path = REPO_ROOT / "improvement_thresholds.yaml"
        with open(config_path) as f:
            cfg = yaml.safe_load(f) or {}

        auto_actions = cfg.get("auto_actions", {})
        assert auto_actions.get("file_size_critical") == "split_large_file", (
            "auto_actions.file_size_critical이 split_large_file이어야 합니다"
        )
