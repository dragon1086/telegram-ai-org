"""MultibotMeetingHandler — 전 조직 봇 일일회고/주간회의 참여 핸들러.

역할:
    - 일일회고(daily_retro) 또는 주간회의(weekly_meeting) 채팅 이벤트 수신
    - 전 조직 봇(6개)에게 보고 요청 발신 (순차, 중복 방지)
    - 각 봇의 보고를 수집하고 GoalTracker에 조치사항 자동 등록
    - idle→evaluate→replan→dispatch 자율 루프 트리거

E2E 시나리오:
    1. 채팅에서 "일일회고" 키워드 감지 → MultibotMeetingHandler.handle()
    2. 6개 부서 봇에 보고 요청 전송 (인터벌 3초)
    3. 봇 응답 수집 (타임아웃 120초)
    4. GoalTrackerClient.register_report() 호출
    5. 루프 결과(states_visited, dispatched_count) 반환

멀티봇 참여 순서:
    개발실 → 운영실 → 디자인실 → 기획실 → 성장실 → 리서치실

중복 등록 방지:
    meeting_id = {meeting_type}_{date} 기준으로 처리된 회의를 추적한다.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Awaitable, Callable, Optional

from loguru import logger

from goal_tracker.goal_tracker_client import GoalTrackerClient, ReportRegisterResult
from goal_tracker.meeting_handler import MeetingType, detect_meeting_type


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── 조직 봇 목록 ───────────────────────────────────────────────────────────────

ALL_ORG_BOTS: list[dict] = [
    {"id": "aiorg_engineering_bot", "name": "🔧 개발실", "emoji": "🔧"},
    {"id": "aiorg_ops_bot",         "name": "⚙️ 운영실", "emoji": "⚙️"},
    {"id": "aiorg_design_bot",      "name": "🎨 디자인실", "emoji": "🎨"},
    {"id": "aiorg_product_bot",     "name": "📋 기획실", "emoji": "📋"},
    {"id": "aiorg_growth_bot",      "name": "📈 성장실", "emoji": "📈"},
    {"id": "aiorg_research_bot",    "name": "🔍 리서치실", "emoji": "🔍"},
]

# 봇 보고 요청 인터벌 (초)
DEFAULT_BOT_REQUEST_INTERVAL_SEC: float = 3.0
# 봇 응답 수집 타임아웃 (초)
DEFAULT_COLLECT_TIMEOUT_SEC: float = 120.0


# ── 결과 타입 ──────────────────────────────────────────────────────────────────


@dataclass
class BotReport:
    """단일 봇의 보고 결과."""

    org_id: str
    org_name: str
    report_text: str
    reported_at: datetime = field(default_factory=_utcnow)
    success: bool = True
    error: Optional[str] = None


@dataclass
class MultibotMeetingResult:
    """handle() 실행 결과."""

    meeting_id: str
    meeting_type: str
    bot_reports: list[BotReport] = field(default_factory=list)
    register_result: Optional[ReportRegisterResult] = None
    started_at: datetime = field(default_factory=_utcnow)
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    skipped: bool = False          # 중복 실행 방지로 건너뛴 경우

    @property
    def success(self) -> bool:
        return self.error is None and not self.skipped

    @property
    def report_count(self) -> int:
        return len(self.bot_reports)

    @property
    def registered_count(self) -> int:
        if self.register_result:
            return self.register_result.registered_count
        return 0

    def finish(self) -> "MultibotMeetingResult":
        self.finished_at = _utcnow()
        return self


# ── MultibotMeetingHandler ────────────────────────────────────────────────────


class MultibotMeetingHandler:
    """전 조직 봇이 일일회고/주간회의에 참여하는 멀티봇 핸들러.

    Args:
        client:               GoalTrackerClient 인스턴스.
        send_func:            Telegram 메시지 전송 함수
                              ``async def send(chat_id, text) -> None``.
        request_bot_report:   개별 봇 보고 요청 함수
                              ``async def req(org_id, chat_id, meeting_type) -> str``.
                              None이면 내부 기본 구현(COLLAB 메시지 전송) 사용.
        bot_request_interval: 봇별 요청 인터벌 (초, 기본 3.0).
        collect_timeout:      봇 응답 수집 타임아웃 (초, 기본 120.0).
        org_bots:             참여 봇 목록 (None이면 ALL_ORG_BOTS).
    """

    def __init__(
        self,
        client: GoalTrackerClient,
        send_func: Optional[Callable[[int, str], Awaitable[None]]] = None,
        request_bot_report: Optional[
            Callable[[str, int, str], Awaitable[str]]
        ] = None,
        bot_request_interval: float = DEFAULT_BOT_REQUEST_INTERVAL_SEC,
        collect_timeout: float = DEFAULT_COLLECT_TIMEOUT_SEC,
        org_bots: Optional[list[dict]] = None,
    ) -> None:
        self._client = client
        self._send = send_func or _noop_send
        self._request_bot_report = request_bot_report
        self._interval = bot_request_interval
        self._timeout = collect_timeout
        self._bots = org_bots if org_bots is not None else list(ALL_ORG_BOTS)
        # 처리된 meeting_id 추적 (중복 방지)
        self._processed_meetings: set[str] = set()

    # ── 메인 진입점 ────────────────────────────────────────────────────────

    async def handle(
        self,
        message_text: str,
        chat_id: int,
        meeting_type: Optional[str] = None,
        force: bool = False,
    ) -> MultibotMeetingResult:
        """회의 이벤트 수신 및 전체 멀티봇 플로우 실행.

        Args:
            message_text: 채팅 메시지 텍스트 (트리거 감지용).
            chat_id:      Telegram 채팅방 ID.
            meeting_type: "daily_retro" | "weekly_meeting" | None (자동 감지).
            force:        True이면 중복 방지 무시하고 강제 실행.

        Returns:
            MultibotMeetingResult.
        """
        # ── 회의 유형 결정 ─────────────────────────────────────────────────
        detected_type = meeting_type or _detect_type(message_text)
        if detected_type is None:
            logger.debug(
                f"[MultibotHandler] 회의 트리거 미감지 — 메시지 길이={len(message_text)}"
            )
            return MultibotMeetingResult(
                meeting_id="", meeting_type="unknown",
                error="회의 트리거 패턴 미감지",
            )

        meeting_id = f"{detected_type}_{date.today().isoformat()}"
        result = MultibotMeetingResult(meeting_id=meeting_id, meeting_type=detected_type)

        # ── 중복 방지 체크 ─────────────────────────────────────────────────
        if not force and meeting_id in self._processed_meetings:
            logger.info(f"[MultibotHandler] 중복 실행 방지 — {meeting_id} 이미 처리됨")
            result.skipped = True
            return result

        logger.info(
            f"[MultibotHandler] 회의 시작 — type={detected_type}, "
            f"chat_id={chat_id}, bots={len(self._bots)}개"
        )

        # ── Step 1: 회의 시작 알림 ─────────────────────────────────────────
        type_label = _meeting_label(detected_type)
        await self._send(
            chat_id,
            f"📣 **{type_label}** 멀티봇 참여 시작\n"
            f"전 조직 {len(self._bots)}개 봇에 보고 요청을 발신합니다...",
        )

        # ── Step 2: 봇별 보고 요청 및 수집 ───────────────────────────────
        bot_reports = await self._collect_bot_reports(chat_id, detected_type)
        result.bot_reports = bot_reports

        # ── Step 3: 통합 보고서 생성 ─────────────────────────────────────
        combined_report = _build_combined_report(
            meeting_type=detected_type,
            bot_reports=bot_reports,
            original_text=message_text,
        )

        # ── Step 4: GoalTracker 등록 및 자율 루프 트리거 ──────────────────
        if combined_report.strip():
            register_result = await self._client.register_report(
                report_text=combined_report,
                report_type=detected_type,
                chat_id=chat_id,
            )
            result.register_result = register_result

            if register_result.action_items_found > 0:
                await self._send(
                    chat_id,
                    f"✅ **{type_label}** 조치사항 등록 완료\n"
                    f"  파싱: {register_result.action_items_found}개 → "
                    f"등록: {register_result.registered_count}개\n"
                    f"  루프 상태: {' → '.join(register_result.loop_states)}\n"
                    f"  배분: {register_result.dispatched_count}개",
                )
            else:
                logger.info(f"[MultibotHandler] 등록할 조치사항 없음 — {meeting_id}")
        else:
            logger.warning(f"[MultibotHandler] 통합 보고서 비어 있음 — {meeting_id}")

        # ── Step 5: 처리 완료 기록 ────────────────────────────────────────
        self._processed_meetings.add(meeting_id)
        result.finish()

        logger.info(
            f"[MultibotHandler] 완료 — meeting={meeting_id}, "
            f"reports={result.report_count}, registered={result.registered_count}"
        )
        return result

    # ── 봇 보고 수집 ──────────────────────────────────────────────────────

    async def _collect_bot_reports(
        self, chat_id: int, meeting_type: str
    ) -> list[BotReport]:
        """전 조직 봇에 보고 요청하고 결과 수집."""
        reports: list[BotReport] = []

        for i, bot in enumerate(self._bots):
            # 봇 간 인터벌
            if i > 0:
                await asyncio.sleep(self._interval)

            report = await self._request_single_bot_report(
                bot=bot,
                chat_id=chat_id,
                meeting_type=meeting_type,
            )
            reports.append(report)
            logger.debug(
                f"[MultibotHandler] {bot['name']} 보고 수집 "
                f"({'ok' if report.success else 'fail'})"
            )

        return reports

    async def _request_single_bot_report(
        self, bot: dict, chat_id: int, meeting_type: str
    ) -> BotReport:
        """단일 봇에 보고 요청하고 BotReport 반환."""
        org_id = bot["id"]
        org_name = bot["name"]

        try:
            if self._request_bot_report is not None:
                # 외부 주입 핸들러 사용 (E2E 테스트에서 mock으로 대체)
                report_text = await asyncio.wait_for(
                    self._request_bot_report(org_id, chat_id, meeting_type),
                    timeout=self._timeout / len(self._bots),
                )
            else:
                # 기본: COLLAB 형식 메시지 전송 후 빈 보고 반환
                # (실제 봇은 채널 메시지를 보고 자율적으로 응답)
                type_label = _meeting_label(meeting_type)
                await self._send(
                    chat_id,
                    f"🙋 도와줄 조직 찾아요!\n"
                    f"발신: aiorg_pm_bot\n"
                    f"요청: {org_name} {type_label} 현황 보고 (200자 이내)\n"
                    f"📎 맥락: {type_label} 진행 중. 완료사항·진행중·블로커·계획 각 1~2줄.",
                )
                report_text = f"[{org_name}] 보고 요청 전송됨 — 봇 자율 응답 대기"

            return BotReport(
                org_id=org_id,
                org_name=org_name,
                report_text=report_text,
            )

        except asyncio.TimeoutError:
            err = f"보고 타임아웃 ({self._timeout:.0f}s)"
            logger.warning(f"[MultibotHandler] {org_name}: {err}")
            return BotReport(
                org_id=org_id, org_name=org_name,
                report_text="", success=False, error=err,
            )
        except Exception as e:
            err = str(e)
            logger.error(f"[MultibotHandler] {org_name} 보고 요청 실패: {err}")
            return BotReport(
                org_id=org_id, org_name=org_name,
                report_text="", success=False, error=err,
            )

    # ── 상태 조회 ─────────────────────────────────────────────────────────

    @property
    def processed_meetings(self) -> set[str]:
        """처리 완료된 meeting_id 집합 (읽기 전용)."""
        return frozenset(self._processed_meetings)

    def reset_processed(self) -> None:
        """처리 완료 기록 초기화 (테스트용)."""
        self._processed_meetings.clear()

    def __repr__(self) -> str:
        return (
            f"<MultibotMeetingHandler bots={len(self._bots)} "
            f"processed={len(self._processed_meetings)}>"
        )


# ── 내부 헬퍼 ─────────────────────────────────────────────────────────────────


def _detect_type(text: str) -> Optional[str]:
    """메시지에서 회의 유형 감지."""
    try:
        mt = detect_meeting_type(text)
        if mt == MeetingType.DAILY_RETRO:
            return "daily_retro"
        if mt == MeetingType.WEEKLY_MEETING:
            return "weekly_meeting"
    except Exception:
        pass
    return None


def _meeting_label(meeting_type: str) -> str:
    return {
        "daily_retro": "일일회고",
        "weekly_meeting": "주간회의",
    }.get(meeting_type, "회의")


def _build_combined_report(
    meeting_type: str,
    bot_reports: list[BotReport],
    original_text: str,
) -> str:
    """봇 보고를 통합하여 GoalTracker 등록용 마크다운 생성."""
    today = date.today().isoformat()
    label = _meeting_label(meeting_type)

    lines = [
        f"# {label} 통합 보고 — {today}",
        "",
        "## 참여 봇 보고",
        "",
    ]

    for report in bot_reports:
        if report.success and report.report_text:
            lines += [
                f"### {report.org_name}",
                "",
                report.report_text.strip(),
                "",
            ]

    # 원본 텍스트 첨부 (조치사항 파싱 정확도 향상)
    if original_text and "조치사항" in original_text:
        lines += [
            "## 원본 회의 텍스트",
            "",
            original_text.strip(),
            "",
        ]

    return "\n".join(lines)


async def _noop_send(chat_id: int, text: str) -> None:  # pragma: no cover
    pass
