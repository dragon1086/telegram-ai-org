# GEMINI.md

이 파일은 Gemini CLI가 이 저장소에서 작업할 때 자동으로 읽는 프로젝트 지침이다.

> **3개 컨텍스트 파일 동기화 원칙**: CLAUDE.md / AGENTS.md / GEMINI.md 는 항상 동시에 수정한다.
> 이 파일을 수정하면 반드시 CLAUDE.md와 AGENTS.md도 같은 내용으로 업데이트한다.

## Gemini CLI 특화 정보

- **인증**: OAuth 2.0 기반 (`~/.gemini/oauth_creds.json`). API Key 사용 금지.
- **바이너리 경로**: `/opt/homebrew/bin/gemini` (또는 `$GEMINI_CLI_PATH`)
- **기본 모델**: `gemini-2.5-flash` (2026-03-22 기준 최신 stable GA)
- **금지 모델**: `gemini-2.0-flash` (2026-06-01 서비스 종료 예정)
- **주의**: `gemini-3.x` 계열은 Preview 단계 — 프로덕션 사용 자제
- **실행 방식**: `gemini -p '<prompt>' --output-format json`
- **러너**: `tools/gemini_cli_runner.py` (GeminiCLIRunner)

### Gemini CLI OAuth 인증 설정
```bash
# 최초 1회 인증 (Google Pro Plan 계정)
gemini auth login

# 인증 상태 확인
gemini auth status

# 환경변수 (API Key 환경변수는 subprocess에서 자동 제거)
# GEMINI_API_KEY 및 GOOGLE_API_KEY 는 OAuth 충돌 방지를 위해 제거됨
```

### Gemini CLI 주요 명령어
```bash
# 기본 실행
gemini -p "프롬프트 내용" --output-format json

# 모델 지정
gemini -p "프롬프트" --model gemini-2.5-flash

# 파일 입력 (대용량 컨텍스트)
gemini -p "분석해줘" -f file.txt

# 스트리밍
gemini -p "프롬프트" --stream
```

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
GEMINI_CLI_PATH=/opt/homebrew/bin/gemini
GEMINI_CLI_DEFAULT_TIMEOUT_SEC=1800  # 긴 리서치 태스크 대응 (30분)
GEMINI_CLI_MODEL=gemini-2.5-flash    # 기본 모델 (gemini-2.0-flash 사용 금지)
```

## 주요 명령어

```bash
# 전체 봇 시작
bash scripts/start_all.sh

# 테스트 실행
./.venv/bin/pytest -q
./.venv/bin/pytest tests/test_pm_orchestrator.py -q

# E2E 회귀 테스트
./.venv/bin/pytest tests/e2e/ -q

# 린트
./.venv/bin/ruff check .

# 오케스트레이션 설정 검증
./.venv/bin/python tools/orchestration_cli.py validate-config
```

## 핵심 경로

| 경로 | 역할 |
|------|------|
| `main.py` | 로컬 진입점 |
| `core/pm_orchestrator.py` | PM 오케스트레이션 메인 루프 |
| `core/pm_router.py` | 태스크 → 워커 라우팅 |
| `core/telegram_relay.py` | Telegram 메시지 중계 |
| `core/context_window.py` | PM 대화 히스토리 컨텍스트 창 |
| `tools/gemini_cli_runner.py` | Gemini CLI 러너 (이 엔진의 실행 코드) |
| `tools/gemini_runner.py` | Gemini API SDK 러너 (대안 방식) |
| `bots/` | 봇 YAML 정의 |
| `tests/` | pytest 회귀 커버리지 |
| `tasks/lessons.md` | 누적 운영 레슨 (반드시 읽을 것) |
| `docs/OPENSOURCE_PLAN.md` | 오픈소스화 마스터 플랜 |

## Gemini 조직 배정 원칙

Gemini CLI가 배정된 조직과 그 이유:

| 조직 | 엔진 | 활용 강점 |
|------|------|-----------|
| 성장실 (aiorg_growth_bot) | gemini-cli | Google 검색 내장 → 최신 시장 데이터 실시간 조회, 경쟁사 분석 |
| 리서치실 (aiorg_research_bot) | gemini-cli | 멀티소스 웹 검색, 문서 요약, 대규모 컨텍스트 처리 |
| 운영실 (aiorg_ops_bot) | gemini-cli | codex rate limit 대응 전환 (2026-03-26) — DevOps 태스크 처리 |

### Gemini CLI의 강점 (다른 엔진과 차별점)
1. **실시간 Google 검색** — 최신 시장 데이터, 경쟁사 정보 즉시 조회
2. **대규모 컨텍스트** — 긴 문서 요약, 멀티소스 비교에 최적
3. **OAuth 기반** — API Key 없이 Google Pro Plan으로 바로 사용
4. **이미지 생성** — Gemini 2.5 Flash Image 모델 접근 가능

## 운영 주의사항 (누적)

> 세션 시작 시 반드시 확인. 실수가 발생할 때마다 여기에 추가한다.

### [2026-03-25] 자율 협업 실행 원칙 — "다음 조치 = 즉시 실행" (전체 조직 필수)

"다음 조치"를 나열하고 끝내는 것은 안티패턴. 나열하는 순간 즉시 실행한다.

**자동 트리거 메시지** (`## 🔄 일일 목표 파이프라인`, `⚠️ STALE`, `[주간회의 보고 요청]`) 수신 시 사용자 확인 없이 즉시 pm-progress-tracker 스킬 실행.

**COLLAB 태그 의무 사용**: 타부서 담당 태스크, 배포 요청, UI 검토, 리서치 선행이 필요한 모든 상황에서 `[COLLAB:태스크 설명|맥락: ...]` 태그를 반드시 포함한다.

**자율 iter 체인**: 세션 시작 시 pm_progress_guide.md 읽기 → IN_PROGRESS 목표 확인 → TODO 서브태스크 배분 → COLLAB 태그로 타부서 위임.

### [2026-03-25] E2E 자율 루프 운영 원칙 (전체 조직 공통)

**구현 완료** — `goal_tracker/goal_tracker_client.py`, `goal_tracker/multibot_meeting_handler.py`, `run_e2e_loop.py`, `tests/e2e/test_autonomous_loop_e2e.py` (37개 테스트 통과)

- **트리거**: 일일회고(`일일회고`/`daily retro`) · 주간회의(`주간회의`/`weekly meeting`) 채팅 메시지
- **GoalTracker 등록 규칙**: `[ ]` 체크박스 아이템 자동 파싱 → `GoalTrackerClient.register_report()`
- **멀티봇 순서**: 개발실 → 운영실 → 디자인실 → 기획실 → 성장실 → 리서치실 (3초 인터벌)
- **중복 방지**: `{meeting_type}_{date}` 기준 당일 재처리 방지
- **루프 상태**: `IDLE → EVALUATE → REPLAN → DISPATCH → IDLE`
- **상세 가이드**: `docs/AUTONOMOUS_LOOP.md`

### [2026-03-25] PM 진척관리 스킬 & 이터레이션 루프 (전체 조직 공통)
- **스킬 위치**: `skills/pm-progress-tracker/skill.md`
- **목표 문서**: `memory/pm_progress_guide.md` (세션 시작 시 반드시 읽을 것)
- **규칙**: 사용자 큰 목표 수신 시 → 즉시 pm_progress_guide.md에 등록 → 이터레이션 루프 시작
- **자동화**: `daily_goal_pipeline` (orchestration.yaml) — 매일 09:00 KST 아침 목표를 GoalTracker에 자동 등록 → 부서 위임
- **완료 원칙**: 완료 조건 충족 시 DONE 처리 / 미충족 시 자율 재루프 (사용자 확인 불필요)

### [2026-03-24] 3개 컨텍스트 파일 동시 수정 원칙
- **원칙**: CLAUDE.md / AGENTS.md / GEMINI.md 는 항상 함께 수정한다
- 한 파일을 수정하면 나머지 두 파일도 같은 내용으로 업데이트
- CLAUDE.md가 가장 진보되어 있으므로 베이스로 사용

### [2026-03-25] CI/CD 파이프라인 운영 규칙
- `.github/workflows/ci-lint.yml` 은 `pull_request`, `main` push, `workflow_dispatch` 기준으로 Ruff lint를 수행한다.
- `.github/workflows/ci-e2e.yml` 은 `pull_request`, `main` push, `workflow_dispatch` 기준으로 `claude-code` / `codex` / `gemini-cli` 3엔진 matrix에서 `python tools/orchestration_cli.py validate-config` 와 `pytest tests/e2e/ -q --tb=short` 를 실행한다.
- `.github/workflows/publish-pypi.yml` 은 `v*` 태그 push 또는 수동 `workflow_dispatch` 시 `verify` 후 `python -m build` / `twine upload` 로 PyPI 패키지를 배포한다.
- `.github/workflows/docker-build.yml` 은 `v*` 태그 push 또는 수동 `workflow_dispatch` 시 `verify` 후 Docker Buildx 로 이미지를 빌드하고 Docker Hub 에 푸시한다.
- GitHub Actions secret 이름은 `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `GEMINI_OAUTH_CREDS`, `CLAUDE_CODE_OAUTH_TOKEN`, `PYPI_TOKEN`, `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` 을 사용한다.
- Gemini CI는 `GEMINI_OAUTH_CREDS` 가 있으면 `~/.gemini/oauth_creds.json` 으로 복원해 사용한다.
- `ci-lint` 와 `ci-e2e` 를 branch protection required checks 로 묶어 `main` 배포 전 테스트를 강제한다.
- 상세 운영 절차와 로컬 재현 명령은 `docs/CI_CD_GUIDE.md` 를 따른다.

### [2026-03-24] Gemini CLI OAuth 환경 주의사항
- **GEMINI_API_KEY 환경변수 설정 금지**: GeminiCLIRunner는 subprocess 실행 시 API Key 환경변수를 자동 제거한다. 혼재 시 OAuth 충돌 발생.
- **인증 파일 경로**: `~/.gemini/oauth_creds.json` — 이 파일이 없으면 `gemini auth login` 실행
- **타임아웃**: 긴 리서치 태스크는 `GEMINI_CLI_DEFAULT_TIMEOUT_SEC=1800` 설정 권장

### [2026-03-21] 배포 행위는 운영실(aiorg_ops_bot) 전담 — 전체 조직 적용
- **원칙**: 운영실을 제외한 **모든 specialist 조직**은 로컬 커밋까지만 수행.
  ```
  ❌ 운영실 외 자체 수행 금지:
    git push / git merge / 봇 재기동(restart_bots.sh, request_restart.sh)

  ✅ 완료 후 운영실에 COLLAB 위임:
    "[COLLAB:머지/푸시/재기동 요청|맥락: 코드 수정 완료]"
  ```

### [2026-03-22] 현재 시간 기준 작업 원칙 (전체 조직 공통)
- **원칙**: 모든 봇은 태스크 시작 시 현재 날짜/시각을 확인하고, 항상 **현재 시각 기준**으로 조사·판단
- **산출물 표기**: 보고서·분석물에 "YYYY-MM-DD 기준" 조사 시점을 반드시 명시
- **Gemini 특화**: 웹 검색 시 "2026년 최신" 등 연도 키워드를 명시해 최신 결과 우선 수집

### [2026-03-22] 안전 코드 수정 방법론 (전체 조직 공통)
> 실패 감지 코드 및 고위험 경로 수정 시 반드시 따른다. 상세: `skills/safe-modify/SKILL.md`

### [2026-03-22] Gemini Flash 모델 버전
- **현행**: `gemini-2.5-flash` (최신 stable)
- **금지**: `gemini-2.0-flash` (2026-06-01 서비스 종료)
- **Preview 주의**: `gemini-3.x` 계열은 프로덕션 사용 자제

### [2026-03-25] Docker Compose 다중 엔진 실행 가이드

서비스 구조: `x-bot-common`(공통 앵커) + 엔진 프로파일 3개 (`claude` / `codex` / `gemini`)

```bash
# 1. 환경변수 준비
cp .env.example .env

# 2. Gemini 계열(성장/리서치) 단독 실행
docker compose --profile gemini up -d

# 3. 전체 조직 동시 실행
docker compose --profile claude --profile codex --profile gemini up -d

# 4. 로그 확인
docker compose ps
docker compose logs -f aiorg-growth-bot
docker compose logs -f aiorg-research-bot
```

볼륨 마운트: `./logs`, `./data`, `./reports`, `./tasks`, `./skills`(read-only)
Gemini 자동 주입: `ENGINE_TYPE=gemini-cli`, `GEMINI_CLI_PATH=/opt/cli/bin/gemini`, `GEMINI_CLI_MODEL=gemini-2.5-flash`

### [2026-03-25] 로컬 패키지 설치 — pip install -e . 사용 가능 (setuptools 전환 완료)
- **빌드 백엔드**: hatchling → setuptools+wheel 전환 완료
- **로컬 설치**: `pip install -e .` 이제 정상 작동
  ```bash
  # 로컬 개발 설치 (editable 모드)
  .venv/bin/pip install -e .

  # 개발 도구 포함 설치
  .venv/bin/pip install -e ".[dev]"
  ```

### [2026-03-23] 위험한 시스템 탐색 절대 금지 (전체 조직 공통)
```python
# ❌ 절대 금지
glob.glob(str(Path.home()) + '/**/*', recursive=True)
find ~ -name '*'

# ✅ 허용 (프로젝트 디렉토리 내부만)
glob.glob('/Users/rocky/telegram-ai-org/**/*.db', recursive=True)
# ✅ 산출물 저장소 (AI_ORG_DATA_DIR 기반 — telegram-ai-org 외부 허용)
glob.glob(os.environ.get('AI_ORG_DATA_DIR', str(Path.home() / 'telegram-ai-org-data')) + '/**/*', recursive=True)
```

### [2026-03-26] AI_ORG_DATA_DIR — 산출물·데이터 저장 경로 표준화 (전체 조직 공통)
- **원칙**: `telegram-ai-org/`는 오픈소스 코드만 포함. 모든 산출물·생성 코드·스킬 로그는 `AI_ORG_DATA_DIR`에 저장
- **기본값**: `~/telegram-ai-org-data` (환경변수 미설정 시 자동 사용)
- **`.env` 설정**: `AI_ORG_DATA_DIR=~/telegram-ai-org-data`
- **`~/.ai-org/workspace`**: 기존 산출물 보존. 신규 산출물은 `AI_ORG_DATA_DIR`로만 저장
- **스킬 경로**: `${AI_ORG_DATA_DIR:-$HOME/telegram-ai-org-data}/skills/<skill-name>/data/`
- **금지**: `../telegram-ai-org-data/` 상대 경로 하드코딩 (오픈소스 사용자 경로 불일치 유발)

---

## 스킬 전략

`skills/` 디렉토리의 프로젝트 전용 스킬을 활용한다. 전체 목록: `skills/README.md`

| 상황 | 사용 스킬 |
|------|-----------|
| 태스크 배분이 필요할 때 | `pm-task-dispatch` |
| 여러 봇 의견 조율이 필요할 때 | `pm-discussion` |
| 코드 병합/배포 전 | `quality-gate` |
| 매주 금요일 | `weekly-review` |
| 스프린트 끝날 때 | `retro` |
| 실패 감지 / 고위험 코드 수정 시 | `safe-modify` |
| 시스템 점검 시 | `harness-audit` |
| 장시간 루프 실행 시 | `loop-checkpoint` |
| 새 스킬 제작 시 | `create-skill` |
| E2E 회귀 테스트 | `e2e-regression` |
| 이미지 생성 필요 시 | `gemini-image-gen` |

### 자율 에이전트 스킬 실행 원칙
- **인터랙티브 스킬 금지**: `AskUserQuestion`을 사용하는 스킬은 자율 모드에서 직접 호출하지 않는다.
- **대체 스킬 사용**: `brainstorming-auto`, `pm-discussion` 등 비인터랙티브 버전을 사용한다.
- **AUTONOMOUS_MODE 원칙**: 불확실하면 합리적 기본값으로 진행하고 로그를 남긴다. 멈추지 않는다.

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

> 이 원칙은 모든 specialist 조직에 예외 없이 적용된다.

- **PM이 해당 태스크에 명시한 "실행 범위" 내의 작업만 수행한다.**
- 명시되지 않은 추가 작업·리팩터링·기능 확장·자기 개선·배포·재기동은 PM의 명시적 지시 없이 수행하지 않는다.
- 스코프 외 작업이 필요하다고 판단되면: PM에게 보고하거나 `[COLLAB]` 태그로 적절한 조직에 위임 요청.

## 개발 규칙

- 변경 범위를 최소화. 타깃 이외 영역 리팩토링 금지.
- async 동작과 기존 public 메서드 시그니처 유지.
- 시크릿/봇 토큰 하드코딩 금지. 환경변수만 사용.
- 줄 길이: Ruff 설정 기준 100자.
- **컨텍스트 파일 변경 시**: CLAUDE.md / AGENTS.md / GEMINI.md 모두 업데이트.

## Git 워크트리 워크플로 (필수)

현재 브랜치가 `main`이 아닌 상태에서 새 태스크를 받으면 반드시 워크트리를 생성한다:

```bash
git worktree add .worktrees/<task-slug> main
git -C .worktrees/<task-slug> checkout -b feat/<task-slug>
# 작업 후
git -C /Users/rocky/telegram-ai-org merge feat/<task-slug> --no-ff
git worktree remove .worktrees/<task-slug>
```
