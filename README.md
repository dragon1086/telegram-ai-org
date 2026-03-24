# telegram-ai-org

텔레그램 그룹 채팅방 = AI 조직의 오피스.

유저가 방향만 제시하면, PM AI가 `workers.yaml`에 등록된 워커 팀에서 적합한 봇을 자율 선택해 태스크를 실행합니다.

## 차별화 포인트

- **동적 워커 팀**: `workers.yaml` 한 파일로 워커 추가/제거 — 코드 수정 불필요
- **Telegram이 Native UI + 메시지 버스**: 별도 대시보드 불필요, 채팅방 자체가 오피스
- **엔진 선택**: 워커별로 `claude-code` / `codex` / `both` 설정 가능
- **공유 컨텍스트 DB**: 모든 봇이 동일한 맥락 접근
- **완료 검증 프로토콜**: PM이 전체 봇에 확인 요청 후 최종 처리
- **봇 캐릭터 진화**: 성격·기억·페르소나가 대화를 통해 점진적으로 발전
- **팀워크·칭찬 시스템**: 봇 간 협업 추적, shoutout 자동 생성
- **자연어 스케줄**: `/schedule` 명령으로 한국어 자연어 기반 반복 태스크 등록
- **P2P 직접통신**: 봇 간 직접 메시지 교환 및 공유 메모리

## 아키텍처

```
유저 → @pm_bot
         ↓ workers.yaml 로드
         ↓ 태스크 분석 → 적합한 워커 자율 선택
         ↓
    @cokac_bot (claude-code)
    @researcher_bot (codex)
    @writer_bot (claude-code)
    ...
         ↓
    실행 (ClaudeCodeRunner / CodexRunner)
         ↓
    @pm_bot ← 결과 보고 → 완료 검증
         ↓
    내장 스케줄러 (반복 태스크 자율 실행)
```

## 빠른 시작

```bash
# 1. 원클릭 설치 (엔진 자동 감지 + 의존성 + .env 생성 + 검증)
bash scripts/setup.sh

# 2. .env 파일에 Telegram 봇 토큰 입력
nano .env

# 3. 설치 마법사 실행 (PM 봇 + 워커 봇 대화형 설정)
./.venv/bin/python scripts/setup_wizard.py

# 4. 모든 봇 시작
bash scripts/start_all.sh
```

테스트 실행도 전역 Python 대신 프로젝트 가상환경을 사용합니다.

```bash
./.venv/bin/pytest -q
./.venv/bin/pytest tests/test_pm_orchestrator.py -q
```

## setup.sh 설치 가이드

### 사전 조건

| 항목 | 요구사항 |
|------|----------|
| Python | 3.10 이상 (3.11+ 권장) |
| AI 엔진 | claude / codex / gemini 중 **최소 1개** 설치 |
| OS | macOS / Linux |

**AI 엔진 설치 방법:**
- **claude-code**: [claude.ai/code](https://claude.ai/code) → `claude` 명령어 설치
- **codex**: `npm install -g @openai/codex` → `codex login`으로 인증
- **gemini-cli**: [gemini-cli 설치](https://github.com/google-gemini/gemini-cli) → `gemini auth login`으로 인증

### 실행 명령

```bash
# 기본 실행 (전체 5단계 자동 수행)
bash scripts/setup.sh

# 옵션
bash scripts/setup.sh --skip-verify   # 검증 단계 건너뜀 (빠른 재설치)
bash scripts/setup.sh --no-venv       # 가상환경 생성 건너뜀 (이미 있는 경우)
```

### 실행 단계 및 출력 예시

```
▶ Step 1/5: AI 엔진 자동 감지
✅ codex 감지됨:  /opt/homebrew/bin/codex
✅ gemini 감지됨: /opt/homebrew/bin/gemini
⚠️  claude CLI 미감지 (설치: https://claude.ai/code)
감지된 엔진: codex gemini (총 2개)

▶ Step 2/5: Python 환경 확인
✅ Python 3.12.12 (python3.12) — 요구사항 충족
✅ 가상환경 이미 존재: .venv/

▶ Step 3/5: Python 의존성 설치
✅ 의존성 설치 완료 (pip deps-only)

▶ Step 4/5: 환경 변수 파일 설정
✅ .env 파일 생성 완료
ℹ️  GEMINI_CLI_PATH → /opt/homebrew/bin/gemini (자동 설정)
ℹ️  CODEX_CLI_PATH  → /opt/homebrew/bin/codex  (자동 설정)

▶ Step 5/5: 초기화 검증
✅ import anthropic        ✅ import pydantic
✅ import python-telegram-bot  ✅ import loguru
...
검증 완료: 10/10 항목 통과 — 모두 정상
```

### 자동 처리 항목

- **엔진 경로 자동 설정**: 감지된 엔진 경로가 `.env`에 자동 기입 (`CLAUDE_CLI_PATH`, `CODEX_CLI_PATH`, `GEMINI_CLI_PATH`)
- **Python 버전 탐색**: `python3.13 → 3.12 → 3.11 → 3.10` 순으로 3.10+ 버전 자동 선택 (macOS 시스템 python 3.9 자동 우회)
- **.env 보호**: `.env`가 이미 있으면 덮어쓰지 않고 경로 값만 업데이트

### 문제 해결

| 증상 | 해결 방법 |
|------|-----------|
| `AI 엔진이 하나도 감지되지 않았습니다` | 위 엔진 중 하나 이상 설치 후 재실행 |
| `Python 3.10 이상을 찾을 수 없습니다` | `brew install python@3.11` (macOS) |
| `import anthropic 실패` | `.venv/bin/pip install anthropic` 수동 실행 |
| Gemini 인증 오류 | `gemini auth login` 실행 후 재시도 |

## 주요 봇 명령어

### PM 봇
| 명령어 | 설명 |
|--------|------|
| `/schedule <자연어>` | 반복 태스크 자연어로 등록 (예: "매일 오전 9시 리포트") |
| `/schedules` | 등록된 스케줄 목록 조회 |
| `/cancel_schedule <id>` | 스케줄 취소 |
| `/verbose 0\|1\|2` | 중간 진행 로그 노출 수준 조절 |

### 워커 봇
| 명령어 | 설명 |
|--------|------|
| `/stop_tasks` | 현재 실행 중인 태스크 중단 |
| `/restart` | 봇 재시작 |
| `/set_engine <claude-code\|codex>` | 실행 엔진 변경 |

## 텔레그램 전달 품질

- 최종 전달본은 로컬 경로나 내부 문서 위치보다 핵심 설명을 먼저 보여준다.
- 첨부 산출물은 파일명만 본문에 남기고 실제 업로드는 런타임이 처리한다.
- 긴 응답은 문단/문장 경계 기준으로 분할해 모바일에서 읽기 쉽게 보낸다.
- `/verbose 0|1|2` 로 중간 진행 노출량을 조절할 수 있다.

## 워커 설정 (workers.yaml)

```yaml
workers:
  - name: cokac
    token: "${COKAC_BOT_TOKEN}"
    engine: claude-code          # claude-code | codex | both
    description: "코딩, 구현, 리팩토링 전문"

  - name: researcher
    token: "${RESEARCHER_BOT_TOKEN}"
    engine: codex
    description: "분석, 리서치, 데이터 처리"
```

워커를 추가하려면 `workers.yaml`에 항목을 추가하고 봇을 재시작하면 됩니다.

## 기능 로드맵

- [x] Phase 1 — P2P 직접통신·공유메모리
- [x] Phase 2 — 기억·성격·회의 강화
- [x] Phase 3 — 팀워크·캐릭터·칭찬 시스템
- [x] 내장 스케줄러 (OpenClaw 독립)
- [x] 자연어 스케줄 등록 인터페이스
- [x] 매일 아침 LLM 팀 목표 자동 생성

## 기술 스택

- Python 3.11+
- python-telegram-bot
- SQLite + sqlite-vec (공유 컨텍스트)
- Claude Code / Codex (실행 엔진)
- asyncio + pydantic + PyYAML

## 관련 프로젝트

MetaGPT, AutoGen, CrewAI, OpenAI Swarm에서 영감을 받았으나,
**Telegram을 native 메시지 버스**로 사용하고 **workers.yaml 기반 동적 팀 구성**이 핵심 차별점입니다.
