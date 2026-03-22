---
title: Phase 4 — 최적 아키텍처 권고안 및 전환 로드맵
type: research
project: telegram-ai-org
date: 2026-03-22
author: aiorg_research_bot (PM)
tags: [memory, architecture, recommendation, roadmap, phase4]
---

# Phase 4: 최적 아키텍처 권고안 및 전환 로드맵

---

## 1. 추천 아키텍처: "Progressive Memory Graph" (점진적 메모리 그래프)

### 선정 근거

Phase 1 요구사항 7개와 Phase 3 평가 결과를 종합한 결론:

> **단일 접근법은 없다. 마크다운 퍼스트 원칙을 지키면서 메타데이터→벡터→그래프 순으로 점진적으로 강화하는 3단계 하이브리드 전략을 권고한다.**

| 요구사항 | 해결 레이어 |
|---------|-----------|
| R1 관계 표현 | YAML frontmatter related[] + 장기적 그래프 DB |
| R2 다차원 필터링 | YAML frontmatter 표준화 + SQLite 메타 인덱스 |
| R3 시간 유효성 | frontmatter의 valid_until / updated_at 필드 |
| R4 시맨틱 검색 | Chroma + 로컬 임베딩 (Phase 2) |
| R5 메모리 통합 | 단일 memory/ 디렉토리 + 공통 스키마 |
| R6 자동 연결 | LLM 메타데이터 자동 생성 (저장 시 호출) |
| R7 경량 운영 | 마크다운 파일 기반 유지, 외부 API 없이 운영 |

---

## 2. 핵심 설계 원칙

### 원칙 1: 마크다운 파일은 소스 오브 트루스
모든 메모리 항목의 원본은 .md 파일이다. 벡터 DB, 그래프 DB, 인덱스는 모두 .md 파일의 파생물이며, 항상 .md에서 재생성 가능해야 한다.

### 원칙 2: 메타데이터는 AI가 생성, 인간이 검증
저장 시 경량 LLM(예: Gemini Flash, Claude Haiku)이 자동으로 tags, related, importance, type을 생성한다. 인간(Rocky)은 CORE 레벨 항목만 수동 검증한다.

### 원칙 3: 쿼리 라우팅 — 질문 유형에 따라 검색 방법 선택
```python
# 쿼리 라우터 (의사코드)
if query_is_exact_fact(query):          # "ACT-5 완료일"
    → SQLite 메타 인덱스
elif query_is_semantic(query):           # "캐시 관련 결정사항"
    → Chroma 벡터 검색
elif query_is_relational(query):         # "T-260 태스크에서 파생된 것들"
    → 관계 인덱스 (frontmatter related[])
else:
    → 모든 레이어 통합 검색
```

### 원칙 4: 단일 메모리 디렉토리
Claude Code 메모리 + MemoryManager 메모리를 하나의 `memory/` 구조로 통합한다.

---

## 3. 메타데이터 스키마 설계

### 표준 YAML Frontmatter 스키마 (모든 메모리 파일 공통)

```yaml
---
# === 식별자 ===
id: "mem-2026-03-22-001"              # 유일 ID (자동 생성)
version: "1.2"                         # 수정 버전
parent_id: null                        # 파생된 원본 메모리 ID

# === 분류 ===
type: "decision | fact | task | feedback | knowledge | rule"
domain: "engineering | design | ops | growth | strategy | meta"
scope: "global | pm | engineering | research | design | growth | ops"
importance: 9                          # 0-10 (LLM 자동 채점)
status: "active | deprecated | superseded | pending"

# === 시간 ===
created_at: "2026-03-22T12:00:00"
updated_at: "2026-03-22T15:30:00"
valid_from: "2026-03-22"
valid_until: null                      # null = 무기한 유효

# === 작성자 ===
author: "aiorg_pm_bot"
approved_by: null                      # Rocky 승인 필요 항목

# === 태그 (계층형) ===
tags:
  - "memory/architecture"
  - "project/telegram-ai-org"
  - "phase/phase4"

# === 관계 ===
related:
  - id: "task-T-260"
    relation: "implements"             # implements|references|contradicts|extends|triggers
    confidence: 0.95
  - id: "mem-2026-03-19-003"
    relation: "extends"
    confidence: 0.80

# === 검색 최적화 ===
summary: "SharedMemory 캐시 레이어 구현 - 12개 테스트 PASS"  # 1-2줄 요약 (LLM 생성)
keywords: ["SharedMemory", "cache", "context_db", "ACT-5"]   # 핵심 키워드 (LLM 추출)
embedding_updated_at: null             # 마지막 벡터 임베딩 시간
---
```

### 관계 타입 정의

| relation | 설명 | 예시 |
|---------|------|------|
| `implements` | 이 항목이 저 항목을 구현함 | 코드 → 요구사항 |
| `references` | 저 항목을 참조함 | 결정 → 근거 문서 |
| `extends` | 저 항목을 확장/심화함 | 후속 결정 → 이전 결정 |
| `contradicts` | 저 항목과 충돌함 | 새 규칙 → 구 규칙 |
| `triggers` | 이 항목이 저 항목을 발생시킴 | 버그 → 핫픽스 태스크 |
| `validated_by` | 저 항목에 의해 검증됨 | 구현 → 테스트 |

---

## 4. 메모리 저장/검색 흐름

### 저장 흐름 (자동화)
```
1. 이벤트 발생 (태스크 완료, 결정, 피드백)
2. 경량 LLM 호출:
   - 핵심 사실 추출 (summary, keywords)
   - 분류 (type, domain, importance)
   - 태그 생성 (tags)
   - 관련 항목 매핑 (related[])
3. YAML frontmatter 생성 + .md 파일 저장
4. SQLite 메타 인덱스 업데이트 (frontmatter 필드)
5. [Phase 2] Chroma 임베딩 업데이트
```

### 검색 흐름
```
1. 쿼리 수신
2. 쿼리 분석 → 라우터가 검색 방법 선택
3. [즉시] SQLite 필터: type, scope, tags, status='active'
4. [즉시] 키워드 검색: keywords 필드 + BM25
5. [Phase 2] 시맨틱: Chroma 벡터 유사도
6. 결과 병합 → 중복 제거 → importance 순 정렬
7. 유효성 체크: valid_until 초과 항목 제외
8. 상위 K개 반환 (context window 제한 준수)
```

---

## 5. 전환 로드맵 (마이그레이션 단계)

### Phase 0: 스키마 표준화 (1-2일, 즉시 착수)
**목표**: 기존 메모리 파일에 표준 YAML frontmatter 적용

| 항목 | 내용 |
|------|------|
| 대상 파일 | MEMORY.md, project_pending_tasks.md, project_skills_strategy.md, feedback_production_data.md |
| 작업 | 각 파일에 표준 frontmatter 추가 |
| 도구 | PM 봇이 LLM으로 자동 생성 → Rocky 검토 |
| 예상 공수 | 4시간 |
| 리스크 | 없음 (기존 파일 내용 변경 없음, frontmatter만 추가) |

**산출물**: 표준 frontmatter가 붙은 메모리 파일 4개

---

### Phase 1: 메타 인덱스 레이어 (3-5일)
**목표**: SQLite 기반 메타데이터 인덱스 + 관계 인덱스 구축

| 항목 | 내용 |
|------|------|
| 구현 | `core/memory_index.py` — frontmatter 파싱 → SQLite 저장 |
| DB 스키마 | memories(id, type, domain, importance, status, valid_until, summary, keywords_json, tags_json) |
| 관계 DB | memory_relations(from_id, to_id, relation, confidence) |
| 트리거 | 파일 저장 시 자동 인덱스 업데이트 (watchdog or hook) |
| 예상 공수 | 3일 |
| 리스크 | 인덱스-파일 동기화 불일치 → 주기적 재인덱싱으로 해결 |

**산출물**: 쿼리 가능한 메모리 인덱스 API

```python
# 사용 예시
index = MemoryIndex()
results = index.query(
    type="decision",
    domain="engineering",
    tags=["memory"],
    status="active",
    since="2026-03-01"
)
# → ["mem-2026-03-19-003.md", "mem-2026-03-22-001.md"]
```

---

### Phase 2: 시맨틱 검색 레이어 (1-2주)
**목표**: Chroma + 로컬 임베딩으로 시맨틱 검색 구현

| 항목 | 내용 |
|------|------|
| 벡터 DB | Chroma (로컬, 파일 기반) |
| 임베딩 모델 | nomic-embed-text (Ollama) 또는 all-MiniLM-L6-v2 (sentence-transformers) |
| 구현 | `core/memory_search.py` — 쿼리 → Chroma top-K → frontmatter 필터 병합 |
| 자동화 | 파일 저장 시 embedding job 트리거 |
| 예상 공수 | 5일 |
| 리스크 | Ollama 미설치 시 임베딩 API 필요 → 폴백으로 BM25 유지 |

**산출물**: 시맨틱 쿼리 가능한 통합 검색 API

---

### Phase 3: LLM 자동 메타데이터 생성 (2-3주)
**목표**: 태스크 완료/대화 종료 시 메모리 자동 저장

| 항목 | 내용 |
|------|------|
| 트리거 | 태스크 done 이벤트, 중요 결정 키워드 감지 |
| LLM 호출 | Gemini Flash (경량, 저비용) — 사실 추출 + 메타데이터 생성 |
| 프롬프트 | "아래 대화에서 기억할 사실을 추출하고 YAML frontmatter 형식으로 반환하라" |
| 저장 | 자동 .md 파일 생성 → 인덱스 업데이트 → 임베딩 |
| 예상 공수 | 7일 |
| 리스크 | LLM 과다 호출 비용 → 중요도 임계값(importance ≥ 6)만 저장 |

---

### Phase 4: 지식 그래프 전환 (1-3개월, 장기)
**목표**: Graphiti/Neo4j 기반 bi-temporal 지식 그래프

| 항목 | 내용 |
|------|------|
| 인프라 | Docker Compose에 Neo4j 추가 |
| 마이그레이션 | Phase 0-3 축적 데이터 → 그래프 노드/엣지 변환 |
| 기능 | 시간 유효성 자동 관리, 충돌 지식 감지, 관계 트래버설 |
| 예상 공수 | 3-4주 |
| 리스크 | Neo4j 인프라 비용, 데이터 마이그레이션 복잡성 |

---

## 6. 리스크 항목 요약

| 리스크 | 가능성 | 영향 | 대응 |
|--------|--------|------|------|
| 기존 파일 frontmatter 추가 시 Claude Code 파싱 오류 | 낮음 | 중간 | 파싱 테스트 후 적용 |
| LLM 자동 메타데이터 정확도 부족 | 중간 | 낮음 | importance 임계값 설정 + 사후 검토 |
| Chroma 임베딩 모델 교체 시 재색인 | 중간 | 낮음 | 재색인 스크립트 미리 준비 |
| 인덱스-파일 동기화 불일치 | 중간 | 중간 | 주기적 재인덱싱 크론 설정 |
| Neo4j 도입 시 인프라 복잡도 증가 | 낮음 | 높음 | Phase 4는 선택적, 충분한 검증 후 진행 |
