#!/usr/bin/env python3
"""telegram-ai-org 설치 마법사 v2.

표준 라이브러리만 사용 (subprocess, shutil, pathlib, json, urllib 등).
실행: python scripts/setup_wizard.py [--check] [--reset]
"""
from __future__ import annotations

import argparse
import glob as _glob
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any

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
    """organizations.yaml에서 기존 조직 목록 읽기 (yaml 없이 간단 파싱)."""
    orgs: list[dict] = []
    if not ORGANIZATIONS_FILE.exists():
        return orgs
    try:
        import re
        content = ORGANIZATIONS_FILE.read_text(encoding="utf-8")
        # 단순 파싱: name: 값 추출
        names = re.findall(r"^\s+- name:\s*(.+)$", content, re.MULTILINE)
        descs = re.findall(r"^\s+description:\s*[\"']?(.+?)[\"']?$", content, re.MULTILINE)
        for i, name in enumerate(names):
            orgs.append({"name": name.strip(), "description": descs[i].strip() if i < len(descs) else ""})
    except Exception:
        pass
    return orgs


# ─── Step 0: Preflight Check ─────────────────────────────────────────────────

class PreflightResult:
    def __init__(self) -> None:
        self.python_ok = False
        self.python_ver = ""
        self.claude_ok = False
        self.claude_path = ""
        self.claude_ver = ""
        self.codex_ok = False
        self.codex_path = ""
        self.codex_ver = ""
        self.omc_ok = False
        self.omc_ver = ""
        self.omc_path = ""
        self.team_mcp_ok = False
        self.agent_teams_ok = False
        self.agent_count = 0
        self.agent_names: list[str] = []
        self.config_ok = False
        self.pm_token_ok = False
        self.worker_token_ok = False
        self.deps_ok = False
        self.deps_missing: list[str] = []
        self.issues: list[str] = []


def run_preflight(verbose: bool = True) -> PreflightResult:
    r = PreflightResult()

    if verbose:
        print(f"\n{bold('🔍 환경 점검 중...')}\n")

    # Python 버전
    v = sys.version_info
    r.python_ver = f"Python {v.major}.{v.minor}.{v.micro}"
    r.python_ok = (v.major, v.minor) >= (3, 11)
    if verbose:
        _pf_line("Python 3.11+", r.python_ok, r.python_ver, warn_not_fail=False)
    if not r.python_ok:
        r.issues.append("python")

    # Claude Code
    r.claude_path = shutil.which("claude") or ""
    if r.claude_path:
        rc, out = run_cmd(["claude", "--version"])
        r.claude_ver = out.splitlines()[0] if out else "버전 미확인"
        r.claude_ok = rc == 0
    if verbose:
        if r.claude_ok:
            _pf_line("Claude Code", True, f"{r.claude_path} {r.claude_ver}")
        else:
            _pf_line("Claude Code", False, "미감지", warn_not_fail=False)
    if not r.claude_ok:
        r.issues.append("claude")

    # Codex (선택)
    r.codex_path = shutil.which("codex") or ""
    if r.codex_path:
        rc, out = run_cmd(["codex", "--version"])
        r.codex_ver = out.splitlines()[0] if out else "버전 미확인"
        r.codex_ok = rc == 0
    if verbose:
        if r.codex_ok:
            _pf_line("Codex", True, f"{r.codex_path} {r.codex_ver}", optional=True)
        else:
            _pf_line("Codex", None, "미감지 (선택사항)", optional=True)

    # omc 감지
    omc_glob = str(Path.home() / ".claude/plugins/cache/omc/oh-my-claudecode/*/bridge/mcp-server.cjs")
    omc_files = _glob.glob(omc_glob)
    if omc_files:
        omc_dir = Path(omc_files[0]).parent.parent
        pkg_json = omc_dir / "package.json"
        if pkg_json.exists():
            try:
                pkg = json.loads(pkg_json.read_text())
                r.omc_ver = pkg.get("version", "?")
            except Exception:
                r.omc_ver = "?"
        r.omc_path = str(omc_files[0])
        r.omc_ok = True
    if verbose:
        if r.omc_ok:
            _pf_line("oh-my-claudecode (omc)", True, f"v{r.omc_ver} 설치됨")
        else:
            _pf_line("oh-my-claudecode (omc)", False, "미감지")
    if not r.omc_ok:
        r.issues.append("omc")

    # omc team MCP
    team_glob = str(Path.home() / ".claude/plugins/cache/omc/oh-my-claudecode/*/bridge/team-mcp.cjs")
    team_files = _glob.glob(team_glob)
    r.team_mcp_ok = len(team_files) > 0
    if verbose:
        _pf_line("omc team MCP 서버", r.team_mcp_ok,
                 "Connected" if r.team_mcp_ok else "미감지")
    if not r.team_mcp_ok:
        r.issues.append("team_mcp")

    # AGENT_TEAMS 활성화
    if CLAUDE_SETTINGS.exists():
        try:
            settings = json.loads(CLAUDE_SETTINGS.read_text())
            env = settings.get("env", {})
            val = env.get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "")
            r.agent_teams_ok = str(val).lower() in ("1", "true", "yes")
        except Exception:
            pass
    if verbose:
        _pf_line("Agent Teams 활성화", r.agent_teams_ok,
                 "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1" if r.agent_teams_ok else "비활성화")
    if not r.agent_teams_ok:
        r.issues.append("agent_teams")

    # 에이전트 페르소나
    agent_files = list(CLAUDE_AGENTS_DIR.glob("*.md")) if CLAUDE_AGENTS_DIR.exists() else []
    r.agent_count = len(agent_files)
    r.agent_names = [f.stem for f in agent_files[:5]]
    if r.agent_count > 5:
        r.agent_names.append(f"... +{r.agent_count - 5}개")
    agents_ok = r.agent_count > 0
    if verbose:
        names_str = ", ".join(r.agent_names) if r.agent_names else ""
        _pf_line("에이전트 페르소나", agents_ok,
                 f"{r.agent_count}개 ({names_str})" if agents_ok else "미감지")
    if not agents_ok:
        r.issues.append("agents")

    # config.yaml 존재
    r.config_ok = CONFIG_FILE.exists()
    if verbose:
        _pf_line("~/.ai-org/config.yaml", r.config_ok if r.config_ok else None,
                 "존재" if r.config_ok else "미존재 → 이 마법사에서 생성")

    # PM 봇 토큰
    existing = load_existing_config()
    r.pm_token_ok = bool(existing.get("PM_BOT_TOKEN") or os.environ.get("PM_BOT_TOKEN"))
    if verbose:
        _pf_line("PM 봇 토큰", r.pm_token_ok if r.pm_token_ok else None,
                 "설정됨" if r.pm_token_ok else "미설정")

    # 워커 봇 토큰 (organizations.yaml 또는 workers.yaml 기반)
    r.worker_token_ok = WORKERS_FILE.exists() or ORGANIZATIONS_FILE.exists()
    if verbose:
        _pf_line("조직/워커 설정", r.worker_token_ok if r.worker_token_ok else None,
                 "설정됨" if r.worker_token_ok else "미설정")

    # Python 의존성
    REQUIRED_PKGS = ["aiosqlite", "loguru", "telegram", "openai", "yaml"]
    PKG_IMPORT_MAP = {"telegram": "telegram", "yaml": "yaml", "openai": "openai",
                      "aiosqlite": "aiosqlite", "loguru": "loguru"}
    for pkg in REQUIRED_PKGS:
        import_name = PKG_IMPORT_MAP.get(pkg, pkg)
        try:
            __import__(import_name)
        except ImportError:
            r.deps_missing.append(pkg)
    r.deps_ok = len(r.deps_missing) == 0
    if verbose:
        if r.deps_ok:
            _pf_line("Python 의존성", True, "requirements.txt 설치됨")
        else:
            _pf_line("Python 의존성", None,
                     f"미설치: {', '.join(r.deps_missing)}")
    if not r.deps_ok:
        r.issues.append("deps")

    return r


def _pf_line(label: str, status: bool | None, detail: str,
             warn_not_fail: bool = True, optional: bool = False) -> None:
    """Preflight 체크 라인 출력."""
    label_padded = label.ljust(36, ".")
    if status is True:
        tag = green("[OK]  ")
    elif status is False:
        tag = (yellow("[WARN]") if warn_not_fail else red("[FAIL]"))
    else:
        # None = warning / optional
        tag = yellow("[WARN]") if not optional else dim("[--]  ")

    print(f"  {tag} {label_padded} {dim(detail)}")


# ─── Step 1: 도구 설치 안내 ───────────────────────────────────────────────────

def step_install_tools(r: PreflightResult) -> None:
    """Preflight 실패 항목에 대해 설치 안내."""
    actionable = [i for i in r.issues if i in ("claude", "omc", "agent_teams", "deps")]
    if not actionable:
        return

    step_header(1, "필수 도구 설치 안내")

    if "claude" in r.issues:
        print(f"\n  {bold('Claude Code')} 미설치:")
        print(f"    {cyan('npm install -g @anthropic-ai/claude-code')}")
        _ = ask_yes("  Claude Code 설치 후 계속하시겠어요?")

    if "omc" in r.issues:
        print(f"\n  {bold('oh-my-claudecode')} 미설치:")
        print(f"    {cyan('claude /plugin install oh-my-claudecode')}")
        _ = ask_yes("  omc 설치 후 계속하시겠어요?")

    if "agent_teams" in r.issues:
        print(f"\n  {bold('Agent Teams')} 비활성화됨.")
        if ask_yes("  자동으로 ~/.claude/settings.json에 활성화할까요?"):
            _enable_agent_teams()

    if "deps" in r.issues:
        print(f"\n  {bold('Python 의존성')} 미설치: {', '.join(r.deps_missing)}")
        print(f"  (Step 6에서 자동 설치 안내 예정)")


def _enable_agent_teams() -> None:
    """~/.claude/settings.json에 CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1 추가."""
    try:
        if CLAUDE_SETTINGS.exists():
            settings = json.loads(CLAUDE_SETTINGS.read_text())
        else:
            settings = {}
        if "env" not in settings:
            settings["env"] = {}
        settings["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"
        CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        CLAUDE_SETTINGS.write_text(json.dumps(settings, indent=2, ensure_ascii=False))
        ok("Agent Teams 활성화 완료 (Claude Code 재시작 필요)")
    except Exception as e:
        warn(f"settings.json 수정 실패: {e}")


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
            print(f"  1. 텔레그램에서 @BotFather 채팅 열기")
            print(f"  2. /setprivacy 입력")
            print(f"  3. @{bot_info.get('username', 'your_bot')} 선택")
            print(f"  4. Disable 클릭")
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

def step_org_structure(pm_token: str, pm_chat_id: str) -> list[dict]:
    """조직 목록 반환. [{name, description, pm_token, group_chat_id}]"""
    step_header(3, "조직 구성 선택")
    print(f"""
  조직 구성 방식을 선택하세요:
    {bold('1.')} 단일 조직 (PM 1개 + 동적 에이전트팀)  {dim('← 기본, 권장')}
    {bold('2.')} 다중 조직 (여러 PM + 조직간 협업)
""")
    choice = ask("선택", default="1")

    if choice != "2":
        # 단일 조직
        org_name = ask("조직 이름", default="dev_team")
        org_desc = ask("조직 설명", default="개발팀 — 코딩, 구현, 배포")
        specialties_raw = ask("이 PM의 전문분야를 입력하세요 (콤마 구분, 예: 코딩, 버그, API)", default="일반")
        specialties = [s.strip() for s in specialties_raw.split(",") if s.strip()]
        _generate_pm_identity(org_name, pm_token, int(pm_chat_id) if pm_chat_id.lstrip("-").isdigit() else 0, specialties, org_desc)
        return [{"name": org_name, "description": org_desc,
                 "pm_token": pm_token, "group_chat_id": pm_chat_id}]

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
        name = ask("  이름 (예: dev_team, marketing_team)")
        desc = ask("  설명", default=f"{name} 팀")
        if i == 0 and pm_token:
            print(f"  {dim('첫 번째 조직에 방금 입력한 PM 봇을 사용합니다.')}")
            token = pm_token
            chat_id = pm_chat_id
        else:
            while True:
                token = ask(f"  PM 봇 토큰")
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
                chat_id = ask(f"  그룹 채팅방 ID")
                if chat_id.lstrip("-").isdigit():
                    break
                warn("숫자만 입력하세요.")

        specialties_raw = ask(f"  이 PM의 전문분야를 입력하세요 (콤마 구분, 예: 코딩, 버그, API)", default="일반")
        specialties = [s.strip() for s in specialties_raw.split(",") if s.strip()]
        chat_id_int = int(chat_id) if chat_id.lstrip("-").isdigit() else 0
        _generate_pm_identity(name, token, chat_id_int, specialties, desc)
        print(f"  ✅ pm_{name}.md 생성 완료")

        orgs.append({"name": name, "description": desc,
                     "pm_token": token, "group_chat_id": chat_id})
        ok(f"{name} 조직 추가됨")

    return orgs


def _generate_pm_identity(org_id: str, bot_token: str, chat_id: int, specialties: list[str], role: str = "") -> None:
    """pm_{org_id}.md 자동 생성."""
    try:
        sys.path.insert(0, str(PROJECT_ROOT))
        from core.org_registry import OrgRegistry
        registry = OrgRegistry()
        registry.register_org(
            org_id=org_id,
            bot_token=bot_token,
            chat_id=chat_id,
            specialties=specialties,
            role=role,
        )
        print(f"  ✅ pm_{org_id}.md 생성 완료")
    except Exception as e:
        # fallback: 직접 파일 생성
        memory_dir = Path.home() / ".ai-org" / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        specialties_str = ", ".join(specialties) if specialties else "일반"
        content = (
            f"## [CORE] PM 정체성\n"
            f"- 봇명: @aiorg_{org_id}_pm_bot ({org_id})\n"
            f"- 역할: {role or org_id + ' PM'}\n"
            f"- 전문분야: {specialties_str}\n\n"
            f"## [CORE] 조직 목록\n"
            f"- pm_global: 전체 조율, 일반 대화\n"
            f"- pm_{org_id}: {specialties_str}\n"
        )
        (memory_dir / f"pm_{org_id}.md").write_text(content, encoding="utf-8")
        warn(f"OrgRegistry 사용 불가 ({e}), 직접 파일 생성 완료")


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
        ok(f"agent_hints.yaml 생성 (전체 프로파일)")
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

def save_all(orgs: list[dict], exec_mode: str, binaries: dict, preferred_engine: str = "claude-code") -> None:
    """config.yaml + organizations.yaml 저장."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # config.yaml
    lines = ["# telegram-ai-org 설정 (setup_wizard.py v2 생성)\n\n"]
    first_org = orgs[0] if orgs else {}
    lines.append(f"PM_BOT_TOKEN={first_org.get('pm_token', '')}\n")
    lines.append(f"TELEGRAM_GROUP_CHAT_ID={first_org.get('group_chat_id', '')}\n")
    lines.append(f"DEFAULT_EXECUTION_MODE={exec_mode}\n")
    lines.append(f"PREFERRED_ENGINE={preferred_engine}\n")
    if binaries.get("claude"):
        lines.append(f"CLAUDE_CLI_PATH={binaries['claude']}\n")
    if binaries.get("codex"):
        lines.append(f"CODEX_CLI_PATH={binaries['codex']}\n")
    lines.append("CONTEXT_DB_PATH=~/.ai-org/context.db\n")

    # 다중 조직 토큰
    if len(orgs) > 1:
        lines.append("\n# 추가 조직 토큰\n")
        for i, org in enumerate(orgs[1:], 2):
            env_name = org["name"].upper()
            lines.append(f"{env_name}_PM_TOKEN={org['pm_token']}\n")
            lines.append(f"{env_name}_GROUP_CHAT_ID={org['group_chat_id']}\n")

    CONFIG_FILE.write_text("".join(lines), encoding="utf-8")
    ok(f"설정 저장: {CONFIG_FILE}")

    # organizations.yaml
    org_lines = [
        "# AI 조직 설정 (setup_wizard.py v2 생성)\n",
        "# 각 조직은 독립된 PM봇 + 동적 에이전트팀으로 운영됩니다.\n\n",
        "organizations:\n",
    ]
    for i, org in enumerate(orgs):
        env_name = org["name"].upper()
        token_ref = "${PM_BOT_TOKEN}" if i == 0 else f"${{{env_name}_PM_TOKEN}}"
        chat_ref = "${TELEGRAM_GROUP_CHAT_ID}" if i == 0 else f"${{{env_name}_GROUP_CHAT_ID}}"
        org_lines += [
            f"  - name: {org['name']}\n",
            f"    description: \"{org['description']}\"\n",
            f"    pm_token: \"{token_ref}\"\n",
            f"    group_chat_id: \"{chat_ref}\"\n",
        ]
    ORGANIZATIONS_FILE.write_text("".join(org_lines), encoding="utf-8")
    ok(f"조직 설정 저장: {ORGANIZATIONS_FILE}")


# ─── 완료 화면 ────────────────────────────────────────────────────────────────

def print_final_summary(r: PreflightResult, orgs: list[dict], exec_mode: str, preferred_engine: str = "claude-code") -> None:
    banner("✅ telegram-ai-org 설정 완료!")

    print(f"  {bold('환경:')}")
    if r.claude_ok:
        print(f"    • Claude Code: {r.claude_path} {r.claude_ver}")
    if r.omc_ok:
        team_str = "team MCP ✓" if r.team_mcp_ok else "team MCP ✗"
        teams_str = "Agent Teams ✓" if r.agent_teams_ok else "Agent Teams ✗"
        print(f"    • omc: v{r.omc_ver} ({team_str}, {teams_str})")
    if r.agent_count > 0:
        print(f"    • 에이전트: {r.agent_count}개 페르소나 로드됨")
    print(f"    • 실행 모드: {EXEC_MODE_LABEL.get(exec_mode, exec_mode)}")
    print(f"    • 기본 엔진: {EXEC_ENGINE_LABEL.get(preferred_engine, preferred_engine)}")

    print(f"\n  {bold('조직:')}")
    for org in orgs:
        print(f"    • {bold(org['name'])} — {org['description']}")

    print(f"\n  {bold('저장된 파일:')}")
    print(f"    • {CONFIG_FILE}")
    print(f"    • {ORGANIZATIONS_FILE}")
    print(f"    • {AGENT_HINTS_FILE}")

    print(f"\n  {bold('시작:')}")
    print(f"    {cyan('cd ~/telegram-ai-org')}")
    if (VENV_DIR / "bin" / "activate").exists():
        print(f"    {cyan('source .venv/bin/activate')}")
    print(f"    {cyan('python main.py')}  {dim('# 또는 bash scripts/start_all.sh')}")
    print()


# ─── 설정 초기화 ──────────────────────────────────────────────────────────────

MEMORY_DIR = CONFIG_DIR / "memory"


def reset_config(keep_memory: bool | None = None) -> None:
    """--reset: 기존 설정 파일 초기화."""
    files = [CONFIG_FILE, ORGANIZATIONS_FILE, AGENT_HINTS_FILE, WORKERS_FILE]

    print(f"\n{bold(red('⚠️  기존 설정을 초기화합니다.'))}")
    print(f"삭제될 항목:")
    for f in files:
        if f.exists():
            print(f"  • {f}")

    if not ask_yes("정말 초기화하시겠어요?", default=False):
        print("취소됨.")
        sys.exit(0)

    # 메모리 보존 여부
    memory_exists = MEMORY_DIR.exists() and any(MEMORY_DIR.iterdir()) if MEMORY_DIR.exists() else False
    if keep_memory is None and memory_exists:
        keep_memory = ask_yes("메모리는 보존하시겠습니까?", default=True)

    for f in files:
        if f.exists():
            f.unlink()
            print(f"  {red('삭제:')} {f}")

    if not keep_memory and memory_exists:
        import shutil as _shutil
        _shutil.rmtree(str(MEMORY_DIR), ignore_errors=True)
        print(f"  {red('삭제:')} {MEMORY_DIR}")
    elif memory_exists:
        ok(f"메모리 보존: {MEMORY_DIR}")

    ok("초기화 완료. 마법사를 다시 시작합니다.\n")


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

    # Step 5: 실행 엔진
    exec_mode, preferred_engine = step_exec_engine(existing_cfg, preflight)

    # Step 6: Python 의존성
    step_python_deps(preflight.deps_missing)

    # 설정 저장
    binaries = {"claude": preflight.claude_path, "codex": preflight.codex_path}
    save_all(orgs, exec_mode, binaries, preferred_engine)

    # Step 7: 시뮬레이션 검증
    step_simulation()

    # 완료 화면
    print_final_summary(preflight, orgs, exec_mode, preferred_engine)


if __name__ == "__main__":
    main()
