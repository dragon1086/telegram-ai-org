# 자가진화형 AI 조직 — 전체 자가개선 아키텍처 설계

작성일: 2026-03-21

---

## 0. 진단: 현재 상태와 구멍

### 우리가 이미 가진 것 (자산 목록)

| 레이어 | 존재하는 코드 | 상태 |
|--------|-------------|------|
| **데이터 수집** | `retro_memory.db`, `lesson_memory.db`, `collaboration.db`, `agent_persona_memory.db` | 쌓이고 있음 |
| **분석 모듈** | `lesson_memory.py`, `retro_memory.py`, `bot_business_retro.py`, `staleness_checker.py` | 작동하지만 고립됨 |
| **자동화 트리거** | `scheduler.py`, `weekly_standup.py`, `daily_metrics.py` | 실행되지만 개선 루프 없음 |
| **개선 도구** | `auto_improve_recent_conversations.py`, `skill-evolve` 스킬, `skill_loader.py` | 수동 또는 미연결 |
| **평가 도구** | `confidence_scorer.py`, `verification.py`, `worker_health.py` | 점수는 내지만 행동 없음 |
| **진화 엔진** | `bot_character_evolution.py`, `agent_persona_memory.py` | 수동 트리거 |
| **테스트** | 60개+ pytest, `test_auto_improvement_tools.py` | CI 있음 |

### 핵심 문제: 단방향 데이터 흐름

```
회고/주간리뷰/평가 → DB에 저장 → 끝 (아무것도 안 읽음)
```

데이터는 쌓이는데, 그 데이터가 **다음 행동을 바꾸지 않는다**.
이것이 모든 구멍의 근원이다.

### 구체적 구멍 목록

1. `retro_memory.db` → 개선 행동 연결 없음
2. `lesson_memory.db` → nl_classifier 업데이트 연결 없음
3. `performance_eval` → bot_character_evolution 연결 없음
4. `skill-evolve` → eval 기준 없음 (수동 판단)
5. `staleness_checker.py` → 탐지만 하고 수정 안 함
6. `auto_improve_recent_conversations.py` → 스케줄러에 연결 안 됨
7. `confidence_scorer.py` → 점수 내지만 라우팅 규칙 업데이트 안 됨
8. `pm_orchestrator.py` (95KB), `telegram_relay.py` (201KB) → 비대화 경고 없음
9. 스킬마다 eval.json 없음 → 개선 품질 측정 불가
10. weekly_review 결과 → 다음 주 우선순위 자동 반영 없음

---

## 1. 전체 아키텍처: 자가개선 버스

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES (이미 존재)                      │
│  retro_memory.db │ lesson_memory.db │ collaboration.db │ context.db  │
│  weekly_review data │ performance scores │ task completion logs      │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│              IMPROVEMENT BUS (신규: core/improvement_bus.py)         │
│                                                                      │
│  Signal Collector → Priority Queue → Improver Router                │
│                                                                      │
│  신호 종류:                                                           │
│  - RETRO_INSIGHT: 회고에서 나온 교훈                                  │
│  - LESSON_LEARNED: 에러 후 학습                                      │
│  - PERF_DROP: 봇 성능 하락                                           │
│  - SKILL_FAIL: 스킬 실패/저품질                                       │
│  - ROUTE_MISS: 라우팅 실패                                           │
│  - STALE_CODE: 오래된/복잡한 코드                                     │
│  - ARCH_SMELL: 구조적 문제                                           │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────────┐
          ▼                    ▼                         ▼
   [스킬 개선]         [라우팅 최적화]            [봇 진화]
   SkillImprover      RoutingImprover          PersonaImprover
          │                    │                         │
          ▼                    ▼                         ▼
   [코드 진화]         [구조 진화]              [CLAUDE.md 진화]
   CodeImprover       ArchImprover            DocImprover
          │                    │                         │
          └────────────────────┼─────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    EVAL LAYER (신규: evals/)                          │
│                                                                      │
│  각 Improver의 변경사항을 정량적으로 평가                               │
│  score_before → apply_change → score_after                          │
│  score_after > score_before → KEEP (git commit)                     │
│  score_after ≤ score_before → REVERT (git revert)                   │
└──────────────────────────────┬──────────────────────────────────────┘
                               │
                               ▼
              [Telegram 보고 → Rocky에게]
              개선 내용 + 점수 변화 + keep/revert 결정
```

---

## 2. Layer 1: 스킬 자동개선 루프

### 현재 상태
- `skill-evolve` 스킬 존재 (SKILL.md만, eval 없음)
- 수동 실행만 가능

### 목표 상태
```
매일 새벽 2시:
  for each skill in skills/:
    1. eval.json 기준으로 현재 점수 측정 (score_baseline)
    2. 개선 제안 생성 (SKILL.md 수정)
    3. score_after 측정
    4. score_after > score_baseline → git commit "skill-improve: [skill]"
    5. 아니면 revert
  새벽 6시 요약 → Telegram 보고
```

### 구현 필요 항목

**a) evals/skills/[skill-name]/eval.json 구조**
```json
{
  "skill": "pm-task-dispatch",
  "version": "1.0",
  "scenarios": [
    {
      "input": "코딩 버그 고쳐줘",
      "expected_bot": "engineering",
      "weight": 1.0
    },
    {
      "input": "UI 디자인 개선 필요",
      "expected_bot": "design",
      "weight": 1.0
    }
  ],
  "metrics": {
    "clarity_score": "스킬 지시문이 얼마나 명확한가 (1-10)",
    "coverage_score": "시나리오 커버리지",
    "gotcha_count": "gotchas.md 항목 수 (적을수록 좋음)"
  },
  "baseline": 7.2
}
```

**b) skill_loader.py 확장**
- 현재: 스킬 로딩만
- 추가: eval 실행, 점수 반환

**c) skill-evolve 스킬 업그레이드**
- 현재: 수동 제안
- 추가: eval 기반 자동 루프, keep/revert 결정

**d) 스케줄러 연결**
- `scheduler.py`에 `skill_improve_nightly` 작업 등록

---

## 3. Layer 2: PM 라우팅 자동 최적화

### 현재 상태
- `nl_classifier.py` (2.9KB) — 키워드 기반, 매우 단순
- `pm_router.py` (5KB) — 라우팅 로직
- `confidence_scorer.py` — 점수 내지만 피드백 없음
- `lesson_memory.db`에 라우팅 실패 쌓임

### 목표 상태
```
라우팅 실패 감지:
  context_db.py의 task completion 로그 →
  "이 태스크가 잘못된 봇에 갔다" 패턴 탐지 →
  nl_classifier.py 규칙 자동 제안 →
  routing_test_suite.json으로 accuracy 측정 →
  accuracy 개선 시 → 규칙 업데이트 commit
```

### 구현 필요 항목

**a) evals/routing/test_cases.json**
```json
{
  "test_cases": [
    {"input": "코드 버그", "correct_bot": "engineering", "id": "r001"},
    {"input": "주간 회의 준비", "correct_bot": "pm", "id": "r002"},
    {"input": "사용자 인터뷰 결과 분석", "correct_bot": "research", "id": "r003"}
  ],
  "baseline_accuracy": 0.82
}
```

**b) RoutingOptimizer (신규)**
- 입력: lesson_memory + retro insights + routing failure logs
- 출력: nl_classifier.py 업데이트 제안
- 평가: routing_test_suite accuracy 점수
- Karpathy 루프: 제안 → 측정 → keep/revert

**c) confidence_scorer.py 피드백 루프 연결**
- 낮은 신뢰도 라우팅 → 자동으로 routing failure log에 기록
- 주간 집계 → RoutingOptimizer 트리거

---

## 4. Layer 3: 봇 캐릭터/페르소나 자가진화

### 현재 상태
- `bot_character_evolution.py` (4.9KB) — 존재하지만 수동 트리거
- `agent_persona_memory.py` (13KB) — 기억 저장
- `shoutout_system.py` (8KB) — 칭찬 시스템
- `collaboration_tracker.py` (4.7KB) — 협업 추적
- `bot_business_retro.py` (3.2KB) — 봇별 회고

### 목표 상태
```
주간 회고 완료 시:
  for each bot:
    1. 주간 성과 데이터 수집
       - task_completion_rate
       - collaboration_score (collaboration_tracker)
       - shoutout_received (shoutout_system)
       - lesson_learned_count (lesson_memory)
    2. 현재 persona traits 조회 (agent_persona_memory)
    3. 개선 방향 제안:
       - 완료율 낮음 → 집중력 trait 강화
       - 협업 점수 낮음 → 소통 trait 강화
       - 칭찬 많이 받음 → 강점 trait 증폭
    4. persona 업데이트 + 기록
    5. bot YAML의 instructions 자동 업데이트 제안 (Rocky 승인 후 적용)
```

### 구현 필요 항목

**a) PersonaEvolverScheduled (신규)**
- `bot_business_retro.py`의 출력을 읽어
- `bot_character_evolution.py`를 자동 트리거
- 변화 전/후 행동 비교 → 개선 여부 판단

**b) bots/[bot].yaml에 metrics 섹션 추가**
```yaml
# bots/aiorg_engineering_bot.yaml 예시
name: engineering-bot
metrics:
  target_completion_rate: 0.90
  target_collab_score: 7.0
  evolution_frequency: weekly
```

**c) 주간리뷰 → 페르소나 진화 자동 연결**
- `weekly-review` 스킬 완료 시 → PersonaEvolver 자동 실행
- 현재: 주간리뷰 결과가 어디에도 연결 안 됨

---

## 5. Layer 4: 프로젝트 코드 자가진화

### 현재 상태
- `auto_improve_recent_conversations.py` — 존재하지만 스케줄러 미연결
- `staleness_checker.py` (7.2KB) — 탐지만, 수정 없음
- `lesson_memory.py` (12KB) — 교훈 저장하지만 코드 수정 없음
- `pm_orchestrator.py` (95KB), `telegram_relay.py` (201KB) — 비대화 위험

### 목표 상태
```
[신호 → 코드 개선 루프]

신호 1: lesson_memory에 같은 에러 3회 이상 → auto-fix 제안
신호 2: staleness_checker가 "90일 이상 변경 없음 + 에러 많음" → 리팩토링 제안
신호 3: pm_orchestrator.py > 100KB → 분리 필요 경고
신호 4: test coverage < 70% 모듈 → 테스트 추가 제안

루프:
  코드 변경 제안 생성 →
  pytest 실행 (pass rate = 평가 기준) →
  pass rate 유지/개선 → feature branch commit →
  Rocky 승인 → merge
```

### 구현 필요 항목

**a) CodeHealthMonitor (신규: core/code_health.py)**
```python
# 매일 실행
metrics = {
    "file_sizes": {f: size for f, size in scan_core()},
    "test_coverage": run_coverage(),
    "error_frequency": lesson_memory.get_frequent_errors(),
    "staleness": staleness_checker.scan()
}
# 임계값 초과 시 improvement_bus에 신호 발송
```

**b) auto_improve_recent_conversations.py → 스케줄러 연결**
- 현재: 수동 스크립트
- 변경: scheduler.py에 `code_improve_weekly` 작업 등록
- 조건: 새 lesson이 3개 이상 쌓였을 때만 실행

**c) 실험 기록 규칙 (Karpathy 패턴)**
- 모든 자동 코드 변경은 feature branch에서만
- commit message: `[auto-improve] {module}: {lesson_id}`
- git history = 실험 로그

---

## 6. Layer 5: 아키텍처/구조 자가진화

### 현재 상태
- 구조적 비대화 탐지 없음
- CLAUDE.md 수동 업데이트만
- .omc/plans/ 에 계획 있지만 실행 추적 없음

### 목표 상태
```
[구조 건강도 지표]
- core/ 파일 평균 크기 추세
- 모듈 간 의존성 복잡도
- 새 기능 추가 vs 기존 코드 재사용 비율
- 스킬 활용률 (어떤 스킬이 안 쓰이는가)

[자동 제안]
월 1회:
  - "pm_orchestrator.py가 100KB 초과. 분리 권장: [제안]"
  - "skill-X가 3개월째 호출 0회. 삭제 또는 통합 고려"
  - "A와 B 모듈이 70% 중복. 통합 제안"
  → Telegram으로 Rocky에게 보고 (행동은 Rocky가 결정)
```

### 구현 필요 항목

**a) ArchitectureAdvisor (신규: scripts/arch_advisor.py)**
- 코드 복잡도 메트릭 수집
- 스킬 사용 빈도 분석 (weekly-review data 활용)
- 월간 구조 건강 리포트 생성

**b) CLAUDE.md 자동 업데이트 규칙**
- 회고에서 나온 "운영 주의사항"만 자동으로 제안
- Rocky 승인 후 PR로 반영

---

## 7. 핵심 연결 고리: Improvement Bus 설계

```python
# core/improvement_bus.py (신규)

class ImprovementSignal:
    source: str        # "retro", "lesson", "perf", "code", "routing"
    priority: int      # 1-10
    target: str        # "skill:pm-task-dispatch", "routing", "bot:engineering", "code:nl_classifier"
    evidence: dict     # 신호의 근거 데이터
    suggested_action: str

class ImprovementBus:
    """
    신호 수집 → 우선순위 큐 → Improver 라우팅
    스케줄러와 연동: 매일 새벽 수집, 새벽 2시 실행
    """

    def collect_signals(self):
        # 모든 DB에서 신호 수집
        signals = []
        signals += self._from_retro_memory()      # retro_memory.db
        signals += self._from_lesson_memory()     # lesson_memory.db
        signals += self._from_performance()       # worker_health.py
        signals += self._from_routing_logs()      # context_db.py
        signals += self._from_code_health()       # staleness_checker
        return sorted(signals, key=lambda s: s.priority, reverse=True)

    def route(self, signal: ImprovementSignal):
        routers = {
            "skill": SkillImprover,
            "routing": RoutingImprover,
            "bot": PersonaImprover,
            "code": CodeImprover,
            "arch": ArchitectureAdvisor,
        }
        target_type = signal.target.split(":")[0]
        return routers[target_type](signal)
```

---

## 8. 스케줄 설계 (scheduler.py 추가 항목)

```
매일 01:00 KST: CodeHealthMonitor.scan() → 신호 생성
매일 02:00 KST: ImprovementBus.collect_and_route() → 자동 개선 실행
매일 06:00 KST: 개선 요약 → Telegram 보고

매주 금요일 17:00 KST: weekly-review 스킬 실행
매주 금요일 18:00 KST: 주간리뷰 결과 → PersonaEvolver 자동 실행
매주 금요일 19:00 KST: skill_improve_nightly (전체 스킬 대상)

매월 1일 09:00 KST: ArchitectureAdvisor 월간 리포트
```

---

## 9. 평가(Eval) 프레임워크

### 디렉토리 구조 (신규)

```
evals/
├── schema.json                    ← eval 정의 스키마
├── skills/
│   ├── pm-task-dispatch/eval.json
│   ├── weekly-review/eval.json
│   ├── engineering-review/eval.json
│   ├── bot-triage/eval.json
│   └── quality-gate/eval.json
├── routing/
│   ├── test_cases.json            ← 라우팅 테스트 케이스 100개
│   └── baseline.json             ← 현재 accuracy 기준선
└── bots/
    ├── engineering/kpi.json       ← 봇별 KPI 정의
    ├── design/kpi.json
    └── ...
```

### 평가 기준 원칙
- **스킬**: 시나리오 정확도 + 명확성 + gotcha 감소율
- **라우팅**: accuracy (정답 봇으로 간 비율)
- **봇**: task_completion_rate + collab_score + lesson_learned
- **코드**: test_pass_rate + 파일 크기 + 중복도

---

## 10. 구현 우선순위 로드맵

### Phase 1: 연결 (1주일) — 새 코드 최소화
```
1. improvement_bus.py 기본 구조 (신호 수집만)
2. auto_improve_recent_conversations.py → scheduler 연결
3. weekly-review 완료 후 → bot_character_evolution 자동 트리거
4. retro 결과 → lesson_memory 자동 기록 확인 (이미 있을 수 있음)
```

### Phase 2: Eval 레이어 (2주일)
```
5. evals/schema.json 정의
6. 핵심 스킬 5개에 eval.json 작성
7. routing/test_cases.json 100개 작성
8. eval_runner.py 구현
```

### Phase 3: Skill Auto-Improve (1주일)
```
9. skill-evolve 스킬 eval 기반으로 업그레이드
10. 야간 스킬 개선 루프 스케줄 등록
```

### Phase 4: Routing Optimizer (1주일)
```
11. RoutingOptimizer 구현
12. nl_classifier.py 자동 업데이트 제안 파이프라인
```

### Phase 5: Code Health + Architecture (2주일)
```
13. code_health.py 구현
14. arch_advisor.py 구현
15. 월간 구조 리포트 스케줄 등록
```

---

## 11. 중요 설계 원칙

### Rocky가 항상 최종 결정권
- **자동 실행**: 스킬 개선, eval 실행, 점수 측정, 제안 생성
- **Rocky 승인 필요**: bot YAML 변경, CLAUDE.md 변경, 코드 merge
- 자동화는 제안을 만들고, Rocky가 결정한다

### Karpathy 원칙 준수
- 모든 자동 변경은 git commit으로 기록
- 점수 개선 시만 keep, 아니면 revert
- git history = 실험 로그 = 학습 기록

### 연결 우선, 새 코드 나중
- 이미 있는 `auto_improve_recent_conversations.py`, `staleness_checker.py`, `confidence_scorer.py`를 먼저 연결
- 새 모듈은 연결 작업이 막힐 때만 작성

### 측정 없으면 개선 없음
- eval.json이 없는 스킬은 개선 루프 대상에서 제외
- eval 작성이 선행 조건

---

## 12. 우리만의 차별화 — "자기진화형 AI 조직"

이것이 완성되면:

```
[Karpathy 루프 적용 범위]

  everything-claude-code:  스킬만 (단일 개발자 워크플로)

  우리:
  ├── 스킬 자가개선     (Layer 1)
  ├── 라우팅 자가최적화  (Layer 2)  ← 조직 고유
  ├── 봇 페르소나 자가진화 (Layer 3) ← 조직 고유
  ├── 코드 자가개선     (Layer 4)
  └── 구조 자가진화     (Layer 5)  ← 조직 고유

  개선 루프가 조직 전체를 관통한다.
  봇들은 경험을 통해 성장하고,
  조직은 데이터를 통해 스스로 최적화된다.
```

이것은 단순한 에이전트 시스템이 아니라,
**성장하는 조직의 시뮬레이션**이다.
