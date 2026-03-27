"""relay_command_handlers.py — /명령어 핸들러 모듈 (Phase 1c 분리).

telegram_relay.py의 on_command_* 메서드들을 독립 함수로 추출한 모듈.
- /start, /status, /reset
- /schedule*, /cancel_schedule, /pause_schedule, /resume_schedule
- /stop_tasks, /restart
- /engine, /set_engine
- /setup 마법사 (on_command_setup, _setup_callback_menu 등)
- _ensure_runtime_bootstrap, on_self_added_to_chat

Feature Flag: ENABLE_REFACTORED_COMMAND_HANDLERS (기본값: True)
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from loguru import logger

from core.relay_bot_setup import (
    SETUP_AWAIT_ENGINE,
    SETUP_AWAIT_IDENTITY,
    SETUP_AWAIT_TOKEN,
    SETUP_MENU,
    _default_identity_for_org,
    _launch_bot_subprocess,
    _profile_bundle_for_org,
    _set_org_bot_commands,
    _validate_bot_token,
)

ENABLE_REFACTORED_COMMAND_HANDLERS = os.environ.get("ENABLE_REFACTORED_COMMAND_HANDLERS", "1") == "1"

TEAM_ID = "pm"  # aiorg_pm tmux 세션 (telegram_relay.py와 동일 값)

if TYPE_CHECKING:
    from telegram import Update
    from telegram.ext import ContextTypes


# ---------------------------------------------------------------------------
# Protocol — TelegramRelay가 암묵적으로 충족
# ---------------------------------------------------------------------------

@runtime_checkable
class CommandRelayProtocol(Protocol):
    """TelegramRelay에서 명령어 처리에 필요한 최소 인터페이스."""

    org_id: str
    _is_pm_org: bool
    _schedule_store: object | None
    _nl_parser: object | None
    _org_scheduler: object | None
    _message_count: int
    session_store: object
    session_manager: object
    memory_manager: object
    identity: object
    display: object


# ---------------------------------------------------------------------------
# /start
# ---------------------------------------------------------------------------

async def on_command_start(
    relay: CommandRelayProtocol,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """PM 세션 없으면 생성 + 메모리 주입 후 /start."""
    from core.telegram_formatting import markdown_to_html

    if update.message is None:
        return

    initialized = _ensure_runtime_bootstrap(relay)

    if initialized:
        await update.message.reply_text(
            markdown_to_html(
                "🤖 **PM Bot 온라인**\n\n"
                "tmux 세션에서 Claude Code가 실행 중입니다.\n"
                "무엇이든 말씀하세요 — 메시지를 Claude에게 전달합니다.\n\n"
                "/status — 세션 상태 확인"
            ),
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("✅ 이미 실행 중인 세션에 연결됩니다.")


def _ensure_runtime_bootstrap(relay: CommandRelayProtocol) -> bool:
    """세션이 없으면 생성하고 True를, 이미 있으면 False를 반환한다."""
    existed = relay.session_manager.session_exists(TEAM_ID)
    relay.session_manager.ensure_session(TEAM_ID)
    if existed:
        return False
    ctx = relay.memory_manager.build_context()
    if ctx:
        relay.session_manager.inject_context(TEAM_ID, ctx)
    try:
        memory_ctx = relay.memory_manager.build_context()
        if memory_ctx:
            relay.session_manager.write_memory_to_claude_md(TEAM_ID, memory_ctx)
    except Exception as _e:
        logger.debug(f"[{relay.org_id}] CLAUDE.md 갱신 실패(무시): {_e}")
    return True


# ---------------------------------------------------------------------------
# on_self_added_to_chat
# ---------------------------------------------------------------------------

async def on_self_added_to_chat(
    relay: CommandRelayProtocol,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """봇이 그룹에 추가되면 /start 없이 자동 초기화한다."""
    from core.telegram_formatting import markdown_to_html

    if update.message is None or update.effective_chat is None:
        return
    if update.effective_chat.id != relay.allowed_chat_id:  # type: ignore[attr-defined]
        return
    new_members = getattr(update.message, "new_chat_members", None) or []
    if not new_members:
        return
    me = await context.bot.get_me()
    if not any(member.id == me.id for member in new_members):
        return

    initialized = _ensure_runtime_bootstrap(relay)
    specialties = relay.identity.get_specialty_text() or "미설정"
    if initialized:
        text = (
            "✅ 봇 초기화 완료\n\n"
            f"조직: {relay.org_id}\n"
            f"전문분야: {specialties}\n\n"
            "이제 바로 메시지를 보내면 됩니다. 별도 `/start` 나 `/org` 초기 설정은 필요하지 않습니다."
        )
    else:
        text = "✅ 이미 준비된 세션에 연결되어 있습니다. 바로 사용하시면 됩니다."
    await update.message.reply_text(markdown_to_html(text), parse_mode="HTML")


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------

async def on_command_status(
    relay: CommandRelayProtocol,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """세션 상태, 메모리 크기, PM 정체성 출력."""
    from core.telegram_formatting import markdown_to_html

    if update.message is None:
        return
    try:
        sess_status = relay.session_manager.status()
        mem_stats = relay.memory_manager.stats()
        specialties = relay.identity.get_specialty_text() or "없음"
        text = (
            f"📊 세션 상태\n"
            f"• tmux 사용 가능: {sess_status.get('tmux', False)}\n"
            f"• 활성 세션: {', '.join(sess_status.get('sessions', [])) or '없음'}\n\n"
            f"🏷️ PM 정체성 [{relay.org_id}]\n"
            f"• 전문분야: {specialties}\n\n"
            f"🧠 메모리 ({mem_stats['scope']})\n"
            f"• CORE: {mem_stats['core']}개\n"
            f"• SUMMARY: {mem_stats['summary']}개\n"
            f"• LOG: {mem_stats['log']}개\n\n"
            f"메시지 카운터: {relay._message_count}"
        )
        await update.message.reply_text(markdown_to_html(text), parse_mode="HTML")
    except Exception as e:
        logger.error(f"/status 처리 실패: {e}")
        await update.message.reply_text(
            markdown_to_html(f"⚠️ 상태 조회 실패: {e}"), parse_mode="HTML"
        )


# ---------------------------------------------------------------------------
# /reset
# ---------------------------------------------------------------------------

async def on_command_reset(
    relay: CommandRelayProtocol,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """세션 writeback + 리셋."""
    from core.telegram_formatting import escape_html

    if update.message is None:
        return
    await update.message.reply_text("🔄 세션 writeback 후 리셋 중...")
    try:
        await relay.session_manager.writeback_and_reset(TEAM_ID, relay.memory_manager)
        relay._message_count = 0
        relay.session_store.reset()
        await update.message.reply_text("✅ 새 세션으로 시작합니다. 대화 기록도 초기화했습니다.", parse_mode="HTML")
    except Exception as e:
        logger.error(f"리셋 실패: {e}")
        await update.message.reply_text(f"❌ 리셋 실패: {escape_html(str(e))}", parse_mode="HTML")


# ---------------------------------------------------------------------------
# /schedule 관련
# ---------------------------------------------------------------------------

async def on_command_schedule(
    relay: CommandRelayProtocol,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """/schedule [자연어 텍스트] — 새 스케줄 등록."""
    from core.telegram_formatting import escape_html

    if update.message is None:
        return
    if not relay._is_pm_org or relay._schedule_store is None or relay._nl_parser is None:
        await update.message.reply_text("❌ 이 봇에서는 스케줄 기능을 사용할 수 없습니다.")
        return
    text = " ".join(context.args) if context.args else ""
    if not text:
        await update.message.reply_text(
            "사용법: /schedule [자연어 스케줄]\n"
            "예시:\n"
            "  /schedule 매일 오전 9시에 AI 뉴스 요약\n"
            "  /schedule 매주 월요일 오전 10시에 팀 리포트 확인\n"
            "  /schedule 매달 1일 오전 9시에 월간 보고서 생성"
        )
        return
    try:
        from apscheduler.triggers.cron import CronTrigger as _CronTrigger
        parsed = relay._nl_parser.parse(text)
        _CronTrigger.from_crontab(parsed["cron_expr"], timezone="Asia/Seoul")
        loop = asyncio.get_event_loop()
        sched = await loop.run_in_executor(
            None, relay._schedule_store.add, text, parsed["cron_expr"], parsed["task_description"]
        )
        if relay._org_scheduler is not None:
            relay._org_scheduler.add_user_job(sched)
        await update.message.reply_text(
            f"✅ 스케줄 등록!\n"
            f"📋 ID: <code>{escape_html(str(sched.id))}</code>\n"
            f"⏰ {escape_html(parsed['human_readable'])}\n"
            f"📝 {escape_html(parsed['task_description'])}",
            parse_mode="HTML",
        )
    except Exception as e:
        await update.message.reply_text(f"❌ 등록 실패: {escape_html(str(e))}", parse_mode="HTML")


async def on_command_schedules(
    relay: CommandRelayProtocol,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """/schedules — 등록된 스케줄 목록."""
    if update.message is None:
        return
    if not relay._is_pm_org or relay._schedule_store is None:
        return
    loop = asyncio.get_event_loop()
    schedules = await loop.run_in_executor(None, relay._schedule_store.list_all)
    if not schedules:
        await update.message.reply_text("등록된 스케줄이 없습니다.")
        return
    from core.telegram_formatting import escape_html as _esc
    lines = ["<b>📋 등록된 스케줄 목록</b>\n"]
    for s in schedules:
        status = "✅" if s.enabled else "⏸️"
        lines.append(f"{status} ID:{s.id} | <code>{_esc(s.cron_expr)}</code> | {_esc(s.task_description)}")
    lines.append(
        "\n취소: /cancel_schedule [id]  일시중지: /pause_schedule [id]  재개: /resume_schedule [id]"
    )
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def on_command_cancel_schedule(
    relay: CommandRelayProtocol,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """/cancel_schedule [id] — 스케줄 영구 삭제."""
    if update.message is None:
        return
    if not relay._is_pm_org or relay._schedule_store is None:
        return
    if not context.args:
        await update.message.reply_text("사용법: /cancel_schedule [스케줄 ID]")
        return
    try:
        schedule_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ 유효하지 않은 ID입니다.")
        return
    loop = asyncio.get_event_loop()
    deleted = await loop.run_in_executor(None, relay._schedule_store.delete, schedule_id)
    if deleted:
        if relay._org_scheduler is not None:
            relay._org_scheduler.remove_user_job(schedule_id)
        await update.message.reply_text(f"🗑️ 스케줄 ID {schedule_id} 삭제 완료.")
    else:
        await update.message.reply_text(f"❌ ID {schedule_id}를 찾을 수 없습니다.")


async def on_command_pause_schedule(
    relay: CommandRelayProtocol,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """/pause_schedule [id] — 스케줄 일시중지."""
    if update.message is None:
        return
    if not relay._is_pm_org or relay._schedule_store is None:
        return
    if not context.args:
        await update.message.reply_text("사용법: /pause_schedule [스케줄 ID]")
        return
    try:
        schedule_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ 유효하지 않은 ID입니다.")
        return
    loop = asyncio.get_event_loop()
    disabled = await loop.run_in_executor(None, relay._schedule_store.disable, schedule_id)
    if disabled:
        if relay._org_scheduler is not None:
            relay._org_scheduler.remove_user_job(schedule_id)
        await update.message.reply_text(f"⏸️ 스케줄 ID {schedule_id} 일시중지.")
    else:
        await update.message.reply_text(f"❌ ID {schedule_id}를 찾을 수 없습니다.")


async def on_command_resume_schedule(
    relay: CommandRelayProtocol,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """/resume_schedule [id] — 스케줄 재개."""
    if update.message is None:
        return
    if not relay._is_pm_org or relay._schedule_store is None:
        return
    if not context.args:
        await update.message.reply_text("사용법: /resume_schedule [스케줄 ID]")
        return
    try:
        schedule_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ 유효하지 않은 ID입니다.")
        return
    loop = asyncio.get_event_loop()
    sched = await loop.run_in_executor(None, relay._schedule_store.get_by_id, schedule_id)
    if sched is None:
        await update.message.reply_text(f"❌ ID {schedule_id}를 찾을 수 없습니다.")
        return
    enabled = await loop.run_in_executor(None, relay._schedule_store.enable, schedule_id)
    if enabled:
        sched.enabled = True
        if relay._org_scheduler is not None:
            relay._org_scheduler.add_user_job(sched)
        await update.message.reply_text(f"▶️ 스케줄 ID {schedule_id} 재개.")
    else:
        await update.message.reply_text(f"❌ 재개 실패: ID {schedule_id}")


# ---------------------------------------------------------------------------
# /stop_tasks, /restart
# ---------------------------------------------------------------------------

async def on_command_stop_tasks(
    relay: CommandRelayProtocol,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """현재 진행 중인 tmux 세션 전체 종료. PM봇 전용."""
    from core.telegram_formatting import escape_html

    if update.message is None:
        return
    if not relay._is_pm_org:
        return

    sessions = relay.session_manager.list_sessions()
    if not sessions:
        await update.message.reply_text("ℹ️ 현재 실행 중인 세션이 없습니다.")
        return

    prefix = "aiorg_"
    stopped = []
    for session_name in sessions:
        team_id = session_name[len(prefix):] if session_name.startswith(prefix) else session_name
        try:
            relay.session_manager.kill_session(team_id)
            stopped.append(session_name)
        except Exception as exc:
            logger.warning(f"[stop_tasks] 세션 종료 실패 {session_name}: {exc}")

    if stopped:
        await update.message.reply_text(
            f"🛑 작업 종료 완료\n종료된 세션: <code>{escape_html(', '.join(stopped))}</code>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text("⚠️ 세션 종료 중 오류가 발생했습니다.", parse_mode="HTML")


async def on_command_restart(
    relay: CommandRelayProtocol,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """봇 전체 재시작 (scripts/restart_bots.sh 실행). PM봇 전용."""
    from core.telegram_formatting import escape_html

    if update.message is None:
        return
    if not relay._is_pm_org:
        return

    await update.message.reply_text("🔄 봇 재시작 중... (약 5초 후 다시 온라인 됩니다)")
    project_dir = Path(__file__).parent.parent
    restart_script = project_dir / "scripts" / "restart_bots.sh"
    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", str(restart_script),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=str(project_dir),
        )
        asyncio.create_task(proc.wait())
    except Exception as exc:
        logger.error(f"/restart 실패: {exc}")
        await update.message.reply_text(f"❌ 재시작 실패: {escape_html(str(exc))}", parse_mode="HTML")


# ---------------------------------------------------------------------------
# /engine, /set_engine
# ---------------------------------------------------------------------------

async def on_command_engine(
    relay: CommandRelayProtocol,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """/engine — 현재 봇별 엔진 확인. PM봇 전용."""
    from core.telegram_formatting import escape_html

    if update.message is None:
        return
    if not relay._is_pm_org:
        return

    import yaml as _yaml
    project_dir = Path(__file__).parent.parent
    bots_dir = project_dir / "bots"
    lines = ["⚙️ <b>현재 엔진 현황</b>"]
    for yaml_path in sorted(bots_dir.glob("*.yaml")):
        try:
            data = _yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            engine = data.get("engine", "—")
            name = data.get("name", yaml_path.stem)
            lines.append(f"• <b>{escape_html(name)}</b>: {escape_html(str(engine))}")
        except Exception:
            lines.append(f"• {escape_html(yaml_path.stem)}: 읽기 실패")
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def on_command_set_engine(
    relay: CommandRelayProtocol,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """/set_engine <engine> — bots/*.yaml 엔진 변경 후 재시작. PM봇 전용."""
    from core.telegram_formatting import escape_html

    if update.message is None:
        return
    if not relay._is_pm_org:
        return

    args = (update.message.text or "").split()
    if len(args) < 2:
        await update.message.reply_text(
            "사용법: /set_engine &lt;engine&gt;\n예: /set_engine claude-code",
            parse_mode="HTML",
        )
        return

    engine = args[1].strip()
    _VALID_ENGINES = {"claude-code", "codex", "gemini-cli"}
    if engine not in _VALID_ENGINES:
        await update.message.reply_text(
            f"❌ 유효하지 않은 엔진: {escape_html(engine)}\n사용 가능: {', '.join(sorted(_VALID_ENGINES))}",
            parse_mode="HTML",
        )
        return

    import yaml as _yaml
    project_dir = Path(__file__).parent.parent
    bots_dir = project_dir / "bots"
    updated = []
    errors = []

    for yaml_path in sorted(bots_dir.glob("*.yaml")):
        try:
            data = _yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            if data.get("engine") != engine:
                data["engine"] = engine
                yaml_path.write_text(
                    _yaml.dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8",
                )
                updated.append(yaml_path.stem)
        except Exception as exc:
            logger.warning(f"[set_engine] {yaml_path.name} 수정 실패: {exc}")
            errors.append(yaml_path.stem)

    org_yaml_path = project_dir / "organizations.yaml"
    try:
        org_data = _yaml.safe_load(org_yaml_path.read_text(encoding="utf-8")) or {}
        org_changed = False
        for org in org_data.get("organizations", []):
            exec_block = org.setdefault("execution", {})
            if exec_block.get("preferred_engine") != engine:
                exec_block["preferred_engine"] = engine
                org_changed = True
            if exec_block.get("fallback_engine") != engine:
                exec_block["fallback_engine"] = engine
                org_changed = True
        if org_changed:
            org_yaml_path.write_text(
                _yaml.dump(org_data, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            updated.append("organizations")
    except Exception as exc:
        logger.warning(f"[set_engine] organizations.yaml 수정 실패: {exc}")
        errors.append("organizations")

    if not updated and not errors:
        await update.message.reply_text(
            f"ℹ️ 모든 봇이 이미 {escape_html(engine)} 엔진을 사용 중입니다.",
            parse_mode="HTML",
        )
        return

    from core.telegram_formatting import markdown_to_html
    msg = f"⚙️ 엔진 변경: {engine}\n"
    if updated:
        msg += f"• 업데이트: {', '.join(updated)}\n"
    if errors:
        msg += f"• 실패: {', '.join(errors)}\n"
    msg += "\n🔄 재시작 중..."
    await update.message.reply_text(markdown_to_html(msg), parse_mode="HTML")

    restart_script = project_dir / "scripts" / "restart_bots.sh"
    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", str(restart_script),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(project_dir),
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        if proc.returncode != 0:
            logger.error(f"[set_engine] 재시작 실패 (rc={proc.returncode}): {stderr.decode()[:200]}")
            await update.message.reply_text(f"❌ 재시작 실패 (rc={proc.returncode})", parse_mode="HTML")
    except asyncio.TimeoutError:
        logger.warning("[set_engine] 재시작 타임아웃 — 백그라운드에서 계속 실행 중일 수 있음")
    except Exception as exc:
        logger.error(f"[set_engine] 재시작 실패: {exc}")
        await update.message.reply_text(f"❌ 재시작 실패: {escape_html(str(exc))}", parse_mode="HTML")


# ---------------------------------------------------------------------------
# /setup 마법사
# ---------------------------------------------------------------------------

async def on_command_setup(
    relay: CommandRelayProtocol,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """설정 마법사 진입 — 메뉴 표시."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import ConversationHandler

    if update.message is None:
        return ConversationHandler.END
    keyboard = [
        [InlineKeyboardButton("📋 현재 봇 설정 보기", callback_data="setup_view")],
        [InlineKeyboardButton("🤖 새 조직 봇 추가 (토큰 입력)", callback_data="setup_add")],
        [InlineKeyboardButton("❌ 취소", callback_data="setup_cancel")],
    ]
    await update.message.reply_text(
        "<b>🔧 봇 설정 마법사</b>\n\n원하는 작업을 선택하세요:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )
    return SETUP_MENU


async def _setup_callback_menu(
    relay: CommandRelayProtocol,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """메뉴 버튼 선택 처리."""
    from telegram.ext import ConversationHandler
    from core.telegram_formatting import markdown_to_html

    query = update.callback_query
    await query.answer()

    if query.data == "setup_view":
        me = await query.bot.get_me()
        bot_name = me.username or "봇이름"
        d = relay.identity._data
        msg = (
            f"🔧 **{relay.org_id} 봇 현재 설정**\n\n"
            f"역할: {d.get('role', '미설정')}\n"
            f"전문분야: {', '.join(d.get('specialties', [])) or '미설정'}\n"
            f"방향성: {d.get('direction', '미설정')}\n\n"
            f"**설정 변경 명령어**\n"
            f"`/org@{bot_name} 역할|전문분야1,분야2|방향성`\n"
            f"`/org add@{bot_name} <이름> [engine]`\n\n"
            f"💡 그룹방에서는 `/명령어@{bot_name}` 형식으로 사용하세요."
        )
        await query.edit_message_text(markdown_to_html(msg), parse_mode="HTML")
        return ConversationHandler.END

    elif query.data == "setup_add":
        await query.edit_message_text(
            "<b>🤖 새 조직 봇 추가</b>\n\n"
            "BotFather에서 발급받은 토큰을 입력하세요:\n\n"
            "⚠️ 보안: 토큰 메시지는 즉시 삭제됩니다.\n"
            "취소하려면 /cancel 을 입력하세요.",
            parse_mode="HTML",
        )
        return SETUP_AWAIT_TOKEN

    else:  # setup_cancel
        await query.edit_message_text("❌ 설정 취소됨.")
        return ConversationHandler.END


async def _setup_receive_token(
    relay: CommandRelayProtocol,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """토큰 수신 → 검증 → 다음 단계(엔진 선택)."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    from core.telegram_formatting import markdown_to_html

    if update.message is None:
        return SETUP_AWAIT_TOKEN

    token = (update.message.text or "").strip()
    try:
        await update.message.delete()
    except Exception:
        pass

    processing_msg = await update.effective_chat.send_message("🔍 토큰 검증 중...")

    bot_info = await _validate_bot_token(token)
    if not bot_info:
        await processing_msg.edit_text(
            "❌ 유효하지 않은 토큰입니다.\n\n"
            "토큰을 다시 입력하거나 /cancel 로 취소하세요."
        )
        return SETUP_AWAIT_TOKEN

    username = bot_info["username"]
    bot_display = bot_info["first_name"]
    chat_id = update.effective_chat.id

    context.user_data["setup_token"] = token
    context.user_data["setup_username"] = username
    context.user_data["setup_bot_display"] = bot_display
    context.user_data["setup_chat_id"] = chat_id

    keyboard = [
        [InlineKeyboardButton("1️⃣ Claude Code (기본, 권장)", callback_data="engine_claude-code")],
        [InlineKeyboardButton("2️⃣ Codex (경량 DevOps)", callback_data="engine_codex")],
        [InlineKeyboardButton("3️⃣ Gemini CLI (Google 검색 내장)", callback_data="engine_gemini-cli")],
        [InlineKeyboardButton("4️⃣ Auto (자동 결정)", callback_data="engine_auto")],
    ]
    await processing_msg.edit_text(
        markdown_to_html(
            f"✅ 봇 확인: **@{username}**\n\n"
            f"⚙️ **실행 엔진을 선택하세요:**\n\n"
            f"1️⃣ `claude-code` — 복잡한 작업, 고품질 *(기본)*\n"
            f"2️⃣ `codex` — 단순한 작업, 저렴\n"
            f"3️⃣ `gemini-cli` — Google 검색 내장, 리서치·성장 조직 권장\n"
            f"4️⃣ `auto` — LLM이 자동 결정"
        ),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return SETUP_AWAIT_ENGINE


async def _setup_receive_engine(
    relay: CommandRelayProtocol,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """엔진 선택 콜백 → 조직 정체성 입력 단계."""
    from core.telegram_formatting import markdown_to_html

    query = update.callback_query
    await query.answer()

    engine = (query.data or "").replace("engine_", "") or "claude-code"
    username = context.user_data.get("setup_username", "")
    context.user_data["setup_engine"] = engine

    _engine_labels = {
        "claude-code": "Claude Code",
        "codex": "Codex",
        "auto": "자동 결정",
    }
    identity = _default_identity_for_org(username)
    specialty_text = ",".join(identity.get("specialties", [])) if identity.get("specialties") else ""
    await query.edit_message_text(
        markdown_to_html(
            f"✅ 엔진 선택: `{engine}` — {_engine_labels.get(engine, engine)}\n\n"
            "🏷️ **조직 정체성을 입력하세요.**\n"
            "형식: `역할|전문분야1,전문분야2|방향성`\n\n"
            f"기본값:\n`{identity.get('role', '')}|{specialty_text}|방향성 입력`\n\n"
            "기본값을 그대로 쓰려면 `기본` 이라고 입력하세요."
        ),
        parse_mode="HTML",
    )
    return SETUP_AWAIT_IDENTITY


async def _setup_receive_identity(
    relay: CommandRelayProtocol,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """조직 정체성 수신 → 등록 완료."""
    from telegram.ext import ConversationHandler
    from core.telegram_formatting import escape_html, markdown_to_html
    from core.setup_registration import (
        parse_setup_identity,
        refresh_legacy_bot_configs,
        refresh_pm_identity_files,
        upsert_org_in_canonical_config,
        upsert_runtime_env_var,
    )

    if update.message is None:
        return SETUP_AWAIT_IDENTITY

    token = context.user_data.get("setup_token", "")
    username = context.user_data.get("setup_username", "")
    bot_display = context.user_data.get("setup_bot_display", "")
    chat_id = context.user_data.get("setup_chat_id", 0)
    engine = context.user_data.get("setup_engine", "claude-code")
    raw_identity = (update.message.text or "").strip()

    _engine_labels = {
        "claude-code": "Claude Code",
        "codex": "Codex",
        "auto": "자동 결정",
    }
    processing_msg = await update.effective_chat.send_message("⚙️ 조직 등록 중...")

    try:
        identity = parse_setup_identity(username, raw_identity)
        env_key = f"BOT_TOKEN_{username.upper().replace('-', '_')}"
        upsert_runtime_env_var(REPO_ROOT, env_key, token)
        upsert_org_in_canonical_config(
            REPO_ROOT,
            username=username,
            token_env=env_key,
            chat_id=chat_id,
            engine=engine,
            identity=identity,
        )
        refresh_legacy_bot_configs(REPO_ROOT)
        refresh_pm_identity_files(REPO_ROOT)
        pid = _launch_bot_subprocess(token, username, chat_id)
        org_kind = _profile_bundle_for_org(username)["kind"]
        await _set_org_bot_commands(token, kind=org_kind)

        await processing_msg.edit_text(
            markdown_to_html(
                f"✅ **@{username} 등록 완료!**\n\n"
                f"봇 이름: {bot_display}\n"
                f"역할: {identity.role}\n"
                f"전문분야: {', '.join(identity.specialties) or '미설정'}\n"
                f"엔진: `{engine}` ({_engine_labels.get(engine, engine)})\n"
                f"PID: {pid}\n\n"
                "canonical config / PM identity / bot commands 동기화 완료\n"
                "봇이 시작되었습니다. 그룹방에 초대하면 자동으로 초기화됩니다.\n"
                "별도 `/org` 나 `/start` 초기 설정은 필요하지 않습니다."
            ),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.error(f"봇 등록 실패: {e}")
        await processing_msg.edit_text(f"❌ 등록 실패: {escape_html(str(e))}", parse_mode="HTML")

    return ConversationHandler.END


async def _setup_cancel(
    relay: CommandRelayProtocol,
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> int:
    """설정 마법사 취소."""
    from telegram.ext import ConversationHandler

    if update.message:
        await update.message.reply_text("❌ 설정 취소됨.")
    return ConversationHandler.END


REPO_ROOT = Path(__file__).parent.parent
