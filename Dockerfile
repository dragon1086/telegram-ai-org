# =============================================================================
# telegram-ai-org Dockerfile — 멀티스테이지 빌드
#
# 사용법:
#   # 기본 빌드 (BASE — 의존성만, 엔진 CLI 없음)
#   docker build -t telegram-ai-org .
#
#   # Claude Code 엔진 포함 빌드
#   docker build --build-arg ENGINE=claude -t telegram-ai-org:claude .
#
#   # Codex 엔진 포함 빌드
#   docker build --build-arg ENGINE=codex -t telegram-ai-org:codex .
#
#   # Gemini CLI 엔진 + SDK 포함 빌드
#   docker build --build-arg ENGINE=gemini -t telegram-ai-org:gemini .
#
#   # 실행
#   docker run --env-file .env telegram-ai-org
# =============================================================================

# ─── Stage 1: Builder — wheel 빌드 ───────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# 빌드 도구 설치
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# pip 업그레이드 + PEP 517 빌드 도구 설치
RUN pip install --upgrade pip build

# 패키지 메타데이터 먼저 복사 (레이어 캐시 최적화)
COPY pyproject.toml README.md ./

# 전체 소스 복사
COPY core/ ./core/
COPY tools/ ./tools/
COPY skills/ ./skills/
COPY bots/ ./bots/
COPY telegram_ai_org/ ./telegram_ai_org/
COPY cli.py main.py orchestration.yaml organizations.yaml workers.yaml \
     agent_hints.yaml improvement_thresholds.yaml ./

# PEP 517 빌드 — dist/*.whl 생성
RUN python -m build --wheel --outdir dist/


# ─── Stage 2: Node.js CLI installer (엔진별 선택 설치) ───────────────────────
FROM node:20-slim AS node-installer

WORKDIR /npm-install

# 엔진별 CLI 설치 (해당 엔진만 선택)
ARG ENGINE=base
RUN if [ "$ENGINE" = "claude" ]; then \
        npm install -g @anthropic-ai/claude-code --prefix /opt/cli; \
    elif [ "$ENGINE" = "codex" ]; then \
        npm install -g @openai/codex --prefix /opt/cli; \
    elif [ "$ENGINE" = "gemini" ]; then \
        npm install -g @google/gemini-cli --prefix /opt/cli; \
    else \
        mkdir -p /opt/cli/bin; \
    fi


# ─── Stage 3: Runtime — 경량 실행 이미지 ─────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL org.opencontainers.image.title="telegram-ai-org"
LABEL org.opencontainers.image.description="AI organization on Telegram — multi-agent PM bot system"
LABEL org.opencontainers.image.source="https://github.com/dragon1086/aimesh"
LABEL org.opencontainers.image.version="0.1.0"

# 런타임 시스템 패키지 (Node.js 런타임 — CLI 실행용)
RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ① 런타임 의존성 사전 설치 (빌드 캐시 최대화)
#    pyproject.toml dependencies 목록과 동기화 유지
ARG ENGINE=base
RUN pip install --no-cache-dir \
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
        pip install --no-cache-dir "google-genai>=1.0"; \
    fi

# ② Builder 에서 빌드된 wheel 복사 후 패키지 단독 설치 (deps 중복 설치 방지)
COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install --no-cache-dir --no-deps /tmp/*.whl && rm /tmp/*.whl

# ③ 런타임 설정 파일 복사 (/app 기준 상대 경로 로더 대응)
COPY --from=builder /build/orchestration.yaml /app/orchestration.yaml
COPY --from=builder /build/organizations.yaml /app/organizations.yaml
COPY --from=builder /build/workers.yaml /app/workers.yaml
COPY --from=builder /build/agent_hints.yaml /app/agent_hints.yaml
COPY --from=builder /build/improvement_thresholds.yaml /app/improvement_thresholds.yaml
COPY --from=builder /build/bots /app/bots

# ④ Node CLI 복사 (엔진별)
COPY --from=node-installer /opt/cli /opt/cli
ENV PATH="/opt/cli/bin:$PATH"

# ⑤ 데이터 디렉토리 생성 및 비루트 사용자 설정
RUN mkdir -p /app/logs /app/data /app/reports /app/tasks \
    && useradd -r -u 1001 -g root -s /sbin/nologin aiorg \
    && chown -R aiorg:root /app
USER aiorg

# ─── 환경변수 기본값 ──────────────────────────────────────────────────────────
# 실제 값은 --env-file .env 또는 docker-compose env_file 로 주입
ENV PM_BOT_TOKEN="" \
    TELEGRAM_BOT_TOKEN="" \
    TELEGRAM_GROUP_CHAT_ID="" \
    ANTHROPIC_API_KEY="" \
    OPENAI_API_KEY="" \
    GEMINI_API_KEY="" \
    CLAUDE_CODE_OAUTH_TOKEN="" \
    CLAUDE_CLI_PATH="/opt/cli/bin/claude" \
    CODEX_CLI_PATH="/opt/cli/bin/codex" \
    GEMINI_CLI_PATH="/opt/cli/bin/gemini" \
    GEMINI_CLI_DEFAULT_TIMEOUT_SEC="1800" \
    GEMINI_CLI_MODEL="gemini-2.5-flash" \
    CLAUDE_DEFAULT_TIMEOUT_SEC="14400" \
    CODEX_DEFAULT_TIMEOUT_SEC="1800" \
    ENGINE_TYPE="" \
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

# 기본 진입점: PyPI 패키지 CLI 또는 main.py 직접 실행
ENTRYPOINT ["python", "-m", "telegram_ai_org"]
CMD []
