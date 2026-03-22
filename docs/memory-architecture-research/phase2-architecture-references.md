---
title: Phase 2 — 주요 아키텍처 접근법 레퍼런스 조사
type: research
project: telegram-ai-org
date: 2026-03-22
author: aiorg_research_bot (PM)
tags: [memory, architecture, vector-db, graph-db, json-ld, tagging, phase2]
---

# Phase 2: 주요 아키텍처 접근법 레퍼런스 조사

---

## 접근법 A: 벡터 DB — 임베딩 기반 의미 검색

### 개요
벡터 DB는 텍스트를 수치 벡터(임베딩)로 변환하여 저장하고, 쿼리 시 코사인 유사도 등으로 가장 의미론적으로 가까운 항목을 검색한다. 키워드 매칭 없이도 동의어·관련 개념 검색이 가능하다.

### 주요 솔루션

| 솔루션 | 특징 | 운영 방식 | 로컬 지원 |
|--------|------|---------|---------|
| **Chroma** | 개발자 친화, 인메모리/파일 모드 | OSS, 로컬 우선 | ✅ 완벽 |
| **Qdrant** | 고성능 OSS, 필터링 강력 | OSS/클라우드 | ✅ Docker |
| **Weaviate** | 그래프 구조 + 벡터 하이브리드 | OSS/클라우드 | ✅ Docker |
| **Pinecone** | 관리형 SaaS, 프로덕션 안정성 | 클라우드 전용 | ❌ |

### AI 에이전트 메모리 적용 사례

**사례 1: Mem0 (mem0ai/mem0)**
- 벡터 DB + 그래프 DB 하이브리드로 에이전트 장기 메모리 구현
- Chroma/Qdrant를 벡터 저장 레이어로 사용
- 67.13% LLM-as-a-Judge 점수 (LOCOMO 벤치마크), p95 검색 latency 0.2초
- 토큰 사용량 91% 절감 (전체 컨텍스트 로드 대비)
- 참조: https://github.com/mem0ai/mem0

**사례 2: LangChain ConversationVectorStoreRetrieverMemory**
- Chroma를 백엔드로 대화 히스토리의 의미 검색 구현
- `from langchain.memory import VectorStoreRetrieverMemory` 단 3줄로 통합
- 로컬 LLM(Ollama)과 Chroma 조합으로 완전 오프라인 운영 가능
- 참조: https://fast.io/resources/best-vector-databases-ai-agents/

### 핵심 패턴
```
저장 시: 텍스트 → embedding model → 벡터 + 원문 + 메타데이터 → 벡터DB
검색 시: 쿼리 → embedding → 코사인 유사도 top-K → 원문 반환
```

### 한계
- 정확한 사실 조회에는 취약 (날짜, 버전 등 구조적 데이터)
- 임베딩 모델 의존성 — 모델 교체 시 재색인 필요
- 관계 표현 불가 (A가 B를 구현함 등)
- Chroma 기준 100만 벡터 이상에서 성능 저하

---

## 접근법 B: 그래프 DB — 노드/엣지 기반 관계 표현

### 개요
그래프 DB는 개체(노드)와 관계(엣지)로 데이터를 저장한다. "태스크 T-260 → 구현함 → SharedMemory 캐시", "SharedMemory → 사용함 → context.db" 같은 복잡한 관계망을 자연스럽게 표현한다.

### 주요 솔루션

| 솔루션 | 특징 | 운영 방식 | 로컬 지원 |
|--------|------|---------|---------|
| **Neo4j** | 가장 성숙한 그래프 DB, Cypher 쿼리 | OSS/Enterprise | ✅ |
| **ArangoDB** | 멀티 모델(문서+그래프+키값) | OSS/클라우드 | ✅ |
| **Dgraph** | 분산 그래프 DB, GraphQL | OSS/클라우드 | ✅ |
| **NetworkX** (Python) | 인메모리 그래프, 경량 | 라이브러리 | ✅ 완벽 |

### AI 에이전트 메모리 적용 사례

**사례 1: Graphiti — Zep AI의 시간적 지식 그래프 (★★★★★)**
- 실시간 대화/JSON 데이터를 Neo4j 기반 지식 그래프로 변환
- **bi-temporal 모델**: "사건 발생 시간" + "시스템 수집 시간" 이중 타임스탬프
- 충돌 지식 감지 시 시간 메타데이터로 자동 업데이트/무효화 (삭제 않음)
- 시맨틱 + 키워드 + 그래프 트래버설 복합 검색
- 참조: https://github.com/getzep/graphiti

**사례 2: neo4j-labs/agent-memory**
- 단기(대화) / 장기(사실/선호) / 추론(reasoning trace) 3계층 그래프 메모리
- MCP(Model Context Protocol) 통합으로 Claude 직접 연결 가능
- 참조: https://github.com/neo4j-labs/agent-memory

### 핵심 패턴 (Graphiti 기반)
```
노드: Episode(대화), Entity(봇/프로젝트/태스크), Fact(사실)
엣지: IMPLEMENTS, REFERENCES, CONTRADICTS, VALID_FROM/VALID_TO
쿼리: 의미 검색 → 관련 노드 → 엣지 트래버설 → 관련 사실 회수
```

### 한계
- Neo4j 운영 오버헤드 (Docker 필요, JVM 메모리)
- Cypher 학습 곡선
- 임베딩 없이는 의미 검색 불가 (그래프 단독으로는 구조 검색만)
- ArangoDB, Dgraph는 Neo4j 대비 생태계 작음

---

## 접근법 C: JSON-LD / 구조화 메타데이터

### 개요
JSON-LD(JSON for Linked Data)는 W3C 표준으로, 데이터에 "@context"(의미 정의)를 부착하여 기계가 의미를 이해할 수 있게 한다. 마크다운 파일에 YAML frontmatter로 JSON-LD 메타데이터를 삽입하는 방식이 에이전트 메모리에 유망하다.

### 마크다운 + YAML Frontmatter 패턴

```yaml
---
"@context": "https://schema.org"
"@type": "TechArticle"
id: "memory-001"
title: "SharedMemory 캐시 구현"
date_created: "2026-03-19"
date_valid_until: "2026-06-01"
author: "aiorg_engineering_bot"
tags: ["memory", "cache", "SharedMemory"]
related:
  - id: "task-T-260"
    relation: "implements"
  - id: "memory-002"
    relation: "extends"
status: "active"
importance: 9
---
# SharedMemory 캐시 구현
...본문...
```

### AI 에이전트 메모리 적용 사례

**사례 1: Markdown-LD (iunera/json-ld-markdown)**
- .md 파일 YAML frontmatter를 JSON-LD로 자동 변환
- 언어 json-ld 코드 블록 지원으로 문서 내 인라인 구조화 데이터 삽입
- 참조: https://github.com/iunera/json-ld-markdown

**사례 2: OpenAI Context Engineering / Agents SDK**
- YAML frontmatter로 task_plan.md, notes.md 구조화
- 에이전트가 파일 읽을 때 frontmatter에서 메타데이터 우선 파싱
- token count, type, interactable 등 필드 자동 생성
- 참조: https://developers.openai.com/cookbook/examples/agents_sdk/context_personalization

**사례 3: DEV Community — "Your Markdown Docs are Useless to AI"**
- 마크다운 단독은 AI가 의미를 파악하지 못함
- JSON-LD 메타헤더 추가 시 AI의 문서 이해도 및 검색 정확도 향상
- 참조: https://dev.to/ahmmrizv9/your-markdown-docs-are-useless-to-ai-lets-fix-that-with-json-ld-45i

### 핵심 패턴
```
마크다운 파일 = YAML frontmatter (구조화 메타데이터) + Markdown 본문 (자연어)
인덱서: frontmatter 파싱 → SQLite/JSON 인덱스 생성
검색: 인덱스 필터링 → 해당 파일 본문 읽기
```

### 한계
- 의미적 유사도 검색은 여전히 불가 (키워드/필터 기반)
- 스키마 정의·유지 부담 (어느 필드를 쓸지 팀 합의 필요)
- 파일 증가 시 인덱스 관리 복잡
- 관계 표현은 가능하나 graph traversal은 별도 구현 필요

---

## 접근법 D: 태그 기반 연관관계 매핑

### 개요
계층형 태그(hierarchical tags), 폴크소노미(folksonomy, 사용자 생성 자유 태그), 온톨로지 경량화(lightweight ontology)를 결합하여 유연한 분류와 연관관계 표현을 구현한다.

### 주요 패턴

**패턴 1: 계층형 태그 (Nested Tags)**
```
memory/architecture → memory/architecture/vector-db
project/telegram-ai-org → project/telegram-ai-org/phase1
```
- Obsidian, Notion 등 현대 PKM(Personal Knowledge Management) 도구의 표준
- 부모 태그 검색 시 하위 태그 자동 포함

**패턴 2: 폴크소노미 → 온톨로지 진화**
- 초기: 자유 태그 (`cache`, `redis`, `인메모리`)
- 발전: 동의어 그룹 정의 (`cache = 인메모리 = in-memory-store`)
- 성숙: 공식 온톨로지 (`MemoryType: [Cache, Persistent, Session]`)

**패턴 3: 태그 인덱스 + 역색인**
```json
{
  "tag_index": {
    "memory": ["memory-001.md", "memory-003.md", "task-260.md"],
    "cache": ["memory-001.md", "shared_memory.md"],
    "phase1": ["memory-001.md"]
  }
}
```

### AI 에이전트 적용 사례

**사례 1: AutoSchemaKG (2025)**
- LLM이 문서에서 엔티티를 추출하고 태그/스키마를 자동 생성
- schema-based + schema-free 통합 — 초기에는 자유 태그, 점차 온톨로지로 수렴
- 참조: https://arxiv.org/html/2510.20345v1

**사례 2: LKD-KGC — Lightweight Knowledge Discovery**
- 문서 요약에서 엔티티 타입을 클러스터링하여 경량 스키마 유도
- 외부 DB 없이 JSON 파일로 운영 가능
- 참조: https://arxiv.org/html/2511.05991v1

### 핵심 패턴
```
저장 시: LLM이 내용 분석 → 태그 제안 → 태그 인덱스 업데이트
검색 시: 쿼리 → 태그 확장(동의어) → 역색인 → 관련 파일 목록 → 파일 읽기
```

### 한계
- 태그 폭발 (태그가 수백 개로 증가) 관리 필요
- 동의어 관리 없이는 "cache"와 "캐시"가 분리됨
- 의미적 유사도 없음 (태그에 없는 개념은 검색 불가)
- 관계의 방향성 표현 약함 ("구현됨" vs "테스트됨" 구분 어려움)

---

## 참고 문헌 (Sources)

- [Best Vector Databases for AI Agents: 2026 Comparison | Fast.io](https://fast.io/resources/best-vector-databases-ai-agents/)
- [Graphiti: Knowledge Graph Memory for an Agentic World — Neo4j](https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/)
- [GitHub: getzep/graphiti — Real-Time Knowledge Graphs for AI Agents](https://github.com/getzep/graphiti)
- [GitHub: neo4j-labs/agent-memory](https://github.com/neo4j-labs/agent-memory)
- [Graph Memory for AI Agents (January 2026) — Mem0](https://mem0.ai/blog/graph-memory-solutions-ai-agents)
- [AI Agent Memory Systems in 2026: Mem0, Zep, Hindsight... — Medium](https://yogeshyadav.medium.com/ai-agent-memory-systems-in-2026-mem0-zep-hindsight-memvid-and-everything-in-between-compared-96e35b818da8)
- [GitHub: iunera/json-ld-markdown](https://github.com/iunera/json-ld-markdown)
- [Your Markdown Docs are Useless to AI. Let's Fix That with JSON-LD — DEV](https://dev.to/ahmmrizv9/your-markdown-docs-are-useless-to-ai-lets-fix-that-with-json-ld-45i)
- [OpenAI Context Engineering / Agents SDK](https://developers.openai.com/cookbook/examples/agents_sdk/context_personalization)
- [Ontology Learning and KGC Comparison — arXiv](https://arxiv.org/html/2511.05991v1)
- [The 6 Best AI Agent Memory Frameworks in 2026 — MachineLearningMastery](https://machinelearningmastery.com/the-6-best-ai-agent-memory-frameworks-you-should-try-in-2026/)
