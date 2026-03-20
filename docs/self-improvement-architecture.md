# Self-Improvement Architecture (자기 개선 아키텍처)

> 목표: 각 봇이 일할수록 복리처럼 능력이 향상되는 메커니즘

## 현황 분석

### 이미 있는 것
- `core/lesson_memory.py` — SQLite 실패 패턴 기록 + 키워드 기반 검색
- `core/bot_character_evolution.py` — 봇별 성공률/실패패턴/시너지 추적
- `skills/retro/` — 수동 회고 스킬 (Start/Stop/Continue + 5 Whys)
- `.ai-org/lesson_memory.db` — 교훈 DB

### 핵심 Gap
1. **실패만 기록** — 성공 패턴(무엇이 잘 됐는지)을 안 남김
2. **수동 트리거** — 회고가 사용자 개입 없이는 안 돌아감
3. **Pre-task briefing 없음** — 태스크 시작 전 관련 교훈 주입 안 함
4. **스킬 진화 없음** — 교훈 축적 → 새 스킬 생성/개선 피드백 루프 없음

---

## 설계: 3-Phase Self-Improvement Loop

```
┌─────────────────────────────────────────────────┐
│                   TASK LIFECYCLE                 │
│                                                 │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   │
│  │ Phase 1  │──>│ Phase 2  │──>│ Phase 3  │   │
│  │ BRIEFING │   │EXECUTION │   │  DEBRIEF │   │
│  │ (Pre)    │   │          │   │  (Post)  │   │
│  └──────────┘   └──────────┘   └──────────┘   │
│       ▲                             │           │
│       │                             ▼           │
│  ┌────────────────────────────────────────┐     │
│  │        KNOWLEDGE DB (SQLite)           │     │
│  │  lessons + successes + patterns        │     │
│  └────────────────────────────────────────┘     │
│       ▲                             │           │
│       │         (주간)              ▼           │
│  ┌──────────────────────────────────────┐       │
│  │     Phase 4: SKILL EVOLUTION         │       │
│  │  패턴 분석 → 스킬 제안/개선          │       │
│  └──────────────────────────────────────┘       │
└─────────────────────────────────────────────────┘
```

### Phase 1: Pre-Task Briefing (태스크 시작 전)

**트리거**: PM이 봇에게 태스크 할당 시 자동
**동작**:
1. `lesson_memory.get_relevant(task_description)` 호출
2. 관련 교훈 3개를 시스템 프롬프트에 주입
3. 봇 성격 진화 데이터(`bot_character_evolution`)도 참고

**구현 위치**: `core/telegram_relay.py` → `_execute_pm_task()`
```python
# 태스크 시작 전 관련 교훈 조회
lessons = await lesson_memory.aget_relevant(task_description, limit=3)
if lessons:
    briefing = "## 관련 과거 교훈\n"
    for l in lessons:
        briefing += f"- [{l.category}] {l.what_went_wrong} → {l.how_to_prevent}\n"
    system_prompt += briefing
```

### Phase 2: Execution (실행)

현재와 동일. 봇이 자율적으로 태스크 수행.

### Phase 3: Post-Task Debrief (태스크 완료 후 자동 회고)

**트리거**: PM이 태스크 완료 확인 시 자동
**동작**:
1. 태스크 결과 분석 (성공/실패/부분성공)
2. **성공이든 실패든** 교훈 기록
3. 패턴 분류 (timing, approach, tool_usage, communication)

**새로운 DB 스키마 확장**:
```sql
ALTER TABLE lessons ADD COLUMN outcome TEXT DEFAULT 'failure';
-- outcome: 'success', 'failure', 'partial'
ALTER TABLE lessons ADD COLUMN effectiveness_score REAL DEFAULT 0;
-- 0.0 ~ 1.0, 같은 유형 태스크 재실행 시 성공률 변화로 측정
ALTER TABLE lessons ADD COLUMN applied_count INTEGER DEFAULT 0;
-- 이 교훈이 briefing에 주입된 횟수
```

**자동 회고 프롬프트** (봇에게 주입):
```
이 태스크가 완료되었습니다. 30초 안에 다음을 정리하세요:
1. 무엇이 잘 됐는가? (success_pattern)
2. 무엇이 어려웠는가? (difficulty)
3. 다음에 같은 유형 태스크 시 어떻게 하면 더 좋겠는가? (improvement)
JSON으로 응답: {"success_pattern": "...", "difficulty": "...", "improvement": "..."}
```

### Phase 4: Skill Evolution (주간 스킬 진화)

**트리거**: 주간 cron (일요일 밤)
**동작**:
1. 최근 7일 교훈 분석
2. 반복 패턴 탐지 (같은 category 3회 이상)
3. 패턴 → 스킬 제안 생성
4. `/create-skill` 메타스킬로 스킬 초안 작성
5. Rocky에게 승인 요청

**예시 흐름**:
```
[교훈 DB] "API 호출 시 rate limit 에러 3회 발생"
    → [패턴 감지] "api_failure 카테고리 급증"
    → [스킬 제안] "api-resilience 스킬: retry + backoff 패턴 가이드"
    → [/create-skill api-resilience] 스킬 초안 생성
    → [Rocky 승인] → skills/api-resilience/SKILL.md 배포
```

---

## 구현 우선순위

### P0: 즉시 (이번 스프린트)
1. **`/create-skill` 메타스킬** — 공식 가이드 기반 스킬 제작 템플릿
2. **lesson_memory 확장** — success 패턴 기록 추가

### P1: 다음 스프린트
3. **Pre-task briefing** — telegram_relay.py에 교훈 주입
4. **Post-task debrief** — 자동 회고 + 교훈 기록

### P2: 그 다음
5. **Skill evolution cron** — 주간 패턴 분석 + 스킬 제안
6. **Effectiveness tracking** — 교훈 적용 후 성과 변화 추적

---

## 복리 효과 메커니즘

```
Week 1: 봇이 10개 태스크 수행 → 3개 교훈 축적
Week 2: 3개 교훈이 briefing에 주입 → 실패율 감소 → 5개 교훈 축적
Week 4: 반복 패턴 → 새 스킬 1개 생성 → 전체 봇 능력 향상
Week 8: 스킬 5개 + 교훈 40개 → 태스크 성공률 80%+ 달성
```

**핵심**: 교훈이 쌓일수록 briefing이 정확해지고, 스킬이 늘어날수록 봇의 기본 능력이 올라감.
실패에서만 배우는 게 아니라 성공에서도 배워서, 잘 하는 것을 더 잘하게 됨.
