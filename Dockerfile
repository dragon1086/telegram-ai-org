# =============================================================================
# telegram-ai-org Dockerfile — 멀티스테이지 빌드
#
# 사용법:
#   # 기본 빌드 (claude-code 엔진)
#   docker build -t telegram-ai-org .
#
#   # Gemini SDK 포함 빌드
#   docker build --build-arg ENGINE=gemini -t telegram-ai-org:gemini .
#
#   # 실행
#   docker run --env-file .env telegram-ai-org
# =============================================================================

# ─── Stage 1: Builder ────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# 빌드 도구 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# pip 업그레이드 + hatchling 설치
RUN pip install --upgrade pip hatchling

# 의존성 파일만 먼저 복사 (레이어 캐시 최적화)
COPY pyproject.toml .
COPY README.md .

# 엔진 선택 빌드 인수 (기본: 기본 의존성만, gemini 옵션 추가 가능)
ARG ENGINE=base
# 기본 의존성 설치 (wheel 디렉토리에 미리 빌드)
RUN pip wheel --no-cache-dir --wheel-dir /wheels \
    "python-telegram-bot>=20.0" \
    "pydantic>=2.0" \
    "aiosqlite>=0.19" \
    "httpx>=0.25" \
    "python-dotenv>=1.0" \
    "loguru>=0.7" \
    "typer>=0.9" \
    "openai>=1.0" \
    "anthropic>=0.20" \
    "PyYAML>=6.0" \
    "apscheduler>=3.10.0" \
    "rank-bm25>=0.2" \
    "mcp>=1.0" \
    "claude-agent-sdk>=0.1.50"

# Gemini 엔진 선택 시 추가 SDK 설치
RUN if [ "$ENGINE" = "gemini" ]; then \
        pip wheel --no-cache-dir --wheel-dir /wheels "google-genai>=1.0"; \
    fi

# ─── Stage 2: Node.js installer (Gemini CLI / Claude Code CLI) ───────────────
FROM node:20-slim AS node-installer

WORKDIR /npm-install

ARG ENGINE=base

# 엔진별 CLI 설치
# claude-code: @anthropic-ai/claude-code
# codex: @openai/codex
# gemini: @google/gemini-cli
RUN if [ "$ENGINE" = "claude" ]; then \
        npm install -g @anthropic-ai/claude-code --prefix /opt/cli; \
    elif [ "$ENGINE" = "codex" ]; then \
        npm install -g @openai/codex --prefix /opt/cli; \
    elif [ "$ENGINE" = "gemini" ]; then \
        npm install -g @google/gemini-cli --prefix /opt/cli; \
    fi

# ─── Stage 3: Runtime ────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="telegram-ai-org"
LABEL org.opencontainers.image.description="AI organization on Telegram — multi-agent PM bot system"
LABEL org.opencontainers.image.source="https://github.com/dragon1086/aimesh"
LABEL org.opencontainers.image.version="0.1.0"

# 런타임 시스템 의존성
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Node.js 런타임 (CLI 실행용)
    nodejs \
    # 기타 유틸
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 애플리케이션 디렉토리
WORKDIR /app

# Builder에서 빌드된 wheels 복사 후 설치
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links /wheels /wheels/*.whl \
    && rm -rf /wheels

# Node CLI 복사 (엔진별)
COPY --from=node-installer /opt/cli /opt/cli
ENV PATH="/opt/cli/bin:$PATH"

# 애플리케이션 소스 복사
COPY core/ ./core/
COPY tools/ ./tools/
COPY skills/ ./skills/
COPY bots/ ./bots/
COPY main.py cli.py orchestration.yaml workers.yaml ./

# 데이터 디렉토리 생성 및 권한 설정
RUN mkdir -p /app/logs /app/data /app/reports /app/tasks \
    && useradd -r -u 1001 -g root -s /sbin/nologin aiorg \
    && chown -R aiorg:root /app
USER aiorg

# ─── 환경변수 기본값 (플레이스홀더) ───────────────────────────────────────────
# 실제 값은 --env-file .env 또는 -e 플래그로 주입
ENV PM_BOT_TOKEN="" \
    TELEGRAM_GROUP_CHAT_ID="" \
    CLAUDE_CODE_OAUTH_TOKEN="" \
    CLAUDE_CLI_PATH="/opt/cli/bin/claude" \
    CODEX_CLI_PATH="/opt/cli/bin/codex" \
    GEMINI_CLI_PATH="/opt/cli/bin/gemini" \
    GEMINI_CLI_DEFAULT_TIMEOUT_SEC="1800" \
    CLAUDE_DEFAULT_TIMEOUT_SEC="14400" \
    CODEX_DEFAULT_TIMEOUT_SEC="1800" \
    ENABLE_PM_ORCHESTRATOR="1" \
    ENABLE_DISCUSSION_PROTOCOL="1" \
    ENABLE_AUTO_DISPATCH="1" \
    ENABLE_CROSS_VERIFICATION="1" \
    ENABLE_GOAL_TRACKER="1" \
    AUTONOMOUS_MODE="false" \
    CONTEXT_DB_PATH="/app/data/context.db" \
    SHARED_MEMORY_PATH="/app/data/shared_memory.json" \
    AIORG_REPORT_DIR="/app/reports" \
    DB_PATH="/app/data/context.db" \
    PM_HOURLY_CALL_LIMIT="40" \
    PYTHONUNBUFFERED="1" \
    PYTHONDONTWRITEBYTECODE="1"

# 헬스체크: PM 봇 PID 파일 존재 확인
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD test -f /tmp/telegram-ai-org-${PM_ORG_NAME:-global}.pid || exit 1

# 기본 진입점: PM 봇 실행
ENTRYPOINT ["python", "main.py"]
CMD []
