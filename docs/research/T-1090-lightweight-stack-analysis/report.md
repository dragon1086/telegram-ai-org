# aimesh 경량화 분석 보고서
**Task ID**: T-aiorg_pm_bot-1090
**작성일**: 2026-04-01
**담당**: 리서치실 (aiorg_research_bot)

---

## 요약 결론

> **전체 venv 516MB 중 단 2개 패키지(`claude-agent-sdk` 185MB + ML 간접 유입 70MB)가 절반(49%)을 점유.**
> 이 두 항목만 제거해도 venv는 **~260MB로 줄어들며**, Docker 이미지는 현행 대비 **~45% 감소** 추정.
> 원클릭 셋팅은 `uv` 기본값 전환으로 설치 속도 10~100배 개선 가능.
> 실시간 대시보드는 **이미 FastAPI+SSE로 구현 완료** — 추가 스택 불필요, pyproject.toml 누락 수정만 필요.

---

## Phase 1: 현행 의존성 전수 분석

### 1-A. 런타임 핵심 의존성 (pyproject.toml `dependencies`)

| 패키지 | 버전 | 실제 사용 위치 | 설치 크기 | 분류 |
|--------|------|--------------|-----------|------|
| `python-telegram-bot` | 22.6 | 봇 런타임 전반 (core/, telegram_ai_org/) | 7.5MB | ✅ **필수** |
| `pydantic` | 2.12.5 | 데이터 검증 전반 | 8.3MB (core+pydantic_core) | ✅ **필수** |
| `aiosqlite` | 0.22.1 | DB 비동기 접근 (context_db, repositories) | 132KB | ✅ **필수** |
| `python-dotenv` | 1.0+ | .env 로딩 | ~60KB | ✅ **필수** |
| `loguru` | 0.7.3 | 로깅 전반 | 516KB | ✅ **필수** |
| `PyYAML` | 6.0+ | orchestration.yaml, organizations.yaml 파싱 | ~400KB | ✅ **필수** |
| `apscheduler` | 3.11.2 | core/scheduler.py, session_manager.py | 480KB | ✅ **필수** |
| `rank-bm25` | 0.2.2 | core/memory_manager.py, telegram_relay.py | 12KB | ✅ **필수** (초경량) |
| `mcp` | 1.26.0 | tools/memory_mcp_server.py, claude_code_runner.py | 2.0MB | ✅ **필수** |
| **`claude-agent-sdk`** | **0.1.50** | **tools/claude_agent_runner.py 1개 파일만 사용** | **185MB** | ⚠️ **경량화 가능** |

### 1-B. 엔진별 선택 의존성

| 패키지 | 사용 위치 | 설치 크기 | 분류 |
|--------|-----------|-----------|------|
| `anthropic` | tools/claude_agent_runner.py 보완 | 5.9MB | ⚠️ **경량화 가능** (claude-agent-sdk와 역할 중복) |
| `openai` | tools/codex_runner.py | 9.6MB | ✅ **필수** (codex 프로파일 사용 시) |
| `google-genai` | tools/gemini_runner.py, generate_assets.py | 11MB | ✅ **필수** (gemini 프로파일 사용 중) |
| `httpx` | test 전용 (런타임 미사용) | ~3MB | 🔴 **제거 가능** (runtime에서 미사용) |
| `fastapi` + `uvicorn` | dashboard.py, core/api/ 전반 | 2.0MB | ✅ **필수** (pyproject.toml에 **누락**) |

### 1-C. 🔴 무거운 요소 — 제거/경량화 가능 목록

| 패키지 | 설치 크기 | 유입 경로 | 런타임 사용 | 분류 |
|--------|-----------|-----------|------------|------|
| **`claude-agent-sdk._bundled.claude`** | **184MB** | SDK 내부에 Claude CLI 바이너리 번들 포함 | tools/claude_agent_runner.py 1개 파일 | ⚠️ **경량화 가능** — subprocess 직접 호출로 대체 시 불필요 |
| `matplotlib` | 20MB | dev deps 또는 간접 유입 | **런타임 코드에서 미사용** | 🔴 **제거 가능** |
| `PIL` (pillow) | 13MB | 간접 유입 | **런타임 코드에서 미사용** | 🔴 **제거 가능** |
| `fontTools` | 13MB | matplotlib 의존성 | **런타임 코드에서 미사용** | 🔴 **제거 가능** |
| `numpy` | 23MB | matplotlib 간접 의존 | **런타임 코드에서 미사용** | 🔴 **제거 가능** |
| `telethon` | 13MB | E2E 테스트 스크립트 전용 (scripts/) | 봇 런타임 미사용 | 🔴 **제거 가능** (test extras 분리 필요) |
| `mypy` + `mypyc` | 32MB | dev extras → 프로덕션 이미지 유입 | 타입 체크 도구 | 🔴 **제거 가능** (builder stage에만 필요) |
| `black` | 2.1MB | dev extras → 프로덕션 이미지 유입 | 포매터 도구 | 🔴 **제거 가능** (런타임 불필요) |

**총 제거 가능 용량: ~300MB (현행 516MB의 58%)**

### 1-D. 인프라 레이어 평가

| 컴포넌트 | 현황 | 평가 |
|----------|------|------|
| **Redis** | redis:7-alpine, 봇간 태스크 큐 공유 | ✅ **필수** |
| **FastAPI + uvicorn** | dashboard.py + core/api/ REST API + SSE 스트림 구현됨 | ✅ **필수** — pyproject.toml에 **누락 상태** |
| **Node.js 런타임** | Dockerfile apt nodejs 설치, 3엔진 CLI 실행 | ✅ **필수** (runtime stage에만 필요) |
| **3개 엔진 CLI 바이너리** | docker-compose profile 분리 (claude/codex/gemini) | ✅ **구조 양호** |
| **Telethon** | scripts/ E2E 테스트 전용 | 🔴 **test extras로 이동 필요** |

### 1-E. 원클릭 셋팅 현황 문제점

| 항목 | 현황 | 문제 |
|------|------|------|
| `install.sh` 기본 설치 | `pip install -e .[dev]` | dev 의존성 전체 프로덕션 유입 |
| `FastAPI` | 실사용 중이나 pyproject.toml 누락 | 설치 불안정 위험 |
| `uv` | setup.sh에 조건부 지원 | 기본값은 여전히 pip |
| 원클릭 셋팅 단계 수 | ~6~8단계 수동 작업 | 원클릭 목표 미달 |

---

## Phase 2: 경량 트렌딩 기술 스택 조사 (2026-04-01 기준)

### 2-A. 텔레그램 봇 프레임워크 비교

| 항목 | python-telegram-bot (현행) | aiogram v3 | Telethon |
|------|--------------------------|------------|----------|
| **GitHub Stars** | ~29,000 | ~5,600 | ~11,900 (**archived**) |
| **최근 릴리즈** | v22.7 (2026-03-16) | v3.26.0 (2026-03-02) | v1.42.0 (2025-11-05) |
| **비동기 지원** | ✅ native asyncio (v20+) | ✅ native asyncio | ✅ asyncio |
| **pip wheel 크기** | 745KB | 716KB | 748KB |
| **유지보수 상태** | 활발 | 활발 | ⛔ GitHub archived (Codeberg 이전) |
| **원클릭 적합성** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ (v2 과도기) |

> **결론**: python-telegram-bot v22 유지 권고. Stars 최다, 문서 최고, 코드베이스 전반에 깊이 통합. Telethon은 GitHub archived — 신규 사용 금지.

### 2-B. 비동기 경량 HTTP/태스크 비교

| 항목 | httpx | aiohttp | anyio |
|------|-------|---------|-------|
| **GitHub Stars** | ~15,100 | ~16,200 | ~2,350 |
| **최근 릴리즈** | v0.28.1 (2024-12-06) | v3.13.4 (2026-03-28) | v4.13.0 (2026-03-24) |
| **pip wheel 크기** | 73.5KB | ~1.8MB | ~300KB |
| **의존성 수** | 5개 | 4개 | 3개 |
| **HTTP/2 지원** | ✅ optional | ❌ | N/A |
| **원클릭 적합성** | 상 | 상 | 중 (클라이언트 아님) |

> **결론**: 현행 런타임에서 별도 HTTP 클라이언트 불필요 (python-telegram-bot이 httpx 내장). httpx를 runtime extras에서 제거 가능.

### 2-C. 원클릭 패키징 패턴 비교

| 항목 | uv | pip-tools | devcontainer |
|------|----|-----------|-------------|
| **GitHub Stars** | **82,336** | ~8,000 | N/A |
| **최근 릴리즈** | 2026-03-24 | v7.5.3 (2026-02-11) | 지속 업데이트 |
| **설치 속도** | pip 대비 **10~100x 빠름** (Rust 기반) | 소폭 개선 | Docker 빌드 수분 |
| **Docker 이미지 크기 영향** | 멀티스테이지 시 **최대 80% 감소** | pip 동일 수준 | base image 200~900MB |
| **lockfile** | uv.lock (결정론적) | requirements.txt pin | docker layer cache |
| **원클릭 적합성** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |

> **결론**: `uv`는 2025~2026 Python 패키징 업계 표준으로 확립. setup.sh에 조건부 지원 이미 존재 — 기본값 전환만 필요.

### 2-D. 실시간 대시보드 경량 옵션 비교

| 항목 | FastAPI+SSE (현행) | Textual TUI | NiceGUI | Streamlit | Grafana OSS |
|------|------------------|-------------|---------|-----------|-------------|
| **GitHub Stars** | 96,700 | 35,114 | 15,600 | 44,100 | 72,900 |
| **최근 릴리즈** | v0.135.2 | v7.3.0 (2026-01) | v3.9.0 (2026-03) | v1.55.0 (2026-03) | v12.4.2 (2026-03) |
| **pip 설치 크기** | ~1.5MB | ~5MB | ~15MB | ~9.1MB wheel | Docker 전용 |
| **Docker 이미지 추가** | +2MB | 불필요 가능 | +20MB | +250MB | +400MB (별도 컨테이너) |
| **WebSocket/SSE** | ✅ SSE 네이티브 구현됨 | ❌ (터미널 전용) | ✅ WebSocket | ✅ | ✅ |
| **현행 연동 가능성** | ✅ 이미 구현됨 | 별도 구현 | FastAPI 마운트 가능 | 별도 서버 필요 | 별도 인프라 |
| **원클릭 적합성** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |

---

## Phase 3: 경량화 권고 보고서

### 3-A. 현행→제안 비교표 (우선순위 순)

| # | 현행 항목 | 제안 대체 | 예상 효과 | 적용 난이도 |
|---|-----------|-----------|-----------|------------|
| **R-01** | `claude-agent-sdk` 185MB (CLI 바이너리 184MB 번들) | SDK 제거, `claude_agent_runner.py`는 subprocess 직접 호출(`claude_code_runner.py` 방식과 동일화) | **-184MB** (venv 36% 감소) | **하** |
| **R-02** | `matplotlib`+`PIL`+`fontTools`+`numpy` (간접 유입, 런타임 미사용, 69MB) | pyproject.toml extras 정리 + Dockerfile runtime stage `--no-deps` 또는 명시적 제외 | **-69MB** | **하** |
| **R-03** | `mypy`+`mypyc`+`black` 프로덕션 이미지 포함 (34MB) | Dockerfile builder stage에만 설치, runtime stage COPY 제외 | **-34MB** | **하** |
| **R-04** | `telethon` 프로덕션 포함 (13MB) | `test` extras로 이동, `requirements-e2e.txt` 분리 | **-13MB** | **하** |
| **R-05** | `FastAPI`+`uvicorn` pyproject.toml 누락 | `dependencies`에 `"fastapi>=0.100"`, `"uvicorn>=0.20"` 추가 | 설치 안정성 향상 | **하** |
| **R-06** | `pip install -e .[dev]` 원클릭 기본값 | `uv sync --no-dev` 기본값 전환, Dockerfile `pip install uv && uv sync` 패턴 | 설치 **10~100x 빠름**, 이미지 -5~10% | **중** |
| **R-07** | `anthropic` SDK + `claude-agent-sdk` 중복 의존 | R-01 완료 후 `claude` extras를 `anthropic`만으로 단순화 | 중복 제거, -0MB (anthropic 유지) | **하** (R-01 선행 필요) |
| **R-08** | `httpx` runtime extras 포함 | `test` extras로 이동 (런타임 미사용 확인됨) | **-3MB** | **하** |

### 3-B. 최소 의존성 구성 제안 (Minimal Viable Stack)

```toml
# pyproject.toml 권장 구성 (경량화 후)
[project]
dependencies = [
    "python-telegram-bot>=22.0",   # 봇 프레임워크 (7.5MB)
    "pydantic>=2.0",               # 데이터 검증 (8.3MB)
    "aiosqlite>=0.19",             # 비동기 DB (132KB)
    "python-dotenv>=1.0",          # 환경변수 (60KB)
    "loguru>=0.7",                 # 로깅 (516KB)
    "PyYAML>=6.0",                 # YAML 파싱 (400KB)
    "apscheduler>=3.10.0",         # 스케줄러 (480KB)
    "rank-bm25>=0.2",              # 메모리 검색 (12KB)
    "mcp>=1.0",                    # MCP 서버 (2MB)
    "fastapi>=0.100",              # REST API + 대시보드 (1.5MB) ← 추가
    "uvicorn>=0.20",               # ASGI 서버 (500KB) ← 추가
]

[project.optional-dependencies]
claude  = ["anthropic>=0.80"]           # claude-agent-sdk 제거, anthropic만 유지
codex   = ["openai>=2.0"]
gemini  = ["google-genai>=1.0"]
test    = ["pytest>=7.0", "pytest-asyncio>=0.21", "pytest-mock>=3.0",
           "pytest-timeout>=2.1", "httpx>=0.25", "telethon>=1.0"]  # telethon 이동
dev     = ["ruff>=0.1", "mypy>=1.10", "black>=23.0",
           "build>=1.0", "twine>=5.0"]  # 빌드 도구만
```

**예상 결과**: 현행 516MB → **약 195~220MB** (~58% 감소)

### 3-C. 실시간 대시보드 스택 Top 3 추천

| 순위 | 스택 | 추천 이유 | 추가 작업량 |
|------|------|-----------|------------|
| 🥇 **1위** | **FastAPI + SSE (현행 유지·개선)** | 이미 구현됨(`dashboard.py`+`core/api/routes/events.py`), SSE 스트림 `/api/v1/events/stream` 작동 중, 1.5MB 경량, 추가 의존성 0 | pyproject.toml에 `fastapi`+`uvicorn` 추가 1줄만 필요 |
| 🥈 **2위** | **Textual TUI** | 2MB 이하 경량, 터미널 기반 실시간 모니터링, Docker 없이 로컬 운영 가능, 35k Stars 급성장 | 별도 `dashboard_tui.py` 구현 (~300줄 내외) |
| 🥉 **3위** | **NiceGUI** | WebSocket 기반 반응형 웹 UI, FastAPI 위에 마운트 가능, 모바일 접근, AI/로봇 대시보드 레퍼런스 풍부 | 기존 FastAPI 앱에 `ui.run(app=app)` 마운트, ~15MB 추가 |

> Streamlit 제외 이유: 50MB+ + 자체 서버 구조 — 기존 FastAPI와 구조적 충돌, 오버킬
> Grafana OSS 제외 이유: 별도 컨테이너 400MB+, Prometheus 연동 인프라 필요 — aimesh 규모 대비 과도

---

## 핵심 요약 (기획실·개발실 PRD 활용용)

### 경량화 로드맵 (난이도 하 → 즉시 실행 가능)

```
Step 1 (즉시, 하): claude-agent-sdk 제거 → -184MB
Step 2 (즉시, 하): matplotlib/PIL/fontTools/numpy extras 정리 → -69MB
Step 3 (즉시, 하): mypy/black Dockerfile runtime stage 제외 → -34MB
Step 4 (즉시, 하): telethon → test extras 이동 → -13MB
Step 5 (즉시, 하): fastapi+uvicorn pyproject.toml dependencies 추가
Step 6 (단기, 중): uv 기본값 전환 (설치 10~100x 빠름)
────────────────────────────────────────────────────
총 감소: ~300MB | 516MB → ~216MB (58% 감소)
원클릭 셋팅: 현행 6~8단계 → uv 전환 시 2~3단계
```

### 출처 목록
1. aimesh pyproject.toml, Dockerfile, docker-compose.yml, requirements-*.txt (로컬 분석)
2. .venv/lib/python3.14/site-packages/ 디렉토리 용량 측정 (du -sh)
3. [python-telegram-bot GitHub](https://github.com/python-telegram-bot/python-telegram-bot) — v22.7 (2026-03-16)
4. [aiogram GitHub](https://github.com/aiogram/aiogram) — v3.26.0 (2026-03-02)
5. [Telethon GitHub (archived 2026-02)](https://github.com/LonamiWebs/Telethon)
6. [uv GitHub (astral-sh)](https://github.com/astral-sh/uv) — 82,336 Stars
7. [uv Docker integration docs](https://docs.astral.sh/uv/guides/integration/docker/)
8. [FastAPI GitHub](https://github.com/fastapi/fastapi) — v0.135.2
9. [NiceGUI GitHub](https://github.com/zauberzeug/nicegui) — v3.9.0 (2026-03-19)
10. [Textual GitHub](https://github.com/Textualize/textual) — v7.3.0 (2026-01)
11. [Grafana GitHub](https://github.com/grafana/grafana) — v12.4.2 (2026-03-25)
12. [HTTPX vs aiohttp benchmark (decodo)](https://decodo.com/blog/httpx-vs-requests-vs-aiohttp)
13. [uv 100x faster benchmark (Analytics Vidhya)](https://www.analyticsvidhya.com/blog/2025/08/uv-python-package-manager/)
