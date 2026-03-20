"""
Architecture diagrams for telegram-ai-org system.
Generates two PNG files:
  docs/arch-pipeline.png  - Message flow pipeline (programming/infra layer)
  docs/arch-llm.png       - LLM layer (agents / teams / phases)
"""

import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.font_manager import FontProperties

# ---------------------------------------------------------------------------
# Font setup
# ---------------------------------------------------------------------------
FONT_PATH = "/System/Library/Fonts/Supplemental/AppleGothic.ttf"
if os.path.exists(FONT_PATH):
    from matplotlib.font_manager import fontManager
    fontManager.addfont(FONT_PATH)
    FONT_FAMILY = "AppleGothic"
else:
    FONT_FAMILY = "DejaVu Sans"

def fp(size=10, bold=False):
    return FontProperties(family=FONT_FAMILY, size=size,
                          weight="bold" if bold else "normal")

# ---------------------------------------------------------------------------
# Color palette
# ---------------------------------------------------------------------------
BG        = "#1e1e2e"
SURFACE   = "#2a2a3e"
BORDER    = "#45475a"

C_ENTRY   = "#89b4fa"   # blue   – entry / telegram
C_ROUTE   = "#cba6f7"   # mauve  – routing
C_ORCH    = "#f38ba8"   # red    – orchestrator
C_SESSION = "#a6e3a1"   # green  – session / execution
C_STATE   = "#f9e2af"   # yellow – state / config
C_BOT     = "#89dceb"   # sky    – bots
C_ARROW   = "#cdd6f4"   # lavender – arrow / label

C_LLM_CLASS  = "#f38ba8"
C_LLM_TEAM   = "#cba6f7"
C_LLM_PHASE  = "#89b4fa"
C_LLM_AGENT  = "#a6e3a1"
C_LLM_MCP    = "#f9e2af"
C_LLM_PROMPT = "#89dceb"

# ---------------------------------------------------------------------------
# Helper drawing utilities
# ---------------------------------------------------------------------------

def bg_rect(ax, xy, w, h, color, alpha=0.18, lw=1.5, zorder=2):
    """Filled rectangle with colored border."""
    x, y = xy
    rect = FancyBboxPatch((x, y), w, h,
                          boxstyle="round,pad=0.02",
                          linewidth=lw,
                          edgecolor=color,
                          facecolor=color,
                          alpha=alpha,
                          zorder=zorder)
    ax.add_patch(rect)
    return rect


def box(ax, xy, w, h, color, label, sublabel=None,
        fontsize=9, bold=True, zorder=3):
    """Solid colored box with label."""
    x, y = xy
    rect = FancyBboxPatch((x, y), w, h,
                          boxstyle="round,pad=0.03",
                          linewidth=1.8,
                          edgecolor=color,
                          facecolor=SURFACE,
                          zorder=zorder)
    ax.add_patch(rect)
    ty = y + h / 2
    if sublabel:
        ty = y + h * 0.65
    ax.text(x + w / 2, ty, label,
            ha="center", va="center",
            color=color, fontproperties=fp(fontsize, bold),
            zorder=zorder + 1)
    if sublabel:
        ax.text(x + w / 2, y + h * 0.28, sublabel,
                ha="center", va="center",
                color=color, alpha=0.75,
                fontproperties=fp(fontsize - 1.5),
                zorder=zorder + 1)


def arrow(ax, x0, y0, x1, y1, color=C_ARROW, label=None,
          lw=1.5, zorder=4, style="->"):
    ax.annotate("",
                xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(arrowstyle=style,
                                color=color,
                                lw=lw,
                                connectionstyle="arc3,rad=0.0"),
                zorder=zorder)
    if label:
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        ax.text(mx + 0.05, my, label,
                ha="left", va="center",
                color=color, fontproperties=fp(7.5),
                zorder=zorder + 1)


def section_label(ax, x, y, text, color):
    ax.text(x, y, text,
            ha="left", va="center",
            color=color, fontproperties=fp(8, bold=True),
            alpha=0.7)


# ===========================================================================
# DIAGRAM 1 – Message Flow Pipeline
# ===========================================================================

def draw_pipeline():
    fig, ax = plt.subplots(figsize=(20, 14))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 20)
    ax.set_ylim(0, 14)
    ax.axis("off")

    # Title
    ax.text(10, 13.4, "telegram-ai-org  |  메시지 플로우 파이프라인",
            ha="center", va="center",
            color=C_ARROW, fontproperties=fp(16, bold=True))
    ax.text(10, 13.0, "Programming / Infrastructure Layer",
            ha="center", va="center",
            color=C_ARROW, fontproperties=fp(10), alpha=0.6)

    # ------------------------------------------------------------------
    # ROW 0 – Bots (left panel)
    # ------------------------------------------------------------------
    bg_rect(ax, (0.3, 7.0), 3.2, 5.5, C_BOT, alpha=0.08)
    section_label(ax, 0.5, 12.2, "부서 봇 (Bots)", C_BOT)

    bots = [
        ("PM Bot", "aiorg_pm_bot"),
        ("Research", "aiorg_research_bot"),
        ("Engineering", "aiorg_engineering_bot"),
        ("Product", "aiorg_product_bot"),
        ("Design", "aiorg_design_bot"),
        ("Growth", "aiorg_growth_bot"),
        ("Ops", "aiorg_ops_bot"),
    ]
    bot_colors = [C_ORCH, C_ENTRY, C_SESSION, C_ROUTE, C_LLM_AGENT, C_LLM_MCP, C_STATE]
    for i, ((name, yid), col) in enumerate(zip(bots, bot_colors)):
        bx = 0.45
        by = 11.5 - i * 0.75
        box(ax, (bx, by), 2.9, 0.58, col, name, yid, fontsize=8)

    # ------------------------------------------------------------------
    # ROW 1 – Entry
    # ------------------------------------------------------------------
    bg_rect(ax, (4.2, 11.2), 4.2, 1.4, C_ENTRY, alpha=0.10)
    section_label(ax, 4.4, 12.4, "Entry", C_ENTRY)
    box(ax, (4.4, 11.35), 1.7, 0.9, C_ENTRY, "main.py", "polling start")
    box(ax, (6.3, 11.35), 1.8, 0.9, C_ENTRY, "TelegramRelay",
        "python-telegram-bot")

    # arrow bots → entry
    arrow(ax, 3.35, 11.5, 4.4, 11.8, C_BOT, "token / updates")

    # arrow entry internal
    arrow(ax, 6.1, 11.8, 6.3, 11.8, C_ENTRY)

    # ------------------------------------------------------------------
    # ROW 2 – Routing
    # ------------------------------------------------------------------
    bg_rect(ax, (4.2, 9.2), 8.5, 1.6, C_ROUTE, alpha=0.10)
    section_label(ax, 4.4, 10.6, "Routing  (core/telegram_relay.py  →  on_message())", C_ROUTE)

    box(ax, (4.4, 9.35), 2.2, 0.9, C_ROUTE, "direct_reply", "즉시 응답")
    box(ax, (7.0, 9.35), 2.4, 0.9, C_ROUTE, "local_execution", "로컬 실행")
    box(ax, (9.8, 9.35), 2.5, 0.9, C_ROUTE, "delegate", "위임")

    # arrow entry → routing
    arrow(ax, 7.2, 11.35, 7.2, 10.8, C_ENTRY, "on_message()")

    # ------------------------------------------------------------------
    # ROW 3 – Orchestrator
    # ------------------------------------------------------------------
    bg_rect(ax, (4.2, 7.2), 8.5, 1.7, C_ORCH, alpha=0.10)
    section_label(ax, 4.4, 8.7, "Orchestrator  (core/pm_orchestrator.py)", C_ORCH)

    box(ax, (4.4, 7.35), 2.5, 0.9, C_ORCH, "plan_request()", "요청 분석")
    box(ax, (7.2, 7.35), 2.5, 0.9, C_ORCH, "RequestPlan", "플랜 생성")
    box(ax, (10.0, 7.35), 2.3, 0.9, C_ORCH, "dispatch()", "팀 배정")

    # routing → orchestrator (delegate lane)
    arrow(ax, 11.05, 9.35, 11.05, 8.25, C_ROUTE, "delegate")
    # routing → orchestrator (local lane)
    arrow(ax, 8.2, 9.35, 8.2, 8.25, C_ROUTE)

    # orchestrator internal
    arrow(ax, 6.9, 7.8, 7.2, 7.8, C_ORCH)
    arrow(ax, 9.7, 7.8, 10.0, 7.8, C_ORCH)

    # ------------------------------------------------------------------
    # ROW 4 – Session
    # ------------------------------------------------------------------
    bg_rect(ax, (4.2, 5.0), 8.5, 1.9, C_SESSION, alpha=0.10)
    section_label(ax, 4.4, 6.7, "Session  (core/session_manager.py)", C_SESSION)

    box(ax, (4.4, 5.15), 2.3, 0.9, C_SESSION, "tmux send-keys", "세션 관리")
    box(ax, (7.0, 5.15), 2.6, 0.9, C_SESSION, "Claude Code CLI", "에이전트 실행")
    box(ax, (9.9, 5.15), 2.4, 0.9, C_SESSION, "response capture", "결과 수집")

    # orchestrator → session
    arrow(ax, 8.2, 7.35, 8.2, 7.05, C_ORCH)

    # session internal
    arrow(ax, 6.7, 5.6, 7.0, 5.6, C_SESSION)
    arrow(ax, 9.6, 5.6, 9.9, 5.6, C_SESSION)

    # ------------------------------------------------------------------
    # ROW 5 – State & Config
    # ------------------------------------------------------------------
    bg_rect(ax, (4.2, 2.8), 8.5, 1.9, C_STATE, alpha=0.10)
    section_label(ax, 4.4, 4.5, "State & Config", C_STATE)

    box(ax, (4.4, 2.95), 3.0, 0.9, C_STATE,
        "state.json", ".ai-org/runs/run-<ts>/")
    box(ax, (7.7, 2.95), 2.5, 0.9, C_STATE,
        "orchestration.yaml", "phase/backend policies")
    box(ax, (10.5, 2.95), 1.9, 0.9, C_STATE,
        "bots/*.yaml", "org config")

    # session → state
    arrow(ax, 8.2, 5.15, 8.2, 4.7, C_SESSION, "write state")

    # state → session (read config)
    arrow(ax, 9.0, 4.7, 9.0, 5.15, C_STATE, "read config", style="<-")

    # ------------------------------------------------------------------
    # RIGHT PANEL – Config files detail
    # ------------------------------------------------------------------
    bg_rect(ax, (13.2, 2.8), 6.3, 9.2, C_STATE, alpha=0.06)
    section_label(ax, 13.4, 11.8, "orchestration.yaml  구조", C_STATE)

    cfg_items = [
        ("phase_policies",    "단계별 실행 정책"),
        ("backend_policies",  "LLM 백엔드 우선순위"),
        ("session_policies",  "tmux 세션 설정"),
        ("team_profiles",     "팀 프로파일 정의"),
    ]
    for i, (k, v) in enumerate(cfg_items):
        by = 10.9 - i * 1.1
        box(ax, (13.4, by), 5.8, 0.75, C_STATE, k, v, fontsize=8.5)

    section_label(ax, 13.4, 8.8, "bots/aiorg_*.yaml  구조", C_BOT)
    bot_fields = [
        ("org_id / token_env", "봇 식별자 & 토큰"),
        ("engine",             "LLM 엔진 지정"),
        ("team_config",        "팀 구성 설정"),
        ("personality",        "시스템 프롬프트"),
    ]
    for i, (k, v) in enumerate(bot_fields):
        by = 8.0 - i * 1.0
        box(ax, (13.4, by), 5.8, 0.75, C_BOT, k, v, fontsize=8.5)

    # arrows: bots → entry (config read)
    arrow(ax, 16.3, 2.95, 16.3, 2.0, C_STATE, style="->")

    # ------------------------------------------------------------------
    # Legend
    # ------------------------------------------------------------------
    legend_items = [
        (C_ENTRY,   "Entry / Telegram"),
        (C_ROUTE,   "Routing"),
        (C_ORCH,    "Orchestrator"),
        (C_SESSION, "Session / Exec"),
        (C_STATE,   "State / Config"),
        (C_BOT,     "Bot Configs"),
    ]
    for i, (col, label) in enumerate(legend_items):
        lx = 0.4 + i * 3.1
        rect = FancyBboxPatch((lx, 0.3), 0.35, 0.25,
                              boxstyle="round,pad=0.02",
                              facecolor=col, edgecolor=col,
                              alpha=0.85, zorder=5)
        ax.add_patch(rect)
        ax.text(lx + 0.45, 0.42, label,
                ha="left", va="center",
                color=col, fontproperties=fp(8))

    out = "/Users/rocky/telegram-ai-org/docs/arch-pipeline.png"
    fig.savefig(out, dpi=150, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close(fig)
    print(f"[OK] {out}")
    return out


# ===========================================================================
# DIAGRAM 2 – LLM Layer
# ===========================================================================

def draw_llm():
    fig, ax = plt.subplots(figsize=(20, 14))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.set_xlim(0, 20)
    ax.set_ylim(0, 14)
    ax.axis("off")

    # Title
    ax.text(10, 13.4, "telegram-ai-org  |  LLM 레이어",
            ha="center", va="center",
            color=C_ARROW, fontproperties=fp(16, bold=True))
    ax.text(10, 13.0, "Agents / Teams / Phases / Classification",
            ha="center", va="center",
            color=C_ARROW, fontproperties=fp(10), alpha=0.6)

    # ------------------------------------------------------------------
    # SECTION A – Classification LLM
    # ------------------------------------------------------------------
    bg_rect(ax, (0.3, 10.5), 8.0, 2.0, C_LLM_CLASS, alpha=0.10)
    section_label(ax, 0.5, 12.3, "Classification LLM  (Confidence Scoring + Fallback)", C_LLM_CLASS)

    classifiers = [
        ("Gemini", "1순위"),
        ("OpenAI", "2순위"),
        ("Anthropic", "3순위"),
        ("DeepSeek", "4순위 fallback"),
    ]
    for i, (name, pri) in enumerate(classifiers):
        cx = 0.5 + i * 1.95
        box(ax, (cx, 10.65), 1.75, 0.85, C_LLM_CLASS, name, pri, fontsize=8.5)

    # fallback arrows
    for i in range(3):
        ax.annotate("",
                    xy=(0.5 + (i+1) * 1.95, 11.07),
                    xytext=(0.5 + i * 1.95 + 1.75, 11.07),
                    arrowprops=dict(arrowstyle="->",
                                   color=C_LLM_CLASS,
                                   lw=1.2,
                                   connectionstyle="arc3,rad=0.0"),
                    zorder=5)

    # ------------------------------------------------------------------
    # SECTION B – System Prompt
    # ------------------------------------------------------------------
    bg_rect(ax, (8.8, 10.5), 10.9, 2.0, C_LLM_PROMPT, alpha=0.10)
    section_label(ax, 9.0, 12.3, "System Prompt 구성", C_LLM_PROMPT)

    prompts = [
        ("Bot YAML", "personality/\ninstruction"),
        ("~/.claude/agents/", "동적 로드\n에이전트 파일"),
        ("Agent Hints", "agent_hints.yaml\n역할 힌트"),
        ("CLAUDE.md", "프로젝트/글로벌\n지침"),
    ]
    for i, (title, sub) in enumerate(prompts):
        px = 9.0 + i * 2.65
        box(ax, (px, 10.65), 2.4, 0.85, C_LLM_PROMPT, title, sub, fontsize=8)

    # ------------------------------------------------------------------
    # SECTION C – Team Strategy
    # ------------------------------------------------------------------
    bg_rect(ax, (0.3, 7.8), 8.0, 2.3, C_LLM_TEAM, alpha=0.10)
    section_label(ax, 0.5, 9.9, "Team Strategy  (detect_strategy())", C_LLM_TEAM)

    strategies = [
        ("omc", "MCP 서버\n감지"),
        ("native", "EXPERIMENTAL\nAGENT_TEAMS"),
        ("solo", "단일 에이전트\n실행"),
    ]
    for i, (name, sub) in enumerate(strategies):
        sx = 0.5 + i * 2.55
        box(ax, (sx, 7.95), 2.3, 0.9, C_LLM_TEAM, name, sub, fontsize=8.5)

    # MCP detail
    box(ax, (0.5, 7.0), 2.3, 0.75, C_LLM_MCP, "AmpCaller", "amp MCP placeholder", fontsize=8)
    box(ax, (3.05, 7.0), 2.3, 0.75, C_LLM_MCP, "omc MCP", "서버 감지 / 연결", fontsize=8)

    arrow(ax, 1.65, 7.95, 1.65, 7.75, C_LLM_TEAM)
    arrow(ax, 4.2, 7.95, 4.2, 7.75, C_LLM_TEAM)

    # ------------------------------------------------------------------
    # SECTION D – Agent Catalog
    # ------------------------------------------------------------------
    bg_rect(ax, (8.8, 7.8), 10.9, 2.3, C_LLM_AGENT, alpha=0.10)
    section_label(ax, 9.0, 9.9, "Agent Catalog  (~/.claude/agents/ 동적 로드)", C_LLM_AGENT)

    agents = [
        "planner", "architect", "executor",
        "debugger", "analyst", "designer",
        "writer", "verifier",
    ]
    cols_a = 4
    for i, ag in enumerate(agents):
        row, col = divmod(i, cols_a)
        ax_ = 9.0 + col * 2.65
        ay_ = 9.3 - row * 0.85
        box(ax, (ax_, ay_), 2.4, 0.7, C_LLM_AGENT, ag, fontsize=8.5)

    # ------------------------------------------------------------------
    # SECTION E – Phase Pipeline
    # ------------------------------------------------------------------
    bg_rect(ax, (0.3, 4.8), 19.4, 2.6, C_LLM_PHASE, alpha=0.10)
    section_label(ax, 0.5, 7.2, "Phase Pipeline  (orchestration.yaml  →  phase_policies)", C_LLM_PHASE)

    phases = [
        ("intake",          "요청 수신\n& 검증"),
        ("planning",        "플랜 수립\nRequestPlan"),
        ("design",          "설계 결정\n아키텍처"),
        ("implementation",  "코드 실행\n에이전트"),
        ("verification",    "결과 검증\nverifier"),
        ("feedback",        "피드백\n& 학습"),
    ]
    pw = 19.4 / len(phases) - 0.15
    for i, (name, sub) in enumerate(phases):
        px = 0.45 + i * (pw + 0.15)
        box(ax, (px, 4.95), pw, 1.8, C_LLM_PHASE, name, sub, fontsize=9)
        if i < len(phases) - 1:
            arrow(ax, px + pw, 5.85, px + pw + 0.15, 5.85, C_LLM_PHASE)

    # ------------------------------------------------------------------
    # SECTION F – Bot Dept × Agent mapping
    # ------------------------------------------------------------------
    bg_rect(ax, (0.3, 1.5), 19.4, 3.0, C_BOT, alpha=0.07)
    section_label(ax, 0.5, 4.3, "부서 봇  ×  담당 에이전트  매핑", C_BOT)

    dept_map = [
        ("PM Bot",          C_ORCH,      "planner\norchestrator"),
        ("Research",        C_ENTRY,     "analyst\nresearcher"),
        ("Engineering",     C_SESSION,   "executor\ndebugger"),
        ("Product",         C_ROUTE,     "designer\nwriter"),
        ("Design",          C_LLM_AGENT, "designer\narchitect"),
        ("Growth",          C_LLM_MCP,   "analyst\nwriter"),
        ("Ops",             C_STATE,     "verifier\nexecutor"),
    ]
    dw = 19.4 / len(dept_map) - 0.12
    for i, (name, col, ags) in enumerate(dept_map):
        dx = 0.4 + i * (dw + 0.12)
        box(ax, (dx, 3.2), dw, 0.75, col, name, fontsize=8.5, bold=True)
        box(ax, (dx, 1.7), dw, 1.3, col, ags, fontsize=7.5, bold=False)
        arrow(ax, dx + dw/2, 3.2, dx + dw/2, 3.0, col)

    # ------------------------------------------------------------------
    # Cross-section arrows
    # ------------------------------------------------------------------
    # Classification → Team Strategy
    arrow(ax, 4.3, 10.5, 4.3, 10.1, C_LLM_CLASS, "라우팅 결정")
    # System Prompt → Agent Catalog
    arrow(ax, 14.3, 10.5, 14.3, 10.1, C_LLM_PROMPT, "프롬프트 주입")
    # Team Strategy → Phase Pipeline
    arrow(ax, 4.3, 7.8, 4.3, 7.4, C_LLM_TEAM, "실행 전략")
    # Agent Catalog → Phase Pipeline
    arrow(ax, 14.3, 7.8, 14.3, 7.4, C_LLM_AGENT, "에이전트 선택")
    # Phase Pipeline → Dept mapping
    arrow(ax, 10, 4.8, 10, 4.5, C_LLM_PHASE, "페이즈 실행")

    # ------------------------------------------------------------------
    # Legend
    # ------------------------------------------------------------------
    legend_items = [
        (C_LLM_CLASS,  "Classification"),
        (C_LLM_PROMPT, "System Prompt"),
        (C_LLM_TEAM,   "Team Strategy"),
        (C_LLM_AGENT,  "Agent Catalog"),
        (C_LLM_PHASE,  "Phase Pipeline"),
        (C_LLM_MCP,    "MCP"),
        (C_BOT,        "Bot / Dept"),
    ]
    for i, (col, label) in enumerate(legend_items):
        lx = 0.4 + i * 2.8
        rect = FancyBboxPatch((lx, 0.3), 0.35, 0.25,
                              boxstyle="round,pad=0.02",
                              facecolor=col, edgecolor=col,
                              alpha=0.85, zorder=5)
        ax.add_patch(rect)
        ax.text(lx + 0.45, 0.42, label,
                ha="left", va="center",
                color=col, fontproperties=fp(8))

    out = "/Users/rocky/telegram-ai-org/docs/arch-llm.png"
    fig.savefig(out, dpi=150, bbox_inches="tight",
                facecolor=BG, edgecolor="none")
    plt.close(fig)
    print(f"[OK] {out}")
    return out


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    p1 = draw_pipeline()
    p2 = draw_llm()
    print("\nGenerated:")
    print(f"  {p1}")
    print(f"  {p2}")
