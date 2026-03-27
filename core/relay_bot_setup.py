"""relay_bot_setup.py — 봇 등록·설정 유틸리티 모듈 (Phase 1c 분리).

telegram_relay.py 하단의 봇 등록·설정 관련 독립 함수들을 추출한 모듈.
- 봇 토큰 검증 (_validate_bot_token)
- 봇 명령어 등록 (_set_org_bot_commands, register_all_bot_commands)
- 조직 프로필 결정 (_profile_bundle_for_org, _default_identity_for_org)
- 설정 파일 관리 (_upsert_org_in_canonical_config, _sync_identity_to_canonical_config)
- 봇 프로세스 시작 (_launch_bot_subprocess)

ConversationHandler 상태 상수도 여기서 정의한다.
"""
from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

REPO_ROOT = Path(__file__).parent.parent

# /setup 마법사 ConversationHandler 상태 상수
SETUP_MENU, SETUP_AWAIT_TOKEN, SETUP_AWAIT_ENGINE, SETUP_AWAIT_IDENTITY = range(4)


async def _set_org_bot_commands(token: str, *, kind: str = "specialist") -> None:
    """새로 등록된 조직봇에 전용 명령어 세트를 자동으로 등록한다."""
    from telegram import Bot as _TGBot

    from core.bot_commands import get_bot_commands
    try:
        bot = _TGBot(token=token)
        org_commands = get_bot_commands(kind)
        await bot.set_my_commands(org_commands)
        logger.info(f"조직봇 명령어 자동 등록 완료: {[c.command for c in org_commands]}")
    except Exception as e:
        logger.warning(f"조직봇 명령어 등록 실패 (무시): {e}")


async def register_all_bot_commands() -> None:
    """bots/*.yaml 의 모든 봇에 setMyCommands 를 호출해 명령어 목록을 최신화한다."""
    import yaml as _yaml
    from telegram import Bot as _TGBot

    from core.bot_commands import get_bot_commands

    bots_dir = REPO_ROOT / "bots"
    for yaml_path in sorted(bots_dir.glob("*.yaml")):
        try:
            data = _yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
            token_env = data.get("token_env", "")
            token = os.environ.get(token_env, "") if token_env else ""
            if not token:
                logger.debug(f"[register_commands] 토큰 없음: {yaml_path.name} ({token_env})")
                continue
            kind = "orchestrator" if data.get("is_pm") else "specialist"
            commands = get_bot_commands(kind)
            bot = _TGBot(token=token)
            await bot.set_my_commands(commands)
            logger.info(f"[register_commands] {yaml_path.stem} ({kind}) 명령어 등록 완료")
        except Exception as exc:
            logger.warning(f"[register_commands] {yaml_path.name} 실패 (무시): {exc}")


async def _validate_bot_token(token: str) -> dict | None:
    """토큰으로 봇 정보를 조회한다. 유효하지 않으면 None 반환."""
    from telegram import Bot as _TGBot
    try:
        bot = _TGBot(token=token)
        me = await bot.get_me()
        return {"username": me.username, "first_name": me.first_name, "id": me.id}
    except Exception:
        return None


def _append_env_var(key: str, value: str) -> None:
    """.env 파일에 환경변수를 추가한다. 이미 존재하면 덮어쓴다."""
    env_path = REPO_ROOT / ".env"
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    new_lines = [line for line in lines if not line.startswith(f"{key}=")]
    new_lines.append(f"{key}={value}")
    env_path.write_text("\n".join(new_lines) + "\n")


def _create_bot_config(
    username: str, token_env: str, org_id: str, chat_id: int,
    engine: str = "claude-code",
    dept_name: str = "", role: str = "", instruction: str = "",
) -> None:
    """bots/ 디렉토리에 봇 설정 YAML 파일을 생성한다."""
    import datetime
    bots_dir = REPO_ROOT / "bots"
    bots_dir.mkdir(exist_ok=True)
    config_path = bots_dir / f"{username}.yaml"
    lines = [
        f"# 자동 생성 봇 설정 — {datetime.datetime.now().isoformat()}",
        f'username: "{username}"',
        f'org_id: "{org_id}"',
        f'token_env: "{token_env}"',
        f"chat_id: {chat_id}",
        f'engine: "{engine}"',
    ]
    if dept_name:
        lines.append(f'dept_name: "{dept_name}"')
    if role:
        lines.append(f'role: "{role}"')
    if instruction:
        lines.append(f'instruction: "{instruction}"')
    config_path.write_text("\n".join(lines) + "\n")


def _profile_bundle_for_org(org_id: str) -> dict:
    """org_id 기반 프로필 번들(kind, team_profile 등)을 반환한다."""
    lowered = org_id.lower()
    if lowered in {"global", "aiorg_pm_bot"} or lowered.endswith("_pm_bot"):
        return {
            "kind": "orchestrator",
            "team_profile": "global_orchestrator",
            "verification_profile": "orchestrator_default",
            "backend_policy": "orchestrator_default",
            "session_policy": "orchestrator_default",
            "can_direct_reply": True,
        }
    if "research" in lowered or "insight" in lowered or "reference" in lowered:
        return {
            "kind": "specialist",
            "team_profile": "research_strategy",
            "verification_profile": "specialist_default",
            "backend_policy": "specialist_default",
            "session_policy": "specialist_default",
            "can_direct_reply": False,
        }
    if "engineering" in lowered or "dev" in lowered or "code" in lowered:
        return {
            "kind": "specialist",
            "team_profile": "engineering_delivery",
            "verification_profile": "specialist_default",
            "backend_policy": "specialist_default",
            "session_policy": "specialist_default",
            "can_direct_reply": False,
        }
    if "design" in lowered or "ux" in lowered or "ui" in lowered:
        return {
            "kind": "specialist",
            "team_profile": "design_strategy",
            "verification_profile": "specialist_default",
            "backend_policy": "specialist_default",
            "session_policy": "specialist_default",
            "can_direct_reply": False,
        }
    if "product" in lowered or "plan" in lowered or "prd" in lowered:
        return {
            "kind": "specialist",
            "team_profile": "product_strategy",
            "verification_profile": "specialist_default",
            "backend_policy": "specialist_default",
            "session_policy": "specialist_default",
            "can_direct_reply": False,
        }
    if "growth" in lowered or "marketing" in lowered:
        return {
            "kind": "specialist",
            "team_profile": "growth_strategy",
            "verification_profile": "specialist_default",
            "backend_policy": "specialist_default",
            "session_policy": "specialist_default",
            "can_direct_reply": False,
        }
    if "ops" in lowered or "infra" in lowered:
        return {
            "kind": "specialist",
            "team_profile": "ops_delivery",
            "verification_profile": "specialist_default",
            "backend_policy": "specialist_default",
            "session_policy": "specialist_default",
            "can_direct_reply": False,
        }
    return {
        "kind": "specialist",
        "team_profile": "research_strategy",
        "verification_profile": "specialist_default",
        "backend_policy": "specialist_default",
        "session_policy": "specialist_default",
        "can_direct_reply": False,
    }


def _default_identity_for_org(org_id: str) -> dict:
    """org_id 기반 기본 정체성 딕셔너리를 반환한다."""
    lowered = org_id.lower()
    if "research" in lowered or "insight" in lowered or "reference" in lowered:
        return {
            "dept_name": "리서치실",
            "display_name": "Research",
            "role": "시장조사/레퍼런스 조사/문서 요약/경쟁사 분석",
            "specialties": ["시장조사", "레퍼런스조사", "문서요약", "경쟁사분석"],
            "instruction": "시장·레퍼런스·경쟁사 조사 결과를 출처 기반으로 구조화해 정리하세요.",
            "guidance": "조사 범위, 출처, 비교표, 핵심 인사이트를 반드시 남긴다.",
        }
    return {
        "dept_name": org_id,
        "display_name": org_id,
        "role": f"{org_id} 역할",
        "specialties": [],
        "instruction": "요청을 분석하고 처리하세요.",
        "guidance": "추후 /org 명령으로 조직 정체성을 보완하세요.",
    }


def _upsert_org_in_canonical_config(
    *,
    username: str,
    token_env: str,
    chat_id: int,
    engine: str,
) -> None:
    """organizations.yaml에 새 org 항목을 추가하거나 기존 항목을 업데이트한다."""
    import yaml as _yaml

    orgs_path = REPO_ROOT / "organizations.yaml"
    if orgs_path.exists():
        data = _yaml.safe_load(orgs_path.read_text(encoding="utf-8")) or {}
    else:
        data = {
            "schema_version": 2,
            "source_of_truth": {
                "docs_root": "docs/orchestration-v2",
                "orchestration_config": "orchestration.yaml",
            },
            "organizations": [],
        }

    bundle = _profile_bundle_for_org(username)
    identity_defaults = _default_identity_for_org(username)
    org_entry = {
        "id": username,
        "enabled": True,
        "kind": bundle["kind"],
        "description": f"{username} org",
        "telegram": {
            "username": username,
            "token_env": token_env,
            "chat_id": chat_id,
        },
        "identity": {
            "dept_name": identity_defaults["dept_name"],
            "display_name": identity_defaults["display_name"],
            "role": identity_defaults["role"],
            "specialties": identity_defaults["specialties"],
            "direction": "추후 /org 명령으로 업데이트",
            "instruction": identity_defaults["instruction"],
        },
        "routing": {
            "default_handler": False,
            "can_direct_reply": bundle["can_direct_reply"],
            "confidence_threshold": 5,
            "orchestration_mode": "skill_cli",
        },
        "execution": {
            "preferred_engine": engine,
            "fallback_engine": "claude-code" if engine != "claude-code" else "codex",
            "team_profile": bundle["team_profile"],
            "verification_profile": bundle["verification_profile"],
            "phase_policy": "default",
            "backend_policy": bundle["backend_policy"],
            "session_policy": bundle["session_policy"],
        },
        "team": {
            "preferred_agents": [],
            "avoid_agents": [],
            "max_team_size": 3,
            "preferred_skills": [],
            "guidance": identity_defaults["guidance"],
        },
        "collaboration": {
            "peers": [],
            "announce_plan": True,
            "announce_progress": True,
            "brainstorming_mode": "structured",
        },
    }

    orgs = data.setdefault("organizations", [])
    replaced = False
    for idx, existing in enumerate(orgs):
        if existing.get("id") == username:
            orgs[idx] = org_entry
            replaced = True
            break
    if not replaced:
        orgs.append(org_entry)

    orgs_path.write_text(
        _yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _sync_identity_to_canonical_config(org_id: str, identity_data: dict) -> None:
    """organizations.yaml의 특정 org identity 필드를 부분 업데이트한다."""
    import yaml as _yaml

    orgs_path = REPO_ROOT / "organizations.yaml"
    if not orgs_path.exists():
        return

    data = _yaml.safe_load(orgs_path.read_text(encoding="utf-8")) or {}
    for org in data.get("organizations", []):
        if org.get("id") != org_id:
            continue
        identity = org.setdefault("identity", {})
        if identity_data.get("role"):
            identity["role"] = identity_data["role"]
        specialties = identity_data.get("specialties")
        if specialties:
            identity["specialties"] = list(specialties)
        if identity_data.get("direction"):
            identity["direction"] = identity_data["direction"]
        break

    orgs_path.write_text(
        _yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _refresh_legacy_bot_configs() -> None:
    """bots/*.yaml 레거시 설정 파일을 orchestration_cli.py로 재생성한다."""
    import subprocess as _subprocess
    import sys as _sys
    _subprocess.run(
        [_sys.executable, str(REPO_ROOT / "tools" / "orchestration_cli.py"),
         "export-legacy-bots", "--target-dir", "bots"],
        cwd=str(REPO_ROOT),
        check=False,
        stdout=_subprocess.DEVNULL,
        stderr=_subprocess.DEVNULL,
    )


def _launch_bot_subprocess(token: str, org_id: str, chat_id: int) -> int:
    """새 봇 프로세스를 시작하고 PID를 반환한다."""
    import subprocess as _subprocess
    import sys as _sys
    env = {
        **os.environ,
        "PM_BOT_TOKEN": token,
        "TELEGRAM_GROUP_CHAT_ID": str(chat_id),
        "PM_ORG_NAME": org_id,
    }
    proc = _subprocess.Popen(
        [_sys.executable, str(REPO_ROOT / "main.py")],
        env=env,
        stdin=_subprocess.DEVNULL,
        stdout=_subprocess.DEVNULL,
        stderr=_subprocess.DEVNULL,
        cwd=str(REPO_ROOT),
        start_new_session=True,
    )
    pid_dir = Path.home() / ".ai-org" / "bots"
    pid_dir.mkdir(parents=True, exist_ok=True)
    (pid_dir / f"{org_id}.pid").write_text(str(proc.pid))
    return proc.pid
