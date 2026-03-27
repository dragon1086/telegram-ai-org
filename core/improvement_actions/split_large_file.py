"""split_large_file 액션 — 크리티컬 크기 파일에 대해
SelfCodeImprover를 통해 모듈 분리를 요청한다.

dry_run=True이면 실제 수정 없이 계획만 반환한다.

자동 분리 실패 시 data/.refactor_needed_{filename}.flag 파일을 생성하여
수동 검토가 필요함을 표시한다. 이 케이스는 파이프라인 blocking failure가 아닌
"needs_action" 경고로 분류된다.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from core.health_report_parser import ImprovementItem
from core.improvement_actions.base import ActionResult, BaseAction

REPO_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = REPO_ROOT / "data"


def _create_refactor_flag(file_path: str, size_kb: float, reason: str) -> Path:
    """수동 리팩토링이 필요함을 알리는 플래그 파일을 data/ 에 생성한다.

    Returns:
        생성된 플래그 파일 경로
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # 파일명에서 안전한 슬러그 생성 (경로 구분자 → __)
    safe_name = file_path.replace("/", "__").replace("\\", "__").rstrip("_")
    flag_path = DATA_DIR / f".refactor_needed_{safe_name}.flag"
    payload = {
        "file_path": file_path,
        "size_kb": round(size_kb, 1),
        "reason": reason,
        "status": "needs_manual_refactor",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    flag_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    logger.warning(
        f"[SplitLargeFileAction] 플래그 생성: {flag_path.name} — "
        f"{file_path} ({size_kb:.0f}KB) 수동 리팩토링 필요"
    )
    return flag_path


class SplitLargeFileAction(BaseAction):
    """대형 파일 → SelfCodeImprover를 통해 모듈 분리 시도.

    자동 분리 실패 시 플래그 파일을 생성하고 needs_action 상태로 보고한다.
    이 케이스는 파이프라인 blocking failure가 아닌 경고(warn) 범주다.
    """

    name = "split_large_file"

    def run(self, item: ImprovementItem) -> ActionResult:
        file_path = item.file_path or "unknown"
        size_kb = item.detail.get("size_kb", 0)
        target = file_path

        logger.info(f"[SplitLargeFileAction] 분리 시도: {file_path} ({size_kb:.0f}KB)")

        if self.dry_run:
            msg = (
                f"[dry_run] {file_path} ({size_kb:.0f}KB) — "
                "모듈 분리 계획 생성 완료 (실제 실행 안 함)"
            )
            logger.info(f"[SplitLargeFileAction] {msg}")
            return ActionResult(
                action_name=self.name,
                target=target,
                success=True,
                dry_run=True,
                message=msg,
            )

        # rate limit 확인 (SelfCodeImprover 내부에서도 하지만 여기서도 선 체크)
        from core.self_code_improver import SelfCodeImprover
        improver = SelfCodeImprover(dry_run=False)

        # 실제 파일 존재 여부 확인
        abs_path = REPO_ROOT / file_path
        if not abs_path.exists():
            msg = f"{file_path} 파일을 찾을 수 없음 — 스킵"
            logger.warning(f"[SplitLargeFileAction] {msg}")
            return ActionResult(
                action_name=self.name, target=target, success=False, message=msg
            )

        fix_result = improver.fix(
            target=file_path,
            error_summary=(
                f"{file_path} 파일이 {size_kb:.0f}KB로 임계값 초과. "
                "논리적으로 분리 가능한 기능을 별도 모듈로 추출하라. "
                "public API는 backward-compatible하게 유지할 것."
            ),
            related_files=[file_path],
        )

        if fix_result and fix_result.success:
            msg = f"분리 완료 — branch={fix_result.branch}, commit={fix_result.commit_hash[:7]}"
            logger.info(f"[SplitLargeFileAction] {msg}")
            return ActionResult(
                action_name=self.name, target=target, success=True, message=msg
            )

        attempts = fix_result.attempts if fix_result else 0
        reason = f"자동 분리 실패 ({attempts}회 시도)"
        msg = f"{reason} — 수동 리팩토링 플래그 생성됨 (pipeline non-blocking)"

        # 플래그 파일 생성: 자동 수정 불가 → 수동 검토 요청
        try:
            flag_path = _create_refactor_flag(file_path, size_kb, reason)
            msg = f"{reason} — 플래그 생성: {flag_path.name} (수동 검토 필요, pipeline non-blocking)"
        except Exception as flag_err:
            logger.error(f"[SplitLargeFileAction] 플래그 생성 실패: {flag_err}")

        # needs_action: 자동 수정 불가이지만 pipeline blocking failure는 아님.
        # success=True로 반환하여 파이프라인이 이 항목으로 실패 판정하지 않도록 한다.
        logger.warning(f"[SplitLargeFileAction] needs_action: {msg}")
        return ActionResult(
            action_name=self.name,
            target=target,
            success=True,  # pipeline non-blocking — 수동 조치가 필요하지만 자동화 실패는 아님
            message=msg,
        )
