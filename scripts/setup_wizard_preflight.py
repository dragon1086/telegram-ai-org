from __future__ import annotations

import json
from pathlib import Path


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


def _pf_line(ctx, label: str, status: bool | None, detail: str, warn_not_fail: bool = True, optional: bool = False) -> None:
    label_padded = label.ljust(36, ".")
    if status is True:
        tag = ctx.green("[OK]  ")
    elif status is False:
        tag = (ctx.yellow("[WARN]") if warn_not_fail else ctx.red("[FAIL]"))
    else:
        tag = ctx.yellow("[WARN]") if not optional else ctx.dim("[--]  ")
    print(f"  {tag} {label_padded} {ctx.dim(detail)}")


def run_preflight(ctx, verbose: bool = True) -> PreflightResult:
    r = PreflightResult()

    if verbose:
        print(f"\n{ctx.bold('🔍 환경 점검 중...')}\n")

    v = ctx.sys.version_info
    r.python_ver = f"Python {v.major}.{v.minor}.{v.micro}"
    r.python_ok = (v.major, v.minor) >= (3, 11)
    if verbose:
        _pf_line(ctx, "Python 3.11+", r.python_ok, r.python_ver, warn_not_fail=False)
    if not r.python_ok:
        r.issues.append("python")

    r.claude_path = ctx.shutil.which("claude") or ""
    if r.claude_path:
        rc, out = ctx.run_cmd(["claude", "--version"])
        r.claude_ver = out.splitlines()[0] if out else "버전 미확인"
        r.claude_ok = rc == 0
    if verbose:
        if r.claude_ok:
            _pf_line(ctx, "Claude Code", True, f"{r.claude_path} {r.claude_ver}")
        else:
            _pf_line(ctx, "Claude Code", False, "미감지", warn_not_fail=False)
    if not r.claude_ok:
        r.issues.append("claude")

    r.codex_path = ctx.shutil.which("codex") or ""
    if r.codex_path:
        rc, out = ctx.run_cmd(["codex", "--version"])
        r.codex_ver = out.splitlines()[0] if out else "버전 미확인"
        r.codex_ok = rc == 0
    if verbose:
        if r.codex_ok:
            _pf_line(ctx, "Codex", True, f"{r.codex_path} {r.codex_ver}", optional=True)
        else:
            _pf_line(ctx, "Codex", None, "미감지 (선택사항)", optional=True)

    omc_glob = str(Path.home() / ".claude/plugins/cache/omc/oh-my-claudecode/*/bridge/mcp-server.cjs")
    omc_files = ctx._glob.glob(omc_glob)
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
            _pf_line(ctx, "oh-my-claudecode (omc)", True, f"v{r.omc_ver} 설치됨")
        else:
            _pf_line(ctx, "oh-my-claudecode (omc)", False, "미감지")
    if not r.omc_ok:
        r.issues.append("omc")

    team_glob = str(Path.home() / ".claude/plugins/cache/omc/oh-my-claudecode/*/bridge/team-mcp.cjs")
    team_files = ctx._glob.glob(team_glob)
    r.team_mcp_ok = len(team_files) > 0
    if verbose:
        _pf_line(ctx, "omc team MCP 서버", r.team_mcp_ok, "Connected" if r.team_mcp_ok else "미감지")
    if not r.team_mcp_ok:
        r.issues.append("team_mcp")

    if ctx.CLAUDE_SETTINGS.exists():
        try:
            settings = json.loads(ctx.CLAUDE_SETTINGS.read_text())
            env = settings.get("env", {})
            val = env.get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS", "")
            r.agent_teams_ok = str(val).lower() in ("1", "true", "yes")
        except Exception:
            pass
    if verbose:
        _pf_line(
            ctx,
            "Agent Teams 활성화",
            r.agent_teams_ok,
            "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1" if r.agent_teams_ok else "비활성화",
        )
    if not r.agent_teams_ok:
        r.issues.append("agent_teams")

    agent_files = list(ctx.CLAUDE_AGENTS_DIR.glob("*.md")) if ctx.CLAUDE_AGENTS_DIR.exists() else []
    r.agent_count = len(agent_files)
    r.agent_names = [f.stem for f in agent_files[:5]]
    if r.agent_count > 5:
        r.agent_names.append(f"... +{r.agent_count - 5}개")
    agents_ok = r.agent_count > 0
    if verbose:
        names_str = ", ".join(r.agent_names) if r.agent_names else ""
        _pf_line(ctx, "에이전트 페르소나", agents_ok, f"{r.agent_count}개 ({names_str})" if agents_ok else "미감지")
    if not agents_ok:
        r.issues.append("agents")

    r.config_ok = ctx.CONFIG_FILE.exists()
    if verbose:
        _pf_line(ctx, "~/.ai-org/config.yaml", r.config_ok if r.config_ok else None, "존재" if r.config_ok else "미존재 → 이 마법사에서 생성")

    existing = ctx.load_existing_config()
    r.pm_token_ok = bool(existing.get("PM_BOT_TOKEN") or ctx.os.environ.get("PM_BOT_TOKEN"))
    if verbose:
        _pf_line(ctx, "PM 봇 토큰", r.pm_token_ok if r.pm_token_ok else None, "설정됨" if r.pm_token_ok else "미설정")

    r.worker_token_ok = ctx.WORKERS_FILE.exists() or ctx.ORGANIZATIONS_FILE.exists()
    if verbose:
        _pf_line(ctx, "조직/워커 설정", r.worker_token_ok if r.worker_token_ok else None, "설정됨" if r.worker_token_ok else "미설정")

    required = ["aiosqlite", "loguru", "telegram", "openai", "yaml"]
    import_map = {"telegram": "telegram", "yaml": "yaml", "openai": "openai", "aiosqlite": "aiosqlite", "loguru": "loguru"}
    for pkg in required:
        try:
            __import__(import_map.get(pkg, pkg))
        except ImportError:
            r.deps_missing.append(pkg)
    r.deps_ok = len(r.deps_missing) == 0
    if verbose:
        if r.deps_ok:
            _pf_line(ctx, "Python 의존성", True, "requirements.txt 설치됨")
        else:
            _pf_line(ctx, "Python 의존성", None, f"미설치: {', '.join(r.deps_missing)}")
    if not r.deps_ok:
        r.issues.append("deps")

    return r


def _enable_agent_teams(ctx) -> None:
    try:
        if ctx.CLAUDE_SETTINGS.exists():
            settings = json.loads(ctx.CLAUDE_SETTINGS.read_text())
        else:
            settings = {}
        if "env" not in settings:
            settings["env"] = {}
        settings["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] = "1"
        ctx.CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        ctx.CLAUDE_SETTINGS.write_text(json.dumps(settings, indent=2, ensure_ascii=False))
        ctx.ok("Agent Teams 활성화 완료 (Claude Code 재시작 필요)")
    except Exception as e:
        ctx.warn(f"settings.json 수정 실패: {e}")


def step_install_tools(ctx, r: PreflightResult) -> None:
    actionable = [i for i in r.issues if i in ("claude", "omc", "agent_teams", "deps")]
    if not actionable:
        return

    ctx.step_header(1, "필수 도구 설치 안내")

    if "claude" in r.issues:
        print(f"\n  {ctx.bold('Claude Code')} 미설치:")
        print(f"    {ctx.cyan('npm install -g @anthropic-ai/claude-code')}")
        _ = ctx.ask_yes("  Claude Code 설치 후 계속하시겠어요?")

    if "omc" in r.issues:
        print(f"\n  {ctx.bold('oh-my-claudecode')} 미설치:")
        print(f"    {ctx.cyan('claude /plugin install oh-my-claudecode')}")
        _ = ctx.ask_yes("  omc 설치 후 계속하시겠어요?")

    if "agent_teams" in r.issues:
        print(f"\n  {ctx.bold('Agent Teams')} 비활성화됨.")
        if ctx.ask_yes("  자동으로 ~/.claude/settings.json에 활성화할까요?"):
            _enable_agent_teams(ctx)

    if "deps" in r.issues:
        print(f"\n  {ctx.bold('Python 의존성')} 미설치: {', '.join(r.deps_missing)}")
        print("  (Step 6에서 자동 설치 안내 예정)")

