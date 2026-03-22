# Relation Traversal Design

**문서 ID**: DESIGN-REL-2026-03-22-001
**작성일**: 2026-03-22
**작성자**: aiorg_engineering_bot
**Phase**: 2

---

## 1. 핵심 탐색 함수 인터페이스

### 1.1 getChildren

부모 노드의 직접 자식 노드 목록을 반환한다.

```python
def get_children(
    node_id: str,
    relation_types: list[RelationType] | None = None,
    min_strength: float = 0.0,
    include_archived: bool = False
) -> list[NodeMetadata]:
    """
    Args:
        node_id: 대상 노드 ID
        relation_types: 필터할 관계 타입 목록 (None = 모든 타입)
        min_strength: 최소 엣지 강도 (0.0~1.0)
        include_archived: archived 상태 노드 포함 여부

    Returns:
        직접 연결된 outgoing 관계의 target 노드 목록

    Time complexity: O(degree(node_id))
    """
    edges = graph.outgoing.get(node_id, [])

    result = []
    for edge in edges:
        if relation_types and edge.relation_type not in relation_types:
            continue
        if edge.strength < min_strength:
            continue
        target = index.nodes.get(edge.target_id)
        if target is None:
            continue  # dangling reference — log warning
        if not include_archived and target.status == "archived":
            continue
        result.append(target)

    return result
```

### 1.2 getReferences

특정 노드를 참조하는 모든 노드(incoming edges)를 반환한다.

```python
def get_references(
    node_id: str,
    relation_types: list[RelationType] | None = None,
    min_strength: float = 0.0
) -> list[NodeMetadata]:
    """
    Args:
        node_id: 대상 노드 ID (피참조자)
        relation_types: 필터할 관계 타입 목록
        min_strength: 최소 엣지 강도

    Returns:
        이 노드를 target으로 하는 source 노드 목록

    Time complexity: O(in-degree(node_id))
    """
    edges = graph.incoming.get(node_id, [])

    result = []
    for edge in edges:
        if relation_types and edge.relation_type not in relation_types:
            continue
        if edge.strength < min_strength:
            continue
        source = index.nodes.get(edge.source_id)
        if source:
            result.append(source)

    return result
```

### 1.3 traverseGraph (BFS/DFS 범용 탐색)

그래프를 너비 우선(BFS) 또는 깊이 우선(DFS)으로 탐색한다.
순환 참조 방지를 위해 visited set을 사용한다.

```python
def traverse_graph(
    start_id: str,
    direction: Literal["outgoing", "incoming", "both"] = "outgoing",
    relation_types: list[RelationType] | None = None,
    max_depth: int = 5,
    algorithm: Literal["bfs", "dfs"] = "bfs",
    min_strength: float = 0.0
) -> TraversalResult:
    """
    Args:
        start_id: 탐색 시작 노드
        direction: 탐색 방향 (outgoing=자식방향, incoming=부모방향, both=양방향)
        relation_types: 필터할 엣지 타입
        max_depth: 최대 탐색 깊이 (순환 방지 + 성능 보호)
        algorithm: BFS(레벨별 탐색) vs DFS(깊이 우선)
        min_strength: 최소 엣지 강도 필터

    Returns:
        TraversalResult(
            nodes: dict[str, NodeMetadata],   # 발견된 노드
            edges: list[RelationEdge],         # 탐색된 엣지
            depth_map: dict[str, int],         # 노드별 시작점으로부터의 깊이
            cycles_detected: list[str]         # 순환 참조 감지된 노드 ID 목록
        )
    """

    visited: set[str] = set()         # 순환 참조 방지 핵심
    queue = deque([(start_id, 0)])    # (node_id, depth)
    result_nodes = {}
    result_edges = []
    depth_map = {start_id: 0}
    cycles = []

    while queue:
        if algorithm == "bfs":
            current_id, depth = queue.popleft()   # FIFO
        else:
            current_id, depth = queue.pop()        # LIFO (DFS)

        if current_id in visited:
            cycles.append(current_id)              # 이미 방문 = 순환 참조
            continue

        visited.add(current_id)

        node = index.nodes.get(current_id)
        if node is None:
            continue  # dangling reference
        result_nodes[current_id] = node

        if depth >= max_depth:
            continue  # 최대 깊이 초과 — 더 이상 탐색하지 않음

        # 엣지 수집
        edges_to_explore = []
        if direction in ("outgoing", "both"):
            edges_to_explore += graph.outgoing.get(current_id, [])
        if direction in ("incoming", "both"):
            edges_to_explore += graph.incoming.get(current_id, [])

        for edge in edges_to_explore:
            if relation_types and edge.relation_type not in relation_types:
                continue
            if edge.strength < min_strength:
                continue

            next_id = edge.target_id if direction == "outgoing" else edge.source_id
            if direction == "both":
                next_id = edge.target_id if edge.source_id == current_id else edge.source_id

            result_edges.append(edge)

            if next_id not in visited:
                queue.append((next_id, depth + 1))
                depth_map[next_id] = depth + 1

    return TraversalResult(
        nodes=result_nodes,
        edges=result_edges,
        depth_map=depth_map,
        cycles_detected=cycles
    )
```

---

## 2. 순환 참조 방지 전략

### 2.1 visited set 방식 (채택)

```python
visited: set[str] = set()

# 노드 방문 전:
if node_id in visited:
    log_warning(f"Cycle detected at {node_id}")
    cycles_detected.append(node_id)
    continue   # 스킵 — 재방문하지 않음

visited.add(node_id)
```

**장점:**
- O(1) 멤버십 체크
- 구현 단순
- BFS/DFS 모두 동일하게 적용

**한계:**
- 동일 노드가 여러 경로에서 도달 가능한 DAG(방향 비순환 그래프)에서는 재방문을 막지만, 진짜 순환인지 DAG의 합류인지 구분 어려움
- **대응**: `depth_map`을 활용해 같은 노드에 더 짧은 경로로 도달했으면 업데이트만 하고 재탐색은 생략

### 2.2 스키마 레벨 자가 참조 방지

```python
# 엣지 추가 시 validation
def add_relation(source_id: str, target_id: str, ...):
    if source_id == target_id:
        raise ValueError(f"Self-loop not allowed: {source_id}")
    # 직접 순환 감지: A→B→A
    if source_id in [e.target_id for e in graph.outgoing.get(target_id, [])]:
        log_warning(f"Direct cycle would be created: {source_id}↔{target_id}")
        # 금지하지 않고 경고만 — bidirectional 관계는 의도적일 수 있음
```

---

## 3. 고수준 쿼리 함수

### 3.1 getContext (LLM 컨텍스트 로딩용)

```python
def get_context_for_task(task_id: str, max_nodes: int = 10) -> list[NodeMetadata]:
    """
    태스크 실행에 필요한 관련 메모리를 우선순위 기반으로 수집.
    LLM 컨텍스트 창에 로드할 노드 목록 반환.
    """
    result = {}

    # 1. 직접 구현 대상 (PRD, 스펙)
    for node in get_children(task_id, relation_types=["implements", "references"]):
        result[node.id] = (node, 1.0)  # (노드, 우선순위)

    # 2. 유발 관계 (retro, 결정)
    for node in get_children(task_id, relation_types=["triggers"]):
        result[node.id] = (node, 0.8)

    # 3. 같은 도메인 HIGH 이상 최근 노드 (시맨틱 근접)
    task_meta = index.nodes[task_id]
    similar = query_by_tags(task_meta.tags, importance=["CORE", "HIGH"], limit=5)
    for node in similar:
        if node.id not in result:
            result[node.id] = (node, 0.6)

    # 우선순위 정렬 후 상위 max_nodes 반환
    sorted_nodes = sorted(result.values(), key=lambda x: -x[1])
    return [n for n, _ in sorted_nodes[:max_nodes]]
```

---

## 4. 필터 쿼리 인터페이스

```python
def query_nodes(
    types: list[str] | None = None,
    tags: list[dict] | None = None,           # [{namespace, value}]
    importance: list[str] | None = None,
    status: list[str] | None = None,
    org: list[str] | None = None,
    since: datetime | None = None,            # created_at >= since
    until: datetime | None = None,            # created_at <= until
    keywords: list[str] | None = None,        # OR 매칭
    limit: int = 20,
    sort_by: Literal["created_at", "updated_at", "importance"] = "updated_at",
    sort_dir: Literal["asc", "desc"] = "desc"
) -> list[NodeMetadata]:
    """
    인덱스 기반 다차원 필터 쿼리.
    벡터 검색 없이 메타데이터만으로 수행 — O(N) 최악이지만
    인덱스 총 노드 1,000개 이하에서는 충분히 빠름.
    """
    candidates = list(index.nodes.values())

    if types:
        candidates = [n for n in candidates if n.type in types]
    if importance:
        candidates = [n for n in candidates if n.importance in importance]
    if status:
        candidates = [n for n in candidates if n.status in status]
    if org:
        candidates = [n for n in candidates if n.org in org]
    if since:
        candidates = [n for n in candidates if n.created_at >= since]
    if until:
        candidates = [n for n in candidates if n.created_at <= until]
    if tags:
        def matches_tags(node):
            node_tag_keys = {f"{t.namespace}:{t.value}" for t in node.tags}
            return all(f"{t['namespace']}:{t['value']}" in node_tag_keys for t in tags)
        candidates = [n for n in candidates if matches_tags(n)]
    if keywords:
        candidates = [n for n in candidates
                      if any(kw.lower() in (n.keywords or []) for kw in keywords)]

    # 정렬
    reverse = (sort_dir == "desc")
    importance_order = {"CORE": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    if sort_by == "importance":
        candidates.sort(key=lambda n: importance_order.get(n.importance, 99), reverse=not reverse)
    else:
        candidates.sort(key=lambda n: getattr(n, sort_by, ""), reverse=reverse)

    return candidates[:limit]
```
