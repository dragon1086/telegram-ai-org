# 자율 루프 (Autonomous Loop) 운영 가이드

> 문서 버전: 2026-03-25
> 구현 상태: **완료** — 37개 E2E 테스트 전체 통과

---

## 개요

E2E 자율 루프는 전 조직 봇이 일일회고/주간회의 채팅에 참여해 보고·조치사항을
GoalTracker에 자동 등록하고, **idle → evaluate → replan → dispatch** 사이클을
자율적으로 실행하는 시스템이다.

```
채팅 수신 → MultibotMeetingHandler
    → 6개 봇 보고 수집
    → GoalTrackerClient.register_report()
        → auto_register_from_report() (파싱 + 등록)
        → run_meeting_cycle() (루프 실행)
            → idle → evaluate → replan → dispatch → idle
```

---

## 핵심 컴포넌트

### 1. 상태머신 (`goal_tracker/state_machine.py`)

| 상태 | 설명 | 진입 조건 |
|------|------|----------|
| **IDLE** | 대기 | 초기 상태 / dispatch 완료 / 달성 / 정체 |
| **EVALUATE** | 목표 달성률 분석 | iteration < max_iterations |
| **REPLAN** | 재계획 수립 | achieved=False + 정체 미감지 |
| **DISPATCH** | 부서별 태스크 배분 | task_ids > 0 |

전이 규칙:
```
IDLE → EVALUATE → REPLAN → DISPATCH → IDLE
                ↓              ↓
               IDLE           IDLE
           (달성/정체)     (태스크 없음)
```

### 2. GoalTrackerClient (`goal_tracker/goal_tracker_client.py`)

GoalTracker API 단일 인터페이스 — 목표 생성·업데이트·보고 등록을 래핑한다.

```python
client = GoalTrackerClient(
    goal_tracker=tracker,
    org_id="aiorg_pm_bot",
    chat_id=GROUP_CHAT_ID,
    send_func=send_func,
)

# 목표 생성
result = await client.create_goal(
    title="E2E 자율 루프 구현",
    description="idle→evaluate→replan→dispatch 전체 구현",
)

# 보고서 등록 + 자율 루프 실행
report_result = await client.register_report(
    report_text=retro_md,
    report_type="daily_retro",
)
print(report_result.loop_states)  # ["idle", "evaluate", "replan", "dispatch", "idle"]
```

### 3. MultibotMeetingHandler (`goal_tracker/multibot_meeting_handler.py`)

전 조직 봇(6개)을 순서대로 회의에 참여시키고 GoalTracker에 조치사항을 등록한다.

```python
handler = MultibotMeetingHandler(
    client=client,
    send_func=send_func,
    request_bot_report=my_bot_request_func,  # 봇별 응답 함수
    bot_request_interval=3.0,  # 봇 간 인터벌(초)
)

result = await handler.handle(
    message_text="일일회고 시작합니다",
    chat_id=GROUP_CHAT_ID,
)
print(result.registered_count)  # GoalTracker에 등록된 조치사항 수
```

**멀티봇 참여 순서**: 개발실 → 운영실 → 디자인실 → 기획실 → 성장실 → 리서치실

### 4. AutonomousLoopRunner (`goal_tracker/loop_runner.py`)

회의 1회 분량의 조치사항을 즉시 한 사이클 처리하는 경량 실행기.

```python
runner = AutonomousLoopRunner(
    goal_id="G-daily-2026-03-25",
    dispatch_func=my_dispatch,
)
result = await runner.run_cycle(registered_ids=["G-pm-001", "G-pm-002"])
print(result.states_visited)  # ["idle", "evaluate", "replan", "dispatch", "idle"]
```

### 5. 장기 백그라운드 루프 (`core/autonomous_loop.py`)

여러 목표를 주기적으로 관리하는 상위 루프 (PM 봇 시작 시 자동 실행).

```python
loop = AutonomousLoop(
    goal_tracker=tracker,
    idle_sleep_sec=300,  # 5분 간격
    send_func=send_func,
)
asyncio.create_task(loop.run())
```

---

## 트리거 조건

### 일일회고 (daily_retro)
- 감지 패턴: `일일회고`, `daily retro`, `데일리`, `#daily`, `오늘의 회고`
- 실행 시각: 매일 23:30 KST (`scripts/daily_retro.py` 크론)
- GoalTracker 등록: 마크다운 `조치사항:` 섹션 아이템 파싱

### 주간회의 (weekly_meeting)
- 감지 패턴: `주간회의`, `weekly meeting`, `주간 미팅`, `#weekly`
- 실행 시각: 매주 월요일 09:03 KST (`scripts/weekly_meeting_multibot.py` 크론)
- GoalTracker 등록: 부서별 보고에서 조치사항 추출

---

## GoalTracker 등록 규칙

1. **파싱**: `goal_tracker/report_parser.py` — `[ ]` 체크박스 항목 추출
2. **중복 방지**: 동일 제목 키워드(첫 10자 정규화) 기준으로 기존 active/achieved 목표 재생성 방지
3. **메타데이터**: `meeting_type`, `priority`, `assigned_dept`, `due_date` 자동 추출
4. **등록 후 루프**: `run_meeting_cycle()` 호출 → 즉시 한 사이클 실행

```
보고서 텍스트
    → parse_action_items()  ← goal_tracker/report_parser.py
    → MeetingActionRegistrar.register_from_event()
    → GoalTracker.start_goal()  (목표당 1개)
    → run_meeting_cycle()  (idle→evaluate→replan→dispatch)
```

---

## 멀티봇 참여 프로토콜

```
PM 봇 (사회자)
    ├─ 채팅: "일일회고 시작합니다"
    ├─ MultibotMeetingHandler.handle() 실행
    │   ├─ [3초 간격] 개발실에 보고 요청
    │   ├─ [3초 간격] 운영실에 보고 요청
    │   ├─ [3초 간격] 디자인실에 보고 요청
    │   ├─ [3초 간격] 기획실에 보고 요청
    │   ├─ [3초 간격] 성장실에 보고 요청
    │   └─ [3초 간격] 리서치실에 보고 요청
    ├─ 통합 보고서 생성 (_build_combined_report)
    ├─ GoalTrackerClient.register_report()
    │   ├─ auto_register_from_report() → 조치사항 파싱·등록
    │   └─ run_meeting_cycle() → 자율 루프 사이클 실행
    └─ 완료 알림 전송
```

**중복 방지**: `meeting_id = {type}_{date}` 기준으로 당일 재처리 방지.
`force=True`로 강제 재실행 가능.

---

## 설정 방법

### orchestration.yaml 설정

```yaml
autonomous_loop:
  idle_sleep_sec: 300      # 장기 루프 대기 간격 (초)
  max_dispatch: 3          # 한 사이클 최대 배분 목표 수

goal_tracker:
  enabled: true            # ENABLE_GOAL_TRACKER=1 환경변수와 연동
  max_iterations: 10
  max_stagnation: 3
  poll_interval_sec: 30
```

### 환경변수

```bash
ENABLE_GOAL_TRACKER=1          # GoalTracker 활성화 (기본 off)
CONTEXT_DB_PATH=~/.ai-org/context.db  # DB 경로
TELEGRAM_GROUP_CHAT_ID=-12345  # 그룹 채팅방 ID
```

---

## E2E 실행

```bash
# 일일회고 E2E 시나리오 (dry-run)
./.venv/bin/python run_e2e_loop.py --type daily_retro --dry-run

# 주간회의 E2E 시나리오 (실제 GoalTracker 연동)
ENABLE_GOAL_TRACKER=1 ./.venv/bin/python run_e2e_loop.py --type weekly_meeting

# 커스텀 보고서 파일 지정
./.venv/bin/python run_e2e_loop.py --type daily_retro --report docs/retros/2026-03-25.md

# E2E 테스트 전체 실행
./.venv/bin/pytest tests/e2e/test_autonomous_loop_e2e.py -v
```

---

## 트러블슈팅

### 조치사항이 등록되지 않는 경우

```
증상: action_items_found=0
원인: 보고서에 "조치사항:" 섹션 없음 / "[ ]" 체크박스 없음
해결: 보고서 마크다운에 아래 형식으로 조치사항 추가

## 조치사항:
- [ ] 버그 수정 담당: 개발실 긴급
- [ ] 문서 작성 담당: 기획실 마감: 2026-03-31
```

### 중복 등록 오류

```
증상: 동일 목표가 재등록됨
원인: force=True로 핸들러 재실행
해결: handler.reset_processed() 호출 없이 force=True 사용 자제
     또는 GoalTracker 중복 방지 로직 (제목 키워드 10자 기준) 확인
```

### 봇 응답 타임아웃

```
증상: BotReport.success=False, error="보고 타임아웃"
원인: 개별 봇 응답 지연 (collect_timeout / len(bots) 초 초과)
해결: MultibotMeetingHandler(collect_timeout=120.0) 값 증가
     또는 bot_request_interval 축소
```

### 루프가 DISPATCH에 도달하지 않는 경우

```
증상: states_visited = ["idle", "evaluate", "idle"]
원인1: evaluation.achieved=True (즉시 달성으로 평가)
원인2: max_stagnation 초과 (정체 감지)
원인3: max_iterations 초과
해결: GoalTrackerStateMachine.to_dict()로 컨텍스트 확인
     sm.ctx.iteration, sm.ctx.stagnation_count 값 점검
```

---

## 구현 파일 목록

| 파일 | 역할 | 상태 |
|------|------|------|
| `core/autonomous_loop.py` | 장기 백그라운드 루프 | ✅ 기존 |
| `core/goal_tracker.py` | GoalTracker 메인 클래스 | ✅ 기존 |
| `goal_tracker/state_machine.py` | 4단계 상태머신 | ✅ 기존 |
| `goal_tracker/loop_runner.py` | 단일 사이클 실행기 | ✅ 기존 |
| `goal_tracker/auto_register.py` | 보고→GoalTracker 자동 등록 | ✅ 기존 |
| `goal_tracker/goal_tracker_client.py` | API 클라이언트 래퍼 | ✅ **신규** |
| `goal_tracker/multibot_meeting_handler.py` | 멀티봇 회의 핸들러 | ✅ **신규** |
| `run_e2e_loop.py` | E2E 통합 진입점 | ✅ **신규** |
| `tests/e2e/test_autonomous_loop_e2e.py` | E2E 테스트 37개 | ✅ **신규** |
| `scripts/daily_retro.py` | 일일회고 크론 스크립트 | ✅ 기존 |
| `scripts/weekly_meeting_multibot.py` | 주간회의 멀티봇 스크립트 | ✅ 기존 |

---

*자동 생성: 2026-03-25 | E2E 자율 루프 구현 완료 (37 tests passed)*
