# Skills 이관 아키텍처 권고안
> 작성일: 2026-03-22 | 작성 조직: 기획실(aiorg_product_bot)
> 검토 대상: telegram_relay, result_synthesizer, task_poller 및 전체 core/ 컴포넌트

---

## 핵심 결론 (Executive Summary)

**`telegram_relay`, `task_poller`는 Skills 이관이 구조적으로 불가능하다.
`result_synthesizer`는 이관이 가능하나 실익이 없다.
→ 세 컴포넌트 모두 현행 유지가 최선이며, Skills 이관은 더 나쁜 선택이다.**

이유는 단 하나의 구조적 충돌로 요약된다:

> **Skills = on-demand · stateless · 단발 실행 (prompt-driven procedure)**
> **이 컴포넌트들 = 지속 실행 · 상태 보존 · 이벤트 반응 (persistent daemon)**

이 두 가지는 근본적으로 다른 실행 모델이다. Skills 파일은 Claude가 실행 중에 참조하는
"절차 지침서(Markdown)"이지, asyncio 루프나 폴링 서버를 대체할 수 없다.

---

## Phase 1: 현황 분석 결과

### 1-1. 전체 Skills 현황 목록표

| 스킬명 | 유형 | 복잡도 | 재사용성 | 관리 팀 | 비고 |
|--------|------|--------|---------|---------|------|
| quality-gate | 품질검사 절차 | Low | High | 전조직 | hooks(PostToolUse) 포함 |
| bot-triage | 장애 진단 절차 | Mid | Mid | Ops | templates/스크립트 포함 |
| brainstorming-auto | 자율 설계 절차 | Low | High | PM | 사용자 승인 없는 설계 |
| error-gotcha | 에러 회고 절차 | Low | High | 전조직 | gotcha DB 업데이트 |
| pm-task-dispatch | PM 태스크 위임 절차 | Mid | Mid | PM | - |
| pm-discussion | 토론 진행 절차 | Low | Low | PM | - |
| retro | 회고 절차 | Low | Low | 전조직 | - |
| weekly-review | 주간회의 절차 | Mid | Low | PM | - |
| engineering-review | 코드 리뷰 절차 | Low | Mid | Engineering | - |
| growth-analysis | 성장 분석 절차 | Low | Low | Growth | - |
| design-critique | 디자인 비평 절차 | Low | Low | Design | - |
| harness-audit | 하네스 감사 | Mid | Low | Ops | - |
| skill-evolve | 스킬 자동 개선 | Mid | Low | PM | - |
| create-skill | 스킬 생성 절차 | Low | Mid | PM | - |
| autonomous-skill-proxy | 자율 프록시 | High | Low | PM | - |
| performance-eval | 성과 평가 | Low | Low | PM | - |
| loop-checkpoint | 루프 체크포인트 | Low | Low | PM | - |

**Skills의 공통 특성 (실제 파일 구조 기반)**:
- 모두 `SKILL.md` (Markdown 절차서) + 선택적 `scripts/` + `gotchas.md`로 구성
- `hooks:` 섹션은 harness가 실행하는 트리거이지, 상시 실행 프로세스가 아님
- 상태를 자체 저장하지 않음 (외부 DB/파일 참조만 허용)

---

### 1-2. 이관 후보 컴포넌트별 운영 현황 보고서

#### `core/telegram_relay.py` — 4,549 lines
- **역할**: Telegram Bot API ↔ tmux Claude Code 세션 중계 서버
- **실행 모델**: `Application.run_polling()` — 상시 실행 asyncio 이벤트 루프
- **의존성**: 16개 core 모듈 import, Telegram Bot API, SessionManager, ClaimManager, ConfidenceScorer, PMRouter, PMOrchestrator 등
- **상태 보존**: 세션 상태, claim 파일, confidence scoring, 전달 대상 캐시
- **운영 Pain Point**: 재기동 시 진행 중인 태스크 유실 위험 → `request_restart.sh` watchdog 운영 중
- **현재 장애 패턴**: 봇 응답 없음 시 `bot-triage` 스킬로 진단

#### `core/task_poller.py` — 151 lines
- **역할**: 부서봇이 ContextDB를 폴링하여 배정된 태스크를 자동 수신
- **실행 모델**: `asyncio.create_task(_poll_loop())` — 상시 실행 백그라운드 루프
- **상태 보존**: `_processing` set(중복 방지), heartbeat_tasks dict, lease TTL 관리
- **배경**: Telegram Bot API는 bot→bot 메시지 수신 불가 → DB 폴링으로 우회
- **운영 Pain Point**: stale lease 복구 로직 필요 (시작 시 자동 복구 구현됨)

#### `core/result_synthesizer.py` — 346 lines
- **역할**: 여러 부서 결과를 LLM으로 분석·판단·통합 보고서 생성
- **실행 모델**: 클래스 메서드 호출 (stateless pure computation)
- **의존성**: `DecisionClientProtocol` 런타임 주입 (LLM 클라이언트), `core.constants`, `core.pm_decision`
- **상태 보존**: 없음 (완전 stateless)
- **운영 Pain Point**: LLM timeout(180s), false_claim 감지 로직 유지보수 필요

---

## Phase 2: 의사결정 기준 프레임워크

### 2-1. 이관 의사결정 기준 정의서

Skills의 본질적 특성에서 도출한 4개 판단 기준:

**[기준 A] 실행 모델 호환성** (가중치: 35%)
Skills는 단발 on-demand 실행만 가능. 상시 실행(daemon/event-loop/polling)이 필요하면 이관 불가.

| 등급 | 정의 | 점수 |
|------|------|------|
| Compatible(3) | 단발 실행, 완료 후 종료 가능 | 3 |
| Partial(2) | 대부분 단발이나 일부 상태 필요 | 2 |
| Incompatible(0) | 상시 실행/이벤트 루프/폴링 필수 | 0 |

**[기준 B] 복잡도** (가중치: 25%)
로직 분기 수, 외부 API 의존성, 코드 규모 기준.

| 등급 | 정의 | 점수 |
|------|------|------|
| Low(3) | ~200 lines, 분기 3개 이하, API 의존 없음 | 3 |
| Mid(2) | 200~1000 lines, 분기 5개 이하, API 1~2개 | 2 |
| High(1) | 1000+ lines, 다수 분기, API 3개 이상 | 1 |

**[기준 C] 재사용성** (가중치: 25%)
여러 조직/시나리오에서 반복 호출되는지 여부.

| 등급 | 정의 | 점수 |
|------|------|------|
| High(3) | 3개 이상 조직 사용, 범용 패턴 | 3 |
| Mid(2) | 1~2개 조직 사용, 일부 특화 | 2 |
| Low(1) | 단일 조직·단일 시나리오 전용 | 1 |

**[기준 D] 이관 실익** (가중치: 15%)
이관으로 얻는 유지보수 개선, 표준화, 재사용 이익.

| 등급 | 정의 | 점수 |
|------|------|------|
| High(3) | 코드 중복 제거, 표준화 효과 명확 | 3 |
| Mid(2) | 일부 정리 효과 있으나 제한적 | 2 |
| Low(1) | 이관해도 기존 코드 잔존, 실익 없음 | 1 |

---

### 2-2. 정량 평가 매트릭스 (가중치 적용)

```
총점 = (A점수 × 0.35) + (B점수 × 0.25) + (C점수 × 0.25) + (D점수 × 0.15)
최고점: 3.0 | 이관 적합 기준: ≥ 2.0 | 부적합 기준: < 1.5
```

| 컴포넌트 | A(×0.35) | B(×0.25) | C(×0.25) | D(×0.15) | **총점** | **판정** |
|---------|----------|----------|----------|----------|---------|---------|
| telegram_relay | 0 (0×0.35) | 0.25 (1×0.25) | 0.75 (3×0.25) | 0.15 (1×0.15) | **1.15** | ❌ 부적합 |
| task_poller | 0 (0×0.35) | 0.75 (3×0.25) | 0.5 (2×0.25) | 0.15 (1×0.15) | **1.40** | ❌ 부적합 |
| result_synthesizer | 1.05 (3×0.35) | 0.75 (3×0.25) | 0.5 (2×0.25) | 0.15 (1×0.15) | **2.45** | ⚠️ 가능하나 실익 無 |

---

## Phase 3: 컴포넌트 분류 결과

### 3-1. 분류 결과표

#### ❌ 이관 부적합: `telegram_relay.py`

| 항목 | 판단 근거 |
|------|---------|
| **A: 실행 모델** | `Application.run_polling()` — Telegram Bot API 이벤트 루프 상시 실행 필수. Skills 호출로는 절대 대체 불가 |
| **B: 복잡도** | 4,549 lines, 16개 core 모듈 의존, Telegram/asyncio/claim/routing 등 다계층 로직 |
| **C: 재사용성** | 높으나 의미 없음 — 이관 불가 컴포넌트이므로 재사용성 평가 무의미 |
| **D: 이관 실익** | 없음. Skills로 이관 시 이벤트 기반 수신 자체가 불가능 → 시스템 전체 중단 |
| **부적합 사유** | Skills는 "Claude가 작업 중 참조하는 절차서"이지 "서버 프로세스"가 아님. telegram_relay를 Skills로 바꾸면 Telegram 메시지 수신 자체가 불가능해짐 |
| **향후 재검토 조건** | Skills 실행 모델이 "상시 실행 프로세스" 지원으로 확장될 경우 (현재 로드맵에 없음) |

---

#### ❌ 이관 부적합: `task_poller.py`

| 항목 | 판단 근거 |
|------|---------|
| **A: 실행 모델** | `asyncio.create_task(_poll_loop())` — 2초 간격 상시 폴링 루프. 단발 실행 불가 |
| **B: 복잡도** | 151 lines로 작지만 내부 상태(processing set, heartbeat_tasks, lease TTL)가 루프 생명주기 전체에 걸쳐 유지됨 |
| **C: 재사용성** | 전 부서봇이 사용 (높음). 그러나 이관 불가이므로 무의미 |
| **D: 이관 실익** | 없음. Skills로 이관 시 heartbeat, stale 복구, lease 관리 모두 소실됨 |
| **부적합 사유** | `_processing` set과 heartbeat 루프는 프로세스 생명주기 전체 동안 상태를 유지해야 함. 단발 실행 Skills는 이 상태를 보존할 방법이 없음 |
| **향후 재검토 조건** | Telegram Bot API에서 bot→bot 메시지 수신이 지원될 경우 (poll 자체가 불필요해짐) |

---

#### ⚠️ 이관 가능하나 권장하지 않음: `result_synthesizer.py`

| 항목 | 판단 근거 |
|------|---------|
| **A: 실행 모델** | 완전 stateless. 클래스 인스턴스 생성 후 메서드 호출 → 단발 실행 가능 |
| **B: 복잡도** | 346 lines, LLM 프롬프트 + 파싱 로직. Mid-Low 수준 |
| **C: 재사용성** | PM 오케스트레이터 단독 사용. 특화 로직 |
| **D: 이관 실익** | **없음**. `DecisionClientProtocol`은 런타임 주입 객체 → Skills에서 이 인터페이스를 연결할 방법이 없음. 기존 `pm_orchestrator.py` 내 호출 코드는 그대로 잔존해야 함. Skills로 이관해도 `core/result_synthesizer.py`를 삭제할 수 없음 → 이중화만 발생 |
| **권장하지 않는 이유** | 이관 시 LLM 클라이언트 주입 없이 Skills 단독으로 실행 불가. 실제로는 "스킬 절차서"가 아니라 "런타임 의존성이 있는 Python 클래스"이므로 Skills 레이어와 근본적으로 맞지 않음 |
| **향후 재검토 조건** | Skills가 Python 객체 컨텍스트를 직접 수신할 수 있는 인터페이스가 생길 경우 |

---

### 3-2. 우선순위별 이관 후보 목록 (전체 core/ 컴포넌트 대상)

실제로 Skills 이관이 유효한 컴포넌트는 다음 기준을 충족해야 한다:
- 단발 실행 가능
- 절차/지침 성격
- 여러 조직에서 재사용 가능

| 우선순위 | 컴포넌트 | 이관 근거 |
|---------|---------|---------|
| **즉시 가능** | `code_health.py` (규칙 검사 절차) | 단발 실행, 체크리스트 성격 |
| **즉시 가능** | `staleness_checker.py` (데이터 신선도 검사) | 단발 실행, 범용 패턴 |
| **단기** | `routing_optimizer.py` (라우팅 규칙 분석) | 부분 stateless, 분석 절차 |
| **중기** | `nl_classifier.py` (NL 분류 로직) | LLM 의존이나 단발 가능 |
| **이관 불가** | telegram_relay, task_poller, pm_orchestrator, session_manager, message_bus | 상시 실행 필수 |
| **이관 불필요** | result_synthesizer, dispatch_engine, completion | 실익 없음 |

---

## Phase 4: 아키텍처 권고안

### 4-1. 목표 아키텍처 (현행 유지 + 경계 명확화)

```
┌─────────────────────────────────────────────────────┐
│              Persistent Layer (현행 유지)              │
│  telegram_relay ──► session_manager ──► worker_bot  │
│  task_poller ──► context_db ──► pm_orchestrator     │
│  result_synthesizer (pm_orchestrator에 내장)          │
└─────────────────────────────────────────────────────┘
                          │ 필요 시 호출
┌─────────────────────────────────────────────────────┐
│           Skills Layer (단발 절차서 영역)               │
│  quality-gate, bot-triage, brainstorming-auto, ...  │
│  → 여기에 telegram_relay/task_poller 추가 금지         │
└─────────────────────────────────────────────────────┘
```

**핵심 아키텍처 원칙:**

1. **Skills = 절차서 레이어**: Claude가 작업 중 "어떻게 할 것인가"를 정의하는 지침. 서비스 실행이 아님
2. **Core = 서비스 레이어**: 상시 실행, 이벤트 반응, 상태 보존이 필요한 컴포넌트는 core/에 유지
3. **경계 원칙**: "이 컴포넌트가 꺼지면 시스템이 동작하는가?" → 아니면 Core, 예스이면 Skills 후보

---

### 4-2. 이관 로드맵 (실제 이관 가능 컴포넌트만)

| 단계 | 기간 | 대상 | 담당 |
|------|------|------|------|
| Phase 1 | 즉시 | `code_health.py` 규칙을 skill로 문서화 (코드 삭제 아님, 절차 문서화) | PM + Engineering |
| Phase 2 | 1주 | `staleness_checker` 점검 기준을 `harness-audit` 스킬에 통합 | PM |
| Phase 3 | 2~4주 | `routing_optimizer` 분석 결과를 Skills 트리거 조건으로 문서화 | PM + Engineering |
| **금지** | - | telegram_relay, task_poller, result_synthesizer Skills 이관 | - |

---

### 4-3. 리스크 및 완화 방안

| 리스크 | 심각도 | 완화 방안 |
|--------|--------|---------|
| telegram_relay를 Skills로 이관 시 봇 수신 불가 | **Critical** | 이관 금지. 현행 watchdog 방식 유지 |
| task_poller 이관 시 부서봇 태스크 미수신 | **Critical** | 이관 금지. poll 방식은 Telegram API 제약에 의한 필수 설계 |
| result_synthesizer 이관 시 LLM 클라이언트 연결 불가 | **High** | 이관 불필요. pm_orchestrator 내 현행 위치 유지 |
| 이관 가능 컴포넌트의 코드 이중화 | **Low** | Skills는 절차 "문서화"이지 코드 복사 아님. 원본 코드 유지하되 Skills에 실행 절차만 기술 |

---

## 경영진 보고용 요약

### Skills 이관 여부: **이관하지 않는다**

**판단 근거 (한 줄)**:
`telegram_relay`와 `task_poller`는 "서버 프로세스"이고, Skills는 "절차서"다. 이 두 개념은 대체 관계가 아니다.

**기술적 세부 근거**:
- Skills는 Claude가 실행 중 참조하는 Markdown 기반 절차서. asyncio 이벤트 루프나 폴링 루프를 실행하는 구조가 아님
- `telegram_relay`(4,549 lines)를 Skills로 이관하면 Telegram 메시지 수신 자체가 불가능해짐
- `task_poller`를 이관하면 모든 부서봇이 태스크를 받지 못함
- `result_synthesizer`는 이관 가능하지만, 런타임 LLM 클라이언트 주입이 필요해 Skills 독립 실행이 불가. 이관해도 원본 코드가 반드시 잔존 → 이중화만 발생

**권고 액션**:
1. 세 컴포넌트 현행 위치(`core/`) 유지
2. Skills 레이어는 "절차서 도구"로만 활용 (quality-gate, bot-triage 등 현행 방식 유지)
3. 향후 Skills 이관 검토 시 본 문서의 의사결정 매트릭스 적용 (기준 A: 실행 모델 호환성이 0점이면 즉시 배제)

---

*문서 위치: docs/skills-migration-architecture-recommendation.md*
*다음 재검토 시점: Skills 실행 모델 변경 시 또는 분기별 아키텍처 리뷰 시*
