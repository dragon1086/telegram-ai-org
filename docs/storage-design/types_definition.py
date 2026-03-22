"""
Storage Layer Type Definitions
telegram-ai-org 메모리 저장구조 — 공식 타입 정의

Phase 2 산출물: types_definition.py
작성일: 2026-03-22
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Literal


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class NodeType(str, Enum):
    TASK = "task"
    MEMORY = "memory"
    RETRO = "retro"
    DECISION = "decision"
    REPORT = "report"
    SKILL = "skill"
    PRD = "prd"
    RESEARCH = "research"
    WEEKLY = "weekly"
    EVAL = "eval"
    DESIGN = "design"
    CONVERSATION = "conversation"


class Importance(str, Enum):
    CORE = "CORE"       # 항상 컨텍스트 로드
    HIGH = "HIGH"       # 요청 시 로드
    MEDIUM = "MEDIUM"   # 기본값
    LOW = "LOW"         # 아카이브 수준


class NodeStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"
    DRAFT = "draft"
    DEPRECATED = "deprecated"
    IN_PROGRESS = "in-progress"
    BLOCKED = "blocked"


class RelationType(str, Enum):
    PARENT = "parent"
    CHILD = "child"
    IMPLEMENTS = "implements"
    REFERENCES = "references"
    EXTENDS = "extends"
    CONTRADICTS = "contradicts"
    TRIGGERS = "triggers"
    VALIDATES = "validates"
    SUPERSEDES = "supersedes"
    RELATED = "related"
    DEPENDS_ON = "depends_on"
    BLOCKS = "blocks"


class OrgType(str, Enum):
    ENGINEERING = "engineering"
    PRODUCT = "product"
    DESIGN = "design"
    RESEARCH = "research"
    GROWTH = "growth"
    OPS = "ops"
    PM = "pm"


class EdgeDirection(str, Enum):
    UNIDIRECTIONAL = "unidirectional"
    BIDIRECTIONAL = "bidirectional"


class EdgeCreatedBy(str, Enum):
    HUMAN = "human"
    LLM_AUTO = "llm-auto"
    SYSTEM = "system"


# ─────────────────────────────────────────────
# Core data classes
# ─────────────────────────────────────────────

@dataclass
class TagEntry:
    """Namespaced tag. E.g. domain:memory, tech:python"""
    namespace: Literal["domain", "org", "phase", "tech", "status", "custom"]
    value: str

    def key(self) -> str:
        return f"{self.namespace}:{self.value}"

    def to_dict(self) -> dict:
        return {"namespace": self.namespace, "value": self.value}


@dataclass
class RelationRef:
    """Inline relation reference stored in frontmatter"""
    target_id: str
    relation_type: RelationType
    label: str | None = None
    strength: float = 1.0  # 0.0–1.0

    def to_dict(self) -> dict:
        return {
            "target_id": self.target_id,
            "relation_type": self.relation_type.value,
            "label": self.label,
            "strength": self.strength,
        }


@dataclass
class NodeMetadata:
    """
    Single memory node metadata.
    Stored in YAML frontmatter of .md files and mirrored in index.json.
    Body content is NOT included here — load via file_path when needed.
    """
    id: str
    title: str
    type: NodeType
    file_path: str
    created_at: datetime
    updated_at: datetime

    # Optional fields with defaults
    importance: Importance = Importance.MEDIUM
    status: NodeStatus = NodeStatus.ACTIVE
    org: OrgType | None = None
    valid_until: datetime | None = None
    tags: list[TagEntry] = field(default_factory=list)
    summary: str | None = None
    keywords: list[str] = field(default_factory=list)
    relations: list[RelationRef] = field(default_factory=list)
    meta_generated_by: str | None = None
    meta_confidence: float | None = None  # 0.0–1.0
    vector_id: str | None = None

    def is_expired(self, as_of: datetime | None = None) -> bool:
        """Check if this node has passed its valid_until date."""
        if self.valid_until is None:
            return False
        check_at = as_of or datetime.utcnow()
        return check_at > self.valid_until

    def tag_keys(self) -> set[str]:
        return {t.key() for t in self.tags}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "type": self.type.value,
            "file_path": self.file_path,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "importance": self.importance.value,
            "status": self.status.value,
            "org": self.org.value if self.org else None,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "tags": [t.to_dict() for t in self.tags],
            "summary": self.summary,
            "keywords": self.keywords,
            "relations": [r.to_dict() for r in self.relations],
            "meta_generated_by": self.meta_generated_by,
            "meta_confidence": self.meta_confidence,
            "vector_id": self.vector_id,
        }


@dataclass
class RelationEdge:
    """
    Standalone relation edge — first-class entity in relations_graph.json.
    One edge is created per RelationRef in a node's frontmatter.
    """
    edge_id: str
    source_id: str
    target_id: str
    relation_type: RelationType
    created_at: datetime

    strength: float = 1.0
    direction: EdgeDirection = EdgeDirection.UNIDIRECTIONAL
    created_by: EdgeCreatedBy = EdgeCreatedBy.LLM_AUTO
    label: str | None = None
    valid_until: datetime | None = None
    context: str | None = None

    def to_dict(self) -> dict:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation_type": self.relation_type.value,
            "created_at": self.created_at.isoformat(),
            "strength": self.strength,
            "direction": self.direction.value,
            "created_by": self.created_by.value,
            "label": self.label,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "context": self.context,
        }


# ─────────────────────────────────────────────
# Index structures
# ─────────────────────────────────────────────

@dataclass
class NodeIndex:
    """In-memory representation of index.json"""
    version: str
    built_at: datetime
    nodes: dict[str, NodeMetadata] = field(default_factory=dict)

    @property
    def total_nodes(self) -> int:
        return len(self.nodes)

    def get(self, node_id: str) -> NodeMetadata | None:
        return self.nodes.get(node_id)

    def add(self, node: NodeMetadata) -> None:
        self.nodes[node.id] = node

    def remove(self, node_id: str) -> None:
        self.nodes.pop(node_id, None)


@dataclass
class OutgoingEdgeRef:
    """Lightweight edge reference stored in outgoing adjacency list"""
    edge_id: str
    target_id: str
    relation_type: RelationType
    strength: float = 1.0


@dataclass
class IncomingEdgeRef:
    """Lightweight edge reference stored in incoming adjacency list"""
    edge_id: str
    source_id: str
    relation_type: RelationType
    strength: float = 1.0


@dataclass
class RelationGraph:
    """In-memory representation of relations_graph.json"""
    version: str
    built_at: datetime
    outgoing: dict[str, list[OutgoingEdgeRef]] = field(default_factory=dict)
    incoming: dict[str, list[IncomingEdgeRef]] = field(default_factory=dict)
    edges: dict[str, RelationEdge] = field(default_factory=dict)

    @property
    def total_edges(self) -> int:
        return len(self.edges)

    def add_edge(self, edge: RelationEdge) -> None:
        self.edges[edge.edge_id] = edge

        out_ref = OutgoingEdgeRef(
            edge_id=edge.edge_id,
            target_id=edge.target_id,
            relation_type=edge.relation_type,
            strength=edge.strength,
        )
        self.outgoing.setdefault(edge.source_id, []).append(out_ref)

        in_ref = IncomingEdgeRef(
            edge_id=edge.edge_id,
            source_id=edge.source_id,
            relation_type=edge.relation_type,
            strength=edge.strength,
        )
        self.incoming.setdefault(edge.target_id, []).append(in_ref)

    def remove_node_edges(self, node_id: str) -> None:
        """노드 삭제 시 해당 노드의 모든 엣지를 그래프에서 제거"""
        # outgoing 엣지 제거
        for out_ref in self.outgoing.pop(node_id, []):
            self.edges.pop(out_ref.edge_id, None)
            # incoming 반대쪽 정리
            if out_ref.target_id in self.incoming:
                self.incoming[out_ref.target_id] = [
                    r for r in self.incoming[out_ref.target_id]
                    if r.edge_id != out_ref.edge_id
                ]

        # incoming 엣지 제거
        for in_ref in self.incoming.pop(node_id, []):
            self.edges.pop(in_ref.edge_id, None)
            # outgoing 반대쪽 정리
            if in_ref.source_id in self.outgoing:
                self.outgoing[in_ref.source_id] = [
                    r for r in self.outgoing[in_ref.source_id]
                    if r.edge_id != in_ref.edge_id
                ]


# ─────────────────────────────────────────────
# Traversal result
# ─────────────────────────────────────────────

@dataclass
class TraversalResult:
    """Output of traverse_graph()"""
    nodes: dict[str, NodeMetadata]
    edges: list[RelationEdge]
    depth_map: dict[str, int]          # node_id → depth from start
    cycles_detected: list[str]         # node IDs where cycles were found

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def has_cycles(self) -> bool:
        return len(self.cycles_detected) > 0

    def nodes_at_depth(self, depth: int) -> list[NodeMetadata]:
        ids = [nid for nid, d in self.depth_map.items() if d == depth]
        return [self.nodes[nid] for nid in ids if nid in self.nodes]


# ─────────────────────────────────────────────
# Tag & Type index
# ─────────────────────────────────────────────

@dataclass
class TagIndex:
    """In-memory representation of tags_index.json"""
    built_at: datetime
    index: dict[str, list[str]] = field(default_factory=dict)  # tag_key → [node_id]

    def get_nodes(self, namespace: str, value: str) -> list[str]:
        return self.index.get(f"{namespace}:{value}", [])

    def add(self, tag_key: str, node_id: str) -> None:
        self.index.setdefault(tag_key, [])
        if node_id not in self.index[tag_key]:
            self.index[tag_key].append(node_id)

    def remove_node(self, node_id: str) -> None:
        for key in self.index:
            self.index[key] = [nid for nid in self.index[key] if nid != node_id]


@dataclass
class TypeIndex:
    """In-memory representation of type_index.json"""
    built_at: datetime
    index: dict[str, list[str]] = field(default_factory=dict)  # type → [node_id]

    def get_nodes(self, node_type: str) -> list[str]:
        return self.index.get(node_type, [])
