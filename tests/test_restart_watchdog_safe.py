"""엔진 재기동 안전화 테스트 시나리오 — ST-11 Phase 2.

테스트 시나리오:
1. 정상 재기동 — pre_check 통과 + start_all.sh 성공 → True 반환
2. 실패→롤백    — start_all.sh 실패 → _rollback() 호출 + False 반환
추가:
3. 태스크 실행 중 pre_check 실패 — .active_task 플래그 존재 시 대기
4. 스크립트 없음 — start_all.sh 파일 없을 때 False 반환
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import tempfile
import os

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── 픽스처 ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def tmp_repo(tmp_path: Path):
    """임시 repo 구조를 만들어 반환한다."""
    (tmp_path / "data").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "scripts").mkdir()
    return tmp_path


@pytest.fixture()
def mock_env(tmp_repo: Path, monkeypatch):
    """restart_watchdog 모듈 내 경로 상수를 임시 디렉토리로 패치한다."""
    import scripts.restart_watchdog as rw

    monkeypatch.setattr(rw, "RESTART_FLAG", tmp_repo / "data" / ".restart_requested")
    monkeypatch.setattr(rw, "REPO_ROOT", tmp_repo)
    monkeypatch.setattr(rw, "START_SCRIPT", tmp_repo / "scripts" / "start_all.sh")
    monkeypatch.setattr(rw, "ACTIVE_TASK_FLAG", tmp_repo / "data" / ".active_task")
    monkeypatch.setattr(rw, "ERROR_LOG", tmp_repo / "logs" / "watchdog_error.log")
    monkeypatch.setattr(rw, "HEALTH_CHECK_URL", "http://localhost:19999/health")  # 항상 실패
    return tmp_repo


# ── 시나리오 1: 정상 재기동 ──────────────────────────────────────────────────

class TestNormalRestart:
    """정상 재기동 시나리오 — pre_check 통과 + 스크립트 실행 성공."""

    def test_pre_check_passes_when_no_active_task(self, mock_env):
        """active_task 플래그 없으면 pre_check가 True를 반환해야 한다."""
        import scripts.restart_watchdog as rw

        # active_task 플래그 없음
        assert not rw.ACTIVE_TASK_FLAG.exists()

        ok, reason = rw.pre_restart_check()

        assert ok is True
        assert reason == "ok"

    def test_restart_with_rollback_success(self, mock_env):
        """start_all.sh 성공 시 True를 반환해야 한다."""
        import scripts.restart_watchdog as rw

        # 성공하는 스크립트 생성
        rw.START_SCRIPT.write_text("#!/bin/bash\nexit 0\n")

        result = rw.restart_with_rollback({"target": "all", "reason": "테스트 재기동"})

        assert result is True
        # 오류 로그 없어야 함
        assert not rw.ERROR_LOG.exists()

    def test_full_flow_flag_to_restart(self, mock_env):
        """플래그 생성 → pre_check → 재기동 성공 전체 흐름을 검증한다."""
        import scripts.restart_watchdog as rw

        rw.START_SCRIPT.write_text("#!/bin/bash\nexit 0\n")

        # 플래그 파일 생성
        flag_data = {"target": "all", "reason": "full flow test", "requested_by": "test"}
        rw.RESTART_FLAG.write_text(json.dumps(flag_data))

        # pre_check 통과 확인
        ok, _ = rw.pre_restart_check()
        assert ok is True

        # 플래그 제거 + 재기동
        rw.RESTART_FLAG.unlink()
        result = rw.restart_with_rollback(flag_data)
        assert result is True


# ── 시나리오 2: 실패→롤백 ───────────────────────────────────────────────────

class TestFailRollback:
    """재기동 실패 → 롤백 시나리오."""

    def test_restart_fails_calls_rollback_and_returns_false(self, mock_env):
        """start_all.sh 실패 시 False 반환 + 오류 로그 기록."""
        import scripts.restart_watchdog as rw

        # 실패하는 스크립트 생성
        rw.START_SCRIPT.write_text("#!/bin/bash\nexit 1\n")

        with patch.object(rw, "_rollback") as mock_rollback:
            result = rw.restart_with_rollback({"target": "all", "reason": "실패 테스트"})

        assert result is False
        mock_rollback.assert_called_once()
        # 오류 로그가 기록됐는지 확인
        assert rw.ERROR_LOG.exists()
        log_line = rw.ERROR_LOG.read_text()
        assert "restart_failed" in log_line

    def test_restart_timeout_triggers_rollback(self, mock_env):
        """재기동 타임아웃 시 False 반환 + _rollback() 호출."""
        import scripts.restart_watchdog as rw
        import subprocess

        rw.START_SCRIPT.write_text("#!/bin/bash\nsleep 999\n")

        with patch.object(rw, "RESTART_TIMEOUT_SEC", 0):
            with patch.object(rw, "_rollback") as mock_rollback:
                with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("bash", 0)):
                    result = rw.restart_with_rollback({})

        assert result is False
        mock_rollback.assert_called_once()

    def test_rollback_writes_error_when_script_missing(self, mock_env):
        """start_all.sh 없을 때 _rollback이 오류 로그를 남겨야 한다."""
        import scripts.restart_watchdog as rw

        # 스크립트 없는 상태
        assert not rw.START_SCRIPT.exists()

        rw._rollback()

        assert rw.ERROR_LOG.exists()
        log_line = rw.ERROR_LOG.read_text()
        assert "rollback" in log_line


# ── 시나리오 3: 태스크 실행 중 pre_check 실패 ───────────────────────────────

class TestPreCheckActiveTask:
    """실행 중인 태스크 감지 시 pre_check가 False를 반환해야 한다."""

    def test_active_task_flag_blocks_restart(self, mock_env):
        """active_task 플래그가 있으면 (최근 생성) pre_check가 False를 반환해야 한다."""
        import scripts.restart_watchdog as rw

        # active_task 플래그 생성 (방금 생성 = 현재 실행 중)
        rw.ACTIVE_TASK_FLAG.write_text("running")

        ok, reason = rw.pre_restart_check()

        assert ok is False
        assert "태스크" in reason or "active_task" in reason.lower() or "실행" in reason

    def test_stale_active_task_flag_ignored(self, mock_env):
        """30분 이상 된 active_task 플래그는 stale로 간주하고 pre_check가 True를 반환해야 한다."""
        import scripts.restart_watchdog as rw

        # active_task 플래그 생성 후 mtime을 31분 전으로 조작
        rw.ACTIVE_TASK_FLAG.write_text("stale_task")
        stale_mtime = time.time() - 1860  # 31분 전
        os.utime(rw.ACTIVE_TASK_FLAG, (stale_mtime, stale_mtime))

        ok, reason = rw.pre_restart_check()

        assert ok is True


# ── 시나리오 4: 스크립트 없음 ────────────────────────────────────────────────

class TestMissingScript:
    """start_all.sh 파일이 없을 때 False를 반환해야 한다."""

    def test_restart_returns_false_when_no_script(self, mock_env):
        import scripts.restart_watchdog as rw

        assert not rw.START_SCRIPT.exists()

        result = rw.restart_with_rollback({})

        assert result is False
        assert rw.ERROR_LOG.exists()
        log_line = rw.ERROR_LOG.read_text()
        assert "start_script_missing" in log_line
