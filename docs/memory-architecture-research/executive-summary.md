---
title: Executive Summary — 메모리 저장 아키텍처 혁신
type: executive-summary
project: telegram-ai-org
date: 2026-03-22
author: aiorg_research_bot (PM)
tags: [memory, architecture, executive-summary]
---

# Executive Summary
## 메모리 저장 아키텍처 혁신 — 의사결정자용 요약

**작성일**: 2026-03-22 | **대상**: Rocky (의사결정자) | **작성**: aiorg_research_bot

---

## 핵심 결론 (30초 요약)

> **현재 마크다운 파일 기반 메모리는 키워드 검색과 수동 인덱싱 수준에 머물러 있다. "마크다운 파일 + 표준 메타데이터 스키마 + 시맨틱 검색 레이어"의 3단계 점진적 혁신으로 데이터 간 관계 표현, 의미론적 검색, 시간 유효성 관리를 모두 달성할 수 있다. 1단계(2일)는 지금 바로 시작 가능하다.**

---

## 현재 상태: 무엇이 문제인가

| 한계 | 실제 영향 |
|------|---------|
| 크로스-파일 관계 표현 불가 | "ACT-5가 T-260에서 파생됨"을 시스템이 모름 |
| 메타데이터 없음 → 필터 불가 | "엔지니어링 관련 결정만" 검색 불가 |
| 시간 유효성 없음 | 오래된 사실과 최신 사실 구분 불가 |
| 키워드 검색만 | "캐시"로 검색해도 "인메모리 저장소" 못 찾음 |
| 사일로 분리 | 런타임 메모리 ↔ Claude Code 메모리 단절 |

**비유**: 현재 시스템은 포스트잇을 박스에 던져 놓은 수준. 제안 시스템은 태그+관계+의미로 연결된 지식 네트워크.

---

## 권고 아키텍처: "Progressive Memory Graph"

```
[현재]  .md 파일 → 수동 인덱스(MEMORY.md) → LLM 전체 로드 → BM25 검색
    ↓
[1단계] .md 파일 + YAML 메타데이터 → SQLite 인덱스 → 필터 쿼리  (2일)
    ↓
[2단계] + Chroma 벡터 DB → 시맨틱 검색  (1-2주)
    ↓
[3단계] + LLM 자동 메타데이터 생성  (2-3주)
    ↓
[장기]  + 지식 그래프(Graphiti/Neo4j) → 관계 트래버설  (1-3개월)
```

**핵심 설계 원칙**:
1. 마크다운 파일은 소스 오브 트루스 (기존 파일 유지)
2. AI가 메타데이터 생성, 인간은 CORE 항목만 검토
3. 쿼리 유형에 따라 검색 방법 자동 라우팅

---

## 메타데이터 스키마 핵심 (사용자가 요청한 핵심)

```yaml
---
id: "mem-2026-03-22-001"
type: "decision"            # 타입: decision/fact/task/feedback/rule
domain: "engineering"       # 도메인: engineering/ops/strategy/meta
importance: 9               # 0-10, LLM 자동 채점
status: "active"            # active/deprecated/superseded
valid_until: "2026-09-01"   # 유효기간 (null=무기한)

tags:
  - "memory/architecture"
  - "project/telegram-ai-org"

related:                    # 핵심: 데이터 간 관계 표현
  - id: "task-T-260"
    relation: "implements"  # implements/references/extends/contradicts
  - id: "mem-2026-03-19-003"
    relation: "extends"

summary: "SharedMemory 캐시 구현 완료"  # LLM 자동 생성
keywords: ["cache", "SharedMemory"]      # LLM 자동 추출
---
```

**이 스키마가 핵심인 이유**: `related[]` 필드로 데이터 간 의미 있는 관계가 저장되고, `valid_until`로 시간 유효성이 관리되며, `tags`로 다차원 필터링이 가능해진다.

---

## 단계별 의사결정 포인트

| 단계 | 기간 | 승인 필요 사항 | 결과 |
|------|------|--------------|------|
| **Phase 0** (지금 시작) | 2일 | 없음 (파일 frontmatter 추가) | 메타데이터 기반 필터링 |
| **Phase 1** | 3-5일 | `core/memory_index.py` 신규 코드 | SQL 쿼리로 메모리 검색 |
| **Phase 2** | 1-2주 | Chroma 패키지 + Ollama 설치 | 시맨틱 검색 |
| **Phase 3** | 2-3주 | 경량 LLM API 비용 승인 | 자동 메모리 저장 |
| **Phase 4** | 1-3개월 | Docker Neo4j 인프라 | 완전한 지식 그래프 |

**즉시 시작 권고**: Phase 0는 기존 파일에 YAML frontmatter를 추가하는 것뿐이라 리스크 없이 바로 시작 가능하다.

---

## 참고: 업계 동향

- **Mem0** (2026): 벡터+그래프 하이브리드, 토큰 91% 절감, 검색 latency 0.2초
- **Graphiti/Zep** (2025): bi-temporal 지식 그래프, Neo4j 기반, 에이전트 메모리 표준화
- **업계 합의**: "마크다운 단독으로는 AI 에이전트 메모리로 한계" → 구조화 메타데이터 + 시맨틱 레이어가 필수

---

## 다음 액션 (PM 및 개발팀)

1. **[PM]** Phase 0 표준 frontmatter 스키마 확정 및 기존 파일 4개 업데이트
2. **[Engineering]** `core/memory_index.py` SQLite 인덱스 구현
3. **[Engineering]** Chroma + 로컬 임베딩 POC 진행
4. **[PM]** Phase 1 완료 후 검색 품질 평가 → Phase 2 시작 여부 결정

---

*상세 분석은 `docs/memory-architecture-research/` 하위 4개 문서 참조*
