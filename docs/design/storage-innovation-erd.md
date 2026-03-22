# 메타데이터 스키마 ERD — 저장구조 혁신

**문서 ID**: DESIGN-2026-03-22-ERD-001
**작성일**: 2026-03-22
**작성자**: aiorg_design_bot
**버전**: v1.0
**상태**: 완성본

---

## 범례 (Legend)

| 색상 코드 | 의미 |
|----------|------|
| 🟦 파란색 (#4A90D9) | 핵심 엔티티 (Primary Entity) |
| 🟩 초록색 (#27AE60) | 보조 엔티티 (Support Entity) |
| 🟧 주황색 (#E67E22) | 외부 연동 엔티티 (External/Integration) |
| 🟥 빨간색 (#E74C3C) | 시스템 엔티티 (System Entity) |
| ──► 실선 | 직접 참조 관계 |
| ─ ─► 점선 | 논리적 관계 (물리적 FK 없음) |
| `1`, `N`, `M` | 카디널리티 표기 |

---

## 1. 전체 ERD (Mermaid)

```mermaid
erDiagram
    %% ===== 핵심 엔티티 =====

    MEMORY {
        TEXT    id              PK  "mem-{YYYY-MM-DD}-{SEQ3}"
        TEXT    version             "major.minor (e.g. 1.2)"
        TEXT    parent_id       FK  "파생 원본 메모리 ID (nullable)"
        TEXT    type                "decision|fact|task|feedback|knowledge|rule"
        TEXT    domain              "engineering|design|ops|growth|strategy|meta"
        TEXT    scope               "global|pm|engineering|research|design|growth|ops"
        INTEGER importance          "0-10 정수 (LLM 자동 채점)"
        TEXT    status              "active|deprecated|superseded|pending"
        TEXT    created_at          "ISO 8601 자동 기록"
        TEXT    updated_at          "최종 수정 시각 자동 갱신"
        TEXT    valid_from          "유효 시작일 (YYYY-MM-DD)"
        TEXT    valid_until         "만료일 (null = 무기한)"
        TEXT    author          FK  "최초 작성자 bot/human"
        TEXT    approved_by     FK  "승인자 (rocky|null)"
        TEXT    summary             "1-2줄 요약 (LLM 자동 생성)"
        TEXT    keywords            "JSON array — 핵심 키워드"
        TEXT    tags                "JSON array — 계층형 태그"
        TEXT    file_path           "마크다운 파일 절대 경로"
        TEXT    embedding_updated_at "마지막 벡터 임베딩 시각"
    }

    MEMORY_RELATION {
        TEXT    from_id         FK  "출발 메모리 ID"
        TEXT    to_id           FK  "도착 메모리/태스크 ID"
        TEXT    relation            "implements|references|extends|contradicts|triggers|validated_by"
        REAL    confidence          "0.0-1.0 (LLM 자동 채점)"
        TEXT    created_at          "관계 생성 시각"
    }

    TAG {
        TEXT    name            PK  "계층형 태그명 (e.g. memory/architecture)"
        TEXT    category            "최상위 카테고리 (memory/project/phase/org/task)"
        TEXT    subcategory         "2단계 분류"
        INTEGER usage_count         "사용된 메모리 수"
    }

    MARKDOWN_FILE {
        TEXT    file_path       PK  "절대 경로"
        TEXT    memory_id       FK  "연결된 메모리 ID (1:1)"
        TEXT    content_hash        "파일 변경 감지용 해시"
        TEXT    last_synced_at      "마지막 인덱스 동기화 시각"
    }

    TASK {
        TEXT    task_id         PK  "task-T-{숫자} 형식"
        TEXT    title               "태스크 제목"
        TEXT    status              "pending|in-progress|done"
        TEXT    org                 "담당 조직"
        TEXT    created_at          "생성 시각"
    }

    EMBEDDING_VECTOR {
        TEXT    memory_id       FK  "연결된 메모리 ID (1:1)"
        BLOB    vector              "벡터 데이터 (Chroma 관리)"
        TEXT    model_name          "사용된 임베딩 모델명"
        TEXT    updated_at          "최종 임베딩 업데이트 시각"
    }

    BOT_AGENT {
        TEXT    agent_id        PK  "aiorg_{role}_bot 형식"
        TEXT    role                "pm|engineering|design|research|ops|growth"
        TEXT    org                 "소속 조직명"
    }

    %% ===== 관계 정의 =====

    MEMORY ||--o{ MEMORY_RELATION : "from_id (보냄)"
    MEMORY ||--o{ MEMORY_RELATION : "to_id (받음)"
    MEMORY }o--|| MARKDOWN_FILE  : "1:1 파일 연결"
    MEMORY }o--|| BOT_AGENT      : "author (작성자)"
    MEMORY |o--o| MEMORY         : "parent_id (파생 원본)"
    MEMORY ||--o{ TAG            : "tags JSON (1:N)"
    MEMORY ||--o| EMBEDDING_VECTOR : "1:1 벡터 연결"
    MEMORY_RELATION }o--o{ TASK : "to_id → task-T-xxx (논리적)"
```

---

## 2. 엔티티 상세 정의표

### 2.1 MEMORY (핵심 엔티티)

| 필드명 | 타입 | 필수 | 제약조건 | 기본값 | 비고 |
|--------|------|------|---------|--------|------|
| `id` | TEXT | ✅ | PK, UNIQUE, NOT NULL, 형식: `mem-YYYY-MM-DD-NNN` | — | 자동 생성 |
| `version` | TEXT | ✅ | NOT NULL, 형식: `{major}.{minor}` | `"1.0"` | 수정 시 minor++ |
| `parent_id` | TEXT | ❌ | FK → MEMORY.id, nullable | `null` | 파생 메모리 체인 |
| `type` | TEXT | ✅ | IN ('decision','fact','task','feedback','knowledge','rule') | `'fact'` | LLM 자동 분류 |
| `domain` | TEXT | ✅ | IN ('engineering','design','ops','growth','strategy','meta') | `'meta'` | 담당 도메인 |
| `scope` | TEXT | ✅ | IN ('global','pm','engineering','research','design','growth','ops') | `'global'` | 접근 범위 |
| `importance` | INTEGER | ✅ | CHECK (importance BETWEEN 0 AND 10) | `5` | LLM 채점, ≥6만 자동 저장 |
| `status` | TEXT | ✅ | IN ('active','deprecated','superseded','pending') | `'active'` | 소프트 삭제용 |
| `created_at` | TEXT | ✅ | ISO 8601, NOT NULL | 저장 시 자동 | 불변 |
| `updated_at` | TEXT | ✅ | ISO 8601, NOT NULL | 저장 시 자동 | 갱신 시 자동 변경 |
| `valid_from` | TEXT | ❌ | 형식: YYYY-MM-DD | `created_at` 날짜 | 유효 시작일 |
| `valid_until` | TEXT | ❌ | 형식: YYYY-MM-DD 또는 null | `null` | null = 무기한 |
| `author` | TEXT | ✅ | NOT NULL, FK → BOT_AGENT.agent_id | — | 불변 |
| `approved_by` | TEXT | ❌ | FK → BOT_AGENT.agent_id, nullable | `null` | Rocky 또는 null |
| `summary` | TEXT | ❌ | 1-2줄 텍스트 | — | LLM 자동 생성 |
| `keywords` | TEXT | ❌ | JSON array 형식 | `'[]'` | LLM 자동 추출 |
| `tags` | TEXT | ❌ | JSON array 형식, 최대 10개 | `'[]'` | 계층형 `{cat}/{sub}` |
| `file_path` | TEXT | ✅ | NOT NULL, UNIQUE | — | .md 파일 경로 |
| `embedding_updated_at` | TEXT | ❌ | ISO 8601, nullable | `null` | Phase 2+ 활성화 |

### 2.2 MEMORY_RELATION (관계 엔티티)

| 필드명 | 타입 | 필수 | 제약조건 | 기본값 | 비고 |
|--------|------|------|---------|--------|------|
| `from_id` | TEXT | ✅ | PK(복합), FK → MEMORY.id | — | 출발 노드 |
| `to_id` | TEXT | ✅ | PK(복합) | — | 도착 노드 (메모리 또는 태스크) |
| `relation` | TEXT | ✅ | PK(복합), IN ('implements','references','extends','contradicts','triggers','validated_by') | — | 관계 타입 |
| `confidence` | REAL | ✅ | CHECK (confidence BETWEEN 0.0 AND 1.0) | `1.0` | LLM 채점 |
| `created_at` | TEXT | ❌ | ISO 8601 | 생성 시 자동 | — |

> **참조 무결성 특이사항**: `to_id`가 TASK를 가리킬 경우 FK 강제 없음 (논리적 참조). confidence < 0.5 이면 미검증 참조 허용.

### 2.3 TAG (보조 엔티티)

| 필드명 | 타입 | 필수 | 제약조건 | 비고 |
|--------|------|------|---------|------|
| `name` | TEXT | ✅ | PK, 형식: `{category}/{subcategory}` | 최대 depth 3 |
| `category` | TEXT | ✅ | IN ('memory','project','phase','org','task') | 예약 카테고리 |
| `subcategory` | TEXT | ❌ | nullable | 세부 분류 |
| `usage_count` | INTEGER | — | 집계 필드 (뷰 또는 트리거 갱신) | — |

---

## 3. 관계 카디널리티 정의표

| 관계 | 유형 | 방향 | 설명 |
|------|------|------|------|
| MEMORY → MEMORY_RELATION (from) | 1:N | 단방향 | 1개 메모리가 N개 관계 발생 |
| MEMORY → MEMORY_RELATION (to) | 1:N | 단방향 | 1개 메모리가 N번 참조됨 |
| MEMORY ↔ MEMORY (via MEMORY_RELATION) | M:N | 양방향 | 메모리 간 상호 관계 |
| MEMORY → MARKDOWN_FILE | 1:1 | 단방향 | 메모리당 파일 1개 |
| MEMORY → EMBEDDING_VECTOR | 1:1 | 단방향 | Phase 2 이후 활성화 |
| MEMORY → TAG | 1:N | 단방향 | 1개 메모리에 최대 10개 태그 |
| TAG → MEMORY | 1:N | 역방향 | 1개 태그가 N개 메모리에 사용 |
| MEMORY → BOT_AGENT (author) | N:1 | 단방향 | N개 메모리, 1명 작성자 |
| MEMORY → TASK | N:M | 논리적 | memory_relations.to_id로 매핑 |
| MEMORY → MEMORY (parent_id) | 자기참조 | 단방향 | 파생 체인 (트리 구조) |

---

## 4. 인덱스 전략 다이어그램

```
MEMORY 테이블 인덱스 맵
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  컬럼                    인덱스명                  대상 쿼리    우선순위
  ─────────────────────────────────────────────────────────
  (status, importance)  idx_status_importance     Q-001, Q-005  MUST
  (type, domain)        idx_type_domain           Q-002         MUST
  (created_at)          idx_created_at            Q-004         MUST
  (scope)               idx_scope                 Q-008         SHOULD
  (valid_until)         idx_valid_until           Q-007         SHOULD
  (summary, keywords)   FTS5 virtual table        Q-009         SHOULD

MEMORY_RELATION 테이블 인덱스 맵
  (to_id)               idx_relations_to_id       Q-003         MUST
  (from_id, relation)   idx_relations_from_rel    Q-010         SHOULD
```

---

*다음 문서: [metadata-hierarchy-diagram.md](metadata-hierarchy-diagram.md)*
