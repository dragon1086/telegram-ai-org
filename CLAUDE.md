# CLAUDE.md

이 파일은 Claude Code가 이 저장소에서 작업할 때 자동으로 읽는 프로젝트 지침이다.

## 프로젝트 개요

`telegram-ai-org` — Telegram 그룹 채팅방을 AI 조직의 오피스로 쓰는 멀티봇 오케스트레이션 시스템.

- PM 봇이 `workers.yaml`을 읽어 태스크를 적합한 워커 봇에 자율 배분
- 봇마다 성격·기억·캐릭터 진화, 팀워크/칭찬 시스템, 자연어 스케줄 등록 지원
- 실행 엔진: `claude-code` / `codex` 중 봇별 설정

## 환경 설정

```bash
# 가상환경 활성화 (항상 venv 사용)
source .venv/bin/activate

# 또는 직접 경로로
./.venv/bin/python ...
./.venv/bin/pytest ...
```

`.env` 파일에 `PM_BOT_TOKEN`, `COKAC_BOT_TOKEN` 등 봇 토큰 필수.

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
| `workers.yaml` | 워커 봇 등록부 |
| `orchestration.yaml` | 오케스트레이션 설정 |
| `bots/` | 봇 YAML 정의 |
| `tests/` | pytest 회귀 커버리지 |

## 운영 주의사항 (누적)

> 세션 시작 시 반드시 확인. 실수가 발생할 때마다 여기에 추가한다.

### [2026-03-16] 봇 재시작 전 패키지 sync 필수
- **증상**: 재시작 후 `ModuleNotFoundError` 반복 크래시 → 봇 무응답
- **원인**: `pyproject.toml`에 선언된 패키지도 venv에 자동 설치되지 않음
- **체크리스트**:
  ```bash
  # 소스 수정 후 재시작 전 항상 실행
  # ❌ pip install -e . 는 이 프로젝트에서 작동하지 않음 (hatchling 설정 미비)
  .venv/bin/pip install aiosqlite -q  # 누락 패키지 개별 설치
  bash scripts/start_all.sh
  ```

### [2026-03-17] rank-bm25 설치 시 pip install -e . 사용 불가
- 이 프로젝트는 hatchling 설정 미비로 pip install -e . 작동 안 함
- rank-bm25 등 신규 패키지는 직접 설치: .venv/bin/pip install rank-bm25

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
| 시스템 점검 시 | `harness-audit` |
| 장시간 루프 실행 시 | `loop-checkpoint` |

### 자율 에이전트 스킬 실행 원칙
- **인터랙티브 스킬 금지**: brainstorming, deep-interview 등 `AskUserQuestion`을 사용하는 스킬은 자율 모드에서 직접 호출하지 않는다.
- **대체 스킬 사용**: 대신 `brainstorming-auto`, `pm-discussion` 등 비인터랙티브 버전을 사용한다.
- **AUTONOMOUS_MODE 원칙**: 불확실하면 합리적 기본값으로 진행하고 로그를 남긴다. 멈추지 않는다.
- **스킬 상세**: `skills/README.md` 참조

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
