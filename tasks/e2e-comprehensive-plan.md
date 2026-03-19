# telegram-ai-org 전체 E2E 테스트 계획

> 작성일: 2026-03-19
> 작성자: Planner Agent (자율 모드)
> 상태: DRAFT — Rocky 확인 대기

---

## 1. RALPLAN-DR 요약

### 원칙 (Principles)
1. **기존 패턴 유지**: 현재 테스트는 pytest + AsyncMock + MagicMock 기반. 동일 패턴으로 작성한다.
2. **실제 DB 사용 최소화**: ContextDB는 tmp_path에 SQLite로 생성, 외부 의존성(Telegram API, LLM) 전부 mock.
3. **격리된 테스트**: 각 테스트 카테고리(A~E)가 독립적으로 실행 가능해야 한다.
4. **점진적 복잡도**: 단위 테스트 → 통합 테스트 → E2E 시나리오 순서로 구축.
5. **봇 간 통신 무결성**: 메타데이터 분리 설계는 기존 P2P/collab/discussion 프로토콜을 깨지 않아야 한다.

### 결정 드라이버 (Decision Drivers)
1. **커버리지 우선순위**: PM 업무 처리 모드(C) > 성격 진화(A) > 핑퐁 대화(B) > 협업(D) > 메타데이터 분리(E)
2. **실행 시간 제약**: 전체 테스트 스위트가 60초 이내 완료되어야 한다 (LLM mock 전제).
3. **메타데이터 분리(E)는 신규 기능**: 설계 제안 + 프로토타입 테스트만 포함. 기존 코드 변경 최소화.

### 옵션 비교

| 옵션 | 설명 | 장점 | 단점 |
|------|------|------|------|
| **A: 인메모리 통합 테스트** | ContextDB(tmp SQLite) + mock LLM + mock Telegram으로 전체 흐름 검증 | 빠름, CI 친화적, 외부 의존성 없음 | 실제 LLM 응답 품질 미검증 |
| **B: Telegram Bot API 실제 호출** | 테스트용 봇 토큰으로 실제 API 호출 | 실제 환경 검증 | 느림, 토큰 필요, CI 불안정 |

**선택: 옵션 A** — 인메모리 통합 테스트. 옵션 B는 비결정적이고 CI에서 불안정하므로 제외. 실제 LLM 품질은 별도 수동 E2E 세션으로 검증.

---

## 2. 단계별 구현 계획

### Phase 1: 테스트 인프라 구축
**파일**: `tests/conftest.py` (공통 fixture 추가), `tests/e2e/conftest.py` (E2E 전용)

**할 일**:
- [ ] E2E 테스트 디렉토리 `tests/e2e/` 생성
- [ ] 공통 fixture 작성:
  - `make_orchestrator()`: ContextDB(tmp) + TaskGraph + ClaimManager + MemoryManager + mock send_fn
  - `make_discussion_manager()`: ContextDB + mock send_fn
  - `fake_decision_client()`: 미리 정의된 JSON 응답을 반환하는 mock DecisionClientProtocol
  - `fake_orchestration_config()`: `_FakeConfig` (기존 test_collab_e2e.py 패턴 재사용)
  - `persona_memory(tmp_path)`: AgentPersonaMemory(db_path=tmp/test.db)
  - `collaboration_tracker(tmp_path)`: CollaborationTracker(db_path=tmp/collab.db)
  - `shoutout_system(tmp_path)`: ShoutoutSystem(db_path=tmp/shoutout.db)

**검증 기준**: `pytest tests/e2e/ --co` 로 테스트 수집 성공, fixture import 에러 없음.

---

### Phase 2: 카테고리 A — 조직 이벤트 → 성격 진화 테스트
**파일**: `tests/e2e/test_character_evolution_e2e.py`

#### TC-A1: 태스크 성공 누적 → strengths 자동 추가
- AgentPersonaMemory에 agent "bot_a"의 coding 성공 3회 기록
- BotCharacterEvolution.evolve("bot_a") 호출
- **검증**: result["strengths"]에 "coding" 포함

#### TC-A2: 태스크 실패 누적 → weaknesses 자동 추가
- AgentPersonaMemory에 failure_pattern "timeout" 3회 기록
- BotCharacterEvolution.evolve("bot_a") 호출
- **검증**: result["weaknesses"]에 "timeout" 포함

#### TC-A3: 시너지 점수 추적
- CollaborationTracker.record()로 (bot_a, bot_b) 협업 성공 5회 기록
- AgentPersonaMemory의 synergy_scores 확인
- BotCharacterEvolution.evolve("bot_a") 호출
- **검증**: result["best_partner"] == "bot_b"

#### TC-A4: evolve_all — 전체 봇 진화 일괄 실행
- 3개 봇에 각각 다른 성공/실패 패턴 기록
- BotCharacterEvolution.evolve_all() 호출
- **검증**: 3개 dict 반환, 각각 올바른 strengths/weaknesses

#### TC-A5: get_evolution_summary — 텔레그램 출력 포맷
- bot_a에 coding 성공 5회, timeout 실패 3회, bot_b와 시너지 기록
- get_evolution_summary("bot_a") 호출
- **검증**: 반환 문자열에 "coding", "timeout", "bot_b" 포함

#### TC-A6: 시간 경과 누적 진화 시뮬레이션
- 3라운드 진화 시뮬레이션: 각 라운드마다 태스크 기록 추가 후 evolve()
- **검증**: 라운드별 strengths 목록이 단조증가 (이전 라운드 strengths 포함)

**검증 기준**: 6개 TC 전부 PASS.

---

### Phase 3: 카테고리 B — 자율 봇 핑퐁 대화 테스트
**파일**: `tests/e2e/test_pingpong_conversation_e2e.py`

#### TC-B1: discussion_dispatch → 다중 라운드 서브태스크 생성
- PMOrchestrator.discussion_dispatch(topic, dept_hints=["bot_a", "bot_b"], rounds=3) 호출
- **검증**: create_pm_task가 부모 1회 + 라운드별 서브태스크 생성 호출됨

#### TC-B2: 핑퐁 라운드 진행 — 이전 라운드 결과가 다음 라운드 프롬프트에 포함
- 라운드 1 서브태스크 완료 (result="AI 도입이 필요합니다")
- advance_discussion_round() 호출
- 라운드 2 서브태스크 생성 시 description에 라운드 1 결과 포함 확인
- **검증**: 라운드 2 서브태스크의 description에 "AI 도입이 필요합니다" 문자열 포함

#### TC-B3: 라운드 최대치 도달 시 자동 종료
- rounds=2로 설정, 라운드 2 완료 후
- **검증**: 부모 태스크 상태가 "done"으로 전환

#### TC-B4: 페르소나 컨텍스트 주입 검증
- AgentPersonaMemory에 bot_a의 strengths=["coding"], weaknesses=["design"] 기록
- discussion_dispatch 시 서브태스크 description에 페르소나 컨텍스트 포함 확인
- **검증**: description에 strengths/weaknesses 정보 포함 (기존 test_discussion_pingpong.py TC2 패턴)

#### TC-B5: DiscussionManager 수렴 감지
- DiscussionManager.add_message()로 PROPOSE → OPINION → DECISION 순서 메시지 추가
- **검증**: DECISION 메시지 후 토론 상태가 "decided"로 전환

**검증 기준**: 5개 TC 전부 PASS.

---

### Phase 4: 카테고리 C — PM 업무 처리 모드 전체 테스트
**파일**: `tests/e2e/test_pm_modes_e2e.py`

#### TC-C1: 직접 답변 모드 (plan_request → direct_reply)
- 입력: "안녕하세요" (인사)
- **검증**: plan.route == "direct_reply", plan.lane == "direct_answer"

#### TC-C2: 업무 위임 모드 (plan_request → delegate + decompose)
- 입력: "이 API를 개발해줘"
- plan_request() → decompose() → 서브태스크 생성
- **검증**: plan.route == "delegate", subtasks에 engineering dept 포함

#### TC-C3: 토론 주재 모드 (interaction_mode == "discussion")
- fake_decision_client가 interaction_mode="discussion" 반환하도록 설정
- plan_request() 결과의 interaction_mode 확인
- discussion_dispatch() 호출 → 부모 태스크 + 서브태스크 생성
- **검증**: interaction_mode == "discussion", 서브태스크 metadata에 discussion_round 존재

#### TC-C4: 협업 유도 모드 (collab_dispatch)
- collab_dispatch(parent_task_id, task, target_org, requester_org) 호출
- **검증**: 생성된 서브태스크의 metadata에 collab=True, collab_requester 포함

#### TC-C5: 스케줄 등록 모드 (PMRouter → NLClassifier)
- PMRouter.route("매일 오전 9시에 리포트 보내줘") 호출
- **검증**: route.action == "new_task" (스케줄은 new_task로 라우팅 후 별도 처리)

#### TC-C6: 자율 판단 — 모드 선택 로직 검증
- 6가지 입력(인사, 코딩, 리서치, 기획, 멀티부서, 모호)에 대해 plan_request() 호출
- **검증**: 각 입력에 대해 올바른 lane/route/interaction_mode 조합 반환 (기존 integration test 시나리오 확장)

#### TC-C7: PMRouter fallback — LLM 실패 시 휴리스틱 동작
- decision_client=None으로 PMRouter 생성
- "다시해줘" → retry_task, "상태" → status_query, "응" (with pending) → confirm_pending
- **검증**: 각 fallback 라우팅 정확

**검증 기준**: 7개 TC 전부 PASS.

---

### Phase 5: 카테고리 D — 자율 협업 시스템 테스트
**파일**: `tests/e2e/test_collaboration_e2e.py`

#### TC-D1: P2PMessenger 봇 간 직접 통신
- P2PMessenger에 bot_a, bot_b 핸들러 등록
- bot_a → bot_b 메시지 전송
- **검증**: bot_b의 핸들러가 올바른 payload로 호출됨

#### TC-D2: P2PMessenger 브로드캐스트
- 3개 봇 등록, bot_a가 브로드캐스트
- **검증**: bot_b, bot_c 핸들러 호출됨, bot_a는 미호출

#### TC-D3: CollaborationTracker 빈도 분석
- (bot_a, bot_b) 협업 5회, (bot_a, bot_c) 협업 2회, (bot_b, bot_c) 협업 1회
- get_frequent_pairs(min_count=2) 호출
- **검증**: [(("bot_a", "bot_b"), 5), (("bot_a", "bot_c"), 2)] 반환

#### TC-D4: ShoutoutSystem 칭찬 기록 + MVP 선정
- bot_a → bot_b 칭찬 3회, bot_a → bot_c 칭찬 1회
- get_top_recipients(days=7) 호출
- **검증**: bot_b가 1위, weekly_mvp()가 bot_b 반환

#### TC-D5: collab_request 프로토콜 — 요청/수락/완료 사이클
- make_collab_request_v2() → is_collab_request() → parse_collab_request() 체인
- **검증**: 파싱된 결과에 task, from_org, target_org 정확히 포함

#### TC-D6: MessageBus 이벤트 연쇄 — COLLAB_REQUEST → TASK_CREATED
- MessageBus에 COLLAB_REQUEST 구독자 등록
- collab_dispatch() 호출 시 COLLAB_REQUEST 이벤트 발행 확인
- **검증**: 구독자 핸들러가 올바른 data로 호출됨

**검증 기준**: 6개 TC 전부 PASS.

---

### Phase 6: 카테고리 E — 자연어 통신 + 메타데이터 분리 아키텍처

#### 6.1 문제 정의
현재 봇 간 통신은 Telegram 채팅방에 `[COLLAB_REQUEST:...]`, `[PROPOSE:topic|content]` 등 태그 기반 프로토콜을 사용한다. 이는:
- 사람이 읽기에 부자연스러움
- 태그 파싱 실패 시 통신 장애
- 새 프로토콜 추가 시 태그 형식 충돌 위험

#### 6.2 아키텍처 설계: Envelope Pattern

```
┌─────────────────────────────────────────────┐
│ Telegram Message (사람이 보는 부분)           │
│                                             │
│ "개발팀에서 API 설계 초안을 준비했습니다.      │
│  REST 기반으로 3개 엔드포인트를 제안합니다."   │
│                                             │
├─────────────────────────────────────────────┤
│ Hidden Metadata (봇만 읽는 부분)              │
│ 방법: Telegram 메시지의 entities 활용 불가 →  │
│ Zero-Width Character (ZWC) 인코딩 사용       │
│                                             │
│ \u200B + base64(JSON metadata) + \u200B      │
│                                             │
│ JSON: {                                     │
│   "protocol": "collab_request",             │
│   "task_id": "T-pm-042",                   │
│   "from_org": "aiorg_engineering_bot",      │
│   "target_org": "aiorg_product_bot",        │
│   "round": 1                                │
│ }                                           │
└─────────────────────────────────────────────┘
```

#### 6.3 설계 옵션 비교

| 옵션 | 메커니즘 | 장점 | 단점 |
|------|----------|------|------|
| **A: ZWC 인코딩** | 메시지 끝에 Zero-Width Characters로 JSON 인코딩 | Telegram 표시에 안 보임, 단일 메시지 | 글자수 제한 소모, 일부 클라이언트에서 복사 시 깨짐 |
| **B: Reply-to + DB 룩업** | 메시지는 자연어만, metadata는 ContextDB에 저장. 봇은 message_id로 DB 조회 | 깔끔한 분리, 글자수 절약 | DB 의존성 증가, message_id 매핑 필요 |
| **C: 이중 메시지** | 자연어 메시지 + 즉시 삭제되는 메타데이터 메시지 | 완전 분리 | API 호출 2배, 삭제 타이밍 이슈 |

**선택: 옵션 B (Reply-to + DB 룩업)** — 이유:
- 기존 ContextDB에 이미 pm_tasks 테이블이 metadata JSON 컬럼을 보유
- message_id ↔ task_id 매핑은 update_pm_task_metadata()로 이미 저장 중
- 자연어 메시지만 Telegram에 표시, 봇은 task_id로 DB에서 라우팅 정보 조회
- ZWC는 Telegram의 메시지 길이 제한과 클라이언트 호환성 문제가 있음

#### 6.4 구현 설계

**새 모듈**: `core/message_envelope.py`

```python
@dataclass
class MessageEnvelope:
    """봇 메시지의 자연어/메타데이터 분리 래퍼."""
    display_text: str          # Telegram에 표시할 자연어 텍스트
    metadata: dict             # DB에 저장할 라우팅/프로토콜 정보
    task_id: str | None        # 연결된 태스크 ID
    protocol: str = "generic"  # collab_request, discussion, dispatch 등

class EnvelopeManager:
    """메시지 봉투 관리자 — 기존 태그 프로토콜을 envelope로 마이그레이션."""

    async def wrap(self, text: str, metadata: dict, task_id: str) -> MessageEnvelope:
        """자연어 텍스트 + 메타데이터를 봉투로 패키징."""

    async def send(self, chat_id: int, envelope: MessageEnvelope) -> int:
        """Telegram에 display_text만 전송, metadata는 DB에 task_id로 저장.
        반환: telegram message_id"""

    async def receive(self, message_id: int) -> MessageEnvelope | None:
        """수신된 메시지의 message_id로 DB에서 metadata 조회."""

    def extract_legacy_tags(self, text: str) -> tuple[str, dict]:
        """기존 [COLLAB_REQUEST:...] 등 태그를 파싱해서 (clean_text, metadata) 반환.
        하위 호환용 — 마이그레이션 기간 동안 태그와 envelope 병행."""
```

**마이그레이션 전략**:
1. EnvelopeManager를 TelegramRelay에 주입 (선택적)
2. 기존 태그 기반 메시지는 extract_legacy_tags()로 자동 변환
3. 새 메시지는 wrap() + send()로 envelope 형식 사용
4. 수신 시: 먼저 DB 룩업, 실패하면 legacy 태그 파싱 fallback

#### 6.5 카테고리 E 테스트
**파일**: `tests/e2e/test_message_envelope_e2e.py`

#### TC-E1: EnvelopeManager.wrap() + send()
- 자연어 텍스트와 메타데이터로 봉투 생성
- send() 호출 시 Telegram에는 display_text만, DB에는 metadata 저장
- **검증**: mock telegram_send에 전달된 텍스트에 메타데이터 태그 없음

#### TC-E2: EnvelopeManager.receive() — DB 룩업
- send()로 전송한 메시지의 message_id로 receive() 호출
- **검증**: 원본 metadata와 동일한 dict 반환

#### TC-E3: Legacy 태그 호환 — extract_legacy_tags()
- `"[COLLAB_REQUEST:task|from_org|target_org] 도와주세요"` 입력
- **검증**: clean_text == "도와주세요", metadata에 protocol/task/from_org/target_org 포함

#### TC-E4: 기존 collab_request 프로토콜과 envelope 병행
- 기존 make_collab_request_v2()로 생성한 메시지를 extract_legacy_tags()로 파싱
- 동일 내용을 envelope로 재생성
- **검증**: 두 방식의 metadata가 동일

#### TC-E5: Discussion 메시지 envelope 변환
- 기존 `[PROPOSE:topic|content]` 태그 메시지를 envelope로 변환
- **검증**: display_text에 태그 없음, metadata.protocol == "discussion"

**검증 기준**: 5개 TC 전부 PASS.

---

## 3. 파일 구조 요약

```
tests/
  e2e/
    __init__.py
    conftest.py                          # 공통 fixture
    test_character_evolution_e2e.py       # Phase 2: 카테고리 A (6 TC)
    test_pingpong_conversation_e2e.py     # Phase 3: 카테고리 B (5 TC)
    test_pm_modes_e2e.py                 # Phase 4: 카테고리 C (7 TC)
    test_collaboration_e2e.py            # Phase 5: 카테고리 D (6 TC)
    test_message_envelope_e2e.py         # Phase 6: 카테고리 E (5 TC)
core/
  message_envelope.py                    # 신규: 자연어/메타데이터 분리 모듈
```

총 **29개 테스트 케이스** (A:6 + B:5 + C:7 + D:6 + E:5)

---

## 4. 검증 기준 (성공 조건)

| 카테고리 | 성공 조건 | 실행 방법 |
|----------|-----------|-----------|
| A: 성격 진화 | 6/6 TC PASS | `pytest tests/e2e/test_character_evolution_e2e.py -v` |
| B: 핑퐁 대화 | 5/5 TC PASS | `pytest tests/e2e/test_pingpong_conversation_e2e.py -v` |
| C: PM 모드 | 7/7 TC PASS | `pytest tests/e2e/test_pm_modes_e2e.py -v` |
| D: 협업 시스템 | 6/6 TC PASS | `pytest tests/e2e/test_collaboration_e2e.py -v` |
| E: 메타데이터 분리 | 5/5 TC PASS | `pytest tests/e2e/test_message_envelope_e2e.py -v` |
| 전체 | 29/29 PASS, < 60초 | `pytest tests/e2e/ -v --tb=short` |
| 기존 테스트 회귀 | 기존 테스트 PASS 유지 | `pytest tests/ -v --ignore=tests/e2e/` |

---

## 5. 예상 리스크와 완화 방법

| 리스크 | 영향 | 확률 | 완화 방법 |
|--------|------|------|-----------|
| AgentPersonaMemory SQLite 경합 | TC-A 간 DB 충돌 | 낮음 | 각 TC에서 tmp_path로 격리된 DB 사용 |
| discussion_dispatch 내부 변경 | TC-B 깨짐 | 중간 | mock 범위를 최소화하고 public API만 테스트 |
| plan_request heuristic 변경 | TC-C6 기대값 불일치 | 중간 | expected_lane_contains를 OR 리스트로 유연하게 검증 (기존 integration test 패턴) |
| message_envelope.py 신규 모듈 | 기존 relay 코드 변경 필요 | 높음 | Phase 6은 독립 모듈로 구현, relay 변경 없이 테스트 가능하게 설계. 통합은 별도 PR |
| Telegram API mock 불완전 | send 호출 검증 누락 | 낮음 | AsyncMock(return_value=MagicMock(message_id=12345)) 패턴 사용 |

---

## 6. 구현 순서 및 의존성

```
Phase 1 (인프라)
    │
    ├── Phase 2 (A: 성격 진화) ─── 독립
    ├── Phase 4 (C: PM 모드) ──── 독립
    ├── Phase 5 (D: 협업) ─────── 독립
    │
    └── Phase 3 (B: 핑퐁 대화) ── Phase 2 fixture 일부 재사용
         │
         └── Phase 6 (E: 메타데이터 분리) ── message_envelope.py 먼저 구현 필요
```

Phase 2, 4, 5는 Phase 1 완료 후 병렬 구현 가능.
Phase 3은 Phase 2의 persona_memory fixture 재사용.
Phase 6은 신규 모듈 구현이 선행되어야 하므로 마지막.

---

## 7. ADR (Architecture Decision Record)

### Decision
봇 간 통신의 메타데이터를 Telegram 메시지에서 분리하여 ContextDB에 저장하는 Envelope Pattern을 채택한다.

### Drivers
- 사용자(사람) 경험: 채팅방에서 `[COLLAB_REQUEST:...]` 같은 태그가 보이면 부자연스러움
- 안정성: 태그 파싱 실패 시 봇 간 통신 장애
- 확장성: 새 프로토콜 추가 시 태그 형식 충돌

### Alternatives Considered
1. **ZWC 인코딩**: Telegram 메시지에 보이지 않는 문자로 인코딩 — 글자수 소모 + 클라이언트 호환성 문제로 제외
2. **이중 메시지**: 자연어 + 즉시 삭제 메타데이터 — API 호출 2배 + 삭제 타이밍 문제로 제외
3. **현행 유지 (태그)**: 변경 비용 없음 — UX 개선 불가, 장기적 기술 부채

### Why Chosen
Reply-to + DB 룩업 방식은 기존 ContextDB 인프라를 재사용하며, message_id ↔ task_id 매핑이 이미 구현되어 있어 최소 변경으로 구현 가능.

### Consequences
- 긍정: 깨끗한 자연어 메시지, 안정적 메타데이터 전달, 태그 파싱 버그 제거
- 부정: DB 의존성 증가 (오프라인 시 메타데이터 조회 불가), 마이그레이션 기간 동안 태그/envelope 병행 필요

### Follow-ups
- [ ] message_envelope.py 구현 PR
- [ ] TelegramRelay에 EnvelopeManager 주입 PR (별도)
- [ ] 기존 태그 프로토콜 deprecation 일정 결정
- [ ] DB 오프라인 fallback 전략 (legacy 태그 자동 복원)

---

## 8. 자율 모드 결정 로그

| 결정 사항 | 선택 | 이유 |
|-----------|------|------|
| 테스트 방식 | 인메모리 mock | CI 안정성, 실행 속도 |
| 메타데이터 분리 방식 | DB 룩업 (옵션 B) | 기존 인프라 재사용, ZWC 호환성 문제 |
| TC 수 | 29개 | 각 카테고리 5~7개로 핵심 경로 커버 |
| Phase 실행 순서 | C > A > B > D > E | PM 모드가 시스템 핵심, E는 신규 기능이므로 마지막 |
| E의 신규 모듈 범위 | message_envelope.py만 | relay 변경 없이 독립 테스트 가능하도록 |
