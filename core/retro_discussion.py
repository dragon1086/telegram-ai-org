"""대화형·점진적 회고 토론 시스템 (RetroDiscussion).

기존 broadcast_meeting_start의 일괄 발언 방식과 달리,
각 조직이 순차 발언·반응하며 자연스럽게 회고 내용을 쌓아가는 구조.

흐름:
    1. 라운드 1 — 잘한 것: 각 조직 순서대로 발언
    2. 라운드 2 — 잘못한 것: 이전 조직 발언을 컨텍스트로 참조
    3. 라운드 3 — 해야 할 것: 앞선 두 라운드 전체를 참조하여 Action Item 도출
    4. 후처리 — "해야 할 것" 항목을 MEMORY.md Pending Tasks에 자동 등록
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Coroutine, Optional

if TYPE_CHECKING:
    from core.pm_orchestrator import PMOrchestrator

logger = logging.getLogger(__name__)

# MEMORY.md 경로 — 실제 운영 경로를 여기에 맞춤
_MEMORY_PATH = Path(__file__).parent.parent / "memory" / "MEMORY.md"

# 라운드별 발언 지시
_ROUND_INSTRUCTIONS = {
    "잘한_것": (
        "이번 기간 **잘한 것**, 성공한 것, 잘 작동한 것을 솔직하게 공유해주세요.\n"
        "팀 전체가 참고할 수 있도록 구체적인 사례 위주로 서술합니다.\n"
        "형식: 간결한 불렛 목록 (최대 3개, 각 항목 앞에 '- 잘함:' 접두어)"
    ),
    "잘못한_것": (
        "이번 기간 **잘못한 것**, 아쉬운 점, 실수, 놓친 부분을 솔직하게 공유해주세요.\n"
        "비난이 아닌 개선을 위한 관찰입니다. 구체적으로 서술하세요.\n"
        "형식: 간결한 불렛 목록 (최대 3개, 각 항목 앞에 '- 아쉬움:' 접두어)"
    ),
    "해야_할_것": (
        "앞선 발언들을 참고하여 **해야 할 것**, 개선 액션을 제안해주세요.\n"
        "구체적이고 실행 가능한 항목이어야 합니다.\n"
        "형식: 불렛 목록 (각 항목 앞에 반드시 'TODO:' 접두어로 시작)"
    ),
}


@dataclass
class RoundEntry:
    """조직 1개의 단일 라운드 발언."""
    org_id: str
    dept_name: str
    round_name: str   # 잘한_것 | 잘못한_것 | 해야_할_것
    content: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class RetroSession:
    """회고 세션 전체 상태."""
    meeting_type: str           # daily_retro | friday_retro | weekly_standup
    session_date: str           # YYYY-MM-DD
    entries: list[RoundEntry] = field(default_factory=list)
    todo_items: list[str] = field(default_factory=list)   # 추출된 TODO 항목

    def context_for_round(self, round_name: str) -> str:
        """특정 라운드 시작 전 이전 발언 컨텍스트를 요약 문자열로 반환."""
        relevant = [e for e in self.entries]
        if not relevant:
            return ""
        lines = ["[이전 발언 요약]"]
        for e in relevant[-12:]:   # 최근 12개 발언으로 제한 (컨텍스트 크기 관리)
            label = {"잘한_것": "✅ 잘함", "잘못한_것": "⚠️ 아쉬움", "해야_할_것": "📌 TODO"}.get(
                e.round_name, e.round_name
            )
            lines.append(f"  [{e.dept_name} | {label}]\n{e.content}")
        return "\n".join(lines)


class RetroDiscussion:
    """대화형·점진적 회고 토론 관리자.

    각 조직이 순차 발언하고 이전 발언을 컨텍스트로 참조하는 회고 진행.
    최종적으로 'TODO:' 항목을 MEMORY.md Pending Tasks에 자동 등록.

    사용법:
        rd = RetroDiscussion(
            pm_orchestrator=orchestrator,
            send_text=send_fn,
            pm_chat_id=chat_id,
        )
        session = await rd.run_retro(meeting_type="daily_retro")
    """

    # 조직당 발언 수집 최대 대기 시간 (초)
    PER_ORG_TIMEOUT = 90.0
    # 라운드 사이 중간 보고 전송 여부
    POST_ROUND_SUMMARY = True

    def __init__(
        self,
        pm_orchestrator: "PMOrchestrator",
        send_text: Callable[[str], Coroutine],
        pm_chat_id: int | str | None = None,
        goal_tracker=None,
    ) -> None:
        self._pm = pm_orchestrator
        self._send = send_text
        self._chat_id = pm_chat_id
        self._goal_tracker = goal_tracker

    # ── 공개 진입점 ────────────────────────────────────────────────────────

    async def run_retro(self, meeting_type: str = "daily_retro") -> RetroSession:
        """전체 회고 토론을 순차 실행하고 세션 객체를 반환.

        Steps:
            1. 라운드 1: 잘한 것 (전 조직 순차 발언)
            2. 라운드 2: 잘못한 것 (이전 발언 컨텍스트 포함)
            3. 라운드 3: 해야 할 것 (TODO 도출)
            4. TODO 항목 → MEMORY.md 등록 + GoalTracker 등록
            5. 최종 요약 전송
        """
        session = RetroSession(
            meeting_type=meeting_type,
            session_date=date.today().isoformat(),
        )

        from core.constants import KNOWN_DEPTS
        orgs = list(KNOWN_DEPTS.items())  # [(org_id, dept_name), ...]

        logger.info(
            f"[RetroDiscussion] 회고 시작 — {meeting_type}, 참여 조직: {len(orgs)}개"
        )

        await self._send(
            f"🔔 **[{meeting_type.upper()}] 대화형 회고를 시작합니다.**\n"
            f"총 {len(orgs)}개 조직이 순차 발언합니다. 잘한 것 → 잘못한 것 → 해야 할 것 순서로 진행됩니다.\n"
            f"---"
        )

        # ── 라운드 1: 잘한 것 ───────────────────────────────────────────
        await self._run_round(session, orgs, "잘한_것")

        # ── 라운드 2: 잘못한 것 ─────────────────────────────────────────
        await self._run_round(session, orgs, "잘못한_것")

        # ── 라운드 3: 해야 할 것 (TODO 도출) ────────────────────────────
        await self._run_round(session, orgs, "해야_할_것")

        # ── 후처리: TODO 추출 + 자가개선 등록 ──────────────────────────
        session.todo_items = self._extract_todo_items(session)
        await self._register_self_improvement(session)

        # ── 최종 요약 전송 ──────────────────────────────────────────────
        await self._send_final_summary(session)

        logger.info(
            f"[RetroDiscussion] 회고 완료 — TODO {len(session.todo_items)}개 등록"
        )
        return session

    # ── 라운드 실행 ─────────────────────────────────────────────────────

    async def _run_round(
        self,
        session: RetroSession,
        orgs: list[tuple[str, str]],
        round_name: str,
    ) -> None:
        """단일 라운드(잘한 것/잘못한 것/해야 할 것)를 전 조직 순차 실행.

        각 조직은 이전 조직의 발언을 컨텍스트로 받아 반응·추가 의견을 쌓는다.
        """
        round_label = {"잘한_것": "✅ 잘한 것", "잘못한_것": "⚠️ 잘못한 것", "해야_할_것": "📌 해야 할 것"}.get(
            round_name, round_name
        )
        await self._send(f"\n### 라운드: {round_label}")

        for org_id, dept_name in orgs:
            # 이 조직 발언 전까지 쌓인 컨텍스트
            context_text = session.context_for_round(round_name)
            prompt = self._build_speak_prompt(
                dept_name=dept_name,
                round_name=round_name,
                context=context_text,
                session=session,
            )

            content = await self._collect_single_response(
                org_id=org_id,
                dept_name=dept_name,
                prompt=prompt,
                session=session,
            )

            entry = RoundEntry(
                org_id=org_id,
                dept_name=dept_name,
                round_name=round_name,
                content=content,
            )
            session.entries.append(entry)

            # 즉시 발언 내용 전송 (잡담 효과)
            if content and content != "(발언 없음)":
                await self._send(f"**{dept_name}**: {content}")

        if self.POST_ROUND_SUMMARY:
            await self._send_round_summary(session, round_name)

    # ── 단일 조직 응답 수집 ─────────────────────────────────────────────

    async def _collect_single_response(
        self,
        org_id: str,
        dept_name: str,
        prompt: str,
        session: RetroSession,
    ) -> str:
        """단일 조직에 태스크를 배분하고 응답을 수집한다.

        POMOrchestrator.dispatch + ContextDB polling 방식 사용.
        타임아웃 시 "(발언 없음)" 반환.
        """
        try:
            from core.pm_orchestrator import SubTask
            import uuid as _uuid

            subtask = SubTask(
                assigned_dept=org_id,
                description=prompt,
                depends_on=[],
                task_type="보고",
                allow_file_change=False,
                expected_output=f"{dept_name} 회고 발언",
                rationale=f"대화형 회고 — {session.meeting_type}",
                priority="medium",
            )

            parent_task_id = (
                f"RETRO-{session.meeting_type}-{session.session_date}-"
                f"{org_id[:8]}-{_uuid.uuid4().hex[:6]}"
            )
            await self._pm._db.create_pm_task(
                task_id=parent_task_id,
                description=prompt[:200],
                assigned_dept="pm",
                chat_id=self._chat_id,
            )

            task_ids = await self._pm.dispatch(
                parent_task_id=parent_task_id,
                subtasks=[subtask],
                chat_id=self._chat_id,
            )

            if not task_ids:
                return "(발언 없음 — 태스크 배분 실패)"

            # 응답 폴링
            return await self._poll_response(
                task_id=task_ids[0],
                timeout_sec=self.PER_ORG_TIMEOUT,
            )

        except Exception as e:
            logger.warning(f"[RetroDiscussion] {org_id} 응답 수집 오류: {e}")
            return f"(발언 없음 — 오류: {e})"

    async def _poll_response(self, task_id: str, timeout_sec: float) -> str:
        """ContextDB에서 태스크 완료 응답을 폴링으로 수집한다."""
        db = self._pm._db
        terminal = {"done", "failed", "cancelled"}
        poll_interval = 5.0
        waited = 0.0

        while waited < timeout_sec:
            await asyncio.sleep(poll_interval)
            waited += poll_interval
            try:
                task = await db.get_pm_task(task_id)
                if task and task.get("status") in terminal:
                    return task.get("result", "(응답 없음)") or "(응답 없음)"
            except Exception as e:
                logger.warning(f"[RetroDiscussion] poll 오류 (task={task_id}): {e}")

        return "(발언 없음 — 타임아웃)"

    # ── 프롬프트 생성 ───────────────────────────────────────────────────

    @staticmethod
    def _build_speak_prompt(
        dept_name: str,
        round_name: str,
        context: str,
        session: RetroSession,
    ) -> str:
        """조직별 발언 프롬프트 생성.

        이전 발언 컨텍스트를 포함하여 자연스럽게 반응·추가 의견을 유도.
        """
        instruction = _ROUND_INSTRUCTIONS[round_name]
        date_str = session.session_date
        header = (
            f"[{session.meeting_type.upper()} | {date_str}] "
            f"{dept_name} 발언 차례입니다.\n\n"
        )

        if context:
            header += (
                f"{context}\n\n"
                f"---\n위 다른 조직의 발언을 참고하여, "
                f"같은 부분은 공감·보충하고 다른 시각은 추가해주세요.\n\n"
            )

        return header + instruction

    # ── TODO 추출 ────────────────────────────────────────────────────────

    @staticmethod
    def _extract_todo_items(session: RetroSession) -> list[str]:
        """'해야_할_것' 라운드 발언에서 'TODO:' 접두어 항목을 파싱한다."""
        items: list[str] = []
        for entry in session.entries:
            if entry.round_name != "해야_할_것":
                continue
            for line in entry.content.splitlines():
                line = line.strip().lstrip("- •*")
                if line.upper().startswith("TODO:"):
                    todo = line.split(":", 1)[-1].strip()
                    if len(todo) >= 5 and todo not in items:
                        items.append(f"[{entry.dept_name}] {todo}")
        return items

    # ── 자가개선 등록 ────────────────────────────────────────────────────

    async def _register_self_improvement(self, session: RetroSession) -> None:
        """추출된 TODO 항목을 MEMORY.md Pending Tasks 및 GoalTracker에 등록한다."""
        if not session.todo_items:
            return

        # ── 1) MEMORY.md Pending Tasks 섹션에 등록 ─────────────────────
        await asyncio.get_event_loop().run_in_executor(
            None, self._append_to_memory_md, session
        )

        # ── 2) GoalTracker에 등록 (연결된 경우) ────────────────────────
        if self._goal_tracker is not None:
            registered = 0
            for item in session.todo_items:
                try:
                    goal_id = await self._goal_tracker.start_goal(
                        title=f"[자가개선 | {session.session_date}] {item[:60]}",
                        description=item,
                        meta={
                            "source": session.meeting_type,
                            "auto_registered": True,
                            "session_date": session.session_date,
                        },
                        chat_id=self._chat_id,
                    )
                    logger.info(f"[RetroDiscussion] GoalTracker 등록: {goal_id}")
                    registered += 1
                except Exception as e:
                    logger.warning(f"[RetroDiscussion] GoalTracker 등록 실패: {e}")

            if registered:
                await self._send(
                    f"📌 자가개선 태스크 {registered}개를 GoalTracker에 자동 등록했습니다."
                )

    @staticmethod
    def _append_to_memory_md(session: RetroSession) -> None:
        """MEMORY.md Pending Tasks 섹션에 TODO 항목을 신규 행으로 추가한다.

        기존 내용을 보존하고 '## Pending Tasks' 테이블 마지막에 삽입.
        """
        if not _MEMORY_PATH.exists():
            logger.warning(f"[RetroDiscussion] MEMORY.md 없음: {_MEMORY_PATH}")
            return

        content = _MEMORY_PATH.read_text(encoding="utf-8")
        today = date.today().isoformat()

        new_rows: list[str] = []
        for item in session.todo_items:
            # 중복 방지: 동일 내용이 이미 있으면 스킵
            if item[:40] in content:
                continue
            # ID: RETRO-YYYYMMDD-NNN 형식
            row_id = f"RETRO-{today.replace('-', '')}-{len(new_rows)+1:03d}"
            new_rows.append(
                f"| {row_id} | {item[:80]} | {today} | pending | - |"
            )

        if not new_rows:
            return

        # "### 최근 resolved" 또는 "---" 이전의 Pending Tasks 테이블 끝에 삽입
        insert_marker = "### 최근 resolved 항목"
        if insert_marker in content:
            rows_text = "\n".join(new_rows) + "\n"
            content = content.replace(
                insert_marker,
                rows_text + "\n" + insert_marker,
            )
        else:
            # 마커 없으면 파일 끝에 추가
            content += "\n" + "\n".join(new_rows) + "\n"

        _MEMORY_PATH.write_text(content, encoding="utf-8")
        logger.info(
            f"[RetroDiscussion] MEMORY.md에 {len(new_rows)}개 항목 등록: {_MEMORY_PATH}"
        )

    # ── 요약 전송 ────────────────────────────────────────────────────────

    async def _send_round_summary(self, session: RetroSession, round_name: str) -> None:
        """라운드 종료 후 이 라운드 전체 발언 요약을 전송한다."""
        round_entries = [e for e in session.entries if e.round_name == round_name]
        if not round_entries:
            return
        label = {"잘한_것": "✅ 잘한 것", "잘못한_것": "⚠️ 잘못한 것", "해야_할_것": "📌 해야 할 것"}.get(
            round_name, round_name
        )
        lines = [f"**[{label} 라운드 종료]** 전체 발언 요약:"]
        for e in round_entries:
            short = e.content[:150] + ("…" if len(e.content) > 150 else "")
            lines.append(f"• **{e.dept_name}**: {short}")
        await self._send("\n".join(lines))

    async def _send_final_summary(self, session: RetroSession) -> None:
        """전체 회고 종료 후 최종 요약(TODO 목록 포함)을 전송한다."""
        lines = [
            f"## 🏁 {session.meeting_type.upper()} 회고 완료 — {session.session_date}",
            "",
            f"**참여 조직**: {len({e.org_id for e in session.entries})}개",
            f"**총 발언**: {len(session.entries)}개",
            "",
        ]

        if session.todo_items:
            lines.append("### 📌 자가개선 태스크 (자동 등록됨)")
            for item in session.todo_items:
                lines.append(f"- {item}")
        else:
            lines.append("*이번 회고에서 도출된 TODO 항목 없음.*")

        await self._send("\n".join(lines))
