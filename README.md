<p align="center">
  <!-- TODO: SVG 로고 완성 후 assets/logo/logo.svg 로 교체하세요 -->
  <img src="assets/mascot/mascot_v1.png" alt="telegram-ai-org" width="140"/>
</p>

<h1 align="center">telegram-ai-org</h1>

<p align="center">
  <strong>텔레그램 채팅방 하나가 AI 팀이 됩니다</strong><br/>
  <sub>Your Telegram group chat, reimagined as an AI-powered organization</sub>
</p>

<p align="center">
  <a href="https://github.com/dragon1086/aimesh/actions/workflows/ci-lint.yml">
    <img src="https://img.shields.io/github/actions/workflow/status/dragon1086/aimesh/ci-lint.yml?label=CI&logo=github&style=flat-square" alt="CI"/>
  </a>
  <a href="LICENSE">
    <img src="https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square" alt="MIT License"/>
  </a>
  <a href="https://pypi.org/project/telegram-ai-org/">
    <img src="https://img.shields.io/pypi/v/telegram-ai-org.svg?style=flat-square&logo=pypi&logoColor=white" alt="PyPI"/>
  </a>
  <a href="https://hub.docker.com/r/dragon1086/aimesh">
    <img src="https://img.shields.io/docker/v/dragon1086/aimesh?label=Docker&logo=docker&style=flat-square&color=2496ED" alt="Docker Hub"/>
  </a>
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg?style=flat-square" alt="Python 3.10+"/>
</p>

<br/>

---

## 이게 뭔가요? (30초 설명)

> **메시지 하나 보내면, AI 팀이 알아서 처리합니다.**

지금까지 "AI 도구"는 혼자 쓰는 것이었습니다.
**telegram-ai-org**는 다릅니다 — AI들이 역할을 나눠 **함께** 일합니다.

채팅방에 *"오늘 마케팅 전략 짜줘"* 라고 입력하면:

1. **PM 봇**이 요청을 이해하고 적절한 팀에 위임
2. **기획실 봇**이 요구사항을 정리하고
3. **성장실 봇**이 마케팅 전략을 작성
4. 결과를 채팅방에 바로 돌려줌

설치에서 첫 응답까지 **5분**. 코딩 지식 없이도 시작 가능합니다.

---

## ✨ 주요 기능

| | 기능 | 설명 |
|---|---|---|
| 🧠 | **스마트 라우팅** | PM 봇이 메시지 의도를 파악해 최적의 부서에 자동 위임 |
| 🤝 | **멀티봇 협업** | 개발·디자인·기획·성장·리서치·운영 6개 부서 봇이 유기적으로 협력 |
| ⚡ | **3종 AI 엔진 지원** | Claude Code · OpenAI Codex · Gemini CLI — 원하는 엔진 자유 선택 |
| 🔌 | **스킬 플러그인 시스템** | 봇에 능력을 추가하는 스킬을 직접 만들고 붙일 수 있음 |
| 📊 | **실시간 대시보드** | 봇 상태·메시지 흐름·응답 이력을 웹 UI로 한눈에 모니터링 |
| 🧩 | **자유로운 조직 구성** | 부서 봇을 추가/삭제해 나만의 AI 조직 구조를 설계 |
| 🐳 | **Docker 원클릭 실행** | `docker compose up -d` 한 줄로 전체 시스템 기동 |
| 🔒 | **독립 메모리** | 봇마다 독립 컨텍스트를 유지해 일관된 성격과 맥락 보존 |

---

## 🚀 Quick Start — 5분이면 충분합니다

### 준비물

- Python 3.10 이상 (또는 Docker)
- [Telegram](https://telegram.org/) 계정 + [@BotFather](https://t.me/BotFather)에서 만든 봇 토큰
- AI 엔진 하나: Claude Code / Codex / Gemini CLI 중 선택

### 1. 저장소 클론

```bash
git clone https://github.com/dragon1086/aimesh.git
cd aimesh
```

### 2. 원클릭 설치

```bash
bash quickstart.sh
```

화면 안내에 따라 봇 토큰과 Chat ID를 입력하면 나머지는 자동 설정됩니다.

### 3. 환경변수 확인 (선택)

`.env` 파일이 자동 생성됩니다. 필요한 경우 직접 수정하세요.

```dotenv
# 필수
TELEGRAM_PM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=-100123456789

# AI 엔진 (하나만 설정)
CLAUDE_CODE_PATH=/usr/local/bin/claude   # Claude Code
OPENAI_API_KEY=sk-...                    # Codex
GEMINI_CLI_PATH=/opt/homebrew/bin/gemini # Gemini CLI
```

> 전체 환경변수 목록 → [`.env.example`](.env.example)

### 4. 봇 실행

```bash
bash scripts/start_all.sh
```

### 5. 텔레그램에서 테스트

텔레그램 채팅방에 아무 메시지나 보내보세요!

```
안녕, 오늘 할 일 정리해줘
```

PM 봇이 요청을 받아 적절한 팀에 자동으로 위임합니다. 🎉

---

## 🏗️ 아키텍처

```mermaid
graph TD
    U(["👤 사용자<br/>텔레그램 채팅"])
    PM(["🧠 PM Bot<br/>라우터 &amp; 조율자"])
    DEV(["💻 개발실 봇"])
    DES(["🎨 디자인실 봇"])
    PRD(["📋 기획실 봇"])
    GRO(["📣 성장실 봇"])
    RES(["🔭 리서치실 봇"])
    OPS(["⚙️ 운영실 봇"])
    CE["Claude Code"]
    GE["Gemini CLI"]
    DB[("메모리 &amp; DB")]

    U -->|메시지| PM
    PM -->|위임| DEV & DES & PRD
    PM -->|위임| GRO & RES & OPS
    DEV & DES & PRD --> CE
    GRO & RES & OPS --> GE
    CE & GE --> DB
    DB -->|컨텍스트 유지| PM

    style PM fill:#4f46e5,color:#fff,stroke:none
    style U fill:#0ea5e9,color:#fff,stroke:none
    style CE fill:#7c3aed,color:#fff,stroke:none
    style GE fill:#059669,color:#fff,stroke:none
    style DB fill:#374151,color:#fff,stroke:none
```

**흐름 요약:**
- 모든 메시지는 **PM 봇**이 가장 먼저 수신 → 의도 파악 → 적합한 부서에 위임
- 각 부서 봇은 전문 AI 엔진(Claude Code / Gemini CLI)을 실행
- 모든 대화는 DB에 저장되어 문맥이 누적됨

---

## 📊 실시간 대시보드

봇 상태, 메시지 라우팅, 응답 이력을 **한 화면**에서 확인할 수 있습니다.

<!-- TODO: 대시보드 스크린샷 캡처 후 assets/screenshots/dashboard.png 에 저장 -->
![Dashboard Screenshot](assets/screenshots/dashboard.png)

> 📸 **스크린샷 위치**: `assets/screenshots/dashboard.png`
> 대시보드 실행 후 스크린샷을 찍어 위 경로에 저장하면 자동으로 README에 표시됩니다.

**대시보드에서 볼 수 있는 것:**

- 🟢 **봇 상태** — 각 봇의 온라인/오프라인 상태 실시간 확인
- 📨 **메시지 흐름** — PM → 각 부서 봇으로의 라우팅 경로 시각화
- 🕐 **응답 이력** — 시간순 대화 로그 및 처리 시간
- 🔔 **알림 현황** — 에러·지연·이상 감지 시 즉각 알림

**대시보드 실행:**

```bash
python dashboard.py
# 브라우저에서 http://localhost:8050 접속
```

---

## 🤖 부서별 봇 구성

| 봇 | 역할 | AI 엔진 |
|----|------|---------|
| 🧠 `aiorg_pm_bot` | 전체 조율, 라우팅 | Claude Code |
| 💻 `aiorg_engineering_bot` | 코드 작성, API 구현, 버그 수정 | Claude Code |
| 🎨 `aiorg_design_bot` | UI/UX 설계, 와이어프레임 | Claude Code |
| 📋 `aiorg_product_bot` | 기획, 요구사항 분석, PRD | Claude Code |
| 📣 `aiorg_growth_bot` | 성장 전략, 마케팅, 지표 분석 | Gemini CLI |
| 🔭 `aiorg_research_bot` | 시장조사, 경쟁사 분석 | Gemini CLI |
| ⚙️ `aiorg_ops_bot` | 배포, 인프라, 모니터링 | Gemini CLI |

> 봇 수와 역할은 `organizations.yaml`과 `orchestration.yaml`을 수정해 자유롭게 바꿀 수 있습니다.

---

## 🐳 Docker로 실행

```bash
# 전체 시스템 실행
docker compose up -d

# AI 엔진 프로파일 선택
docker compose --profile claude up -d   # Claude Code 전용
docker compose --profile gemini up -d   # Gemini CLI 전용
```

---

## 📂 프로젝트 구조

```
aimesh/
├── bots/              # 각 부서 봇 구현
├── core/              # 메시지 라우팅·엔진 공통 코어
├── skills/            # 플러그인 스킬 모음
├── dashboard/         # 실시간 모니터링 대시보드
├── tests/             # E2E + 유닛 테스트
├── orchestration.yaml # 조직 운영 전략 설정
├── organizations.yaml # 봇 조직 구성 설정
├── quickstart.sh      # 원클릭 설치 스크립트
└── docker-compose.yml # 멀티엔진 Docker 설정
```

---

## 🤝 기여하기

버그 리포트, 기능 제안, PR 모두 환영합니다!

1. 이 저장소를 **Fork**
2. 새 브랜치 생성 (`git checkout -b feat/my-feature`)
3. 변경 후 커밋 (`git commit -m "feat: 기능 설명"`)
4. PR 생성

자세한 가이드 → [CONTRIBUTING.md](CONTRIBUTING.md)

---

## 📄 라이선스

[MIT License](LICENSE) © 2024 telegram-ai-org contributors
