# telegram-ai-org (aimesh)

> **"10분 안에 텔레그램에서 당신만의 AI 조직을 운영하세요"**

텔레그램 그룹 채팅방을 AI 조직의 오피스로 만드는 오픈소스 멀티봇 오케스트레이션 시스템.
PM 봇이 사용자 요청을 분석해 7개 전문 부서 봇에 자동 배분합니다.
**Claude Code / Codex / Gemini CLI** 3개 엔진을 모두 지원합니다.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![Engine](https://img.shields.io/badge/engine-claude--code%20%7C%20codex%20%7C%20gemini--cli-orange.svg)](#3엔진-설치법)
[![PyPI version](https://img.shields.io/pypi/v/telegram-ai-org.svg)](https://pypi.org/project/telegram-ai-org/)
[![CI](https://img.shields.io/github/actions/workflow/status/dragon1086/aimesh/ci-lint.yml?label=CI&logo=github)](https://github.com/dragon1086/aimesh/actions/workflows/ci-lint.yml)
[![CD Main](https://img.shields.io/github/actions/workflow/status/dragon1086/aimesh/cd-main.yml?label=CD%3Amain&logo=github)](https://github.com/dragon1086/aimesh/actions/workflows/cd-main.yml)
[![Release](https://img.shields.io/github/v/release/dragon1086/aimesh?label=Release&logo=github&color=green)](https://github.com/dragon1086/aimesh/releases/latest)
[![Docker Hub](https://img.shields.io/docker/v/dragon1086/aimesh?label=Docker&logo=docker&color=blue)](https://hub.docker.com/r/dragon1086/aimesh)

---

## 목차

- [프로젝트 소개](#프로젝트-소개)
- [3엔진 설치법](#3엔진-설치법)
- [원클릭 setup.sh 사용법](#원클릭-setupsh-사용법)
- [조직 구조](#조직-구조)
- [스킬 가이드](#스킬-가이드)
- [기여 방법](#기여-방법)
- [Docker 실행법](#docker-실행법)
- [환경변수 참조](#환경변수-참조)
- [FAQ / 트러블슈팅](#faq--트러블슈팅)
- [라이선스](#라이선스)

---

## 프로젝트 소개

### 무엇을 하는 프로젝트인가

aimesh는 **텔레그램 그룹 채팅방 하나를 AI 조직의 사무실로 전환**합니다.
사용자가 자연어로 태스크를 입력하면:

1. **PM 봇**이 태스크를 분석하고 적합한 부서 봇에 자동 배분
2. **부서 봇**이 엔진(Claude Code / Codex / Gemini CLI)을 실행해 결과 생성
3. 결과를 텔레그램 채팅방으로 반환 — 별도 대시보드 불필요

### 주요 기능

| 기능 | 설명 |
|------|------|
| **PM 오케스트레이션** | 자연어 태스크를 PM 봇이 분석 → 적합한 부서 봇에 자동 배분 |
| **7개 전문 부서봇** | PM / 기획실 / 개발실 / 디자인실 / 성장실 / 운영실 / 리서치실 |
| **3엔진 호환** | Claude Code (복잡한 추론) / Codex (DevOps 자동화) / Gemini CLI (실시간 웹 검색) |
| **스킬 시스템** | 재사용 가능한 작업 템플릿 22개 — 텔레그램 슬래시 커맨드로 직접 실행 |
| **자연어 스케줄** | "매주 월요일 오전 9시에 리포트 보내줘" 형식의 스케줄 등록 |
| **교훈 메모리** | 작업 결과를 메모리에 저장, 다음 태스크에 자동 반영 |
| **멀티부서 토론** | 여러 봇이 하나의 주제를 토론 후 PM이 합성 결과 생성 |
| **Telegram Native UI** | 채팅방 자체가 오피스 — 별도 대시보드 불필요 |

### 핵심 파일 구조

```
telegram-ai-org/
├── main.py                          # 로컬 진입점
├── orchestration.yaml               # 전체 오케스트레이션 설정
├── workers.yaml                     # 워커 봇 등록부
├── bots/                            # 봇별 YAML 정의 (성격, 역할, 엔진)
├── core/                            # 핵심 오케스트레이션 로직
│   ├── pm_orchestrator.py           #   PM 메인 루프
│   ├── pm_router.py                 #   태스크 → 부서 라우팅
│   └── nl_classifier.py             #   자연어 분류기
├── tools/                           # 엔진 러너 및 CLI 도구
│   ├── claude_code_runner.py        #   Claude Code CLI 래퍼
│   ├── codex_runner.py              #   Codex CLI 래퍼
│   ├── gemini_cli_runner.py         #   Gemini CLI OAuth 러너
│   └── orchestration_cli.py         #   설정 검증 CLI
├── skills/                          # 재사용 가능한 작업 스킬 (22개)
├── scripts/                         # 운영 스크립트
│   ├── setup.sh                     #   원클릭 초기 설치
│   ├── start_all.sh                 #   전체 봇 시작
│   └── request_restart.sh           #   안전한 재기동 요청
├── CLAUDE.md                        # Claude Code 운영 지침 (기준 문서)
├── AGENTS.md                        # Codex CLI 운영 지침
├── GEMINI.md                        # Gemini CLI 운영 지침
└── .env.example                     # 환경변수 템플릿
```

---

## 3엔진 설치법

3개 엔진 중 **1개 이상** 설치하면 됩니다. 엔진별 특성에 따라 부서가 자동으로 엔진을 선택합니다.

### 엔진 비교

| 항목 | claude-code | codex | gemini-cli |
|------|-------------|-------|------------|
| 개발사 | Anthropic | OpenAI | Google |
| 웹 검색 | 없음 | 없음 | **내장** (Google Search) |
| 최적 태스크 | PRD·코드·기획·설계 | 배포·인프라·DevOps | 시장조사·경쟁사 분석 |
| 컨텍스트 길이 | 200K 토큰 | 표준 | **1M 토큰** |
| 인증 방식 | OAuth 2.0 | OAuth 2.0 | OAuth 2.0 |
| API 키 필요 여부 | **불필요** (OAuth 사용) | **불필요** (OAuth 사용) | **불필요** (Google 계정) |

> 3개 엔진 모두 OAuth 2.0을 지원하므로 API 키 없이 바로 시작할 수 있습니다.

---

### 1. Claude Code (기본·권장)

**사전 요구사항**

| 항목 | 요구사항 |
|------|----------|
| Node.js | 18 이상 |
| npm | 8 이상 |
| 인터넷 연결 | OAuth 인증 시 필요 |
| OS | macOS / Linux / Windows (WSL2) |

**설치 명령어**

```bash
# 1. npm으로 설치
npm install -g @anthropic-ai/claude-code

# 2. 브라우저 OAuth 인증 (1회만)
claude auth login

# 3. 설치 확인
claude --version
```

**인증 확인**: `claude auth status` — 인증 성공 시 `Logged in` 출력

---

### 2. Codex CLI

**사전 요구사항**

| 항목 | 요구사항 |
|------|----------|
| Node.js | 18 이상 |
| npm | 8 이상 |
| OpenAI 계정 | OAuth 인증용 |

**설치 명령어**

```bash
# 1. npm으로 설치
npm install -g @openai/codex

# 2. 브라우저 OAuth 인증 — ~/.codex/auth.json 자동 생성
codex login

# 3. 설치 확인
codex --version
```

**인증 확인**: `~/.codex/auth.json` 파일 존재 여부 확인

> OpenAI API 키가 있는 경우: `.env`에 `OPENAI_API_KEY=sk-...`를 직접 설정하면 OAuth 없이 사용 가능

---

### 3. Gemini CLI

**사전 요구사항**

| 항목 | 요구사항 |
|------|----------|
| Node.js 또는 Homebrew | 둘 중 하나 |
| Google 계정 | OAuth 인증용 (무료) |

**설치 명령어**

```bash
# Homebrew (macOS 권장)
brew install gemini-cli

# 또는 npm
npm install -g @google/gemini-cli

# Google 계정 OAuth 인증 — ~/.gemini/oauth_creds.json 자동 생성
gemini auth login

# 설치 확인
gemini --version
```

**인증 확인**: `~/.gemini/oauth_creds.json` 파일 존재 여부 확인

---

## 원클릭 setup.sh 사용법

`scripts/setup.sh`는 설치된 엔진을 자동으로 감지하고 Python 환경 구성, `.env` 파일 생성, 검증까지 한 번에 수행합니다.

### 빠른 시작

```bash
# 1. 저장소 클론
git clone https://github.com/dragon1086/aimesh.git
cd aimesh

# 2. 원클릭 설치 실행
bash scripts/setup.sh

# 3. .env 파일에 Telegram 봇 토큰 입력
nano .env
# 필수: TELEGRAM_BOT_TOKEN, TELEGRAM_GROUP_CHAT_ID

# 4. 전체 봇 시작
bash scripts/start_all.sh
```

또는 curl 원라이너 (저장소 클론 없이):

```bash
curl -sSL https://raw.githubusercontent.com/dragon1086/aimesh/main/scripts/setup.sh | bash
```

### setup.sh 옵션

| 옵션 | 설명 |
|------|------|
| `bash scripts/setup.sh` | 기본 실행 (대화형) |
| `bash scripts/setup.sh --yes` | CI/자동화 환경 무인 설치 (프롬프트 건너뜀) |
| `bash scripts/setup.sh --docker` | Docker 환경 감지 후 `docker compose up` 자동 실행 |
| `bash scripts/setup.sh --yes --docker` | CI + Docker Compose 완전 비대화형 |
| `bash scripts/setup.sh --skip-verify` | 검증 단계 건너뜀 (빠른 재설치) |
| `bash scripts/setup.sh --no-venv` | 가상환경 생성 건너뜀 (기존 환경 재사용) |

### 실행 예시 출력

```
╔══════════════════════════════════════════════════════════════╗
║        telegram-ai-org — 원클릭 설치 스크립트               ║
║        3-Engine Auto-Detect Setup (claude/codex/gemini)      ║
╚══════════════════════════════════════════════════════════════╝

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

### 3엔진 자동 감지 규칙

| 엔진 | 감지 조건 | 인증 파일 |
|------|-----------|-----------|
| **claude-code** | `which claude` 성공 + `--version` 실행 가능 | OAuth 세션 (브라우저) |
| **codex** | `which codex` 성공 + `--version` 실행 가능 | `~/.codex/auth.json` |
| **gemini-cli** | `/opt/homebrew/bin/gemini` 우선 또는 `which gemini` | `~/.gemini/oauth_creds.json` |

감지된 엔진 경로는 `.env`의 `CLAUDE_CLI_PATH`, `CODEX_CLI_PATH`, `GEMINI_CLI_PATH`에 자동으로 기재됩니다.

---

## 조직 구조

### 부서별 역할과 담당 엔진

| 부서 | 봇 ID | 담당 엔진 | 역할 |
|------|-------|-----------|------|
| **PM** | `aiorg_pm_bot` | claude-code | 태스크 분석, 부서 배분, 오케스트레이션 |
| **기획실** | `aiorg_product_bot` | claude-code | PRD 작성, 요구사항 분석, 기획 |
| **개발실** | `aiorg_engineering_bot` | claude-code | 코드 구현, 버그 수정, API 개발 |
| **디자인실** | `aiorg_design_bot` | claude-code | UI/UX 설계, 와이어프레임, 프로토타입 |
| **운영실** | `aiorg_ops_bot` | codex | 배포, 인프라, DevOps 자동화 |
| **성장실** | `aiorg_growth_bot` | gemini-cli | 성장 전략, 마케팅, 지표 분석 |
| **리서치실** | `aiorg_research_bot` | gemini-cli | 시장조사, 경쟁사 분석, 문서 요약 |

> **엔진 선택 원칙**: 복잡한 추론 → claude-code / 경량 CLI 자동화 → codex / 실시간 웹 검색 → gemini-cli

### 아키텍처 흐름

```
Telegram 그룹 채팅방
        │
        ▼
┌──────────────────────────────────────────────────┐
│              PM Bot (aiorg_pm_bot)               │
│              엔진: claude-code                    │
│  nl_classifier → pm_router → pm_orchestrator     │
│  GoalTracker · DiscussionProtocol · Scheduler    │
└────────────────────┬─────────────────────────────┘
                     │ 태스크 배분
         ┌───────────┼────────────────┐
         ▼           ▼                ▼
┌─────────────────┐ ┌──────────┐ ┌──────────────────┐
│  claude-code 계열 │ │codex 계열│ │  gemini-cli 계열  │
│ PM·기획실·개발실 │ │  운영실  │ │  성장실·리서치실  │
│ 디자인실         │ │ 배포/인프│ │  조사/검색       │
└─────────────────┘ └──────────┘ └──────────────────┘
```

### 봇 추가 방법

`workers.yaml`에 항목을 추가하고 봇을 재시작합니다 — 코드 수정 불필요:

```yaml
workers:
  - name: my_new_bot
    token: "${MY_NEW_BOT_TOKEN}"
    engine: claude-code        # claude-code | codex | gemini-cli
    description: "신규 봇 역할 설명"
```

---

## 스킬 가이드

스킬은 재사용 가능한 자동화 워크플로입니다. 텔레그램에서 슬래시 커맨드 또는 자연어 트리거로 실행할 수 있습니다.

> 상세 작성법 및 MCP 연동 가이드: **[docs/SKILLS_MCP_GUIDE.md](docs/SKILLS_MCP_GUIDE.md)**

### 내장 스킬 목록 (22개)

| 스킬 | 슬래시 커맨드 | 트리거 키워드 | 설명 |
|------|--------------|--------------|------|
| **quality-gate** | `/quality-gate` | `품질검사`, `QA gate`, `pre-merge check` | ruff 린트 + pytest 실행 — 머지/배포 전 필수 |
| **e2e-regression** | `/e2e-regression` | `e2e 테스트`, `회귀테스트`, `smoke test` | 전체 E2E 회귀 테스트 (PM 라우팅·봇 디스패치·엔진 호환성) |
| **gemini-image-gen** | `/gemini-image-gen` | `이미지 생성`, `generate image`, `시각화` | Gemini OAuth 기반 이미지 생성 (gemini-2.5-flash) |
| **bot-triage** | `/bot-triage` | `봇 장애`, `bot down`, `triage` | 봇 장애 진단, 자동 복구, 인시던트 리포트 |
| **error-gotcha** | `/error-gotcha` | `gotcha 추가`, `에러 회고`, `add gotcha` | 에러 재발 방지 — gotcha 항목 자동 등록 |
| **engineering-review** | `/engineering-review` | `code review`, `코드리뷰`, `PR review` | 코드 변경 검토 — 린트 + 테스트 + 구조 체크 |
| **safe-modify** | `/safe-modify` | `safe modify`, `안전 수정`, `부작용 최소화` | 고위험 코드 수정 시 최소 풋프린트 방법론 |
| **brainstorming-auto** | `/brainstorming-auto` | `자동 설계`, `auto design` | 인간 확인 없는 자율 설계 문서 생성 |
| **weekly-review** | `/weekly-review` | `주간 회고`, `weekly review` | 주간 회고 자동 실행 + KR 업데이트 |
| **performance-eval** | `/performance-eval` | `성과 평가`, `KR 달성률` | 월말 KR 달성률 기반 성과 평가 |
| **harness-audit** | `/harness-audit` | `설정 감사`, `출시 전 점검` | 전체 설정 감사 — 릴리스 전 필수 실행 |
| **pm-progress-tracker** | `/pm-progress-tracker` | `진척률`, `목표 추적` | PM 목표 달성률 추적 및 이터레이션 로그 |
| **pm-task-dispatch** | `/pm-task-dispatch` | `태스크 배분`, `task dispatch` | PM 태스크 자동 배분 및 추적 |
| **pm-discussion** | `/pm-discussion` | `부서 토론`, `discussion` | 멀티부서 토론 프로토콜 실행 |
| **growth-analysis** | `/growth-analysis` | `성장 분석`, `지표 분석` | 성장 지표 분석 및 보고서 생성 |
| **design-critique** | `/design-critique` | `디자인 리뷰`, `UI 검토` | UI/UX 디자인 비평 및 개선안 제안 |
| **retro** | `/retro` | `회고`, `retrospective` | 스프린트 회고 자동 실행 |
| **loop-checkpoint** | `/loop-checkpoint` | `루프 체크`, `진행 상황` | 반복 작업 체크포인트 저장 |
| **skill-evolve** | `/skill-evolve` | `스킬 개선`, `skill evolve` | 기존 스킬 자동 개선 및 업데이트 |
| **autonomous-skill-proxy** | `/autonomous-skill-proxy` | `자율 실행`, `autonomous` | 인간 확인 없는 자율 스킬 프록시 |
| **failure-detect-llm** | `/failure-detect-llm` | `장애 감지`, `failure detect` | LLM 기반 장애 감지 및 알림 |
| **create-skill** | `/create-skill` | `스킬 생성`, `new skill` | 새 스킬 자동 생성 템플릿 |

### 스킬 구조

각 스킬은 `skills/<skill-name>/` 디렉토리에 위치하며, Claude Code가 자동으로 로드합니다:

```
skills/
└── quality-gate/
    ├── SKILL.md          # 트리거·실행 절차·산출물 정의
    ├── gotchas.md        # 인시던트 기반 주의사항
    └── scripts/          # 스킬 전용 자동화 스크립트 (선택)
```

새 스킬 추가 방법: [docs/SKILLS_MCP_GUIDE.md](docs/SKILLS_MCP_GUIDE.md) 참조

---

## 기여 방법

기여를 환영합니다! 버그 신고, 기능 제안, PR 모두 가능합니다.

### 로컬 개발 환경 설정

```bash
# 1. 저장소 포크 후 클론
git clone https://github.com/<your-username>/aimesh.git
cd aimesh

# 2. 원클릭 설치 (가상환경 자동 생성)
bash scripts/setup.sh

# 3. 환경 변수 설정
cp .env.example .env
# .env 파일에 테스트용 봇 토큰 입력

# 4. 테스트 실행으로 환경 확인
./.venv/bin/pytest -q
```

### 브랜치 전략

```
main          ─── 프로덕션 배포 기준 (태그 기반 릴리스)
  └── develop ─── 통합 브랜치 (PR 머지 대상)
        ├── feature/xxx   ── 신규 기능
        ├── fix/xxx       ── 버그 수정
        ├── docs/xxx      ── 문서 수정
        ├── refactor/xxx  ── 리팩토링
        └── chore/xxx     ── 빌드/설정 변경
```

| 유형 | 패턴 | 예시 |
|------|------|------|
| 신규 기능 | `feature/<짧은-설명>` | `feature/docker-compose-support` |
| 버그 수정 | `fix/<짧은-설명>` | `fix/gemini-auth-timeout` |
| 문서 | `docs/<짧은-설명>` | `docs/readme-opensource` |
| 리팩토링 | `refactor/<짧은-설명>` | `refactor/runner-interface` |

> **주의**: `main` 브랜치에 직접 푸시하지 마세요. 모든 변경은 `develop` 경유 PR로 머지됩니다.

### PR 절차

```bash
# 1. develop에서 피처 브랜치 생성
git checkout develop && git pull origin develop
git checkout -b feature/my-feature

# 2. 코드 작성 + 테스트
./.venv/bin/pytest -q
./.venv/bin/ruff check .

# 3. 커밋 (Conventional Commits 규칙)
git commit -m "feat(gemini): OAuth 2.0 인증 지원 추가"

# 4. develop 브랜치 대상으로 PR 제출
gh pr create --base develop --title "feat: ..." --body "..."
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

### 3개 컨텍스트 파일 동기화 원칙 (필수)

이 프로젝트는 3개 엔진을 지원합니다. 각 엔진은 자신의 컨텍스트 파일만 읽으므로
**항상 동시에 수정**해야 합니다:

```
CLAUDE.md   →  Claude Code용 (가장 상세한 기준 문서)
AGENTS.md   →  Codex CLI용  (CLAUDE.md와 동기화)
GEMINI.md   →  Gemini CLI용 (CLAUDE.md와 동기화)
```

> 하나의 파일만 수정하면 다른 엔진이 최신 정보를 반영하지 못합니다.
> CLAUDE.md를 먼저 수정한 후 AGENTS.md → GEMINI.md 순서로 동기화하세요.

### 코드 스타일

- **Linter**: `ruff` (line length: 100)
- **Python**: 3.10+, 타입 힌트 필수
- **비동기**: asyncio 기반 (`async/await` 우선)
- **로깅**: `loguru` 사용 (`print` 금지)
- **시크릿**: 하드코딩 절대 금지, `os.environ` 사용

자세한 기여 가이드: [CONTRIBUTING.md](CONTRIBUTING.md)

---

## Docker 실행법

Docker Compose는 엔진별 프로파일로 선택적 실행을 지원합니다.

```bash
# 1. 환경변수 준비
cp .env.example .env && nano .env

# 2. 전체 조직 빌드 + 실행 (claude + codex + gemini)
docker compose --profile claude --profile codex --profile gemini up -d

# 3. 상태 확인
docker compose ps
docker compose logs -f aiorg-pm
```

**프로파일별 선택 실행**

```bash
# Claude 계열만 (PM + 기획실 + 개발실 + 디자인실)
docker compose --profile claude up -d

# Codex 계열만 (운영실)
docker compose --profile codex up -d

# Gemini 계열만 (성장실 + 리서치실)
docker compose --profile gemini up -d
```

| 프로파일 | 봇 | 엔진 |
|----------|----|------|
| `claude` | PM, 기획실, 개발실, 디자인실 | `claude-code` |
| `codex` | 운영실 | `codex` |
| `gemini` | 성장실, 리서치실 | `gemini-cli` (gemini-2.5-flash) |

---

## 환경변수 참조

`.env.example`을 복사해 `.env`를 만들고 값을 채웁니다.

```bash
cp .env.example .env
```

> **보안**: `.env` 파일은 `.gitignore`에 포함되어 있습니다. 절대 커밋하지 마세요.

### 필수 변수

| 변수명 | 설명 | 예시 |
|--------|------|------|
| `TELEGRAM_BOT_TOKEN` | PM 봇 토큰 (@BotFather 발급) | `123456:ABC-DEF...` |
| `TELEGRAM_GROUP_CHAT_ID` | 그룹 채팅 ID (음수) | `-5203707291` |
| `BOT_TOKEN_AIORG_PRODUCT_BOT` | 기획실 봇 토큰 | `123456:ABC...` |
| `BOT_TOKEN_AIORG_ENGINEERING_BOT` | 개발실 봇 토큰 | `123456:ABC...` |
| `BOT_TOKEN_AIORG_DESIGN_BOT` | 디자인실 봇 토큰 | `123456:ABC...` |
| `BOT_TOKEN_AIORG_GROWTH_BOT` | 성장실 봇 토큰 | `123456:ABC...` |
| `BOT_TOKEN_AIORG_OPS_BOT` | 운영실 봇 토큰 | `123456:ABC...` |
| `BOT_TOKEN_AIORG_RESEARCH_BOT` | 리서치실 봇 토큰 | `123456:ABC...` |

### 엔진 경로 (setup.sh 자동 감지)

| 변수명 | 엔진 | 예시 |
|--------|------|------|
| `CLAUDE_CLI_PATH` | Claude Code | `/Users/user/.local/bin/claude` |
| `CODEX_CLI_PATH` | Codex | `/opt/homebrew/bin/codex` |
| `GEMINI_CLI_PATH` | Gemini CLI | `/opt/homebrew/bin/gemini` |

전체 환경변수 레퍼런스: [`.env.example`](.env.example)

---

## FAQ / 트러블슈팅

**Q. 엔진 하나만 설치해도 되나요?**
A. 네. 3개 중 하나만 설치해도 됩니다. `bots/*.yaml`의 `engine:` 필드를 설치된 엔진으로 통일하세요.

**Q. API 비용이 걱정됩니다.**
A. `DAILY_COST_LIMIT_USD`, `PM_HOURLY_CALL_LIMIT` 환경변수로 비용 상한을 설정할 수 있습니다. 초과 시 서킷 브레이커가 자동 동작합니다.

**Q. 봇을 직접 종료/재시작해도 되나요?**
A. **금지**입니다. 직접 프로세스 종료 시 실행 중인 태스크 결과가 유실됩니다. 반드시 `bash scripts/request_restart.sh --reason "이유"`를 사용하세요.

### 설치 문제

| 증상 | 해결 방법 |
|------|-----------|
| `AI 엔진이 하나도 감지되지 않았습니다` | 3엔진 중 하나 이상 설치 후 `bash scripts/setup.sh` 재실행 |
| `Python 3.10 이상을 찾을 수 없습니다` | `brew install python@3.12` 또는 `pyenv install 3.12` |
| `import anthropic 실패` | `.venv/bin/pip install anthropic` 수동 실행 |
| setup.sh가 엔진을 못 찾음 | `which claude` / `which codex` / `which gemini`로 경로 확인 후 `.env`에 직접 입력 |

### 엔진 연결 오류

| 엔진 | 증상 | 해결 방법 |
|------|------|-----------|
| **claude-code** | `claude: command not found` | `npm install -g @anthropic-ai/claude-code` 후 `claude auth login` |
| **codex** | `~/.codex/auth.json not found` | `codex login` 으로 OAuth 인증 완료 |
| **gemini-cli** | `oauth_creds.json not found` | `gemini auth login` 으로 Google 계정 인증 |

---

## 기술 스택

| 레이어 | 기술 |
|--------|------|
| 언어 | Python 3.10+ |
| 봇 프레임워크 | python-telegram-bot |
| 비동기 | asyncio |
| 린터 | ruff |
| 테스트 | pytest + pytest-asyncio |
| DB | SQLite (공유 컨텍스트) |
| 실행 엔진 | Claude Code CLI / Codex CLI / Gemini CLI |
| 컨테이너 | Docker + Docker Compose (프로파일 지원) |
| CI/CD | GitHub Actions (`ci-lint.yml` / `ci-e2e.yml` / `publish-pypi.yml` / `cd-main.yml`) |

---

## 라이선스

이 프로젝트는 **MIT 라이선스** 하에 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

---

## 관련 프로젝트

MetaGPT, AutoGen, CrewAI, OpenAI Swarm에서 영감을 받았으나 핵심 차별점:

- **Telegram을 native 메시지 버스로 사용** — 별도 UI·대시보드 불필요
- **YAML 기반 동적 조직 구성** — 코드 수정 없이 부서·엔진 추가 가능
- **3엔진 동시 지원** — 태스크 특성에 맞게 엔진 자동 선택
- **실사용 검증된 스킬 시스템** — 22개 재사용 가능한 자동화 워크플로

---

*telegram-ai-org (aimesh) — AI 조직을 텔레그램에서 | 2026*
