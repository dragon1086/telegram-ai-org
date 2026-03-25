"""telegram_sender.py — 텔레그램 전송 전용 모듈 (Phase 1a 분리).

telegram_relay.py에서 전송 관련 순수 함수들을 추출한 모듈.
기존 TelegramRelay 클래스의 전송 메서드는 이 모듈 함수를 호출하는 thin wrapper로 전환.

Feature Flag: ENABLE_REFACTORED_SENDER (기본값: True)
"""
from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

ENABLE_REFACTORED_SENDER = os.environ.get("ENABLE_REFACTORED_SENDER", "1") == "1"


async def auto_upload(
    response: str,
    token: str,
    chat_id: int,
    org_id: str,
    uploaded_artifacts: set[str],
) -> None:
    """응답 내 생성 파일 경로를 감지해 텔레그램으로 업로드.

    Args:
        response: 에이전트 응답 텍스트 (파일 경로 포함 가능)
        token: 봇 토큰
        chat_id: 채팅방 ID
        org_id: 조직 ID (로깅용)
        uploaded_artifacts: 이미 업로드된 경로 집합 (중복 방지, 변경됨)
    """
    from core.artifact_pipeline import prepare_upload_bundle
    from core.telegram_delivery import resolve_delivery_target
    from core.telegram_user_guardrail import extract_local_artifact_paths
    from tools.telegram_uploader import upload_file

    target = resolve_delivery_target(org_id)
    if target is None:
        logger.warning(f"[auto_upload:{org_id}] configured target 없음 — passed token/chat_id 사용")
        safe_token = token
        safe_chat_id = int(chat_id)
    else:
        safe_token = target.token
        safe_chat_id = target.chat_id
        if token != safe_token or int(chat_id) != safe_chat_id:
            logger.warning(f"[auto_upload:{org_id}] 전달 대상 불일치 감지, configured target 사용")

    candidates = extract_local_artifact_paths(response or "")
    if not candidates:
        logger.info(
            f"[auto_upload:{org_id}] 업로드 후보 경로 없음 "
            f"(응답 길이={len(response or '')}) — 첨부파일 없이 종료"
        )
        return

    seen: set[str] = set()
    uploaded_count = 0
    for raw in candidates:
        path_text = os.path.expanduser(raw.strip())
        if path_text in seen:
            continue
        if path_text in uploaded_artifacts:
            logger.debug(f"[auto_upload:{org_id}] 중복 업로드 스킵: {path_text}")
            continue
        seen.add(path_text)
        path = Path(path_text)
        bundle = prepare_upload_bundle(path)
        if not bundle:
            logger.warning(
                f"[auto_upload:{org_id}] 파일 없음(경로 탐지됐으나 디스크에 없음): {path_text}"
            )
            continue
        for artifact in bundle:
            try:
                await upload_file(
                    safe_token,
                    safe_chat_id,
                    str(artifact),
                    f"📎 {org_id} 산출물: {artifact.name}",
                )
                uploaded_artifacts.add(path_text)
                uploaded_count += 1
            except Exception as exc:
                logger.warning(f"[auto_upload:{org_id}] 업로드 실패 {artifact}: {exc}")
    logger.info(f"[auto_upload:{org_id}] 완료 — 후보 {len(candidates)}건 / 업로드 {uploaded_count}건")


async def upload_artifacts_to(
    result: str,
    token: str,
    chat_id: int,
    org_id: str,
    uploaded_artifacts: set[str],
) -> None:
    """Cross-org artifact upload — resolve_delivery_target 우회, 직접 지정 token/chat_id 사용.

    Args:
        result: 결과 텍스트 (파일 경로 포함 가능)
        token: 대상 봇 토큰
        chat_id: 대상 채팅방 ID
        org_id: 소스 조직 ID (파일 캡션용)
        uploaded_artifacts: 이미 업로드된 경로 집합 (중복 방지, 변경됨)
    """
    from core.artifact_pipeline import prepare_upload_bundle
    from core.telegram_user_guardrail import extract_local_artifact_paths
    from tools.telegram_uploader import upload_file

    for raw in extract_local_artifact_paths(result):
        for p in prepare_upload_bundle(raw):
            p_str = str(p)
            if p_str not in uploaded_artifacts:
                caption = f"📎 {org_id} 산출물: {p.name}"
                await upload_file(token, int(chat_id), p_str, caption)
                uploaded_artifacts.add(p_str)


async def send_chunked_message(
    bot,
    display,
    chat_id: int,
    text: str,
    org_id: str,
    context_db=None,
    reply_to_message_id: int | None = None,
) -> object | None:
    """4000자 초과 메시지를 split_message로 분할 전송.

    Args:
        bot: telegram.Bot 인스턴스
        display: DisplayLimiter 인스턴스
        chat_id: 채팅방 ID
        text: 전송할 텍스트 (ARTIFACT_MARKER 포함 가능)
        org_id: 조직 ID
        context_db: ContextDB (메시지 envelope 저장용, None이면 저장 생략)
        reply_to_message_id: 답장 대상 메시지 ID

    Returns:
        마지막 전송된 메시지 객체 또는 None
    """
    import re

    from core.message_envelope import EnvelopeManager, MessageEnvelope
    from core.telegram_formatting import split_message

    ARTIFACT_MARKER_RE = re.compile(r"\[ARTIFACT:([^\]]+)\]")

    raw = ARTIFACT_MARKER_RE.sub("", text).strip() or "첨부 파일을 전송합니다."
    env = MessageEnvelope.wrap(content=raw, sender_bot=org_id, intent="DIRECT_REPLY")
    visible_text = env.to_display()
    sent = None
    first = True
    for chunk in split_message(visible_text, 3800):
        sent = await display.send_to_chat(
            bot,
            chat_id,
            chunk,
            reply_to_message_id=reply_to_message_id if first else None,
        )
        first = False
    if sent is not None and context_db is not None:
        mgr = EnvelopeManager(context_db)
        await mgr.save(sent.message_id, env)
    return sent
