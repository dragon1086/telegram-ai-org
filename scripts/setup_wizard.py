#!/usr/bin/env python3
"""telegram-ai-org 설치 마법사 v2.

표준 라이브러리만 사용 (subprocess, shutil, pathlib, json, urllib 등).
실행: python scripts/setup_wizard.py [--check] [--reset]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

from core.setup_registration import (  # noqa: F401 — re-exported as module attrs (ctx.*)
    ensure_orchestration_config,
    parse_setup_identity,
    refresh_legacy_bot_configs,
    refresh_pm_identity_files,
    upsert_org_in_canonical_config,
    upsert_runtime_env_var,
)

try:
    from scripts.setup_wizard_preflight import (
        PreflightResult as _PreflightResult,
        run_preflight as _run_preflight_impl,
        step_install_tools as _step_install_tools_impl,
    )
    from scripts.setup_wizard_storage import (
        print_final_summary as _print_final_summary_impl,
        reset_config as _reset_config_impl,
        save_all as _save_all_impl,
    )
except ImportError:
    from setup_wizard_preflight import (
        PreflightResult as _PreflightResult,
        run_preflight as _run_preflight_impl,
        step_install_tools as _step_install_tools_impl,
    )
    from setup_wizard_flow import (
        EXEC_ENGINE_LABEL,
        EXEC_MODE_LABEL,
        step_pm_bot as _step_pm_bot_impl,
        step_org_structure as _step_org_structure_impl,
        step_agent_hints as _step_agent_hints_impl,
        step_agency_agents as _step_agency_agents_impl,
        step_exec_engine as _step_exec_engine_impl,
        step_python_deps as _step_python_deps_impl,
        step_simulation as _step_simulation_impl,
        _show_engine_check as _show_engine_check_impl,
        _auto_start_bots as _auto_start_bots_impl,
    )
    from setup_wizard_storage import (
        print_final_summary as _print_final_summary_impl,
        reset_config as _reset_config_impl,
        save_all as _save_all_impl,
    )
else:
    from scripts.setup_wizard_flow import (
        EXEC_ENGINE_LABEL,
        EXEC_MODE_LABEL,
        step_pm_bot as _step_pm_bot_impl,
        step_org_structure as _step_org_structure_impl,
        step_agent_hints as _step_agent_hints_impl,
        step_agency_agents as _step_agency_agents_impl,
        step_exec_engine as _step_exec_engine_impl,
        step_python_deps as _step_python_deps_impl,
        step_simulation as _step_simulation_impl,
        _show_engine_check as _show_engine_check_impl,
        _auto_start_bots as _auto_start_bots_impl,
    )

# ─── 경로 상수 ────────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path.home() / ".ai-org"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
ORGANIZATIONS_FILE = PROJECT_ROOT / "organizations.yaml"
AGENT_HINTS_FILE = PROJECT_ROOT / "agent_hints.yaml"
WORKERS_FILE = PROJECT_ROOT / "workers.yaml"
CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
CLAUDE_AGENTS_DIR = Path.home() / ".claude" / "agents"

# ─── ANSI 색상 ────────────────────────────────────────────────────────────────

_COLOR_ENABLED = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code: str, text: str) -> str:
    if not _COLOR_ENABLED:
        return text
    return f"\033[{code}m{text}\033[0m"


def green(t: str) -> str:   return _c("32", t)
def yellow(t: str) -> str:  return _c("33", t)
def red(t: str) -> str:     return _c("31", t)
def cyan(t: str) -> str:    return _c("36", t)
def bold(t: str) -> str:    return _c("1", t)
def dim(t: str) -> str:     return _c("2", t)


# ─── 출력 유틸 ────────────────────────────────────────────────────────────────

def banner(title: str) -> None:
    line = "═" * 56
    print(f"\n{cyan('╔' + line + '╗')}")
    pad = (56 - len(title)) // 2
    print(f"{cyan('║')}{' ' * pad}{bold(title)}{' ' * (56 - pad - len(title))}{cyan('║')}")
    print(f"{cyan('╚' + line + '╝')}\n")


def step_header(n: int, label: str) -> None:
    print(f"\n{bold(cyan(f'▶ Step {n}:'))} {bold(label)}")
    print(dim("─" * 50))


def ok(msg: str) -> None:
    print(f"  {green('[OK]')}  {msg}")


def warn(msg: str) -> None:
    print(f"  {yellow('[WARN]')} {msg}")


def fail(msg: str) -> None:
    print(f"  {red('[FAIL]')} {msg}")


def info(msg: str) -> None:
    print(f"  {dim('[--]')}  {msg}")


def note(msg: str) -> None:
    print(f"       {dim(msg)}")


def ask(prompt: str, default: str = "") -> str:
    suffix = f" {dim(f'[{default}]')}" if default else ""
    try:
        val = input(f"  {prompt}{suffix}: ").strip()
    except (KeyboardInterrupt, EOFError):
        print(f"\n\n{yellow('취소됨.')}")
        sys.exit(0)
    return val or default


def ask_yes(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    raw = ask(f"{prompt} ({hint})")
    if not raw:
        return default
    return raw.lower() in ("y", "yes", "예", "ㅇ")


def mask_token(token: str) -> str:
    if len(token) < 12:
        return "****"
    return token[:6] + "****" + token[-4:]


def run_cmd(cmd: list[str], capture: bool = True) -> tuple[int, str]:
    """명령 실행. (returncode, stdout+stderr) 반환."""
    try:
        r = subprocess.run(cmd, capture_output=capture, text=True, timeout=15)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return 1, ""


# ─── Telegram 검증 ────────────────────────────────────────────────────────────

def validate_telegram_token(token: str) -> dict | None:
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read())
            if data.get("ok"):
                return data["result"]
    except Exception:
        pass
    return None


# ─── 기존 설정 로드 ───────────────────────────────────────────────────────────

def load_existing_config() -> dict[str, str]:
    """~/.ai-org/config.yaml에서 기존 설정 읽기."""
    cfg: dict[str, str] = {}
    if CONFIG_FILE.exists():
        for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                cfg[k.strip()] = v.strip()
    return cfg


def load_existing_orgs() -> list[dict]:
    """organizations.yaml에서 기존 조직 목록 읽기."""
    orgs: list[dict] = []
    if not ORGANIZATIONS_FILE.exists():
        return orgs
    try:
        import yaml

        data = yaml.safe_load(ORGANIZATIONS_FILE.read_text(encoding="utf-8")) or {}
        for entry in data.get("organizations", []):
            org_id = entry.get("id") or entry.get("name")
            if not org_id:
                continue
            orgs.append({"name": org_id, "description": entry.get("description", "")})
    except Exception:
        pass
    return orgs


# ─── Step 0/1: Preflight / 도구 설치 ─────────────────────────────────────────

PreflightResult = _PreflightResult


def run_preflight(verbose: bool = True) -> PreflightResult:
    return _run_preflight_impl(sys.modules[__name__], verbose=verbose)


def step_install_tools(r: PreflightResult) -> None:
    _step_install_tools_impl(sys.modules[__name__], r)


# ─── Step 2: PM 봇 설정 ───────────────────────────────────────────────────────

def step_pm_bot(existing: dict[str, str]) -> tuple[str, str]:
    step_header(2, "PM 봇 설정")
    default_token = existing.get("PM_BOT_TOKEN", "")
    default_chat = existing.get("TELEGRAM_GROUP_CHAT_ID", "")

    while True:
        prompt = "PM 봇 텔레그램 토큰"
        if default_token:
            prompt += f" (현재: {mask_token(default_token)})"
        token = ask(prompt, default=default_token)
        if not token:
            warn("토큰을 입력해주세요.")
            continue

        print("  토큰 검증 중...", end="", flush=True)
        bot_info = validate_telegram_token(token)
        if bot_info:
            print()
            ok(f"PM 봇 연결 확인: @{bot_info.get('username', '?')} ({bot_info.get('first_name', '')})")
            # Privacy Mode 안내
            print()
            print("  " + "─" * 44)
            print("  ⚠️  중요: Privacy Mode 반드시 해제하세요!")
            print("  " + "─" * 44)
            print("  1. 텔레그램에서 @BotFather 채팅 열기")
            print("  2. /setprivacy 입력")
            print(f"  3. @{bot_info.get('username', 'your_bot')} 선택")
            print("  4. Disable 클릭")
            print()
            print("  ℹ️  Privacy Mode가 켜져 있으면 봇이 /명령어만 받고")
            print("     일반 메시지에는 응답하지 않습니다.")
            print("  " + "─" * 44)
            ask_yes("  위 단계를 완료했나요? (나중에 해도 됩니다)", default=True)
            break
        else:
            print()
            warn("토큰 유효성 검증 실패. 오프라인이거나 잘못된 토큰입니다.")
            if ask_yes("그래도 계속하시겠어요?", default=False):
                break

    while True:
        chat_id = ask("텔레그램 그룹 채팅방 ID (예: -1001234567890)", default=default_chat)
        if chat_id.lstrip("-").isdigit():
            break
        warn("숫자만 입력하세요 (음수 가능).")

    return token, chat_id


# ─── Step 3: 조직 구성 선택 ───────────────────────────────────────────────────

def _ask_org_engine(prefix: str = "") -> str:
    """조직별 engine 선택 (1=claude-code, 2=codex, 3=auto). 기본값: claude-code."""
    print(f"\n  {prefix}{bold('실행 엔진 선택:')}")
    print(f"    {bold('1.')} claude-code  {dim('— 복잡한 작업, 고품질 [기본]')}")
    print(f"    {bold('2.')} codex        {dim('— 단순한 작업, 저렴')}")
    print(f"    {bold('3.')} auto         {dim('— LLM이 자동 결정')}")
    choice = ask(f"  {prefix}선택", default="1")
    return EXEC_ENGINE_MAP.get(choice, "claude-code")


def _ask_identity(org_id: str, prefix: str = "") -> dict[str, Any]:
    default = parse_setup_identity(org_id, "기본")
    default_text = f"{default.role}|{','.join(default.specialties)}|{default.direction}"
    raw = ask(
        f"{prefix}조직 정체성 (역할|전문분야1,전문분야2|방향성)",
        default=default_text,
    )
    parsed = parse_setup_identity(org_id, raw)
    return {
        "role": parsed.role,
        "specialties": list(parsed.specialties),
        "direction": parsed.direction,
    }


def step_org_structure(pm_token: str, pm_chat_id: str) -> list[dict]:
    """조직 목록 반환. canonical 등록용 입력 모델."""
    step_header(3, "조직 구성 선택")
    print(f"""
  조직 구성 방식을 선택하세요:
    {bold('1.')} 단일 조직 (PM 1개 + 동적 에이전트팀)  {dim('← 기본, 권장')}
    {bold('2.')} 다중 조직 (여러 PM + 조직간 협업)
""")
    choice = ask("선택", default="1")

    if choice != "2":
        # 단일 조직
        org_name = ask("조직 ID", default="global")
        org_desc = ask("조직 설명", default="총괄 PM — 사용자 요청 조율 및 실행")
        identity = _ask_identity(org_name)
        org_engine = _ask_org_engine()
        return [{
            "org_id": org_name,
            "description": org_desc,
            "pm_token": pm_token,
            "group_chat_id": pm_chat_id,
            "engine": org_engine,
            "identity": identity,
        }]

    # 다중 조직
    while True:
        try:
            count = int(ask("조직 수 (2~10)", default="2"))
            if 2 <= count <= 10:
                break
            warn("2~10 사이로 입력하세요.")
        except ValueError:
            warn("숫자를 입력하세요.")

    orgs: list[dict] = []
    for i in range(count):
        print(f"\n  {bold(f'── 조직 {i+1}/{count} ──')}")
        name = ask("  조직 ID (예: aiorg_engineering_bot)")
        desc = ask("  설명", default=f"{name} 팀")
        if i == 0 and pm_token:
            print(f"  {dim('첫 번째 조직에 방금 입력한 PM 봇을 사용합니다.')}")
            token = pm_token
            chat_id = pm_chat_id
        else:
            while True:
                token = ask("  PM 봇 토큰")
                if not token:
                    warn("토큰을 입력해주세요.")
                    continue
                print("  토큰 검증 중...", end="", flush=True)
                bot_info = validate_telegram_token(token)
                if bot_info:
                    print()
                    ok(f"@{bot_info.get('username','?')} 연결 확인")
                    break
                else:
                    print()
                    if ask_yes("검증 실패. 그래도 계속?", default=False):
                        break

            while True:
                chat_id = ask("  그룹 채팅방 ID")
                if chat_id.lstrip("-").isdigit():
                    break
                warn("숫자만 입력하세요.")

        identity = _ask_identity(name, prefix="  ")
        org_engine = _ask_org_engine(prefix="  ")
        orgs.append({
            "org_id": name,
            "description": desc,
            "pm_token": token,
            "group_chat_id": chat_id,
            "engine": org_engine,
            "identity": identity,
        })
        ok(f"{name} 조직 추가됨 (engine: {EXEC_ENGINE_LABEL.get(org_engine, org_engine)})")

    return orgs


def _auto_start_bots() -> None:
    """설정 완료 후 canonical organizations를 읽어 봇 기동."""
    import subprocess
    import time

    from core.orchestration_config import load_orchestration_config

    cfg = load_orchestration_config(
        PROJECT_ROOT / "organizations.yaml",
        PROJECT_ROOT / "orchestration.yaml",
        force_reload=True,
    )

    started = 0
    for org in cfg.list_orgs():
        try:
            org_id = org.id
            token = org.token
            chat_id = str(org.chat_id or "")
            if not token or not chat_id:
                warn(f"  {org_id}: 토큰/chat_id 없음 — 건너뜀")
                continue
            r = subprocess.run(
                [sys.executable, "scripts/bot_manager.py", "start", token, org_id, chat_id],
                capture_output=True, text=True, cwd=str(PROJECT_ROOT),
            )
            if "시작됨" in r.stdout or r.returncode == 0:
                ok(f"  {org_id} 시작됨")
                started += 1
            else:
                warn(f"  {org_id} 기동 실패: {r.stderr[:60]}")
            time.sleep(2)
        except Exception as e:
            warn(f"  {org_id}: {e}")

    if started:
        ok(f"총 {started}개 봇 자동 기동 완료")

# ─── Step 4: Agent Hints 설정 ─────────────────────────────────────────────────

HINT_PROFILES: dict[str, dict] = {
    "1": {
        "label": "개발/코딩",
        "keys": ["coding"],
        "agents": ["executor", "architect", "debugger"],
    },
    "2": {
        "label": "분석/리서치",
        "keys": ["analysis"],
        "agents": ["analyst", "scientist"],
    },
    "3": {
        "label": "문서/마케팅",
        "keys": ["writing"],
        "agents": ["writer", "document-specialist"],
    },
    "4": {
        "label": "코드 리뷰/QA",
        "keys": ["review"],
        "agents": ["code-reviewer", "qa-tester", "verifier"],
    },
    "5": {
        "label": "전체 (모두 포함)",
        "keys": ["coding", "analysis", "writing", "review", "planning"],
        "agents": [],
    },
}

FULL_HINTS_YAML = """\
# agent_hints.yaml — LLM 라우팅 힌트 카탈로그
# setup_wizard.py 가 생성한 파일입니다.

agent_hints:
  coding:
    description: "코딩, 구현, 버그 수정, 리팩토링"
    keywords: [implement, build, code, fix, refactor, debug, develop, 구현, 코딩, 개발, 수정]
    preferred_agents: [executor, architect, debugger]
    omc_team_format: "2:executor,1:architect"
    execution_mode: omc_team
    preferred_engine: claude-code

  analysis:
    description: "분석, 리서치, 데이터 처리, 시장 조사"
    keywords: [analyze, research, data, market, report, investigate, 분석, 리서치, 조사]
    preferred_agents: [analyst, scientist]
    omc_team_format: "1:analyst,1:scientist"
    execution_mode: agent_teams
    preferred_engine: auto

  writing:
    description: "문서 작성, 보고서, README, 마케팅"
    keywords: [write, document, report, README, content, blog, 작성, 문서, 보고서]
    preferred_agents: [writer, document-specialist]
    omc_team_format: "2:writer"
    execution_mode: agent_teams
    preferred_engine: claude-code

  review:
    description: "코드 리뷰, QA, 보안 감사, 품질 검증"
    keywords: [review, audit, security, quality, test, QA, verify, 리뷰, 검토, 감사]
    preferred_agents: [code-reviewer, qa-tester, verifier]
    omc_team_format: "1:code-reviewer,1:qa-tester"
    execution_mode: agent_teams
    preferred_engine: claude-code

  planning:
    description: "계획 수립, 아키텍처 설계, 전략"
    keywords: [plan, design, architect, strategy, roadmap, 계획, 설계, 전략]
    preferred_agents: [planner, architect, analyst]
    omc_team_format: "1:planner,1:architect"
    execution_mode: sequential
    preferred_engine: claude-code

  simple:
    description: "단순 실행, 빠른 작업"
    keywords: []
    preferred_agents: [executor]
    omc_team_format: "1:executor"
    execution_mode: sequential
    preferred_engine: codex
"""

SUBSET_HINTS_YAML_TPL = """\
# agent_hints.yaml — LLM 라우팅 힌트 카탈로그
# setup_wizard.py 가 생성한 파일입니다.
# 선택된 프로파일: {profiles}

agent_hints:
{sections}
  simple:
    description: "단순 실행, 빠른 작업"
    keywords: []
    preferred_agents: [executor]
    omc_team_format: "1:executor"
    execution_mode: sequential
"""

SECTION_MAP = {
    "coding": """\
  coding:
    description: "코딩, 구현, 버그 수정, 리팩토링"
    keywords: [implement, build, code, fix, refactor, debug, develop, 구현, 코딩, 개발, 수정]
    preferred_agents: [executor, architect, debugger]
    omc_team_format: "2:executor,1:architect"
    execution_mode: omc_team
    preferred_engine: claude-code
""",
    "analysis": """\
  analysis:
    description: "분석, 리서치, 데이터 처리, 시장 조사"
    keywords: [analyze, research, data, market, report, investigate, 분석, 리서치, 조사]
    preferred_agents: [analyst, scientist]
    omc_team_format: "1:analyst,1:scientist"
    execution_mode: agent_teams
    preferred_engine: auto
""",
    "writing": """\
  writing:
    description: "문서 작성, 보고서, README, 마케팅"
    keywords: [write, document, report, README, content, blog, 작성, 문서, 보고서]
    preferred_agents: [writer, document-specialist]
    omc_team_format: "2:writer"
    execution_mode: agent_teams
    preferred_engine: claude-code
""",
    "review": """\
  review:
    description: "코드 리뷰, QA, 보안 감사, 품질 검증"
    keywords: [review, audit, security, quality, test, QA, verify, 리뷰, 검토, 감사]
    preferred_agents: [code-reviewer, qa-tester, verifier]
    omc_team_format: "1:code-reviewer,1:qa-tester"
    execution_mode: agent_teams
    preferred_engine: claude-code
""",
    "planning": """\
  planning:
    description: "계획 수립, 아키텍처 설계, 전략"
    keywords: [plan, design, architect, strategy, roadmap, 계획, 설계, 전략]
    preferred_agents: [planner, architect, analyst]
    omc_team_format: "1:planner,1:architect"
    execution_mode: sequential
    preferred_engine: claude-code
""",
}


def step_agent_hints() -> None:
    step_header(4, "에이전트 힌트 설정 (agent_hints.yaml)")
    print(f"""
  어떤 작업 유형을 주로 다루나요? {dim('(복수 선택 가능)')}
    {bold('1.')} 개발/코딩        {dim('(executor, architect, debugger)')}
    {bold('2.')} 분석/리서치       {dim('(analyst, scientist)')}
    {bold('3.')} 문서/마케팅       {dim('(writer, document-specialist)')}
    {bold('4.')} 코드 리뷰/QA     {dim('(code-reviewer, qa-tester)')}
    {bold('5.')} 전체 {dim('(모두 포함)')}
""")
    raw = ask("선택 (예: 1,2,3)", default="5")
    choices = [c.strip() for c in raw.replace(" ", "").split(",")]

    if "5" in choices or not choices:
        AGENT_HINTS_FILE.write_text(FULL_HINTS_YAML, encoding="utf-8")
        ok("agent_hints.yaml 생성 (전체 프로파일)")
        return

    selected_keys: list[str] = []
    labels: list[str] = []
    for c in choices:
        profile = HINT_PROFILES.get(c)
        if profile:
            selected_keys.extend(profile["keys"])
            labels.append(profile["label"])

    # 중복 제거
    seen: set[str] = set()
    unique_keys = [k for k in selected_keys if not (k in seen or seen.add(k))]  # type: ignore

    sections = "\n".join(SECTION_MAP[k] for k in unique_keys if k in SECTION_MAP)
    content = SUBSET_HINTS_YAML_TPL.format(
        profiles=", ".join(labels),
        sections=sections,
    )
    AGENT_HINTS_FILE.write_text(content, encoding="utf-8")
    ok(f"agent_hints.yaml 생성 ({', '.join(labels)})")



# ─── Step 4b: agency-agents 설치 ─────────────────────────────────────────────

def step_agency_agents() -> None:
    step_header("4b", "agency-agents 커뮤니티 에이전트 설치")
    agents_dir = Path.home() / ".claude" / "agents"
    existing = len(list(agents_dir.glob("*.md"))) if agents_dir.exists() else 0

    print(f"""
  {bold('agency-agents')} — 커뮤니티가 만든 전문 에이전트 컬렉션
  {dim('https://github.com/msitarzewski/agency-agents')}

  포함 항목:
    • engineering  — Frontend, Backend, AI Engineer, DevOps, Security...
    • marketing    — Social Media, Content, Brand, SEO...
    • design       — UI/UX, Brand Guardian, Visual Storyteller...
    • testing      — QA, Performance, Accessibility...
    • product      — Product Manager, Roadmap, Growth...
    • + 총 130개+ 전문 에이전트

  현재 {bold(str(existing))}개 에이전트 설치됨
""")

    choice = ask("agency-agents 설치할까요?", default="y").strip().lower()
    if choice not in ("y", "yes", ""):
        info("건너뜀 — 나중에 수동으로 설치 가능:")
        print(f"  {dim('git clone https://github.com/msitarzewski/agency-agents /tmp/agency-agents')}")
        print("  " + dim(r'find /tmp/agency-agents -name "*.md" ! -path "*/examples/*" -exec cp {} ~/.claude/agents/ \;'))
        return

    import subprocess as _sp
    import tempfile
    tmp = Path(tempfile.mkdtemp()) / "agency-agents"
    info("다운로드 중...")
    result = _sp.run(
        ["git", "clone", "--depth=1", "https://github.com/msitarzewski/agency-agents", str(tmp)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        warn(f"다운로드 실패: {result.stderr[:100]}")
        return

    agents_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for md in tmp.glob("**/*.md"):
        if any(skip in str(md) for skip in ["examples/", ".github/", "README", "CONTRIBUTING"]):
            continue
        shutil.copy(md, agents_dir / md.name)
        count += 1

    shutil.rmtree(tmp, ignore_errors=True)
    total = len(list(agents_dir.glob("*.md")))
    ok(f"agency-agents {count}개 설치 완료 → 총 {total}개 에이전트")

# ─── Step 5: 실행 엔진 기본값 ─────────────────────────────────────────────────

EXEC_MODE_MAP = {"1": "omc_team", "2": "agent_teams", "3": "auto"}
EXEC_MODE_LABEL = {
    "omc_team": "omc /team",
    "agent_teams": "Claude Code Agent Teams",
    "auto": "자동 선택 (LLM이 태스크에 따라 결정)",
}
EXEC_ENGINE_MAP = {"1": "claude-code", "2": "codex", "3": "auto"}
EXEC_ENGINE_LABEL = {
    "claude-code": "Claude Code (omc /team)",
    "codex": "Codex CLI",
    "auto": "자동 결정 (태스크 복잡도에 따라 선택)",
}
_ENGINE_TO_EXEC_MODE = {"claude-code": "omc_team", "codex": "sequential", "auto": "auto"}
_CATEGORY_ENGINE_DEFAULTS = {"coding": "1", "analysis": "3", "writing": "1", "review": "1"}
_CATEGORY_LABELS = {
    "coding": "개발/코딩 작업",
    "analysis": "분석/리서치 작업",
    "writing": "문서/마케팅 작업",
    "review": "코드 리뷰/QA",
}


def _update_agent_hints_engines(category_engines: dict[str, str]) -> None:
    """agent_hints.yaml의 각 카테고리 preferred_engine 라인을 업데이트."""
    if not AGENT_HINTS_FILE.exists():
        return
    try:
        import re as _re
        lines = AGENT_HINTS_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
        current_section: str | None = None
        new_lines: list[str] = []
        for line in lines:
            m = _re.match(r"^  (\w[\w-]*):\s*$", line)
            if m:
                current_section = m.group(1)
            if current_section in category_engines and line.strip().startswith("preferred_engine:"):
                indent = len(line) - len(line.lstrip())
                new_lines.append(" " * indent + f"preferred_engine: {category_engines[current_section]}\n")
                continue
            new_lines.append(line)
        AGENT_HINTS_FILE.write_text("".join(new_lines), encoding="utf-8")
        ok("agent_hints.yaml 엔진 설정 업데이트 완료")
    except Exception as e:
        warn(f"agent_hints.yaml 업데이트 실패: {e}")


def _show_engine_check() -> None:
    """--check 모드에서 agent_hints.yaml의 엔진 설정 현황 출력."""
    if not AGENT_HINTS_FILE.exists():
        return
    try:
        import re as _re
        content = AGENT_HINTS_FILE.read_text(encoding="utf-8")
        current_section: str | None = None
        print(f"\n  {bold('카테고리별 엔진:')}")
        for line in content.splitlines():
            m = _re.match(r"^  (\w[\w-]*):\s*$", line)
            if m:
                current_section = m.group(1)
            if current_section and line.strip().startswith("preferred_engine:"):
                eng = line.strip().split(":", 1)[1].strip()
                label = EXEC_ENGINE_LABEL.get(eng, eng)
                print(f"    • {current_section}: {label}")
    except Exception:
        pass


def step_exec_engine(
    existing_cfg: dict[str, str],
    preflight: PreflightResult | None = None,
) -> tuple[str, str]:
    """실행 엔진 설정. Returns (exec_mode, preferred_engine)."""
    step_header(5, "실행 엔진 설정")

    both_detected = preflight is not None and preflight.claude_ok and preflight.codex_ok
    if both_detected:
        assert preflight is not None
        print(f"\n  {green('[OK]')} Claude Code ... {dim(preflight.claude_ver)}")
        print(f"  {green('[OK]')} Codex .......... {dim(preflight.codex_ver)}")
        print(f"\n  {bold('둘 다 감지됐습니다! 실행 엔진을 설정합니다.')}")

    current_engine = existing_cfg.get("PREFERRED_ENGINE", "claude-code")
    current_label = EXEC_ENGINE_LABEL.get(current_engine, current_engine)
    print(f"""
  기본 실행 엔진 선택: {dim(f'(현재: {current_label})')}
    {bold('1.')} Claude Code + omc /team  {dim('— 복잡한 태스크, 페르소나 21개, plan→exec→verify 파이프라인 [권장]')}
    {bold('2.')} Codex                    {dim('— 빠른 단순 태스크')}
    {bold('3.')} 자동 결정                {dim('— LLM이 태스크 복잡도에 따라 선택 (둘 다 사용)')}
""")
    default_choice = {"claude-code": "1", "codex": "2", "auto": "3"}.get(current_engine, "1")
    choice = ask("선택", default=default_choice)
    engine = EXEC_ENGINE_MAP.get(choice, "claude-code")
    exec_mode = _ENGINE_TO_EXEC_MODE.get(engine, "auto")
    ok(f"기본 실행 엔진: {EXEC_ENGINE_LABEL[engine]}")

    # 태스크 유형별 선호 엔진 (둘 다 감지됐을 때만)
    if both_detected:
        print(f"\n  {bold('태스크 유형별 선호 엔진 설정')} {dim('(엔터=기본값, 1=Claude Code, 2=Codex, 3=자동)')}\n")
        category_engines: dict[str, str] = {}
        for cat_key, cat_label in _CATEGORY_LABELS.items():
            default = _CATEGORY_ENGINE_DEFAULTS[cat_key]
            raw = ask(f"  {cat_label} (1/2/3)", default=default)
            cat_choice = raw if raw in ("1", "2", "3") else default
            category_engines[cat_key] = EXEC_ENGINE_MAP.get(cat_choice, "claude-code")
        _update_agent_hints_engines(category_engines)

    return exec_mode, engine


# ─── Step 6: Python 의존성 설치 ───────────────────────────────────────────────

PACKAGES = ["aiosqlite", "loguru", "python-telegram-bot", "openai", "pyyaml"]
VENV_DIR = PROJECT_ROOT / ".venv"


def step_python_deps(deps_missing: list[str]) -> None:
    step_header(6, "Python 의존성 설치")
    print(f"""
  Python 의존성 설치:
    - 프로젝트 venv 생성: {VENV_DIR}
    - 설치할 패키지: {' '.join(PACKAGES)}
""")
    if not ask_yes("지금 설치하시겠어요?"):
        info("건너뜀 — 나중에 수동 설치: pip install " + " ".join(PACKAGES))
        return

    # venv 생성
    if not (VENV_DIR / "bin" / "python").exists():
        print("  venv 생성 중...", end="", flush=True)
        rc, out = run_cmd([sys.executable, "-m", "venv", str(VENV_DIR)], capture=True)
        if rc != 0:
            print()
            warn(f"venv 생성 실패: {out}")
            return
        print(f" {green('완료')}")
    else:
        info(f"기존 venv 사용: {VENV_DIR}")

    pip = str(VENV_DIR / "bin" / "pip")
    print("  패키지 설치 중...", end="", flush=True)
    rc, out = run_cmd([pip, "install", "--upgrade"] + PACKAGES, capture=True)
    if rc == 0:
        print(f" {green('완료')}")
        ok("모든 의존성 설치 완료")
    else:
        print()
        warn(f"일부 패키지 설치 실패:\n{out[-500:]}")


# ─── Step 7: 시뮬레이션 검증 ─────────────────────────────────────────────────

def step_simulation() -> None:
    step_header(7, "시뮬레이션 검증")
    print(f"""
  설정이 완료되었습니다.
  {dim('시뮬레이션: DynamicTeamBuilder dry-run으로 팀 구성 결과를 확인합니다.')}
""")
    if not ask_yes("시뮬레이션으로 검증하시겠어요?"):
        info("건너뜀")
        return

    sim_script = PROJECT_ROOT / "simulation_mode.py"
    if not sim_script.exists():
        warn(f"simulation_mode.py 미존재: {sim_script}")
        return

    python_bin = str(VENV_DIR / "bin" / "python") if (VENV_DIR / "bin" / "python").exists() else sys.executable
    test_task = "프리즘 인사이트 주간 보고서 작성해줘"
    print(f"\n  태스크: {cyan(repr(test_task))}")
    print("  팀 구성 중...\n")

    rc, out = run_cmd([python_bin, str(sim_script), "--task", test_task, "--dry-run"], capture=True)
    if out:
        for line in out.splitlines()[:30]:
            print(f"  {dim(line)}")

    if rc == 0:
        ok("시뮬레이션 성공 — DynamicTeamBuilder 정상 작동")
    else:
        warn("시뮬레이션에서 오류 발생 (설정 자체는 저장됨)")


# ─── 설정 저장 ────────────────────────────────────────────────────────────────

step_pm_bot = lambda existing: _step_pm_bot_impl(sys.modules[__name__], existing)
step_org_structure = lambda pm_token, pm_chat_id: _step_org_structure_impl(sys.modules[__name__], pm_token, pm_chat_id)
step_agent_hints = lambda: _step_agent_hints_impl(sys.modules[__name__])
step_agency_agents = lambda: _step_agency_agents_impl(sys.modules[__name__])
step_exec_engine = lambda existing_cfg, preflight=None: _step_exec_engine_impl(sys.modules[__name__], existing_cfg, preflight)
step_python_deps = lambda deps_missing: _step_python_deps_impl(sys.modules[__name__], deps_missing)
step_simulation = lambda: _step_simulation_impl(sys.modules[__name__])
_show_engine_check = lambda: _show_engine_check_impl(sys.modules[__name__])
_auto_start_bots = lambda: _auto_start_bots_impl(sys.modules[__name__])

def save_all(orgs: list[dict], exec_mode: str, binaries: dict, preferred_engine: str = "claude-code") -> None:
    _save_all_impl(sys.modules[__name__], orgs, exec_mode, binaries, preferred_engine)


MEMORY_DIR = CONFIG_DIR / "memory"


def print_final_summary(r: PreflightResult, orgs: list[dict], exec_mode: str, preferred_engine: str = "claude-code") -> None:
    _print_final_summary_impl(sys.modules[__name__], r, orgs, exec_mode, preferred_engine)


def reset_config(keep_memory: bool | None = None) -> None:
    _reset_config_impl(sys.modules[__name__], keep_memory)


# ─── 메인 ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="telegram-ai-org 설치 마법사 v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--check", action="store_true", help="Preflight check만 실행하고 종료")
    parser.add_argument("--reset", action="store_true", help="기존 설정 초기화 후 처음부터")
    args = parser.parse_args()

    if args.reset:
        reset_config()

    banner("🤖 telegram-ai-org 설치 마법사 v2")
    print(f"  {dim('Ctrl+C로 언제든 취소할 수 있습니다.')}\n")

    # 기존 설정 감지 (--reset 없이 실행 시)
    if not args.reset and CONFIG_FILE.exists():
        existing_quick = load_existing_config()
        pm_token_preview = existing_quick.get("PM_BOT_TOKEN", "")
        chat_id_preview = existing_quick.get("TELEGRAM_GROUP_CHAT_ID", "")
        token_display = f"@?? (토큰: {mask_token(pm_token_preview)})" if pm_token_preview else "미설정"
        chat_display = chat_id_preview if chat_id_preview else "미설정"
        print(f"  {yellow('기존 설정이 감지됐습니다')} ({token_display}, {chat_display}).")
        print(f"""
    {bold('1.')} 기존 설정 유지하고 계속
    {bold('2.')} 초기화 후 처음부터
""")
        choice = ask("선택", default="1")
        if choice == "2":
            reset_config()

    # Step 0: Preflight
    step_header(0, "Preflight Check (자동 환경 점검)")
    preflight = run_preflight(verbose=True)

    if args.check:
        issues = preflight.issues
        # 엔진 설정 현황
        existing_check = load_existing_config()
        preferred_engine_check = existing_check.get("PREFERRED_ENGINE", "미설정")
        exec_mode_check = existing_check.get("DEFAULT_EXECUTION_MODE", "미설정")
        print(f"\n{bold('⚙ 엔진 설정:')}")
        print(f"  기본 엔진: {EXEC_ENGINE_LABEL.get(preferred_engine_check, preferred_engine_check)}")
        print(f"  실행 모드: {EXEC_MODE_LABEL.get(exec_mode_check, exec_mode_check)}")
        _show_engine_check()
        if issues:
            print(f"\n{yellow('⚠ 문제 감지:')} {', '.join(issues)}")
        else:
            print(f"\n{green('✓ 모든 환경 점검 통과!')}")
        sys.exit(0 if not issues else 1)

    print()
    if not preflight.issues:
        print(f"  {green('✓ 환경 점검 완료 — 모든 항목 정상')}")
    else:
        print(f"  {yellow('⚠ 일부 항목 개선 필요:')} {', '.join(preflight.issues)}")

    if not ask_yes("\n마법사를 계속 진행하시겠어요?"):
        sys.exit(0)

    # Step 1: 도구 설치 안내 (문제 있을 때만)
    if any(i in preflight.issues for i in ("claude", "omc", "agent_teams", "deps")):
        step_install_tools(preflight)

    # 기존 설정 로드
    existing_cfg = load_existing_config()

    # Step 2: PM 봇 설정
    pm_token, pm_chat_id = step_pm_bot(existing_cfg)

    # Step 3: 조직 구성
    orgs = step_org_structure(pm_token, pm_chat_id)

    # Step 4: 에이전트 힌트
    step_agent_hints()

    # Step 4b: agency-agents
    step_agency_agents()

    # Step 5: 실행 엔진
    exec_mode, preferred_engine = step_exec_engine(existing_cfg, preflight)

    # Step 6: Python 의존성
    step_python_deps(preflight.deps_missing)

    # 설정 저장
    binaries = {"claude": preflight.claude_path, "codex": preflight.codex_path}
    save_all(orgs, exec_mode, binaries, preferred_engine)

    # Step 7: 시뮬레이션 검증
    step_simulation()

    # Step 8: 봇 자동 기동
    _auto_start_bots()

    # 완료 화면
    print_final_summary(preflight, orgs, exec_mode, preferred_engine)


if __name__ == "__main__":
    main()
