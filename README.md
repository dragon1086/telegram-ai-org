# telegram-ai-org (aimesh)

> **"10분 안에 텔레그램에서 당신만의 AI 조직을 운영하세요"**

텔레그램 그룹 채팅방을 AI 조직의 오피스로 만드는 오픈소스 멀티봇 오케스트레이션 시스템.
PM 봇이 사용자 요청을 분석해 7개 전문 부서 봇에 자동 배분합니다.
**Claude Code / Codex / Gemini CLI** 3개 엔진을 모두 지원합니다.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Engine](https://img.shields.io/badge/engine-claude--code%20%7C%20codex%20%7C%20gemini--cli-orange.svg)](#3엔진-설치-가이드)
[![PyPI](https://img.shields.io/badge/PyPI-telegram--ai--org-blue.svg)](https://pypi.org/project/telegram-ai-org/)
[![CI](https://github.com/dragon1086/telegram-ai-org/actions/workflows/ci.yml/badge.svg)](https://github.com/dragon1086/telegram-ai-org/actions/workflows/ci.yml)
[![Release](https://github.com/dragon1086/telegram-ai-org/actions/workflows/release.yml/badge.svg)](https://github.com/dragon1086/telegram-ai-org/actions/workflows/release.yml)

---

## 목차

- [주요 기능](#주요-기능)
- [아키텍처](#아키텍처)
- [엔진 선택 매트릭스](#엔진-선택-매트릭스)
- [부서 구조](#부서-구조)
- [빠른 시작 (10분)](#빠른-시작-10분)
- [CI/CD](#cicd)
- [3엔진 설치 가이드](#3엔진-설치-가이드)
  - [Claude Code](#1-claude-code-기본-권장)
  - [Codex CLI](#2-codex-cli)
  - [Gemini CLI](#3-gemini-cli)
- [환경 변수 설정](#환경-변수-설정)
- [봇 구성](#봇-구성)
- [주요 명령어](#주요-명령어)
- [FAQ / 트러블슈팅](#faq--트러블슈팅)
- [기여하기](#기여하기)
- [라이선스](#라이선스)
- [기여자](#기여자)

---

## 주요 기능

| 기능 | 설명 |
|------|------|
| **PM 오케스트레이션** | 자연어 태스크를 PM 봇이 분석 → 적합한 부서 봇에 자동 배분 |
| **7개 전문 부서봇** | PM / 기획실 / 개발실 / 디자인실 / 성장실 / 운영실 / 리서치실 |
| **3엔진 호환** | Claude Code (복잡한 추론) / Codex (DevOps 자동화) / Gemini CLI (실시간 웹 검색) |
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
│                                                           │
│  ┌─────────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │  nl_classifier  │  │  pm_router  │  │  scheduler  │  │
│  │  (태스크 분류)   │→ │ (부서 라우팅)│→ │ (자연어 예약)│  │
│  └─────────────────┘  └─────────────┘  └─────────────┘  │
│                                                           │
│  ┌────────────────────────────────────────────────────┐  │
│  │           pm_orchestrator  (메인 루프)              │  │
│  │   GoalTracker · DiscussionProtocol                 │  │
│  │   AutoDispatch · SynthesisLoop                     │  │
│  └────────────────────────────────────────────────────┘  │
└────────────────────────┬─────────────────────────────────┘
                         │ 태스크 배분
           ┌─────────────┼──────────────────┐
           ▼             ▼                  ▼
 ┌─────────────┐  ┌─────────────┐  ┌──────────────┐
 │  기획실 봇   │  │  개발실 봇   │  │  성장실 봇    │
 │(claude-code)│  │(claude-code)│  │ (gemini-cli) │
 │  PRD 작성   │  │  코드 구현   │  │ 시장조사/검색 │
 └─────────────┘  └─────────────┘  └──────────────┘
 ┌─────────────┐  ┌─────────────┐  ┌──────────────┐
 │ 디자인실 봇  │  │  운영실 봇   │  │  리서치실 봇  │
 │(claude-code)│  │  (codex)    │  │ (gemini-cli) │
 │  UI/UX 설계 │  │  배포/인프라 │  │  경쟁사 분석  │
 └─────────────┘  └─────────────┘  └──────────────┘

엔진 러너 레이어 (tools/)
┌──────────────────┬──────────────────┬──────────────────┐
│  ClaudeCodeRunner │  CodexRunner     │  GeminiCLIRunner  │
│  복잡한 추론      │  CLI 자동화       │  실시간 웹 검색   │
│  PRD/코드/설계   │  DevOps 스크립트  │  시장·경쟁사 조사 │
└──────────────────┴──────────────────┴──────────────────┘
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
│   ├── aiorg_engineering_bot.yaml   #   개발실 — codex
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
├── skills/                          # 재사용 가능한 작업 스킬
│   ├── quality-gate/
│   ├── e2e-regression/
│   ├── gemini-image-gen/
│   ├── bot-triage/
│   └── safe-modify/
│
├── scripts/                         # 운영 스크립트
│   ├── setup.sh                     # 원클릭 초기 설치
│   ├── start_all.sh                 # 전체 봇 시작
│   ├── watchdog.sh                  # 프로세스 감시/자동 재기동
│   └── request_restart.sh           # 안전한 재기동 요청
│
├── tests/                           # pytest 테스트
│   ├── e2e/                         # E2E 회귀 테스트
│   │   ├── test_engine_compat_e2e.py
│   │   └── test_pm_dispatch_e2e.py
│   └── ...
│
├── CLAUDE.md                        # Claude Code 운영 지침 (기준 문서)
├── AGENTS.md                        # Codex CLI 운영 지침
├── GEMINI.md                        # Gemini CLI 운영 지침
└── .env.example                     # 환경변수 템플릿
```

---

## 엔진 선택 매트릭스

각 엔진의 특성에 따라 부서별 최적 엔진이 배정됩니다. `bots/*.yaml`의 `engine:` 필드로 변경 가능합니다.

| 엔진 | 적합 부서 | 주요 특징 | 필요 인증 |
|------|-----------|-----------|-----------|
| **claude-code** | PM / 기획실 / 디자인실 | 복잡한 멀티스텝 추론, 장문 컨텍스트 처리, 구조화된 문서 생성 | `claude auth login` (OAuth) |
| **codex** | 개발실 / 운영실 | 경량 CLI 자동화, DevOps 스크립트 특화, 인프라 명령 실행 | `codex auth login` (OAuth) |
| **gemini-cli** | 성장실 / 리서치실 | Google 검색 내장, 실시간 웹 데이터 조회, 대규모 컨텍스트 | `gemini auth login` (OAuth) |

> **API 키 없이 사용 가능**: 3개 엔진 모두 OAuth 2.0 인증을 지원하므로 별도 API 키 없이 운용할 수 있습니다.
> 태스크 신뢰도 스코어링 기능 사용 시에만 `GEMINI_API_KEY` 또는 `ANTHROPIC_API_KEY`가 선택적으로 필요합니다.

| 비교 항목 | claude-code | codex | gemini-cli |
|-----------|-------------|-------|------------|
| 설치 명령 | `npm i -g @anthropic-ai/claude-code` | `npm i -g @openai/codex` | `npm i -g @google/gemini-cli` |
| 인증 파일 | OAuth 세션 | `~/.codex/auth.json` | `~/.gemini/oauth_creds.json` |
| 웹 검색 | 없음 | 없음 | **내장** (Google Search) |
| 최적 태스크 | PRD·코드·설계 | 배포·인프라 CLI | 시장조사·경쟁사 분석 |
| 컨텍스트 길이 | 200K 토큰 | 표준 | 1M 토큰 |

---

## 부서 구조

telegram-ai-org는 7개 전문 부서로 구성됩니다. 각 부서는 독립 봇으로 운영되며, PM 봇이 태스크를 자동 배분합니다.

### PM (오케스트레이터)

| 항목 | 내용 |
|------|------|
| **봇 ID** | `aiorg_pm_bot` |
| **엔진** | claude-code |
| **역할** | 사용자 요청 분류 → 부서 배분 → 결과 합성 → 스케줄 관리 |
| **보유 스킬** | `pm-dispatch`, `discussion-protocol`, `synthesis-loop`, `goal-tracker` |

### 기획실 (Product)

| 항목 | 내용 |
|------|------|
| **봇 ID** | `aiorg_product_bot` |
| **엔진** | claude-code |
| **역할** | PRD 작성, 요구사항 분석, 기능 스펙 정의 |
| **보유 스킬** | `prd-writer`, `requirement-analysis`, `user-story-gen` |

### 개발실 (Engineering)

| 항목 | 내용 |
|------|------|
| **봇 ID** | `aiorg_engineering_bot` |
| **엔진** | claude-code |
| **역할** | 코드 구현, API 개발, 버그 수정 (Python 백엔드 / TypeScript 웹 선호) |
| **보유 스킬** | `quality-gate`, `engineering-review`, `safe-modify`, `e2e-regression`, `bot-triage` |

### 디자인실 (Design)

| 항목 | 내용 |
|------|------|
| **봇 ID** | `aiorg_design_bot` |
| **엔진** | claude-code |
| **역할** | UI/UX 설계, 와이어프레임, 프로토타입, 비주얼 가이드라인 |
| **보유 스킬** | `wireframe-gen`, `design-review`, `gemini-image-gen` |

### 성장실 (Growth)

| 항목 | 내용 |
|------|------|
| **봇 ID** | `aiorg_growth_bot` |
| **엔진** | gemini-cli |
| **역할** | 마케팅 전략, 지표 분석, 성장 실험, 실시간 트렌드 조사 |
| **보유 스킬** | `growth-analysis`, `metric-report`, `ab-test-design` |

### 운영실 (Ops)

| 항목 | 내용 |
|------|------|
| **봇 ID** | `aiorg_ops_bot` |
| **엔진** | codex |
| **역할** | 배포 자동화, 인프라 관리, 모니터링, CI/CD |
| **보유 스킬** | `deploy-check`, `infra-audit`, `log-analysis` |

### 리서치실 (Research)

| 항목 | 내용 |
|------|------|
| **봇 ID** | `aiorg_research_bot` |
| **엔진** | gemini-cli |
| **역할** | 시장조사, 경쟁사 분석, 논문·문서 요약, 레퍼런스 수집 |
| **보유 스킬** | `market-research`, `competitor-analysis`, `doc-summary` |

---

## 빠른 시작 (10분)

### 사전 준비

- Python 3.11 이상
- Node.js 18+ (Gemini CLI 또는 Codex CLI 사용 시)
- Telegram 계정 + [@BotFather](https://t.me/BotFather)에서 봇 토큰 발급
- 아래 3개 엔진 중 **1개 이상** 설치 (→ [3엔진 설치 가이드](#3엔진-설치-가이드))

### 방법 1: 원클릭 설치 (권장)

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

`setup.sh`가 자동으로 수행하는 작업:

```
▶ Step 1/5: AI 엔진 자동 감지
✅ codex 감지됨:  /opt/homebrew/bin/codex
✅ gemini 감지됨: /opt/homebrew/bin/gemini
⚠️  claude CLI 미감지 (설치: https://claude.ai/code)
감지된 엔진: codex gemini (총 2개)

▶ Step 2/5: Python 환경 확인 (3.13→3.12→3.11→3.10 순 자동 선택)
✅ Python 3.12.x — 요구사항 충족

▶ Step 3/5: Python 의존성 설치
✅ 의존성 설치 완료

▶ Step 4/5: 환경 변수 파일 설정
✅ .env 파일 생성 완료
ℹ️  GEMINI_CLI_PATH → /opt/homebrew/bin/gemini (자동 설정)
ℹ️  CODEX_CLI_PATH  → /opt/homebrew/bin/codex  (자동 설정)

▶ Step 5/5: 초기화 검증
✅ import anthropic   ✅ import pydantic
✅ import telegram    ✅ import loguru
검증 완료: 10/10 항목 통과 — 모두 정상
```

### 방법 2: PyPI 설치

```bash
pip install telegram-ai-org
```

### 방법 3: 개발용 설치 (editable 모드)

```bash
git clone https://github.com/dragon1086/aimesh.git
cd aimesh
pip install -e .           # 기본 설치
pip install -e ".[dev]"    # 개발 도구 포함
```

---

## CI/CD

GitHub Actions는 배포 전 테스트 원칙에 맞춰 `ci.yml`과 `release.yml` 두 단계로 운영합니다. `main` 머지 전에는 `ci.yml`을 required status check로 묶고, `release.yml`은 `verify` → `publish-pypi` → `docker-push` 순서로 직렬 실행해 배포를 단계적으로 진행합니다.

| 워크플로우 | 트리거 | 필요 secret | 실행 내용 |
|------|------|------|------|
| `ci.yml` | `pull_request` | 테스트용 API key 또는 OAuth secret | `ruff check telegram_ai_org` → `validate-config` → `pytest tests/e2e/ -q` |
| `release.yml` | `push` to `main` | 테스트용 API key 또는 OAuth secret, `PYPI_TOKEN`, `DOCKER_USERNAME`, `DOCKER_TOKEN` | 검증 재실행 후 PyPI 배포, Docker Hub 이미지 `latest` + commit SHA 푸시 |

Gemini CI는 필요 시 `GEMINI_OAUTH_CREDS` secret을 `~/.gemini/oauth_creds.json`으로 복원해 사용합니다. 자세한 운영 절차는 `docs/CI_CD_SETUP.md`를 기준으로 관리합니다.

### 텔레그램에서 확인

설치 완료 후 텔레그램 그룹에서 PM 봇에게 메시지를 보내세요:

```
안녕, 오늘 마케팅 전략 분석 부탁해
```

PM 봇이 성장실 봇에게 태스크를 자동 배분하고 결과를 전달합니다.

---

## Docker Compose 실행

Docker Compose는 **공통 시크릿은 `.env`에서**, **엔진별 런타임 변수는 `docker-compose.yml`의 `environment` 블록에서** 주입합니다.
서비스는 조직별로 분리되어 있고, 이미지 빌드는 엔진별(`claude` / `codex` / `gemini`)로 나뉩니다.

### 1. 환경 변수 준비

```bash
cp .env.example .env
```

`.env`에는 최소한 아래 값을 채워야 합니다.

```bash
TELEGRAM_BOT_TOKEN=
TELEGRAM_GROUP_CHAT_ID=
BOT_TOKEN_AIORG_PRODUCT_BOT=
BOT_TOKEN_AIORG_ENGINEERING_BOT=
BOT_TOKEN_AIORG_DESIGN_BOT=
BOT_TOKEN_AIORG_GROWTH_BOT=
BOT_TOKEN_AIORG_OPS_BOT=
BOT_TOKEN_AIORG_RESEARCH_BOT=
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=
```

### 2. 이미지 빌드

```bash
# 전체 엔진 이미지 빌드
docker compose build

# 또는 엔진별 서비스만 선택 빌드
docker compose build aiorg-pm aiorg-product-bot aiorg-design-bot
docker compose build aiorg-engineering-bot aiorg-ops-bot
docker compose build aiorg-growth-bot aiorg-research-bot
```

### 3. 컨테이너 실행

```bash
# Claude 계열(PM/기획/디자인)
docker compose --profile claude up -d

# Codex 계열(개발/운영)
docker compose --profile codex up -d

# Gemini 계열(성장/리서치)
docker compose --profile gemini up -d

# 전체 조직 동시 실행
docker compose --profile claude --profile codex --profile gemini up -d
```

### 4. 로그와 상태 확인

```bash
docker compose ps
docker compose logs -f aiorg-pm
docker compose logs -f aiorg-ops-bot
docker compose logs -f aiorg-research-bot
```

엔진별 컨테이너에는 다음 값이 자동 주입됩니다.

| 프로파일 | 서비스 | 자동 주입 값 |
|------|------|------|
| `claude` | `aiorg-pm`, `aiorg-product-bot`, `aiorg-design-bot` | `ENGINE_TYPE=claude-code`, `CLAUDE_CLI_PATH=/opt/cli/bin/claude` |
| `codex` | `aiorg-engineering-bot`, `aiorg-ops-bot` | `ENGINE_TYPE=codex`, `CODEX_CLI_PATH=/opt/cli/bin/codex` |
| `gemini` | `aiorg-growth-bot`, `aiorg-research-bot` | `ENGINE_TYPE=gemini-cli`, `GEMINI_CLI_PATH=/opt/cli/bin/gemini`, `GEMINI_CLI_MODEL=gemini-2.5-flash` |

공통 볼륨 마운트: `./logs`, `./data`, `./reports`, `./tasks`, `./skills`(read-only — 스킬 파일 공유)

---

## 3엔진 설치 가이드

각 봇은 `bots/*.yaml`의 `engine:` 필드로 실행 엔진을 선택합니다.
시스템 전체에 하나 이상의 엔진만 설치해도 동작합니다.

### 엔진별 권장 역할 분담

| 봇 | 엔진 | 선택 이유 |
|----|------|-----------|
| PM / 기획실 / 디자인실 | **claude-code** | 복잡한 멀티스텝 추론, 긴 컨텍스트, 구조화된 문서 |
| 개발실 / 운영실 | **codex** | 경량 CLI 특화, DevOps 스크립트 자동화 |
| 성장실 / 리서치실 | **gemini-cli** | Google 검색 내장, 실시간 시장 데이터 조회 |

---

### 1. Claude Code (기본 권장)

PM봇·기획실·디자인실에서 사용. 복잡한 멀티스텝 추론과 장문 컨텍스트에 최적.

**설치**

```bash
npm install -g @anthropic-ai/claude-code
claude --version   # 설치 확인
```

**인증**

```bash
claude auth login   # Anthropic 계정으로 OAuth 로그인
```

**환경 변수**

```bash
# .env
CLAUDE_CLI_PATH=              # which claude 로 경로 확인 (setup.sh가 자동 감지)
CLAUDE_CODE_OAUTH_TOKEN=      # 선택: claude auth token 으로 확인
ANTHROPIC_API_KEY=            # LLM 신뢰도 스코어링용 (선택)
```

**봇 YAML 설정**

```yaml
# bots/aiorg_engineering_bot.yaml
engine: claude-code
```

**실행 확인**

```bash
claude -p "hello world" --output-format text
```

---

### 2. Codex CLI

개발실(aiorg_engineering_bot)·운영실(aiorg_ops_bot)에서 사용. 경량 CLI 특화, DevOps 스크립트 및 인프라 자동화에 최적.

**설치**

```bash
npm install -g @openai/codex
codex --version   # 설치 확인
```

**인증**

```bash
codex auth login   # OpenAI 계정으로 OAuth 로그인
# 인증 정보 저장: ~/.codex/auth.json
```

> **참고**: Codex CLI는 OAuth 2.0 방식을 사용합니다. `OPENAI_API_KEY` 환경변수는 불필요합니다.

**환경 변수**

```bash
# .env
CODEX_CLI_PATH=   # which codex 로 경로 확인 (setup.sh가 자동 감지)
# OPENAI_API_KEY 불필요 — OAuth 인증 사용 (~/.codex/auth.json)
```

**봇 YAML 설정**

```yaml
# bots/aiorg_ops_bot.yaml
engine: codex
```

**실행 확인**

```bash
codex "list files in current directory"
```

---

### 3. Gemini CLI

성장실(aiorg_growth_bot)·리서치실(aiorg_research_bot)에서 사용.
Google 검색 내장으로 실시간 웹 데이터 조회 및 대규모 컨텍스트 처리에 최적.

**설치**

```bash
npm install -g @google/gemini-cli   # Node.js 18+ 필요
gemini --version                    # 설치 확인
```

**인증 (OAuth 2.0 — API 키 불필요)**

```bash
gemini auth login   # Google 계정으로 OAuth 로그인
# 인증 정보 저장: ~/.gemini/oauth_creds.json
ls ~/.gemini/oauth_creds.json   # 인증 확인
```

**환경 변수**

```bash
# .env
GEMINI_CLI_PATH=                     # which gemini 로 확인 (setup.sh가 자동 감지)
GEMINI_CLI_DEFAULT_TIMEOUT_SEC=1800  # 긴 리서치 태스크 대응 (기본: 1800)
GEMINI_API_KEY=                      # API 직접 호출 시만 필요 (LLM 스코어링용, 선택)
```

**봇 YAML 설정**

```yaml
# bots/aiorg_growth_bot.yaml
engine: gemini-cli

# bots/aiorg_research_bot.yaml
engine: gemini-cli
```

**실행 확인**

```bash
gemini -p "현재 날짜를 알려줘"
```

**Gemini CLI 특이사항**

- Google 검색 내장으로 실시간 웹 정보 조회 가능 (다른 엔진과 차별점)
- 사용 모델: `gemini-2.5-flash` (2026-03 기준 최신 stable GA)
- `gemini-2.0-flash`는 2026-06-01 서비스 종료 예정이므로 사용 금지

---

## 환경 변수 설정

`.env.example`을 복사해 `.env`를 만들고 값을 채웁니다.

```bash
cp .env.example .env
nano .env
```

> **보안**: `.env` 파일에는 비밀 토큰이 포함됩니다. `.gitignore`에 이미 포함되어 있으니 절대 커밋하지 마세요.

### 필수 설정

```bash
# ── Telegram ──────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=                  # PM 봇 토큰 (@BotFather에서 발급)
TELEGRAM_GROUP_CHAT_ID=              # 그룹 chat_id (음수값, 예: -5203707291)

# ── 부서 봇 토큰 (사용하는 봇만 설정) ─────────────────────────────
BOT_TOKEN_AIORG_PRODUCT_BOT=         # 기획실
BOT_TOKEN_AIORG_ENGINEERING_BOT=     # 개발실
BOT_TOKEN_AIORG_DESIGN_BOT=          # 디자인실
BOT_TOKEN_AIORG_GROWTH_BOT=          # 성장실
BOT_TOKEN_AIORG_OPS_BOT=             # 운영실
BOT_TOKEN_AIORG_RESEARCH_BOT=        # 리서치실
```

### 엔진 경로 (사용하는 엔진만 설정, setup.sh가 자동 감지)

```bash
CLAUDE_CLI_PATH=                     # Claude Code CLI 경로
CODEX_CLI_PATH=                      # Codex CLI 경로
GEMINI_CLI_PATH=                     # Gemini CLI 경로
```

### LLM 스코어링용 API 키 (태스크 신뢰도 판단, 선택)

```bash
GEMINI_API_KEY=                      # Gemini API (권장)
ANTHROPIC_API_KEY=                   # Anthropic REST API (대체)
# 우선순위: GEMINI → ANTHROPIC → DEEPSEEK → keyword fallback
```

### Feature Flags

```bash
ENABLE_PM_ORCHESTRATOR=1             # PM 중앙 통제 모드
ENABLE_DISCUSSION_PROTOCOL=1         # 부서간 토론 프로토콜
ENABLE_AUTO_DISPATCH=1               # 태스크 의존성 자동 디스패치
ENABLE_GOAL_TRACKER=1                # PM 목표 달성 루프 (권장)
```

전체 환경 변수 레퍼런스: [`.env.example`](.env.example)

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

### 기본 부서 구성

| 부서 | 봇 ID | 엔진 | 역할 |
|------|-------|------|------|
| PM | aiorg_pm_bot | claude-code | 오케스트레이션/조율 |
| 기획실 | aiorg_product_bot | claude-code | PRD/요구사항 분석 |
| 개발실 | aiorg_engineering_bot | codex | 코드 구현/버그 수정 |
| 디자인실 | aiorg_design_bot | claude-code | UI/UX 디자인 |
| 성장실 | aiorg_growth_bot | gemini-cli | 마케팅/지표 분석 |
| 운영실 | aiorg_ops_bot | codex | 배포/인프라 |
| 리서치실 | aiorg_research_bot | gemini-cli | 시장조사/경쟁사 분석 |

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

### 내장 스킬 (Telegram에서 슬래시 명령으로 사용)

| 스킬 | 설명 |
|------|------|
| `/quality-gate` | 코드 품질 검사 (ruff + pytest) — 머지 전 사용 |
| `/e2e-regression` | 전체 E2E 회귀 테스트 — 배포 전 사용 |
| `/gemini-image-gen` | Gemini OAuth 기반 이미지 생성 |
| `/bot-triage` | 봇 장애 진단 및 자동 복구 |

---

## FAQ / 트러블슈팅

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

**Q. Docker로 실행할 수 있나요?**
A. 네. `docker-compose.yml`이 포함되어 있습니다. `docker compose up` 으로 시작하세요.

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
- **Python**: 3.11+, 타입 힌트 필수
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

자세한 기여 가이드: [CONTRIBUTING.md](CONTRIBUTING.md)

---

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| 언어 | Python 3.11+ |
| 봇 프레임워크 | python-telegram-bot |
| 비동기 | asyncio |
| 의존성 관리 | uv + pyproject.toml |
| 린터 | ruff |
| 테스트 | pytest + pytest-asyncio |
| DB | SQLite (공유 컨텍스트) |
| 실행 엔진 | Claude Code CLI / Codex CLI / Gemini CLI |

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
