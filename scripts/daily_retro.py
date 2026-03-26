#!/usr/bin/env python3
"""일일 회고 스크립트 — 매일 23:30 KST (UTC 14:30).

[구조] 대화형·점진적 토론 방식
  1. PM이 오늘의 활동 요약으로 회고를 시작
  2. 각 조직이 순차 발언 (잘한 것 → 잘못한 것 → 해야 할 것)
     - 앞 조직 발언을 컨텍스트로 참조하여 반응·추가 의견을 쌓는 점진적 토론
  3. PM이 전체 토론을 수렴하며 핵심 정리
  4. "해야 할 것" 항목을 파싱하여 MEMORY.md Pending Tasks에 자동 등록

이전 방식(단일 PM 생성) → 신규 방식(멀티 조직 점진 토론)으로 전환.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sqlite3
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# ── 환경 설정 ─────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
MEMORY_MD_PATH = Path.home() / ".claude" / "projects" / "-Users-rocky-telegram-ai-org" / "memory" / "MEMORY.md"


def _load_env() -> None:
    for env_path in (Path.home() / ".ai-org" / "config.yaml", PROJECT_ROOT / ".env"):
        if not env_path.exists():
            continue
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


_load_env()

BOT_TOKEN = os.environ.get("PM_BOT_TOKEN", "")
GROUP_CHAT_ID = int(os.environ.get("TELEGRAM_GROUP_CHAT_ID", "-5203707291"))
DB_PATH = Path(os.environ.get("CONTEXT_DB_PATH", "~/.ai-org/context.db")).expanduser()
MEMORY_PATH = Path(os.environ.get("SHARED_MEMORY_PATH", "~/.ai-org/shared_memory.json")).expanduser()

# 참여 조직 순서 (발언 순서 고정 — PM은 사회자 역할)
RETRO_ORGS: list[dict[str, str]] = [
    {"org_id": "aiorg_engineering_bot", "name": "개발실", "emoji": "⚙️"},
    {"org_id": "aiorg_ops_bot",         "name": "운영실", "emoji": "🔧"},
    {"org_id": "aiorg_design_bot",      "name": "디자인실", "emoji": "🎨"},
    {"org_id": "aiorg_product_bot",     "name": "기획실",  "emoji": "📋"},
    {"org_id": "aiorg_growth_bot",      "name": "성장실",  "emoji": "📈"},
    {"org_id": "aiorg_research_bot",    "name": "리서치실", "emoji": "🔬"},
]


# ── ContextDB 쿼리 ────────────────────────────────────────────────────────

def get_today_tasks() -> list[dict]:
    """오늘 완료된 태스크 목록."""
    if not DB_PATH.exists():
        return []
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT id, description, assigned_dept, status, result,
                   created_at, updated_at
            FROM pm_tasks
            WHERE status IN ('completed', 'failed')
              AND updated_at >= ? AND updated_at < ?
            ORDER BY updated_at
            """,
            (today_start.isoformat(), today_end.isoformat()),
        )
        pm = [dict(r) for r in cur.fetchall()]

        cur2 = conn.execute(
            """
            SELECT task_id, assigned_to, status, result, created_at, completed_at
            FROM task_history
            WHERE completed_at >= ? AND completed_at < ?
            ORDER BY completed_at
            """,
            (today_start.isoformat(), today_end.isoformat()),
        )
        hist = [dict(r) for r in cur2.fetchall()]
    return pm + hist


def get_recent_tasks(days: int = 7) -> list[dict]:
    """최근 N일 태스크 요약 (진행 중 + 완료 포함) — 토론 컨텍스트용."""
    if not DB_PATH.exists():
        return []
    now = datetime.now(UTC)
    since = (now - timedelta(days=days)).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            """
            SELECT id, description, assigned_dept, status, result, updated_at
            FROM pm_tasks
            WHERE updated_at >= ?
            ORDER BY updated_at DESC
            LIMIT 50
            """,
            (since,),
        )
        return [dict(r) for r in cur.fetchall()]


# ── SharedMemory 저장 ─────────────────────────────────────────────────────

def save_to_shared_memory(retro_data: dict) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing: dict = {}
    if MEMORY_PATH.exists():
        try:
            existing = json.loads(MEMORY_PATH.read_text())
        except Exception:
            pass
    retro_ns = existing.setdefault("retro", {})
    date_key = datetime.now(UTC).strftime("%Y-%m-%d")
    retro_ns[date_key] = retro_data
    MEMORY_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2))
    print(f"[retro] SharedMemory 저장 완료: retro/{date_key}")


# ── LLM 클라이언트 헬퍼 ────────────────────────────────────────────────────

async def _llm_call(prompt: str, timeout: float = 45.0) -> str | None:
    """PMDecisionClient로 LLM 호출. 실패 시 None 반환."""
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        from core.pm_decision import PMDecisionClient
        client = PMDecisionClient("aiorg_pm_bot", engine="claude-code")
        return await asyncio.wait_for(client.complete(prompt), timeout=timeout)
    except Exception as e:
        print(f"[retro] LLM 호출 실패: {e}")
        return None


# ── Phase 1: 오늘 활동 컨텍스트 생성 ─────────────────────────────────────

def _build_activity_summary(today_tasks: list[dict], recent_tasks: list[dict]) -> str:
    """오늘·최근 태스크를 텍스트 요약으로 변환 — 토론 컨텍스트용."""
    today_completed = [t for t in today_tasks if t.get("status") == "completed"]
    today_failed = [t for t in today_tasks if t.get("status") == "failed"]

    lines = [
        f"=== 오늘({datetime.now(UTC).strftime('%Y-%m-%d')}) 활동 ===",
        f"완료: {len(today_completed)}건 / 실패: {len(today_failed)}건",
    ]

    for t in today_completed[:12]:
        dept = t.get("assigned_dept") or t.get("assigned_to", "?")
        desc = (t.get("description") or t.get("task_id", "?"))[:80]
        lines.append(f"  ✅ [{dept}] {desc}")

    for t in today_failed[:5]:
        dept = t.get("assigned_dept") or t.get("assigned_to", "?")
        desc = (t.get("description") or t.get("task_id", "?"))[:80]
        lines.append(f"  ❌ [{dept}] {desc}")

    # 진행 중 태스크 (최근 7일 in_progress)
    in_progress = [t for t in recent_tasks if t.get("status") == "in_progress"][:8]
    if in_progress:
        lines.append("\n=== 현재 진행 중 ===")
        for t in in_progress:
            dept = t.get("assigned_dept", "?")
            desc = (t.get("description") or t.get("task_id", "?"))[:80]
            lines.append(f"  🔄 [{dept}] {desc}")

    return "\n".join(lines)


# ── Phase 2: 조직별 순차 발언 생성 ───────────────────────────────────────

async def _generate_org_speech(
    org: dict[str, str],
    activity_summary: str,
    prior_speeches: list[dict[str, Any]],
) -> dict[str, Any]:
    """한 조직의 회고 발언을 LLM으로 생성.

    Args:
        org: {"org_id": ..., "name": ..., "emoji": ...}
        activity_summary: 오늘 전체 활동 요약
        prior_speeches: 이전 조직들의 발언 목록 (점진적 컨텍스트)

    Returns:
        {
            "org_id": ..., "name": ..., "emoji": ...,
            "했던것": str, "잘못한것": str, "해야할것": list[str],
            "raw": str,
        }
    """
    # 이전 발언들을 컨텍스트로 구성
    prior_context = ""
    if prior_speeches:
        prior_context = "\n\n=== 앞선 조직 발언 (참고·반응 가능) ===\n"
        for sp in prior_speeches:
            prior_context += (
                f"\n{sp['emoji']} {sp['name']}:\n"
                f"  잘한 것: {sp.get('잘한것', '(없음)')}\n"
                f"  잘못한 것: {sp.get('잘못한것', '(없음)')}\n"
                f"  해야 할 것: {', '.join(sp.get('해야할것', [])) or '(없음)'}\n"
            )

    prompt = f"""당신은 AI 조직 팀의 '{org['name']}({org['org_id']})' 담당자입니다.
오늘의 팀 활동을 바탕으로 일일 회고 발언을 작성해주세요.

{activity_summary}
{prior_context}

위 내용을 바탕으로 '{org['name']}' 관점의 회고를 작성하세요.
앞 조직의 발언이 있다면 거기에 공감하거나 덧붙이는 식으로 자연스럽게 이어가세요.
마치 팀원들이 모여 잡담하듯 솔직하고 간결하게 작성하세요.

정확히 아래 형식으로 출력하세요 (각 항목은 한 줄):
잘한것: (이번에 잘 된 것 1~2가지, 없으면 "특이사항 없음")
잘못한것: (아쉬운 점 또는 실수 1~2가지, 없으면 "특이사항 없음")
해야할것: (앞으로 해야 할 구체적 행동 1~3가지, 각각 세미콜론으로 구분)"""

    raw = await _llm_call(prompt, timeout=45.0)

    # 파싱
    result: dict[str, Any] = {
        "org_id": org["org_id"],
        "name": org["name"],
        "emoji": org["emoji"],
        "잘한것": "(응답 없음)",
        "잘못한것": "(응답 없음)",
        "해야할것": [],
        "raw": raw or "",
    }

    if not raw:
        return result

    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("잘한것:"):
            result["잘한것"] = line[len("잘한것:"):].strip()
        elif line.startswith("잘못한것:"):
            result["잘못한것"] = line[len("잘못한것:"):].strip()
        elif line.startswith("해야할것:"):
            items_raw = line[len("해야할것:"):].strip()
            # 세미콜론 또는 쉼표로 구분, 빈 항목 제거
            items = [i.strip() for i in re.split(r"[;；,，]", items_raw) if i.strip()]
            result["해야할것"] = [i for i in items if i and i != "(없음)"]

    return result


# ── Phase 3: PM 수렴 요약 ─────────────────────────────────────────────────

async def _generate_pm_summary(speeches: list[dict[str, Any]], activity_summary: str) -> str:
    """PM이 전체 토론을 수렴하는 최종 요약 생성."""
    discussion_text = ""
    for sp in speeches:
        discussion_text += (
            f"\n{sp['emoji']} {sp['name']}:\n"
            f"  잘한 것: {sp.get('잘한것', '')}\n"
            f"  잘못한 것: {sp.get('잘못한것', '')}\n"
            f"  해야 할 것: {', '.join(sp.get('해야할것', []))}\n"
        )

    all_todo = []
    for sp in speeches:
        for item in sp.get("해야할것", []):
            all_todo.append(f"[{sp['name']}] {item}")

    prompt = f"""당신은 AI 조직의 총괄 PM입니다.
오늘 일일 회고에서 각 조직이 다음과 같이 발언했습니다.

{activity_summary}

=== 각 조직 발언 ===
{discussion_text}

위 토론을 PM 관점에서 수렴하여 아래 항목을 작성하세요:
1. 오늘의 핵심 성과 (1~2문장)
2. 공통적으로 드러난 아쉬운 점 (있다면 1~2문장)
3. 우선 처리 필요한 개선 사항 (상위 3개만, 간결하게)

솔직하고 실용적으로, 팀장이 팀원들에게 말하듯 작성하세요."""

    result = await _llm_call(prompt, timeout=45.0)
    return result or "(PM 요약 생성 실패)"


# ── Phase 4: 메시지 포맷팅 ────────────────────────────────────────────────

def _format_telegram_message(
    speeches: list[dict[str, Any]],
    pm_summary: str,
    today_tasks: list[dict],
    date_str: str,
) -> str:
    """Telegram용 회고 메시지 포맷."""
    total = len(today_tasks)
    completed = sum(1 for t in today_tasks if t.get("status") == "completed")
    failed = total - completed

    lines = [
        f"🌙 *일일 회고 — {date_str}*",
        "",
        f"📊 오늘 처리: *{total}건* (완료 {completed}, 실패 {failed})",
        "",
        "---",
        "💬 *조직별 토론*",
        "",
    ]

    for sp in speeches:
        lines.append(f"{sp['emoji']} *{sp['name']}*")
        lines.append(f"  👍 잘한 것: {sp.get('잘한것', '')}")
        lines.append(f"  ⚠️ 잘못한 것: {sp.get('잘못한것', '')}")
        todos = sp.get("해야할것", [])
        if todos:
            lines.append("  📌 해야 할 것:")
            for item in todos:
                lines.append(f"    - {item}")
        lines.append("")

    lines += [
        "---",
        "🧭 *PM 수렴 요약*",
        "",
        pm_summary,
        "",
        "내일도 화이팅! 💪",
    ]

    return "\n".join(lines)


def _format_markdown(
    speeches: list[dict[str, Any]],
    pm_summary: str,
    today_tasks: list[dict],
    date_str: str,
) -> str:
    """Markdown 파일용 회고 포맷."""
    total = len(today_tasks)
    completed = sum(1 for t in today_tasks if t.get("status") == "completed")
    failed = total - completed
    now = datetime.now(UTC)

    lines = [
        f"# 일일 회고 — {date_str}",
        "",
        f"**처리 요약**: 총 {total}건 (완료 {completed}, 실패 {failed})",
        "",
        "## 조직별 토론",
        "",
    ]

    for sp in speeches:
        lines.append(f"### {sp['emoji']} {sp['name']}")
        lines.append(f"- **잘한 것**: {sp.get('잘한것', '')}")
        lines.append(f"- **잘못한 것**: {sp.get('잘못한것', '')}")
        todos = sp.get("해야할것", [])
        if todos:
            lines.append("- **해야 할 것**:")
            for item in todos:
                lines.append(f"  - {item}")
        lines.append("")

    lines += [
        "## PM 수렴 요약",
        "",
        pm_summary,
        "",
        "---",
        f"*자동 생성: {now.isoformat()}*",
    ]

    return "\n".join(lines)


# ── Phase 5: Telegram 전송 ─────────────────────────────────────────────────

async def send_telegram(text: str) -> None:
    try:
        import sys
        sys.path.insert(0, str(PROJECT_ROOT))
        from telegram import Bot
        from core.telegram_formatting import markdown_to_html

        bot = Bot(token=BOT_TOKEN)
        async with bot:
            await bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=markdown_to_html(text),
                parse_mode="HTML",
            )
        print(f"[retro] Telegram 전송 완료 ({len(text)}자)")
    except Exception as e:
        print(f"[retro] Telegram 전송 실패: {e}")


# ── Phase 6: 해야 할 것 → MEMORY.md Pending Tasks 자동 등록 ──────────────

def _register_todos_to_memory(speeches: list[dict[str, Any]], date_str: str) -> list[str]:
    """각 조직의 '해야 할 것' 항목을 MEMORY.md Pending Tasks에 자동 등록.

    Returns:
        등록된 태스크 ID 목록
    """
    # 전체 "해야 할 것" 수집
    all_todos: list[dict[str, str]] = []
    for sp in speeches:
        for item in sp.get("해야할것", []):
            if item and item not in ("(없음)", "특이사항 없음"):
                all_todos.append({
                    "org": sp["name"],
                    "item": item,
                })

    if not all_todos:
        print("[retro] 등록할 '해야 할 것' 항목 없음")
        return []

    if not MEMORY_MD_PATH.exists():
        print(f"[retro] MEMORY.md 없음: {MEMORY_MD_PATH}")
        return []

    content = MEMORY_MD_PATH.read_text(encoding="utf-8")

    # 신규 태스크 행 생성
    new_rows: list[str] = []
    registered_ids: list[str] = []

    # 기존 ID 중 최대값 파악 (RETRO- 접두어 항목)
    existing_retro_ids = re.findall(r"RETRO-\d+", content)
    next_num = max((int(x.split("-")[1]) for x in existing_retro_ids), default=0) + 1

    for todo in all_todos:
        task_id = f"RETRO-{next_num:02d}"
        title = f"[{todo['org']}] {todo['item'][:60]}"
        row = f"| {task_id} | {title} | {date_str} | pending | - |"
        new_rows.append(row)
        registered_ids.append(task_id)
        next_num += 1

    if not new_rows:
        return []

    # Pending Tasks 테이블의 헤더 행 아래에 삽입
    # 헤더: "| id | title | created_at | status | resolved_at |"
    insert_marker = "| id | title | created_at | status | resolved_at |"
    separator_pattern = r"\|[-| ]+\|"

    # 테이블 헤더 + separator 다음 줄에 삽입
    def _insert_rows(text: str) -> str:
        lines = text.splitlines()
        insert_after: int = -1
        for i, line in enumerate(lines):
            if insert_marker in line:
                # 다음 줄이 구분선이면 그 다음에 삽입
                if i + 1 < len(lines) and re.match(separator_pattern, lines[i + 1]):
                    insert_after = i + 1
                else:
                    insert_after = i
                break

        if insert_after == -1:
            # 테이블을 찾지 못하면 파일 끝에 추가
            return text + "\n" + "\n".join(new_rows) + "\n"

        result = lines[: insert_after + 1] + new_rows + lines[insert_after + 1 :]
        return "\n".join(result)

    updated = _insert_rows(content)
    MEMORY_MD_PATH.write_text(updated, encoding="utf-8")
    print(f"[retro] MEMORY.md Pending Tasks 자동 등록: {len(registered_ids)}개 — {registered_ids}")
    return registered_ids


# ── Phase 7: GoalTracker 등록 (기존 로직 유지) ───────────────────────────

async def _register_retro_actions(md_content: str) -> None:
    """일일회고 마크다운에서 조치사항을 파싱하여 GoalTracker에 자동 등록."""
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))

    try:
        from goal_tracker.auto_register import auto_register_from_report
        from goal_tracker.loop_runner import run_meeting_cycle

        register_result = await auto_register_from_report(
            report_text=md_content,
            report_type="daily_retro",
            org_id="aiorg_pm_bot",
        )

        print(
            f"[retro] GoalTracker 파싱 완료 — "
            f"조치사항 {register_result.action_items_found}개 추출"
        )

        if register_result.action_items_found == 0:
            print("[retro] 등록할 조치사항 없음 — 자율 루프 생략")
            return

        if not register_result.registered_ids:
            print(
                f"[retro] GoalTracker 미연결 — 파싱 완료 ({register_result.action_items_found}개), "
                "실제 등록 없음 → 루프 생략"
            )
            return

        loop_result = await run_meeting_cycle(
            meeting_type="daily_retro",
            registered_ids=register_result.registered_ids,
        )

        print(
            f"[retro] 자율 루프 완료 — "
            f"states={loop_result.states_visited}, "
            f"dispatched={loop_result.dispatched_count}개"
        )

        if loop_result.error:
            print(f"[retro] 자율 루프 경고: {loop_result.error}")

    except ImportError as e:
        print(f"[retro] GoalTracker 모듈 없음 — 등록 생략 ({e})")
    except Exception as e:
        print(f"[retro] GoalTracker 등록 실패 (비치명적): {e}")


# ── 파일 저장 ─────────────────────────────────────────────────────────────

def save_markdown(content: str) -> Path:
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    out_dir = PROJECT_ROOT / "docs" / "retros"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date_str}.md"
    out_path.write_text(content, encoding="utf-8")
    print(f"[retro] 저장: {out_path}")
    return out_path


# ── GroupChatHub 기반 실시간 대화형 회고 ──────────────────────────────────

async def _run_hub_retro(
    activity_summary: str,
    send_func,
) -> tuple[list[dict[str, Any]], list[str]]:
    """GroupChatHub.start_retro()를 사용한 실시간 대화형 회고.

    각 조직의 고유 LLM(PMDecisionClient(org_id))을 사용해 순차 발언하며,
    이전 발언이 GroupChatContext에 누적되어 자연스러운 토론이 형성된다.

    Returns:
        (speeches_compat, action_items):
            speeches_compat — 기존 _generate_org_speech 형식 호환 리스트
            action_items — 3라운드에서 추출된 ACTION: 항목들
    """
    import sys
    sys.path.insert(0, str(PROJECT_ROOT))

    try:
        from core.group_chat_hub import GroupChatHub, GroupMessage
        from core.pm_decision import PMDecisionClient
    except ImportError as e:
        print(f"[retro] GroupChatHub 모듈 없음 — 건너뜀 ({e})")
        return [], []

    hub = GroupChatHub(send_to_group=send_func)

    # 각 조직별 LLM 콜백 등록 (자신의 org_id로 PMDecisionClient 생성)
    def _make_org_callback(org: dict[str, str]):
        client = PMDecisionClient(org["org_id"], engine="auto")

        async def _speak(message: str, ctx: list[GroupMessage]) -> str | None:
            ctx_text = ""
            if ctx:
                ctx_lines = [
                    f"[{m.from_bot}]: {m.text[:200]}"
                    for m in ctx[-8:]
                ]
                ctx_text = "\n".join(ctx_lines)

            prompt = (
                f"당신은 AI 조직 팀의 '{org['name']}' 담당자입니다.\n\n"
                f"{message}\n\n"
                + (f"[앞선 팀원 발언]\n{ctx_text}\n\n" if ctx_text else "")
                + "앞 발언을 참고하여 공감하거나 덧붙이는 식으로 자연스럽게 발언하세요 (최대 300자)."
            )
            try:
                result = await asyncio.wait_for(
                    client.complete(prompt),
                    timeout=50.0,
                )
                return result.strip() if result else None
            except Exception as e:
                print(f"[retro] {org['org_id']} 발언 실패: {e}")
                return None

        return _speak

    for org in RETRO_ORGS:
        hub.register_participant(
            org["org_id"],
            _make_org_callback(org),
            domain_keywords=[org["name"]],
        )

    # 대화형 회고 실행 (3라운드)
    retro_result = await hub.start_retro(
        context_summary=activity_summary,
        participants=[org["org_id"] for org in RETRO_ORGS],
    )

    print(
        f"[retro] GroupChatHub 회고 완료 — "
        f"라운드 {len(retro_result.rounds)}개, "
        f"액션 아이템 {len(retro_result.action_items)}개"
    )

    # 기존 speeches 형식으로 변환 (MEMORY.md 등록 호환용)
    speeches_compat: list[dict[str, Any]] = []
    for org in RETRO_ORGS:
        org_responses: list[str] = []
        for rnd in retro_result.rounds:
            if org["org_id"] in rnd.responses:
                org_responses.append(rnd.responses[org["org_id"]])

        # 3라운드 응답을 해야할것으로 매핑 (ACTION: 항목 추출)
        todo_items: list[str] = []
        for resp in org_responses:
            for line in resp.splitlines():
                stripped = line.strip()
                if stripped.upper().startswith("ACTION:"):
                    item = stripped[7:].strip()
                    if item:
                        todo_items.append(item)

        speeches_compat.append({
            "org_id": org["org_id"],
            "name":   org["name"],
            "emoji":  org["emoji"],
            "잘한것":  org_responses[0] if len(org_responses) > 0 else "(발언 없음)",
            "잘못한것": org_responses[1] if len(org_responses) > 1 else "(발언 없음)",
            "해야할것": todo_items or (
                [org_responses[2][:80]] if len(org_responses) > 2 else []
            ),
            "raw": "\n".join(org_responses),
        })

    return speeches_compat, retro_result.action_items


# ── 메인 오케스트레이션 ────────────────────────────────────────────────────

async def main() -> None:
    """
    실행 흐름:
      1) 오늘 + 최근 7일 태스크 수집 → 활동 요약 텍스트 생성
      2) [우선] GroupChatHub.start_retro() — 각 조직 고유 LLM으로 실시간 3라운드 토론
         [폴백] 순차 발언 방식 (_generate_org_speech) — GroupChatHub 불가 시
      3) PM 수렴 요약 생성
      4) Telegram 전송 + Markdown 저장 + SharedMemory 저장
      5) "해야 할 것" → MEMORY.md Pending Tasks 자동 등록
      6) GoalTracker 연동 (활성화된 경우)
    """
    print(f"[retro] 시작 — {datetime.now(UTC).isoformat()}")
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")

    # Step 1: 활동 수집
    today_tasks = get_today_tasks()
    recent_tasks = get_recent_tasks(days=7)
    print(f"[retro] 오늘 태스크: {len(today_tasks)}건 / 최근 7일: {len(recent_tasks)}건")

    activity_summary = _build_activity_summary(today_tasks, recent_tasks)

    # Step 2: 대화형 회고 — GroupChatHub 우선, 폴백 시 순차 방식
    speeches: list[dict[str, Any]] = []
    hub_action_items: list[str] = []
    use_hub = BOT_TOKEN  # Telegram 전송 가능할 때만 Hub 방식 사용 (실시간 발언 의미 있음)

    if use_hub:
        print("[retro] GroupChatHub 대화형 회고 시작...")
        speeches, hub_action_items = await _run_hub_retro(
            activity_summary=activity_summary,
            send_func=send_telegram,
        )
        if not speeches:
            print("[retro] GroupChatHub 실패 — 순차 방식으로 폴백")
            use_hub = False

    if not use_hub:
        print("[retro] 순차 발언 방식으로 회고 진행...")
        for org in RETRO_ORGS:
            print(f"[retro] {org['name']} 발언 생성 중...")
            speech = await _generate_org_speech(
                org=org,
                activity_summary=activity_summary,
                prior_speeches=speeches,
            )
            speeches.append(speech)
            print(f"[retro] {org['name']} 발언 완료: 해야할것={speech.get('해야할것', [])}")

    # Step 3: PM 수렴 요약
    print("[retro] PM 수렴 요약 생성 중...")
    pm_summary = await _generate_pm_summary(speeches, activity_summary)

    # Step 4: 메시지 포맷 & 저장
    tg_msg = _format_telegram_message(speeches, pm_summary, today_tasks, date_str)
    md_content = _format_markdown(speeches, pm_summary, today_tasks, date_str)

    retro_data = {
        "date": date_str,
        "total": len(today_tasks),
        "completed": sum(1 for t in today_tasks if t.get("status") == "completed"),
        "failed":    sum(1 for t in today_tasks if t.get("status") == "failed"),
        "mode": "hub_retro" if use_hub else "sequential",
        "speeches": [
            {
                "org_id": sp["org_id"],
                "name":   sp["name"],
                "잘한것":  sp.get("잘한것", ""),
                "잘못한것": sp.get("잘못한것", ""),
                "해야할것": sp.get("해야할것", []),
            }
            for sp in speeches
        ],
        "pm_summary": pm_summary,
        "hub_action_items": hub_action_items,
    }

    save_to_shared_memory(retro_data)
    save_markdown(md_content)

    # Hub 방식은 이미 실시간 전송됨 — 순차 방식만 최종 전송
    if not use_hub:
        if BOT_TOKEN:
            await send_telegram(tg_msg)
        else:
            print("[retro] PM_BOT_TOKEN 없음 — Telegram 전송 건너뜀")
            print(tg_msg)
    else:
        # Hub 방식: PM 수렴 요약만 추가 전송
        if BOT_TOKEN:
            summary_msg = (
                f"---\n🧭 *PM 수렴 요약*\n\n{pm_summary}\n\n내일도 화이팅! 💪"
            )
            await send_telegram(summary_msg)

    # Step 5: "해야 할 것" → MEMORY.md 자동 등록
    registered_ids = _register_todos_to_memory(speeches, date_str)
    if registered_ids:
        print(f"[retro] MEMORY.md 자동 등록 완료: {registered_ids}")

    # Step 6: GoalTracker 연동
    await _register_retro_actions(md_content)

    print(f"[retro] 완료 — {datetime.now(UTC).isoformat()}")


if __name__ == "__main__":
    asyncio.run(main())
