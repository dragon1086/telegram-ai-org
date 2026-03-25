"""GoalTrackerClient — GoalTracker 연동 API 클라이언트.

AutonomousLoop, 멀티봇 핸들러, 외부 스크립트가 GoalTracker에
보고·조치사항을 등록하고 상태를 조회하는 단일 인터페이스.

역할:
    - create_goal()    : 신규 목표 생성
    - update_goal()    : 목표 상태/진척률 업데이트
    - register_report(): 회의 보고에서 조치사항 자동 등록 (auto_register 래퍼)
    - get_active_goals(): 활성 목표 조회
    - get_goal()       : 단일 목표 조회

사용 예::

    client = GoalTrackerClient(goal_tracker=tracker)
    goal_id = await client.create_goal(
        title="E2E 테스트 구현",
        description="자율 루프 E2E 시나리오 코드 구현",
        chat_id=GROUP_CHAT_ID,
    )
    await client.update_goal(goal_id, status="achieved")

    result = await client.register_report(
        report_text=retro_md,
        report_type="daily_retro",
    )
    print(result.registered_ids)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from loguru import logger


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── 결과 타입 ──────────────────────────────────────────────────────────────────


@dataclass
class GoalCreateResult:
    """create_goal() 결과."""

    goal_id: str
    title: str
    status: str = "active"
    created_at: datetime = field(default_factory=_utcnow)
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None


@dataclass
class GoalUpdateResult:
    """update_goal() 결과."""

    goal_id: str
    field_updated: str
    new_value: str
    updated_at: datetime = field(default_factory=_utcnow)
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None


@dataclass
class ReportRegisterResult:
    """register_report() 결과 — AutoRegisterResult 래퍼."""

    report_type: str
    action_items_found: int = 0
    registered_ids: list[str] = field(default_factory=list)
    loop_states: list[str] = field(default_factory=list)
    dispatched_count: int = 0
    error: Optional[str] = None
    registered_at: datetime = field(default_factory=_utcnow)

    @property
    def success(self) -> bool:
        return self.error is None

    @property
    def registered_count(self) -> int:
        return len(self.registered_ids)


# ── GoalTrackerClient ─────────────────────────────────────────────────────────


class GoalTrackerClient:
    """GoalTracker 연동 API 클라이언트.

    GoalTracker 인스턴스를 주입받아 목표 생성·조회·업데이트·보고 등록을
    단일 인터페이스로 노출한다.

    Args:
        goal_tracker: core.goal_tracker.GoalTracker 인스턴스 (None이면 dry-run).
        org_id:       클라이언트 조직 ID (로깅·등록 출처 표기용).
        chat_id:      기본 Telegram 채팅방 ID.
        send_func:    알림 전송 함수 ``async def send(chat_id, text) -> None``.
        dry_run:      True이면 실제 DB 변경 없이 로그만 출력.
    """

    def __init__(
        self,
        goal_tracker=None,
        org_id: str = "aiorg_pm_bot",
        chat_id: int = 0,
        send_func: Optional[Callable[[int, str], Awaitable[None]]] = None,
        dry_run: bool = False,
    ) -> None:
        self._tracker = goal_tracker
        self._org_id = org_id
        self._chat_id = chat_id
        self._send = send_func
        self._dry_run = dry_run

    # ── 목표 생성 ─────────────────────────────────────────────────────────

    async def create_goal(
        self,
        title: str,
        description: str = "",
        meta: dict | None = None,
        chat_id: int | None = None,
        org_id: str | None = None,
    ) -> GoalCreateResult:
        """신규 목표를 GoalTracker에 생성.

        Args:
            title:       목표 제목 (짧은 레이블, 중복 방지 키로 사용됨).
            description: 상세 설명.
            meta:        메타데이터 dict (sprint, due_date, tags 등).
            chat_id:     Telegram 채팅방 ID (None이면 기본값 사용).
            org_id:      등록 조직 ID (None이면 기본값 사용).

        Returns:
            GoalCreateResult.
        """
        effective_chat_id = chat_id if chat_id is not None else self._chat_id
        effective_org = org_id or self._org_id

        if self._dry_run:
            fake_id = f"G-dryrun-{title[:20]}"
            logger.info(f"[GoalTrackerClient] dry_run: create_goal({title!r}) → {fake_id}")
            return GoalCreateResult(goal_id=fake_id, title=title)

        if self._tracker is None:
            logger.warning("[GoalTrackerClient] goal_tracker 없음 — create_goal 건너뜀")
            return GoalCreateResult(goal_id="", title=title, error="goal_tracker not set")

        try:
            goal_id = await self._tracker.start_goal(
                title=title,
                description=description or title,
                meta=meta,
                chat_id=effective_chat_id,
                org_id=effective_org,
            )
            logger.info(f"[GoalTrackerClient] create_goal: {goal_id} — {title[:60]}")
            return GoalCreateResult(goal_id=goal_id, title=title)
        except Exception as e:
            err = f"create_goal 실패: {e}"
            logger.error(f"[GoalTrackerClient] {err}")
            return GoalCreateResult(goal_id="", title=title, error=err)

    # ── 목표 상태 업데이트 ────────────────────────────────────────────────

    async def update_goal(
        self,
        goal_id: str,
        status: str | None = None,
        progress_summary: str | None = None,
    ) -> GoalUpdateResult:
        """목표 상태 또는 진척 요약을 업데이트.

        Args:
            goal_id:          목표 ID.
            status:           새 상태 (active/achieved/cancelled/stagnated).
            progress_summary: 최신 진척 요약 문자열.

        Returns:
            GoalUpdateResult.
        """
        if self._dry_run:
            field_name = "status" if status else "progress"
            logger.info(
                f"[GoalTrackerClient] dry_run: update_goal({goal_id}, "
                f"status={status}, summary={progress_summary!r})"
            )
            return GoalUpdateResult(
                goal_id=goal_id,
                field_updated=field_name,
                new_value=str(status or progress_summary or ""),
            )

        if self._tracker is None:
            err = "goal_tracker not set"
            return GoalUpdateResult(goal_id=goal_id, field_updated="", new_value="", error=err)

        try:
            if status is not None:
                await self._tracker.update_goal_status(goal_id, status)
                logger.info(f"[GoalTrackerClient] update_goal: {goal_id} → status={status}")
                return GoalUpdateResult(goal_id=goal_id, field_updated="status", new_value=status)

            if progress_summary is not None:
                # GoalTracker DB에 직접 진척 요약 기록
                await self._tracker._db.update_goal(
                    goal_id, last_progress=progress_summary
                )
                logger.info(f"[GoalTrackerClient] update_goal: {goal_id} → progress updated")
                return GoalUpdateResult(
                    goal_id=goal_id,
                    field_updated="progress_summary",
                    new_value=progress_summary[:60],
                )

            return GoalUpdateResult(goal_id=goal_id, field_updated="none", new_value="")

        except Exception as e:
            err = f"update_goal 실패: {e}"
            logger.error(f"[GoalTrackerClient] {err}")
            return GoalUpdateResult(goal_id=goal_id, field_updated="", new_value="", error=err)

    # ── 보고 등록 (auto_register 래퍼) ──────────────────────────────────

    async def register_report(
        self,
        report_text: str,
        report_type: str,
        chat_id: int | None = None,
        run_loop: bool = True,
        dispatch_func: Optional[Callable[[list[str]], Awaitable[None]]] = None,
    ) -> ReportRegisterResult:
        """회의/회고 보고에서 조치사항을 파싱하여 GoalTracker에 자동 등록.

        Args:
            report_text: 일일회고 또는 주간회의 마크다운 전문.
            report_type: "daily_retro" | "weekly_meeting".
            chat_id:     Telegram 채팅방 ID (None이면 기본값).
            run_loop:    True이면 등록 후 run_meeting_cycle() 실행.
            dispatch_func: DISPATCH 단계 콜백 (None이면 noop).

        Returns:
            ReportRegisterResult.
        """
        from goal_tracker.auto_register import auto_register_from_report
        from goal_tracker.loop_runner import run_meeting_cycle

        effective_chat_id = chat_id if chat_id is not None else self._chat_id

        result = ReportRegisterResult(report_type=report_type)

        if self._dry_run:
            logger.info(
                f"[GoalTrackerClient] dry_run: register_report(type={report_type}, "
                f"len={len(report_text)})"
            )
            result.action_items_found = 1
            result.registered_ids = [f"G-dryrun-{report_type}-001"]
            result.loop_states = ["idle", "evaluate", "replan", "dispatch", "idle"]
            result.dispatched_count = 1
            return result

        try:
            # Step 1: 파싱 + GoalTracker 등록
            auto_result = await auto_register_from_report(
                report_text=report_text,
                report_type=report_type,
                goal_tracker=self._tracker,
                chat_id=effective_chat_id,
                org_id=self._org_id,
                send_func=self._send,
            )

            result.action_items_found = auto_result.action_items_found
            result.registered_ids = auto_result.registered_ids
            if auto_result.errors:
                result.error = "; ".join(auto_result.errors[:3])

            logger.info(
                f"[GoalTrackerClient] register_report: type={report_type}, "
                f"found={auto_result.action_items_found}, "
                f"registered={auto_result.registered_count}"
            )

            # Step 2: 자율 루프 실행 (선택)
            if run_loop and auto_result.registered_ids:
                loop_result = await run_meeting_cycle(
                    meeting_type=report_type,
                    registered_ids=auto_result.registered_ids,
                    dispatch_func=dispatch_func,
                )
                result.loop_states = loop_result.states_visited
                result.dispatched_count = loop_result.dispatched_count
                if loop_result.error and not result.error:
                    result.error = loop_result.error

                logger.info(
                    f"[GoalTrackerClient] 루프 완료: states={loop_result.states_visited}, "
                    f"dispatched={loop_result.dispatched_count}"
                )

        except ImportError as e:
            result.error = f"GoalTracker 모듈 없음: {e}"
            logger.warning(f"[GoalTrackerClient] {result.error}")
        except Exception as e:
            result.error = f"register_report 실패: {e}"
            logger.error(f"[GoalTrackerClient] {result.error}")

        return result

    # ── 목표 조회 ─────────────────────────────────────────────────────────

    async def get_active_goals(self, org_id: str | None = None) -> list[dict]:
        """활성 목표 목록 조회.

        Returns:
            활성 목표 dict 리스트. tracker 없으면 [].
        """
        if self._tracker is None:
            return []
        try:
            return await self._tracker.get_active_goals(org_id=org_id)
        except Exception as e:
            logger.error(f"[GoalTrackerClient] get_active_goals 실패: {e}")
            return []

    async def get_goal(self, goal_id: str) -> dict | None:
        """단일 목표 조회.

        Returns:
            목표 dict 또는 None.
        """
        if self._tracker is None:
            return None
        try:
            return await self._tracker._db.get_goal(goal_id)
        except Exception as e:
            logger.error(f"[GoalTrackerClient] get_goal({goal_id}) 실패: {e}")
            return None

    # ── 진척 평가 ─────────────────────────────────────────────────────────

    async def evaluate_progress(self, goal_id: str):
        """목표 진척 평가 (GoalStatus 반환).

        Returns:
            GoalStatus 또는 None (tracker 없음).
        """
        if self._tracker is None:
            return None
        try:
            return await self._tracker.evaluate_progress(goal_id)
        except Exception as e:
            logger.error(f"[GoalTrackerClient] evaluate_progress({goal_id}) 실패: {e}")
            return None

    def __repr__(self) -> str:
        has_tracker = self._tracker is not None
        return (
            f"<GoalTrackerClient org={self._org_id} "
            f"tracker={'yes' if has_tracker else 'no'} "
            f"dry_run={self._dry_run}>"
        )
