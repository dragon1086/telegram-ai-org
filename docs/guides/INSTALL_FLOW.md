# install.sh 플로우 설계 문서

> **Phase 1 산출물** — telegram-ai-org 원클릭 셋업 스크립트 설계
> 작성일: 2026-03-30 | 담당: 개발실

---

## 1. 배경 및 목적

`scripts/setup.sh` 는 Docker 모드·자동 엔진 설치·대화형 프롬프트 등 다양한 고급 기능을 포함한 56KB 스크립트다.
신규 사용자에게는 너무 무겁고 진입점도 직관적이지 않다 (`scripts/` 하위에 위치).

`install.sh` (프로젝트 루트)는 **4단계 핵심 플로우만** 담은 경량 원클릭 진입점으로,
기존 `setup.sh` 의 고급 기능은 유지하면서 중복 없이 보완한다.

---

## 2. 엔진별 감지 조건 목록

| 엔진 | 우선 탐색 경로 | PATH fallback | 버전 확인 | 인증 파일 |
|------|----------------|---------------|-----------|-----------|
| **claude-code** | `~/.local/bin/claude` → `~/bin/claude` → `/opt/homebrew/bin/claude` → `/usr/local/bin/claude` | `command -v claude` | `claude --version` | `~/.claude/` (OAuth 자동) |
| **codex** | `~/.local/bin/codex` → `~/bin/codex` → `/opt/homebrew/bin/codex` → `/usr/local/bin/codex` | `command -v codex` | `codex --version` | `~/.codex/auth.json` |
| **gemini-cli** | `/opt/homebrew/bin/gemini` → `~/.local/bin/gemini` → `~/bin/gemini` | `command -v gemini` | `gemini --version` | `~/.gemini/oauth_creds.json` |

### 감지 판단 기준
- `[ -x "$path" ]` — 실행 가능 바이너리 확인
- `command -v <name>` — PATH 등록 여부 fallback
- 감지 실패 → `⚠️` 경고 출력 + 설치 안내 (exit 하지 않음)
- 모든 엔진 미감지 시 → `❌` 오류 + exit 1 (헬스체크 전용 모드 제외)

---

## 3. 의존성 목록

### Python 패키지 (pyproject.toml `[project].dependencies`)
| 패키지 | import 이름 | 용도 |
|--------|------------|------|
| python-telegram-bot | `telegram` | Telegram Bot API |
| pydantic | `pydantic` | 데이터 검증 |
| aiosqlite | `aiosqlite` | 비동기 SQLite |
| httpx | `httpx` | HTTP 클라이언트 |
| python-dotenv | `dotenv` | .env 로드 |
| loguru | `loguru` | 로깅 |
| anthropic | `anthropic` | Claude API SDK |
| openai | `openai` | OpenAI/Codex SDK |
| PyYAML | `yaml` | YAML 파싱 |
| apscheduler | `apscheduler` | 스케줄링 |
| google-genai | `google.genai` | Gemini SDK (gemini-cli 감지 시) |

### 시스템 의존성
| 도구 | 버전 | 용도 |
|------|------|------|
| Python | ≥ 3.10 | 런타임 |
| Node.js | ≥ 18 | 엔진 CLI (npm 기반) |
| npm | - | 엔진 설치 도구 |

---

## 4. 헬스체크 방법

### 엔진 헬스체크
```bash
# claude-code
"$CLAUDE_PATH" --version   → 출력 있으면 ✅, 없거나 오류면 ❌

# codex
"$CODEX_PATH" --version    → 출력 있으면 ✅

# gemini-cli
"$GEMINI_CLI_PATH" --version → 출력 있으면 ✅
```

### Python 패키지 헬스체크
```bash
"$VENV_PYTHON" -c "import <pkg>" 2>/dev/null
# 0 exit → ✅ / 비0 exit → ❌ (설치 필요 안내 포함)
```

---

## 5. install.sh 전체 플로우

```
bash install.sh [flags]
        │
        ├── [--health-only]  ─────────────────────────→ ④ 헬스체크만 실행 후 종료
        │
        ▼
① 3엔진 자동 감지 (항상 실행)
   CLAUDE_PATH / CODEX_PATH / GEMINI_CLI_PATH_DETECTED 설정
   DETECTED_ENGINES[] 배열 구성
   SELECTED_ENGINE 결정 (claude-code 우선, 없으면 감지 첫 번째)
        │
        ├── [--health-only] → ④ 헬스체크
        │
        ▼
② .env 자동 생성
   .env.example 존재 확인 (없으면 exit 1)
   .env 미존재 → cp .env.example .env
   .env 존재  → 기존 유지 (ENGINE 변수만 갱신)
   자동 주입 항목:
     AI_ENGINE / DEFAULT_ENGINE / ENGINE / ACTIVE_ENGINE = SELECTED_ENGINE
     CLAUDE_CLI_PATH / CODEX_CLI_PATH / GEMINI_CLI_PATH = 감지된 경로
        │
        ▼
③ 의존성 자동 설치
   Python 3.10+ 탐색 (python3.13 → python3.10 → python3 순)
   [--no-venv 없으면] .venv/ 생성 → VENV_PYTHON 설정
   pip install -e ".[dev]"  (실패 시 requirements.txt 또는 핵심 패키지 직접 설치)
   gemini-cli 감지 시 google-genai 추가 설치
   Node.js / npm 존재 여부 확인 (미설치 시 경고)
   mkdir -p ~/.ai-org/workspace logs data reports
   chmod +x scripts/*.sh install.sh
        │
        ├── [--skip-verify] → 완료 요약 출력 후 종료
        │
        ▼
④ 헬스체크 (✅/❌ 출력)
   ── 엔진 헬스체크 ──
   claude-code: --version 테스트 → ✅/❌  (미감지 시 ⬜ 건너뜀)
   codex:       --version 테스트 → ✅/❌
   gemini-cli:  --version 테스트 → ✅/❌
   ── Python 패키지 헬스체크 ──
   import anthropic / telegram / pydantic / aiosqlite / dotenv
        / loguru / yaml / apscheduler → 각각 ✅/❌
   (gemini-cli 감지 시) import google.genai → ✅/❌
   ── 결과 요약 ──
   HC_PASS / HC_FAIL 집계 → 전체 합격/일부 실패 메시지
        │
        ▼
완료 요약 출력
   다음 단계 안내:
   1. nano .env → 필수 토큰 입력
   2. 엔진별 인증 안내 (claude OAuth / gemini auth login)
   3. bash scripts/start_all.sh → 봇 실행
   info: 고급 옵션은 bash scripts/setup.sh --help
```

---

## 6. setup.sh 와의 역할 분리 (중복 제거 전략)

| 기능 | install.sh | scripts/setup.sh |
|------|-----------|-----------------|
| 3엔진 감지 | ✅ (핵심 구현) | ✅ (고급: 자동 설치 포함) |
| .env 생성 | ✅ (간결) | ✅ (대화형 토큰 수집 포함) |
| 의존성 설치 | ✅ (uv/pip) | ✅ (Node.js 자동 설치 포함) |
| 헬스체크 | ✅ (✅/❌ 포맷 명확) | ✅ (Step 5, 동일 포맷) |
| Docker Compose | ❌ | ✅ (--docker 플래그) |
| 엔진 자동 설치 | ❌ (경고만) | ✅ (npm/brew 자동 설치) |
| 대화형 토큰 입력 | ❌ | ✅ |
| macOS 권한 설정 | ❌ | ✅ |

**중복 제거 패치**: `scripts/setup.sh` 상단에 install.sh가 기본 진입점임을 명시.
헬스체크 로직은 양쪽에 유지 (install.sh --health-only 로도 독립 실행 가능).

---

## 7. 플래그 목록

| 플래그 | 효과 |
|--------|------|
| `--yes` / `-y` | 비대화형 자동 설치 (CI 환경) |
| `--no-venv` | 가상환경 생성 건너뜀 |
| `--skip-verify` | 헬스체크 단계 건너뜀 |
| `--health-only` | 헬스체크만 실행 (설치/설정 없음) |
