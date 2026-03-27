# 3계층 메모리 아키텍처 구현 방안 설계서 v1.0

**작성일**: 2026-03-27
**작성 조직**: 개발실 (engineering-senior-developer)
**태스크 ID**: T-aiorg_pm_bot-714
**태스크 유형**: 설계 (파일 변경 없음 — 이 문서만 산출)

---

## 결론

현재 코드베이스는 이미 `core/memory_manager.py`에 **CORE/SUMMARY/LOG 3계층 구조**가 구현되어 있다.
단, **Claude 세션 브릿지(MEMORY.md)** 와 **자동 중요도 판단 저장 로직**이 분리되어 있어 대화 중 발생한 정보가 자동으로 적절한 계층에 저장되지 않는 구조적 공백이 존재한다.
이를 해소하기 위한 3단계 점진적 구현 로드맵(Low→Medium→High 난이도)을 도출한다.

---

## Phase 1: 현황 분석 — MEMORY.md 섹션별 계층 분류표 및 매핑 다이어그램

### 1-1. 현재 MEMORY.md 섹션별 계층 분류표

| MEMORY.md 섹션 | 현재 위치 | 3계층 귀속 | TTL | 비고 |
|----------------|-----------|-----------|-----|------|
| Memory Index (파일 링크 5개) | MEMORY.md 상단 | **장기(Long-Term)** | 영구 | 구조 자체는 변하지 않음 |
| Pending Tasks 테이블 (pending/in_progress) | MEMORY.md 중간 | **중기(Mid-Term)** | ~30일 | 태스크 완료 시 resolved → archived |
| 최근 resolved 항목 테이블 | MEMORY.md 하단 | **중기→장기 전환 대기** | 7일→archived | 30일 후 삭제, 이력은 장기에 보존 |
| 전체 조직 공통 운영 원칙 | MEMORY.md 하단 | **장기(Long-Term)** | 영구 | 정책 결정사항, 폐기 시 명시적 삭제만 |
| Gemini 모델 버전 정보 | MEMORY.md 내 | **중기(Mid-Term)** | ~30일 | 모델 버전 변경 시 갱신 필요 |
| 오픈소스화 프로젝트 이력 | MEMORY.md 하단 | **장기(Long-Term)** | 영구 | 완료된 커밋 이력, 삭제 불필요 |
| 앱스토어 링크 (ETC-05) | MEMORY.md 하단 | **장기(Long-Term)** | 영구 | 변경 없는 외부 링크 |
| 보고 형식 운영 원칙 | MEMORY.md 하단 | **장기(Long-Term)** | 영구 | 조직 운영 규칙 |

**현황 진단**: 현재 MEMORY.md에는 단기(세션 내 임시) 섹션이 존재하지 않음.
세션 중 Rocky가 언급한 일회성 지시, 실험적 아이디어, 임시 컨텍스트가 저장될 공간이 없어
→ 전부 Pending Tasks에 등록되거나(오버스케일) 아예 소멸(언더스케일)되는 이분법적 문제 발생.

---

### 1-2. 기존 Pending Tasks 라이프사이클 ↔ 3계층 매핑

```
[대화 중 발생]
      │
      ▼
  ┌─────────────────────────────────────────┐
  │  📥 단기(Short-Term) — 세션 내 휘발     │  ← 현재 공백 구간
  │  • Rocky 구두 지시, 아이디어, 임시 메모  │  TTL: 1 세션
  │  • MEMORY.md ## [SHORT-TERM] 섹션       │
  └──────────────┬──────────────────────────┘
                 │ 승격 조건 (중요도 ≥ 임계값 OR 태스크 ID 부여)
                 ▼
  ┌─────────────────────────────────────────┐
  │  📋 중기(Mid-Term) — Pending Tasks      │  ← 현재 Pending Tasks 테이블
  │  • status: pending / in_progress        │  TTL: 7~30일
  │  • ~/.ai-org/memory/{scope}.md [LOG]    │
  └──────────────┬──────────────────────────┘
                 │ resolved 후 7일 경과 → archived
                 ▼
  ┌─────────────────────────────────────────┐
  │  🗄️  장기(Long-Term) — 영구 보존        │  ← 현재 운영 원칙 + DB
  │  • status: archived (30일 후 삭제)       │  TTL: 영구 or 30일 후 삭제
  │  • ~/.ai-org/memory/{scope}.md [CORE]   │
  │  • lesson_memory.db / retro_memory.db   │
  └─────────────────────────────────────────┘
```

**라이프사이클 매핑 (status ↔ 3계층)**:

| status | 3계층 귀속 | 저장 위치 |
|--------|-----------|---------|
| pending | 중기 | MEMORY.md Pending Tasks |
| in_progress | 중기 | MEMORY.md Pending Tasks |
| resolved | 중기→장기 전환 대기 | MEMORY.md resolved 섹션 (7일 보존) |
| archived | 장기 | project_pending_tasks.md 이력 표 |
| (삭제) | — | archived 후 30일 경과, context.db에 이력 보존 |

---

### 1-3. 메모리 I/O 발생 지점 목록

| 위치 | 파일 | 읽기/쓰기 | 트리거 |
|------|------|----------|--------|
| MemoryManager.load() | core/memory_manager.py | 읽기 | 봇 시작, 프롬프트 빌드 시 |
| MemoryManager._save() | core/memory_manager.py | 쓰기 | add_log_entry, update_core 호출 시 |
| SharedMemory.get/set | core/shared_memory.py | 읽기/쓰기 | 봇 간 상태 동기화 |
| ContextDB.store_message | core/context_db.py | 쓰기 | 모든 Telegram 메시지 수신 시 |
| ContextDB.get_context | core/context_db.py | 읽기 | 프롬프트 컨텍스트 조립 시 |
| LessonMemory.add_lesson | core/lesson_memory.py | 쓰기 | 태스크 실패/성공 후 회고 시 |
| AgentPersonaMemory.update | core/agent_persona_memory.py | 쓰기 | 에이전트 성능 추적 시 |
| memory_mcp_server.update_core | tools/memory_mcp_server.py | 쓰기 | MCP 호출 시 (Claude Code 직접 호출) |
| MEMORY.md 직접 수정 | Claude Code Edit | 쓰기 | PM/봇이 수동으로 Edit 도구 사용 시 |
| settings.local.json hooks | .claude/settings.local.json | 읽기 | PostToolUse(Write/Edit), Stop 이벤트 |
| Stop hook | .claude/settings.local.json | 쓰기 | 세션 종료 시 로그 파일 기록 |

**현황 진단**: 현재 중요도 자동 판단 후 적절 계층으로 라우팅하는 로직이 없음.
모든 메모리 쓰기는 수동 or 사전 정의된 이벤트(태스크 성공/실패)에 의존.

---

## Phase 2: 3계층 메모리 구조 설계 명세

### 2-1. MEMORY.md 신규 섹션 스키마

```markdown
# Memory Index
...

## [SHORT-TERM] 단기 메모리 — 현재 세션 임시 컨텍스트
<!-- TTL: 1 세션 | Stop 훅에서 중요도 판단 후 중기 승격 or 자동 삭제 -->
<!-- 스키마: created_at | content | importance(1-4) | promote_candidate(bool) -->

| created_at | content | importance | promote? |
|------------|---------|------------|---------|
| 2026-03-27 14:30 | Rocky: "리서치 크론 매일 9시로 설정하고 싶다" | 3 | true |

## [MID-TERM] 중기 메모리 — 진행 중 태스크 및 최근 결정사항
<!-- TTL: 7~30일 | resolved 후 7일 → 장기 승격 -->

### Pending Tasks
| id | title | created_at | status | resolved_at |
...

### 최근 결정사항 (지난 30일)
| date | decision | context | expires_at |
...

## [LONG-TERM] 장기 메모리 — 운영 원칙 및 영구 이력
<!-- TTL: 영구 | 명시적 삭제만 허용 -->

### 운영 원칙
...

### 완료 이력 (archived)
...
```

---

### 2-2. 계층별 스키마 명세서

#### SHORT-TERM (단기)

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| created_at | datetime | 기록 시각 (ISO) | 2026-03-27 14:30 |
| content | string | 원문 발화 또는 정보 | "리서치 크론 설정" |
| importance | int(1-4) | 임시 중요도 (낮음) | 3 |
| promote_candidate | bool | 중기 승격 후보 여부 | true |
| session_id | string | 현재 세션 식별자 | sess_20260327 |

**TTL 정책**: 세션 종료(Stop 훅) 시 자동 평가 → promote=true이면 중기로 이동, false이면 삭제

---

#### MID-TERM (중기)

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| id | string | 태스크/결정 ID | ST-12, DEC-03 |
| title | string | 요약 제목 | "리서치 크론 매일 9시" |
| created_at | date | 생성일 | 2026-03-27 |
| status | enum | pending/in_progress/resolved/archived | in_progress |
| resolved_at | date/null | 완료일 | 2026-03-28 |
| expires_at | date | 만료일 (자동 계산: resolved_at + 7일) | 2026-04-04 |
| importance | int(5-8) | 중기 중요도 | 7 |
| source | enum | manual/auto/promoted | promoted |

**TTL 정책**:
- pending/in_progress: expires_at 없음 (항상 유효)
- resolved: expires_at = resolved_at + 7일 → 장기 승격
- importance ≥ 8이면 강제 장기 승격 (TTL 무시)

---

#### LONG-TERM (장기)

| 필드명 | 타입 | 설명 | 예시 |
|--------|------|------|------|
| id | string | 원칙/이력 ID | RULE-01, ARC-ST-11 |
| category | enum | rule/decision/archived_task/project_log | rule |
| title | string | 제목 | "Gemini 모델 버전 원칙" |
| content | string | 상세 내용 | "gemini-2.5-flash 표준..." |
| created_at | date | 최초 기록일 | 2026-03-22 |
| promoted_from | string/null | 승격 출처 (중기 ID) | ST-11 |
| delete_after | date/null | 삭제 예정일 (archived 태스크만) | 2026-05-27 |

**TTL 정책**:
- rule/decision: 영구 보존 (명시적 삭제만)
- archived_task: delete_after = archived_at + 30일 후 삭제
- 삭제 전 context.db에 이력 백업

---

### 2-3. 기존 Pending Tasks 통합 설계안

기존 Pending Tasks 테이블은 **MID-TERM 섹션으로 물리적 이동**:

```
현재:                          변경 후:
## Pending Tasks (루트)   →   ## [MID-TERM] > ### Pending Tasks
## 최근 resolved 항목    →   ## [MID-TERM] > ### 최근 결정사항
## 운영 원칙              →   ## [LONG-TERM] > ### 운영 원칙
## 오픈소스화 이력         →   ## [LONG-TERM] > ### 완료 이력
```

**하위 호환성 보장**: 기존 라이프사이클 규칙(pending→resolved→archived→삭제)은 그대로 유지.
섹션 헤더만 변경되며, 스키마 필드 추가(importance, source, expires_at).

---

### 2-4. 계층 간 승격/강등 규칙 정의서

| 전환 | 조건 | 자동화 방식 |
|------|------|-----------|
| 단기 → 중기 승격 | promote_candidate=true AND (importance≥3 OR 명시적 기억 지시) | Stop 훅에서 평가 |
| 중기 → 장기 승격 | resolved_at + 7일 경과 OR importance≥8 | 세션 시작 시 TTL 체크 |
| 장기 → 삭제 | archived_at + 30일 경과 (category=archived_task만) | 주간 배치 또는 세션 시작 시 |
| 중기 → 강제 장기 | Rocky "운영 원칙으로 채택" 발화 감지 | 중요도 자동 판단 엔진 |
| 단기 → 삭제 | promote_candidate=false (세션 종료 시) | Stop 훅 자동 정리 |

---

## Phase 3: 중요도 자동 판단 로직 설계

### 3-1. 중요도 판단 기준 명세서

#### 규칙 기반 스코어링 (0~10점)

| 분류 | 판단 기준 | 점수 부여 | 귀속 계층 |
|------|----------|----------|---------|
| **키워드 트리거** | "기억해", "저장해", "잊지마", "중요해" | +5 | 중기 이상 |
| **태스크 생성** | 태스크 ID(ST-xx, ETC-xx) 부여됨 | +7 | 중기 |
| **반복 언급** | 동일 주제 3회 이상 언급 (세션 내) | +4 | 중기 |
| **결정/채택** | "채택", "확정", "원칙으로", "정책" | +8 | 장기 |
| **수치/날짜** | 구체적 수치, 마감일, 버전 명시 | +3 | 중기 |
| **부정/취소** | "취소", "안 해도 돼", "무시해" | -10 | 삭제 |
| **일회성 지시** | "지금만", "이번에만", "테스트로" | -5 | 단기 유지 |
| **URL/링크** | 외부 링크 포함 (앱스토어, GitHub 등) | +6 | 장기 |
| **에러/장애** | "오류", "crash", "실패", 스택트레이스 | +5 | 중기 (lesson_memory 연동) |

#### 최종 계층 결정 규칙

```python
def determine_layer(score: int, context: dict) -> str:
    if score <= 2:
        return "SHORT-TERM"   # 세션 내 임시
    elif score <= 6:
        return "MID-TERM"     # 중기 저장
    else:
        return "LONG-TERM"    # 장기 보존

# 예외 처리
if context.get("explicit_cancel"):     return "DELETE"
if context.get("task_id_assigned"):    return "MID-TERM"
if context.get("policy_adoption"):     return "LONG-TERM"
```

---

### 3-2. 판단 플로우차트

```
[대화 메시지 수신]
        │
        ▼
[메시지 스캔: 키워드/패턴 매칭]
        │
        ├─ 취소/부정 감지 → [기존 항목 삭제 or 무시]
        │
        ├─ 태스크 ID 부여 이벤트 → [즉시 MID-TERM 저장]
        │
        ├─ 정책/원칙 채택 감지 → [즉시 LONG-TERM 저장]
        │
        └─ 그 외 → [점수 계산]
                        │
              score ≤ 2 │ score 3~6  │ score ≥ 7
                        │            │
                   [SHORT-TERM]  [MID-TERM]  [LONG-TERM]
                   세션 내 임시   Pending에   운영 원칙에
                   컨텍스트 저장  등록        추가
                        │
                   [세션 종료 시]
                   promote 재평가
                        │
              promote=true → MID-TERM 승격
              promote=false → 삭제
```

---

### 3-3. 계층 승격/강등 조건문 목록

```python
# 단기 → 중기 승격 조건 (OR 관계)
PROMOTE_SHORT_TO_MID = [
    "importance >= 3 AND promote_candidate == True",
    "mention_count >= 3",           # 동일 세션 내 3회 이상 언급
    "task_id_assigned == True",     # 태스크 ID 부여됨
    "explicit_remember == True",    # "기억해" 류 발화
    "has_deadline == True",         # 구체적 날짜/마감 포함
]

# 중기 → 장기 승격 조건 (OR 관계)
PROMOTE_MID_TO_LONG = [
    "status == 'resolved' AND days_since_resolved >= 7",
    "importance >= 8",              # 높은 중요도
    "policy_adoption == True",      # 운영 원칙 채택
    "mention_count >= 10",          # 누적 10회 이상 언급 (cross-session)
]

# 강등/삭제 조건
DEMOTE_OR_DELETE = [
    "explicit_cancel == True",      # "취소해", "무시해"
    "status == 'archived' AND days_since_archived >= 30",  # 30일 경과
    "importance <= 1 AND session_count == 0",  # 한 번도 참조 안 된 항목
]
```

---

### 3-4. 중복 방지 및 갱신 로직 설계안

```python
def save_memory(content: str, layer: str, context: dict) -> None:
    """중복 방지 + 갱신 판단 로직"""

    # 1단계: 기존 항목 유사도 검색 (BM25)
    existing = memory_mcp_server.search_memories(content, top_k=3)

    # 2단계: 유사도 임계값 판단
    if existing and existing[0].similarity >= 0.85:
        # 기존 항목 갱신 (신규 삽입 X)
        existing_entry = existing[0]

        if context.get("importance") > existing_entry.importance:
            # 중요도 상승 → 상위 계층으로 승격
            promote(existing_entry, layer)
        else:
            # 동일 계층에서 내용 갱신
            update(existing_entry, content)

    elif existing and existing[0].similarity >= 0.60:
        # 관련 항목 있음 → 연결 참조 추가 후 신규 삽입
        insert_with_reference(content, layer, ref_id=existing[0].id)

    else:
        # 완전 신규 → 삽입
        insert_new(content, layer)
```

**중복 방지 키 기준**:
1. 태스크 ID (ST-xx, ETC-xx) — 정확 매칭으로 중복 방지
2. 발화 내용 BM25 유사도 ≥ 0.85 — 갱신
3. URL/링크 — 정확 매칭

---

## Phase 4: 구현 태스크 분해 및 우선순위 로드맵

### 4-1. 구현 태스크 분해표

| 태스크 ID | 제목 | 난이도 | 우선순위 | 예상 소요 | 의존 태스크 | 담당 레이어 |
|-----------|------|--------|----------|----------|------------|-----------|
| **MEM-01** | MEMORY.md 섹션 헤더 재구조화 (SHORT/MID/LONG 분리) | Low | P0 | 1h | 없음 | MEMORY.md 구조 변경 |
| **MEM-02** | SHORT-TERM 섹션 스키마 추가 + 예시 데이터 삽입 | Low | P0 | 30m | MEM-01 | MEMORY.md 구조 변경 |
| **MEM-03** | Stop 훅 확장 — 세션 종료 시 SHORT-TERM 항목 promote 평가 | Medium | P1 | 3h | MEM-01 | 훅 추가 (settings.local.json + 스크립트) |
| **MEM-04** | TTL 만료 자동 처리 스크립트 (세션 시작 시 실행) | Medium | P1 | 4h | MEM-01, MEM-02 | 스킬 코드 수정 or 훅 추가 |
| **MEM-05** | 중요도 자동 판단 함수 구현 (규칙 기반 스코어링) | Medium | P1 | 6h | 없음 | 스킬 코드 수정 (core/memory_auto_judge.py 신규) |
| **MEM-06** | PM 봇 메시지 핸들러에 중요도 판단 훅 주입 | High | P2 | 8h | MEM-05, ST-08 | 스킬 코드 수정 |
| **MEM-07** | BM25 중복 검사 로직 memory_mcp_server.py 통합 | Medium | P2 | 4h | MEM-05 | 스킬 코드 수정 |
| **MEM-08** | MID→LONG 자동 승격 배치 로직 구현 | Medium | P2 | 4h | MEM-04, MEM-05 | 스킬 코드 수정 |
| **MEM-09** | 테스트 작성 (unit: 판단 로직 + integration: 라이프사이클) | Medium | P1 | 6h | MEM-05, MEM-04 | 테스트 코드 |
| **MEM-10** | orchestration.yaml global_instructions 메모리 정책 반영 | Low | P2 | 1h | MEM-01 | 오케스트레이션 yaml 수정 |

---

### 4-2. 기존 Pending Tasks 충돌/의존 분석

| 기존 태스크 | 연관 MEM 태스크 | 충돌/의존 관계 | 병렬 가능 여부 |
|------------|----------------|--------------|--------------|
| **ST-08** (bot_message_handler.py 분리) | MEM-06 | **의존**: MEM-06은 핸들러 파일 안정화 후 주입해야 함. ST-08 완료 전 MEM-06 작업 시 충돌 가능 | ❌ 순차 (ST-08 → MEM-06) |
| **ST-08c** (pm_message_handler.py 분리) | MEM-06 | **의존**: 동일. PM 핸들러 분리 후 중요도 판단 훅 주입 | ❌ 순차 (ST-08c → MEM-06) |
| **ETC-02** (E2E timeout 120s) | MEM-09 | **독립**: 테스트 인프라 개선, 직접 충돌 없음 | ✅ 병렬 가능 |
| **ETC-03** (min_id 필터링) | MEM-05, MEM-06 | **약한 의존**: 메시지 필터링 후 판단 로직이 실행되므로 ETC-03 먼저 완료 권장 | ⚠️ 권장 순차 |
| **ETC-04** (E2E 테스트 완성) | MEM-09 | **연계**: MEM-09 테스트 완성 후 ETC-04에 메모리 계층 시나리오 추가 가능 | ⚠️ 권장 순차 |
| **ST-11** (GitHub Release v1.0.0) | 없음 | **독립**: 메모리 아키텍처와 무관 | ✅ 병렬 가능 |

---

### 4-3. 3단계 점진적 롤아웃 계획서

#### 롤아웃 Phase 1 — MEMORY.md 구조 확장 (난이도: Low)

**목표**: 코드 변경 없이 MEMORY.md 파일 구조만 개선, 즉시 효과

**포함 태스크**: MEM-01, MEM-02, MEM-10

**작업 내용**:
1. MEMORY.md에 `## [SHORT-TERM]` 섹션 추가 (세션 내 임시 메모용)
2. `## Pending Tasks` → `## [MID-TERM] Pending Tasks` 헤더 변경
3. 운영 원칙 → `## [LONG-TERM]` 하위로 이동
4. orchestration.yaml global_instructions에 3계층 정책 1줄 추가

**Definition of Done**:
- [ ] MEMORY.md에 SHORT/MID/LONG 3개 섹션 헤더 존재
- [ ] 각 섹션에 TTL 정책 주석 포함
- [ ] 기존 Pending Tasks 테이블이 MID-TERM 하위에 정상 위치
- [ ] orchestration.yaml에 메모리 계층 언급 추가
- [ ] 기존 봇 동작에 영향 없음 (수동 테스트 확인)

**예상 소요**: 1.5시간

---

#### 롤아웃 Phase 2 — 저장 로직 훅 구현 (난이도: Medium)

**목표**: Stop 훅 + TTL 만료 처리로 반자동 메모리 관리 구현

**포함 태스크**: MEM-03, MEM-04, MEM-05, MEM-07, MEM-09

**전제 조건**: 롤아웃 Phase 1 완료

**작업 내용**:
1. `core/memory_auto_judge.py` 신규 생성 — 규칙 기반 스코어링 함수
2. `scripts/memory_ttl_check.py` 신규 생성 — TTL 만료 검사 및 승격/삭제
3. Stop 훅 확장 — `scripts/memory_ttl_check.py` 호출 추가
4. `tools/memory_mcp_server.py`에 BM25 중복 검사 통합
5. 단위 테스트 작성 (`tests/test_memory_auto_judge.py`)

**Definition of Done**:
- [ ] `memory_auto_judge.py` 규칙 10개 이상 구현, 점수 반환 정확도 테스트 통과
- [ ] TTL 만료 스크립트: SHORT-TERM 항목 평가 후 promote/delete 동작 확인
- [ ] BM25 중복 검사: 유사도 0.85 이상 항목 갱신, 0.6~0.85 참조 추가 동작 확인
- [ ] `pytest tests/test_memory_auto_judge.py` 전체 통과
- [ ] 기존 E2E 테스트 회귀 없음

**예상 소요**: 1.5~2일

---

#### 롤아웃 Phase 3 — 자동 판단 엔진 통합 (난이도: High)

**목표**: 모든 대화에서 실시간 중요도 판단 및 자동 계층 저장

**포함 태스크**: MEM-06, MEM-08

**전제 조건**: 롤아웃 Phase 2 완료 + ST-08 + ST-08c 완료

**작업 내용**:
1. PM 봇 메시지 핸들러에 `memory_auto_judge` 미들웨어 주입
2. MID→LONG 자동 승격 배치 로직 (`core/memory_lifecycle_manager.py`)
3. 테스트: 전체 대화 시나리오에서 메모리 자동 저장 동작 검증
4. 모니터링: 오탐(false positive) 저장 케이스 로깅

**Definition of Done**:
- [ ] "기억해" 발화 → MID-TERM 자동 등록 동작 확인
- [ ] 태스크 ID 부여 이벤트 → Pending Tasks 자동 등록 동작 확인
- [ ] 세션 3회 이상 언급 → 자동 승격 동작 확인
- [ ] resolved 후 7일 → 장기 자동 승격 동작 확인
- [ ] 오탐률 < 10% (Rocky 수동 검토 5세션 기준)
- [ ] 기존 E2E 전체 회귀 테스트 통과

**예상 소요**: 2~3일

---

### 4-4. 전체 로드맵 타임라인

```
2026-03-27 (오늘)
│
├── [즉시 착수 가능] 롤아웃 Phase 1 (1.5h)
│   MEM-01 → MEM-02 → MEM-10
│   (코드 변경 없음, 파일 구조만)
│
├── [병렬] ST-11 GitHub Release (독립)
│
2026-03-28
│
├── [롤아웃 Phase 2 시작] (1.5~2일)
│   MEM-05 → MEM-07 → MEM-03 → MEM-04 → MEM-09
│   (ETC-03 병렬 권장)
│
2026-03-29~30
│
├── [ST-08 + ST-08c 완료 대기]
│   (ST-08c 완료 후 MEM-06 착수 가능)
│
2026-03-31
│
└── [롤아웃 Phase 3 착수] (2~3일)
    MEM-06 → MEM-08 → 통합 테스트
```

---

## 요약 — 핵심 구현 포인트 3가지

1. **MEMORY.md 즉시 개선 가능** (Phase 1): 코드 수정 없이 헤더 재구조화만으로 3계층 분리 효과. 오늘 바로 적용 가능.

2. **Stop 훅이 핵심 자동화 진입점** (Phase 2): 세션 종료 시 SHORT-TERM 항목을 평가하는 훅 1개로 "대화 중 기억 → 세션 간 유지" 문제의 80%를 해결 가능. 기존 `core/memory_manager.py` CORE/SUMMARY/LOG 구조를 그대로 활용.

3. **ST-08/ST-08c 완료가 Phase 3 블로커** (Phase 3): 메시지 핸들러 리팩토링 전에 중요도 판단 훅을 주입하면 충돌 발생. ST-08→ST-08c→MEM-06 순서 반드시 준수.
