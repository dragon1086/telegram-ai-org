# Implementation Design Document: 메모리 저장구조 혁신

**문서 ID**: DESIGN-IMPL-2026-03-22-001
**작성일**: 2026-03-22
**작성자**: aiorg_engineering_bot
**버전**: v1.0
**상태**: 구현 준비 완료 (Ready for Implementation)

---

## 0. 핵심 결론 (TL;DR)

현재 마크다운 파일 기반 메모리는 **관계 표현 불가, 필터 불가, 시간 유효성 없음**의 3대 한계를 가진다.
이를 해결하기 위해 **YAML Frontmatter + 파일 시스템 인덱스 + 인접 리스트 그래프** 3-레이어 구조를 설계했다.

| 레이어 | 구성 요소 | 역할 |
|--------|----------|------|
| 저장 레이어 | `.md` + YAML frontmatter | Source of Truth — 내용 + 메타데이터 |
| 인덱스 레이어 | `index.json`, `relations_graph.json` | 빠른 조회용 파생 데이터 |
| 쿼리 레이어 | Python 탐색 함수 | 다차원 필터, 그래프 탐색, LLM 컨텍스트 수집 |

---

## 1. 아키텍처 개요

### 1.1 디렉토리 구조 (변경 후)

```
telegram-ai-org/
├── memory/                          # 메모리 루트
│   ├── index.json                   # [NEW] 전체 노드 인덱스
│   ├── relations_graph.json         # [NEW] 관계 그래프 인덱스
│   ├── tags_index.json              # [NEW] 태그 역인덱스
│   ├── type_index.json              # [NEW] 타입 역인덱스
│   ├── search/
│   │   └── keyword_index.json       # [NEW] 키워드 역인덱스
│   ├── tasks/                       # [기존 유지, frontmatter 추가]
│   │   ├── T-260.md
│   │   └── T-273.md
│   ├── retros/                      # [기존 유지]
│   ├── decisions/                   # [기존 유지]
│   └── weekly/                      # [기존 유지]
│
├── core/
│   ├── memory_index.py              # [NEW] IndexBuilder, query_nodes()
│   ├── relation_graph.py            # [NEW] GraphBuilder, traverse_graph()
│   ├── frontmatter_parser.py        # [NEW] FrontmatterParser
│   └── metadata_generator.py       # [NEW] LLM 메타데이터 자동 생성
│
├── scripts/
│   └── migrate_add_frontmatter.py   # [NEW] 마이그레이션 스크립트
│
└── docs/storage-design/             # [NEW] 이 설계 문서들
    ├── metadata_schema.json
    ├── relation_schema.json
    ├── schema_design_decision.md
    ├── index_structure_spec.md
    ├── relation_traversal_design.md
    ├── types_definition.py
    ├── data_flow_diagram.md
    ├── implementation_design_doc.md  ← 이 파일
    └── implementation_readiness_checklist.md
```

---

## 2. Phase 1 요약: 스키마 설계

### 2.1 채택 방식: **YAML Frontmatter** (사이드카 방식 기각)

결정 근거:
- 단일 파일 원칙 — 메타데이터와 본문의 동기화 실패 위험 제거
- LLM 컨텍스트 효율 — 1회 파일 읽기로 메타데이터 + 본문 함께 로드
- 기존 생태계 호환 — Obsidian, Jekyll, Hugo 등 표준 방식
- 기존 파일 다수 이미 frontmatter 사용 중 (마이그레이션 비용 최소)

### 2.2 핵심 메타데이터 필드 (11개 필수 + 8개 선택)

```yaml
# 필수 (required)
id: TASK-20260322-a1b2c3          # 고유 식별자 (타입+날짜+해시)
title: "..."                       # 제목
type: task                         # NodeType enum
file_path: memory/tasks/T-260.md  # 프로젝트 루트 상대 경로
created_at: "2026-03-22T09:00:00Z"
updated_at: "2026-03-22T12:30:00Z"

# 선택 (optional, 강력 권장)
importance: HIGH                   # CORE/HIGH/MEDIUM/LOW
status: completed                  # active/completed/archived/...
org: engineering                   # 생성 조직
valid_until: null                  # 유효 기간 만료일
tags:                              # 네임스페이스 태그
  - namespace: domain
    value: memory
summary: "..."                     # LLM 생성 요약
keywords: [...]                    # LLM 추출 키워드
relations:                         # 관계 배열
  - target_id: PRD-20260320-x9y8z7
    relation_type: implements
    strength: 1.0
```

### 2.3 관계 타입 12종 (enum)

| 타입 | 의미 | 사용 예 |
|------|------|---------|
| `parent` / `child` | 계층 구조 | 태스크 → 서브태스크 |
| `implements` | 구현 | 코드 → PRD 요구사항 |
| `references` | 참조 | 태스크 → 관련 문서 |
| `extends` | 확장 | v2 설계 → v1 설계 |
| `contradicts` | 모순 | 새 결정 → 기존 결정 |
| `triggers` | 촉발 | retro → 신규 태스크 |
| `validates` | 검증 | 테스트 → 구현 |
| `supersedes` | 대체 | 신규 PRD → 구버전 PRD |
| `related` | 약한 연관 | 범용 |
| `depends_on` | 의존 | A가 B 완료에 의존 |
| `blocks` | 차단 | A가 B의 진행을 막음 |

---

## 3. Phase 2 요약: 인덱싱 및 탐색

### 3.1 인덱스 구조 (4개 파일)

| 파일 | 자료구조 | 업데이트 빈도 |
|------|----------|-------------|
| `index.json` | `Map<id, NodeMetadata>` | 파일 변경 시 즉시 |
| `relations_graph.json` | 인접 리스트 (outgoing + incoming) | 파일 변경 시 즉시 |
| `tags_index.json` | `Map<tag_key, id[]>` | 인덱스 빌드 시 |
| `type_index.json` | `Map<type, id[]>` | 인덱스 빌드 시 |

### 3.2 핵심 함수 3종

```
get_children(node_id, ...)          → 직접 자식/참조 노드 목록
get_references(node_id, ...)        → 이 노드를 참조하는 노드 목록
traverse_graph(start_id, depth=5)   → BFS/DFS 서브그래프 탐색
```

### 3.3 순환 참조 방지

```python
visited: set[str] = set()   # O(1) 멤버십 체크
if node_id in visited:
    cycles_detected.append(node_id)
    continue  # 재방문 스킵
visited.add(node_id)
```

### 3.4 증분 업데이트 전략

- 변경 감지: `updated_at` 비교 (파일 mtime vs 인덱스 저장값)
- 갱신 단위: 변경된 노드 1개 + 해당 노드의 엣지만 재처리
- Atomic write: tmp 파일 → rename (corruption 방지)

---

## 4. Phase 3: 컴포넌트 간 데이터 흐름

```
[.md 파일 (frontmatter + 본문)]
          │
          ▼ python-frontmatter 파싱
[FrontmatterParser] ──실패──► [오류 로그]
          │
          ▼ JSON Schema 검증
[MetadataValidator] ──실패──► [DRAFT 상태로 저장]
          │
          ▼ RelationRef → RelationEdge 변환
[RelationExtractor]
          │
          ├───────────────────┐
          ▼                   ▼
    [IndexBuilder]     [GraphBuilder]
    index.json         relations_graph.json
    tags_index.json
    type_index.json
          │                   │
          └─────────┬─────────┘
                    ▼
          [쿼리 함수 레이어]
          query_nodes() / get_children()
          get_references() / traverse_graph()
          get_context_for_task()
                    │
                    ▼
          [LLM 에이전트 컨텍스트 주입]
```

---

## 5. TODO: 미확정 사항 및 Edge Case

### 5.1 성능 병목 우려

- **TODO-P1**: 노드 10,000개 이상 시 `index.json` 전체 메모리 적재 불가 → 페이지네이션 또는 SQLite 인덱스 레이어 필요
- **TODO-P2**: 인덱스 빌드 시 LLM 메타데이터 생성을 동기 호출하면 bulk 마이그레이션 속도 심각하게 저하 → 비동기 큐 처리 필요

### 5.2 Edge Case

- **TODO-E1**: `target_id`가 존재하지 않는 dangling reference — 현재는 warning 로그만. 향후 자동 제거 또는 dead-link 리포트 기능 추가 고려
- **TODO-E2**: 같은 파일에서 `id`가 중복 정의된 경우 — 마지막 파싱 결과로 덮어쓰기. 향후 중복 id 감지 alert 필요
- **TODO-E3**: `valid_until` 만료 시 자동 archived 처리 — 현재 쿼리 시점에서 필터링. 향후 크론 기반 자동 상태 변경 스크립트 추가 고려
- **TODO-E4**: 양방향 관계 (`direction: bidirectional`) 처리 — 현재 단방향 가정. bidirectional 엣지의 역방향 자동 생성 로직 미구현

### 5.3 LLM 메타데이터 생성

- **TODO-L1**: Gemini Flash API 비용 모니터링 — 노드 1개당 약 0.0001$ 예상. 일 100개 생성 시 월 약 $3
- **TODO-L2**: `meta_confidence < 0.6` 노드의 수동 검토 워크플로 미정의

---

## 6. 의존성 목록

```toml
# 추가 필요 패키지
python-frontmatter = "^1.1.0"   # YAML frontmatter 파싱
jsonschema = "^4.21.0"          # JSON Schema 검증
watchfiles = "^0.21.0"          # 파일 시스템 변경 감지 (선택)
```

---

## 7. 산출물 목록 (전체)

| Phase | 파일 | 상태 |
|-------|------|------|
| P1 | `metadata_schema.json` | ✅ 완료 |
| P1 | `relation_schema.json` | ✅ 완료 |
| P1 | `schema_design_decision.md` | ✅ 완료 |
| P2 | `index_structure_spec.md` | ✅ 완료 |
| P2 | `relation_traversal_design.md` | ✅ 완료 |
| P2 | `types_definition.py` | ✅ 완료 |
| P3 | `implementation_design_doc.md` | ✅ 완료 (이 파일) |
| P3 | `data_flow_diagram.md` | ✅ 완료 |
| P3 | `implementation_readiness_checklist.md` | ✅ 완료 |
