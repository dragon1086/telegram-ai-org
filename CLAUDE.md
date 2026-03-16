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
  .venv/bin/pip install -e . --quiet
  bash scripts/start_all.sh
  ```

---

## 개발 규칙

- 변경 범위를 최소화. 타깃 이외 영역 리팩토링 금지.
- async 동작과 기존 public 메서드 시그니처 유지.
- 시크릿/봇 토큰 하드코딩 금지. 환경변수만 사용.
- 줄 길이: Ruff 설정 기준 100자.
- 동작 변경 시 `README.md`, `ARCHITECTURE.md` 동기화.

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
