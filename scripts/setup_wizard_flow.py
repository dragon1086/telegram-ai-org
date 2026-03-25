from __future__ import annotations

from pathlib import Path
from typing import Any

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

HINT_PROFILES: dict[str, dict[str, Any]] = {
    "1": {"label": "개발/코딩", "keys": ["coding"], "agents": ["executor", "architect", "debugger"]},
    "2": {"label": "분석/리서치", "keys": ["analysis"], "agents": ["analyst", "scientist"]},
    "3": {"label": "문서/마케팅", "keys": ["writing"], "agents": ["writer", "document-specialist"]},
    "4": {"label": "코드 리뷰/QA", "keys": ["review"], "agents": ["code-reviewer", "qa-tester", "verifier"]},
    "5": {"label": "전체", "keys": ["coding", "analysis", "writing", "review", "planning"], "agents": []},
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

PACKAGES = ["aiosqlite", "loguru", "python-telegram-bot", "openai", "pyyaml"]


def step_pm_bot(ctx, existing: dict[str, str]) -> tuple[str, str]:
    ctx.step_header(2, "PM 봇 설정")
    default_token = existing.get("PM_BOT_TOKEN", "")
    default_chat = existing.get("TELEGRAM_GROUP_CHAT_ID", "")

    while True:
        prompt = "PM 봇 텔레그램 토큰"
        if default_token:
            prompt += f" (현재: {ctx.mask_token(default_token)})"
        token = ctx.ask(prompt, default=default_token)
        if not token:
            ctx.warn("토큰을 입력해주세요.")
            continue

        print("  토큰 검증 중...", end="", flush=True)
        bot_info = ctx.validate_telegram_token(token)
        if bot_info:
            print()
            ctx.ok(f"PM 봇 연결 확인: @{bot_info.get('username', '?')} ({bot_info.get('first_name', '')})")
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
            ctx.ask_yes("  위 단계를 완료했나요? (나중에 해도 됩니다)", default=True)
            break
        print()
        ctx.warn("토큰 유효성 검증 실패. 오프라인이거나 잘못된 토큰입니다.")
        if ctx.ask_yes("그래도 계속하시겠어요?", default=False):
            break

    while True:
        chat_id = ctx.ask("텔레그램 그룹 채팅방 ID (예: -1001234567890)", default=default_chat)
        if chat_id.lstrip("-").isdigit():
            break
        ctx.warn("숫자만 입력하세요 (음수 가능).")

    return token, chat_id


def _ask_org_engine(ctx, prefix: str = "") -> str:
    print(f"\n  {prefix}{ctx.bold('실행 엔진 선택:')}")
    print(f"    {ctx.bold('1.')} claude-code  {ctx.dim('— 복잡한 작업, 고품질 [기본]')}")
    print(f"    {ctx.bold('2.')} codex        {ctx.dim('— 단순한 작업, 저렴')}")
    print(f"    {ctx.bold('3.')} auto         {ctx.dim('— LLM이 자동 결정')}")
    choice = ctx.ask(f"  {prefix}선택", default="1")
    return EXEC_ENGINE_MAP.get(choice, "claude-code")


def _ask_identity(ctx, org_id: str, prefix: str = "") -> dict[str, Any]:
    default = ctx.parse_setup_identity(org_id, "기본")
    default_text = f"{default.role}|{','.join(default.specialties)}|{default.direction}"
    raw = ctx.ask(
        f"{prefix}조직 정체성 (역할|전문분야1,전문분야2|방향성)",
        default=default_text,
    )
    parsed = ctx.parse_setup_identity(org_id, raw)
    return {
        "role": parsed.role,
        "specialties": list(parsed.specialties),
        "direction": parsed.direction,
    }


def step_org_structure(ctx, pm_token: str, pm_chat_id: str) -> list[dict]:
    ctx.step_header(3, "조직 구성 선택")
    print(
        f"""
  조직 구성 방식을 선택하세요:
    {ctx.bold('1.')} 단일 조직 (PM 1개 + 동적 에이전트팀)  {ctx.dim('← 기본, 권장')}
    {ctx.bold('2.')} 다중 조직 (여러 PM + 조직간 협업)
"""
    )
    choice = ctx.ask("선택", default="1")

    if choice != "2":
        org_name = ctx.ask("조직 ID", default="global")
        org_desc = ctx.ask("조직 설명", default="총괄 PM — 사용자 요청 조율 및 실행")
        identity = _ask_identity(ctx, org_name)
        org_engine = _ask_org_engine(ctx)
        return [{
            "org_id": org_name,
            "description": org_desc,
            "pm_token": pm_token,
            "group_chat_id": pm_chat_id,
            "engine": org_engine,
            "identity": identity,
        }]

    while True:
        try:
            count = int(ctx.ask("조직 수 (2~10)", default="2"))
            if 2 <= count <= 10:
                break
            ctx.warn("2~10 사이로 입력하세요.")
        except ValueError:
            ctx.warn("숫자를 입력하세요.")

    orgs: list[dict] = []
    for i in range(count):
        print(f"\n  {ctx.bold(f'── 조직 {i+1}/{count} ──')}")
        name = ctx.ask("  조직 ID (예: aiorg_engineering_bot)")
        desc = ctx.ask("  설명", default=f"{name} 팀")
        if i == 0 and pm_token:
            print(f"  {ctx.dim('첫 번째 조직에 방금 입력한 PM 봇을 사용합니다.')}")
            token = pm_token
            chat_id = pm_chat_id
        else:
            while True:
                token = ctx.ask("  PM 봇 토큰")
                if not token:
                    ctx.warn("토큰을 입력해주세요.")
                    continue
                print("  토큰 검증 중...", end="", flush=True)
                bot_info = ctx.validate_telegram_token(token)
                if bot_info:
                    print()
                    ctx.ok(f"@{bot_info.get('username','?')} 연결 확인")
                    break
                print()
                if ctx.ask_yes("검증 실패. 그래도 계속?", default=False):
                    break
            while True:
                chat_id = ctx.ask("  그룹 채팅방 ID")
                if chat_id.lstrip("-").isdigit():
                    break
                ctx.warn("숫자만 입력하세요.")

        identity = _ask_identity(ctx, name, prefix="  ")
        org_engine = _ask_org_engine(ctx, prefix="  ")
        orgs.append({
            "org_id": name,
            "description": desc,
            "pm_token": token,
            "group_chat_id": chat_id,
            "engine": org_engine,
            "identity": identity,
        })
        ctx.ok(f"{name} 조직 추가됨 (engine: {EXEC_ENGINE_LABEL.get(org_engine, org_engine)})")

    return orgs


def _auto_start_bots(ctx) -> None:
    import subprocess
    import time

    from core.orchestration_config import load_orchestration_config

    cfg = load_orchestration_config(ctx.PROJECT_ROOT / "organizations.yaml", ctx.PROJECT_ROOT / "orchestration.yaml", force_reload=True)
    started = 0
    for org in cfg.list_orgs():
        try:
            org_id = org.id
            token = org.token
            chat_id = str(org.chat_id or "")
            if not token or not chat_id:
                ctx.warn(f"  {org_id}: 토큰/chat_id 없음 — 건너뜀")
                continue
            r = subprocess.run(
                [ctx.sys.executable, "scripts/bot_manager.py", "start", token, org_id, chat_id],
                capture_output=True, text=True, cwd=str(ctx.PROJECT_ROOT),
            )
            if "시작됨" in r.stdout or r.returncode == 0:
                ctx.ok(f"  {org_id} 시작됨")
                started += 1
            else:
                ctx.warn(f"  {org_id} 기동 실패: {r.stderr[:60]}")
            time.sleep(2)
        except Exception as e:
            ctx.warn(f"  {org_id}: {e}")
    if started:
        ctx.ok(f"총 {started}개 봇 자동 기동 완료")


def step_agent_hints(ctx) -> None:
    ctx.step_header(4, "에이전트 힌트 설정 (agent_hints.yaml)")
    print(
        f"""
  어떤 작업 유형을 주로 다루나요? {ctx.dim('(복수 선택 가능)')}
    {ctx.bold('1.')} 개발/코딩        {ctx.dim('(executor, architect, debugger)')}
    {ctx.bold('2.')} 분석/리서치       {ctx.dim('(analyst, scientist)')}
    {ctx.bold('3.')} 문서/마케팅       {ctx.dim('(writer, document-specialist)')}
    {ctx.bold('4.')} 코드 리뷰/QA     {ctx.dim('(code-reviewer, qa-tester)')}
    {ctx.bold('5.')} 전체 {ctx.dim('(모두 포함)')}
"""
    )
    raw = ctx.ask("선택 (예: 1,2,3)", default="5")
    choices = [c.strip() for c in raw.replace(" ", "").split(",")]

    if "5" in choices or not choices:
        ctx.AGENT_HINTS_FILE.write_text(FULL_HINTS_YAML, encoding="utf-8")
        ctx.ok("agent_hints.yaml 생성 (전체 프로파일)")
        return

    selected_keys: list[str] = []
    labels: list[str] = []
    for choice in choices:
        profile = HINT_PROFILES.get(choice)
        if profile:
            selected_keys.extend(profile["keys"])
            labels.append(profile["label"])

    seen: set[str] = set()
    unique_keys = [key for key in selected_keys if not (key in seen or seen.add(key))]
    sections = "\n".join(SECTION_MAP[key] for key in unique_keys if key in SECTION_MAP)
    content = SUBSET_HINTS_YAML_TPL.format(profiles=", ".join(labels), sections=sections)
    ctx.AGENT_HINTS_FILE.write_text(content, encoding="utf-8")
    ctx.ok(f"agent_hints.yaml 생성 ({', '.join(labels)})")


def step_agency_agents(ctx) -> None:
    ctx.step_header("4b", "agency-agents 커뮤니티 에이전트 설치")
    agents_dir = Path.home() / ".claude" / "agents"
    existing = len(list(agents_dir.glob("*.md"))) if agents_dir.exists() else 0

    print(
        f"""
  {ctx.bold('agency-agents')} — 커뮤니티가 만든 전문 에이전트 컬렉션
  {ctx.dim('https://github.com/msitarzewski/agency-agents')}

  포함 항목:
    • engineering  — Frontend, Backend, AI Engineer, DevOps, Security...
    • marketing    — Social Media, Content, Brand, SEO...
    • design       — UI/UX, Brand Guardian, Visual Storyteller...
    • testing      — QA, Performance, Accessibility...
    • product      — Product Manager, Roadmap, Growth...
    • + 총 130개+ 전문 에이전트

  현재 {ctx.bold(str(existing))}개 에이전트 설치됨
"""
    )

    choice = ctx.ask("agency-agents 설치할까요?", default="y").strip().lower()
    if choice not in ("y", "yes", ""):
        ctx.info("건너뜀 — 나중에 수동으로 설치 가능:")
        print(f"  {ctx.dim('git clone https://github.com/msitarzewski/agency-agents /tmp/agency-agents')}")
        print("  " + ctx.dim(r'find /tmp/agency-agents -name "*.md" ! -path "*/examples/*" -exec cp {} ~/.claude/agents/ \;'))
        return

    import shutil
    import subprocess as _sp
    import tempfile

    tmp = Path(tempfile.mkdtemp()) / "agency-agents"
    ctx.info("다운로드 중...")
    result = _sp.run(["git", "clone", "--depth=1", "https://github.com/msitarzewski/agency-agents", str(tmp)], capture_output=True, text=True)
    if result.returncode != 0:
        ctx.warn(f"다운로드 실패: {result.stderr[:100]}")
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
    ctx.ok(f"agency-agents {count}개 설치 완료 → 총 {total}개 에이전트")


def _update_agent_hints_engines(ctx, category_engines: dict[str, str]) -> None:
    if not ctx.AGENT_HINTS_FILE.exists():
        return
    try:
        lines = ctx.AGENT_HINTS_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
        current_section: str | None = None
        new_lines: list[str] = []
        for line in lines:
            match = ctx.re.match(r"^  (\w[\w-]*):\s*$", line)
            if match:
                current_section = match.group(1)
            if current_section in category_engines and line.strip().startswith("preferred_engine:"):
                indent = len(line) - len(line.lstrip())
                new_lines.append(" " * indent + f"preferred_engine: {category_engines[current_section]}\n")
                continue
            new_lines.append(line)
        ctx.AGENT_HINTS_FILE.write_text("".join(new_lines), encoding="utf-8")
        ctx.ok("agent_hints.yaml 엔진 설정 업데이트 완료")
    except Exception as e:
        ctx.warn(f"agent_hints.yaml 업데이트 실패: {e}")


def _show_engine_check(ctx) -> None:
    if not ctx.AGENT_HINTS_FILE.exists():
        return
    try:
        content = ctx.AGENT_HINTS_FILE.read_text(encoding="utf-8")
        current_section: str | None = None
        print(f"\n  {ctx.bold('카테고리별 엔진:')}")
        for line in content.splitlines():
            match = ctx.re.match(r"^  (\w[\w-]*):\s*$", line)
            if match:
                current_section = match.group(1)
            if current_section and line.strip().startswith("preferred_engine:"):
                eng = line.strip().split(":", 1)[1].strip()
                label = EXEC_ENGINE_LABEL.get(eng, eng)
                print(f"    • {current_section}: {label}")
    except Exception:
        pass


def step_exec_engine(ctx, existing_cfg: dict[str, str], preflight=None) -> tuple[str, str]:
    ctx.step_header(5, "실행 엔진 설정")

    both_detected = preflight is not None and preflight.claude_ok and preflight.codex_ok
    if both_detected:
        print(f"\n  {ctx.green('[OK]')} Claude Code ... {ctx.dim(preflight.claude_ver)}")
        print(f"  {ctx.green('[OK]')} Codex .......... {ctx.dim(preflight.codex_ver)}")
        print(f"\n  {ctx.bold('둘 다 감지됐습니다! 실행 엔진을 설정합니다.')}")

    current_engine = existing_cfg.get("PREFERRED_ENGINE", "claude-code")
    current_label = EXEC_ENGINE_LABEL.get(current_engine, current_engine)
    print(
        f"""
  기본 실행 엔진 선택: {ctx.dim(f'(현재: {current_label})')}
    {ctx.bold('1.')} Claude Code + omc /team  {ctx.dim('— 복잡한 태스크, 페르소나 21개, plan→exec→verify 파이프라인 [권장]')}
    {ctx.bold('2.')} Codex                    {ctx.dim('— 빠른 단순 태스크')}
    {ctx.bold('3.')} 자동 결정                {ctx.dim('— LLM이 태스크 복잡도에 따라 선택 (둘 다 사용)')}
"""
    )
    default_choice = {"claude-code": "1", "codex": "2", "auto": "3"}.get(current_engine, "1")
    choice = ctx.ask("선택", default=default_choice)
    engine = EXEC_ENGINE_MAP.get(choice, "claude-code")
    exec_mode = _ENGINE_TO_EXEC_MODE.get(engine, "auto")
    ctx.ok(f"기본 실행 엔진: {EXEC_ENGINE_LABEL[engine]}")

    if both_detected:
        print(f"\n  {ctx.bold('태스크 유형별 선호 엔진 설정')} {ctx.dim('(엔터=기본값, 1=Claude Code, 2=Codex, 3=자동)')}\n")
        category_engines: dict[str, str] = {}
        for cat_key, cat_label in _CATEGORY_LABELS.items():
            default = _CATEGORY_ENGINE_DEFAULTS[cat_key]
            raw = ctx.ask(f"  {cat_label} (1/2/3)", default=default)
            category_engines[cat_key] = EXEC_ENGINE_MAP.get(raw if raw in ("1", "2", "3") else default, "claude-code")
        _update_agent_hints_engines(ctx, category_engines)

    return exec_mode, engine


def step_python_deps(ctx, deps_missing: list[str]) -> None:
    ctx.step_header(6, "Python 의존성 설치")
    print(
        f"""
  Python 의존성 설치:
    - 프로젝트 venv 생성: {ctx.VENV_DIR}
    - 설치할 패키지: {' '.join(PACKAGES)}
"""
    )
    if not ctx.ask_yes("지금 설치하시겠어요?"):
        ctx.info("건너뜀 — 나중에 수동 설치: pip install " + " ".join(PACKAGES))
        return

    if not (ctx.VENV_DIR / "bin" / "python").exists():
        print("  venv 생성 중...", end="", flush=True)
        rc, out = ctx.run_cmd([ctx.sys.executable, "-m", "venv", str(ctx.VENV_DIR)], capture=True)
        if rc != 0:
            print()
            ctx.warn(f"venv 생성 실패: {out}")
            return
        print(f" {ctx.green('완료')}")
    else:
        ctx.info(f"기존 venv 사용: {ctx.VENV_DIR}")

    pip = str(ctx.VENV_DIR / "bin" / "pip")
    print("  패키지 설치 중...", end="", flush=True)
    rc, out = ctx.run_cmd([pip, "install", "--upgrade"] + PACKAGES, capture=True)
    if rc == 0:
        print(f" {ctx.green('완료')}")
        ctx.ok("모든 의존성 설치 완료")
    else:
        print()
        ctx.warn(f"일부 패키지 설치 실패:\n{out[-500:]}")


def step_simulation(ctx) -> None:
    ctx.step_header(7, "시뮬레이션 검증")
    print(
        f"""
  설정이 완료되었습니다.
  {ctx.dim('시뮬레이션: DynamicTeamBuilder dry-run으로 팀 구성 결과를 확인합니다.')}
"""
    )
    if not ctx.ask_yes("시뮬레이션으로 검증하시겠어요?"):
        ctx.info("건너뜀")
        return

    sim_script = ctx.PROJECT_ROOT / "simulation_mode.py"
    if not sim_script.exists():
        ctx.warn(f"simulation_mode.py 미존재: {sim_script}")
        return

    python_bin = str(ctx.VENV_DIR / "bin" / "python") if (ctx.VENV_DIR / "bin" / "python").exists() else ctx.sys.executable
    test_task = "프리즘 인사이트 주간 보고서 작성해줘"
    print(f"\n  태스크: {ctx.cyan(repr(test_task))}")
    print("  팀 구성 중...\n")

    rc, out = ctx.run_cmd([python_bin, str(sim_script), "--task", test_task, "--dry-run"], capture=True)
    if out:
        for line in out.splitlines()[:30]:
            print(f"  {ctx.dim(line)}")

    if rc == 0:
        ctx.ok("시뮬레이션 성공 — DynamicTeamBuilder 정상 작동")
    else:
        ctx.warn("시뮬레이션에서 오류 발생 (설정 자체는 저장됨)")
