# telegram-ai-org

> **"10분 안에 텔레그램에서 당신만의 AI 조직을 운영하세요"**

텔레그램 그룹 채팅방을 AI 조직의 오피스로 만드는 오픈소스 멀티봇 오케스트레이션 시스템.
PM 봇이 사용자 요청을 분석해 7개 전문 부서 봇에 자동 배분합니다.
**Claude Code / Codex / Gemini CLI** 3개 엔진을 모두 지원합니다.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/)
[![Engine](https://img.shields.io/badge/engine-claude--code%20%7C%20codex%20%7C%20gemini--cli-orange.svg)](#3엔진-설치-가이드)

---

## 목차

- [주요 기능](#주요-기능)
- [아키텍처](#아키텍처)
- [빠른 시작 (10분)](#빠른-시작-10분)
- [3엔진 설치 가이드](#3엔진-설치-가이드)
  - [Claude Code](#1-claude-code-기본-권장)
  - [Codex CLI](#2-codex-cli)
  - [Gemini CLI](#3-gemini-cli)
- [환경 변수 설정](#환경-변수-설정)
- [봇 구성](#봇-구성)
- [주요 명령어](#주요-명령어)
- [기여하기](#기여하기)
- [라이선스](#라이선스)

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
 │(claude-code)│  │  (codex)    │  │ (gemini-cli) │
 │  PRD 작성   │  │  코드 구현   │  │ 시장조사/검색 │
 └─────────────┘  └─────────────┘  └──────────────┘
 ┌─────────────┐  ┌─────────────┐  ┌──────────────┐
 │ 디자인실 봇  │  │  운영실 봇   │  │  리서치실 봇  │
 │(claude-code)│  │  (codex)    │  │ (gemini-cli) │
 │  UI/UX 설계 │  │  배포/인프라 │  │  경쟁사 분석  │
 └─────────────┘  └─────────────┘  └──────────────┘

공통 인프라 레이어
┌──────────────────────────────────────────────────────────┐
│  telegram_relay  │  lesson_memory   │  skills/           │
│  bot_character   │  shoutout_system │  context_window    │
│  collaboration_tracker             │  user_schedule_store│
└──────────────────────────────────────────────────────────┘

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
│   ├── nl_schedule_parser.py        # 자연어 스케줄 파싱
│   ├── bot_character_evolution.py   # 봇 캐릭터 진화
│   ├── shoutout_system.py           # 팀워크·칭찬 시스템
│   ├── lesson_memory.py             # 교훈 메모리
│   ├── collaboration_tracker.py     # 협업 추적
│   ├── agent_persona_memory.py      # 봇 페르소나 메모리
│   └── context_window.py            # PM 대화 히스토리 컨텍스트
│
├── tools/                           # 엔진 러너 및 CLI 도구
│   ├── base_runner.py               # 러너 추상 기반 클래스
│   ├── claude_code_runner.py        # Claude Code CLI 래퍼
│   ├── codex_runner.py              # Codex CLI 래퍼
│   ├── gemini_cli_runner.py         # Gemini CLI OAuth 러너
│   └── orchestration_cli.py         # 설정 검증 CLI
│
├── skills/                          # 재사용 가능한 작업 스킬
│   ├── pm-task-dispatch/
│   ├── quality-gate/
│   ├── e2e-regression/
│   ├── gemini-image-gen/
│   ├── bot-triage/
│   ├── brainstorming-auto/
│   └── safe-modify/
│
├── scripts/                         # 운영 스크립트
│   ├── setup.sh                     # 초기 설정
│   ├── start_all.sh                 # 전체 봇 시작
│   ├── start_pm.sh                  # PM 봇만 시작
│   ├── watchdog.sh                  # 프로세스 감시/자동 재기동
│   └── request_restart.sh           # 안전한 재기동 요청
│
├── tests/                           # pytest 테스트
│   ├── e2e/                         # E2E 회귀 테스트
│   │   ├── test_engine_compat_e2e.py
│   │   └── test_pm_dispatch_e2e.py
│   └── ...
│
├── docs/                            # 문서
│   ├── OPENSOURCE_PLAN.md           # 오픈소스화 마스터 플랜
│   ├── SKILLS_MCP_GUIDE.md          # 스킬/MCP 표준 가이드
│   └── REFACTORING_PLAN.md          # 리팩토링 계획
│
├── CLAUDE.md                        # Claude Code 운영 지침 (기준 문서)
├── AGENTS.md                        # Codex CLI 운영 지침
├── GEMINI.md                        # Gemini CLI 운영 지침
└── .env.example                     # 환경변수 템플릿
```

---

## 빠른 시작 (10분)

### 사전 준비

- Python 3.11 이상
- Node.js 18+ (Gemini CLI 사용 시)
- Telegram 계정 + [@BotFather](https://t.me/BotFather)에서 봇 토큰 발급
- 아래 3개 엔진 중 **1개 이상** 설치 (→ [3엔진 설치 가이드](#3엔진-설치-가이드))

### 1단계: 저장소 클론 및 의존성 설치

```bash
git clone https://github.com/your-org/telegram-ai-org.git
cd telegram-ai-org
bash scripts/setup.sh
```

`setup.sh`가 자동으로 수행하는 작업:
- Python 가상환경(`.venv`) 생성
- 의존성 설치 (`uv` 또는 `pip` 자동 감지)
- `.env` 파일 초기 생성 (`.env.example` 복사)
- 컨텍스트 DB 디렉토리 생성 (`~/.ai-org/workspace`)

### 2단계: 환경 변수 설정

```bash
nano .env   # 또는 선호하는 에디터로 .env 파일 편집
```

최소 필수 설정:

```bash
PM_BOT_TOKEN=<@BotFather에서 발급받은 PM 봇 토큰>
TELEGRAM_GROUP_CHAT_ID=<그룹 chat_id (음수값, 예: -5203707291)>
CLAUDE_CLI_PATH=/path/to/claude   # which claude 로 확인
```

→ 전체 환경 변수 레퍼런스: [환경 변수 설정](#환경-변수-설정)

### 3단계: 봇 시작

```bash
# 전체 봇 시작
bash scripts/start_all.sh

# 테스트용: PM 봇만 시작
bash scripts/start_pm.sh
```

### 4단계: 텔레그램에서 확인

텔레그램 그룹에서 PM 봇에게 메시지를 보내세요:

```
안녕, 오늘 마케팅 전략 분석 부탁해
```

PM 봇이 성장실 봇에게 태스크를 자동 배분하고 결과를 전달합니다.

---

## 3엔진 설치 가이드

각 봇은 `bots/*.yaml`의 `engine:` 필드로 실행 엔진을 선택합니다.
시스템 전체에 하나 이상의 엔진만 설치해도 동작합니다.

### 엔진별 권장 역할 분담

| 봇 | 엔진 | 선택 이유 |
|----|------|-----------|
| PM / 기획실 / 디자인실 | **claude-code** | 복잡한 멀티스텝 추론, 긴 컨텍스트, 구조화된 문서 |
| 개발실 | **codex** 또는 **claude-code** | 코드 구현·디버깅·테스트 작성 |
| 운영실 | **codex** | 경량 CLI 특화, DevOps 스크립트 자동화 |
| 성장실 / 리서치실 | **gemini-cli** | Google 검색 내장, 실시간 시장 데이터 조회 |

---

### 1. Claude Code (기본 권장)

PM봇·기획실·디자인실에서 사용. 복잡한 멀티스텝 추론과 장문 컨텍스트에 최적.

**설치**

```bash
# npm으로 설치
npm install -g @anthropic-ai/claude-code

# 설치 확인
claude --version
```

**인증**

```bash
# Anthropic 계정으로 OAuth 로그인
claude auth login
```

**환경 변수**

```bash
# .env
CLAUDE_CLI_PATH=/path/to/claude        # which claude 로 경로 확인
CLAUDE_CODE_OAUTH_TOKEN=               # 선택: claude auth token 으로 확인
ANTHROPIC_API_KEY=                     # LLM 신뢰도 스코어링용 (선택)
```

**봇 YAML 설정**

```yaml
# bots/aiorg_product_bot.yaml
engine: claude-code
```

**실행 확인**

```bash
claude -p "hello world" --output-format text
```

---

### 2. Codex CLI

운영실(aiorg_ops_bot)·개발실에서 사용. 경량 CLI 특화, DevOps 스크립트 및 인프라 자동화에 최적.

**설치**

```bash
# npm으로 설치
npm install -g @openai/codex

# 설치 확인
codex --version
```

**인증**

```bash
# OpenAI 계정으로 OAuth 로그인 (API 키 불필요)
codex auth login
# 인증 정보 저장 위치: ~/.codex/auth.json
```

> **참고**: Codex CLI는 OAuth 2.0 방식을 사용합니다. `OPENAI_API_KEY` 환경변수는 불필요합니다.

**환경 변수**

```bash
# .env
CODEX_CLI_PATH=/path/to/codex          # which codex 로 경로 확인
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
# npm으로 설치 (Node.js 18+ 필요)
npm install -g @google/gemini-cli

# 설치 확인
gemini --version
```

**인증 (OAuth 2.0 방식 — API 키 불필요)**

```bash
# Google 계정으로 OAuth 로그인
gemini auth login
# 인증 정보 저장 위치: ~/.gemini/oauth_creds.json
ls ~/.gemini/oauth_creds.json   # 인증 확인
```

**환경 변수**

```bash
# .env
GEMINI_CLI_PATH=/path/to/gemini              # which gemini 로 경로 확인
GEMINI_CLI_DEFAULT_TIMEOUT_SEC=1800          # 긴 리서치 태스크 대응 (기본: 1800)
GEMINI_API_KEY=                              # API 직접 호출 시만 필요 (LLM 스코어링용)
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
- `GEMINI_CLI_DEFAULT_TIMEOUT_SEC` 값을 늘려 장시간 리서치 태스크 대응 가능
- 사용 모델: `gemini-2.5-flash` (2026-03 기준 최신 stable GA)
- `gemini-2.0-flash`는 2026-06-01 서비스 종료 예정이므로 사용 금지

**Python 런너 직접 사용**

```python
from tools.gemini_cli_runner import GeminiCLIRunner

runner = GeminiCLIRunner()
result = await runner.run("최신 AI 시장 트렌드를 분석해줘")
```

---

## 환경 변수 설정

`.env.example`을 복사해서 `.env`를 만들고 값을 채웁니다.

```bash
cp .env.example .env
```

> **보안**: `.env` 파일에는 비밀 토큰이 포함됩니다. `.gitignore`에 이미 포함되어 있으므로 절대 커밋하지 마세요.

### 필수 설정

```bash
# ── Telegram ──────────────────────────────────────────────────────
PM_BOT_TOKEN=                        # PM 봇 토큰 (@BotFather에서 발급)
TELEGRAM_GROUP_CHAT_ID=              # 그룹 chat_id (음수값, 예: -5203707291)

# ── 부서 봇 토큰 (사용하는 봇만 설정) ─────────────────────────────
BOT_TOKEN_AIORG_PRODUCT_BOT=         # 기획실
BOT_TOKEN_AIORG_ENGINEERING_BOT=     # 개발실
BOT_TOKEN_AIORG_DESIGN_BOT=          # 디자인실
BOT_TOKEN_AIORG_GROWTH_BOT=          # 성장실
BOT_TOKEN_AIORG_OPS_BOT=             # 운영실
```

### 엔진 경로 (사용하는 엔진만 설정)

```bash
CLAUDE_CLI_PATH=/path/to/claude      # Claude Code CLI 경로
CODEX_CLI_PATH=/path/to/codex        # Codex CLI 경로
GEMINI_CLI_PATH=/path/to/gemini      # Gemini CLI 경로
GEMINI_CLI_DEFAULT_TIMEOUT_SEC=1800  # Gemini 타임아웃 (초, 기본: 1800)
```

### LLM 스코어링용 API 키 (태스크 신뢰도 판단, 선택)

```bash
GEMINI_API_KEY=                      # Gemini API (권장)
ANTHROPIC_API_KEY=                   # Anthropic REST API (대체)
DEEPSEEK_API_KEY=                    # DeepSeek (대체)
# 우선순위: GEMINI → ANTHROPIC → DEEPSEEK → keyword fallback
```

### Feature Flags

```bash
ENABLE_PM_ORCHESTRATOR=0             # 1: PM 중앙 통제 모드 활성화
ENABLE_DISCUSSION_PROTOCOL=0         # 1: 부서간 토론 프로토콜 활성화
ENABLE_AUTO_DISPATCH=0               # 1: 태스크 의존성 자동 디스패치
ENABLE_CROSS_VERIFICATION=0          # 1: 엔진 간 교차 검증
ENABLE_GOAL_TRACKER=1                # 1: PM 목표 달성 루프 (권장)
```

### PM 컨텍스트 창 튜닝

```bash
MAX_HISTORY_MESSAGES=10              # 히스토리 최대 메시지 수 (기본: 10)
MAX_HISTORY_TOKENS=2000              # 히스토리 컨텍스트 토큰 한도 (기본: 2000)
# 복잡한 멀티턴 태스크: MAX_HISTORY_MESSAGES=20, MAX_HISTORY_TOKENS=4000
```

### 자율 에이전트 모드

```bash
AUTONOMOUS_MODE=false                # true: 사용자 입력 없이 자동 진행
```

---

## 봇 구성

각 봇은 `bots/*.yaml` 파일로 정의됩니다. 아래 구조를 참고해 새 봇을 추가할 수 있습니다.

### 봇 YAML 구조

```yaml
schema_version: 2
organization_ref: aiorg_product_bot   # 봇 고유 ID
username: aiorg_product_bot           # Telegram 사용자명
token_env: BOT_TOKEN_AIORG_PRODUCT_BOT # .env에서 토큰 읽는 환경변수 키
chat_id: -5203707291                   # 그룹 chat_id
engine: claude-code                    # 실행 엔진 (claude-code / codex / gemini-cli)
dept_name: 기획실
role: PRD/요구사항 분석/기획
is_pm: false                           # true: PM 봇, false: 워커 봇

# 봇 성격 (캐릭터 시스템)
personality: "논리적이고 사용자 중심"
tone: "친절하고 명확함"
catchphrase: "사용자가 진짜 원하는 게 뭔지 먼저 파악하자"
strengths:
  - "PRD 작성"
  - "요구사항 분석"

active_hours:          # 활성 시간대
  start: 9
  end: 22
  timezone: "Asia/Seoul"
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
| `/brainstorming-auto` | 사용자 입력 없는 자율 모드 브레인스토밍 |

---

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| 언어 | Python 3.11+ |
| 봇 프레임워크 | python-telegram-bot |
| 비동기 | asyncio |
| 스코어링 | Gemini API / Anthropic API |
| 의존성 관리 | uv + pyproject.toml |
| 린터 | ruff |
| 테스트 | pytest + pytest-asyncio |
| 실행 엔진 | Claude Code CLI / Codex CLI / Gemini CLI |

---

## 관련 프로젝트

MetaGPT, AutoGen, CrewAI에서 영감을 받았으나 핵심 차별점이 있습니다:

- **Telegram을 native 메시지 버스로 사용** — 별도 UI·대시보드 불필요
- **YAML 기반 동적 조직 구성** — 코드 수정 없이 부서·엔진 추가 가능
- **3엔진 동시 지원** — 태스크 특성에 맞게 엔진 선택
- **봇 캐릭터 진화 시스템** — 각 봇이 개성을 가지고 성장
- **실사용 검증된 스킬 시스템** — 재사용 가능한 자동화 워크플로

---

## 기여하기

[CONTRIBUTING.md](CONTRIBUTING.md)를 참고해 주세요.

- **버그 신고**: [GitHub Issues](https://github.com/your-org/telegram-ai-org/issues)
- **기능 제안**: Issues에 `enhancement` 라벨로 등록
- **PR 제출**: `develop` 브랜치 기준으로 작성

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

### MIT 라이선스를 선택한 이유

| 기준 | MIT | Apache 2.0 | GPL v3 |
|------|-----|-----------|--------|
| 상업적 사용 | ✅ 무조건 허용 | ✅ | 조건부 |
| 수정 후 비공개 배포 | ✅ | ✅ | ❌ |
| 특허 보호 조항 | ❌ | ✅ | ✅ |
| 라이선스 단순성 | ✅ 가장 짧음 | 중간 | 복잡 |
| 오픈소스 생태계 채택률 | 매우 높음 | 높음 | 낮음 |

**선택 근거**: telegram-ai-org는 개인 개발자·스타트업·기업 누구나 제약 없이 사용하고, 자신만의 AI 조직으로 커스터마이징할 수 있어야 합니다. MIT는 가장 단순하고 허용 범위가 넓어 채택 장벽이 가장 낮습니다. 특허 분쟁 가능성이 낮은 현 단계에서는 Apache 2.0의 특허 조항보다 MIT의 단순성이 더 중요합니다. 향후 엔터프라이즈 버전이나 특허 이슈가 발생하면 Apache 2.0으로 전환을 검토할 수 있습니다.

---

*telegram-ai-org — AI 조직을 텔레그램에서 | 2026-03-25*
