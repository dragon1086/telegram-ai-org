# Skills 이관 마이그레이션 비용 분석 보고서

**작성일**: 2026-03-22
**대상**: telegram_relay, result_synthesizer, task_poller
**버전**: 1.0 (최초 작성)

---

## Executive Summary (요약본)

### 핵심 결론

> **세 컴포넌트 모두 Skills 이관이 불가능하거나 실익이 없다. 이관 시도 자체가 더 나쁜 선택이다.**

| 컴포넌트 | LoC | 이관 가능성 | 판정 |
|---|---|---|---|
| telegram_relay.py | 4,549 | 구조적 불가 | 현행 유지 필수 |
| task_poller.py | 151 | 구조적 불가 | 현행 유지 필수 |
| result_synthesizer.py | 346 | 기술적 가능하나 실익 없음 | 현행 유지 권고 |

**총 마이그레이션 시도 시 예상 비용**: 개발 28~42인일 + 테스트 12~18인일 = **40~60인일 (약 8~12주)**
**이관 후 실질적 이득**: 0 (아키텍처 개선 없음, 복잡도만 증가)
**권고**: 이관 프로젝트 착수 금지. 비용 전액 낭비.

---

## Phase 1: 현황 분석 및 범위 정의

### 1-1. Skills 아키텍처 실행 모델

현재 Skills는 **마크다운 기반 instruction 파일**로, Claude Code 하네스가 프롬프트 컨텍스트에 주입하는 방식으로 동작한다.

```
skills/
├── quality-gate/SKILL.md       # 린트+테스트 실행 지침
├── engineering-review/SKILL.md  # 코드리뷰 체크리스트
├── bot-triage/SKILL.md         # 봇 장애 진단 절차
└── ... (총 17개 스킬)
```

**Skills의 본질적 제약**:
- On-demand: 호출될 때만 실행, 상시 실행 불가
- Stateless: 호출 간 상태 유지 불가 (메모리 없음)
- Single-execution: 반복 루프·폴링 불가
- No event subscription: MessageBus, asyncio 이벤트 수신 불가
- No daemon: 백그라운드 스레드/태스크 생성 불가

### 1-2. 이관 대상 컴포넌트 현황

#### telegram_relay.py
- **위치**: `core/telegram_relay.py`
- **LoC**: 4,549줄
- **언어/프레임워크**: Python + python-telegram-bot + asyncio
- **핵심 기능**:
  - Telegram Bot API 폴링 (Application.run_polling)
  - `_synthesis_poll_loop()` — 30초 주기 백그라운드 폴러
  - MessageBus 이벤트 발행/구독
  - ClaimManager, ConfidenceScorer, SessionManager 통합
  - 메시지 라우팅, P2P 메신저, 협업 요청 처리
- **import 수**: 45개 (내부 core 모듈 30개 포함)
- **실행 방식**: asyncio 이벤트 루프에서 상시 실행 (daemon process)

#### task_poller.py
- **위치**: `core/task_poller.py`
- **LoC**: 151줄
- **핵심 기능**:
  - ContextDB 2초 주기 폴링
  - 분산 lease 획득 (TTL=180s)
  - 하트비트 갱신 (30초 주기)
  - worker_id 기반 중복 실행 방지
- **import 수**: 8개
- **실행 방식**: asyncio 백그라운드 태스크 (상시 실행)

#### result_synthesizer.py
- **위치**: `core/result_synthesizer.py`
- **LoC**: 346줄
- **핵심 기능**:
  - 부서 결과 LLM 분석 (sufficient/insufficient/conflicting/needs_integration)
  - 판단별 후속 조치 (추가 태스크, 통합 보고서)
  - false_claim 탐지
- **import 수**: 7개
- **실행 방식**: pm_orchestrator가 호출하는 **일반 함수** (비동기 메서드)
- **호출자**: `core/pm_orchestrator.py` (유일한 direct caller)

### 1-3. 외부/내부 의존성 맵

#### telegram_relay 의존성 (30개 내부 모듈)
```
core/message_bus.py          — 이벤트 버스 (EventType.TASK_RESULT 등)
core/session_manager.py      — tmux 세션 관리
core/memory_manager.py       — 메모리 접근
core/pm_identity.py          — PM 정체성
core/claim_manager.py        — 메시지 claim 관리
core/confidence_scorer.py    — 라우팅 신뢰도
core/session_store.py        — 세션 상태
core/global_context.py       — 전역 컨텍스트
core/collab_request.py       — 협업 요청 파싱
core/pm_orchestrator.py      — PM 오케스트레이터
core/task_poller.py          — 태스크 폴러 (포함 관계)
... 19개 추가 모듈
```

#### task_poller 의존성
```
core/context_db.py           — SQLite DB (ContextDB)
asyncio (stdlib)
socket, uuid, os (stdlib)
```

#### result_synthesizer 의존성
```
core/constants.py            — KNOWN_DEPTS
core/pm_decision.py          — DecisionClientProtocol
asyncio (stdlib)
```

---

## Phase 2: 코드 변경 범위 산정

### 2-1. telegram_relay 이관 시 코드 변경 범위

**판정: 이관 불가 (구조적 충돌)**

telegram_relay는 Skills로 이관하면 다음을 모두 포기해야 한다:

| 기능 | 현재 구현 | Skills로 대체 가능? |
|---|---|---|
| Telegram 폴링 루프 | `Application.run_polling()` | 불가 (daemon 필요) |
| synthesis_poll_loop | asyncio 30s 백그라운드 | 불가 (persistent loop) |
| MessageBus 이벤트 수신 | asyncio event subscription | 불가 (stateless) |
| 메시지 claim 관리 | ClaimManager 상태 유지 | 불가 (stateless) |
| 세션 관리 | SessionManager persistent | 불가 |

**이관 시 변경 필요 파일 수**: 31개 이상 (대 규모)

| 카테고리 | 파일 수 | 주요 변경 |
|---|---|---|
| 핵심 실행 파일 | 1 | telegram_relay.py 전면 재작성 |
| 의존 모듈 (인터페이스 변경) | 15+ | message_bus, claim_manager 등 |
| 테스트 파일 | 15+ | TelegramRelay import 전체 |
| main.py, bot 실행 파일 | 3+ | 초기화 코드 |

**예상 개발 공수**: 20~30인일
**변경 규모**: 대 (31개 이상 파일)

### 2-2. task_poller 이관 시 코드 변경 범위

**판정: 이관 불가 (구조적 충돌)**

TaskPoller는 2초 주기 폴링 루프가 핵심이다. Skills는 단발 실행이므로 폴링 자체가 불가능하다. 이관 시 부서봇이 태스크를 자동 수신하는 메커니즘 전체를 대체해야 한다.

**이관 시 변경 필요 파일 수**: 11~20개 (중 규모)

| 카테고리 | 파일 수 |
|---|---|
| task_poller.py 재설계 | 1 |
| worker_bot.py 폴링 로직 | 1 |
| context_db.py 인터페이스 | 1 |
| telegram_relay.py (TaskPoller 사용처) | 1 |
| 테스트 파일 (test_task_poller.py 등) | 3 |
| main.py, 봇 초기화 | 2+ |

**예상 개발 공수**: 5~8인일
**변경 규모**: 중 (11~20개 파일)

### 2-3. result_synthesizer 이관 시 코드 변경 범위

**판정: 기술적 가능하나 실익 없음**

result_synthesizer는 단순 비동기 함수 집합으로, 기술적으로 Skills로 이관이 가능하다.
그러나 **pm_orchestrator.py가 여전히 존재해야 하고**, pm_orchestrator가 result_synthesizer를 호출하는 구조를 Skill로 변경해도 pm_orchestrator 자체는 제거되지 않는다.

```
현재:  pm_orchestrator → result_synthesizer.synthesize()
이관 후: pm_orchestrator → [Skill 호출] → LLM → 응답 파싱
```

**이관 시 변경 필요 파일 수**: 3~5개 (소 규모)

| 카테고리 | 주요 변경 |
|---|---|
| result_synthesizer.py | Skill SKILL.md로 교체 |
| pm_orchestrator.py | result_synthesizer import 제거, Skill 호출로 교체 |
| 테스트 3개 파일 | 전면 재작성 |

**예상 개발 공수**: 3~4인일
**변경 규모**: 소 (3~5개 파일)
**실질 이득**: 없음 (pm_orchestrator 삭제 불가, 복잡도만 증가)

### 2-4. 합산 개발 공수

| 컴포넌트 | 공수 (인일) | 규모 분류 |
|---|---|---|
| telegram_relay | 20~30 | 대 |
| task_poller | 5~8 | 중 |
| result_synthesizer | 3~4 | 소 |
| **합계** | **28~42** | — |

---

## Phase 3: 테스트 커버리지 분석

### 3-1. 현행 테스트 현황

**전체 테스트**: 868개 (868 passed, 0 failed — 100% pass rate)

**이관 대상 모듈 관련 테스트**:

| 테스트 파일 | 테스트 수 | LoC | 관련 모듈 |
|---|---|---|---|
| test_result_synthesizer.py | 21 | 334 | result_synthesizer |
| test_task_poller.py | 11 | 215 | task_poller |
| test_task_poller_release.py | 3 | ~80 | task_poller |
| test_telegram_relay_collab.py | 2 | 80 | telegram_relay |
| test_telegram_relay_formatting.py | ~5 | ~100 | telegram_relay |
| test_pm_intercept.py | ~15 | 367 | telegram_relay |
| test_collab_e2e.py | ~10 | 216 | telegram_relay |
| test_collab_mode.py | ~8 | 158 | telegram_relay |
| test_notify_task_done_auto.py | ~5 | ~120 | telegram_relay |
| test_pm_task_workdir.py | ~5 | ~100 | telegram_relay |
| **합계** | **~85개** | **~1,770** | — |

**현행 커버리지 추정**: 이관 대상 3개 모듈에 대해 약 70~75%

### 3-2. 이관 후 신규 테스트 케이스 필요 범위

**telegram_relay 이관 시**:
- Telegram bot Application을 Skills로 대체할 경우 기존 85개 테스트 전면 재작성
- Skills 호출 mock, 이벤트 루프 mock 구성 필요
- 신규 테스트 작성 공수: **8~12인일**

**task_poller 이관 시**:
- 폴링 로직 테스트 → Skills 단발 실행 테스트로 교체
- lease/heartbeat 테스트 전면 재작성
- 신규 테스트 작성 공수: **2~3인일**

**result_synthesizer 이관 시**:
- 21개 단위 테스트 → Skill 입출력 테스트로 교체
- LLM 응답 파싱 mock 재구성
- 신규 테스트 작성 공수: **2~3인일**

### 3-3. 회귀 테스트 범위

이관 시 직접 영향을 받는 연동 테스트:

| 테스트 파일 | 영향 유형 |
|---|---|
| test_collab_e2e.py | TelegramRelay 전면 사용 — 전체 재작성 필요 |
| test_pm_intercept.py | TelegramRelay 15회 import — 전체 재작성 필요 |
| test_debate_mode.py | result_synthesizer import — 수정 필요 |
| test_discussion_dispatch.py | ResultSynthesizer import — 수정 필요 |

**회귀 테스트 공수**: **2~3인일** 추가

### 3-4. 테스트 환경 구성 비용

| 항목 | 소요 시간 |
|---|---|
| Skills 테스트 harness 구성 | 1인일 |
| 목 서버 (LLM mock) 재구성 | 0.5인일 |
| 스테이징 환경 Skill 로더 테스트 | 0.5인일 |
| 데이터 픽스처 재작성 | 0.5인일 |

**환경 구성 합계**: 2.5인일

### 3-5. 목표 커버리지 기준

| 기준 | 현행 | 이관 후 목표 |
|---|---|---|
| 전체 테스트 pass rate | 100% (868/868) | 100% 유지 필수 |
| 이관 대상 모듈 커버리지 | 70~75% | 80% 이상 |
| 회귀 테스트 통과율 | 100% | 100% 유지 필수 |

**테스트 전체 공수 합계**: 12~18인일

---

## Phase 4: 기술적 리스크 식별 및 등급화

### 4-1. 리스크 전체 목록

#### ① 호환성 리스크

| ID | 리스크 | 가능성 | 영향도 | 등급 |
|---|---|---|---|---|
| C-1 | telegram_relay의 45개 import 중 Skills 환경에서 실행 불가 모듈 (python-telegram-bot 등) | 상 | 상 | **Critical** |
| C-2 | asyncio 이벤트 루프를 Skills 실행 컨텍스트에서 사용 불가 | 상 | 상 | **Critical** |
| C-3 | Skills 버전 업그레이드 시 내부 Python 인터페이스 호환성 파괴 | 중 | 중 | High |

#### ② 데이터 정합성 리스크

| ID | 리스크 | 가능성 | 영향도 | 등급 |
|---|---|---|---|---|
| D-1 | task_poller 이관 시 lease 상태 손실로 태스크 중복 실행 | 상 | 상 | **Critical** |
| D-2 | result_synthesizer 이관 후 LLM 응답 파싱 불일치로 follow_up 태스크 미생성 | 중 | 상 | High |
| D-3 | 이관 전환 기간 중 pm_tasks 상태 불일치 (pending/assigned 혼재) | 중 | 중 | Medium |

#### ③ 성능 리스크

| ID | 리스크 | 가능성 | 영향도 | 등급 |
|---|---|---|---|---|
| P-1 | task_poller 이관 시 2초 폴링 → Skills 호출 지연 (최소 5~10초) | 상 | 상 | **Critical** |
| P-2 | synthesis_poll_loop 상실로 완료 태스크 미합성 (무응답) | 상 | 상 | **Critical** |
| P-3 | Skills LLM 호출 추가로 result_synthesizer 레이턴시 2배 증가 | 상 | 중 | High |

#### ④ 보안 리스크

| ID | 리스크 | 가능성 | 영향도 | 등급 |
|---|---|---|---|---|
| S-1 | TELEGRAM_BOT_TOKEN이 Skills SKILL.md 파일에 노출될 수 있음 | 중 | 상 | High |
| S-2 | Skills 컨텍스트에서 인증 체계 우회 가능성 | 하 | 상 | Medium |

#### ⑤ 운영 리스크

| ID | 리스크 | 가능성 | 영향도 | 등급 |
|---|---|---|---|---|
| O-1 | telegram_relay 이관 실패 시 전체 봇 서비스 중단 (롤백 복잡) | 중 | 상 | **Critical** |
| O-2 | task_poller 이관 중 부서봇 태스크 수신 불가 (배포 의존성) | 상 | 상 | **Critical** |
| O-3 | 이관 중 기존 868개 테스트 일부 실패 → CI 파이프라인 블로킹 | 상 | 중 | High |

### 4-2. 리스크 등급 매트릭스

```
영향도
  상  | C-1** C-2** | D-1** P-1** P-2** | O-1** O-2**
  중  | C-3         | D-2  P-3  S-1    | D-3  O-3
  하  |             | S-2              |
      +-고가능성----+-중가능성----------+-저가능성--
                    가능성
```

**Critical (즉각 대응)**: C-1, C-2, D-1, P-1, P-2, O-1, O-2 — **7개**
**High**: C-3, D-2, P-3, S-1, O-3 — **5개**
**Medium**: D-3, S-2 — **2개**

### 4-3. Critical 리스크 대응 방안

| ID | 대응 방안 | 컨틴전시 플랜 |
|---|---|---|
| C-1, C-2 | **이관 포기** — asyncio daemon은 Skills로 실행 불가 | 현행 core/ 구조 유지 |
| D-1, P-1, P-2 | **이관 포기** — 폴링 기반 시스템은 Skills의 stateless 모델과 근본 충돌 | TaskPoller core/ 유지 |
| O-1, O-2 | 이관을 시도할 경우 블루/그린 배포 + feature flag 필요 | 롤백 플랜: git revert + 재배포 |

---

## Phase 5: 종합 비용 및 마이그레이션 로드맵

### 5-1. 총 마이그레이션 비용 산출서

| 항목 | 공수 (인일) | 비고 |
|---|---|---|
| 개발 공수 (telegram_relay) | 20~30 | 이관 불가 판정으로 실제 집행 금지 |
| 개발 공수 (task_poller) | 5~8 | 이관 불가 판정으로 실제 집행 금지 |
| 개발 공수 (result_synthesizer) | 3~4 | 실익 없어 집행 불권고 |
| 테스트 작성 공수 | 12~18 | 이관 시 기존 테스트 전면 재작성 필요 |
| 테스트 환경 구성 | 2~3 | Skills harness, mock 서버 |
| **총합** | **42~63인일** | **약 8~13주 (1인 기준)** |
| **실질 이득** | **0** | 아키텍처 개선 없음 |
| **ROI** | **-100%** | 순비용만 발생 |

### 5-2. Skills 이관 우선순위 결정

비즈니스 임팩트 × 마이그레이션 난이도 역수로 산정:

| 컴포넌트 | 비즈니스 임팩트 | 난이도 | 우선순위 점수 | 결론 |
|---|---|---|---|---|
| telegram_relay | 최상 (서비스 진입점) | 불가능 | 0 | 이관 금지 |
| task_poller | 상 (부서봇 태스크 수신) | 불가능 | 0 | 이관 금지 |
| result_synthesizer | 중 (합성 품질) | 가능하나 실익 없음 | 0.1 | 이관 비권고 |

**모든 컴포넌트의 우선순위: 없음 (이관 착수하지 않음)**

### 5-3. 마이그레이션 로드맵 (가상 시나리오 — 참고용)

> ⚠️ 아래는 "강행할 경우"의 가상 로드맵이며, 실행을 권고하지 않음

```
Week 1-2:  result_synthesizer 이관 시도 (가장 작은 범위, 소 규모)
           → test_result_synthesizer.py 21개 재작성
           → pm_orchestrator.py 수정
Week 3-8:  task_poller 대안 아키텍처 설계 (폴링 대체 메커니즘 필요)
           → DB trigger 또는 webhook 방식 탐색
Week 9-20: telegram_relay 대체 불가 — 프로젝트 중단
```

### 5-4. 롤백 기준 및 Go/No-Go 판단

| 기준 | 임계값 |
|---|---|
| 테스트 pass rate 저하 | 868개 중 1개라도 실패 → 즉시 롤백 |
| 레이턴시 증가 | task 수신 지연 2초 초과 → 롤백 |
| 서비스 중단 | Telegram 응답 없음 30초 이상 → 긴급 롤백 |
| 데이터 손실 | pm_tasks 상태 불일치 발견 → 즉시 중단 |

**Go/No-Go 판단**: 현 시점 **No-Go** (구조적 불가 + 이득 없음)

---

## 최종 권고

### 현행 유지 결정 근거

1. **telegram_relay**: 4,549 LoC의 stateful async daemon. Telegram 폴링 루프와 30초 synthesis_poll_loop이 핵심. Skills의 on-demand stateless 모델과 **근본적 충돌**. 이관 시 서비스 전체 중단.

2. **task_poller**: 2초 주기 폴링 + lease/heartbeat 유지. Skills는 단발 실행이므로 **물리적으로 폴링 불가**. 이관 시 부서봇 태스크 수신 메커니즘 전체 붕괴.

3. **result_synthesizer**: 기술적으로 이관 가능하나, 호출자인 pm_orchestrator가 여전히 남아야 하므로 이관해도 삭제되는 코드가 없음. 복잡도만 증가.

### 대안 제안

Skills 이관 대신 다음 방향이 더 효과적:
- result_synthesizer 품질 향상: 현재 위치에서 프롬프트 튜닝 및 판단 로직 개선
- task_poller 안정성 향상: lease TTL 최적화, 하트비트 간격 조정
- telegram_relay 모듈 분리: 4,549 LoC를 기능별 모듈로 분리 (이관 없이 유지보수성 향상)
