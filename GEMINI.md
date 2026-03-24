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
GEMINI_CLI_DEFAULT_TIMEOUT_SEC=1800  # 긴 리서치 태스크 대응
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

### Gemini CLI의 강점 (다른 엔진과 차별점)
1. **실시간 Google 검색** — 최신 시장 데이터, 경쟁사 정보 즉시 조회
2. **대규모 컨텍스트** — 긴 문서 요약, 멀티소스 비교에 최적
3. **OAuth 기반** — API Key 없이 Google Pro Plan으로 바로 사용
4. **이미지 생성** — Gemini 2.5 Flash Image 모델 접근 가능

## 운영 주의사항 (누적)

> 세션 시작 시 반드시 확인. 실수가 발생할 때마다 여기에 추가한다.

### [2026-03-24] 3개 컨텍스트 파일 동시 수정 원칙
- **원칙**: CLAUDE.md / AGENTS.md / GEMINI.md 는 항상 함께 수정한다
- 한 파일을 수정하면 나머지 두 파일도 같은 내용으로 업데이트
- CLAUDE.md가 가장 진보되어 있으므로 베이스로 사용

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

### [2026-03-16] 봇 재시작 전 패키지 sync 필수
```bash
# ❌ pip install -e . 는 이 프로젝트에서 작동하지 않음 (hatchling 설정 미비)
.venv/bin/pip install <package> -q  # 누락 패키지 개별 설치
```

### [2026-03-23] 위험한 시스템 탐색 절대 금지 (전체 조직 공통)
```python
# ❌ 절대 금지
glob.glob(str(Path.home()) + '/**/*', recursive=True)
find ~ -name '*'

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
