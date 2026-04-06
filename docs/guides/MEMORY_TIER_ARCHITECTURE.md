# 3계층 메모리 아키텍처 구현 설계 명세서

**문서 버전**: v1.0
**작성 기준일**: 2026-03-26
**작성 조직**: 개발실 (PM: aiorg_engineering_bot)
**태스크**: T-aiorg_pm_bot-714

---

## 현황 분석: 기존 메모리 레이어 지형도

현재 시스템에는 6개의 독립적 메모리 구현체가 파편화되어 존재한다:

| 구현체 | 위치 | 역할 | 현재 계층 |
|--------|------|------|-----------|
| `MemoryManager` | `core/memory_manager.py` | CORE/SUMMARY/LOG 3계층, `~/.ai-org/memory/{scope}.md` | 중기+장기 |
| `SharedMemory` | `core/shared_memory.py` | 봇 간 KV + context_db 2-tier 캐시 (TTL=300s) | 단기 |
| `ProjectMemory` | `core/project_memory.py` | 태스크 이력 + 워커 통계, JSON | 중기 |
| `LessonMemory` | `core/lesson_memory.py` | 실패/성공 교훈, SQLite | 중기→장기 |
| `ContextDB` | `core/context_db.py` | SQLite 공유 컨텍스트 | 중기 |
| `MEMORY.md` (Claude project) | `~/.claude/.../memory/MEMORY.md` | PM-사용자 세션 브릿지, system-reminder | 중기+장기 |

**핵심 문제**: 6개 구현체 간 통합된 승격/강등 규칙 없음. 이번 설계는 파편화 위에 통합 거버넌스 계층을 추가하는 방식으로 접근.

---

## Phase 1: 현황 분석 산출물

### 1.1 MEMORY.md 섹션별 계층 분류표

| 섹션 | 항목 | 계층 분류 | TTL | 근거 |
|------|------|-----------|-----|------|
| Memory Index | 참조 파일 목록 | **장기(영구)** | ∞ | 시스템 구조 자체, 불변 |
| Pending Tasks - pending/in_progress | 대기·진행 태스크 | **중기(활성)** | 완료까지 유지 | 세션 재시작 후에도 재개 필수 |
| Pending Tasks - resolved (최근 7일) | 최근 완료 항목 | **중기→단기 전환** | resolved 후 7일 | 참조 가능성 잔존 |
| Pending Tasks - archived | 보관 항목 | **중기→장기 전환** | 30일 후 삭제 | 이력 보존, 참조 빈도 낮음 |
| 공통 운영 원칙 - 현재 시간 기준 | 규칙 | **장기(영구)** | ∞ | ADR급, 정책 변경 전까지 불변 |
| 공통 운영 원칙 - Gemini Flash 버전 | 버전 정보 | **중기(갱신형)** | 30~90일 | 모델 버전 변경 시 갱신 |
| 오픈소스화 - 최우선 목표 | 목표 선언 | **중기** | 목표 완료 시 장기 이관 | 진행 중 상태 |
| 오픈소스화 - 완료 작업 에피소드 | 에피소드 이력 | **중기** | 60일 후 장기 압축 | 커밋 해시 포함, 참조 빈도 낮아지는 중 |
| 오픈소스화 - 3파일 동기화 규칙 | 운영 규칙 | **장기(영구)** | ∞ | ADR, 명시적 선언으로만 변경 |
| 오픈소스화 - Gemini CLI 환경 설정 | 환경 정보 | **중기(설치 의존)** | 환경 변경 시 갱신 | 특정 머신 의존 |
| 보고 형식 - 앱스토어 링크 | 링크 | **중기→장기** | 앱 폐기 전까지 | 외부 서비스, 변경 빈도 낮음 |
| 보고 형식 - 투입 페르소나 규칙 | 운영 규칙 | **장기(영구)** | ∞ | ADR급, 조직 보고 형식 결정 |

### 1.2 라이프사이클 ↔ 3계층 매핑 다이어그램

```
[pending tasks 라이프사이클]          [3계층 메모리 모델]

pending ─────────────────────────>  MID-TERM (중기)
in_progress ─────────────────────>  MID-TERM (활성, 만료 없음)
resolved (0~7일) ─────────────────> MID-TERM (감소 중)
archived (7~30일) ────────────────> MID-TERM (importance<8: 삭제 대기)
                                    MID-TERM → LONG-TERM (importance≥8: 장기 승격)
삭제 (30일 후) ───────────────────> 소멸 (또는 project_pending_tasks.md 이력)

[현재 MemoryManager CORE/SUMMARY/LOG]
  LOG  ─────────────────────────>   SHORT-TERM → MID-TERM [SUMMARY]
  SUMMARY ──────────────────────>   MID-TERM
  CORE ─────────────────────────>   LONG-TERM

[SharedMemory 캐시 TTL=300s]
  캐시 항목 ────────────────────>   SHORT-TERM (5분 후 소멸)
```

### 1.3 메모리 I/O 발생 지점 목록

**쓰기(Write) 발생 지점**

| 발생 지점 | 파일 | 기록 대상 | 현재 계층 |
|-----------|------|-----------|-----------|
| 태스크 완료 | `core/project_memory.py:record_task()` | TaskRecord | 중기 |
| 세션 writeback | `core/session_manager.py:WRITEBACK_PROMPT` | 중요 결정 3-10개 | 중기 |
| 교훈 발생 | `core/lesson_memory.py:record()` | Lesson | 중기→장기 |
| MEMORY_UPDATE 이벤트 | `core/shared_memory.py:set()` | KV 쌍 | 단기 |
| 크론 트리거 (09:05 KST) | `scripts/daily_goal_pipeline.py` | 완료 보고 | 중기 |
| 사용자 명시 지시 | `core/memory_manager.py:maybe_promote_to_core()` | 핵심 사실 | 장기 |
| LOG 30개 초과 | `core/memory_manager.py:_compress_doc()` | SUMMARY 승격 | 중기→장기 |
| 세션 시작 훅 | `scripts/hooks/session-start.sh` | stdout만 (읽기 전용) | - |

**읽기(Read) 발생 지점**

| 발생 지점 | 파일 | 읽기 대상 | 목적 |
|-----------|------|-----------|------|
| 세션 시작 | system-reminder 주입 | MEMORY.md 전체 | 컨텍스트 복구 |
| 태스크 착수 전 | `core/memory_manager.py:build_context()` | CORE+SUMMARY+LOG | 프롬프트 주입 |
| PM 태스크 계획 | `core/project_memory.py:get_planning_context()` | 유사 과거 태스크 | RAG 검색 |
| 봇 착수 전 briefing | `core/lesson_memory.py:get_briefing()` | 관련 교훈 | 사전 경고 |
| iter 시작 | `skills/pm-progress-tracker/skill.md` Step 3 | pm_progress_guide.md | 잔여 태스크 파악 |

---

## Phase 2: 3계층 섹션 스키마 명세서

### 2.1 Short-Term Memory (STM) 스키마

```
계층명: SHORT_TERM
저장소: 컨텍스트 윈도우 + SharedMemory (cache_ttl=300s)
TTL: 세션 유지 시간 (최대 180분, orchestration.yaml:session_policies.stale_after_minutes=180)
```

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| `session_id` | string | 세션 식별자 | `"aiorg_pm_bot_20260326_0900"` |
| `bot_id` | string | 봇 식별자 | `"aiorg_pm_bot"` |
| `content` | string | 기록 내용 (최대 200자) | `"ST-08 Phase 1b 착수 결정"` |
| `importance_score` | int(0-10) | 중요도 점수 | `7` |
| `memory_type` | enum | 유형 | `episodic \| semantic \| procedural` |
| `created_at` | ISO8601 | 생성 시각 | `"2026-03-26T09:15:00"` |
| `expires_at` | ISO8601 | 만료 시각 | `"2026-03-26T12:15:00"` |
| `source_event` | enum | 발생 원인 | `user_utterance \| task_event \| tool_call \| llm_output` |
| `promotion_candidate` | bool | 중기 승격 후보 여부 | `true` |

**자동 강등 조건**:
- `expires_at` 도달 + importance <= 4 → 삭제
- `expires_at` 도달 + importance >= 5 → 중기 승격 후보 큐 추가
- 세션 종료 이벤트 → importance >= 5 전체 중기 승격 평가

### 2.2 Mid-Term Memory (MTM) 스키마

```
계층명: MID_TERM
저장소: MEMORY.md (Pending Tasks, 진행 목표)
        + core/memory_manager.py [SUMMARY/LOG]
        + core/project_memory.py (TaskRecord JSON)
TTL: 생성 후 7~30일, 라이프사이클 상태에 따라 조정
```

**Pending Tasks 확장 스키마 (기존 5컬럼 → 8컬럼)**

| 필드명 | 타입 | 설명 | 기존 스키마 여부 |
|--------|------|------|-----------------|
| `id` | string | 태스크 ID (ST-XX) | 기존 |
| `title` | string | 태스크 제목 | 기존 |
| `created_at` | date | 생성일 | 기존 |
| `status` | enum | `pending \| in_progress \| resolved \| archived` | 기존 |
| `resolved_at` | date\|null | 완료일 | 기존 |
| `importance` | int(0-10) | 중요도 점수 | **신규** |
| `tier` | enum | `mid_term \| long_term` | **신규** |
| `delete_at` | date\|null | 삭제 예정일 (archived+30일) | **신규** |

**TTL 규칙**:
- status=`pending/in_progress`: 만료 없음 (완료까지 유지)
- status=`resolved`: 7일 후 → `archived` 전환
- status=`archived`: 30일 후 → 삭제 (importance >= 8이면 장기 승격)
- 목표 `DONE`: 60일 후 → 장기 이력으로 압축

### 2.3 Long-Term Memory (LTM) 스키마

```
계층명: LONG_TERM
저장소: MEMORY.md (## 전체 조직 공통 운영 원칙, ## 보고 형식 운영 원칙)
        + core/memory_manager.py [CORE] (importance 9-10)
        + core/lesson_memory.db (LessonMemory)
TTL: ∞ (명시적 삭제 전까지)
```

| 필드명 | 타입 | 설명 | 분류 기준 |
|--------|------|------|-----------|
| `id` | string | LTM-XXX | - |
| `category` | enum | `adr \| org_rule \| env_config \| project_history \| lesson` | - |
| `title` | string | 항목 제목 | - |
| `content` | string | 전체 내용 | - |
| `importance_score` | int(9-10) | 장기 계층 기준 최소 9 | - |
| `source_tier` | enum | `mid_term \| explicit_directive` | 승격 경로 |
| `promoted_at` | ISO8601 | 장기 승격 시각 | - |
| `promoted_by` | enum | `auto \| user_directive \| pm_decision` | - |
| `immutable` | bool | 수동 삭제만 허용 | true면 자동 삭제 불가 |

**category별 immutable 기준**:

| category | 예시 | immutable |
|----------|------|-----------|
| `adr` | "3파일 동기화 원칙", "투입 페르소나 규칙" | **true** |
| `org_rule` | "현재 시간 기준 작업 원칙" | **true** |
| `env_config` | "gemini-2.5-flash 현행 표준" | false (버전 변경 가능) |
| `project_history` | "GOAL-001 오픈소스화 완료" | false |
| `lesson` | LessonMemory (effectiveness >= 0.7) | false |

### 2.4 계층 간 승격/강등 규칙 정의서

```
[승격 규칙]

STM → MTM:
  A: importance_score >= 5 AND 세션 종료 이벤트
  B: source_event == "task_event" AND status IN (pending, in_progress)
  C: 사용자 발화에 승격 키워드 포함 ("꼭 기억", "항상 기억", "세션 넘어서")
  D: 태스크 ID 패턴 감지 (ST-XX, ETC-XX, GOAL-XXX)

MTM → LTM:
  A: importance_score >= 8 AND MTM 체류 >= 30일
  B: 사용자 발화에 장기 키워드 ("항상", "규칙으로", "ADR", "원칙으로")
  C: status=archived + importance >= 8 (자동)
  D: 완료 목표 에피소드 (DONE + 전략적 가치 있음)

[강등/삭제 규칙]

MTM → 삭제:
  A: archived + 체류 >= 30일 + importance < 8
  B: env_config 항목 + 환경 변경 감지

LTM → MTM 강등 (예외적):
  A: category=env_config + 새 버전으로 대체되는 경우

[동결(Freeze) 규칙]
LTM + immutable=true:
  - 자동 강등/삭제 불가
  - 수정: 사용자 명시 지시 + PM 확인 2단계 승인 필요
  - 삭제: Rocky 직접 조작만 허용
```

---

## Phase 3: 중요도 자동 판단 기준 명세서

### 3.1 4축 스코어링 로직

총점 = KW + UP + TE + EI (합산, 상한 10 클리핑)

**축 1: 키워드 트리거 (KW, 최대 4점)**

```
HIGH 키워드 (각 +2점, 최대 4점):
  한국어: 결정, 변경, 항상, 절대, 중요, 승인, 지시, 필수, 꼭, 원칙, 규칙, 아키텍처
  영어: decision, never, always, critical, mandatory, approved, architecture, ADR

MEDIUM 키워드 (각 +1점, 최대 2점):
  한국어: 완료, 구현, 배포, 수정, 버그, 보안, 태스크, 목표, 스프린트
  영어: completed, deployed, fixed, security, task, goal, sprint
```

**축 2: 발화 패턴 (UP, 최대 3점)**

```
+3점: "기억해", "꼭 기억", "영속", "다음 세션에서도"
+2점: 태스크 ID 패턴 (ST-[0-9]+, ETC-[0-9]+, GOAL-[0-9]+)
+2점: 완료 보고 패턴 ("완료 보고", "DONE", "resolved", "✅")
+1점: 날짜 명시 패턴 (YYYY-MM-DD 형식 포함)
+1점: 파일 경로/커밋 해시 포함
```

**축 3: 태스크 이벤트 (TE, 최대 3점)**

```
+3점: 신규 태스크 생성 (status=pending 신규 삽입)
+3점: in_progress → resolved 전환
+2점: 태스크 블로커 발생 (status=blocked)
+2점: 크론 트리거 발동 (daily_goal_pipeline, meeting_end_hooks)
+1점: COLLAB 태그 감지
```

**축 4: 명시적 지시 (EI, 최대 3점 또는 즉시 LTM 승격)**

```
즉시 LTM 승격 (EI=10 오버라이드):
  "항상 기억해", "절대 잊지 마", "규칙으로 정해", "ADR로 등록", "원칙으로"

+3점: "기억해", "메모해", "적어둬", "다음에도 이렇게"
+2점: 사용자가 직접 MEMORY.md 업데이트 요청
+1점: PM이 pm_progress_guide.md 목표 등록 행위
```

**총점 해석**:

| 총점 | 판정 | 액션 |
|------|------|------|
| 0~2 | 무시 | STM 자연 소멸 |
| 3~4 | 낮음 | STM 유지 (세션 종료 시 소멸) |
| 5~7 | 중간 | MTM 승격 후보 큐 추가 |
| 8~9 | 높음 | MTM 즉시 등록 |
| 10 | 장기 필수 | LTM 즉시 등록 |

### 3.2 단기→중기 승격 조건문

```
PROMOTE_STM_TO_MTM if ANY of:
  P1: event_type == "task_created" AND task_id MATCHES r"(ST|ETC|GOAL)-\d+"
  P2: event_type == "task_status_changed" AND new_status IN ("in_progress","resolved","blocked")
  P3: final_score >= 5 AND session_end_triggered
  P4: final_score >= 8  # 세션 종료 무관, 즉시
  P5: explicit_directive_detected (EI축 +3 이상)
  P6: event_source IN ("daily_goal_pipeline","meeting_end_hook","collab_trigger")
  P7: contains_file_path OR contains_commit_hash
  P8: contains_date_pattern AND references_future_date
```

### 3.3 중기→장기 승격 조건문

```
PROMOTE_MTM_TO_LTM if ANY of:
  L1: mtm_age_days >= 30 AND importance_score >= 8
  L2: mtm_age_days >= 7 AND importance_score == 10
  L3: explicit_lterm_directive ("규칙으로", "원칙으로", "ADR", "항상")
  L4: user_id == "rocky" AND directive_type == "explicit"
  L5: status == "archived" AND importance_score >= 8
  L6: goal_status == "DONE" AND strategic_value == true
  L7: lesson_effectiveness_score >= 0.7 AND applied_count >= 3
  L8: category IN ("adr","org_rule") AND confirmed_by_pm
  L9: category == "env_config" AND in_production_for_days >= 14
```

### 3.4 중복 방지 및 갱신 로직

```
[중복 판단 알고리즘]
1. exact_match: content 해시값 동일 → timestamp만 갱신
2. semantic_match: 키워드 overlap >= 0.7 AND 같은 category → UPDATE 기존 항목
3. tag_match: tags 교집합 >= 2개 AND 같은 memory_type → PM에게 병합 여부 확인
4. no_match → INSERT 신규 항목

[갱신 vs 신규삽입 판단 규칙]
UPDATE 선택 조건:
  - 동일 태스크 ID의 status 변경 (항상 UPDATE)
  - 동일 category=env_config의 버전 변경 (항상 UPDATE, 구 버전 deprecation 기록)
  - 동일 goal_id의 completion_pct 변경

INSERT 선택 조건:
  - 새로운 태스크 ID
  - 다른 category + 내용 유사도 < 0.7
  - 에피소드 이력 (새 관점이면 INSERT)

[중복 임계값]
  - 태스크 ID 기반: window=3600초 (ProjectMemory._is_duplicate 기준 유지)
  - 내용 기반: 키워드 overlap 70%
```

### 3.5 자동 판단 플로우차트

```
[새 정보/이벤트 발생]
         |
         v
[소스 분류]
  user_utterance ─┐
  task_event ─────┤──> [4축 스코어 계산: KW + UP + TE + EI → total_score]
  cron_trigger ───┘
         |
         v
[total_score 평가]
  0~2 ──> [무시 / 소멸]
  3~4 ──> [STM 유지, 세션 종료 시 소멸]
  5~7 ──> [MTM 승격 후보 큐]
               |
          [세션 종료?]
           YES -> [MTM 즉시 등록]
           NO  -> [큐 대기]
  8~9 ──> [MTM 즉시 등록]
  10  ──> [LTM 즉시 등록]
         |
         v
[MTM 등록 시 중복 검사]
  exact_match? → timestamp 갱신
  semantic_match(≥0.7)? → UPDATE 기존
  no_match → INSERT 신규
         |
         v
[MTM 체류 기간 평가] (크론: 매일 자정 KST)
  archived + 30일 + importance < 8 → [삭제]
  archived + importance >= 8 ────────> [LTM 승격 평가 L1~L9]
         |
         v
[LTM 등록] → immutable 결정 → category 분류 → [영구 보존]
```

---

## Phase 4: 구현 태스크 분해표

### 4.1 전체 구현 태스크

| ID | 제목 | 난이도 | 예상 시간 | 의존 태스크 | 담당 레이어 |
|----|------|--------|-----------|-------------|-------------|
| M3L-01 | MEMORY.md 스키마 확장 (3컬럼 추가) | **Low** | 1h | - | MTM |
| M3L-02 | MEMORY.md 섹션 재구조화 (3계층 구역 분리) | **Low** | 2h | M3L-01 | MTM+LTM |
| M3L-15 | `orchestration.yaml` memory_policies 섹션 추가 | **Low** | 1h | M3L-01 | 설정 |
| M3L-03 | `memory_manager.py` 4축 스코어링 함수 구현 | **Medium** | 3h | - | STM→MTM |
| M3L-04 | STM 캡처 훅: 세션 종료 감지 + 승격 후보 큐 | **Medium** | 4h | M3L-03 | STM |
| M3L-05 | MTM 라이프사이클 크론 구현 (memory_gc.py) | **Medium** | 3h | M3L-01 | MTM |
| M3L-07 | 중복 방지 로직 (exact/semantic/tag 3단계) | **Medium** | 4h | M3L-03 | 전 계층 |
| M3L-11 | memory-gc 스킬 신규 생성 | **Medium** | 4h | M3L-05, M3L-06 | MTM |
| M3L-12 | 에피소드 vs 시맨틱 분류 로직 | **Medium** | 3h | M3L-03 | 전 계층 |
| M3L-13 | BM25 검색을 3계층 통합 검색으로 확장 | **Medium** | 4h | M3L-10 | 전 계층 |
| M3L-14 | E2E 테스트: 승격/강등 시나리오 pytest | **Medium** | 4h | M3L-10 | 테스트 |
| M3L-06 | MTM→LTM 승격 엔진 (L1~L9 조건 평가) | **High** | 5h | M3L-03, M3L-05 | MTM→LTM |
| M3L-08 | LTM immutable 보호 레이어 (Rocky 승인 게이트) | **High** | 4h | M3L-06 | LTM |
| M3L-09 | 세션 경계 브릿지 개선 (STM→MTM 자동 스냅샷) | **High** | 6h | M3L-04, M3L-05 | STM→MTM |
| M3L-10 | `memory_tier_manager.py` 통합 관리 클래스 | **High** | 8h | M3L-03~M3L-08 | 전 계층 |

### 4.2 기존 Pending Tasks와 충돌/의존 관계 분석

| 기존 태스크 | 상태 | M3L 관계 | 처리 방안 |
|-------------|------|----------|-----------|
| ST-08 (리팩토링 1b) | in_progress | **병렬 가능** (단, M3L-04는 1b 완료 후 착수 권장) | bot_message_handler.py 분리 후 훅 주입이 더 깔끔 |
| ST-08c (Phase 1c) | pending | **M3L-04 선행 권장** | pm_message_handler.py 분리 후 메모리 훅 주입 |
| ST-11 (GitHub Release) | in_progress | **완전 독립** | 병렬 진행 가능 |
| ETC-02 (E2E timeout) | pending | **M3L-14에 포함 가능** | memory E2E 테스트 구현 시 함께 처리 |
| ETC-03 (Telethon min_id) | pending | **완전 독립** | 메모리 시스템과 무관 |
| ETC-04 (E2E 테스트 완성) | pending | **M3L-14 선행 후 통합** | M3L-14가 추가하는 memory E2E를 ETC-04 CI에 포함 |

**주요 충돌 없음** — 메모리 아키텍처는 독립 레이어

### 4.3 3단계 점진적 롤아웃 계획

#### 롤아웃 Phase 1: MEMORY.md 구조 확장 (1~2일, 저위험)

**포함 태스크**: M3L-01, M3L-02, M3L-15
**예상 소요**: 4h

**구체 작업**:
1. MEMORY.md Pending Tasks 테이블에 `importance` / `tier` / `delete_at` 컬럼 추가
2. `## [LONG-TERM] 영구 운영 원칙` 섹션으로 기존 운영 원칙 이관
3. `## [SHORT-TERM] 현재 세션 후보` 섹션 추가 (수동 관리용)
4. `orchestration.yaml`에 `memory_policies` 섹션 추가 (TTL 기본값 명시)

**Definition of Done**:
- [ ] MEMORY.md에 3계층 구역이 명확히 구분되어 있음
- [ ] Pending Tasks 모든 행에 `importance` 필드 채워짐
- [ ] `memory_policies` YAML 초안이 orchestration.yaml에 포함됨
- [ ] 기존 라이프사이클 규칙(7일/30일)이 새 스키마로 표현됨
- [ ] 파일 변경 후 `.venv/bin/python tools/orchestration_cli.py validate-config` 통과

#### 롤아웃 Phase 2: 저장 로직 훅 구현 (3~5일, 중위험)

**포함 태스크**: M3L-03, M3L-04, M3L-05, M3L-07, M3L-11, M3L-12
**예상 소요**: 21h

**구체 작업**:
1. `core/memory_manager.py` `_keyword_score()` → 4축 스코어링으로 교체
2. `core/session_manager.py` `WRITEBACK_PROMPT` → `memory_writeback()` 자동 호출
3. `scripts/memory_gc.py` MTM 라이프사이클 크론 스크립트 신규 구현
4. `skills/memory-gc/skill.md` 스킬 생성 (PM 수동 트리거 가능)
5. `MemoryManager.add_log()`에 에피소드/시맨틱 분류 통합

**Definition of Done**:
- [ ] 세션 종료 시 importance >= 5인 STM 항목이 MEMORY.md MTM 섹션에 자동 기록
- [ ] memory_gc 크론이 매일 자정 KST 실행, expired 항목 처리
- [ ] `pytest tests/unit/test_memory_gc.py` 통과 (최소 10개 케이스)
- [ ] 중복 판단 로직이 기존 `ProjectMemory._is_duplicate()` 기준과 일관됨

#### 롤아웃 Phase 3: 자동 판단 엔진 통합 (5~7일, 고위험)

**포함 태스크**: M3L-06, M3L-08, M3L-09, M3L-10, M3L-13, M3L-14
**예상 소요**: 31h

**구체 작업**:
1. `core/memory_tier_manager.py` 신규 클래스 구현
2. `core/context_db.py`에 `memory_items` 테이블 추가
3. BM25 검색 → `search_across_tiers()` 확장
4. `tests/e2e/test_memory_tier_e2e.py` 구현

**`memory_tier_manager.py` 핵심 인터페이스**:
```python
class MemoryTierManager:
    async def capture(content, source_event, bot_id) -> MemoryItem
    async def promote(item_id, target_tier, reason) -> bool
    async def demote(item_id, target_tier, reason) -> bool
    async def gc_run() -> GCReport        # 만료 항목 정리
    async def search(query, tiers=None, top_k=10) -> list[MemoryItem]
    async def get_context(task, bot_id) -> str  # 프롬프트 주입용
```

**Definition of Done**:
- [ ] `tests/e2e/test_memory_tier_e2e.py` 25개 이상 케이스 통과
- [ ] STM→MTM→LTM 승격 시나리오 자동 검증
- [ ] LTM immutable 항목 변경 시도 시 Rocky 승인 게이트 동작 확인
- [ ] 기존 MemoryManager/SharedMemory/ProjectMemory/LessonMemory 하위 호환 유지
- [ ] CI `.github/workflows/test.yml`에 memory tier 테스트 포함

### 4.4 전체 롤아웃 타임라인

```
2026-03-26  2026-03-27  2026-03-28  2026-03-29  2026-03-30  2026-03-31
     |            |            |            |            |            |
[롤아웃 P1]──────┤  (4h, Low)
  M3L-01,02,15   │
                 │[롤아웃 P2]─────────────────┤  (21h, Medium)
                 │  M3L-03,04,05,07,11,12    │
                 │                           │[롤아웃 P3]──────────────>
                 │                           │  M3L-06,08,09,10,13,14
[ST-08 1b]────────────────────┤             │  (31h, High)
[ST-08c]                      └────────────M3L-04 착수
[ETC-04]                                   └── M3L-14와 통합
```

---

## 구현 핵심 파일 참조

| 파일 | 수정 Phase | 역할 |
|------|-----------|------|
| `~/.claude/.../memory/MEMORY.md` | 롤아웃 P1 | 3계층 구역 분리 직접 대상 |
| `core/memory_manager.py` | 롤아웃 P2 | `_keyword_score()` → 4축 스코어링 교체 |
| `core/session_manager.py` | 롤아웃 P2 | `WRITEBACK_PROMPT`(L30-36) → 자동 writeback |
| `core/project_memory.py` | 롤아웃 P3 | 중복 방지, TTL 관리 패턴 참조 구현체 |
| `orchestration.yaml` | 롤아웃 P1 | `memory_policies` 섹션 신규 추가 위치 |
| `core/memory_tier_manager.py` | 롤아웃 P3 | 통합 관리 클래스 신규 생성 |

---

## 2026년 메모리 관리 트렌드 반영 요약

| 트렌드 | 적용 방식 |
|--------|-----------|
| **Mem0 스타일 계층형 메모리** | STM/MTM/LTM 3계층 명시적 분리 + 자동 승격 파이프라인 |
| **MemGPT 세션 경계 브릿지** | 세션 종료 이벤트 훅 + WRITEBACK_PROMPT 강화 |
| **선별적 자동 기억** | 4축 스코어링 (무분별한 전체 기억 → 중요도 기반 선별) |
| **에피소드 vs 시맨틱 메모리** | `memory_type` 필드로 에피소드(특정 사건)와 시맨틱(일반 규칙) 구분 |
| **BM25 + 시간 감쇠 RAG** | 기존 `search_relevant()` 패턴(tf_score*0.7 + time_score*0.3) 유지·확장 |
| **중복 방지** | 3단계 중복 판단 (exact → semantic → tag) |
| **프루닝 자동화** | 기존 `ProjectMemory.prune()` SCORE_DECAY=0.95 + TTL 정책 통합 |
