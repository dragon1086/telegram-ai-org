# telegram-ai-org (aimesh)

> **"10분 안에 텔레그램에서 당신만의 AI 조직을 운영하세요"**

텔레그램 그룹 채팅방을 AI 조직의 오피스로 만드는 오픈소스 멀티봇 오케스트레이션 시스템.
PM 봇이 사용자 요청을 분석해 7개 전문 부서 봇에 자동 배분합니다.
**Claude Code / Codex / Gemini CLI** 3개 엔진을 모두 지원합니다.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Engine](https://img.shields.io/badge/engine-claude--code%20%7C%20codex%20%7C%20gemini--cli-orange.svg)](#3엔진-선택-가이드)
[![PyPI version](https://img.shields.io/pypi/v/telegram-ai-org.svg)](https://pypi.org/project/telegram-ai-org/)
[![CI](https://img.shields.io/github/actions/workflow/status/dragon1086/aimesh/ci.yml?label=CI&logo=github)](https://github.com/dragon1086/aimesh/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/actions/workflow/status/dragon1086/aimesh/release.yml?label=Release&logo=github)](https://github.com/dragon1086/aimesh/actions/workflows/release.yml)
[![Docker Hub](https://img.shields.io/docker/v/dragon1086/aimesh?label=Docker&logo=docker&color=blue)](https://hub.docker.com/r/dragon1086/aimesh)

---

## 목차

- [주요 기능](#주요-기능)
- [아키텍처](#아키텍처)
- [빠른 시작 (10분)](#빠른-시작-10분)
- [3엔진 선택 가이드](#3엔진-선택-가이드)
- [Docker 실행법](#docker-실행법)
- [환경변수 설명](#환경변수-설명)
- [봇 구성](#봇-구성)
- [주요 명령어](#주요-명령어)
- [내장 스킬 목록](#내장-스킬-목록)
- [CI/CD](#cicd)
- [FAQ / 트러블슈팅](#faq--트러블슈팅)
- [기여하기](#기여하기)
- [기술 스택](#기술-스택)
- [관련 프로젝트](#관련-프로젝트)
- [라이선스](#라이선스)
- [기여자](#기여자)

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| **PM 오케스트레이션** | 자연어 태스크를 PM 봇이 분석 → 적합한 부서 봇에 자동 배분 |
| **7개 전문 부서봇** | PM / 기획실 / 개발실 / 디자인실 / 성장실 / 운영실 / 리서치실 |
| **3엔진 호환** | Claude Code (PRD·기획·코드 추론) / Codex (DevOps 자동화) / Gemini CLI (실시간 웹 검색·멀티모달) |
| **봇 캐릭터 진화** | 각 봇은 고유 성격·어조·캐치프레이즈를 가지고 시간에 따라 진화 |
| **팀워크·칭찬 시스템** | 봇 간 협업 트래킹, shoutout 자동 생성 |
| **교훈 메모리** | 작업 결과를 메모리에 저장, 다음 태스크에 자동 반영 |
| **자연어 스케줄** | "매주 월요일 오전 9시에 리포트 보내줘" 형식의 스케줄 등록 |
| **멀티부서 토론** | 여러 봇이 하나의 주제를 토론 후 PM이 합성 결과 생성 |
| **스킬 시스템** | 재사용 가능한 작업 템플릿 (PRD 작성, E2E 테스트, 코드 리뷰 등) |
| **Telegram Native UI** | 채팅방 자체가 오피스 — 별도 대시보드 불필요 |

---

## 아키텍처

```
Telegram 그룹 채팅방
        │
        ▼
┌──────────────────────────────────────────────────────────┐
│                   PM Bot (aiorg_pm_bot)                   │
│                   엔진: claude-code                        │
│  ┌─────────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │  nl_classifier  │  │  pm_router  │  │  scheduler  │  │
│  │  (태스크 분류)   │→ │ (부서 라우팅)│→ │ (자연어 예약)│  │
│  └─────────────────┘  └─────────────┘  └─────────────┘  │
│  ┌────────────────────────────────────────────────────┐  │
│  │           pm_orchestrator  (메인 루프)              │  │
│  │   GoalTracker · DiscussionProtocol                 │  │
│  │   AutoDispatch · SynthesisLoop                     │  │
│  └────────────────────────────────────────────────────┘  │
└────────────────────────┬─────────────────────────────────┘
                         │ 태스크 배분
          ┌──────────────┼──────────────────────┐
          ▼              ▼                      ▼
┌──────────────────┐  ┌──────────┐  ┌──────────────────┐
│  claude-code 계열 │  │codex 계열│  │  gemini-cli 계열  │
│ 기획실·개발실     │  │  운영실  │  │  성장실·리서치실  │
│ 디자인실(PM 포함) │  │ 배포/인프│  │  조사/검색       │
└──────────────────┘  └──────────┘  └──────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│                  엔진 러너 레이어 (tools/)                  │
│  ClaudeCodeRunner │ CodexRunner │ GeminiCLIRunner         │
│  복잡한 추론      │ CLI 자동화  │ 실시간 웹 검색            │
└──────────────────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│                  스킬 / MCP 레이어 (skills/)               │
│  quality-gate · e2e-regression · bot-triage               │
│  gemini-image-gen · safe-modify · error-gotcha            │
│  brainstorming-auto · weekly-review · + 16개 더           │
└──────────────────────────────────────────────────────────┘
```

### 핵심 파일 구조

```
telegram-ai-org/
├── main.py                          # 로컬 진입점
├── orchestration.yaml               # 전체 오케스트레이션 설정
├── workers.yaml                     # 워커 봇 등록부
│
├── bots/                            # 봇별 YAML 정의 (성격, 역할, 엔진)
│   ├── aiorg_pm_bot.yaml            #   PM — claude-code
│   ├── aiorg_product_bot.yaml       #   기획실 — claude-code
│   ├── aiorg_engineering_bot.yaml   #   개발실 — claude-code
│   ├── aiorg_design_bot.yaml        #   디자인실 — claude-code
│   ├── aiorg_growth_bot.yaml        #   성장실 — gemini-cli
│   ├── aiorg_ops_bot.yaml           #   운영실 — codex
│   └── aiorg_research_bot.yaml      #   리서치실 — gemini-cli
│
├── core/                            # 핵심 오케스트레이션 로직
│   ├── pm_orchestrator.py           # PM 메인 루프
│   ├── pm_router.py                 # 태스크 → 부서 라우팅
│   ├── nl_classifier.py             # 자연어 분류기
│   ├── telegram_relay.py            # Telegram 메시지 중계
│   ├── scheduler.py                 # 내장 스케줄러
│   └── lesson_memory.py             # 교훈 메모리
│
├── tools/                           # 엔진 러너 및 CLI 도구
│   ├── claude_code_runner.py        # Claude Code CLI 래퍼
│   ├── codex_runner.py              # Codex CLI 래퍼
│   ├── gemini_cli_runner.py         # Gemini CLI OAuth 러너
│   └── orchestration_cli.py         # 설정 검증 CLI
│
├── skills/                          # 재사용 가능한 작업 스킬 (24개)
│   ├── quality-gate/                #   코드 품질 검사
│   ├── e2e-regression/              #   E2E 회귀 테스트
│   ├── gemini-image-gen/            #   Gemini OAuth 이미지 생성
│   ├── bot-triage/                  #   봇 장애 진단
│   └── ...
│
├── scripts/                         # 운영 스크립트
│   ├── setup.sh                     # 원클릭 초기 설치
│   ├── start_all.sh                 # 전체 봇 시작
│   ├── watchdog.sh                  # 프로세스 감시/자동 재기동
│   └── request_restart.sh           # 안전한 재기동 요청
│
├── CLAUDE.md                        # Claude Code 운영 지침 (기준 문서)
├── AGENTS.md                        # Codex CLI 운영 지침
├── GEMINI.md                        # Gemini CLI 운영 지침
└── .env.example                     # 환경변수 템플릿
```

---

## 빠른 시작 (10분)

### 사전 준비

- Python 3.10 이상
- Node.js 18+ (Gemini CLI 또는 Codex CLI 사용 시)
- Telegram 계정 + [@BotFather](https://t.me/BotFather)에서 봇 토큰 발급
- 아래 3개 엔진 중 **1개 이상** 설치 (→ [3엔진 선택 가이드](#3엔진-선택-가이드))

### 원클릭 설치 (권장)

```bash
# 1. 저장소 클론
git clone https://github.com/dragon1086/aimesh.git
cd aimesh

# 2. 원클릭 설치 — 엔진 자동 감지 + 의존성 + .env 생성 + 검증
bash scripts/setup.sh

# 3. .env 파일에 Telegram 봇 토큰 입력
nano .env

# 4. 모든 봇 시작
bash scripts/start_all.sh
```

### setup.sh 자동 감지 흐름 (5단계)

`setup.sh`가 자동으로 수행하는 5단계:

```
▶ Step 1/5: AI 엔진 자동 감지
  ✅ codex 감지됨:  /opt/homebrew/bin/codex
  ✅ gemini 감지됨: /opt/homebrew/bin/gemini
  ⚠️  claude CLI 미감지 (설치: https://claude.ai/code)
  감지된 엔진: codex gemini (총 2개)

▶ Step 2/5: Python 환경 확인 (3.13→3.12→3.11→3.10 순 자동 선택)
  ✅ Python 3.12.x — 요구사항 충족

▶ Step 3/5: Python 의존성 설치
  ✅ .venv 생성 및 의존성 설치 완료

▶ Step 4/5: 환경 변수 파일 설정
  ✅ .env 파일 생성 완료
  ℹ️  GEMINI_CLI_PATH → /opt/homebrew/bin/gemini (자동 설정)
  ℹ️  CODEX_CLI_PATH  → /opt/homebrew/bin/codex  (자동 설정)

▶ Step 5/5: 초기화 검증
  ✅ import anthropic   ✅ import pydantic
  ✅ import telegram    ✅ import loguru
  검증 완료: 10/10 항목 통과 — 모두 정상
```

#### setup.sh 옵션

| 옵션 | 설명 |
|------|------|
| `bash scripts/setup.sh` | 기본 실행 (대화형) |
| `bash scripts/setup.sh --yes` | CI/자동화 환경 무인 설치 (프롬프트 건너뜀) |
| `bash scripts/setup.sh --docker` | Docker 환경 감지 후 `docker compose up` 자동 실행 |
| `bash scripts/setup.sh --yes --docker` | CI 환경 + Docker Compose 자동 실행 (완전 비대화형) |
| `bash scripts/setup.sh --skip-verify` | 검증 단계 건너뜀 (빠른 재설치) |
| `bash scripts/setup.sh --no-venv` | 가상환경 생성 건너뜀 (기존 환경 재사용) |

#### 3엔진 자동 감지 규칙

| 엔진 | 감지 조건 | 인증 확인 |
|------|-----------|-----------|
| **claude-code** | `which claude` 성공 + `--version` 실행 가능 | `CLAUDE_CODE_OAUTH_TOKEN` 또는 브라우저 OAuth |
| **codex** | `which codex` 성공 + `--version` 실행 가능 | `~/.codex/auth.json` 또는 `OPENAI_API_KEY` |
| **gemini-cli** | `/opt/homebrew/bin/gemini` 우선 또는 `which gemini` + `--version` | `~/.gemini/oauth_creds.json` (OAuth) |

감지된 엔진 경로는 `.env`의 `CLAUDE_CLI_PATH`, `CODEX_CLI_PATH`, `GEMINI_CLI_PATH`에 자동으로 기재됩니다.

### PyPI 설치

```bash
pip install telegram-ai-org
```

### 개발용 설치 (editable 모드)

```bash
git clone https://github.com/dragon1086/aimesh.git
cd aimesh
pip install -e .           # 기본 설치
pip install -e ".[dev]"    # 개발 도구 포함
```

### 설치 후 텔레그램 확인

텔레그램 그룹에서 PM 봇에게 메시지를 보내세요:

```
안녕, 오늘 마케팅 전략 분석 부탁해
```

PM 봇이 성장실 봇에게 태스크를 자동 배분하고 결과를 전달합니다.

---

## 3엔진 선택 가이드

각 엔진의 특성에 따라 부서별 최적 엔진이 배정됩니다. `bots/*.yaml`의 `engine:` 필드로 변경 가능합니다.

### 부서별 권장 엔진

| 부서 | 봇 ID | 권장 엔진 | 선택 이유 |
|------|-------|-----------|-----------|
| PM | `aiorg_pm_bot` | **claude-code** | 복잡한 멀티스텝 추론, 오케스트레이션 판단 |
| 기획실 | `aiorg_product_bot` | **claude-code** | PRD 작성, 장문 컨텍스트 구조화 |
| 개발실 | `aiorg_engineering_bot` | **claude-code** | 코드 구현, 버그 수정, 타입 추론 |
| 디자인실 | `aiorg_design_bot` | **claude-code** | UI/UX 설계, 멀티모달 이미지 이해 |
| 운영실 | `aiorg_ops_bot` | **codex** | 경량 CLI 특화, DevOps 스크립트 자동화 |
| 성장실 | `aiorg_growth_bot` | **gemini-cli** | Google 검색 내장, 실시간 트렌드 조사 |
| 리서치실 | `aiorg_research_bot` | **gemini-cli** | 웹 데이터 실시간 조회, 1M 토큰 컨텍스트 |

### 엔진 비교 매트릭스

| 비교 항목 | claude-code | codex | gemini-cli |
|-----------|-------------|-------|------------|
| 설치 명령 | `npm i -g @anthropic-ai/claude-code` | `npm i -g @openai/codex` | `npm i -g @google/gemini-cli` |
| 인증 방식 | `claude auth login` (OAuth) | `codex login` (OAuth) | `gemini auth login` (OAuth) |
| 인증 파일 | OAuth 세션 | `~/.codex/auth.json` | `~/.gemini/oauth_creds.json` |
| 웹 검색 | 없음 | 없음 | **내장** (Google Search) |
| 최적 태스크 | PRD·코드·설계·기획 | 배포·인프라 CLI | 시장조사·경쟁사 분석 |
| 컨텍스트 길이 | 200K 토큰 | 표준 | **1M 토큰** |
| 멀티모달 | 이미지 이해 | 제한적 | **이미지 이해·생성** |

> **API 키 없이 사용 가능**: 3개 엔진 모두 OAuth 2.0 인증을 지원하므로 별도 API 키 없이 운용할 수 있습니다.
> 태스크 신뢰도 스코어링 기능 사용 시에만 `GEMINI_API_KEY` 또는 `ANTHROPIC_API_KEY`가 선택적으로 필요합니다.

### 엔진별 설치 방법

#### 1. Claude Code (기본·권장)

```bash
npm install -g @anthropic-ai/claude-code
claude auth login   # 브라우저 OAuth
claude --version
```

#### 2. Codex CLI

```bash
npm install -g @openai/codex
codex login         # 브라우저 OAuth → ~/.codex/auth.json 생성
codex --version
```

#### 3. Gemini CLI

```bash
# Homebrew 권장
brew install gemini-cli
# 또는 npm
npm install -g @google/gemini-cli

gemini auth login   # Google OAuth → ~/.gemini/oauth_creds.json 생성
gemini --version
```

---

## Docker 실행법

Docker Compose는 **공통 시크릿은 `.env`에서**, **엔진별 런타임 변수는 `docker-compose.yml`의 `environment` 블록에서** 주입합니다.
서비스는 조직별로 분리되어 있고, 이미지 빌드는 엔진별(`claude` / `codex` / `gemini`)로 나뉩니다.

### 빠른 시작

```bash
# 1. 환경변수 준비
cp .env.example .env
nano .env  # 필수 토큰 입력

# 2. 전체 조직 빌드 + 실행
docker compose --profile claude --profile codex --profile gemini up -d

# 3. 상태 확인
docker compose ps
```

### 프로파일별 선택 실행

```bash
# Claude 계열만 (PM + 기획실 + 개발실 + 디자인실)
docker compose --profile claude up -d

# Codex 계열만 (운영실)
docker compose --profile codex up -d

# Gemini 계열만 (성장실 + 리서치실)
docker compose --profile gemini up -d

# 전체 조직 동시 실행
docker compose --profile claude --profile codex --profile gemini up -d
```

### 서비스 구조

| 프로파일 | 컨테이너명 | 봇 역할 | 자동 주입 엔진 변수 |
|----------|-----------|---------|-------------------|
| `claude` | `aiorg-pm` | PM 오케스트레이터 | `ENGINE_TYPE=claude-code` |
| `claude` | `aiorg-product-bot` | 기획실 | `ENGINE_TYPE=claude-code` |
| `claude` | `aiorg-engineering-bot` | 개발실 | `ENGINE_TYPE=claude-code` |
| `claude` | `aiorg-design-bot` | 디자인실 | `ENGINE_TYPE=claude-code` |
| `codex` | `aiorg-ops-bot` | 운영실 | `ENGINE_TYPE=codex` |
| `gemini` | `aiorg-growth-bot` | 성장실 | `ENGINE_TYPE=gemini-cli`, `GEMINI_CLI_MODEL=gemini-2.5-flash` |
| `gemini` | `aiorg-research-bot` | 리서치실 | `ENGINE_TYPE=gemini-cli`, `GEMINI_CLI_MODEL=gemini-2.5-flash` |

공통 Redis: `aiorg-redis` (Redis 7 alpine, 포트 6379 — 내부 전용)

공통 볼륨 마운트: `./logs`, `./data`, `./reports`, `./tasks`, `./skills` (read-only), `./memory`

### 이미지 빌드 (선택적)

```bash
docker compose build                                        # 전체 빌드
docker compose build aiorg-pm aiorg-product-bot aiorg-engineering-bot aiorg-design-bot
docker compose build aiorg-ops-bot
docker compose build aiorg-growth-bot aiorg-research-bot
```

### 로그 확인

```bash
docker compose ps
docker compose logs -f aiorg-pm
docker compose logs -f aiorg-ops-bot
docker compose logs -f aiorg-research-bot
```

### `.env` 최소 필수값 (Docker 실행 전)

```bash
TELEGRAM_BOT_TOKEN=          # PM 봇 토큰
TELEGRAM_GROUP_CHAT_ID=      # 그룹 채팅 ID (음수)
BOT_TOKEN_AIORG_PRODUCT_BOT=
BOT_TOKEN_AIORG_ENGINEERING_BOT=
BOT_TOKEN_AIORG_DESIGN_BOT=
BOT_TOKEN_AIORG_GROWTH_BOT=
BOT_TOKEN_AIORG_OPS_BOT=
BOT_TOKEN_AIORG_RESEARCH_BOT=
GEMINI_API_KEY=              # 신뢰도 스코어링용 (선택)
```

---

## 환경변수 설명

`.env.example`을 복사해 `.env`를 만들고 값을 채웁니다.

```bash
cp .env.example .env
nano .env
```

> **보안**: `.env` 파일에는 비밀 토큰이 포함됩니다. `.gitignore`에 이미 포함되어 있으니 절대 커밋하지 마세요.

### Telegram 봇 토큰

| 변수명 | 목적 | 필수 여부 | 예시값 |
|--------|------|-----------|--------|
| `TELEGRAM_BOT_TOKEN` | PM 봇 토큰 (@BotFather 발급) | **필수** | `123456:ABC-DEF...` |
| `PM_BOT_TOKEN` | `TELEGRAM_BOT_TOKEN` 하위 호환 별칭 | 선택 | 동일 |
| `TELEGRAM_GROUP_CHAT_ID` | 그룹 채팅 ID (음수값) | **필수** | `-5203707291` |
| `ADMIN_CHAT_ID` | 관리자 개인 채팅 ID (오류 알림용) | 선택 (권장) | `123456789` |
| `BOT_TOKEN_AIORG_PRODUCT_BOT` | 기획실 봇 토큰 | 기획실 사용 시 필수 | `123456:ABC...` |
| `BOT_TOKEN_AIORG_ENGINEERING_BOT` | 개발실 봇 토큰 | 개발실 사용 시 필수 | `123456:ABC...` |
| `BOT_TOKEN_AIORG_DESIGN_BOT` | 디자인실 봇 토큰 | 디자인실 사용 시 필수 | `123456:ABC...` |
| `BOT_TOKEN_AIORG_GROWTH_BOT` | 성장실 봇 토큰 | 성장실 사용 시 필수 | `123456:ABC...` |
| `BOT_TOKEN_AIORG_OPS_BOT` | 운영실 봇 토큰 | 운영실 사용 시 필수 | `123456:ABC...` |
| `BOT_TOKEN_AIORG_RESEARCH_BOT` | 리서치실 봇 토큰 | 리서치실 사용 시 필수 | `123456:ABC...` |
| `WATCHDOG_BOT_TOKEN` | Watchdog 전용 봇 토큰 | 선택 | `123456:ABC...` |
| `WATCHDOG_CHAT_ID` | Watchdog 전용 채팅 ID | 선택 | `-5203707291` |

### LLM API 키 (신뢰도 스코어링용)

> 우선순위: `GEMINI_API_KEY` → `ANTHROPIC_API_KEY` → `DEEPSEEK_API_KEY` → keyword fallback

| 변수명 | 목적 | 필수 여부 | 예시값 |
|--------|------|-----------|--------|
| `GEMINI_API_KEY` | Google Gemini API (권장 — gemini-2.5-flash) | 선택 (권장) | `AIza...` |
| `GOOGLE_API_KEY` | `GEMINI_API_KEY` 대체 키 | 선택 | `AIza...` |
| `ANTHROPIC_API_KEY` | Anthropic REST API (대체용) | 선택 | `sk-ant-...` |
| `DEEPSEEK_API_KEY` | DeepSeek API (최하위 대체) | 선택 | `sk-...` |

### Claude Code 엔진 설정

| 변수명 | 목적 | 필수 여부 | 예시값 |
|--------|------|-----------|--------|
| `CLAUDE_CODE_OAUTH_TOKEN` | Claude Code CLI 인증 토큰 | Claude Code 사용 시 필수 | OAuth 토큰 문자열 |
| `CLAUDE_CLI_PATH` | claude CLI 실행 파일 경로 | 선택 (setup.sh 자동 감지) | `/Users/user/.local/bin/claude` |
| `CLAUDE_DEFAULT_TIMEOUT_SEC` | 태스크 기본 타임아웃 (초) | 선택 | `14400` (4시간) |
| `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS` | 실험적 에이전트 팀 기능 | 선택 | `0` |

### Codex 엔진 설정

| 변수명 | 목적 | 필수 여부 | 예시값 |
|--------|------|-----------|--------|
| `CODEX_CLI_PATH` | codex CLI 실행 파일 경로 | 선택 (setup.sh 자동 감지) | `/opt/homebrew/bin/codex` |
| `OPENAI_API_KEY` | OpenAI API 키 (OAuth 없을 때 대체) | 선택 | `sk-...` |
| `CODEX_DEFAULT_TIMEOUT_SEC` | 기본 타임아웃 (초) | 선택 | `1800` (30분) |
| `CODEX_COMPLEX_TIMEOUT_SEC` | 복잡 태스크 타임아웃 (초) | 선택 | `14400` (4시간) |
| `CODEX_REPO_SEARCH_ROOTS` | 리포지토리 검색 루트 (콜론 구분) | 선택 | `/home/user/projects` |

### Gemini CLI 엔진 설정

| 변수명 | 목적 | 필수 여부 | 예시값 |
|--------|------|-----------|--------|
| `GEMINI_CLI_PATH` | gemini CLI 실행 파일 경로 | 선택 (setup.sh 자동 감지) | `/opt/homebrew/bin/gemini` |
| `GEMINI_OAUTH_CREDS_PATH` | OAuth 인증 파일 경로 | 선택 | `~/.gemini/oauth_creds.json` |
| `GEMINI_CLI_DEFAULT_TIMEOUT_SEC` | 기본 타임아웃 (초) | 선택 | `1800` (30분) |
| `GEMINI_CLI_MODEL` | 사용 모델 | 선택 | `gemini-2.5-flash` |

### 엔진 선택

| 변수명 | 목적 | 필수 여부 | 예시값 |
|--------|------|-----------|--------|
| `DEFAULT_ENGINE` | 기본 엔진 (setup.sh 자동 감지 후 기재) | 선택 | `claude-code` |
| `ENGINE_TYPE` | Docker Compose 런타임 엔진 | 선택 | `claude-code` \| `codex` \| `gemini-cli` |

> `ENGINE`, `ACTIVE_ENGINE`은 deprecated — 런타임에서 `organizations.yaml`의 `preferred_engine` 필드를 우선 참조합니다.

### Feature Flags

| 변수명 | 목적 | 필수 여부 | 기본값 |
|--------|------|-----------|--------|
| `ENABLE_PM_ORCHESTRATOR` | PM 중앙 통제 모드 | 선택 | `1` |
| `ENABLE_DISCUSSION_PROTOCOL` | 부서간 토론 프로토콜 | 선택 | `1` |
| `ENABLE_AUTO_DISPATCH` | 태스크 의존성 자동 디스패치 | 선택 | `1` |
| `ENABLE_CROSS_VERIFICATION` | Codex↔Claude Code 교차 검증 | 선택 | `1` |
| `ENABLE_GOAL_TRACKER` | PM 목표 달성 루프 | 선택 (권장) | `1` |
| `AUTONOMOUS_MODE` | 자율 실행 모드 (인터랙티브 자동 응답) | 선택 | `false` |

### DB / 스토리지

| 변수명 | 목적 | 필수 여부 | 기본값 |
|--------|------|-----------|--------|
| `CONTEXT_DB_PATH` | Context DB 경로 | 선택 | `~/.ai-org/context.db` |
| `SHARED_MEMORY_PATH` | 공유 메모리 JSON 경로 | 선택 | `~/.ai-org/shared_memory.json` |
| `AIORG_REPORT_DIR` | 리포트 저장 디렉토리 | 선택 | `./reports` |
| `DB_PATH` | MCP 서버용 DB 경로 | 선택 | `~/.ai-org/context.db` |

### 봇 동작 / 타임아웃

| 변수명 | 목적 | 필수 여부 | 기본값 |
|--------|------|-----------|--------|
| `BOT_IDLE_TIMEOUT_SEC` | 봇 무응답 타임아웃 (초) | 선택 | `300` |
| `BOT_HB_INTERVAL_SEC` | 하트비트 전송 간격 (초) | 선택 | `30` |
| `BOT_MAX_TIMEOUT_SEC` | 봇 절대 상한 타임아웃 (초) | 선택 | `1800` |
| `PM_CHAT_REPLY_TIMEOUT_SEC` | PM 채팅 응답 대기 (초) | 선택 | `300` |
| `PM_COUNT` | 동시 실행 PM 봇 수 | 선택 | `1` |
| `PM_ORG_NAME` | 조직 이름 식별자 | 선택 | `global` |

### 비용 / 서킷 브레이커

| 변수명 | 목적 | 필수 여부 | 기본값 |
|--------|------|-----------|--------|
| `PM_HOURLY_CALL_LIMIT` | 시간당 API 호출 상한 | 선택 | `40` |
| `DAILY_COST_LIMIT_USD` | 일일 비용 상한 (USD) | 선택 | `50.0` |
| `COST_PER_1K_TOKENS_USD` | 토큰 1000개당 비용 (USD) | 선택 | `0.003` |
| `CIRCUIT_BREAKER_ERROR_THRESHOLD` | 서킷 브레이커 오류 임계치 | 선택 | `3` |
| `CIRCUIT_BREAKER_RESET_SEC` | 서킷 브레이커 리셋 시간 (초) | 선택 | `300` |

### CI/CD 변수

| 변수명 | 목적 | 필수 여부 | 예시값 |
|--------|------|-----------|--------|
| `PYPI_API_TOKEN` | PyPI publish 토큰 | Release 시 필수 | `pypi-...` |
| `DOCKER_USERNAME` | Docker Hub 사용자명 | Docker 배포 시 필수 | `dragon1086` |
| `DOCKER_PASSWORD` | Docker Hub access token | Docker 배포 시 필수 | `dckr_pat_...` |

### 로깅

| 변수명 | 목적 | 필수 여부 | 기본값 |
|--------|------|-----------|--------|
| `LOG_LEVEL` | 로그 레벨 | 선택 | `INFO` |
| `AIORG_DEBUG` | 디버그 모드 (상세 트레이스) | 선택 | `false` |
| `USE_DISPLAY_LIMITER` | 메시지 디스플레이 제한기 | 선택 | `true` |

전체 환경변수 레퍼런스: [`.env.example`](.env.example)

---

## 봇 구성

각 봇은 `bots/*.yaml` 파일로 정의됩니다.

### 봇 YAML 구조

```yaml
schema_version: 2
organization_ref: aiorg_product_bot   # 봇 고유 ID
username: aiorg_product_bot           # Telegram 사용자명
token_env: BOT_TOKEN_AIORG_PRODUCT_BOT
chat_id: -5203707291                   # 그룹 chat_id
engine: claude-code                    # claude-code | codex | gemini-cli
dept_name: 기획실
role: PRD/요구사항 분석/기획
is_pm: false

# 봇 성격 (캐릭터 시스템)
personality: "논리적이고 사용자 중심"
tone: "친절하고 명확함"
catchphrase: "사용자가 진짜 원하는 게 뭔지 먼저 파악하자"
strengths:
  - "PRD 작성"
  - "요구사항 분석"
```

### 워커 봇 추가

`workers.yaml`에 항목을 추가하고 봇을 재시작합니다 — 코드 수정 불필요:

```yaml
workers:
  - name: my_new_bot
    token: "${MY_NEW_BOT_TOKEN}"
    engine: claude-code        # claude-code | codex | gemini-cli
    description: "신규 봇 역할 설명"
```

---

## 주요 명령어

```bash
# ── 봇 운영 ────────────────────────────────────────────────────────
bash scripts/start_all.sh                           # 전체 봇 시작
bash scripts/start_pm.sh                            # PM 봇만 시작 (테스트)
bash scripts/request_restart.sh --reason "이유"      # 안전한 봇 재기동 요청

# ── 테스트 ─────────────────────────────────────────────────────────
./.venv/bin/pytest -q                               # 전체 단위 테스트
./.venv/bin/pytest tests/e2e/ -q                    # E2E 회귀 테스트
./.venv/bin/pytest tests/test_pm_orchestrator.py -q # PM 봇 테스트만

# ── 코드 품질 ──────────────────────────────────────────────────────
./.venv/bin/ruff check .                            # 린트 검사
./.venv/bin/ruff check --fix .                      # 자동 수정

# ── 설정 검증 ──────────────────────────────────────────────────────
./.venv/bin/python tools/orchestration_cli.py validate-config
```

---

## 내장 스킬 목록

텔레그램에서 슬래시 명령어로 직접 사용 가능한 스킬 목록입니다.

| 스킬 | 트리거 키워드 | 설명 |
|------|--------------|------|
| **quality-gate** | `/quality-gate`, `품질검사`, `QA gate` | 코드 품질 검사 (ruff + pytest) — 머지/배포 전 사용 |
| **e2e-regression** | `/e2e-regression`, `e2e 테스트`, `회귀테스트` | 전체 E2E 회귀 테스트 — 배포 전 사용 |
| **gemini-image-gen** | `이미지 생성`, `generate image`, `시각화` | Gemini OAuth 기반 이미지 생성 (gemini-2.5-flash) |
| **bot-triage** | `/bot-triage`, `봇 장애`, `bot down` | 봇 장애 진단, 자동 복구, 인시던트 리포트 |
| **error-gotcha** | `gotcha 추가`, `에러 회고`, `add gotcha` | 에러 재발 방지 — 자동 gotcha 항목 추가 |
| **brainstorming-auto** | `자동 설계`, `auto design` | 인간 확인 없는 자율 설계 문서 생성 |
| **safe-modify** | `safe-modify`, `안전 수정` | 안전한 파일 수정 (프로덕션 데이터 보호) |
| **weekly-review** | `/weekly-review` | 주간 회고 자동 실행 + KR 업데이트 |
| **performance-eval** | `/performance-eval` | 월말 KR 달성률 기반 성과 평가 |
| **harness-audit** | `/harness-audit` | 전체 설정 감사 — 출시 전 필수 실행 |

전체 스킬 디렉토리: [`skills/`](skills/) | 상세 작성법: [CONTRIBUTING.md](CONTRIBUTING.md)

---

## CI/CD

GitHub Actions는 `ci.yml`, `release.yml`, `docker.yml` 세 단계로 운영합니다.
`main` 머지 전에는 `ci.yml`을 required status check로 묶고, 태그 릴리즈와 Docker 배포는 각각 별도 워크플로우로 분리합니다.

| 워크플로우 | 트리거 | 필요 Secret | 실행 내용 |
|-----------|--------|------------|-----------|
| `ci.yml` | PR, `push` to `main` | 선택: 엔진/OAuth secret | Python 3.10/3.11 매트릭스 E2E + 3엔진 호환성 테스트 + `validate-config` |
| `release.yml` | `push` tag `v*` | `PYPI_API_TOKEN` | 검증 재실행 후 `python -m build` 및 `twine upload`로 PyPI 릴리즈 |
| `docker.yml` | `push` to `main`, `push` tag `v*` | `DOCKER_USERNAME`, `DOCKER_PASSWORD` | 검증 재실행 후 Docker Buildx 빌드 및 Docker Hub 푸시 |

Fork PR 안전성을 위해 secret 기반 인증값은 조건부 step에서만 주입합니다.
Gemini CI는 필요 시 `GEMINI_OAUTH_CREDS` secret을 `~/.gemini/oauth_creds.json`으로 복원해 사용합니다.

---

## FAQ / 트러블슈팅

### macOS 권한 사전 승인 (Mac 미니/로컬 서버 운영 시 필수)

봇 실행 중 **"Python 3.x이 접근하는 것을 허용합니까?"** 다이얼로그가 반복 팝업되어 프로세스가 hang되는 경우, 아래 **1회** 조치로 영구 해결할 수 있습니다.

```
시스템 설정 → 개인 정보 보호 및 보안 → 전체 디스크 접근
→ "+" 버튼 → Terminal.app (또는 iTerm2) 추가 → 체크 활성화
```

> Claude Code로 봇을 실행하는 경우: Terminal 대신 Claude Code 바이너리(`which claude`로 경로 확인)도 동일하게 추가.

### 설치 문제

| 증상 | 해결 방법 |
|------|-----------|
| `AI 엔진이 하나도 감지되지 않았습니다` | 3엔진 중 하나 이상 설치 후 `bash scripts/setup.sh` 재실행 |
| `Python 3.10 이상을 찾을 수 없습니다` | `brew install python@3.12` (macOS) 또는 `pyenv install 3.12` |
| `import anthropic 실패` | `.venv/bin/pip install anthropic` 수동 실행 |
| `ModuleNotFoundError: telegram` | `.venv/bin/pip install python-telegram-bot` |
| setup.sh가 엔진을 못 찾음 | `which claude` / `which codex` / `which gemini` 로 경로 확인 후 `.env`에 직접 입력 |

### 엔진 연결 오류

| 엔진 | 증상 | 해결 방법 |
|------|------|-----------|
| **claude-code** | `claude: command not found` | `npm install -g @anthropic-ai/claude-code` 후 `claude auth login` |
| **claude-code** | `OAuth token expired` | `claude auth login` 재실행 |
| **codex** | `codex: command not found` | `npm install -g @openai/codex` 후 `codex login` |
| **codex** | `~/.codex/auth.json not found` | `codex login` 으로 OAuth 인증 완료 |
| **gemini-cli** | `gemini: command not found` | `npm install -g @google/gemini-cli` 후 `gemini auth login` |
| **gemini-cli** | `oauth_creds.json not found` | `gemini auth login` 으로 Google 계정 인증 |

### 봇 동작 이상

| 증상 | 해결 방법 |
|------|-----------|
| PM 봇이 응답하지 않음 | `bash scripts/request_restart.sh --reason "무응답"` 후 로그 확인 |
| 잘못된 부서로 라우팅 | `ENABLE_PM_ORCHESTRATOR=1` 확인, `orchestration.yaml` 라우팅 규칙 검토 |
| 스케줄이 실행되지 않음 | `ENABLE_PM_ORCHESTRATOR=1` 확인, `scheduler.py` 로그 확인 |
| 텔레그램 메시지 미수신 | `TELEGRAM_GROUP_CHAT_ID` 값 확인 (반드시 음수값) |

### 자주 묻는 질문

**Q. 엔진 하나만 설치해도 되나요?**
A. 네. 3개 엔진 중 하나만 설치해도 해당 엔진으로 모든 봇을 구동할 수 있습니다. 각 `bots/*.yaml` 파일에서 `engine:` 을 설치된 엔진으로 통일하면 됩니다.

**Q. 새 부서 봇을 추가하려면?**
A. `bots/` 디렉토리에 새 YAML 파일을 생성하고 `workers.yaml`에 항목을 추가합니다. 코드 수정이 필요 없습니다.

**Q. 봇 성격(캐릭터)을 바꾸려면?**
A. `bots/<봇이름>.yaml`의 `personality`, `tone`, `catchphrase` 필드를 수정하고 `bash scripts/request_restart.sh --reason "캐릭터 변경"`으로 재기동합니다.

**Q. API 비용이 걱정됩니다.**
A. `DAILY_COST_LIMIT_USD`, `PM_HOURLY_CALL_LIMIT` 환경변수로 비용 상한을 설정할 수 있습니다. 초과 시 서킷 브레이커가 자동으로 동작합니다.

**Q. 봇을 직접 종료/재시작해도 되나요?**
A. **금지**입니다. 직접 프로세스 종료 시 실행 중인 태스크 결과가 유실됩니다. 반드시 `bash scripts/request_restart.sh --reason "이유"` 를 사용하세요.

---

## 기여하기

기여를 환영합니다! 버그 신고, 기능 제안, PR 모두 가능합니다.

### 브랜치 전략

```
main          ─── 프로덕션 배포 기준 (태그 기반 릴리스)
  └── develop ─── 통합 브랜치 (PR 머지 대상)
        ├── feature/xxx   ── 신규 기능
        ├── fix/xxx       ── 버그 수정
        ├── docs/xxx      ── 문서 수정
        └── chore/xxx     ── 빌드/설정 변경
```

### PR 절차

```bash
# 1. 저장소 포크 후 클론
git clone https://github.com/<your-username>/aimesh.git
cd aimesh

# 2. develop에서 피처 브랜치 생성
git checkout develop && git pull origin develop
git checkout -b feature/my-feature

# 3. 코드 작성 + 테스트
./.venv/bin/pytest -q
./.venv/bin/ruff check .

# 4. 커밋 (Conventional Commits 규칙)
git commit -m "feat(gemini): OAuth 2.0 인증 지원 추가"

# 5. develop 브랜치 대상으로 PR 제출
```

**PR 제출 전 체크리스트**

```
[ ] develop 브랜치 기준으로 작성했다
[ ] .venv/bin/pytest -q 통과 확인
[ ] .venv/bin/ruff check . 경고 없음
[ ] 새 기능/버그 수정에 테스트 추가
[ ] CLAUDE.md / AGENTS.md / GEMINI.md 동시 업데이트 (해당 시)
[ ] .env 파일이나 시크릿이 커밋에 포함되지 않았다 확인
```

### 코드 스타일

- **Linter**: `ruff` (line length: 100)
- **Python**: 3.10+, 타입 힌트 필수
- **비동기**: asyncio 기반 (`async/await` 우선)
- **로깅**: `loguru` 사용 (`print` 금지)
- **시크릿**: 하드코딩 절대 금지, `os.environ` 사용

### 3개 컨텍스트 파일 동기화 (필수)

이 프로젝트는 3개 엔진을 지원합니다. 각 엔진은 자신의 컨텍스트 파일만 읽으므로
**항상 동시에 수정**해야 합니다:

```
CLAUDE.md   (기준 문서, 가장 상세)
AGENTS.md   (Codex CLI용)
GEMINI.md   (Gemini CLI용)
```

> 하나의 파일만 수정하면 다른 엔진이 최신 정보를 반영하지 못합니다.

### 새 스킬 추가 절차

**1. 스킬 디렉토리 생성**

```bash
mkdir -p skills/my-new-skill
```

**2. 스킬 정의 파일 작성** (`skills/my-new-skill/skill.md`)

```markdown
# my-new-skill

## 언제 사용하나
- 트리거 조건 설명 (예: "코드 리뷰 요청 시")

## 실행 절차
1. 단계 1
2. 단계 2
3. 단계 3

## 산출물
- 결과물 설명
```

**3. 설정 검증 통과 확인**

```bash
./.venv/bin/python tools/orchestration_cli.py validate-config
./.venv/bin/pytest -q
```

**4. 3개 컨텍스트 파일에 스킬 정보 추가 (운영 규칙 관련 시)**

새 스킬이 운영 규칙에 영향을 미친다면 `CLAUDE.md`, `AGENTS.md`, `GEMINI.md`를 동시에 업데이트합니다.

자세한 기여 가이드: [CONTRIBUTING.md](CONTRIBUTING.md)

---

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| 언어 | Python 3.10+ |
| 봇 프레임워크 | python-telegram-bot |
| 비동기 | asyncio |
| 의존성 관리 | uv + pyproject.toml |
| 린터 | ruff |
| 테스트 | pytest + pytest-asyncio |
| DB | SQLite (공유 컨텍스트) |
| 실행 엔진 | Claude Code CLI / Codex CLI / Gemini CLI |
| 패키징 | python-build + twine |
| 컨테이너 | Docker + Docker Compose (프로파일 지원) |
| CI/CD | GitHub Actions (ci.yml / release.yml / docker.yml) |

---

## 관련 프로젝트

MetaGPT, AutoGen, CrewAI, OpenAI Swarm에서 영감을 받았으나 핵심 차별점이 있습니다:

- **Telegram을 native 메시지 버스로 사용** — 별도 UI·대시보드 불필요
- **YAML 기반 동적 조직 구성** — 코드 수정 없이 부서·엔진 추가 가능
- **3엔진 동시 지원** — 태스크 특성에 맞게 엔진 자동 선택
- **봇 캐릭터 진화 시스템** — 각 봇이 개성을 가지고 성장
- **실사용 검증된 스킬 시스템** — 재사용 가능한 자동화 워크플로

---

## 라이선스

이 프로젝트는 **MIT 라이선스** 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

```
MIT License

Copyright (c) 2026 telegram-ai-org contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 기여자

이 프로젝트에 기여해 주신 모든 분들께 감사드립니다.

<!-- 기여자 목록은 GitHub Contributors 그래프를 기준으로 자동 갱신됩니다 -->
<!-- https://github.com/dragon1086/aimesh/graphs/contributors -->

기여 방법은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

---

*telegram-ai-org (aimesh) — AI 조직을 텔레그램에서 | 2026-03-25*
