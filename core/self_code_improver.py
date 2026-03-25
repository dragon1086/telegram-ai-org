"""코드 자가 수정 — subprocess claude → TDD 루프 → git commit/push."""
from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from loguru import logger

REPO_ROOT = Path(__file__).parent.parent
MAX_ATTEMPTS = 3


@dataclass
class FixResult:
    target: str
    success: bool
    branch: str
    commit_hash: str
    attempts: int
    error_message: str = ""


class SelfCodeImprover:
    """반복 에러 신호 → claude subprocess → TDD 루프 → git commit/push."""

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self._rate_limit_file = REPO_ROOT / "data" / "self_fix_rate.json"

    def fix(self, target: str, error_summary: str, related_files: list[str]) -> FixResult | None:
        if self.dry_run:
            logger.info(f"[SelfCodeImprover] dry_run: {target}")
            return None

        if not self._check_rate_limit(target):
            logger.warning(f"[SelfCodeImprover] rate limit 초과: {target}")
            return None

        branch = f"fix/auto-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}-{Path(target).stem}"
        self._run_git(["checkout", "-b", branch])

        prompt = self._build_prompt(target, error_summary, related_files)
        result: FixResult | None = None

        try:
            for attempt in range(1, MAX_ATTEMPTS + 1):
                logger.info(f"[SelfCodeImprover] {target} 시도 {attempt}/{MAX_ATTEMPTS}")
                if not self._run_claude(prompt):
                    continue
                passed, output = self._run_tests()
                if passed:
                    commit_hash = self._commit_and_push(branch, target, attempt)
                    self._record_rate_limit(target)
                    self._signal_restart(target)
                    result = FixResult(
                        target=target, success=True,
                        branch=branch, commit_hash=commit_hash, attempts=attempt,
                    )
                    return result
                prompt = self._build_prompt(target, error_summary, related_files, output)

            logger.error(f"[SelfCodeImprover] {target} 자동 수정 실패 — 원복")
            result = FixResult(
                target=target, success=False,
                branch=branch, commit_hash="", attempts=MAX_ATTEMPTS,
                error_message="max attempts reached",
            )
            return result
        finally:
            self._return_to_main(branch, success=result is not None and result.success)

    def _return_to_main(self, branch: str, *, success: bool) -> None:
        """작업 완료 후 main (또는 main의 HEAD)으로 복귀. 워크트리 충돌 대응."""
        try:
            self._run_git(["checkout", "main"])
        except Exception:
            # bot-runtime 워크트리가 main을 점유 중이면 detached HEAD로 복귀
            main_hash = subprocess.check_output(
                ["git", "rev-parse", "main"], cwd=REPO_ROOT, text=True,
            ).strip()
            self._run_git(["checkout", "--detach", main_hash])
            logger.info(f"[SelfCodeImprover] main 워크트리 충돌 → detached HEAD ({main_hash[:7]})")
        if not success:
            self._run_git(["branch", "-D", branch])

    def _build_prompt(
        self,
        target: str,
        error_summary: str,
        related_files: list[str],
        test_output: str = "",
    ) -> str:
        file_list = "\n".join(f"  - {f}" for f in related_files)
        feedback = f"\n\n이전 시도 실패:\n{test_output[:800]}" if test_output else ""
        return (
            f"[자가수정 태스크]\n"
            f"에러 패턴: {error_summary}\n\n"
            f"수정 지침:\n"
            f"1. 근본 원인 가설 명시\n"
            f"2. 최소 변경 원칙 (public API 유지)\n"
            f"3. 실패 재현 테스트 먼저 작성 (TDD)\n"
            f"4. pytest 전체 통과 확인\n"
            f"5. ruff check 통과\n\n"
            f"관련 파일:\n{file_list}"
            f"{feedback}"
        )

    def _run_claude(self, prompt: str) -> bool:
        try:
            result = subprocess.run(
                ["claude", "--print", "--dangerously-skip-permissions", "-p", prompt],
                cwd=str(REPO_ROOT),
                capture_output=True, text=True, timeout=300,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error(f"[SelfCodeImprover] claude 실행 실패: {e}")
            return False

    def _run_tests(self) -> tuple[bool, str]:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=short"],
            cwd=str(REPO_ROOT),
            capture_output=True, text=True, timeout=120,
        )
        return result.returncode == 0, result.stdout + result.stderr

    def _commit_and_push(self, branch: str, target: str, attempt: int) -> str:
        self._run_git(["add", "-A"])
        msg = f"fix: 자동 수정 — {target} (시도 {attempt}회)"
        self._run_git(["commit", "-m", msg])
        self._run_git(["push", "origin", branch])
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
        )
        return result.stdout.strip()

    def _signal_restart(self, target: str) -> None:
        if target.startswith("core/"):
            flag = REPO_ROOT / "data" / ".restart_requested"
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.touch()
            logger.info("[SelfCodeImprover] 재기동 플래그 생성")

    def _check_rate_limit(self, target: str) -> bool:
        data: dict = {}
        if self._rate_limit_file.exists():
            try:
                data = json.loads(self._rate_limit_file.read_text())
            except Exception:
                pass
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        recent = [t for t in data.get(target, []) if t > cutoff]
        return len(recent) < 3

    def _record_rate_limit(self, target: str) -> None:
        self._rate_limit_file.parent.mkdir(parents=True, exist_ok=True)
        data: dict = {}
        if self._rate_limit_file.exists():
            try:
                data = json.loads(self._rate_limit_file.read_text())
            except Exception:
                pass
        data.setdefault(target, []).append(datetime.now(timezone.utc).isoformat())
        self._rate_limit_file.write_text(json.dumps(data, indent=2))

    def _run_git(self, args: list[str]) -> None:
        subprocess.run(["git"] + args, cwd=str(REPO_ROOT), check=False)
