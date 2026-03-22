# 설계 패키지 최종 요약 — 저장구조 혁신 메타데이터 시각화

**문서 ID**: DESIGN-2026-03-22-SUM-001
**작성일**: 2026-03-22
**작성자**: aiorg_design_bot
**버전**: v1.0
**상태**: 검토 완료 (Phase 3 정제 포함)

---

## 핵심 설계 결론 (먼저 읽기)

**메타데이터 구조도 설계 완료.** 핵심은 세 가지입니다:

1. **`related[]` 배열** — 메모리 간 M:N 관계를 6가지 타입(implements/references/extends/contradicts/triggers/validated_by)으로 표현. confidence 0.0~1.0으로 신뢰도 관리.
2. **`valid_until` 시간 유효성** — null=무기한, 날짜 지정 시 크론이 자동으로 deprecated 처리. 지식 부패(knowledge decay) 자동 관리.
3. **`tags` 계층형 분류** — `{category}/{subcategory}` 형식 depth 3까지. 5개 예약 카테고리(memory/project/phase/org/task)로 일관성 강제.

---

## Phase별 산출물 완료 현황

### ✅ Phase 1: 분석 및 설계 기획 — 완료

| 산출물 | 파일 | 핵심 내용 |
|--------|------|---------|
| 엔티티-관계 분석 정리 | `storage-innovation-erd.md` §2 | 7개 엔티티, 필드별 타입/제약/기본값 전체 정의 |
| 시각화 범위 정의서 | `storage-innovation-erd.md` §4 | Must/Should 인덱스 7종, 쿼리 시나리오 Q-001~Q-013 |
| 다이어그램 레이아웃 스케치 | 아래 §3 참조 | ERD + 트리 + 플로우차트 3종 결정 |

**엔티티 목록 (7개)**:
- `MEMORY` (핵심) — 19개 필드
- `MEMORY_RELATION` (관계) — 5개 필드
- `TAG` (보조 분류) — 4개 필드
- `MARKDOWN_FILE` (파일 연동) — 4개 필드
- `TASK` (외부 참조) — 5개 필드
- `EMBEDDING_VECTOR` (Phase 2) — 4개 필드
- `BOT_AGENT` (주체) — 3개 필드

---

### ✅ Phase 2: 다이어그램 및 와이어프레임 설계 — 완료

| 산출물 | 파일 | 상태 |
|--------|------|------|
| 엔티티 관계도 (ERD/그래프) | `storage-innovation-erd.md` §1 | ✅ Mermaid ERD 완성 |
| 메타데이터 계층 구조 다이어그램 | `metadata-hierarchy-diagram.md` §2 | ✅ 6그룹 트리 완성 |
| 저장 흐름 와이어프레임 | `storage-retrieval-wireframe.md` PAGE 1 | ✅ 5단계 + 분기 완성 |
| 조회 흐름 와이어프레임 | `storage-retrieval-wireframe.md` PAGE 2 | ✅ 4라우트 완성 |
| 크론 자동화 흐름 | `storage-retrieval-wireframe.md` PAGE 3 | ✅ 3개 JOB 완성 |
| 범례 및 색상 가이드 | `design-color-legend.md` | ✅ 9색 팔레트 + WCAG AA |

---

### ✅ Phase 3: 검토 및 최종 정제 — 완료

**자체 검증 항목**:

| 검증 항목 | 결과 | 비고 |
|---------|------|------|
| PRD 스펙과 ERD 필드 일치성 | ✅ | 모든 필드 반영 |
| 쿼리 시나리오 Q-001~Q-013 커버리지 | ✅ | 조회 흐름 분기 완전 대응 |
| WCAG 2.1 AA 접근성 | ✅ | 색상 대비 4.5:1 이상, 아이콘 병기 |
| 디자인 시스템 일관성 | ✅ | 9색 팔레트 전 문서 통일 적용 |
| 관계 타입 6가지 완결성 | ✅ | implements/references/extends/contradicts/triggers/validated_by |
| 누락 엔티티 | ✅ | BOT_AGENT 추가 (PRD에서 author 필드 정의됐으나 엔티티 미정의) |

**피드백 반영 필요 항목 (개발팀 검증 대기)**:
- [ ] FTS5 virtual table Python sqlite3 버전 호환성 확인
- [ ] Chroma 임베딩 모델 최종 선정 (nomic-embed-text vs all-MiniLM-L6-v2)
- [ ] 1-hop 관계 트래버설(Q-010) 구현 난이도 재검토

---

## 핵심 다이어그램 요약

### ERD 핵심 관계 (3줄 요약)

```
MEMORY ──1:N──► MEMORY_RELATION ◄──1:N── MEMORY
  │ (from_id)    (relation, confidence)   (to_id)
  │
MEMORY ──1:1──► MARKDOWN_FILE (소스 오브 트루스)
MEMORY ──1:1──► EMBEDDING_VECTOR (Phase 2+)
```

### 메타데이터 계층 (6대 그룹)

```
MEMORY
├── 🆔 식별자: id, version, parent_id
├── 🏷 분류: type, domain, scope, importance, status
├── ⏰ 시간: created_at, updated_at, valid_from, valid_until
├── 👤 소유권: author, approved_by, contributors
├── 🔗 관계: related[] (id + relation + confidence)
└── 🔍 검색: summary, keywords, embedding_updated_at
```

### 저장 흐름 핵심 경로 (5단계)

```
이벤트 발생
  → ⚡ LLM 자동 메타데이터 생성 (Gemini Flash)
  → YAML Frontmatter 조립 (시스템 필드 병합)
  → .md 파일 저장 (소스 오브 트루스)
  → SQLite 인덱스 + 관계 테이블 동시 업데이트
  → [Phase 2] Chroma 임베딩 비동기 큐
```

### 조회 흐름 핵심 분기 (4-라우트)

```
쿼리 입력
  → LLM 쿼리 분석
  ├── EXACT: SQLite 메타 필터 (Q-001~Q-005, Must 인덱스)
  ├── SEMANTIC: BM25 + Chroma 벡터 (Q-009, Q-011)
  ├── RELATIONAL: 관계 인덱스 1-hop (Q-003, Q-010)
  └── HYBRID: 전체 통합 → 중복 제거 → importance 재정렬
```

---

## 파일 위치 안내

모든 산출물: `/Users/rocky/telegram-ai-org/docs/design/`

| 파일명 | 내용 |
|--------|------|
| `storage-innovation-erd.md` | ERD + 엔티티 상세 + 인덱스 맵 |
| `metadata-hierarchy-diagram.md` | 메타데이터 6그룹 계층 트리 |
| `storage-retrieval-wireframe.md` | 저장/조회/크론 3개 흐름 와이어프레임 |
| `design-color-legend.md` | 색상 팔레트 + WCAG 준수 사항 |
| `design-package-summary.md` | 현재 문서 (통합 요약) |

---

*관련 문서: PRD `docs/PRD-storage-architecture-innovation.md`*
*개발팀 구현 착수 시: `core/memory_index.py` Phase 1 구현 요청 → @aiorg_engineering_bot*
