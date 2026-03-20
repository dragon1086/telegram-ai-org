# PRD 회고 문서: AI Org v1 핵심 기능 정리

**작성**: aiorg_product_bot (기획실)
**날짜**: 2026-03-20
**대상 독자**: Rocky, 개발팀, 온보딩 신규 봇

---

## 개요

이 문서는 2026년 3월 기준으로 telegram-ai-org 시스템에 구현·배포된 핵심 기능들을 제품 관점에서 정리한 것이다. "왜 만들었는가"와 "사용자(Rocky)에게 어떤 가치를 주는가"를 중심으로 기술한다.

---

## 1. 봇 성격·말투 주입 시스템 (Task A)

**커밋**: 63ae084
**모듈**: `core/pm_identity.py`, `bots/*.yaml`

### 문제
봇들이 모두 동일한 말투로 응답해 "AI 조직"이라는 세계관이 살지 않았다. 사용자 입장에서 어떤 봇이 답하는지 구분이 어렵고, 장기적으로 봇에 대한 친밀감이 생기기 어려웠다.

### 해결책
각 봇의 `personality`, `tone`, `catchphrase`, `strengths` 필드를 YAML에 정의하고, 시스템 프롬프트 앞에 자동 주입한다.

### 사용자 가치
- 봇마다 고유한 말투 → 조직 내 캐릭터 분화
- 봇 교체/추가 시 YAML 수정만으로 성격 변경 가능

---

## 2. Cross-Org Bridge MessageEnvelope 정규화 (Task B)

**커밋**: 855ac4c
**모듈**: `core/cross_org_bridge.py`, `core/message_envelope.py`

### 문제
외부 조직(openclaw-bot 등)에서 온 워커 결과가 내부 메시지 스키마와 달라, 합성 단계에서 필드 누락·오류가 발생했다.

### 해결책
`cross_org_bridge` 워커 결과를 `MessageEnvelope`으로 정규화한 뒤 `result_synthesizer`에 전달. 내부/외부 결과를 동일한 인터페이스로 처리.

### 사용자 가치
- 멀티 조직 협업 시 오류율 감소
- 외부 봇 응답이 내부 봇 응답과 동일하게 합성됨

---

## 3. E2E 타임아웃 58% 단축 + 상수 중앙화 (Task C)

**커밋**: 63a757e
**모듈**: `core/constants.py`, E2E 테스트 전반

### 문제
E2E 테스트 스위트가 너무 오래 걸렸다(일부 시나리오 60초 이상). 타임아웃 값이 코드 곳곳에 흩어져 유지보수가 어려웠다.

### 해결책
- 타임아웃 상수를 `core/constants.py`에 중앙화
- 실제 응답 지연을 분석해 불필요하게 긴 타임아웃을 조정
- 평균 58% 단축

### 사용자 가치
- CI 피드백 루프가 빨라짐
- 타임아웃 조정이 한 곳에서 가능

---

## 4. /history + /stats 명령어 (Task D)

**커밋**: 10e557f
**모듈**: `core/bot_commands.py`, `core/context_db.py`, `core/telegram_relay.py`

### 문제
Rocky가 "지금까지 어떤 태스크가 처리됐지?"를 알려면 직접 DB를 뒤지거나 로그를 봐야 했다. 봇 성과를 한눈에 파악할 방법이 없었다.

### 해결책
- `/history [N]`: 최근 N개(기본 10, 최대 50) 태스크 이력을 Telegram으로 출력
- `/stats`: 봇별 처리 태스크 수·성공률을 대시보드 형식으로 출력
- PM 오케스트레이터 전용 명령어로 등록 (`ORCHESTRATOR_ONLY_COMMANDS`)

### 사용자 가치
- Rocky가 Telegram에서 바로 조직 현황 파악 가능
- 봇별 성과 비교로 병목 식별 가능

---

## 5. Stuck Agent 자동 감지 + LLM 응답 주입

**커밋**: b0804c8
**모듈**: `scripts/agent_monitor.py`, `scripts/start_all.sh`

### 문제 (발생 맥락)
2026-03-20, 봇 재시작 직후 5개 Claude agent 세션이 동시에 "재시작할까요?" 질문으로 멈춰버렸다. 아무도 응답하지 않으면 무한 블락. Rocky가 수동으로 tmux에 들어가 일일이 응답해야 했다.

### 해결책
`agent_monitor.py` 데몬:
- 30초 주기로 `aiorg_aiorg_*` tmux 세션 전체 감시
- 3분 이상 화면 변화 없고 + 질문 패턴 감지 시 자동 개입
- `claude -p haiku`로 컨텍스트 기반 자연어 응답 생성 → `tmux send-keys`로 주입
- 중복 방지: context hash 추적 + 5분 쿨다운
- 결과를 `~/.ai-org/agent-monitor.log`에 기록 + Telegram 알림
- `start_all.sh`에서 봇 시작 시 자동 데몬 시작

### 후속 개선 (커밋 4ce4e13, 19e75cb)
- Telegram 알림 메시지 가독성 개선
- fresh session 감지 로직 추가 (신규 세션은 stuck으로 오판하지 않음)

### 사용자 가치
- 봇 재시작 후 Rocky 개입 없이 자동 복구
- stuck 발생 시 Telegram으로 즉시 알림

---

## 6. 재시작 시 Context 완전 리셋

**커밋**: d683dad, d7cf738
**모듈**: `scripts/restart_bots.sh`

### 문제
`restart_bots.sh`가 서브세션(`_claude-*`)만 종료했고, 메인 tmux 세션은 살아있었다. 재시작 후 `/context_budget`이 이전 값 그대로 남아 봇이 "컨텍스트 가득 찼다"고 잘못 인식했다.

### 해결책
- 메인 tmux 세션(`aiorg_aiorg_*`)도 재시작 시 종료 (단, `aiorg_global` 제외)
- `~/.ai-org/sessions/pm_*.json`의 `context_percent`, `msg_count`, `token` 필드를 0으로 리셋

### 사용자 가치
- 재시작 후 깨끗한 상태에서 시작 보장
- `/context_budget` 명령어가 항상 정확한 값 반환

---

## 기능 맵

```
telegram-ai-org v1 기능 레이어
├── 관찰성 (Observability)
│   ├── /history — 태스크 이력 조회
│   ├── /stats   — 봇 성과 대시보드
│   └── agent_monitor — stuck 실시간 감지 + 알림
│
├── 안정성 (Reliability)
│   ├── stuck agent 자동 복구
│   ├── restart context 완전 리셋
│   └── cross_org_bridge 결과 정규화
│
└── 사용자 경험 (UX)
    ├── 봇 성격/말투 주입
    └── E2E 테스트 속도 개선 (CI 58% 단축)
```

---

## 미해결 개선 포인트 (참고용, 미요청)

| # | 항목 | 배경 |
|---|------|------|
| 1 | E2E S-P1 타임아웃 | Claude Code 응답 지연으로 60s → 120s 필요 |
| 2 | Telethon listener min_id 필터링 | 재시작 후 cross-contamination 방지 |
| 3 | agent_monitor 오탐률 측정 | fresh session 감지 외 추가 휴리스틱 필요 가능성 |

---

*이 문서는 기획실(aiorg_product_bot)이 git 이력과 커밋 메시지를 기반으로 작성했다.*
