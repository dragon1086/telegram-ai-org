"""PMSynthesisMixin — 결과 합성 및 COLLAB 트리거 관련 메서드 모음.

PMOrchestrator에서 분리된 Mixin 클래스.
이 파일의 모든 메서드는 self가 PMOrchestrator 인스턴스임을 전제로 한다.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from core.constants import KNOWN_DEPTS
from core.orchestration_config import load_orchestration_config
from core.orchestration_runbook import OrchestrationRunbook
from core.result_synthesizer import SynthesisJudgment
from core.telegram_user_guardrail import ensure_user_friendly_output, extract_local_artifact_paths

if TYPE_CHECKING:
    pass


class PMSynthesisMixin:
    """결과 합성·COLLAB 트리거·stale 체크 기능 Mixin.

    PMOrchestrator가 이 Mixin을 상속한다.
    self._db, self._send, self._synthesizer, self._decision_client,
    self._org_id, self._collab_dedup, self._next_task_id, self._org_mention,
    self.dispatch, self.collab_dispatch, self._debate_synthesize,
    self._discussion_summarize 등은 PMOrchestrator/다른 Mixin에서 제공된다.
    """

    async def _fire_collab_triggers(
        self, task_id: str, result: str, chat_id: int
    ) -> None:
        """orchestration.yaml collab_triggers 기반 자동 크로스팀 태스크 생성.

        완료된 task_id의 assigned_dept + task_type을 읽어 매칭 트리거를 찾고,
        dedup 창 안에 이미 발동된 조합은 건너뛴다.
        """
        import time

        try:
            task_info = await self._db.get_pm_task(task_id)
            if not task_info:
                return

            source_dept = task_info.get("assigned_dept") or ""
            # task_type은 metadata에 저장됨 (예: "기획", "구현", "리서치" 등)
            task_meta = task_info.get("metadata") or {}
            task_type = task_meta.get("task_type") or ""
            task_description = task_info.get("description") or ""

            if not source_dept:
                return

            # collab 태스크 자체가 또 트리거를 발동하는 순환 방지
            if task_meta.get("collab"):
                return

            cfg = load_orchestration_config(force_reload=False)
            # task_type 저장값 우선, 없으면 description 키워드로 폴백
            triggers = cfg.get_collab_triggers(source_dept, task_type)
            if not triggers and task_description:
                triggers = cfg.get_collab_triggers_by_description(source_dept, task_description)
            if not triggers:
                return

            source_dept_name = KNOWN_DEPTS.get(source_dept, source_dept)
            result_summary = result[:300] if result else "(결과 없음)"
            now = time.monotonic()

            for trigger in triggers:
                for target_dept in trigger.target_depts:
                    dedup_key = (task_id, target_dept)
                    last_fired = self._collab_dedup.get(dedup_key)
                    dedup_window_sec = trigger.dedup_window_minutes * 60

                    # 중복 트리거 억제 (같은 source_task_id → 같은 target_dept)
                    if last_fired is not None and (now - last_fired) < dedup_window_sec:
                        logger.info(
                            f"[COLLAB-TRIGGER] dedup 억제: {task_id} → {target_dept} "
                            f"(마지막 발동 {int(now - last_fired)}초 전)"
                        )
                        continue

                    # 대상 부서가 존재하는지 확인
                    org = cfg.get_org(target_dept)
                    if org is None:
                        logger.warning(
                            f"[COLLAB-TRIGGER] 대상 부서 없음: {target_dept} (trigger={trigger.id})"
                        )
                        continue

                    target_role = org.role or org.dept_name

                    # 메시지 생성
                    task_description = trigger.render_message(
                        source_dept=source_dept_name,
                        source_task_id=task_id,
                        result_summary=result_summary,
                        target_role=target_role,
                    )

                    # 후속 태스크 생성 (collab_dispatch 재사용)
                    new_task_id = await self.collab_dispatch(
                        parent_task_id=task_id,
                        task=task_description,
                        target_org=target_dept,
                        requester_org=source_dept,
                        context=f"[자동 COLLAB 트리거: {trigger.id}]",
                        chat_id=chat_id,
                    )

                    # 태스크 할당 상태 업데이트
                    await self._db.update_pm_task_status(new_task_id, "assigned")

                    # 대상 부서에 알림 발송
                    dept_mention = self._org_mention(target_dept)
                    target_dept_name = KNOWN_DEPTS.get(target_dept, target_dept)
                    notify_msg = (
                        f"{dept_mention} [PM_TASK:{new_task_id}|dept:{target_dept}] "
                        f"{target_dept_name}에 자동 배정 (COLLAB: {trigger.id})\n"
                        f"태스크 유형: 협업\n"
                        f"파일·코드 변경 허용: 예\n"
                        f"{task_description[:400]}"
                    )
                    try:
                        await self._send(chat_id, notify_msg)
                    except Exception as _send_err:
                        logger.warning(
                            f"[COLLAB-TRIGGER] 알림 전송 실패 (태스크는 생성됨): {_send_err}"
                        )

                    # dedup 캐시 기록
                    self._collab_dedup[dedup_key] = now

                    logger.info(
                        f"[COLLAB-TRIGGER] 발동: {trigger.id} | "
                        f"{source_dept} ({task_type}) → {target_dept} | "
                        f"new_task_id={new_task_id}"
                    )

        except Exception as _e:
            # COLLAB 트리거 실패는 메인 태스크 완료를 막지 않는다
            logger.warning(f"[COLLAB-TRIGGER] 처리 중 오류 (무시): {_e}")

    async def consolidate_results(self, parent_task_id: str) -> str:
        """부모 태스크의 완료된 서브태스크 결과를 단순 요약 문자열로 합친다."""
        subtasks = await self._db.get_subtasks(parent_task_id)
        lines: list[str] = []
        for task in subtasks:
            dept = task.get("assigned_dept") or "unknown"
            dept_name = KNOWN_DEPTS.get(dept, dept)
            result = (task.get("result") or "").strip() or "(결과 없음)"
            lines.append(f"[{dept_name}] {result}")
        return "\n".join(lines)

    async def _check_stale_subtasks(
        self, parent_id: str, stale_threshold_sec: float = 300.0,
    ) -> list[str]:
        """assigned 상태인 채로 threshold 이상 지난 서브태스크 ID 반환 + 경고 로그."""
        from datetime import UTC, datetime, timedelta
        try:
            subtasks = await self._db.get_subtasks(parent_id)
        except Exception as _e:
            logger.debug(f"[PM] stale check 실패 (무시): {_e}")
            return []

        stale_ids: list[str] = []
        cutoff = datetime.now(UTC) - timedelta(seconds=stale_threshold_sec)

        for st in subtasks:
            if st.get("status") != "assigned":
                continue
            updated_raw = st.get("updated_at") or st.get("created_at", "")
            if not updated_raw:
                continue
            try:
                updated = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=UTC)
                if updated < cutoff:
                    stale_ids.append(st["id"])
                    logger.warning(
                        f"[PM] stale 서브태스크 감지: {st['id']} "
                        f"(assigned {int((datetime.now(UTC) - updated).total_seconds())}초 전)"
                    )
            except (ValueError, TypeError):
                pass

        return stale_ids

    async def _synthesize_and_act(
        self,
        parent_task_id: str,
        subtasks: list[dict],
        chat_id: int,
        _skip_discussion_gate: bool = False,
    ) -> None:
        """부서 결과를 합성하고 판단에 따라 후속 조치.

        _skip_discussion_gate=True 는 _discussion_summarize 최종 라운드에서
        재귀 호출 없이 전체 synthesis를 수행할 때만 사용한다.
        """
        from core.pm_orchestrator import MAX_REWORK_RETRIES, SubTask, aggregate_results, should_delegate_further

        # 원래 요청 복원
        parent = await self._db.get_pm_task(parent_task_id)
        original_request = parent["description"][:1500] if parent else ""

        parent_meta = parent.get("metadata", {}) if parent else {}
        # 스탈니스 체크 — assigned 상태로 오래된 서브태스크 경고
        stale = await self._check_stale_subtasks(parent_task_id)
        if stale:
            logger.warning(f"[PM] _synthesize_and_act {parent_task_id}: stale 서브태스크 {stale}")
        if parent_meta.get("debate"):
            await self._debate_synthesize(parent_task_id, parent_meta, subtasks, chat_id)
            return

        if parent_meta.get("interaction_mode") == "discussion" and not _skip_discussion_gate:
            await self._discussion_summarize(parent_task_id, subtasks, chat_id)
            return

        # ── COLLAB 재진입 Judgment Gate ─────────────────────────────────────
        # COLLAB 서브태스크가 있으면 각 결과를 PMJudgmentGate로 평가한다.
        # APPROVE → 기존 합성 진행, REJECT → 동일 부서 재작업, REROUTE → 타 부서 디스패치
        collab_subtasks = [s for s in subtasks if (s.get("metadata") or {}).get("collab")]
        if collab_subtasks:
            try:
                from core.pm_judgment_gate import JudgmentVerdict, PMJudgmentGate
                gate = PMJudgmentGate()
                rework_dispatched = False
                for st in collab_subtasks:
                    st_result = (st.get("result") or "").strip()
                    st_desc = st.get("description") or ""
                    st_meta = st.get("metadata") or {}
                    judgment = await gate.evaluate(
                        task_description=st_desc,
                        result=st_result,
                        context=st_meta.get("collab_context", ""),
                        decision_client=self._decision_client,
                    )
                    logger.info(
                        f"[PMJudgmentGate] {st.get('id', '?')} → {judgment.verdict.value}: {judgment.reasoning}"
                    )
                    if judgment.verdict == JudgmentVerdict.REJECT:
                        # 동일 부서 재작업 디스패치
                        rework_task_id = await self._next_task_id()
                        rework_desc = (
                            f"[재작업 요청] 이전 결과가 불충분합니다.\n"
                            f"사유: {judgment.reasoning}\n"
                            f"보완 지시: {judgment.rework_prompt}\n\n"
                            f"원본 태스크: {st_desc[:300]}"
                        )
                        await self._db.create_pm_task(
                            task_id=rework_task_id,
                            description=rework_desc,
                            assigned_dept=st.get("assigned_dept", ""),
                            created_by=self._org_id,
                            parent_id=parent_task_id,
                            metadata={
                                "collab": True,
                                "collab_rework": True,
                                "original_subtask_id": st.get("id", ""),
                            },
                        )
                        await self._send(
                            chat_id,
                            f"⚠️ [PMJudgmentGate] 결과 불충분 → {st.get('assigned_dept','?')} 재작업 배정\n"
                            f"사유: {judgment.reasoning}",
                        )
                        rework_dispatched = True
                        logger.info(f"[PMJudgmentGate] REJECT → 재작업 {rework_task_id} 생성")
                    elif judgment.verdict == JudgmentVerdict.REROUTE and judgment.suggested_dept:
                        # 타 부서 재라우팅
                        reroute_task_id = await self.collab_dispatch(
                            parent_task_id=parent_task_id,
                            task=st_desc,
                            target_org=judgment.suggested_dept,
                            requester_org=self._org_id,
                            context=f"[PMJudgmentGate 재라우팅] {judgment.reasoning}",
                            chat_id=chat_id,
                        )
                        await self._send(
                            chat_id,
                            f"🔀 [PMJudgmentGate] 재라우팅 → {judgment.suggested_dept}\n"
                            f"사유: {judgment.reasoning}",
                        )
                        rework_dispatched = True
                        logger.info(f"[PMJudgmentGate] REROUTE → {judgment.suggested_dept} | {reroute_task_id}")
                if rework_dispatched:
                    # 재작업/재라우팅이 생겼으면 현재 합성 중단 (완료 후 재합성)
                    return
            except Exception as _gate_err:
                logger.warning(f"[PMJudgmentGate] 게이트 처리 중 오류 (무시, 합성 계속): {_gate_err}")
        # ── /COLLAB 재진입 Judgment Gate ─────────────────────────────────────

        synthesis = await self._synthesizer.synthesize(original_request, subtasks)
        logger.info(
            f"[PM] 결과 합성: {parent_task_id} → {synthesis.judgment.value}"
        )
        parent_workdir = parent_meta.get("workdir")
        run_id = parent_meta.get("run_id")
        runbook = OrchestrationRunbook(Path(__file__).resolve().parent.parent)
        # LLM 합성 성공 시 unified_report 사용, 실패(keyword fallback) 시 subtask 원본 결과 직접 전달
        full_results = "\n\n".join(
            f"## {KNOWN_DEPTS.get(st.get('assigned_dept', ''), st.get('assigned_dept', '?'))}\n"
            f"{(st.get('result') or '').lstrip('-').strip()}"
            for st in subtasks
            if st.get("result")
        )
        report_text = synthesis.unified_report or full_results or synthesis.summary
        # 합성 LLM 성공 시 이미 구조화된 보고서 → full_context 불필요 (이중 재작성 방지).
        # 합성 fallback(keyword) 시에만 full_results를 context로 전달해 재구조화.
        _synthesis_succeeded = bool(synthesis.unified_report)
        user_friendly_report = await ensure_user_friendly_output(
            report_text,
            original_request=original_request,
            full_context="" if _synthesis_succeeded else full_results,
            decision_client=self._decision_client,
        )
        artifact_path = self._write_unified_report_artifact(
            parent_task_id,
            original_request,
            user_friendly_report,
            subtasks,
        )

        # 첨부 파일 경로 수집: LLM 선별 우선, 없으면 정규식 fallback
        seen_paths: set[str] = set()
        subtask_artifact_markers = ""
        if synthesis.artifact_paths:
            # LLM이 사용자에게 보낼 파일을 직접 선별한 경우
            for path in synthesis.artifact_paths:
                if path not in seen_paths:
                    seen_paths.add(path)
                    subtask_artifact_markers += f"\n[ARTIFACT:{path}]"
        else:
            # fallback: subtask result에서 경로 자동 추출
            for st in subtasks:
                for path in extract_local_artifact_paths(st.get("result") or ""):
                    if path not in seen_paths:
                        seen_paths.add(path)
                        subtask_artifact_markers += f"\n[ARTIFACT:{path}]"

        # 사용자가 볼 수 있는 산출물 목록 (ARTIFACT 마커와 별도로 채팅에 표시)
        _extra_paths = [
            m.split("[ARTIFACT:")[1].rstrip("]")
            for m in subtask_artifact_markers.split("\n")
            if "[ARTIFACT:" in m
        ]
        _all_artifact_paths = [artifact_path] + _extra_paths
        _artifact_names = [Path(p).name for p in _all_artifact_paths if p]
        _artifact_list_note = (
            f"\n\n📎 첨부 산출물 ({len(_artifact_names)}개): "
            + ", ".join(f"`{n}`" for n in _artifact_names)
        ) if _artifact_names else ""

        # 팀 구성 헤더 — 미렌더링 (T-aiorg_pm_bot-700)
        # 사용자 요청에 따라 PM 위임 보고서에서 팀 구성 헤더를 표시하지 않도록 변경.
        _synthesis_team_header = ""

        if synthesis.judgment == SynthesisJudgment.SUFFICIENT:
            report = _synthesis_team_header + user_friendly_report
            _artifact_suffix = (
                f"\n\n---\n📎 첨부: {', '.join(f'`{Path(p).name}`' for p in _all_artifact_paths if p)}"
                if _all_artifact_paths else ""
            )
            # 투입 페르소나는 각 조직 자체 보고에 기재 — PM 최종 합산 보고에는 포함하지 않음
            await self._send(
                chat_id,
                f"{report}{_artifact_suffix}\n[ARTIFACT:{artifact_path}]{subtask_artifact_markers}",
            )
            if run_id:
                try:
                    runbook.advance_phase(run_id, note="조직 협업 결과 통합 완료, verification phase 이동")
                    runbook.advance_phase(run_id, note="피드백 phase 이동")
                    runbook.advance_phase(run_id, note="delegated run 완료")
                except Exception as e:
                    logger.warning(f"[PM] runbook 완료 처리 실패 ({run_id}): {e}")
            # 허위 접수 주장 감지: 보고서에 "접수했습니다" 썼지만 실제 FOLLOW_UP 없는 경우 사용자에게 알림
            if synthesis.false_claim_detected:
                await self._send(
                    chat_id,
                    "⚠️ **보고서 불일치 감지**: 보고서에 후속 태스크를 접수했다고 기재되어 있으나 "
                    "실제 등록된 태스크가 없습니다. 보고서 내용을 검토하고 필요한 작업을 명시적으로 요청해 주세요.",
                )
            # 2-pass 위임 판단: synthesis FOLLOW_UP 라인 + 보고서 내 COLLAB 태그 통합 처리
            # should_delegate_further()가 두 소스를 합산·중복 제거하여 반환한다.
            _follow_up_all = should_delegate_further(synthesis, user_friendly_report)
            if _follow_up_all:
                follow_ups = [
                    SubTask(
                        description=ft["description"],
                        assigned_dept=ft["dept"],
                        workdir=parent_workdir,
                    )
                    for ft in _follow_up_all
                ]
                _2pass_depts = ", ".join(
                    sorted({ft["dept"] for ft in _follow_up_all})
                )
                await self._send(
                    chat_id,
                    f"📋 2-pass 추가 위임: {len(follow_ups)}건 자동 실행 중... ({_2pass_depts})",
                )
                # aggregate_results 로그 (디버깅·감사용)
                logger.info(
                    aggregate_results(subtasks, follow_ups, original_request)[:400]
                )
                await self._db.update_pm_task_status(
                    parent_task_id, "done", result=report,
                )
                await self.dispatch(parent_task_id, follow_ups, chat_id)
            else:
                await self._db.update_pm_task_status(
                    parent_task_id, "done", result=report,
                )
            # Goal(G-*) parent는 pm_goals 테이블도 업데이트해야
            # SynthesisPoller가 재합성 루프에 빠지지 않는다.
            if parent_task_id.startswith("G-"):
                try:
                    await self._db.update_goal(parent_task_id, status="completed")
                    logger.info(f"[PM] Goal {parent_task_id} → completed")
                except Exception as _ge:
                    logger.warning(f"[PM] Goal 상태 업데이트 실패 {parent_task_id}: {_ge}")
        elif synthesis.judgment == SynthesisJudgment.INSUFFICIENT:
            rework_count = int(parent_meta.get("rework_count", 0))
            if run_id:
                try:
                    runbook.advance_phase(run_id, note="결과 부족으로 verification phase에서 추가 작업 필요")
                except Exception as e:
                    logger.warning(f"[PM] runbook 진행 실패 ({run_id}): {e}")
            if rework_count < MAX_REWORK_RETRIES:
                # 재작업 루프: parent는 "running" 유지 (done으로 마킹하지 않음)
                new_rework_count = rework_count + 1
                await self._db.update_pm_task_metadata(
                    parent_task_id, {"rework_count": new_rework_count}
                )
                try:
                    await self._send(
                        chat_id,
                        f"⚠️ 결과 부족 — 추가 작업 배분 중... (재작업 {new_rework_count}/{MAX_REWORK_RETRIES})\n"
                        f"사유: {synthesis.reasoning}\n\n{_synthesis_team_header}{user_friendly_report}\n\n"
                        f"현재까지의 통합 보고서를 첨부합니다.\n[ARTIFACT:{artifact_path}]{subtask_artifact_markers}",
                    )
                except Exception as _send_err:
                    logger.warning(
                        f"[PM] INSUFFICIENT 알림 전송 실패 ({parent_task_id}), "
                        f"재작업 배분 계속 진행: {_send_err}"
                    )
                if synthesis.follow_up_tasks:
                    follow_ups = [
                        SubTask(
                            description=ft["description"],
                            assigned_dept=ft["dept"],
                            workdir=parent_workdir,
                        )
                        for ft in synthesis.follow_up_tasks
                    ]
                else:
                    # LLM이 follow-up을 안 줬으면 완료된 서브태스크를 "보완 필요" 프롬프트로 재발행
                    follow_ups = [
                        SubTask(
                            description=(
                                f"[보완 필요] {st.get('metadata', {}).get('original_description', st.get('description', ''))}\n\n"
                                f"이전 결과가 충분하지 않습니다. 더 구체적이고 완성도 높은 결과를 제출해주세요.\n"
                                f"이전 결과 요약: {(st.get('result') or '')[:200]}"
                            ),
                            assigned_dept=st["assigned_dept"],
                            workdir=parent_workdir,
                        )
                        for st in subtasks
                        if st.get("assigned_dept") and st.get("status") == "done"
                    ]
                if follow_ups:
                    # parent를 "running" 상태로 유지한 채 follow-up 서브태스크 발행
                    await self.dispatch(parent_task_id, follow_ups, chat_id)
                else:
                    logger.warning(f"[PM] INSUFFICIENT retry {parent_task_id}: follow-up 없음, done 처리")
                    await self._db.update_pm_task_status(
                        parent_task_id, "done", result=synthesis.summary,
                    )
                    if parent_task_id.startswith("G-"):
                        try:
                            await self._db.update_goal(parent_task_id, status="completed")
                            logger.info(f"[PM] Goal {parent_task_id} → completed (insufficient, no follow-up)")
                        except Exception as _ge:
                            logger.warning(f"[PM] Goal 상태 업데이트 실패 {parent_task_id}: {_ge}")
            else:
                # 최대 재시도 횟수 도달 — 최선의 결과로 done 처리
                try:
                    await self._send(
                        chat_id,
                        f"⚠️ 자동 보완 한계 ({MAX_REWORK_RETRIES}회) 도달. 현재 최선의 결과를 전달합니다.\n\n"
                        f"{_synthesis_team_header}{user_friendly_report}\n\n통합 보고서를 첨부합니다.\n[ARTIFACT:{artifact_path}]{subtask_artifact_markers}",
                    )
                except Exception as _send_err:
                    logger.warning(
                        f"[PM] INSUFFICIENT 최종 알림 전송 실패 ({parent_task_id}), "
                        f"done 처리 계속 진행: {_send_err}"
                    )
                await self._db.update_pm_task_status(
                    parent_task_id, "done", result=synthesis.summary,
                )
                if parent_task_id.startswith("G-"):
                    try:
                        await self._db.update_goal(parent_task_id, status="max_iterations_reached")
                        logger.info(f"[PM] Goal {parent_task_id} → max_iterations_reached (insufficient)")
                    except Exception as _ge:
                        logger.warning(f"[PM] Goal 상태 업데이트 실패 {parent_task_id}: {_ge}")
        elif synthesis.judgment == SynthesisJudgment.CONFLICTING:
            await self._send(
                chat_id,
                f"⚠️ 부서 간 결과 충돌 감지\n"
                f"사유: {synthesis.reasoning}\n\n{_synthesis_team_header}{user_friendly_report}\n\n"
                f"조율이 필요합니다.\n현재 통합 보고서를 첨부합니다.\n[ARTIFACT:{artifact_path}]{subtask_artifact_markers}",
            )
            if run_id:
                try:
                    runbook.advance_phase(run_id, note="결과 충돌로 verification phase에서 정지")
                except Exception as e:
                    logger.warning(f"[PM] runbook 진행 실패 ({run_id}): {e}")
            await self._db.update_pm_task_status(
                parent_task_id, "needs_review", result=synthesis.summary,
            )
            # Goal도 needs_review로 업데이트 → SynthesisPoller 무한루프 방지
            if parent_task_id.startswith("G-"):
                try:
                    await self._db.update_goal(parent_task_id, status="needs_review")
                    logger.info(f"[PM] Goal {parent_task_id} → needs_review (conflicting)")
                except Exception as _ge:
                    logger.warning(f"[PM] Goal 상태 업데이트 실패 {parent_task_id}: {_ge}")
        else:  # NEEDS_INTEGRATION
            report = _synthesis_team_header + user_friendly_report
            _artifact_suffix = (
                f"\n\n---\n📎 첨부: {', '.join(f'`{Path(p).name}`' for p in _all_artifact_paths if p)}"
                if _all_artifact_paths else ""
            )
            await self._send(
                chat_id,
                f"{report}{_artifact_suffix}\n[ARTIFACT:{artifact_path}]{subtask_artifact_markers}",
            )
            if run_id:
                try:
                    runbook.advance_phase(run_id, note="통합 보고서 작성 완료, verification phase 이동")
                    runbook.advance_phase(run_id, note="피드백 phase 이동")
                    runbook.advance_phase(run_id, note="delegated run 완료")
                except Exception as e:
                    logger.warning(f"[PM] runbook 완료 처리 실패 ({run_id}): {e}")
            await self._db.update_pm_task_status(
                parent_task_id, "done", result=report,
            )
            # Goal(G-*) parent는 pm_goals 테이블도 업데이트 (SynthesisPoller 재합성 루프 방지)
            if parent_task_id.startswith("G-"):
                try:
                    await self._db.update_goal(parent_task_id, status="completed")
                    logger.info(f"[PM] Goal {parent_task_id} → completed (needs_integration)")
                except Exception as _ge:
                    logger.warning(f"[PM] Goal 상태 업데이트 실패 {parent_task_id}: {_ge}")
