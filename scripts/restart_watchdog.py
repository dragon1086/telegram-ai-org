#!/usr/bin/env python3
"""재기동 플래그 감지 → 봇 재시작 (안전화 버전 — ST-11 Phase 2).

변경 내역 (ST-11 Phase 2):
- pre_restart_check(): 재기동 전 실행 중인 태스크 유무 + 헬스체크 엔드포인트 응답 확인
- restart_with_rollback(): 재기동 실패 시 이전 프로세스를 복구하는 fallback 분기
- 실패 원인은 로그 파일(logs/watchdog_error.log)에 기록

SelfCodeImprover가 core/ 파일을 수정하면 data/.restart_requested 플래그를 생성한다.
이 스크립트가 해당 플래그를 감지해 start_all.sh를 실행한다.

사용법:
    python scripts/restart_watchdog.py
"""
from __future__ import annotations

import json
import logging
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

# ── 상수 ────────────────────────────────────────────────────────────────────

RESTART_FLAG = Path(__file__).parent.parent / "data" / ".restart_requested"
REPO_ROOT = Path(__file__).parent.parent
START_SCRIPT = REPO_ROOT / "scripts" / "start_all.sh"
POLL_INTERVAL = 10  # seconds

# 헬스체크 URL (존재하면 응답 확인, 없으면 건너뜀)
HEALTH_CHECK_URL = "http://localhost:8080/health"

# 실행 중 태스크 마커 파일 (pm_orchestrator가 태스크 중 생성하는 플래그)
ACTIVE_TASK_FLAG = REPO_ROOT / "data" / ".active_task"

# 오류 로그 경로
ERROR_LOG = REPO_ROOT / "logs" / "watchdog_error.log"

# 재기동 타임아웃(초)
RESTART_TIMEOUT_SEC = 30

# ── 로거 설정 ────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [restart_watchdog] %(levelname)s %(message)s",
)
logger = logging.getLogger("restart_watchdog")


def _write_error_log(reason: str, detail: str = "") -> None:
    """실패 원인을 로그 파일에 기록한다."""
    try:
        ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
        with ERROR_LOG.open("a", encoding="utf-8") as f:
            entry = {
                "ts": datetime.now(UTC).isoformat(),
                "reason": reason,
                "detail": detail,
            }
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.error(f"오류 로그 기록 실패: {e}")


# ── 사전 상태 체크 ───────────────────────────────────────────────────────────

def pre_restart_check() -> tuple[bool, str]:
    """재기동 전 사전 상태 체크.

    확인 항목:
    1. 현재 실행 중인 태스크 유무 (.active_task 플래그 파일)
    2. 헬스체크 엔드포인트 응답 여부 (HEALTH_CHECK_URL)

    Returns:
        (ok: bool, reason: str) — ok=True면 재기동 진행 가능.
    """
    # 1. 실행 중 태스크 확인
    if ACTIVE_TASK_FLAG.exists():
        try:
            age_sec = time.time() - ACTIVE_TASK_FLAG.stat().st_mtime
        except OSError:
            age_sec = 0
        # 30분 이상 된 플래그는 stale로 간주하고 무시
        if age_sec < 1800:
            reason = (
                f"실행 중인 태스크 감지 ({ACTIVE_TASK_FLAG.name}, "
                f"{age_sec:.0f}초 전 생성) — 재기동 대기"
            )
            logger.warning(f"[pre_check] {reason}")
            return False, reason

    # 2. 헬스체크 엔드포인트 응답 확인
    try:
        import urllib.request
        req = urllib.request.urlopen(HEALTH_CHECK_URL, timeout=3)
        status = req.getcode()
        if status != 200:
            reason = f"헬스체크 비정상 응답: HTTP {status}"
            logger.warning(f"[pre_check] {reason}")
            # 헬스체크 실패는 경고만 (이미 죽어있을 수 있으므로 재기동은 허용)
            logger.info("[pre_check] 헬스체크 비정상이지만 재기동 진행")
    except Exception:
        # 엔드포인트가 없거나 응답 없음 → 이미 종료된 상태로 간주, 재기동 허용
        logger.debug("[pre_check] 헬스체크 응답 없음 (이미 종료된 상태로 간주)")

    return True, "ok"


# ── 재기동 + 롤백 가드 ───────────────────────────────────────────────────────

def restart_with_rollback(flag_data: dict | None = None) -> bool:
    """재기동을 시도하고 실패 시 롤백(이전 프로세스 복구)한다.

    롤백 전략:
    - start_all.sh 실패 시 → 이전 봇 프로세스를 재시도 기동 (최대 1회)
    - 이전 프로세스 PID를 저장한 data/.prev_pids 파일이 있으면 참조

    Args:
        flag_data: request_restart.sh가 남긴 JSON 데이터 (target, reason 등).

    Returns:
        True면 재기동 성공, False면 실패(롤백 시도).
    """
    reason = (flag_data or {}).get("reason", "")
    target = (flag_data or {}).get("target", "all")
    logger.info(f"[restart] 재기동 시작 — target={target}, reason={reason!r}")

    if not START_SCRIPT.exists():
        _write_error_log("start_script_missing", str(START_SCRIPT))
        logger.error(f"[restart] {START_SCRIPT} 없음 — 수동 재시작 필요")
        return False

    try:
        result = subprocess.run(
            ["bash", str(START_SCRIPT)],
            capture_output=True,
            text=True,
            timeout=RESTART_TIMEOUT_SEC,
        )
        if result.returncode == 0:
            logger.info("[restart] 재기동 성공")
            return True

        # 재기동 실패 → 롤백
        error_detail = result.stderr[:500] if result.stderr else "(no stderr)"
        _write_error_log(
            "restart_failed",
            f"returncode={result.returncode} stderr={error_detail}",
        )
        logger.error(
            f"[restart] 재기동 실패 (returncode={result.returncode}) "
            f"— 롤백 가드 실행"
        )
        _rollback()
        return False

    except subprocess.TimeoutExpired:
        _write_error_log("restart_timeout", f"{RESTART_TIMEOUT_SEC}s 초과")
        logger.error(f"[restart] 재기동 타임아웃 ({RESTART_TIMEOUT_SEC}s) — 롤백 가드 실행")
        _rollback()
        return False

    except Exception as e:
        _write_error_log("restart_exception", str(e))
        logger.error(f"[restart] 재기동 예외: {e} — 롤백 가드 실행")
        _rollback()
        return False


def _rollback() -> None:
    """롤백 가드 — 재기동 실패 시 이전 프로세스 상태로 복구를 시도한다.

    복구 전략:
    1. data/.prev_pids 파일이 있으면 기록된 PID의 프로세스가 살아있는지 확인
    2. 살아있지 않은 경우에만 start_all.sh를 한 번 더 시도 (타임아웃 완화)
    3. 모든 시도 실패 시 오류 로그만 남기고 watchdog는 계속 동작
    """
    logger.warning("[rollback] 롤백 가드 시작")
    prev_pids_file = REPO_ROOT / "data" / ".prev_pids"

    if prev_pids_file.exists():
        try:
            pids = json.loads(prev_pids_file.read_text())
            alive = []
            for pid in pids:
                try:
                    import os
                    os.kill(pid, 0)  # 프로세스 존재 확인 (signal 0)
                    alive.append(pid)
                except (ProcessLookupError, PermissionError):
                    pass
            if alive:
                logger.info(f"[rollback] 이전 프로세스 살아있음 — PIDs: {alive} → 재기동 불필요")
                return
        except Exception as e:
            logger.warning(f"[rollback] prev_pids 읽기 실패: {e}")

    # 재기동 재시도 (완화된 타임아웃)
    if START_SCRIPT.exists():
        logger.info("[rollback] start_all.sh 재시도 중...")
        try:
            result = subprocess.run(
                ["bash", str(START_SCRIPT)],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                logger.info("[rollback] 롤백 재기동 성공")
                return
            else:
                _write_error_log(
                    "rollback_failed",
                    f"returncode={result.returncode}",
                )
                logger.error(f"[rollback] 롤백 재기동도 실패 (returncode={result.returncode})")
        except Exception as e:
            _write_error_log("rollback_exception", str(e))
            logger.error(f"[rollback] 롤백 예외: {e}")
    else:
        _write_error_log("rollback_no_script", str(START_SCRIPT))
        logger.error("[rollback] start_all.sh 없음 — 수동 복구 필요")


# ── 메인 루프 ────────────────────────────────────────────────────────────────

def main() -> None:
    logger.info("시작 — 재기동 플래그 감지 대기 중")
    while True:
        if RESTART_FLAG.exists():
            # 플래그 데이터 읽기 (request_restart.sh가 남긴 JSON)
            flag_data: dict | None = None
            try:
                raw = RESTART_FLAG.read_text(encoding="utf-8").strip()
                flag_data = json.loads(raw) if raw else None
            except Exception:
                pass

            logger.info("재기동 플래그 감지")

            # ST-11 Phase 2: 사전 상태 체크
            ok, reason = pre_restart_check()
            if not ok:
                # 태스크 중 → 플래그는 남겨두고 다음 폴링에서 재시도
                logger.info(f"재기동 대기 — {reason}")
                time.sleep(POLL_INTERVAL)
                continue

            # 플래그 제거 후 재기동 (롤백 가드 포함)
            RESTART_FLAG.unlink(missing_ok=True)
            success = restart_with_rollback(flag_data)
            if success:
                logger.info("재기동 완료")
            else:
                logger.error("재기동 실패 — 롤백 처리 완료, 다음 폴링 계속")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
