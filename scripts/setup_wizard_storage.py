from __future__ import annotations


def save_all(ctx, orgs: list[dict], exec_mode: str, binaries: dict, preferred_engine: str = "claude-code") -> None:
    ctx.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    ctx.ensure_orchestration_config(ctx.PROJECT_ROOT)

    first_org = orgs[0] if orgs else {}
    if first_org:
        ctx.upsert_runtime_env_var(ctx.PROJECT_ROOT, "PM_BOT_TOKEN", first_org.get("pm_token", ""))
        ctx.upsert_runtime_env_var(ctx.PROJECT_ROOT, "TELEGRAM_GROUP_CHAT_ID", str(first_org.get("group_chat_id", "")))
    ctx.upsert_runtime_env_var(ctx.PROJECT_ROOT, "DEFAULT_EXECUTION_MODE", exec_mode)
    ctx.upsert_runtime_env_var(ctx.PROJECT_ROOT, "PREFERRED_ENGINE", preferred_engine)
    if binaries.get("claude"):
        ctx.upsert_runtime_env_var(ctx.PROJECT_ROOT, "CLAUDE_CLI_PATH", binaries["claude"])
    if binaries.get("codex"):
        ctx.upsert_runtime_env_var(ctx.PROJECT_ROOT, "CODEX_CLI_PATH", binaries["codex"])
    ctx.upsert_runtime_env_var(ctx.PROJECT_ROOT, "CONTEXT_DB_PATH", "~/.ai-org/context.db")

    for i, org in enumerate(orgs):
        org_id = org["org_id"]
        env_name = "PM_BOT_TOKEN" if i == 0 else f"BOT_TOKEN_{org_id.upper()}"
        chat_key = "TELEGRAM_GROUP_CHAT_ID" if i == 0 else f"{org_id.upper()}_GROUP_CHAT_ID"
        ctx.upsert_runtime_env_var(ctx.PROJECT_ROOT, env_name, org["pm_token"])
        ctx.upsert_runtime_env_var(ctx.PROJECT_ROOT, chat_key, str(org["group_chat_id"]))
        identity = org["identity"]
        ctx.upsert_org_in_canonical_config(
            ctx.PROJECT_ROOT,
            username=org_id,
            token_env=env_name,
            chat_id=int(str(org["group_chat_id"])),
            engine=org.get("engine", "claude-code"),
            identity=ctx.parse_setup_identity(
                org_id,
                "|".join(
                    [
                        identity.get("role", ""),
                        ",".join(identity.get("specialties", [])),
                        identity.get("direction", ""),
                    ]
                ),
            ),
        )

    ctx.refresh_legacy_bot_configs(ctx.PROJECT_ROOT)
    ctx.refresh_pm_identity_files(ctx.PROJECT_ROOT)
    ctx.ok(f"설정 저장: {ctx.CONFIG_FILE}")
    ctx.ok(f"조직 설정 저장: {ctx.ORGANIZATIONS_FILE}")
    ctx.ok(f"오케스트레이션 설정 저장: {ctx.PROJECT_ROOT / 'orchestration.yaml'}")


def print_final_summary(ctx, r, orgs: list[dict], exec_mode: str, preferred_engine: str = "claude-code") -> None:
    ctx.banner("✅ telegram-ai-org 설정 완료!")

    print(f"  {ctx.bold('환경:')}")
    if r.claude_ok:
        print(f"    • Claude Code: {r.claude_path} {r.claude_ver}")
    if r.omc_ok:
        team_str = "team MCP ✓" if r.team_mcp_ok else "team MCP ✗"
        teams_str = "Agent Teams ✓" if r.agent_teams_ok else "Agent Teams ✗"
        print(f"    • omc: v{r.omc_ver} ({team_str}, {teams_str})")
    if r.agent_count > 0:
        print(f"    • 에이전트: {r.agent_count}개 페르소나 로드됨")
    print(f"    • 실행 모드: {ctx.EXEC_MODE_LABEL.get(exec_mode, exec_mode)}")
    print(f"    • 기본 엔진: {ctx.EXEC_ENGINE_LABEL.get(preferred_engine, preferred_engine)}")

    print(f"\n  {ctx.bold('조직:')}")
    for org in orgs:
        print(f"    • {ctx.bold(org['org_id'])} — {org['description']}")

    print(f"\n  {ctx.bold('저장된 파일:')}")
    print(f"    • {ctx.CONFIG_FILE}")
    print(f"    • {ctx.ORGANIZATIONS_FILE}")
    print(f"    • {ctx.PROJECT_ROOT / 'orchestration.yaml'}")
    print(f"    • {ctx.AGENT_HINTS_FILE}")

    print(f"\n  {ctx.bold('시작:')}")
    print(f"    {ctx.cyan('cd ~/telegram-ai-org')}")
    if (ctx.VENV_DIR / "bin" / "activate").exists():
        print(f"    {ctx.cyan('source .venv/bin/activate')}")
    print(f"    {ctx.cyan('bash scripts/start_all.sh')}")
    print()


def reset_config(ctx, keep_memory: bool | None = None) -> None:
    files = [ctx.CONFIG_FILE, ctx.ORGANIZATIONS_FILE, ctx.PROJECT_ROOT / "orchestration.yaml", ctx.AGENT_HINTS_FILE, ctx.WORKERS_FILE]

    print(f"\n{ctx.bold(ctx.red('⚠️  기존 설정을 초기화합니다.'))}")
    print("삭제될 항목:")
    for path in files:
        if path.exists():
            print(f"  • {path}")

    if not ctx.ask_yes("정말 초기화하시겠어요?", default=False):
        print("취소됨.")
        ctx.sys.exit(0)

    memory_exists = ctx.MEMORY_DIR.exists() and any(ctx.MEMORY_DIR.iterdir()) if ctx.MEMORY_DIR.exists() else False
    if keep_memory is None and memory_exists:
        keep_memory = ctx.ask_yes("메모리는 보존하시겠습니까?", default=True)

    for path in files:
        if path.exists():
            path.unlink()
            print(f"  {ctx.red('삭제:')} {path}")

    if not keep_memory and memory_exists:
        ctx.shutil.rmtree(str(ctx.MEMORY_DIR), ignore_errors=True)
        print(f"  {ctx.red('삭제:')} {ctx.MEMORY_DIR}")
    elif memory_exists:
        ctx.ok(f"메모리 보존: {ctx.MEMORY_DIR}")

    ctx.ok("초기화 완료. 마법사를 다시 시작합니다.\n")
