# telegram-ai-org

텔레그램 그룹 채팅방 = AI 조직의 오피스.

유저가 방향만 제시하면, PM AI가 `workers.yaml`에 등록된 워커 팀에서 적합한 봇을 자율 선택해 태스크를 실행합니다.

## 차별화 포인트

- **동적 워커 팀**: `workers.yaml` 한 파일로 워커 추가/제거 — 코드 수정 불필요
- **Telegram이 Native UI + 메시지 버스**: 별도 대시보드 불필요, 채팅방 자체가 오피스
- **엔진 선택**: 워커별로 `claude-code` / `codex` / `both` 설정 가능
- **공유 컨텍스트 DB**: 모든 봇이 동일한 맥락 접근
- **완료 검증 프로토콜**: PM이 전체 봇에 확인 요청 후 최종 처리

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
```

## 빠른 시작

```bash
# 1. 의존성 설치
./scripts/setup.sh

# 2. 설치 마법사 실행 (PM 봇 + 워커 봇 대화형 설정)
python scripts/setup_wizard.py

# 3. 모든 봇 시작
bash scripts/start_all.sh
```

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

## 기술 스택

- Python 3.11+
- python-telegram-bot
- SQLite + sqlite-vec (공유 컨텍스트)
- Claude Code / Codex (실행 엔진)
- asyncio + pydantic + PyYAML

## 관련 프로젝트

MetaGPT, AutoGen, CrewAI, OpenAI Swarm에서 영감을 받았으나,
**Telegram을 native 메시지 버스**로 사용하고 **workers.yaml 기반 동적 팀 구성**이 핵심 차별점입니다.
