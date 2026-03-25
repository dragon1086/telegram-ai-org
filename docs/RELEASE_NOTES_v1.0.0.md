# telegram-ai-org v1.0.0

> **첫 번째 공식 오픈소스 릴리스** — AI 조직 자동화 플랫폼

## 🚀 What's New

### 3-Engine Support
- **claude-code** (Claude Code CLI) — 개발실/디자인실/기획실/PM
- **codex** (OpenAI Codex CLI) — 운영실
- **gemini-cli** (Google Gemini CLI) — 성장실/리서치실

All engines are auto-detected by `scripts/setup.sh` with zero manual configuration.

### One-Click Setup
```bash
git clone https://github.com/dragon1086/telegram-ai-org
cd telegram-ai-org
bash scripts/setup.sh
```

### Docker Compose Multi-Engine
```bash
docker compose --profile claude up -d   # Claude Code engine
docker compose --profile codex up -d    # Codex engine
docker compose --profile gemini up -d   # Gemini CLI engine
```

### GitHub Actions CI/CD
| Workflow | Trigger |
|----------|---------|
| `ci.yml` | PR, main push |
| `cd-main.yml` | main push |
| `publish-pypi.yml` | `v*` tag push |
| `docker-publish.yml` | `v*` tag push |
| `release.yml` | `v*` tag push |

---

## 📋 Full Changelog

### Community & Governance
- `docs/CODE_OF_CONDUCT.md` — Contributor Covenant v2.1 추가
- `CONTRIBUTING.md` — SPDX 헤더 + 기여 가이드 완비
- `LICENSE` — MIT 2026

### Bug Fixes
- `_load_env_file` YAML 파싱 오류 수정 (`0a3e32f`)
- GoalTracker noop dispatch + `reply_to_message_id` TypeError 수정 (`032ed88`)
- cancelled 태스크 의존성 자동 정리 (`05e3c97`)
- staleness_checker: running 태스크 heartbeat 기반 타임아웃 변경 (`9987d68`)
- 주간회의 멀티봇: 스팸 메시지 + SynthesisPoller GoalTracker 지원 (`fa08569`)

### Features
- E2E 자율 루프 검증 완료 — idle→evaluate→replan→dispatch, 37 tests pass (`bbfd972`)
- `telegram_sender.py` 분리 — 전송 모듈 Feature Flag 적용 (`ee7b986`)

### CI/CD
- publish 트리거를 tag-based (`v*`)로 변경 (`033826a`)
- 중복 워크플로우 파일 정리 (`cd201b0`)

### Documentation
- README.md 오픈소스 버전 전면 개편 — 뱃지, 3엔진 설명, 설치 가이드 (`deec2da`)
- CI 뱃지 URL 수정 (`ba7c762`)

### Tests
- E2E 테스트 288개 전체 통과 (filterwarnings 추가, `29e11d6`)

---

## 🔧 Requirements

- Python 3.11+
- Telegram Bot API token
- One of: Claude Code CLI / OpenAI Codex CLI / Google Gemini CLI

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup.

---

## 📦 Installation

### PyPI
```bash
pip install telegram-ai-org
```

### Docker
```bash
docker pull dragon1086/telegram-ai-org:v1.0.0
```

---

*Released 2026-03-25 by [aiorg_engineering_bot](https://github.com/dragon1086/telegram-ai-org)*
