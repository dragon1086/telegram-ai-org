# Implementation Readiness Checklist

**문서 ID**: DESIGN-CHK-2026-03-22-001
**작성일**: 2026-03-22
**목적**: 실제 코드 구현 진입 전 확인 체크리스트

---

## 1. 설계 완료 확인 (Design Gates)

- [x] **G1** JSON Schema 정의 완료 (`metadata_schema.json`)
  - 필수 필드 6개, 선택 필드 9개 정의
  - `$defs/RelationRef` 공유 정의 완료
- [x] **G2** 관계 스키마 정의 완료 (`relation_schema.json`)
  - 12종 relation_type enum 정의
  - 각 타입의 semantic guide 문서화
- [x] **G3** 스키마 채택 방식 결정 완료 (`schema_design_decision.md`)
  - Frontmatter 방식 채택, 근거 문서화
  - 마이그레이션 전략 명시
- [x] **G4** 인덱스 구조 설계 완료 (`index_structure_spec.md`)
  - 4개 인덱스 파일 자료구조 정의
  - 인덱스 빌드 pseudocode 작성
  - 증분 업데이트 로직 설계
- [x] **G5** 관계 탐색 함수 설계 완료 (`relation_traversal_design.md`)
  - `get_children`, `get_references`, `traverse_graph` 인터페이스 정의
  - 순환 참조 방지 전략 (visited set) 명시
  - `query_nodes` 다차원 필터 인터페이스 정의
- [x] **G6** Python 타입 정의 완료 (`types_definition.py`)
  - 모든 Enum, dataclass 정의 완료
  - `NodeIndex`, `RelationGraph`, `TraversalResult` 완료
- [x] **G7** 데이터 흐름도 작성 완료 (`data_flow_diagram.md`)
  - Mermaid 다이어그램 (전체 흐름)
  - ASCII 다이어그램 (저장/조회/LLM 생성 3종)

---

## 2. 구현 진입 조건 (Implementation Prerequisites)

### 2.1 환경 조건
- [ ] **PRE-1** `python-frontmatter>=1.1.0` pyproject.toml에 추가
- [ ] **PRE-2** `jsonschema>=4.21.0` pyproject.toml에 추가
- [ ] **PRE-3** `memory/` 디렉토리 존재 확인 (또는 생성)
- [ ] **PRE-4** 기존 `.md` 파일 중 frontmatter 있는 파일 목록 파악 (`grep -rl "^---" memory/`)

### 2.2 설계 검토
- [ ] **PRE-5** Rocky 또는 PM의 설계 검토 및 승인
  - 관계 타입 12종이 실제 사용 케이스를 커버하는지 확인
  - `importance` 4단계 (CORE/HIGH/MEDIUM/LOW) 기준 명확화 필요
- [ ] **PRE-6** `id` 포맷 결정 확정
  - 현재 설계: `{TYPE_PREFIX}-{YYYYMMDD}-{6-char-hash}`
  - 기존 태스크 ID (`T-260`, `T-273`)와의 호환 전략 결정 필요
  - 옵션 A: 기존 ID를 `id` 필드에 그대로 사용 (패턴 검증 완화)
  - 옵션 B: 새 형식으로 마이그레이션 후 alias 필드 추가

---

## 3. 구현 순서 (Implementation Order)

```
Step 1: types_definition.py → core/에 배치, import 확인
        └── 의존성: 없음 (순수 타입 정의)

Step 2: core/frontmatter_parser.py
        └── 의존성: python-frontmatter, jsonschema, types_definition
        └── 테스트: tests/test_frontmatter_parser.py

Step 3: core/memory_index.py (IndexBuilder + query_nodes)
        └── 의존성: frontmatter_parser
        └── 테스트: tests/test_memory_index.py

Step 4: core/relation_graph.py (GraphBuilder + traversal)
        └── 의존성: memory_index
        └── 테스트: tests/test_relation_graph.py

Step 5: scripts/migrate_add_frontmatter.py
        └── 의존성: frontmatter_parser, metadata_generator
        └── --dry-run 필수 지원

Step 6: core/metadata_generator.py (LLM 자동 생성)
        └── 의존성: Gemini API / Claude API
        └── 마지막에 추가 (옵션)
```

---

## 4. 테스트 커버리지 목표

| 컴포넌트 | 최소 커버리지 | 핵심 테스트 케이스 |
|----------|-------------|------------------|
| `FrontmatterParser` | 90% | frontmatter 없음, 필수 필드 누락, 잘못된 id 포맷 |
| `MetadataValidator` | 85% | 정상 케이스, schema violation, additional properties |
| `IndexBuilder` | 85% | 신규 빌드, 증분 업데이트, 삭제 파일 처리 |
| `GraphBuilder` | 85% | 엣지 추가/삭제, dangling reference, bidirectional |
| `traverse_graph` | 90% | BFS/DFS, 순환 참조, max_depth, 빈 그래프 |
| `query_nodes` | 85% | 필터 조합, 정렬, 빈 결과 |

---

## 5. 미확정 사항 (Blockers for Full Implementation)

| ID | 사항 | 우선순위 | 결정 필요자 |
|----|------|----------|------------|
| BLK-1 | 기존 `T-260`, `T-273` 등 ID 포맷 호환 전략 | P0 | Rocky / PM |
| BLK-2 | `memory/` 디렉토리 vs 기존 `docs/` 내 파일 분산 — 통합 여부 | P1 | Rocky |
| BLK-3 | 인덱스 빌드 트리거 시점 — 크론(주기적) vs 저장 시 즉시 | P1 | PM/Eng |
| BLK-4 | LLM 메타데이터 생성 모델 선택 — Gemini Flash vs Claude Haiku | P2 | Rocky |
| BLK-5 | `valid_until` 만료 노드 자동 처리 크론 포함 여부 | P2 | PM |

---

## 6. 완료 기준 (Done Criteria)

구현이 완료되었다고 볼 수 있는 기준:

- [ ] 기존 `.md` 파일 100% frontmatter 마이그레이션 완료
- [ ] `index.json` 정상 생성 및 전체 노드 수 확인
- [ ] `relations_graph.json` 정상 생성 및 엣지 수 0 이상
- [ ] `traverse_graph("TASK-T260", depth=3)` 정상 동작 확인
- [ ] `query_nodes(type="task", importance=["HIGH","CORE"])` 정상 동작
- [ ] 전체 테스트 suite PASS (`pytest tests/ -v`)
- [ ] 순환 참조 감지 테스트 케이스 PASS
- [ ] 마이그레이션 스크립트 `--dry-run` + 실제 실행 모두 검증
