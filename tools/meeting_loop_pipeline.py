"""meeting_loop_pipeline.py — 회의 파싱→추출→GoalTracker 등록 3단계 파이프라인.

`MeetingLoopPipeline` 이 메인 클래스다.
`parse → extract → register` 3단계를 순차 실행하며,
각 단계 실패 시 에러 로깅 후 다음 아이템을 계속 처리한다.

사용 예::

    pipeline = MeetingLoopPipeline(
        client=GoalTrackerClient(org_id="aiorg_pm_bot"),
    )
    result = await pipeline.run(
        chat_log=chat_text,
        meeting_type="daily_retro",
    )
    print(result.registered_count)   # 등록 성공 건수
    print(result.failed_count)       # 실패 건수
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

from loguru import logger

from tools.goaltracker_client import GoalTrackerClient, RegisterResult
from tools.meeting_parser import MeetingParser, ParsedActionItem


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── 파이프라인 결과 ───────────────────────────────────────────────────────────


@dataclass
class PipelineStepError:
    """파이프라인 단계별 에러 기록."""

    step: str           # "parse" | "extract" | "register"
    item_title: str
    error: str
    occurred_at: datetime = field(default_factory=_utcnow)


@dataclass
class PipelineResult:
    """MeetingLoopPipeline.run() 실행 결과.

    Attributes:
        meeting_type:     감지/지정된 회의 유형.
        parsed_count:     parse 단계에서 추출된 아이템 수.
        extracted_count:  extract 단계 통과 아이템 수.
        registered_count: register 단계 성공 건수.
        failed_count:     register 단계 실패 건수.
        registered_ids:   등록된 goal_id 목록.
        errors:           단계별 에러 기록.
        success:          에러 없이 완료했으면 True.
    """

    meeting_type: str
    parsed_count: int = 0
    extracted_count: int = 0
    registered_count: int = 0
    failed_count: int = 0
    registered_ids: list[str] = field(default_factory=list)
    errors: list[PipelineStepError] = field(default_factory=list)
    started_at: datetime = field(default_factory=_utcnow)
    finished_at: Optional[datetime] = None

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    @property
    def has_registered(self) -> bool:
        return self.registered_count > 0

    def finish(self) -> "PipelineResult":
        self.finished_at = _utcnow()
        return self

    def __str__(self) -> str:
        return (
            f"PipelineResult("
            f"type={self.meeting_type}, "
            f"parsed={self.parsed_count}, "
            f"extracted={self.extracted_count}, "
            f"registered={self.registered_count}, "
            f"failed={self.failed_count}, "
            f"ok={self.success})"
        )


# ── MeetingLoopPipeline ───────────────────────────────────────────────────────


class MeetingLoopPipeline:
    """parse → extract → register 3단계 파이프라인.

    단계별 동작:
        1. **parse**:    MeetingParser 로 채팅 로그에서 조치사항 후보 추출.
        2. **extract**:  confidence 필터링 + 유효성 검사 (최소 길이 등).
        3. **register**: GoalTrackerClient 로 GoalTracker에 단건 순차 등록.
                         각 아이템 실패 시 에러 로깅 후 다음 아이템 계속 처리.

    Args:
        client:           GoalTrackerClient 인스턴스.
        parser:           MeetingParser 인스턴스 (None 이면 기본값 생성).
        min_confidence:   extract 단계 최소 신뢰도 (기본 0.5).
        min_content_len:  extract 단계 최소 내용 길이 (기본 5자).
        on_register_done: 각 아이템 등록 완료 후 호출 콜백
                          (성공/실패 모두). ``async def cb(result: RegisterResult)``
    """

    def __init__(
        self,
        client: GoalTrackerClient,
        parser: Optional[MeetingParser] = None,
        min_confidence: float = 0.5,
        min_content_len: int = 5,
        on_register_done: Optional[Callable[[RegisterResult], Awaitable[None]]] = None,
    ) -> None:
        self._client = client
        self._parser = parser or MeetingParser(min_confidence=min_confidence)
        self._min_confidence = min_confidence
        self._min_content_len = min_content_len
        self._on_register_done = on_register_done

    # ── 메인 실행 ─────────────────────────────────────────────────────────

    async def run(
        self,
        chat_log: str,
        meeting_type: str = "auto",
        chat_id: Optional[int] = None,
    ) -> PipelineResult:
        """3단계 파이프라인 전체 실행.

        Args:
            chat_log:     회의 채팅 로그 전문.
            meeting_type: "daily_retro" | "weekly_meeting" | "auto".
            chat_id:      Telegram 채팅방 ID (알림용).

        Returns:
            PipelineResult 인스턴스.
        """
        # 실제 회의 유형 결정
        resolved_type = (
            self._parser.detect_type(chat_log)
            if meeting_type == "auto"
            else meeting_type
        )

        result = PipelineResult(meeting_type=resolved_type)
        logger.info(
            f"[MeetingLoopPipeline] 파이프라인 시작 — "
            f"type={resolved_type}, log_len={len(chat_log)}"
        )

        # ── Step 1: Parse ──────────────────────────────────────────────────
        parsed_items = self._step_parse(chat_log, resolved_type, result)

        # ── Step 2: Extract ────────────────────────────────────────────────
        extracted_items = self._step_extract(parsed_items, result)

        # ── Step 3: Register ───────────────────────────────────────────────
        await self._step_register(extracted_items, resolved_type, chat_id, result)

        result.finish()
        logger.info(f"[MeetingLoopPipeline] 완료 — {result}")
        return result

    # ── Step 1: Parse ──────────────────────────────────────────────────────

    def _step_parse(
        self,
        chat_log: str,
        meeting_type: str,
        result: PipelineResult,
    ) -> list[ParsedActionItem]:
        """채팅 로그에서 조치사항 후보 추출."""
        try:
            items = self._parser.parse(chat_log, meeting_type=meeting_type)
            result.parsed_count = len(items)
            logger.info(
                f"[MeetingLoopPipeline] Step1/Parse — {len(items)}개 추출"
            )
            return items
        except Exception as e:
            err_msg = f"parse 단계 오류: {e}"
            logger.error(f"[MeetingLoopPipeline] {err_msg}")
            result.errors.append(
                PipelineStepError(step="parse", item_title="<전체>", error=err_msg)
            )
            return []

    # ── Step 2: Extract ────────────────────────────────────────────────────

    def _step_extract(
        self,
        parsed_items: list[ParsedActionItem],
        result: PipelineResult,
    ) -> list[ParsedActionItem]:
        """confidence + 최소 길이 필터링."""
        extracted: list[ParsedActionItem] = []

        for item in parsed_items:
            try:
                # confidence 필터
                if item.confidence < self._min_confidence:
                    logger.debug(
                        f"[MeetingLoopPipeline] Step2/Extract 스킵 (confidence): "
                        f"{item.content[:40]} ({item.confidence:.2f})"
                    )
                    continue

                # 최소 길이 필터
                if len(item.content.strip()) < self._min_content_len:
                    logger.debug(
                        f"[MeetingLoopPipeline] Step2/Extract 스킵 (길이 부족): "
                        f"'{item.content[:40]}'"
                    )
                    continue

                extracted.append(item)
            except Exception as e:
                err_msg = f"extract 단계 오류: {e}"
                logger.error(
                    f"[MeetingLoopPipeline] {err_msg} — {item.content[:40]}"
                )
                result.errors.append(
                    PipelineStepError(
                        step="extract", item_title=item.content[:60], error=err_msg
                    )
                )

        result.extracted_count = len(extracted)
        logger.info(
            f"[MeetingLoopPipeline] Step2/Extract — "
            f"{len(parsed_items)}개 → {len(extracted)}개 통과"
        )
        return extracted

    # ── Step 3: Register ───────────────────────────────────────────────────

    async def _step_register(
        self,
        items: list[ParsedActionItem],
        source: str,
        chat_id: Optional[int],
        result: PipelineResult,
    ) -> None:
        """각 아이템 GoalTracker 등록. 개별 실패 시 에러 로깅 후 계속."""
        if not items:
            logger.info("[MeetingLoopPipeline] Step3/Register — 등록 대상 없음")
            return

        for item in items:
            try:
                reg_result = await self._client.register_action_item(
                    title=item.content,
                    assignee=item.assignee,
                    due_date=item.due_date,
                    source=source,
                    priority=item.priority,
                    chat_id=chat_id,
                )

                if reg_result.success and reg_result.goal_id:
                    result.registered_count += 1
                    result.registered_ids.append(reg_result.goal_id)
                    logger.info(
                        f"[MeetingLoopPipeline] Step3/Register 성공: "
                        f"{reg_result.goal_id} — {item.content[:50]}"
                    )
                else:
                    result.failed_count += 1
                    err_msg = reg_result.error or "goal_id 없음"
                    logger.warning(
                        f"[MeetingLoopPipeline] Step3/Register 실패: "
                        f"{err_msg} — {item.content[:50]}"
                    )
                    result.errors.append(
                        PipelineStepError(
                            step="register",
                            item_title=item.content[:60],
                            error=err_msg,
                        )
                    )

                # 콜백 실행
                if self._on_register_done is not None:
                    try:
                        await self._on_register_done(reg_result)
                    except Exception as cb_err:
                        logger.warning(
                            f"[MeetingLoopPipeline] on_register_done 콜백 오류 "
                            f"(비치명적): {cb_err}"
                        )

            except Exception as e:
                result.failed_count += 1
                err_msg = f"register 단계 예외: {e}"
                logger.error(
                    f"[MeetingLoopPipeline] {err_msg} — {item.content[:50]}"
                )
                result.errors.append(
                    PipelineStepError(
                        step="register",
                        item_title=item.content[:60],
                        error=err_msg,
                    )
                )
                # 다음 아이템 계속 처리 (continue)
                continue

        logger.info(
            f"[MeetingLoopPipeline] Step3/Register 완료 — "
            f"성공={result.registered_count}, 실패={result.failed_count}"
        )

    def __repr__(self) -> str:
        return (
            f"<MeetingLoopPipeline "
            f"client={self._client._org_id} "
            f"min_conf={self._min_confidence}>"
        )
