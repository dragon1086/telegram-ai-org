# Index Structure Specification

**문서 ID**: DESIGN-IDX-2026-03-22-001
**작성일**: 2026-03-22
**작성자**: aiorg_engineering_bot
**Phase**: 2

---

## 1. 인덱스 파일 구성 개요

```
memory/
├── index.json                 # 전체 노드 인덱스 (Map<id, NodeMetadata>)
├── relations_graph.json       # 관계 그래프 (인접 리스트)
├── tags_index.json            # 태그별 역인덱스 (Map<tag_key, id[]>)
├── type_index.json            # 타입별 역인덱스 (Map<type, id[]>)
└── search/
    └── keyword_index.json     # 키워드 역인덱스 (Map<keyword, id[]>)
```

---

## 2. index.json — 전체 노드 인덱스

### 2.1 자료구조

```
Map<node_id: string, NodeIndexEntry>
```

### 2.2 NodeIndexEntry 필드

인덱스 엔트리는 전체 frontmatter를 저장하되, `body`(본문)은 제외한다.
본문이 필요할 때만 file_path를 통해 실제 .md 파일을 읽는다.

```json
// index.json 예시
{
  "version": "1.0.0",
  "built_at": "2026-03-22T12:00:00Z",
  "total_nodes": 142,
  "nodes": {
    "TASK-20260322-a1b2c3": {
      "id": "TASK-20260322-a1b2c3",
      "title": "SharedMemory 캐시 레이어 구현",
      "type": "task",
      "importance": "HIGH",
      "status": "completed",
      "org": "engineering",
      "file_path": "memory/tasks/T-260.md",
      "created_at": "2026-03-22T09:00:00Z",
      "updated_at": "2026-03-22T12:30:00Z",
      "valid_until": null,
      "tags": [
        {"namespace": "domain", "value": "memory"},
        {"namespace": "tech", "value": "python"}
      ],
      "summary": "SharedMemory 캐시 레이어 구현 태스크. 12개 테스트 PASS.",
      "keywords": ["SharedMemory", "캐시", "LRU", "python"],
      "relations": [
        {"target_id": "PRD-20260320-x9y8z7", "relation_type": "implements", "strength": 1.0},
        {"target_id": "RETRO-20260319-91k2m3", "relation_type": "triggers", "strength": 0.9}
      ],
      "meta_generated_by": "gemini-2.5-flash",
      "meta_confidence": 0.87,
      "vector_id": null
    }
  }
}
```

### 2.3 설계 결정: 전체 메타데이터 vs 경량 메타데이터

**결정**: 인덱스에 전체 frontmatter 저장 (본문 제외)

- 이유: 대부분의 쿼리(필터링, 관계 탐색)는 메타데이터만으로 충분
- 본문 로드는 lazy loading — 실제로 요구될 때만 file_path 통해 읽기
- 인덱스 파일 예상 크기: 노드 1,000개 기준 약 500KB — LLM 컨텍스트 적재 가능

---

## 3. relations_graph.json — 관계 그래프 인덱스

### 3.1 자료구조: 인접 리스트 (Adjacency List)

```
{
  outgoing: Map<source_id, EdgeEntry[]>,   // 노드에서 나가는 엣지
  incoming: Map<target_id, EdgeEntry[]>,   // 노드로 들어오는 엣지
  edges: Map<edge_id, RelationEdge>        // 전체 엣지 원본
}
```

### 3.2 실제 JSON 구조

```json
{
  "version": "1.0.0",
  "built_at": "2026-03-22T12:00:00Z",
  "total_edges": 87,
  "outgoing": {
    "TASK-20260322-a1b2c3": [
      {
        "edge_id": "EDGE-a1b2c3d4e5f6",
        "target_id": "PRD-20260320-x9y8z7",
        "relation_type": "implements",
        "strength": 1.0
      },
      {
        "edge_id": "EDGE-b2c3d4e5f6a1",
        "target_id": "RETRO-20260319-91k2m3",
        "relation_type": "triggers",
        "strength": 0.9
      }
    ]
  },
  "incoming": {
    "PRD-20260320-x9y8z7": [
      {
        "edge_id": "EDGE-a1b2c3d4e5f6",
        "source_id": "TASK-20260322-a1b2c3",
        "relation_type": "implements",
        "strength": 1.0
      }
    ]
  },
  "edges": {
    "EDGE-a1b2c3d4e5f6": {
      "edge_id": "EDGE-a1b2c3d4e5f6",
      "source_id": "TASK-20260322-a1b2c3",
      "target_id": "PRD-20260320-x9y8z7",
      "relation_type": "implements",
      "strength": 1.0,
      "direction": "unidirectional",
      "created_at": "2026-03-22T12:00:00Z",
      "created_by": "llm-auto",
      "valid_until": null,
      "context": null
    }
  }
}
```

### 3.3 인접 리스트를 선택한 이유

| 대안 | 특성 | 기각 이유 |
|------|------|----------|
| 인접 행렬 | O(1) 조회 | 노드 N²의 공간 — 희소 그래프에 비효율 |
| 인접 리스트 | O(degree) 조회 | **채택** — 메모리 효율, JSON 직렬화 자연스러움 |
| 엣지 리스트만 | O(E) 조회 | 특정 노드의 이웃 탐색 시 O(E) 선형 스캔 필요 |

outgoing + incoming 양방향 인덱스를 유지함으로써 "이 노드가 참조하는 것"과 "이 노드를 참조하는 것" 모두 O(degree)에 조회 가능.

---

## 4. 역인덱스 구조

### 4.1 tags_index.json

```json
{
  "built_at": "2026-03-22T12:00:00Z",
  "index": {
    "domain:memory": ["TASK-20260322-a1b2c3", "MEM-20260320-d4e5f6"],
    "tech:python": ["TASK-20260322-a1b2c3", "TASK-20260318-g7h8i9"],
    "org:engineering": ["TASK-20260322-a1b2c3"]
  }
}
```

### 4.2 type_index.json

```json
{
  "built_at": "2026-03-22T12:00:00Z",
  "index": {
    "task": ["TASK-20260322-a1b2c3", "TASK-20260318-g7h8i9"],
    "retro": ["RETRO-20260319-91k2m3"],
    "prd": ["PRD-20260320-x9y8z7"]
  }
}
```

---

## 5. 인덱스 빌드 로직 (Pseudocode)

```
function buildIndex(rootDir: string):
    nodes = {}
    edges = {}
    outgoing = {}
    incoming = {}
    tags_idx = {}
    type_idx = {}

    // 1. 스캔 단계
    md_files = glob(rootDir + "/**/*.md")

    // 2. 파싱 단계
    for each file in md_files:
        frontmatter = parseFrontmatter(file)
        if frontmatter is None:
            continue  // frontmatter 없는 파일 스킵

        node_id = frontmatter.id
        nodes[node_id] = frontmatter  // 본문 제외

        // 역인덱스 갱신
        for tag in frontmatter.tags:
            key = tag.namespace + ":" + tag.value
            tags_idx[key] = tags_idx.get(key, []) + [node_id]

        type_idx[frontmatter.type] = type_idx.get(frontmatter.type, []) + [node_id]

        // 3. 관계 처리
        for relation in frontmatter.relations:
            edge_id = generateEdgeId(node_id, relation.target_id)
            edge = {
                edge_id, source_id: node_id,
                target_id: relation.target_id,
                ...relation
            }
            edges[edge_id] = edge
            outgoing[node_id] = outgoing.get(node_id, []) + [edge]
            incoming[relation.target_id] = incoming.get(relation.target_id, []) + [edge]

    // 4. 저장 단계
    writeJSON("index.json", {version, built_at, nodes})
    writeJSON("relations_graph.json", {version, built_at, outgoing, incoming, edges})
    writeJSON("tags_index.json", {built_at, index: tags_idx})
    writeJSON("type_index.json", {built_at, index: type_idx})
```

---

## 6. 증분 업데이트 로직 (Incremental Update)

변경된 파일만 재파싱하여 인덱스를 부분 갱신한다.

```
function incrementalUpdate(changedFiles: string[]):
    // index.json 로드
    index = loadJSON("index.json")
    graph = loadJSON("relations_graph.json")

    for each file in changedFiles:
        frontmatter = parseFrontmatter(file)
        node_id = frontmatter.id

        // 기존 엔트리 제거 (stale 엣지 포함)
        removeNodeFromGraph(graph, node_id)

        if file.exists():
            // 신규/수정: 재추가
            index.nodes[node_id] = frontmatter
            addNodeToGraph(graph, node_id, frontmatter.relations)
        else:
            // 삭제된 파일
            delete index.nodes[node_id]

    index.built_at = now()
    saveJSON("index.json", index)
    saveJSON("relations_graph.json", graph)
```

**변경 감지 전략:**
- Option A: `inotify` / `watchfiles` 라이브러리 — 실시간 파일 시스템 이벤트
- Option B: `updated_at` 필드 비교 — 인덱스의 `updated_at` vs 파일 mtime
- **채택**: Option B (운영 단순성 우선, 스케줄 실행 또는 저장 hook에서 호출)
