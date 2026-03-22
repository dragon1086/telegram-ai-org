# PRD: 저장구조 혁신 — 메타데이터 기반 메모리 아키텍처

---

**문서 ID**: PRD-2026-03-22-storage-innovation
**작성일**: 2026-03-22
**작성자**: aiorg_product_bot (PM)
**버전**: v1.0
**상태**: 리뷰 대기
**리뷰 대상**: 개발팀(aiorg_engineering_bot), 데이터팀

---

## 1. 배경 및 목적

### 1.1 현재 구조의 한계

현재 메모리 시스템은 마크다운 파일 기반으로, 아래 5가지 핵심 한계를 지닌다:

| 한계 | 실제 영향 |
|------|---------|
| **크로스-파일 관계 표현 불가** | "ACT-5가 T-260에서 파생됨"을 시스템이 모름 |
| **메타데이터 없음 → 필터 불가** | "엔지니어링 관련 결정만" 검색 불가 |
| **시간 유효성 없음** | 오래된 사실과 최신 사실 구분 불가 |
| **키워드 검색만** | "캐시"로 검색해도 "인메모리 저장소" 못 찾음 |
| **사일로 분리** | 런타임 메모리 ↔ Claude Code 메모리 단절 |

### 1.2 목적

본 PRD는 **"마크다운 파일 + 표준 메타데이터 스키마 + 시맨틱 검색 레이어"** 의 점진적 혁신을 통해 아래를 달성하는 요구사항을 정의한다:

1. 데이터 간 의미 있는 관계 표현 (1:1, 1:N, M:N)
2. 다차원 메타데이터 필터링 쿼리
3. 시간 유효성 자동 관리
4. 시맨틱(의미론적) 검색
5. LLM 자동 메타데이터 생성

---

## 2. 범위

### In-Scope
- 메모리 파일(`.md`) YAML frontmatter 표준 스키마 정의
- SQLite 기반 메타 인덱스 레이어 구현 요구사항
- 데이터 간 연관관계 유형 및 매핑 정책
- 쿼리 시나리오별 우선순위 및 인덱스 전략
- 경량 LLM을 통한 메타데이터 자동 생성 파이프라인

### Out-of-Scope
- Neo4j/그래프 DB 도입 (Phase 4, 장기)
- 기존 메모리 파일 내용(본문) 변경
- 외부 유료 임베딩 API (폴백은 BM25)

---

## 3. 메타데이터 필드 상세 스펙

### 3.1 표준 YAML Frontmatter 스키마

모든 메모리 파일에 공통 적용되는 표준 스키마:

```yaml
---
# === 식별자 (Identifiers) ===
id: "mem-{YYYY-MM-DD}-{SEQ3}"    # 예: mem-2026-03-22-001
version: "1.0"                    # 수정 시 증가 (major.minor)
parent_id: null                   # 파생된 원본 메모리 ID (없으면 null)

# === 분류 (Classification) ===
type: "decision"                  # 열거형 — 아래 3.2 참조
domain: "engineering"             # 열거형 — 아래 3.3 참조
scope: "global"                   # 열거형 — 아래 3.4 참조
importance: 9                     # 0–10 정수 (LLM 자동 채점, 인간 검토)
status: "active"                  # 열거형 — 아래 3.5 참조

# === 시간 (Timestamps) ===
created_at: "2026-03-22T12:00:00" # 생성 시각 (ISO 8601, 자동 기록)
updated_at: "2026-03-22T15:30:00" # 최종 수정 시각 (자동 갱신)
valid_from: "2026-03-22"          # 이 항목이 유효한 시작일
valid_until: null                 # 만료일 (null = 무기한, "YYYY-MM-DD" 형식)

# === 소유자 (Ownership) ===
author: "aiorg_pm_bot"            # 최초 작성자 (단일)
approved_by: null                 # Rocky 승인 필요 시 "rocky", 아니면 null
contributors: []                  # 추가 기여자 목록 (다중 허용)

# === 태그 (Tags) ===
tags:
  - "memory/architecture"         # 계층형: "{domain}/{topic}" 형식
  - "project/telegram-ai-org"
  - "phase/phase1"

# === 관계 (Relations) ===
related:
  - id: "task-T-260"
    relation: "implements"        # 관계 타입 — 아래 4.1 참조
    confidence: 0.95              # 0.0–1.0 (LLM 자동 채점)
  - id: "mem-2026-03-19-003"
    relation: "extends"
    confidence: 0.80

# === 검색 최적화 (Search) ===
summary: "1–2줄 핵심 요약 (LLM 자동 생성)"
keywords: ["keyword1", "keyword2"]  # 핵심 키워드 (LLM 자동 추출)
embedding_updated_at: null          # 마지막 벡터 임베딩 시각
---
```

---

### 3.2 `type` 필드 정의

| 값 | 설명 | 예시 |
|----|------|------|
| `decision` | 의사결정 사항 | "캐시 레이어 도입 결정" |
| `fact` | 관찰된 사실/현상 | "테스트 12개 PASS 확인" |
| `task` | 태스크/액션 아이템 | "T-260 SharedMemory 구현" |
| `feedback` | 피드백/회고 사항 | "응답 지연 이슈 피드백" |
| `knowledge` | 개념/지식 기반 | "Chroma 벡터 DB 특성" |
| `rule` | 운영 규칙/정책 | "프로덕션 파일 수정 승인 필수" |

- **필수여부**: 필수
- **기본값**: `fact`
- **허용값**: 위 6가지 열거형만 허용

---

### 3.3 `domain` 필드 정의

| 값 | 설명 |
|----|------|
| `engineering` | 개발, 코딩, 아키텍처 |
| `design` | UI/UX, 디자인 |
| `ops` | 운영, 인프라, 배포 |
| `growth` | 마케팅, 성장, 지표 |
| `strategy` | 전략, 비즈니스 결정 |
| `meta` | 시스템 자체에 관한 것 |

- **필수여부**: 필수
- **기본값**: `meta`
- **허용값**: 위 6가지 열거형만 허용

---

### 3.4 `scope` 필드 정의

| 값 | 설명 |
|----|------|
| `global` | 전 조직 공통 |
| `pm` | 기획실 전용 |
| `engineering` | 개발실 전용 |
| `research` | 리서치실 전용 |
| `design` | 디자인팀 전용 |
| `growth` | 그로스팀 전용 |
| `ops` | 운영팀 전용 |

- **필수여부**: 필수
- **기본값**: `global`

---

### 3.5 `status` 필드 정의

| 값 | 설명 | 전환 규칙 |
|----|------|---------|
| `active` | 현재 유효한 항목 | 기본 상태 |
| `deprecated` | 더 이상 권장하지 않음 | `superseded`로 전환 전 중간 상태 |
| `superseded` | 새 항목으로 교체됨 | `superseded_by` 필드 필수 |
| `pending` | 검토/승인 대기 중 | `approved_by` 채워지면 `active`로 전환 |

- **필수여부**: 필수
- **기본값**: `active`

---

### 3.6 `tags` 필드 정의

- **다중값 허용**: 최대 10개
- **계층 구조**: `{category}/{subcategory}` 형식 (depth ≤ 3)
- **예약 카테고리**: `memory/`, `project/`, `phase/`, `org/`, `task/`
- **필수여부**: 선택 (최소 1개 권장)
- **기본값**: `[]`

---

### 3.7 `importance` 필드 정의

- **범위**: 0 (불필요) ~ 10 (최고 중요)
- **LLM 자동 채점 기준**:
  - 9–10: 프로덕션 영향, Rocky 직접 결정
  - 7–8: 아키텍처/구조 변경
  - 5–6: 일반 기능 결정
  - 3–4: 참고 사항
  - 0–2: 임시/일회성
- **필수여부**: 필수
- **기본값**: `5`
- **LLM 자동 메타데이터 저장 임계값**: `importance ≥ 6`만 자동 저장

---

### 3.8 `valid_until` 필드 정의

- **형식**: `"YYYY-MM-DD"` 또는 `null`
- **null의 의미**: 무기한 유효 (명시적으로 `deprecated`/`superseded` 처리 전까지)
- **만료 처리**: 매일 자정 크론이 만료된 항목을 `status: deprecated`로 자동 전환
- **필수여부**: 선택
- **기본값**: `null`

---

### 3.9 소유권 정책

| 필드 | 허용 | 설명 |
|------|------|------|
| `author` | 단일값만 | 최초 생성한 봇/사람 (수정 불가) |
| `approved_by` | 단일값 또는 null | 승인자 (Rocky 또는 null) |
| `contributors` | 다중값 허용 | 기여한 봇/사람 목록 |

**소유권 정책**: 작성자는 불변이다. 내용이 수정되면 `contributors`에 추가하고 `version`을 올린다.

---

## 4. 연관관계 매핑 정책

### 4.1 관계 유형 정의

| relation 값 | 설명 | 방향 | 예시 |
|------------|------|------|------|
| `implements` | A가 B를 구현함 | A → B | 코드 → 요구사항 |
| `references` | A가 B를 참조함 | A → B | 결정 → 근거 문서 |
| `extends` | A가 B를 확장/심화함 | A → B | 후속 결정 → 이전 결정 |
| `contradicts` | A가 B와 충돌함 | A ↔ B (양방향) | 새 규칙 → 구 규칙 |
| `triggers` | A가 B를 발생시킴 | A → B | 버그 → 핫픽스 태스크 |
| `validated_by` | A가 B에 의해 검증됨 | A ← B | 구현 ← 테스트 |

---

### 4.2 관계 카디널리티 정책

| 관계 유형 | 카디널리티 | 설명 |
|---------|-----------|------|
| 단일 메모리 → 승인자 | 1:1 | `approved_by`는 1명만 |
| 메모리 → 태그 | 1:N | 1개 메모리에 다수 태그 가능 |
| 메모리 ↔ 메모리 (related[]) | M:N | 양방향 관계 허용 |
| 태스크 → 메모리 | 1:N | 1개 태스크가 다수 메모리 생성 가능 |

---

### 4.3 참조 무결성 규칙

1. **참조 ID 검증**: `related[].id`는 실제 존재하는 메모리 ID 또는 태스크 ID여야 함
   - 존재하지 않는 ID 참조 시: `confidence: 0.0` 처리하고 경고 로그 기록
   - 강제 삭제는 하지 않음 (메모리 항목이 나중에 생성될 수 있음)

2. **존재하지 않는 ID 허용 조건**: `confidence < 0.5`인 경우 미검증 참조로 허용

---

### 4.4 삭제 시 연쇄 처리 방식

| 삭제 대상 | 연쇄 처리 |
|---------|---------|
| 메모리 항목 삭제 | `status: deprecated`로 소프트 삭제. 실제 파일 삭제 금지 |
| `related[]` 중 삭제된 항목 참조 | `confidence: 0.0`으로 마킹. 관계 레코드 유지 |
| `valid_until` 만료 | `status: deprecated` 자동 전환. 파일 보존 |

> **원칙**: 물리적 삭제 없음. 모든 삭제는 소프트 삭제(상태 변경)로 처리한다.

---

## 5. 쿼리 시나리오별 요구사항

### 5.1 쿼리 시나리오 목록 (우선순위 포함)

#### Must (즉시 구현 필수)

| ID | 시나리오 | 유형 | 발생빈도 | 비즈니스중요도 | 구현난이도 |
|----|---------|------|---------|------------|---------|
| Q-001 | 현재 유효한(status=active) 메모리 전체 조회 | 단순 조회 | 매우 높음 | 최상 | 낮음 |
| Q-002 | type + domain 필터 조회 (예: engineering decision) | 복합 조회 | 높음 | 높음 | 낮음 |
| Q-003 | 태스크 ID로 연관된 메모리 조회 (related[].id = "task-T-xxx") | 관계 탐색 | 높음 | 최상 | 중간 |
| Q-004 | 특정 날짜 이후 생성된 메모리 조회 (created_at >= N) | 시계열 조회 | 높음 | 높음 | 낮음 |
| Q-005 | importance ≥ 7인 항목만 필터 (고중요도 메모리 로드) | 단순 조회 | 높음 | 최상 | 낮음 |

#### Should (1차 릴리즈 내 구현 권장)

| ID | 시나리오 | 유형 | 발생빈도 | 비즈니스중요도 | 구현난이도 |
|----|---------|------|---------|------------|---------|
| Q-006 | tags 복합 조회 (태그 A AND 태그 B 교차) | 복합 조회 | 중간 | 높음 | 중간 |
| Q-007 | valid_until 기준 만료 예정 메모리 조회 | 시계열 조회 | 중간 | 중간 | 낮음 |
| Q-008 | scope 기준 조직별 메모리 필터 | 단순 조회 | 중간 | 중간 | 낮음 |
| Q-009 | 키워드 풀텍스트 검색 (keywords 필드 BM25) | 복합 조회 | 높음 | 높음 | 중간 |
| Q-010 | 관계 트래버설 1-hop (related 체인 1단계 탐색) | 관계 탐색 | 중간 | 높음 | 높음 |

#### Could (2차 릴리즈 고려)

| ID | 시나리오 | 유형 | 발생빈도 | 비즈니스중요도 | 구현난이도 |
|----|---------|------|---------|------------|---------|
| Q-011 | 시맨틱 유사도 검색 (Chroma 벡터 top-K) | 시맨틱 | 중간 | 높음 | 높음 |
| Q-012 | 관계 트래버설 N-hop (트리 전체 순회) | 관계 탐색 | 낮음 | 중간 | 매우 높음 |
| Q-013 | 변경 이력 조회 (version 별 diff) | 시계열 조회 | 낮음 | 낮음 | 높음 |

#### Won't (현재 범위 제외)

| ID | 시나리오 | 제외 이유 |
|----|---------|---------|
| Q-014 | 실시간 스트리밍 쿼리 | 인프라 복잡도 과대 |
| Q-015 | 그래프 패턴 매칭 (Cypher 쿼리) | Neo4j Phase 4 범위 |

---

### 5.2 인덱스 전략 권고안

SQLite `memories` 테이블 기준:

```sql
-- 테이블 정의
CREATE TABLE memories (
    id          TEXT PRIMARY KEY,
    version     TEXT,
    parent_id   TEXT,
    type        TEXT NOT NULL,
    domain      TEXT NOT NULL,
    scope       TEXT NOT NULL,
    importance  INTEGER NOT NULL DEFAULT 5,
    status      TEXT NOT NULL DEFAULT 'active',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    valid_from  TEXT,
    valid_until TEXT,
    author      TEXT,
    approved_by TEXT,
    summary     TEXT,
    keywords    TEXT,   -- JSON array
    tags        TEXT,   -- JSON array
    file_path   TEXT NOT NULL,
    embedding_updated_at TEXT
);

-- 관계 테이블
CREATE TABLE memory_relations (
    from_id     TEXT NOT NULL,
    to_id       TEXT NOT NULL,
    relation    TEXT NOT NULL,
    confidence  REAL DEFAULT 1.0,
    created_at  TEXT,
    PRIMARY KEY (from_id, to_id, relation)
);
```

**인덱스 전략 (우선순위 순)**:

| 인덱스 | 대상 쿼리 | 우선순위 |
|-------|---------|---------|
| `idx_status_importance` on `(status, importance DESC)` | Q-001, Q-005 | Must |
| `idx_type_domain` on `(type, domain)` | Q-002 | Must |
| `idx_created_at` on `(created_at)` | Q-004 | Must |
| `idx_relations_to_id` on `memory_relations(to_id)` | Q-003 | Must |
| `idx_valid_until` on `(valid_until)` | Q-007 | Should |
| `idx_scope` on `(scope)` | Q-008 | Should |
| FTS5 virtual table on `(summary, keywords)` | Q-009 | Should |

---

## 6. 비기능 요구사항

### 6.1 성능 목표

| 항목 | 목표값 | 측정 방법 |
|------|-------|---------|
| 단순 조회(Q-001~Q-005) 응답시간 | < 50ms | SQLite query plan |
| 복합 조회(Q-006~Q-009) 응답시간 | < 200ms | 실측 |
| 시맨틱 검색(Q-011) 응답시간 | < 500ms | Chroma query latency |
| LLM 메타데이터 생성 시간 | < 3초 | Gemini Flash API 기준 |
| 인덱스 재구축 시간 | < 30초 | 파일 500개 기준 |

### 6.2 확장성 기준

| 항목 | 초기 목표 | 1년 목표 |
|------|---------|---------|
| 메모리 파일 수 | ~100개 | ~2,000개 |
| SQLite DB 크기 | < 10MB | < 200MB |
| 관계 레코드 수 | ~500개 | ~10,000개 |
| 임베딩 벡터 수 | - | ~2,000개 |

### 6.3 가용성 / 안정성

- SQLite 인덱스 손상 시 마크다운 파일에서 완전 재구축 가능해야 함 (재구축 스크립트 필수)
- LLM API 실패 시 폴백: BM25 키워드 검색으로 자동 전환
- 인덱스-파일 동기화: 매 1시간 크론으로 drift 감지 및 자동 보정

### 6.4 이전 호환성

- 기존 메모리 파일(`.md`) 본문 내용 변경 없음
- frontmatter가 없는 기존 파일은 `status: active, importance: 5` 기본값으로 인덱싱
- 기존 `MEMORY.md` 인덱스는 유지하되, 점진적으로 SQLite로 이관

---

## 7. 구현 단계 및 일정

| 단계 | 기간 | 핵심 산출물 | 의사결정 포인트 |
|------|------|------------|--------------|
| **Phase 0**: 스키마 표준화 | 1–2일 | 표준 frontmatter 적용 파일 4개 | 없음 (리스크 없음) |
| **Phase 1**: 메타 인덱스 | 3–5일 | `core/memory_index.py` + SQLite | Rocky 코드 리뷰 |
| **Phase 2**: 시맨틱 검색 | 1–2주 | Chroma + BM25 통합 검색 API | Ollama 설치 승인 |
| **Phase 3**: LLM 자동화 | 2–3주 | 자동 메타데이터 생성 파이프라인 | Gemini Flash API 비용 승인 |
| **Phase 4**: 지식 그래프 | 1–3개월 | Neo4j + Graphiti 전환 | 인프라 예산 승인 |

---

## 8. 미결 사항 (Open Issues)

| ID | 이슈 | 담당 | 기한 |
|----|------|------|------|
| OI-001 | `importance` LLM 자동 채점 프롬프트 기준 확정 필요 | PM | Phase 3 시작 전 |
| OI-002 | Chroma vs. Qdrant 벡터 DB 최종 선택 | Engineering | Phase 2 시작 전 |
| OI-003 | 임베딩 모델: nomic-embed-text vs. all-MiniLM-L6-v2 성능 비교 | Research | Phase 2 시작 전 |
| OI-004 | 메타데이터 자동 생성 시 Rocky 검토 workflow 확정 | PM + Rocky | Phase 3 시작 전 |
| OI-005 | `valid_until` 자동 만료 시 Rocky 알림 방식 결정 | Ops | Phase 1 완료 후 |
| OI-006 | 기존 메모리 파일 전체 backfill 공수 추정 (파일 ~20개) | Engineering | Phase 0 착수 시 |

---

## 9. 부서 간 리뷰 체크리스트

### 9.1 개발팀 (aiorg_engineering_bot) 리뷰 항목

- [ ] SQLite 스키마 (`memories`, `memory_relations`) — 누락 컬럼 없는지 확인
- [ ] FTS5 적용 가능 여부 (Python sqlite3 버전 확인)
- [ ] `memory_index.py` 설계 — frontmatter 파싱 라이브러리 선택 (`python-frontmatter` vs. 자체 구현)
- [ ] 인덱스-파일 동기화 방식 — watchdog 이벤트 vs. 크론 재인덱싱 선택
- [ ] 관계 트래버설 1-hop 구현 난이도 재검토 (Q-010)
- [ ] 재구축 스크립트 설계 — SQLite 손상 시 완전 복구 가능한지 검증
- [ ] Phase 0 백필(backfill) 스크립트 공수 추정

### 9.2 데이터팀 리뷰 항목

- [ ] 메타데이터 스키마 필드 충분성 — 미래 분석 요구사항 충족 여부
- [ ] `importance` 0–10 척도의 LLM 채점 일관성 검증 방법
- [ ] `tags` 계층 구조 depth 3 제한 적절성
- [ ] 관계 타입 6가지 (implements/references/extends/contradicts/triggers/validated_by) 완결성
- [ ] 시계열 쿼리(Q-004, Q-007) 인덱스 전략 검토
- [ ] Chroma 임베딩 모델 교체 시 재색인 비용 추정

### 9.3 PM / Rocky 확인 항목

- [ ] `importance ≥ 6` 자동 저장 임계값 적절성 (너무 많이 / 너무 적게 저장되지 않는지)
- [ ] `approved_by` 필드 — Rocky 검토가 필요한 항목 기준 명확화
- [ ] Phase 3 Gemini Flash API 비용 한도 승인
- [ ] Phase 4 (Neo4j) 진행 여부 — 선택적 의사결정 포인트 확인
- [ ] Open Issues OI-001, OI-004 우선 결정 필요

---

*본 PRD는 리서치실 조사 결과(`docs/memory-architecture-research/`)를 기반으로 작성되었습니다.*
*다음 검토 일자: Phase 0 완료 후 (예상: 2026-03-24)*
