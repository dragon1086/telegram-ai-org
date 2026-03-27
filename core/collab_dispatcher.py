"""ST-11 COLLAB 위임 디스패처 — task_type == COLLAB 시 관련 부서로 분기 전달.

허브-앤-스포크 안티패턴을 완화하기 위해, COLLAB 태그가 붙은 태스크를
PM 단독 경유 없이 직접 대상 부서 에이전트로 dispatch한다.

사용 예:
    dispatcher = CollabDispatcher(send_func=telegram_relay.send_text)
    result = await dispatcher.dispatch(task_id="T-123", task_text="...",
                                       source_dept="aiorg_engineering_bot",
                                       target_depts=["aiorg_design_bot"])
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Awaitable, Callable, Literal

from loguru import logger

# COLLAB 태그 파싱 정규식 (양식: [COLLAB:작업 설명|맥락: 요약])
_COLLAB_TAG_RE = re.compile(
    r"\[COLLAB:(?P<task>[^|\]]+?)(?:\|맥락:\s*(?P<context>[^\]]+))?\]",
    re.DOTALL,
)

# 부서별 채팅 ID 환경 변수 키 (telegram_relay와 동일한 네이밍 규칙)
_DEPT_CHAT_ID_ENV: dict[str, str] = {
    "aiorg_engineering_bot": "ENGINEERING_BOT_CHAT_ID",
    "aiorg_design_bot":      "DESIGN_BOT_CHAT_ID",
    "aiorg_product_bot":     "PRODUCT_BOT_CHAT_ID",
    "aiorg_growth_bot":      "GROWTH_BOT_CHAT_ID",
    "aiorg_ops_bot":         "OPS_BOT_CHAT_ID",
    "aiorg_research_bot":    "RESEARCH_BOT_CHAT_ID",
}

# 사람이 읽기 좋은 부서 이름
_DEPT_NAMES: dict[str, str] = {
    "aiorg_engineering_bot": "🔧 개발실",
    "aiorg_design_bot":      "🎨 디자인실",
    "aiorg_product_bot":     "📋 기획실",
    "aiorg_growth_bot":      "📈 성장실",
    "aiorg_ops_bot":         "⚙️ 운영실",
    "aiorg_research_bot":    "🔍 리서치실",
}

_DISPATCH_LOG_PATH = Path(__file__).resolve().parent.parent / "logs" / "collab_dispatch.jsonl"

# 동일 task_id + target_dept 조합의 최대 dispatch 횟수 (무한루프 방지)
_MAX_DISPATCH_PER_TARGET = 3

# chat_id 조회 실패 시 재시도 설정
_RETRY_MAX = 2
_RETRY_DELAY = 0.5  # seconds

# 실패 유형 리터럴 타입
_FailureType = Literal["permanent", "transient"]


def _count_previous_dispatches(task_id: str, target_dept: str) -> int:
    """collab_dispatch.jsonl에서 동일 task_id + target_dept 의 dispatched 횟수를 반환한다."""
    if not _DISPATCH_LOG_PATH.exists():
        return 0
    count = 0
    try:
        with _DISPATCH_LOG_PATH.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    entry = json.loads(line)
                    if (
                        entry.get("task_id") == task_id
                        and entry.get("target_dept") == target_dept
                        and entry.get("status") == "dispatched"
                    ):
                        count += 1
                except json.JSONDecodeError:
                    continue
    except OSError:
        return 0
    return count


def _append_dispatch_event(
    *,
    status: str,
    task_id: str,
    source_dept: str,
    target_dept: str = "",
    context: str = "",
    detail: str = "",
    failure_type: str = "",
) -> None:
    """COLLAB 전달 이력을 JSONL로 남긴다."""
    payload: dict[str, str] = {
        "ts": datetime.now(UTC).isoformat(),
        "status": status,
        "task_id": task_id,
        "source_dept": source_dept,
        "target_dept": target_dept,
        "context": context[:300],
        "detail": detail[:400],
    }
    if failure_type:
        payload["failure_type"] = failure_type
    _DISPATCH_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _DISPATCH_LOG_PATH.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, ensure_ascii=False) + "\n")


def parse_collab_tags(text: str) -> list[dict[str, str]]:
    """텍스트에서 [COLLAB:...] 태그를 모두 추출한다.

    Returns:
        [{"task": "...", "context": "..."}, ...] 리스트.
        태그가 없으면 빈 리스트.
    """
    results: list[dict[str, str]] = []
    for m in _COLLAB_TAG_RE.finditer(text):
        results.append({
            "task": m.group("task").strip(),
            "context": (m.group("context") or "").strip(),
        })
    return results


def resolve_target_depts(
    task_text: str,
    explicit_targets: list[str] | None = None,
) -> list[str]:
    """COLLAB 대상 부서를 결정한다.

    우선순위:
    1. explicit_targets 가 명시된 경우 → 그대로 사용
    2. 태스크 텍스트에 @mention 형태(예: @aiorg_design_bot)가 있으면 추출
    3. 위 두 가지 모두 없으면 전체 알려진 부서 반환
    """
    if explicit_targets:
        return [d for d in explicit_targets if d in _DEPT_CHAT_ID_ENV]

    mentioned: list[str] = []
    for dept_id in _DEPT_CHAT_ID_ENV:
        if dept_id in task_text or dept_id.replace("_bot", "") in task_text:
            mentioned.append(dept_id)
    if mentioned:
        return mentioned

    return list(_DEPT_CHAT_ID_ENV.keys())


class CollabDispatcher:
    """COLLAB 태스크를 대상 부서로 직접 분기 전달하는 디스패처.

    Args:
        send_func: (chat_id: int, text: str) → Awaitable[None] 시그니처의 전송 함수.
                   chat_id 없이 텍스트만 받는 경우 chat_id_resolver도 함께 제공.
        chat_id_resolver: dept_id → chat_id 매핑 함수. 없으면 환경변수에서 조회.
        admin_chat_id: fallback 알림을 수신할 관리자 채팅방 ID.
                       지정 시 일시적 실패 재시도 소진 후 관리자에게 알림 전송.
    """

    def __init__(
        self,
        send_func: Callable[[int, str], Awaitable[None]],
        chat_id_resolver: Callable[[str], int | None] | None = None,
        admin_chat_id: int | None = None,
    ) -> None:
        self._send = send_func
        self._resolver = chat_id_resolver or self._env_chat_id_resolver
        self._admin_chat_id = admin_chat_id

    @staticmethod
    def _env_chat_id_resolver(dept_id: str) -> int | None:
        """환경 변수에서 dept_id에 대응하는 chat_id를 조회한다."""
        env_key = _DEPT_CHAT_ID_ENV.get(dept_id)
        if not env_key:
            return None
        val = os.environ.get(env_key)
        if val is None:
            return None
        try:
            return int(val)
        except ValueError:
            logger.warning(f"[CollabDispatcher] {env_key}={val!r} — int 변환 실패")
            return None

    @staticmethod
    def _classify_env_failure(dept_id: str) -> tuple[_FailureType, str]:
        """환경변수 기반 chat_id 조회 실패 원인을 분류한다.

        Returns:
            (failure_type, reason) — "permanent" (재시도 불필요) 또는 "transient" (재시도 가능)
        """
        env_key = _DEPT_CHAT_ID_ENV.get(dept_id)
        if not env_key:
            return "permanent", (
                f"dept_id={dept_id!r} 는 알 수 없는 부서 — "
                f"_DEPT_CHAT_ID_ENV 매핑 없음 (등록되지 않은 조직 ID)"
            )
        val = os.environ.get(env_key)
        if val is None:
            return "permanent", (
                f"환경변수 {env_key} 미설정 — "
                f".env 또는 배포 환경에 {env_key}=<chat_id> 추가 필요"
            )
        return "permanent", (
            f"환경변수 {env_key}={val!r} — 정수 변환 불가 (유효한 Telegram chat_id가 아님)"
        )

    async def _resolve_with_retry(
        self, dept_id: str
    ) -> tuple[int | None, _FailureType | None, str]:
        """chat_id를 조회하고, 일시적 실패 시 최대 _RETRY_MAX 회 재시도한다.

        실패 유형 분류:
        - permanent: resolver가 None 반환 (환경변수 미설정, 부서 미등록 등)
                     — 재시도해도 회복되지 않으므로 즉시 포기
        - transient: resolver가 Exception 발생 (네트워크 오류, API 타임아웃 등)
                     — 재시도 후 회복 가능, 소진 시 fallback

        Returns:
            (chat_id, failure_type, reason)
            - chat_id가 None인 경우 failure_type·reason에 상세 원인 포함
        """
        last_exc: Exception | None = None

        # 1차 시도
        try:
            chat_id = self._resolver(dept_id)
        except Exception as e:
            last_exc = e
            chat_id = None

        if chat_id is not None:
            return chat_id, None, ""

        # resolver가 None 반환(예외 없음) → 환경 설정 문제 → 영구적 실패
        if last_exc is None:
            if self._resolver is self._env_chat_id_resolver:
                failure_type, reason = self._classify_env_failure(dept_id)
            else:
                env_key = _DEPT_CHAT_ID_ENV.get(dept_id, "N/A")
                reason = (
                    f"커스텀 resolver가 None 반환 "
                    f"(dept_id={dept_id!r}, env_key={env_key})"
                )
                failure_type = "permanent"
            return None, failure_type, reason

        # resolver가 Exception 발생 → 일시적 실패 → retry
        logger.warning(
            f"[CollabDispatcher] {dept_id} chat_id 1차 조회 실패 (일시적) — "
            f"재시도 최대 {_RETRY_MAX}회 시작. 오류: {last_exc}"
        )
        for attempt in range(1, _RETRY_MAX + 1):
            await asyncio.sleep(_RETRY_DELAY)
            try:
                chat_id = self._resolver(dept_id)
                if chat_id is not None:
                    logger.info(
                        f"[CollabDispatcher] {dept_id} chat_id 재시도 {attempt}/{_RETRY_MAX} 성공"
                    )
                    return chat_id, None, ""
                # retry 중 None 반환 → 이제 영구적으로 전환
                if self._resolver is self._env_chat_id_resolver:
                    failure_type, reason = self._classify_env_failure(dept_id)
                else:
                    reason = f"재시도 {attempt}회 중 resolver가 None 반환 (dept_id={dept_id!r})"
                    failure_type = "permanent"
                return None, failure_type, reason
            except Exception as e:
                last_exc = e
                logger.warning(
                    f"[CollabDispatcher] {dept_id} chat_id 재시도 {attempt}/{_RETRY_MAX} 실패: {e}"
                )

        reason = (
            f"재시도 {_RETRY_MAX}회 모두 소진 — "
            f"dept_id={dept_id!r}, "
            f"마지막 오류: {last_exc}"
        )
        return None, "transient", reason

    async def dispatch(
        self,
        task_id: str,
        task_text: str,
        source_dept: str,
        target_depts: list[str] | None = None,
        context: str = "",
    ) -> list[str]:
        """COLLAB 태스크를 대상 부서로 분기 전달한다.

        Args:
            task_id: 원본 태스크 ID (추적용).
            task_text: 전달할 태스크 본문 (COLLAB 태그 포함 가능).
            source_dept: 요청 발신 부서 org_id.
            target_depts: 명시적 수신 부서 목록. None이면 자동 추론.
            context: 추가 맥락 문자열.

        Returns:
            실제로 메시지가 전달된 부서 org_id 목록.
        """
        targets = resolve_target_depts(task_text, target_depts)
        if not targets:
            logger.warning(f"[CollabDispatcher] {task_id} — 대상 부서 없음, dispatch 취소")
            _append_dispatch_event(
                status="no_targets",
                task_id=task_id,
                source_dept=source_dept,
                context=context,
                detail=task_text,
            )
            return []

        source_name = _DEPT_NAMES.get(source_dept, source_dept)
        dispatched: list[str] = []

        # ContextDB에 COLLAB pm_task 레코드 생성 (추적 및 재시작 내성 확보)
        try:
            from core.context_db import ContextDB
            _ctx_db = ContextDB()
            await _ctx_db.create_pm_task(
                task_id=task_id,
                description=task_text[:500],
                assigned_dept=",".join(t for t in targets if t != source_dept) or source_dept,
                created_by=source_dept,
                metadata={
                    "collab": True,
                    "collab_requester": source_dept,
                    "collab_targets": targets,
                    "collab_context": context[:300],
                },
            )
        except Exception as _ctx_err:
            logger.warning(f"[CollabDispatcher] ContextDB pm_task 생성 실패 (무시): {_ctx_err}")

        for dept_id in targets:
            if dept_id == source_dept:
                # 자기 자신에게는 보내지 않는다
                continue

            # 동일 task_id + target_dept 이미 최대 횟수 dispatch됐으면 skip (무한루프 방지)
            prev_count = _count_previous_dispatches(task_id, dept_id)
            if prev_count >= _MAX_DISPATCH_PER_TARGET:
                logger.warning(
                    f"[CollabDispatcher] {task_id} → {dept_id} 이미 {prev_count}회 dispatch — "
                    f"최대({_MAX_DISPATCH_PER_TARGET}회) 초과, skip"
                )
                _append_dispatch_event(
                    status="skipped_max_retry",
                    task_id=task_id,
                    source_dept=source_dept,
                    target_dept=dept_id,
                    context=context,
                    detail=f"max_retry={_MAX_DISPATCH_PER_TARGET} 초과 (prev={prev_count})",
                )
                continue

            # ── chat_id 조회 (재시도 + 원인 분류 포함) ──────────────────────
            chat_id, failure_type, failure_reason = await self._resolve_with_retry(dept_id)
            if chat_id is None:
                env_key = _DEPT_CHAT_ID_ENV.get(dept_id, "N/A")
                logger.warning(
                    f"[CollabDispatcher] {dept_id} chat_id 조회 실패 — "
                    f"failure_type={failure_type}, env_key={env_key}, "
                    f"reason={failure_reason}"
                )
                # 원인 유형별 세분화 status: skipped_no_chat_id_permanent / skipped_no_chat_id_transient
                status = f"skipped_no_chat_id_{failure_type}"
                _append_dispatch_event(
                    status=status,
                    task_id=task_id,
                    source_dept=source_dept,
                    target_dept=dept_id,
                    context=context,
                    detail=failure_reason,
                    failure_type=failure_type or "",
                )

                # fallback: 일시적 실패(재시도 소진) 시 관리자 채널 알림
                if failure_type == "transient" and self._admin_chat_id:
                    try:
                        await self._send(
                            self._admin_chat_id,
                            (
                                f"[COLLAB_DISPATCH_ALERT] {task_id} → {dept_id} "
                                f"chat_id 일시적 조회 실패 (재시도 {_RETRY_MAX}회 소진)\n"
                                f"원인: {failure_reason}"
                            ),
                        )
                        logger.info(
                            f"[CollabDispatcher] {dept_id} 일시적 실패 — "
                            f"관리자({self._admin_chat_id}) 알림 전송 완료"
                        )
                    except Exception as alert_err:
                        logger.error(
                            f"[CollabDispatcher] 관리자 알림 전송 실패 "
                            f"(admin_chat_id={self._admin_chat_id}): {alert_err}"
                        )
                continue
            # ────────────────────────────────────────────────────────────────

            dept_name = _DEPT_NAMES.get(dept_id, dept_id)
            msg_lines = [
                f"[COLLAB_DISPATCH:{task_id}]",
                f"발신: {source_name}",
                f"수신: {dept_name}",
                f"요청: {task_text[:400]}",
            ]
            if context:
                msg_lines.append(f"맥락: {context[:300]}")

            msg = "\n".join(msg_lines)

            try:
                await self._send(chat_id, msg)
                dispatched.append(dept_id)
                _append_dispatch_event(
                    status="dispatched",
                    task_id=task_id,
                    source_dept=source_dept,
                    target_dept=dept_id,
                    context=context,
                    detail=task_text,
                )
                logger.info(
                    f"[CollabDispatcher] {task_id} → {dept_id} ({dept_name}) 전달 완료"
                )
            except Exception as e:
                _append_dispatch_event(
                    status="error",
                    task_id=task_id,
                    source_dept=source_dept,
                    target_dept=dept_id,
                    context=context,
                    detail=str(e),
                )
                logger.error(
                    f"[CollabDispatcher] {task_id} → {dept_id} 전달 실패: {e}"
                )

        return dispatched

    async def dispatch_from_tag(
        self,
        task_id: str,
        full_text: str,
        source_dept: str,
    ) -> list[str]:
        """텍스트에서 [COLLAB:...] 태그를 추출해 자동 dispatch한다.

        태그가 없으면 아무것도 하지 않는다.

        Returns:
            전달된 부서 org_id 목록 (여러 태그가 있으면 합산).
        """
        tags = parse_collab_tags(full_text)
        if not tags:
            logger.debug(f"[CollabDispatcher] {task_id} — COLLAB 태그 없음")
            return []

        all_dispatched: list[str] = []
        for tag in tags:
            dispatched = await self.dispatch(
                task_id=task_id,
                task_text=tag["task"],
                source_dept=source_dept,
                context=tag["context"],
            )
            all_dispatched.extend(dispatched)

        return all_dispatched
