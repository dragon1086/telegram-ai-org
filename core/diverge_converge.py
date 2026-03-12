"""Diverge-Converge 프로토콜 — 동일 문제를 복수 부서에 동시 할당 후 결과 병합.

서로 다른 모델이 같은 문제를 독립적으로 풀고,
결과를 비교·병합하여 최선의 해답을 도출한다.
"""
from __future__ import annotations

from typing import Callable, Awaitable

from loguru import logger

from core.context_db import ContextDB
from core.verification import BOT_ENGINE_MAP, CrossModelVerifier


class DivergeConvergeProtocol:
    """동일 태스크를 복수 부서에 팬아웃하고 결과를 수렴하는 프로토콜."""

    def __init__(
        self,
        context_db: ContextDB,
        telegram_send_func: Callable[[int, str], Awaitable[None]],
        verifier: CrossModelVerifier | None = None,
    ):
        self._db = context_db
        self._send = telegram_send_func
        self._verifier = verifier

    async def diverge(
        self,
        parent_task_id: str,
        description: str,
        target_depts: list[str],
        created_by: str,
        chat_id: int,
    ) -> list[str]:
        """동일 태스크를 복수 부서에 병렬 발송.

        Args:
            parent_task_id: 부모 태스크 ID
            description: 태스크 설명
            target_depts: 할당할 부서 org_id 목록 (최소 2개, 서로 다른 엔진 권장)
            created_by: 생성자 org_id
            chat_id: Telegram 채팅 ID

        Returns:
            생성된 diverge 태스크 ID 목록.
        """
        if len(target_depts) < 2:
            logger.warning("[Diverge] 최소 2개 부서 필요")
            return []

        # 서로 다른 엔진이 포함되어 있는지 확인
        engines = {BOT_ENGINE_MAP.get(d, "unknown") for d in target_depts}
        if len(engines) < 2:
            logger.warning("[Diverge] 다양한 엔진 미포함 — 단일 엔진 diverge")

        task_ids: list[str] = []

        for dept in target_depts:
            engine = BOT_ENGINE_MAP.get(dept, "unknown")
            task_id = f"{parent_task_id}-dv-{dept.split('_')[1] if '_' in dept else dept}"
            await self._db.create_pm_task(
                task_id=task_id,
                description=description,
                assigned_dept=dept,
                created_by=created_by,
                parent_id=parent_task_id,
                metadata={"diverge": True, "engine": engine},
            )
            task_ids.append(task_id)

            msg = (
                f"🔀 Diverge [{task_id}]\n"
                f"[PM_TASK:{task_id}|dept:{dept}|diverge] "
                f"{description[:300]}"
            )
            await self._send(chat_id, msg)
            await self._db.update_pm_task_status(task_id, "assigned")

        logger.info(f"[Diverge] {parent_task_id} → {len(task_ids)}개 부서 팬아웃: {task_ids}")
        return task_ids

    async def check_convergence(self, diverge_task_ids: list[str]) -> bool:
        """모든 diverge 태스크가 완료되었는지 확인."""
        for tid in diverge_task_ids:
            task = await self._db.get_pm_task(tid)
            if not task or task["status"] != "done":
                return False
        return True

    async def converge(
        self,
        parent_task_id: str,
        diverge_task_ids: list[str],
        chat_id: int,
    ) -> dict:
        """diverge 태스크 결과를 수집·비교하여 병합.

        Returns:
            {"results": [...], "agreement": bool, "merged_result": str}
        """
        results: list[dict] = []
        for tid in diverge_task_ids:
            task = await self._db.get_pm_task(tid)
            if task:
                results.append({
                    "task_id": tid,
                    "dept": task["assigned_dept"],
                    "engine": BOT_ENGINE_MAP.get(task["assigned_dept"], "unknown"),
                    "result": task.get("result", ""),
                })

        # 간단한 합의 판단: 모든 결과에 공통 키워드가 있으면 합의
        all_results = [r["result"] for r in results if r["result"]]
        agreement = len(set(all_results)) == 1 if all_results else False

        if agreement:
            merged = all_results[0] if all_results else ""
            status_msg = "✅ 모든 부서 결과 일치"
        else:
            # 결과가 다르면 병합 (각 결과 나열)
            merged_parts = []
            for r in results:
                dept = r["dept"]
                engine = r["engine"]
                merged_parts.append(f"[{dept}({engine})]: {r['result'][:200]}")
            merged = "\n---\n".join(merged_parts)
            status_msg = "⚠️ 부서 간 결과 차이 — 병합 결과 참조"

        # Telegram 알림
        result_summary = "\n".join(
            f"• {r['dept']}({r['engine']}): {r['result'][:100]}"
            for r in results
        )
        msg = (
            f"🔀→🔗 Converge [{parent_task_id}]\n"
            f"{status_msg}\n\n"
            f"{result_summary}"
        )
        await self._send(chat_id, msg)

        # 부모 태스크에 병합 결과 저장
        await self._db.update_pm_task_status(
            parent_task_id, "done",
            result=merged[:2000],
        )

        logger.info(f"[Converge] {parent_task_id}: agreement={agreement}, {len(results)}개 결과")

        return {
            "results": results,
            "agreement": agreement,
            "merged_result": merged,
        }
