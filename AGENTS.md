# AGENTS.md

이 파일은 Codex CLI 등 AI 에이전트가 이 저장소에서 작업할 때 자동으로 읽는 프로젝트 지침이다.

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

# 린트
./.venv/bin/ruff check .
```

## 핵심 경로

| 경로 | 역할 |
|------|------|
| `main.py` | 로컬 진입점 |
| `core/pm_orchestrator.py` | PM 오케스트레이션 메인 루프 |
| `core/pm_router.py` | 태스크 → 워커 라우팅 |
| `core/telegram_relay.py` | Telegram 메시지 중계 |
| `workers.yaml` | 워커 봇 등록부 |
| `orchestration.yaml` | 오케스트레이션 설정 |
| `tasks/lessons.md` | 누적 운영 레슨 (반드시 읽을 것) |

## 스킬 전략

`skills/` 디렉토리의 프로젝트 전용 스킬을 활용한다. 전체 목록: `skills/README.md`

| 스킬 | 트리거 | 용도 |
|------|--------|------|
| `pm-task-dispatch` | '업무배분', 'pm dispatch' | PM 태스크 배분 |
| `pm-discussion` | '토론', 'discuss' | 다봇 토론 조율 |
| `quality-gate` | '품질검사', 'quality gate' | 배포 전 품질 검사 |
| `weekly-review` | '주간회의', 'weekly review' | 주간회의 자율 진행 |
| `retro` | '회고', 'retrospective' | 스프린트 회고 |
| `engineering-review` | '코드리뷰', 'code review' | 코드 품질 검토 |
| `safe-modify` | '안전 수정', 'safe modify', '실패감지 수정', '부작용 최소화' | 실패 감지·고위험 코드 안전 수정 체크리스트 |
| `harness-audit` | '하네스 감사', 'harness audit' | 시스템 신뢰성 감사 |
| `loop-checkpoint` | '체크포인트', 'checkpoint' | 루프 상태 저장/재개 |
| `autonomous-skill-proxy` | '자율모드', 'autonomous mode' | 인터랙티브 스킬 자동 응답 |

**핵심 원칙**: 자율 에이전트는 `AskUserQuestion`을 요구하는 스킬(brainstorming 등) 대신 비인터랙티브 대체 스킬을 사용한다.

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

## 안전 코드 수정 원칙 (safe-modify — 2026-03-22 도입)

> 실패 감지 코드 및 고위험 경로 수정 시 `skills/safe-modify/SKILL.md` 절차를 따른다.

**수정 전 Pre-flight**: CRAP 점수 확인 → 스코프 명시 → 롤백 경로 확보 → quality-gate PASS 기준선 확인
**수정 중**: Guard Clause 우선 · Feature Flag 적용 · Idempotency 유지 · Minimal Footprint 준수
**수정 후**: 실패 주입 테스트 → pytest 회귀 → quality-gate → engineering-review

**절대 금지**:
- `except: pass` 예외 삼킴
- LLM fallback 경로 제거
- CRAP > 30 함수 테스트 없이 수정
- 한 PR에서 복수 판정 경로 동시 수정

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

## 운영 주의사항 (누적)

> 작업 시작 전 반드시 확인. 실수 발생 시 여기와 `tasks/lessons.md`에 추가한다.

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

## 레슨 추가 규칙

새 운영 실수가 생기면 반드시 **세 파일 모두** 업데이트:
1. `CLAUDE.md` → Claude Code용
2. `AGENTS.md` → Codex 등 기타 엔진용
3. `tasks/lessons.md` → 상세 원인/해결 기록
