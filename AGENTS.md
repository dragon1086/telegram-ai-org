# AGENTS.md

이 파일은 Codex CLI 등 AI 에이전트가 이 저장소에서 작업할 때 자동으로 읽는 프로젝트 지침이다.

> **3개 컨텍스트 파일 동기화 원칙**: CLAUDE.md / AGENTS.md / GEMINI.md 는 항상 동시에 수정한다.
> 이 파일을 수정하면 반드시 CLAUDE.md와 GEMINI.md도 같은 내용으로 업데이트한다.

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

# E2E 회귀 테스트
./.venv/bin/pytest tests/e2e/ -q

# 오케스트레이션 설정 검증
./.venv/bin/python tools/orchestration_cli.py validate-config
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
| `workers.yaml` | 워커 봇 등록부 (레거시, bots/*.yaml 참조) |
| `orchestration.yaml` | 오케스트레이션 설정 |
| `bots/` | 봇 YAML 정의 |
| `tests/` | pytest 회귀 커버리지 |
| `tools/codex_runner.py` | Codex CLI 러너 |
| `tasks/lessons.md` | 누적 운영 레슨 (반드시 읽을 것) |
| `docs/OPENSOURCE_PLAN.md` | 오픈소스화 마스터 플랜 |

## 운영 주의사항 (누적)

> 세션 시작 시 반드시 확인. 실수가 발생할 때마다 여기에 추가한다.

### [2026-03-24] 3개 컨텍스트 파일 동시 수정 원칙
- **원칙**: CLAUDE.md / AGENTS.md / GEMINI.md 는 항상 함께 수정한다
- 한 파일을 수정하면 나머지 두 파일도 같은 내용으로 업데이트
- CLAUDE.md가 가장 진보되어 있으므로 베이스로 사용
- 각 파일은 엔진별 특성만 다르게 유지 (기본 내용은 동일)

### [2026-03-25] CI/CD 파이프라인 추가됨
- `.github/workflows/ci.yml` 은 `pull_request` 기준 Python 3.11 환경에서 `pip install -e ".[dev]"`, `ruff check telegram_ai_org`, `python tools/orchestration_cli.py validate-config`, `pytest tests/e2e/ -q` 순서로 PR 검증을 수행한다.
- `.github/workflows/release.yml` 은 `main` push 기준 `verify` → `publish-pypi` → `docker-push` 순서로 직렬 실행되며, 검증 재실행 뒤 `python -m build` / `twine upload` 와 `docker/build-push-action` 배포를 수행한다.
- GitHub Actions secret 이름은 `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `GEMINI_OAUTH_CREDS`, `CLAUDE_CODE_OAUTH_TOKEN`, `PYPI_TOKEN`, `DOCKER_USERNAME`, `DOCKER_TOKEN` 을 사용한다.
- Gemini CI는 `GEMINI_OAUTH_CREDS` 가 있으면 `~/.gemini/oauth_creds.json` 으로 복원해 사용한다.
- `ci.yml` 을 branch protection required check로 묶어 `main` 배포 전 테스트를 강제한다.
- 상세 운영 절차와 로컬 재현 명령은 `docs/CI_CD_SETUP.md` 를 따른다.

### [2026-03-21] 배포 행위는 운영실(aiorg_ops_bot) 전담 — 전체 조직 적용
- **원칙**: 운영실을 제외한 **모든 specialist 조직**은 로컬 커밋까지만 수행.
  ```
  ❌ 운영실 외 자체 수행 금지:
    git push / git merge / 봇 재기동(restart_bots.sh, request_restart.sh)

  ✅ 완료 후 운영실에 COLLAB 위임:
    "[COLLAB:머지/푸시/재기동 요청|맥락: 코드 수정 완료]"
  ```

### [2026-03-25] 로컬 패키지 설치 — pip install -e . 사용 가능 (setuptools 전환 완료)
- **빌드 백엔드**: hatchling → setuptools+wheel 전환 완료
- **로컬 설치**: `pip install -e .` 이제 정상 작동
  ```bash
  # 로컬 개발 설치 (editable 모드)
  .venv/bin/pip install -e .

  # 개발 도구 포함 설치
  .venv/bin/pip install -e ".[dev]"

  # 봇 재시작 전 패키지 동기화
  .venv/bin/pip install -e . && bash scripts/start_all.sh
  ```

### [2026-03-22] 현재 시간 기준 작업 원칙 (전체 조직 공통)
- **원칙**: 모든 봇은 태스크 시작 시 현재 날짜/시각을 확인하고, 항상 **현재 시각 기준**으로 조사·판단
- **산출물 표기**: 보고서·분석물에 "YYYY-MM-DD 기준" 조사 시점을 반드시 명시

### [2026-03-22] 안전 코드 수정 방법론 (전체 조직 공통)
> 실패 감지 코드 및 고위험 경로 수정 시 반드시 따른다. 상세: `skills/safe-modify/SKILL.md`

| 원칙 | 한 줄 요약 |
|------|-----------|
| Defensive Programming | Guard Clause 우선, `except: pass` 금지 |
| Minimal Footprint | PR당 파일 3개 이하 |
| Feature Flags | 판정 로직 변경 시 Feature Flag 필수 |
| Idempotency | 전역 상태 변경 금지, 순수 함수 지향 |

### [2026-03-22] Gemini Flash 모델 버전 — gemini-2.5-flash 사용
- **현행**: `gemini-2.5-flash` (2026-03-22 기준 최신 stable)
- **금지**: `gemini-2.0-flash` (2026-06-01 서비스 종료 예정)
- **주의**: `gemini-3.x` 계열은 Preview 단계 — 프로덕션 사용 자제

### [2026-03-23] 위험한 시스템 탐색 절대 금지 (전체 조직 공통)
```python
# ❌ 절대 금지
glob.glob(str(Path.home()) + '/**/*', recursive=True)
os.walk(Path.home()) / os.walk('/')
find ~ -name '*' / find / -name '*'

# ✅ 허용 (프로젝트 디렉토리 내부만)
glob.glob('/Users/rocky/telegram-ai-org/**/*.db', recursive=True)
```

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
| 코드 리뷰 요청 시 | `engineering-review` |
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
- 글로벌 적용 위치: `orchestration.yaml` → `global_instructions`

## 개발 규칙

- 변경 범위를 최소화. 타깃 이외 영역 리팩토링 금지.
- async 동작과 기존 public 메서드 시그니처 유지.
- 시크릿/봇 토큰 하드코딩 금지. 환경변수만 사용.
- 줄 길이: Ruff 설정 기준 100자.
- 동작 변경 시 `README.md`, `ARCHITECTURE.md` 동기화.
- **컨텍스트 파일 변경 시**: CLAUDE.md / AGENTS.md / GEMINI.md 모두 업데이트.

## Git 워크트리 워크플로 (필수)

현재 브랜치가 `main`이 아닌 상태에서 새 태스크를 받으면 반드시 워크트리를 생성한다:

```bash
git worktree add .worktrees/<task-slug> main
cd .worktrees/<task-slug>
git checkout -b fix/<task-slug>
# 작업 완료 후
git checkout main
git merge fix/<task-slug> --no-ff
git worktree remove .worktrees/<task-slug>
```

## 조직별 엔진 배정

| 조직 | 엔진 | 근거 |
|------|------|------|
| PM (aiorg_pm_bot) | claude-code | 복잡한 오케스트레이션, 멀티스텝 추론 |
| 개발실 (aiorg_engineering_bot) | claude-code | 복잡한 코드 아키텍처, 디버깅 |
| 디자인실 (aiorg_design_bot) | claude-code | 크리에이티브 UI/UX 태스크 |
| 기획실 (aiorg_product_bot) | claude-code | PRD, 요구사항 문서화 |
| 성장실 (aiorg_growth_bot) | gemini-cli | Google 검색 내장, 시장 데이터 |
| 리서치실 (aiorg_research_bot) | gemini-cli | 실시간 웹 검색, 경쟁사 분석 |
| 운영실 (aiorg_ops_bot) | codex | 경량 DevOps 스크립트 특화 |
