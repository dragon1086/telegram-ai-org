"""교차 모델 검증 — 서로 다른 엔진의 봇이 결과물을 상호 검증.

Feature flag: ENABLE_CROSS_VERIFICATION (환경변수, 기본 off)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Literal

from loguru import logger

from core.context_db import ContextDB

ENABLE_CROSS_VERIFICATION = os.environ.get("ENABLE_CROSS_VERIFICATION", "0") == "1"

# 봇별 엔진 매핑 (yaml config에서도 확인 가능)
BOT_ENGINE_MAP: dict[str, str] = {
    "aiorg_engineering_bot": "codex",
    "aiorg_design_bot": "codex",
    "aiorg_product_bot": "claude-code",
    "aiorg_growth_bot": "claude-code",
    "aiorg_ops_bot": "claude-code",
}


@dataclass
class VerificationResult:
    """검증 결과."""
    verdict: Literal["AGREE", "DISAGREE", "PARTIAL"]
    task_id: str
    original_dept: str
    verifier_dept: str
    original_model: str
    verifier_model: str
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


class CrossModelVerifier:
    """교차 모델 검증기.

    모델 A가 생성한 결과를 모델 B가 검증하고,
    결과를 ContextDB에 저장한다.
    """

    def __init__(
        self,
        context_db: ContextDB,
        telegram_send_func: Callable[[int, str], Awaitable[None]],
    ):
        self._db = context_db
        self._send = telegram_send_func

    def select_verifier(self, original_dept: str) -> str | None:
        """원본 부서와 다른 엔진을 사용하는 검증 부서 선택.

        Returns:
            검증 부서 org_id, 또는 적합한 검증자가 없으면 None.
        """
        original_engine = BOT_ENGINE_MAP.get(original_dept)
        if not original_engine:
            return None

        candidates = [
            dept for dept, engine in BOT_ENGINE_MAP.items()
            if engine != original_engine and dept != original_dept
        ]
        if not candidates:
            return None

        # 첫 번째 후보 반환 (향후 라운드로빈 등 전략 확장 가능)
        return candidates[0]

    async def request_verification(
        self, task_id: str, chat_id: int,
    ) -> str | None:
        """태스크 결과에 대해 교차 검증을 요청.

        ContextDB에서 태스크 정보를 읽고, 다른 엔진의 부서에 검증 태스크를 생성.

        Returns:
            검증 태스크 ID, 또는 검증 불가 시 None.
        """
        task = await self._db.get_pm_task(task_id)
        if not task or task["status"] != "done":
            logger.warning(f"[Verify] 검증 불가: {task_id} (태스크 없음 또는 미완료)")
            return None

        original_dept = task["assigned_dept"]
        verifier_dept = self.select_verifier(original_dept)
        if not verifier_dept:
            logger.info(f"[Verify] {task_id}: 적합한 교차 검증자 없음")
            return None

        original_model = BOT_ENGINE_MAP.get(original_dept, "unknown")
        verifier_model = BOT_ENGINE_MAP.get(verifier_dept, "unknown")

        # ContextDB에 검증 요청 생성
        verification_id = await self._db.create_verification(
            task_id=task_id,
            original_dept=original_dept,
            verifier_dept=verifier_dept,
            original_model=original_model,
            verifier_model=verifier_model,
        )

        # 검증 태스크를 Telegram으로 발송
        result_text = task.get("result", "(결과 없음)")[:500]
        msg = (
            f"🔍 교차 검증 요청 [{verification_id}]\n"
            f"태스크: {task_id}\n"
            f"원본: {original_dept} ({original_model})\n"
            f"검증: {verifier_dept} ({verifier_model})\n\n"
            f"[PM_TASK:{task_id}|dept:{verifier_dept}|verify] "
            f"검증 요청 — 다음 결과를 검토하세요:\n{result_text}"
        )
        await self._send(chat_id, msg)
        logger.info(f"[Verify] 교차 검증 요청: {verification_id} ({original_dept} → {verifier_dept})")

        return verification_id

    async def submit_verdict(
        self,
        verification_id: str,
        verdict: Literal["AGREE", "DISAGREE", "PARTIAL"],
        issues: list[str] | None = None,
        suggestions: list[str] | None = None,
        chat_id: int | None = None,
    ) -> VerificationResult | None:
        """검증 결과 제출. ContextDB에 저장."""
        v = await self._db.get_verification(verification_id)
        if not v:
            return None

        result = VerificationResult(
            verdict=verdict,
            task_id=v["task_id"],
            original_dept=v["original_dept"],
            verifier_dept=v["verifier_dept"],
            original_model=v["original_model"],
            verifier_model=v["verifier_model"],
            issues=issues or [],
            suggestions=suggestions or [],
        )

        await self._db.update_verification(
            verification_id=verification_id,
            verdict=verdict,
            issues=result.issues,
            suggestions=result.suggestions,
        )

        # Telegram 알림
        if chat_id is not None:
            icon = {"AGREE": "✅", "DISAGREE": "❌", "PARTIAL": "⚠️"}[verdict]
            issue_text = "\n".join(f"  - {i}" for i in result.issues) if result.issues else "(없음)"
            msg = (
                f"{icon} 교차 검증 결과 [{verification_id}]\n"
                f"태스크: {result.task_id}\n"
                f"판정: {verdict}\n"
                f"이슈:\n{issue_text}"
            )
            await self._send(chat_id, msg)

        logger.info(f"[Verify] 결과: {verification_id} = {verdict}")
        return result

    def should_verify(self, task: dict) -> bool:
        """태스크가 교차 검증이 필요한지 판단.

        고위험 태스크 (코드 변경, 아키텍처 결정 등)에 대해 True.
        """
        if os.environ.get("ENABLE_CROSS_VERIFICATION", "0") != "1":
            return False

        desc = (task.get("description") or "").lower()
        high_risk_keywords = [
            "코드", "구현", "아키텍처", "보안", "인증", "결제",
            "api", "build", "deploy", "migration", "security",
        ]
        return any(kw in desc for kw in high_risk_keywords)
