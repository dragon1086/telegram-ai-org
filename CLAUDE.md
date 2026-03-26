# CLAUDE.md

이 파일은 Claude Code가 이 저장소에서 작업할 때 자동으로 읽는 프로젝트 지침이다.

> **3개 컨텍스트 파일 동기화 원칙**: CLAUDE.md / AGENTS.md / GEMINI.md 는 항상 동시에 수정한다.
> 이 파일을 수정하면 반드시 AGENTS.md와 GEMINI.md도 같은 내용으로 업데이트한다.

## 프로젝트 개요

`telegram-ai-org` — Telegram 그룹 채팅방을 AI 조직의 오피스로 쓰는 멀티봇 오케스트레이션 시스템.

- PM 봇이 태스크를 적합한 워커 봇에 자율 배분
- 봇마다 성격·기억·캐릭터 진화, 팀워크/칭찬 시스템, 자연어 스케줄 등록 지원
- 실행 엔진: `claude-code` / `codex` / `gemini-cli` 중 봇별 설정 (bots/*.yaml 참조)

## 오픈소스화 목표 (2026-03-24 기준 최우선 과제)

> **미션**: telegram-ai-org 오픈소스화 + 원클릭 풀셋팅 서비스 패키징 (7일 내 완료)
> 상세 계획: `docs/OPENSOURCE_PLAN.md` 참조

## 환경 설정

```bash
# 가상환경 활성화 (항상 venv 사용)
source .venv/bin/activate

# 또는 직접 경로로
./.venv/bin/python ...
./.venv/bin/pytest ...
```

`.env` 파일에 `PM_BOT_TOKEN`, `COKAC_BOT_TOKEN` 등 봇 토큰 필수.

### CLI 경로 설정 (.env)
```bash
CLAUDE_CLI_PATH=/Users/rocky/.local/bin/claude
CODEX_CLI_PATH=/opt/homebrew/bin/codex
GEMINI_CLI_PATH=/opt/homebrew/bin/gemini  # Gemini CLI (OAuth 기반, gemini auth login 필요)
GEMINI_CLI_DEFAULT_TIMEOUT_SEC=1800       # 긴 리서치 태스크 대응 (30분)
GEMINI_CLI_MODEL=gemini-2.5-flash         # 기본 모델 (gemini-2.0-flash 사용 금지)
```

## 주요 명령어

```bash
# 전체 봇 시작
bash scripts/start_all.sh

# 테스트 실행
./.venv/bin/pytest -q
./.venv/bin/pytest tests/test_pm_orchestrator.py -q
./.venv/bin/pytest tests/test_pm_routing.py -q

# 린트
./.venv/bin/ruff check .
```

## 핵심 경로

| 경로 | 역할 |
|------|------|
| `main.py` | 로컬 진입점 |
| `core/pm_orchestrator.py` | PM 오케스트레이션 메인 루프 |
| `core/pm_router.py` | 태스크 → 워커 라우팅 |
| `core/nl_classifier.py` | 자연어 분류기 |
| `core/scheduler.py` | 내장 스케줄러 |
| `core/nl_schedule_parser.py` | 자연어 스케줄 파싱 |
| `core/bot_character_evolution.py` | 봇 캐릭터 진화 |
| `core/shoutout_system.py` | 팀워크·칭찬 시스템 |
| `core/lesson_memory.py` | 교훈 메모리 |
| `core/telegram_relay.py` | Telegram 메시지 중계 |
| `core/context_window.py` | PM 대화 히스토리 컨텍스트 창 유틸리티 |
| `workers.yaml` | 워커 봇 등록부 |
| `orchestration.yaml` | 오케스트레이션 설정 |
| `bots/` | 봇 YAML 정의 |
| `tests/` | pytest 회귀 커버리지 |

## 주요 명령어 (추가)

```bash
# E2E 회귀 테스트 전체 실행
./.venv/bin/pytest tests/e2e/ -q

# 오케스트레이션 설정 검증
./.venv/bin/python tools/orchestration_cli.py validate-config
```

## 운영 주의사항 (누적)

> 세션 시작 시 반드시 확인. 실수가 발생할 때마다 여기에 추가한다.

### [2026-03-26] 엔진 전환 — 운영실 codex → gemini-cli (임시)
- **배경**: OpenAI Codex CLI rate limit 도달 → 운영실(aiorg_ops_bot)을 gemini-cli로 임시 전환
- **변경 파일**: `bots/aiorg_ops_bot.yaml`, `orchestration.yaml` (team_profiles), `.env.example`, AGENTS.md, GEMINI.md
- **현재 엔진 배정**:
  | 조직 | 엔진 |
  |------|------|
  | PM / 개발실 / 디자인실 / 기획실 | claude-code |
  | 성장실 / 리서치실 / **운영실** | **gemini-cli** |
- **복원 조건**: Codex 리밋 해소 시 `bots/aiorg_ops_bot.yaml` engine: 다시 `codex`로 변경

### [2026-03-25] 자율 협업 실행 원칙 — "다음 조치 = 즉시 실행" (전체 조직 필수)

**가장 중요한 원칙**: "다음 조치"를 나열하고 끝내는 것은 안티패턴이다. 나열하는 순간 즉시 실행한다.

#### 자동 트리거 메시지 처리 (PM 봇 필수)
아래 메시지 패턴을 수신하면 사용자 확인 없이 즉시 pm-progress-tracker 스킬을 실행한다:

| 트리거 패턴 | 즉시 실행 액션 |
|------------|--------------|
| `## 🔄 일일 목표 파이프라인` | pm-progress-tracker 스킬 → 잔여 TODO 즉시 배분 |
| `## 🔬 Harness Audit` / `harness-audit` 결과 | STALE 목표 자동 iter 재개 |
| `⚠️ STALE` 포함 | 해당 목표 iter 즉시 재개 → COLLAB 태그로 부서 배분 |
| `[주간회의 보고 요청]` | 해당 조직 주간 현황 보고 (200자 이내) 즉시 제출 |
| `[일일 회고]` | 오늘 완료/미완료 집계 → 미완료 → pm_progress_guide.md TODO 등록 |

#### COLLAB 태그 의무 사용 조건 (모든 조직 공통)
아래 상황에서는 반드시 `[COLLAB:태스크 설명|맥락: ...]` 태그를 응답에 포함한다:

```
✅ COLLAB 태그 사용해야 하는 상황:
- 개발 완료 후 배포가 필요할 때 → [COLLAB:배포 요청|맥락: 구현 완료]
- 리서치 선행이 필요한 구현 태스크 → [COLLAB:리서치 요청|맥락: 구현 전 선행 조사]
- UI 변경이 포함된 개발 태스크 → [COLLAB:UX 검토 요청|맥락: 신규 화면 설계]
- 주간회의/회고 조치사항 중 타부서 담당 → [COLLAB:조치사항|맥락: 주간회의]
- iter 배분 시 타부서 태스크 → [COLLAB:서브태스크 설명|맥락: GOAL-XXX iter N]

❌ COLLAB 없이 처리하는 것은 "봇들이 고립되어 일하는" 안티패턴
✅ COLLAB 태그는 봇들이 유기적으로 협업하는 핵심 메커니즘
```

#### 자율 iter 실행 체인 (PM 봇 세션 시작 시 항상 실행)
```
1. memory/pm_progress_guide.md 읽기
2. IN_PROGRESS 목표 + 잔여 TODO 확인
3. TODO 서브태스크 > 0 이면:
   - 개발실 담당 → [TEAM:engineering-senior-developer] 즉시 실행
   - 운영실 담당 → [COLLAB:태스크|맥락: GOAL iter] 즉시 위임
   - 디자인/리서치 담당 → [COLLAB:태스크|맥락: GOAL iter] 즉시 위임
4. STALE(3일 이상 진척 없음) → harness-audit 결과와 함께 자동 재개
5. 이터레이션 로그 업데이트
```

### [2026-03-25] PM 진척관리 스킬 & 이터레이션 루프 (전체 조직 공통)
- **스킬 위치**: `skills/pm-progress-tracker/skill.md`
- **목표 문서**: `memory/pm_progress_guide.md` (세션 시작 시 반드시 읽을 것)
- **규칙**: 사용자 큰 목표 수신 시 → 즉시 pm_progress_guide.md에 등록 → 이터레이션 루프 시작
- **자동화**: `daily_goal_pipeline` (orchestration.yaml) — 매일 09:00 KST 아침 목표를 GoalTracker에 자동 등록 → 부서 위임
- **상태 관리**: TODO / IN_PROGRESS / DONE / BLOCKED 4가지 상태로 모든 목표 추적
- **완료 원칙**: 완료 조건 충족 시 DONE 처리 / 미충족 시 자율 재루프 (사용자 확인 불필요)

### [2026-03-25] E2E 자율 루프 운영 원칙 (전체 조직 공통)

**구현 완료** — `goal_tracker/goal_tracker_client.py`, `goal_tracker/multibot_meeting_handler.py`, `run_e2e_loop.py`, `tests/e2e/test_autonomous_loop_e2e.py` (37개 테스트 통과)

#### 트리거 조건
| 트리거 | 처리 모듈 | 등록 대상 |
|--------|----------|----------|
| 일일회고 채팅 감지 | `MultibotMeetingHandler` | `조치사항:` 체크박스 아이템 |
| 주간회의 채팅 감지 | `MultibotMeetingHandler` | 부서별 보고 + 조치사항 |
| 크론 `daily_retro.py` | `GoalTrackerClient.register_report()` | 회고 MD에서 자동 추출 |

#### GoalTracker 등록 규칙
- `[ ]` 형식의 체크박스 아이템만 등록 (`goal_tracker/report_parser.py`)
- 동일 제목 키워드(10자 정규화) 기준 중복 방지
- `meeting_type`, `priority`, `assigned_dept`, `due_date` 자동 추출

#### 멀티봇 참여 프로토콜
- 참여 순서: 개발실 → 운영실 → 디자인실 → 기획실 → 성장실 → 리서치실
- 봇 간 인터벌: 3.0초 (기본값)
- 중복 방지: `{meeting_type}_{date}` 기준 당일 재처리 방지 (`force=True` 시 무시)
- 상세 가이드: `docs/AUTONOMOUS_LOOP.md`

#### 루프 상태 전이
```
IDLE → EVALUATE → REPLAN → DISPATCH → IDLE
                ↓              ↓
              IDLE (달성)   IDLE (태스크 없음)
```

### [2026-03-24] 3개 컨텍스트 파일 동시 수정 원칙 (전체 조직 공통)
- **원칙**: CLAUDE.md / AGENTS.md / GEMINI.md 는 반드시 동시에 수정한다
- **이유**: 각 엔진(Claude Code / Codex / Gemini CLI)이 자신의 컨텍스트 파일만 읽음 → 한 파일만 수정하면 나머지 엔진에 정보 불일치 발생
- **실행 방법**: 한 파일 수정 완료 → 바로 나머지 두 파일도 동일 내용 반영
- **CLAUDE.md가 기준**: 가장 상세하게 유지. AGENTS.md와 GEMINI.md는 여기서 동기화

### [2026-03-25] CI/CD 파이프라인 운영 규칙
- `.github/workflows/ci-lint.yml` 은 `pull_request`, `main` push, `workflow_dispatch` 기준으로 Ruff lint를 수행한다.
- `.github/workflows/ci-e2e.yml` 은 `pull_request`, `main` push, `workflow_dispatch` 기준으로 `claude-code` / `codex` / `gemini-cli` 3엔진 matrix에서 `python tools/orchestration_cli.py validate-config` 와 `pytest tests/e2e/ -q --tb=short` 를 실행한다.
- `.github/workflows/publish-pypi.yml` 은 `v*` 태그 push 또는 수동 `workflow_dispatch` 시 `verify` 후 `python -m build` / `twine upload` 로 PyPI 패키지를 배포한다.
- `.github/workflows/docker-build.yml` 은 `v*` 태그 push 또는 수동 `workflow_dispatch` 시 `verify` 후 Docker Buildx 로 이미지를 빌드하고 Docker Hub 에 푸시한다.
- GitHub Actions secret 이름은 `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `GEMINI_OAUTH_CREDS`, `CLAUDE_CODE_OAUTH_TOKEN`, `PYPI_TOKEN`, `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` 을 사용한다.
- Gemini CI는 `GEMINI_OAUTH_CREDS` 가 있으면 `~/.gemini/oauth_creds.json` 으로 복원해 사용한다.
- `ci-lint` 와 `ci-e2e` 를 branch protection required checks 로 묶어 `main` 배포 전 테스트를 강제한다.
- 상세 운영 절차와 로컬 재현 명령은 `docs/CI_CD_GUIDE.md` 를 따른다.

### [2026-03-21] ⚠️ 배포 행위는 운영실(aiorg_ops_bot) 전담 — 전체 조직 적용
- **원칙**: 운영실을 제외한 **모든 specialist 조직**은 로컬 커밋까지만 수행. 아래 세 가지는 운영실(@aiorg_ops_bot)만 실행:
  ```
  ❌ 운영실 외 자체 수행 금지 (조직 추가 시에도 동일 적용):
    git push / git merge / 봇 재기동(restart_bots.sh, request_restart.sh)

  ✅ 완료 후 운영실에 COLLAB 위임:
    "[COLLAB:머지/푸시/재기동 요청|맥락: 코드 수정 완료]"
  ```
- **글로벌 적용 위치**: bot-triage/SKILL.md Step 3d, pm_identity.py 봇 재기동 규칙 섹션, pm-task-dispatch/SKILL.md 안티패턴 항목
- **새 조직 추가 시**: organizations.yaml에 추가만 하면 위 글로벌 규칙이 자동 적용됨 (per-org 중복 명시 불필요)

### [2026-03-25] Docker Compose 다중 엔진 실행 가이드

서비스 구조: `x-bot-common`(공통 앵커) + 엔진 프로파일 3개 (`claude` / `codex` / `gemini`)

```bash
# 1. 환경변수 준비
cp .env.example .env
# .env에 최소값 입력: TELEGRAM_BOT_TOKEN, BOT_TOKEN_* 6개, ANTHROPIC/OPENAI/GEMINI API 키

# 2. 단일 엔진 실행 (예: Claude 계열 — PM/기획/디자인)
docker compose --profile claude up -d

# 3. 특정 엔진 실행 (Codex: 개발/운영, Gemini: 성장/리서치)
docker compose --profile codex up -d
docker compose --profile gemini up -d

# 4. 전체 조직 동시 실행
docker compose --profile claude --profile codex --profile gemini up -d

# 5. 로그 확인
docker compose ps
docker compose logs -f aiorg-pm
```

볼륨 마운트: `./logs`, `./data`, `./reports`, `./tasks`, `./skills`(read-only)
엔진별 자동 주입: `ENGINE_TYPE`, `*_CLI_PATH`, `GEMINI_CLI_MODEL` (각 서비스 environment 블록)

### [2026-03-25] 로컬 패키지 설치 — pip install -e . 사용 가능 (setuptools 전환 완료)
- **빌드 백엔드**: hatchling → setuptools+wheel 전환 완료 (`pyproject.toml` 기준)
- **로컬 설치**: `pip install -e .` 이제 정상 작동
  ```bash
  # 로컬 개발 설치 (editable 모드)
  .venv/bin/pip install -e .

  # 개발 도구 포함 설치
  .venv/bin/pip install -e ".[dev]"

  # 봇 재시작 전 패키지 동기화
  .venv/bin/pip install -e . && bash scripts/start_all.sh
  ```
- **PyPI 배포**: `python -m build --wheel --sdist` → `twine upload dist/*`
- **twine 검증**: `twine check dist/*` (PASS 확인됨)

### [2026-03-22] 현재 시간 기준 작업 원칙 (전체 조직 공통)
- **원칙**: 모든 봇은 태스크 시작 시 현재 날짜/시각을 확인하고, 사용자가 과거 시점을 명시하지 않는 한 항상 **현재 시각 기준**으로 조사·판단한다.
- **적용 범위**: 웹검색, 모델/라이브러리 버전 확인, 시장조사, 레퍼런스 조사 등 시간 의존성 있는 모든 작업
- **산출물 표기**: 보고서·분석물에 "YYYY-MM-DD 기준" 조사 시점을 반드시 명시
- **글로벌 적용 위치**: `orchestration.yaml` → `global_instructions` 섹션 "현재 시간 사용 원칙"

### [2026-03-22] 안전 코드 수정 방법론 — safe-modify 스킬 (전체 조직 공통)

> 실패 감지(failure-detect) 코드 및 고위험 경로 수정 시 아래 6개 방법론을 반드시 따른다.
> 상세 절차: `skills/safe-modify/SKILL.md`

**6개 핵심 원칙 요약**:

| 원칙 | 한 줄 요약 | 실무 규칙 |
|------|-----------|-----------|
| **Defensive Programming** | 예상 밖 입력에서도 안전 기본값 반환 | Guard Clause 우선, `except: pass` 금지 |
| **Minimal Footprint** | 최소 범위만 변경 | PR당 파일 3개 이하, 시그니처 유지 |
| **Feature Flags** | 새 로직은 flag 뒤에 감추기 | 판정 로직 변경 시 Feature Flag 필수 |
| **Idempotency** | 동일 입력 → 동일 출력 | 전역 상태 변경 금지, 순수 함수 지향 |
| **CRAP 점수 관리** | 복잡도 × 미커버리지 = 위험도 | CRAP > 30이면 테스트 먼저, 수정 금지 |
| **산업 표준 체크리스트** | Google/Shopify/Netflix 공통 원칙 | Dark Launch → 실패 주입 테스트 → 롤백 경로 확인 |

**절대 금지 항목** (failure-detect 코드 수정 시):
- `except: pass` 예외 삼킴
- LLM fallback 경로 제거
- confidence 임계값(0.85, 0.60) 테스트 없이 변경
- 한 PR에서 복수 판정 경로 동시 수정

**실전 엣지케이스 축적**: `skills/safe-modify/gotchas.md` — 실제 인시던트 기반 7개 Gotcha (confidence 임계값 변경, 예외 삼킴, Minimal Footprint 위반 등)

**트리거**: `safe-modify`, `안전 수정`, `failure detect 수정`, `스코프 제한`, `부작용 최소화`

### [2026-03-22] Gemini Flash 모델 버전 — gemini-2.5-flash 사용
- **현황**: `gemini-2.0-flash` → `gemini-2.5-flash` 로 업데이트 (2026-03-22 기준 최신 안정화 버전)
- **주의**: 사용자가 "3.1 flash"로 알고 있었으나, 실제 Google 공식 최신 stable 모델은 `gemini-2.5-flash`. 3.x 계열은 Preview 단계임.
- **변경 파일**: `tools/gemini_runner.py` (기본값 변경), `tools/base_runner.py` (주석 갱신)
- **Deprecated**: `gemini-2.0-flash` 는 2026-06-01 서비스 종료 예정

### [2026-03-23] ⛔ 위험한 시스템 CLI/파일 탐색 절대 금지 (전체 조직 공통)

**인시던트**: 봇 에이전트가 `glob.glob(str(Path.home()) + '/**/*.db', recursive=True)` 를 직접 생성·실행 → 홈 디렉토리 전체 재귀 탐색으로 CPU 68% 30분 이상 점유, 시스템 메모리 고갈 발생.

**절대 금지 패턴** (에이전트가 코드 생성·실행 시 포함 금지):

```python
# ❌ 홈/루트 전체 재귀 탐색
glob.glob(str(Path.home()) + '/**/*', recursive=True)
glob.glob('/Users/**/*', recursive=True)
os.walk(Path.home())
os.walk('/')

# ❌ 쉘에서도 동일하게 금지
find ~ -name '*.db'
find / -name '*.db'
```

**허용 패턴** — 반드시 프로젝트 디렉토리 내로 스코프 제한:

```python
# ✅ 프로젝트 루트 내부만
glob.glob('/Users/rocky/telegram-ai-org/**/*.db', recursive=True)
# ✅ 환경변수로 프로젝트 경로 특정
glob.glob(os.environ['CLAUDE_PROJECT_DIR'] + '/**/*.db', recursive=True)
# ✅ 산출물 저장소 (AI_ORG_DATA_DIR 기반 — telegram-ai-org 외부 허용)
glob.glob(os.environ.get('AI_ORG_DATA_DIR', str(Path.home() / 'telegram-ai-org-data')) + '/**/*', recursive=True)
```

**적용 범위**: 에이전트가 직접 작성·실행하는 모든 Python/shell 코드, subprocess 호출, Bash tool 사용 포함.
**글로벌 적용 위치**: `orchestration.yaml` → `global_instructions` 섹션 "위험한 시스템 탐색 금지"

### [2026-03-22] PM 봇 대화 히스토리 컨텍스트 창 튜닝
PM 봇은 작업 배분 판단 시 최근 대화 이력을 `[CONTEXT]...[/CONTEXT]` 블록으로 프롬프트에 주입한다.
아래 환경변수로 런타임 조정 가능 (`.env` 또는 실행 환경):

| 환경변수 | 기본값 | 설명 |
|----------|--------|------|
| `MAX_HISTORY_MESSAGES` | `10` | 히스토리에 포함할 최대 메시지 수 |
| `MAX_HISTORY_TOKENS` | `2000` | 히스토리 컨텍스트 전체 토큰 한도 (근사치) |

**튜닝 기준**:
- 짧은 세션(5턴 이하): 기본값(`10`, `2000`) 유지
- 복잡한 멀티턴 태스크: `MAX_HISTORY_MESSAGES=20`, `MAX_HISTORY_TOKENS=4000`
- API 비용 절감 필요 시: `MAX_HISTORY_MESSAGES=5`, `MAX_HISTORY_TOKENS=1000`
- 50턴 이상 장기 세션에서도 토큰 초과 방지 로직이 자동 동작함

**관련 파일**:
- `core/context_window.py` — `build_context_window()`, `format_history_for_prompt()` 구현
- `core/telegram_relay.py` (L1665~1703) — PM 핸들러 컨텍스트 주입 지점
- `tests/test_context_window.py` — 단위 테스트 (16개)
- `tests/test_pm_context_injection.py` — 통합 테스트 (7개)

### [2026-03-26] AI_ORG_DATA_DIR — 산출물·데이터 저장 경로 표준화 (전체 조직 공통)
- **원칙**: `telegram-ai-org/`는 오픈소스 코드만 포함. 모든 산출물·생성 코드·스킬 로그는 `AI_ORG_DATA_DIR`에 저장
- **기본값**: `~/telegram-ai-org-data` (환경변수 미설정 시 자동 사용)
- **`.env` 설정**: `AI_ORG_DATA_DIR=~/telegram-ai-org-data`
- **`~/.ai-org/workspace`**: 기존 산출물 보존. 신규 산출물은 `AI_ORG_DATA_DIR`로만 저장
- **스킬 경로**: `${AI_ORG_DATA_DIR:-$HOME/telegram-ai-org-data}/skills/<skill-name>/data/`
- **금지**: `../telegram-ai-org-data/` 상대 경로 하드코딩 (오픈소스 사용자 경로 불일치 유발)

---

## 스킬 전략

`skills/` 디렉토리에 프로젝트 전용 스킬이 있다. 자율 에이전트는 상황에 맞는 스킬을 적극 활용한다.

| 상황 | 사용 스킬 |
|------|-----------|
| 태스크 배분이 필요할 때 | `pm-task-dispatch` |
| 여러 봇 의견 조율이 필요할 때 | `pm-discussion` |
| 코드 병합/배포 전 | `quality-gate` |
| 매주 금요일 | `weekly-review` |
| 스프린트 끝날 때 | `retro` |
| 코드 리뷰 요청 시 | `engineering-review` |
| 실패 감지 / 고위험 코드 수정 시 | `safe-modify` |
| 시스템 점검 시 | `harness-audit` |
| 장시간 루프 실행 시 | `loop-checkpoint` |

### 자율 에이전트 스킬 실행 원칙
- **인터랙티브 스킬 금지**: brainstorming, deep-interview 등 `AskUserQuestion`을 사용하는 스킬은 자율 모드에서 직접 호출하지 않는다.
- **대체 스킬 사용**: 대신 `brainstorming-auto`, `pm-discussion` 등 비인터랙티브 버전을 사용한다.
- **AUTONOMOUS_MODE 원칙**: 불확실하면 합리적 기본값으로 진행하고 로그를 남긴다. 멈추지 않는다.
- **스킬 상세**: `skills/README.md` 참조

## 협업 위임 원칙 (COLLAB — 모든 에이전트 공통)

> 이 원칙은 구조화된 팀 내부에서 실행 중인 에이전트에게도 적용된다.

작업 중 내 역할·전문성 밖의 영역이 등장하면 직접 처리하지 말고 [COLLAB:] 태그로 위임하라.

**위임 판단 기준 (역할 기반, 조직 구성 무관)**

| 상황 | 행동 |
|------|------|
| 이 작업이 내 역할 범위를 벗어난다 | COLLAB 위임 |
| 동료 조직이 이 작업을 나보다 잘 할 수 있다 | COLLAB 위임 |
| 병렬 처리하면 전체 완료가 빨라진다 | COLLAB 위임 |
| 내 판단/조율만 필요하다 | 직접 처리 |

**핵심 질문**: "내가 이걸 직접 해야만 하는가?" → 아니라면 COLLAB

**사용법**:
```
[COLLAB:작업 설명 (구체적이고 실행 가능하게)|맥락: 현재 진행 중인 작업 요약]
```

주의: 위임 후 해당 작업을 중복으로 직접 수행하지 말 것. 결과는 자동으로 전달된다.

## PM 업무 스코프 준수 원칙 (전체 조직 공통 — 최우선)

> 이 원칙은 모든 specialist 조직에 예외 없이 적용된다. 아래 모든 규칙보다 이 원칙이 상위에 위치한다.

- **PM이 해당 태스크에 명시한 "실행 범위" 내의 작업만 수행한다.**
- 명시되지 않은 추가 작업·리팩터링·기능 확장·자기 개선·배포·재기동은 PM의 명시적 지시 없이 수행하지 않는다.
- 스코프 외 작업이 필요하다고 판단되면: PM에게 보고하거나 `[COLLAB]` 태그로 적절한 조직에 위임 요청.
- 모호한 경우에도 임의로 확장하지 말고 PM에게 확인을 구한다.
- 글로벌 적용 위치: `orchestration.yaml` → `global_instructions` (모든 엔진에 자동 주입)

## 개발 규칙

- 변경 범위를 최소화. 타깃 이외 영역 리팩토링 금지.
- async 동작과 기존 public 메서드 시그니처 유지.
- 시크릿/봇 토큰 하드코딩 금지. 환경변수만 사용.
- 줄 길이: Ruff 설정 기준 100자.
- 동작 변경 시 `README.md`, `ARCHITECTURE.md` 동기화.

## Git 워크트리 워크플로 (필수)

> **이 프로젝트를 수정하는 모든 봇/세션에 적용된다.**

현재 브랜치가 `main`이 아닌 상태에서 **새 태스크**(= 현재 브랜치 작업과 무관한 요청)를 받으면, 반드시 아래 절차를 따른다.

### 절차

1. **브랜치 확인**: `git branch --show-current` — `main`이면 평소대로 진행.
2. **워크트리 생성**: `main`이 아니면 임시 워크트리를 만든다.
   ```bash
   git worktree add .worktrees/<task-slug> main
   cd .worktrees/<task-slug>
   git checkout -b fix/<task-slug>
   ```
3. **작업 수행**: 워크트리 안에서 코드 수정 → 테스트 → 커밋.
4. **main에 머지**:
   ```bash
   cd <project-root>
   git checkout main
   git merge fix/<task-slug> --no-ff -m "merge: <설명>"
   ```
5. **정리**:
   ```bash
   git worktree remove .worktrees/<task-slug>
   git branch -d fix/<task-slug>
   ```
6. **원래 브랜치 복귀**: 기존 작업 브랜치로 `git checkout` 복귀.

### 판단 기준

- 현재 브랜치 작업의 **연장선**이면 → 그냥 현재 브랜치에서 계속.
- 현재 브랜치와 **무관한 새 요청**이면 → 워크트리 절차 필수.
- 확신이 없으면 → 워크트리를 쓴다 (안전한 쪽 선택).

## 자주 보는 파일 묶음

PM/라우팅 수정 시:
- `core/pm_orchestrator.py`
- `core/pm_router.py`
- `core/nl_classifier.py`
- `core/telegram_relay.py`

스케줄 수정 시:
- `core/scheduler.py`
- `core/nl_schedule_parser.py`
- `core/user_schedule_store.py`
- `core/bot_commands.py`

캐릭터/팀워크 수정 시:
- `core/bot_character_evolution.py`
- `core/shoutout_system.py`
- `core/collaboration_tracker.py`
- `core/agent_persona_memory.py`
