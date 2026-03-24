# 환경변수 목록 — telegram-ai-org

> 생성일: 2026-03-25
> 수집 방법: `os.environ.get` / `os.getenv` / `os.environ[...]` 패턴 전수 grep
> 대상: `core/`, `tools/`, `scripts/`, `main.py`, `bots/*.yaml`

---

## 카테고리 분류

### 1. API 키 (필수/선택)

| 변수명 | 필수 | 기본값 | 설명 |
|--------|------|--------|------|
| `GEMINI_API_KEY` | 권장 | — | Google Gemini API 키 (LLM confidence scoring, gemini-2.5-flash) |
| `GOOGLE_API_KEY` | 선택 | — | GEMINI_API_KEY 대체 키 |
| `ANTHROPIC_API_KEY` | 선택 | — | Anthropic REST API 키 (GEMINI 없을 때 대체) |
| `DEEPSEEK_API_KEY` | 선택 | — | DeepSeek API 키 (최하위 대체) |

> 우선순위: GEMINI_API_KEY → GOOGLE_API_KEY → ANTHROPIC_API_KEY → DEEPSEEK_API_KEY → keyword fallback
> OPENAI_API_KEY는 제거됨 — Codex CLI는 `~/.codex/auth.json` OAuth 사용

---

### 2. 텔레그램 봇 설정 (필수)

| 변수명 | 필수 | 기본값 | 설명 |
|--------|------|--------|------|
| `TELEGRAM_BOT_TOKEN` | 필수 | — | PM 글로벌 봇 토큰 (PyPI/Docker 표준 변수명) |
| `PM_BOT_TOKEN` | 필수 | — | PM 봇 토큰 (TELEGRAM_BOT_TOKEN과 동일, 하위 호환) |
| `TELEGRAM_GROUP_CHAT_ID` | 필수 | — | 그룹 채팅 ID (음수값, 예: -5203707291) |
| `BOT_TOKEN_AIORG_PRODUCT_BOT` | 권장 | — | 기획실 봇 토큰 |
| `BOT_TOKEN_AIORG_ENGINEERING_BOT` | 권장 | — | 개발실 봇 토큰 |
| `BOT_TOKEN_AIORG_DESIGN_BOT` | 권장 | — | 디자인실 봇 토큰 (codex 엔진) |
| `BOT_TOKEN_AIORG_GROWTH_BOT` | 권장 | — | 성장실 봇 토큰 (gemini-cli 엔진) |
| `BOT_TOKEN_AIORG_OPS_BOT` | 권장 | — | 운영실 봇 토큰 (codex 엔진) |
| `BOT_TOKEN_AIORG_RESEARCH_BOT` | 권장 | — | 리서치실 봇 토큰 (gemini-cli 엔진) |
| `MKT_PM_TOKEN` | 선택 | — | 마케팅 팀 PM 봇 토큰 |
| `DEV_PM_TOKEN` | 선택 | — | 개발 팀 PM 봇 토큰 |
| `WATCHDOG_BOT_TOKEN` | 선택 | — | Watchdog 전용 봇 토큰 |
| `WATCHDOG_CHAT_ID` | 선택 | — | Watchdog 전용 채팅 ID |

---

### 3. 엔진별 설정

#### Claude Code 엔진 (`core/`, `tools/claude_code_runner.py`)

| 변수명 | 필수 | 기본값 | 설명 |
|--------|------|--------|------|
| `CLAUDE_CODE_OAUTH_TOKEN` | 필수 | — | Claude Code OAuth 토큰 (claude CLI 인증) |
| `CLAUDE_CLI_PATH` | 선택 | `/Users/rocky/.local/bin/claude` | claude CLI 실행 경로 |
| `CLAUDE_DEFAULT_TIMEOUT_SEC` | 선택 | `14400` | 기본 타임아웃 (초, 4시간) |
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | 선택 | `0` | 실험적 에이전트 팀 기능 (1=활성화) |

#### Codex 엔진 (`tools/codex_runner.py`)

| 변수명 | 필수 | 기본값 | 설명 |
|--------|------|--------|------|
| `CODEX_CLI_PATH` | 선택 | `codex` | codex CLI 실행 경로 |
| `CODEX_DEFAULT_TIMEOUT_SEC` | 선택 | `1800` | 기본 타임아웃 (초, 30분) |
| `CODEX_COMPLEX_TIMEOUT_SEC` | 선택 | `14400` | 복잡 태스크 타임아웃 (초, 4시간) |
| `CODEX_REPO_SEARCH_ROOTS` | 선택 | — | 리포지토리 검색 루트 (콜론 구분) |

#### Gemini CLI 엔진 (`tools/gemini_cli_runner.py`, `tools/gemini_runner.py`)

| 변수명 | 필수 | 기본값 | 설명 |
|--------|------|--------|------|
| `GEMINI_CLI_PATH` | 선택 | `/opt/homebrew/bin/gemini` | gemini CLI 실행 경로 |
| `GEMINI_CLI_DEFAULT_TIMEOUT_SEC` | 선택 | `1800` | 기본 타임아웃 (초, 30분) |

#### 엔진 선택

| 변수명 | 필수 | 기본값 | 설명 |
|--------|------|--------|------|
| `ENGINE` | 선택 | — | 기본 실행 엔진 (claude-code \| codex \| gemini-cli) |
| `ENGINE_TYPE` | 선택 | — | docker-compose 엔진 식별자 |

---

### 4. 기능 플래그

| 변수명 | 필수 | 기본값 | 설명 | 코드 참조 |
|--------|------|--------|------|-----------|
| `ENABLE_PM_ORCHESTRATOR` | 선택 | `0` | PM 중앙 통제 모드 | `core/pm_orchestrator.py` |
| `ENABLE_DISCUSSION_PROTOCOL` | 선택 | `0` | 부서간 토론 프로토콜 | `core/discussion.py` |
| `ENABLE_AUTO_DISPATCH` | 선택 | `0` | 태스크 의존성 자동 디스패치 | `core/dispatch_engine.py` |
| `ENABLE_CROSS_VERIFICATION` | 선택 | `0` | Codex↔Claude 교차 검증 | `core/verification.py` |
| `ENABLE_GOAL_TRACKER` | 선택 | `0` | PM 목표 달성 루프 | `core/goal_tracker.py` |

---

### 5. DB/스토리지

| 변수명 | 필수 | 기본값 | 설명 | 코드 참조 |
|--------|------|--------|------|-----------|
| `CONTEXT_DB_PATH` | 선택 | `~/.ai-org/context.db` | Context DB 경로 | `core/context_db.py` |
| `SHARED_MEMORY_PATH` | 선택 | `~/.ai-org/shared_memory.json` | 공유 메모리 JSON | `scripts/monthly_review.py` |
| `AIORG_REPORT_DIR` | 선택 | `./reports` | 리포트 저장 디렉토리 | `core/pm_orchestrator.py` |
| `DB_PATH` | 선택 | `~/.ai-org/context.db` | MCP 서버용 DB 경로 | `tools/memory_mcp_server.py` |
| `BOT_ID` | 선택 | `unknown` | MCP 서버 봇 식별자 | `tools/memory_mcp_server.py` |

---

### 6. 봇 동작 / 타임아웃

| 변수명 | 필수 | 기본값 | 설명 | 코드 참조 |
|--------|------|--------|------|-----------|
| `BOT_IDLE_TIMEOUT_SEC` | 선택 | `120` | 봇 무응답 타임아웃 (초) | `core/telegram_relay.py` |
| `BOT_HB_INTERVAL_SEC` | 선택 | `30` | 하트비트 전송 간격 (초) | `core/telegram_relay.py` |
| `BOT_MAX_TIMEOUT_SEC` | 선택 | `1800` | 봇 절대 상한 타임아웃 (초) | `core/telegram_relay.py` |
| `PM_CHAT_REPLY_TIMEOUT_SEC` | 선택 | `300` | PM 채팅 응답 대기 타임아웃 (초) | `core/telegram_relay.py` |
| `PM_COUNT` | 선택 | `1` | 동시 실행 PM 봇 수 | `core/telegram_relay.py` |
| `PM_ORG_NAME` | 선택 | `global` | 조직 이름 식별자 | `main.py` |

---

### 7. 비용/성능 제한

| 변수명 | 필수 | 기본값 | 설명 | 코드 참조 |
|--------|------|--------|------|-----------|
| `PM_HOURLY_CALL_LIMIT` | 선택 | `100` | 시간당 API 호출 상한 | `core/llm_cost_tracker.py` |
| `DAILY_COST_LIMIT_USD` | 선택 | `50.0` | 일일 비용 상한 (USD) | `core/llm_cost_tracker.py` |
| `COST_PER_1K_TOKENS_USD` | 선택 | `0.003` | 토큰 1000개당 비용 (USD) | `core/llm_cost_tracker.py` |
| `CIRCUIT_BREAKER_ERROR_THRESHOLD` | 선택 | `3` | 서킷 브레이커 오류 임계치 | `core/llm_cost_tracker.py` |
| `CIRCUIT_BREAKER_RESET_SEC` | 선택 | `600` | 서킷 브레이커 리셋 시간 (초) | `core/llm_cost_tracker.py` |

---

### 8. Staleness 체크

| 변수명 | 필수 | 기본값 | 설명 | 코드 참조 |
|--------|------|--------|------|-----------|
| `STALE_THRESHOLD_SEC` | 선택 | `300` | 스탈 임계값 (초) | `core/staleness_checker.py` |
| `HEARTBEAT_GRACE_SEC` | 선택 | `120` | 하트비트 그레이스 시간 (초) | `core/staleness_checker.py` |
| `SUBTASK_TIMEOUT_SEC` | 선택 | `600` | 서브태스크 타임아웃 (초) | `core/staleness_checker.py` |
| `STALENESS_CHECK_INTERVAL_SEC` | 선택 | `60` | 스탈 체크 인터벌 (초) | `core/staleness_checker.py` |

---

### 9. 컨텍스트 윈도우 / PM 오케스트레이터

| 변수명 | 필수 | 기본값 | 설명 | 코드 참조 |
|--------|------|--------|------|-----------|
| `MAX_HISTORY_MESSAGES` | 선택 | `20` | 히스토리 최대 메시지 수 | `core/context_window.py` |
| `MAX_HISTORY_TOKENS` | 선택 | `6000` | 히스토리 최대 토큰 수 | `core/context_window.py` |
| `MAX_REWORK_RETRIES` | 선택 | `2` | 재작업 최대 재시도 횟수 | `core/pm_orchestrator.py` |
| `MAX_CONCURRENT_PARENT_TASKS` | 선택 | `10` | 동시 부모 태스크 최대 수 | `core/pm_orchestrator.py` |
| `CLAIM_TTL_SEC` | 선택 | `600` | Claim TTL (초) | `core/claim_manager.py` |
| `TEXT_HASH_TTL_SEC` | 선택 | `86400` | 텍스트 해시 TTL (초, 24시간) | `core/claim_manager.py` |

---

### 10. 첨부파일 분석 (선택)

| 변수명 | 필수 | 기본값 | 설명 | 코드 참조 |
|--------|------|--------|------|-----------|
| `ATTACHMENT_VISION_BRIDGE_CMD` | 선택 | — | 이미지 분석 브리지 명령어 | `core/attachment_analysis.py` |
| `ATTACHMENT_MULTIMODAL_BRIDGE_CMD` | 선택 | — | 멀티모달 브리지 명령어 | `core/attachment_analysis.py` |
| `ATTACHMENT_VISION_BRIDGE_TIMEOUT_SEC` | 선택 | `60` | 비전 브리지 타임아웃 (초) | `core/attachment_analysis.py` |

---

### 11. UI/디스플레이 (선택)

| 변수명 | 필수 | 기본값 | 설명 | 코드 참조 |
|--------|------|--------|------|-----------|
| `USE_DISPLAY_LIMITER` | 선택 | `true` | 메시지 디스플레이 제한기 활성화 | `core/telegram_relay.py` |
| `NO_COLOR` | 선택 | — | 터미널 색상 비활성화 (값 있으면 off) | `scripts/setup_wizard.py` |
| `AUTONOMOUS_MODE` | 선택 | `false` | 자율 실행 모드 | 전역 |

---

### 12. E2E 테스트 전용

| 변수명 | 필수 | 기본값 | 설명 | 코드 참조 |
|--------|------|--------|------|-----------|
| `TELEGRAM_API_ID` | E2E전용 | — | Telegram MTProto API ID | `scripts/e2e_*.py` |
| `TELEGRAM_API_HASH` | E2E전용 | — | Telegram MTProto API Hash | `scripts/e2e_*.py` |
| `TELEGRAM_PHONE` | E2E전용 | — | 등록된 전화번호 | `scripts/tg_auth.py` |

---

## 누락 변수 식별 리포트

| 항목 | 상태 | 비고 |
|------|------|------|
| 코드베이스 전체 env var 수집 | ✅ 완료 | 총 ~55개 변수 |
| .env.example 커버리지 | ✅ 100% | 모든 변수 포함 |
| 코드에 있고 .env.example에 없는 변수 | ✅ 없음 | 완전 일치 |
| Redis 연결 변수 (`REDIS_URL` 등) | N/A | 현재 코드에서 Redis 미사용 (docker-compose 사이드카만) |
| `PYTHONUNBUFFERED`, `PYTHONDONTWRITEBYTECODE` | Docker 내부 | Dockerfile ENV에만 존재, .env 불필요 |
