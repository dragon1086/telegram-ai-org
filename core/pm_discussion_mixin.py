"""PMDiscussionMixin — Discussion/Debate 관련 메서드 모음.

PMOrchestrator에서 분리된 Mixin 클래스.
이 파일의 모든 메서드는 self가 PMOrchestrator 인스턴스임을 전제로 한다.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

from core.constants import KNOWN_DEPTS
from core.orchestration_config import load_orchestration_config

if TYPE_CHECKING:
    from core.pm_orchestrator import DiscussionNeeded, SubTask


class PMDiscussionMixin:
    """Discussion/Debate 기능 Mixin.

    PMOrchestrator가 이 Mixin을 상속한다.
    self._db, self._send, self._synthesizer, self._decision_client,
    self._org_id, self._discussion, self._next_task_id, self._org_mention
    등의 속성/메서드는 PMOrchestrator에서 제공된다.
    """

    async def _debate_synthesize(
        self,
        parent_task_id: str,
        parent_meta: dict,
        subtasks: list[dict],
        chat_id: int,
    ) -> None:
        """debate 모드 전용 합성 — 관점 비교 후 PM 종합 판단 전송."""
        topic = parent_meta.get("debate_topic", "토론 주제")
        opinions = [
            {
                "bot_id": task.get("assigned_to", "unknown"),
                "dept_name": task.get("metadata", {}).get(
                    "dept_name", task.get("assigned_to", "")
                ),
                "content": task.get("result", "(응답 없음)"),
            }
            for task in subtasks
        ]

        conclusion = await self._synthesizer.synthesize_debate(topic, opinions)

        header = f"[토론 결론] {topic[:50]}\n\n"
        opinion_lines = "".join(
            f"• {op['dept_name']}: {op['content'][:80]}...\n" for op in opinions
        )
        msg = f"{header}{opinion_lines}\n🎯 PM 종합 판단:\n{conclusion}"

        await self._send(chat_id, msg)
        await self._db.update_pm_task_status(parent_task_id, "done", result=conclusion)

    async def _discussion_summarize(
        self, parent_id: str, results: list[dict], chat_id: int,
    ) -> None:
        """discussion 모드 라운드 관리. 라운드가 남으면 핑퐁 재발행, 아니면 최종 요약."""
        # parent 먼저 조회 — current_round 기준으로 perspectives 필터링 필요
        parent = await self._db.get_pm_task(parent_id)
        parent_meta = parent.get("metadata", {}) if parent else {}
        max_rounds: int = int(parent_meta.get("discussion_rounds", 1))
        current_round: int = int(parent_meta.get("discussion_current_round", 1))
        topic: str = parent_meta.get("discussion_topic", "")
        # 현재 라운드 서브태스크 결과만 추출 (이전 라운드 중복 제외)
        # discussion_round가 없는 결과는 backward compat으로 포함
        perspectives = [
            r.get("result", "") for r in results
            if r.get("result")
            and (
                r.get("metadata", {}).get("discussion_round") is None
                or r.get("metadata", {}).get("discussion_round") == current_round
            )
        ]
        if not perspectives:
            await self._db.update_pm_task_status(parent_id, "done", result="")
            return

        if current_round < max_rounds:
            round_summary = await self._synthesizer.summarize_discussion(perspectives)
            next_round = current_round + 1
            # 충돌/합의 독립 감지 (순차 게이팅 아님)
            has_conflict, conflict_points = await self._detect_discussion_conflict(perspectives)
            has_consensus = await self._detect_discussion_consensus(perspectives)

            if has_conflict:
                logger.info(f"[PM] discussion {parent_id} 라운드 {current_round}: 의견 충돌 감지")
                if chat_id:
                    await self._send(chat_id, "🔥 *의견 충돌 감지* — 다음 라운드에서 구체적 반박 요청")

            # 합의 도달 AND 충돌 없음 → 조기 종료 (충돌+합의 동시 = 모순 신호, 계속 진행)
            if has_consensus and not has_conflict:
                logger.info(f"[PM] discussion {parent_id} 라운드 {current_round}: 합의 도달 — 조기 종료")
                if chat_id:
                    await self._send(
                        chat_id,
                        f"✅ *합의 도달* — 토론 조기 종료 (라운드 {current_round}/{max_rounds})\n\n"
                        f"💬 *최종 요약*\n{round_summary or '의견 수렴 완료'}",
                    )
                await self._db.update_pm_task_status(parent_id, "done", result=round_summary or "")
                return

            follow_up = await self._generate_discussion_followup(
                topic, round_summary, next_round,
                has_conflict=has_conflict, conflict_points=conflict_points,
            )
            await self._db.update_pm_task_metadata(
                parent_id, {"discussion_current_round": next_round}
            )
            if chat_id:
                await self._send(
                    chat_id,
                    f"💬 *라운드 {current_round} 요약*\n{round_summary or '의견 수렴 중...'}"
                    f"\n\n➡️ 라운드 {next_round} 시작",
                )
            participants: list[str] = parent_meta.get("discussion_participants", [])
            if participants:
                await self._redispatch_discussion_round(
                    parent_id, follow_up, participants, chat_id, next_round, max_rounds,
                )
            return

        summary = await self._synthesizer.summarize_discussion(perspectives)
        if summary and chat_id:
            await self._send(chat_id, f"💬 *토론 요약*\n{summary}")
        await self._db.update_pm_task_status(parent_id, "done", result=summary or "")
        # 최종 라운드 완료 → 전체 subtask 결과로 PM 통합 보고서 생성
        # (_skip_discussion_gate=True 로 재귀 방지)
        await self._synthesize_and_act(parent_id, results, chat_id, _skip_discussion_gate=True)

    async def _generate_discussion_followup(
        self, topic: str, round_summary: str, next_round: int,
        has_conflict: bool = False, conflict_points: str = "",
    ) -> str:
        """다음 라운드 follow-up 질문 생성. LLM 실패 시 기본 문자열 반환."""
        if self._decision_client is None:
            if has_conflict and conflict_points:
                return f"[라운드 {next_round}] {topic} (충돌 포인트: {conflict_points})"
            return f"[라운드 {next_round}] {topic}"
        conflict_instruction = ""
        if has_conflict and conflict_points:
            conflict_instruction = (
                f"\n\n다음 의견 차이를 중심으로 반박하도록 유도하세요: {conflict_points[:200]}"
            )
        prompt = (
            f"토론 주제: {topic}\n"
            f"라운드 요약: {round_summary[:300]}\n\n"
            f"다음 라운드({next_round})를 위한 간결한 follow-up 질문을 한 문장으로 작성하세요. "
            f"판단이나 결론 없이 탐색적 질문만 사용하세요."
            f"{conflict_instruction}"
        )
        try:
            return await asyncio.wait_for(
                self._decision_client.complete(prompt), timeout=20.0,
            )
        except Exception as _e:
            logger.debug(f"[PM] follow-up 질문 생성 실패 (무시): {_e}")
            if has_conflict and conflict_points:
                return f"[라운드 {next_round}] {topic} (충돌 포인트: {conflict_points})"
            return f"[라운드 {next_round}] {topic}"

    async def _detect_discussion_conflict(self, perspectives: list[str]) -> tuple[bool, str]:
        """perspectives에서 의견 충돌 감지. LLM 우선, 실패 시 키워드 fallback.

        Returns:
            (has_conflict, conflict_points) — conflict_points는 충돌 요약 문자열 (없으면 "").
        """
        if not perspectives or len(perspectives) < 2:
            return False, ""

        _CONFLICT_KEYWORDS = [
            "반대", "다르다", "아니다", "하지만", "그러나", "반면",
            "disagree", "however", "but", "contrast", "oppose",
        ]

        # LLM 판단 시도
        if self._decision_client is not None:
            prompt = (
                "다음 의견들에서 명확한 의견 충돌(서로 상반된 주장)이 있는지 판단하세요.\n"
                + "\n".join(f"[{i+1}] {p[:200]}" for i, p in enumerate(perspectives))
                + "\n\n충돌이 있으면 'YES: [충돌 포인트 한 줄 요약]', 없으면 'NO'로만 답하세요."
            )
            try:
                answer = await asyncio.wait_for(
                    self._decision_client.complete(prompt), timeout=15.0,
                )
                lower = answer.lower()
                if lower.startswith("yes"):
                    conflict_points = ""
                    if ":" in answer:
                        conflict_points = answer.split(":", 1)[1].strip()
                    return True, conflict_points
                return False, ""
            except Exception as _e:
                logger.debug(f"[PM] conflict 감지 LLM 실패 (키워드 fallback): {_e}")

        # 키워드 fallback — 매칭된 키워드 주변 문맥 반환
        combined = " ".join(perspectives).lower()
        for kw in _CONFLICT_KEYWORDS:
            idx = combined.find(kw)
            if idx != -1:
                start = max(0, idx - 30)
                end = min(len(combined), idx + len(kw) + 60)
                snippet = combined[start:end].strip()
                return True, snippet
        return False, ""

    async def _detect_discussion_consensus(self, perspectives: list[str]) -> bool:
        """perspectives에서 합의/수렴 감지. LLM 우선, 실패 시 키워드 fallback.

        키워드 fallback: 명시적 합의 키워드가 있을 때만 True 반환.
        """
        if not perspectives or len(perspectives) < 2:
            return False

        _CONSENSUS_KEYWORDS = [
            "동의", "합의", "agreed", "맞아요", "동의합니다",
            "agree", "consensus", "맞습니다", "그렇습니다",
        ]

        # LLM 판단 시도
        if self._decision_client is not None:
            prompt = (
                "다음 의견들이 충분히 수렴(합의)되었는지 판단하세요.\n"
                + "\n".join(f"[{i+1}] {p[:200]}" for i, p in enumerate(perspectives))
                + "\n\n합의가 이루어졌으면 'YES', 아직 의견 차이가 있으면 'NO'로만 답하세요."
            )
            try:
                answer = await asyncio.wait_for(
                    self._decision_client.complete(prompt), timeout=15.0,
                )
                return "yes" in answer.lower()
            except Exception as _e:
                logger.debug(f"[PM] consensus 감지 LLM 실패 (키워드 fallback): {_e}")

        # 키워드 fallback — 명시적 합의 키워드가 있을 때만 True
        combined = " ".join(perspectives).lower()
        return any(kw in combined for kw in _CONSENSUS_KEYWORDS)

    async def _redispatch_discussion_round(
        self,
        parent_id: str,
        topic: str,
        participants: list[str],
        chat_id: int,
        current_round: int,
        max_rounds: int,
    ) -> None:
        """discussion 다음 라운드 서브태스크 재발행."""
        try:
            cfg = load_orchestration_config(force_reload=True)
            org_map = {org.id: org for org in cfg.list_orgs()}
        except Exception as _e:
            logger.warning(f"[PM] discussion round {current_round} org_map 로드 실패: {_e}")
            org_map = {}

        # 이전 라운드 발언 컨텍스트 수집 (라운드 2부터)
        prev_round_context = ""
        if current_round > 1:
            try:
                all_subtasks = await self._db.get_subtasks(parent_id)
                prev_utterances = [
                    f"- {KNOWN_DEPTS.get(st.get('assigned_dept', ''), st.get('assigned_dept', '?'))}: "
                    f"{(st.get('result') or '')[:300]}"
                    for st in all_subtasks
                    if st.get("metadata", {}).get("discussion_round") == current_round - 1
                    and st.get("status") == "done"
                    and st.get("result")
                ]
                if prev_utterances:
                    context_text = "\n".join(prev_utterances)
                    if len(context_text) > 2000:
                        context_text = context_text[:2000] + "..."
                    prev_round_context = f"[이전 라운드 발언]\n{context_text}\n\n"
            except Exception as _ctx_e:
                logger.debug(f"[PM] 이전 라운드 컨텍스트 조회 실패 (무시): {_ctx_e}")

        for bot_id in participants:
            org = org_map.get(bot_id)
            dept_name = org.dept_name if org else bot_id
            if prev_round_context:
                prompt = (
                    f"{prev_round_context}"
                    f"{topic}\n\n"
                    f"[자유 토론 라운드 {current_round}/{max_rounds}] 당신은 {dept_name}입니다. "
                    f"위 발언들을 참고하여, 동의/반박/보완할 점을 중심으로 의견을 나눠주세요."
                )
            else:
                prompt = (
                    f"{topic}\n\n"
                    f"[자유 토론 라운드 {current_round}/{max_rounds}] 당신은 {dept_name}입니다. "
                    f"이 주제에 대해 자유롭게 의견을 나눠주세요."
                )
            tid = await self._next_task_id()
            await self._db.create_pm_task(
                task_id=tid,
                description=prompt,
                assigned_dept=bot_id,
                created_by=self._org_id,
                parent_id=parent_id,
                metadata={
                    "interaction_mode": "discussion",
                    "discussion_topic": topic,
                    "discussion_round": current_round,
                },
            )
            await self._db.update_pm_task_status(tid, "assigned")
            dept_mention = self._org_mention(bot_id)
            try:
                await self._send(
                    chat_id,
                    f"{dept_mention} [PM_TASK:{tid}|dept:{bot_id}] "
                    f"토론 라운드 {current_round} 참여 요청: {prompt[:200]}",
                )
            except Exception as _e:
                logger.warning(f"[PM] discussion round {current_round} 태스크 {tid} 알림 실패: {_e}")
            logger.info(f"[PM] discussion 라운드 {current_round} 태스크 발송: {tid} → {bot_id}")

    # ── Discussion Integration ────────────────────────────────────────────

    # 키워드 fallback용 (LLM 실패 시)
    _DISCUSSION_KEYWORDS = [
        "어떤 방식", "어떻게 할까", "선택", "비교", "vs", "논의", "토론", "결정",
        "정해", "골라", "택해", "뭐가 나을", "뭐가 좋을", "어떤 걸", "추천",
        "장단점", "트레이드오프", "tradeoff", "trade-off", "compare", "choose", "decide",
    ]

    _LLM_DISCUSSION_PROMPT = (
        "You are a project manager. Given a user request and a list of departments involved, "
        "determine if this request requires a DISCUSSION between departments before execution.\n\n"
        "A discussion is needed when:\n"
        "- Multiple departments need to AGREE on an approach before starting work\n"
        "- There are trade-offs or alternatives that departments should debate\n"
        "- A technology/design/strategy choice affects multiple departments\n"
        "- The request implies comparison, selection, or decision-making\n\n"
        "A discussion is NOT needed when:\n"
        "- Each department can work independently on their part\n"
        "- The request is straightforward with no ambiguity\n"
        "- Tasks are sequential but don't require agreement\n\n"
        "Reply with ONLY 'YES' or 'NO'. Nothing else.\n\n"
        "User request: {message}\n"
        "Departments involved: {departments}"
    )

    async def detect_discussion_needs(self, user_message: str, subtasks: list[SubTask]) -> list[DiscussionNeeded]:
        """분해 결과에서 토론이 필요한 항목을 LLM으로 감지.

        LLM 판단 실패 시 키워드 fallback.
        조건: 2개 이상 부서가 관여해야 함.
        """
        if len(subtasks) < 2:
            return []

        participants = list({st.assigned_dept for st in subtasks})
        if len(participants) < 2:
            return []

        needs_discussion = await self._llm_detect_discussion(
            user_message,
            participants,
            workdir=self._extract_workdir(user_message),
        )

        if not needs_discussion:
            return []

        # 지연 임포트 — pm_orchestrator ↔ pm_discussion_mixin 순환 임포트 방지
        from core.pm_orchestrator import DiscussionNeeded  # noqa: PLC0415
        return [DiscussionNeeded(
            topic=user_message[:100],
            proposal=user_message[:300],
            participants=participants,
        )]

    async def _llm_detect_discussion(
        self,
        user_message: str,
        participants: list[str],
        workdir: str | None = None,
    ) -> bool:
        """LLM으로 토론 필요 여부 판단. 실패 시 키워드 fallback."""
        if self._decision_client is None:
            logger.debug("[PM] LLM provider 없음 — 키워드 fallback")
            return self._keyword_detect_discussion(user_message)

        dept_names = [KNOWN_DEPTS.get(p, p) for p in participants]
        prompt = self._LLM_DISCUSSION_PROMPT.format(
            message=user_message[:500],
            departments=", ".join(dept_names),
        )

        try:
            response = await asyncio.wait_for(
                self._decision_client.complete(prompt, workdir=workdir),
                timeout=30.0,
            )
            answer = response.strip().upper()
            result = answer.startswith("YES")
            logger.info(f"[PM] LLM 토론 감지: {answer} → {result}")
            return result
        except Exception as e:
            logger.warning(f"[PM] LLM 토론 감지 실패, 키워드 fallback: {e}")
            return self._keyword_detect_discussion(user_message)

    def _keyword_detect_discussion(self, user_message: str) -> bool:
        """키워드 기반 토론 필요 여부 판단 (fallback)."""
        msg_lower = user_message.lower()
        return any(kw in msg_lower for kw in self._DISCUSSION_KEYWORDS)

    async def start_discussions(
        self, discussions: list[DiscussionNeeded],
        parent_task_id: str, chat_id: int,
    ) -> list[str]:
        """토론이 필요한 항목들에 대해 DiscussionManager로 토론 시작.

        Returns:
            생성된 discussion_id 목록.
        """
        if not self._discussion or not discussions:
            return []

        disc_ids: list[str] = []
        for dn in discussions:
            disc = await self._discussion.start_discussion(
                topic=dn.topic,
                initial_proposal=dn.proposal,
                from_dept=self._org_id,
                participants=dn.participants,
                parent_task_id=parent_task_id,
                chat_id=chat_id,
            )
            disc_ids.append(disc["id"])
            logger.info(f"[PM] 토론 시작: {disc['id']} — {dn.topic[:50]}")

        return disc_ids

    # ── Debate Dispatch ───────────────────────────────────────────────────

    def _select_debate_participants(self, dept_hints: list[str], topic: str) -> list[str]:
        """debate 참여 봇 목록 선정.

        dept_hints가 주어지면 최대 4개까지 그대로 사용.
        비어있으면 orchestration config에서 specialist + enabled 봇을 최대 4개 선택.
        최소 2개 미만이면 빈 리스트 반환 (debate 불가).
        """
        if dept_hints:
            selected = dept_hints[:4]
        else:
            try:
                cfg = load_orchestration_config(force_reload=True)
                selected = [org.id for org in cfg.list_specialist_orgs()][:4]
            except Exception as e:
                logger.warning(f"[PM] debate 참여자 조회 실패: {e}")
                selected = []

        if len(selected) < 2:
            logger.info(f"[PM] debate 참여자 부족 ({len(selected)}개) — debate 불가")
            return []
        return selected

    async def debate_dispatch(
        self,
        parent_task_id: str,
        topic: str,
        participants: list[str],
        chat_id: int,
    ) -> list[str]:
        """각 participant에게 독자적 관점의 debate 서브태스크를 생성·배정한다.

        Args:
            parent_task_id: 상위 태스크 ID.
            topic: debate 주제 (사용자 요청 원문).
            participants: 참여할 봇 ID 목록 (_select_debate_participants 결과).
            chat_id: 알림을 보낼 Telegram chat ID.

        Returns:
            생성된 subtask ID 목록. 참여자가 없으면 빈 리스트.
        """
        if not participants:
            logger.info("[PM] debate 참여자 없음 — debate_dispatch 건너뜀")
            return []

        # 봇 프로필 캐시 (dept_name, direction 조회용)
        try:
            cfg = load_orchestration_config(force_reload=True)
            org_map = {org.id: org for org in cfg.list_orgs()}
        except Exception as e:
            logger.warning(f"[PM] debate org_map 로드 실패: {e}")
            org_map = {}

        task_ids: list[str] = []
        for bot_id in participants:
            org = org_map.get(bot_id)
            dept_name = org.dept_name if org else bot_id
            direction = org.direction if org else ""

            prompt = (
                f"{topic}\n\n"
                f"[당신의 관점] 당신은 {dept_name}입니다. {direction}\n"
                f"다른 부서와 차별화된 {dept_name} 관점에서 의견을 제시하세요. "
                f"반드시 자신의 전문 영역과 가치관을 바탕으로 독자적인 입장을 표명하세요."
            )

            tid = await self._next_task_id()
            await self._db.create_pm_task(
                task_id=tid,
                description=prompt,
                assigned_dept=bot_id,
                created_by=self._org_id,
                parent_id=parent_task_id,
                metadata={
                    "debate": True,
                    "debate_topic": topic,
                    "debate_parent": parent_task_id,
                },
            )
            await self._db.update_pm_task_status(tid, "assigned")
            task_ids.append(tid)

            dept_mention = self._org_mention(bot_id)
            try:
                await self._send(
                    chat_id,
                    f"{dept_mention} [PM_TASK:{tid}|dept:{bot_id}] {dept_name} debate 배정: "
                    f"{prompt[:200]}",
                )
            except Exception as _e:
                logger.warning(f"[PM] debate 태스크 {tid} 알림 전송 실패: {_e}")
            logger.info(f"[PM] debate 태스크 발송: {tid} → {bot_id}")

        # 부모 태스크 metadata 업데이트
        await self._db.update_pm_task_metadata(
            parent_task_id,
            {"debate": True, "debate_topic": topic},
        )

        return task_ids

    async def collab_dispatch(
        self,
        parent_task_id: str,
        task: str,
        target_org: str,
        requester_org: str,
        context: str = "",
        chat_id: int = 0,
    ) -> str:
        """요청 봇이 지정한 target_org에 collab 서브태스크를 생성·배정한다.

        Args:
            parent_task_id: 상위 태스크 ID.
            task: 협업 요청 태스크 내용.
            target_org: 태스크를 수행할 조직 ID.
            requester_org: 협업을 요청한 조직 ID.
            context: 추가 컨텍스트 (선택).
            chat_id: 알림 Telegram chat ID (미사용, 향후 확장용).

        Returns:
            생성된 task_id 문자열.
        """
        try:
            cfg = load_orchestration_config(force_reload=True)
            org_map = {org.id: org for org in cfg.list_orgs()}
        except Exception as e:
            logger.warning(f"[PM] collab_dispatch org_map 로드 실패: {e}")
            org_map = {}

        org = org_map.get(target_org)
        dept_name = org.dept_name if org else target_org
        direction = org.direction if org else ""

        description_parts = [task]
        if context:
            description_parts.append(f"\n[요청 컨텍스트] {context}")
        if direction:
            description_parts.append(
                f"\n[{dept_name} 전문 영역] {direction}"
            )
        description = "".join(description_parts)

        task_id = await self._next_task_id()
        await self._db.create_pm_task(
            task_id=task_id,
            description=description,
            assigned_dept=target_org,
            created_by=requester_org,
            parent_id=parent_task_id,
            metadata={
                "collab": True,
                "collab_requester": requester_org,
                "parent_task_id": parent_task_id,
            },
        )
        logger.info(
            f"[PM] collab_dispatch: {requester_org} -> {target_org} | task_id={task_id}"
        )
        return task_id

    async def discussion_dispatch(
        self,
        topic: str,
        dept_hints: list[str],
        chat_id: int,
        rounds: int = 3,
    ) -> list[str]:
        """자유 토론 모드 — PM 약한 진행, 강제 결론 없음.

        debate_dispatch와 달리 관점 대립 유도 없이 자유 발언.
        부모 태스크를 내부에서 생성한다 (relay가 _db에 직접 접근 불필요).

        # TODO(cycle-6): 서브태스크 타임아웃/스탈니스 체커 추가.
        """
        participants = list(dict.fromkeys(dept_hints))[:4]
        if len(participants) < 2:
            try:
                cfg = load_orchestration_config(force_reload=True)
                participants = [o.id for o in cfg.list_specialist_orgs()][:4]
            except Exception as _e:
                logger.warning(f"[PM] discussion specialist org 로드 실패: {_e}")

        if len(participants) < 2:
            logger.info("[PM] discussion 참여자 부족 — discussion_dispatch 건너뜀")
            return []

        # 부모 태스크 내부 생성 (relay가 _db에 직접 접근 금지)
        parent_id = await self._next_task_id()
        await self._db.create_pm_task(
            task_id=parent_id,
            description=topic,
            assigned_dept=self._org_id,
            created_by=self._org_id,
            metadata={
                "interaction_mode": "discussion",
                "discussion_topic": topic,
                "discussion_rounds": rounds,
                "discussion_current_round": 1,
                "discussion_participants": participants,
            },
        )

        try:
            cfg = load_orchestration_config(force_reload=True)
            org_map = {org.id: org for org in cfg.list_orgs()}
        except Exception as e:
            logger.warning(f"[PM] discussion org_map 로드 실패: {e}")
            org_map = {}

        task_ids: list[str] = []
        for bot_id in participants:
            org = org_map.get(bot_id)
            dept_name = org.dept_name if org else bot_id

            prompt = (
                f"{topic}\n\n"
                f"[자유 토론] 당신은 {dept_name}입니다. "
                f"이 주제에 대해 자유롭게 의견을 나눠주세요."
            )

            tid = await self._next_task_id()
            await self._db.create_pm_task(
                task_id=tid,
                description=prompt,
                assigned_dept=bot_id,
                created_by=self._org_id,
                parent_id=parent_id,
                metadata={"interaction_mode": "discussion", "discussion_topic": topic, "discussion_round": 1},
            )
            await self._db.update_pm_task_status(tid, "assigned")
            task_ids.append(tid)

            dept_mention = self._org_mention(bot_id)
            try:
                await self._send(
                    chat_id,
                    f"{dept_mention} [PM_TASK:{tid}|dept:{bot_id}] "
                    f"토론 참여 요청: {prompt[:200]}",
                )
            except Exception as _e:
                logger.warning(f"[PM] discussion 태스크 {tid} 알림 실패: {_e}")
            logger.info(f"[PM] discussion 태스크 발송: {tid} → {bot_id}")

        return task_ids
