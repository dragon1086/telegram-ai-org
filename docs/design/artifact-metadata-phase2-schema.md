---
id: DESIGN-20260322-art002
title: "봇 산출물 메타데이터 인덱싱 — Phase 2: 스키마 구조 설계 및 포맷 정의"
type: design
status: completed
org: design
created_at: "2026-03-22T00:00:00Z"
updated_at: "2026-03-22T00:00:00Z"
tags:
  - namespace: domain
    value: memory
  - namespace: domain
    value: metadata
  - namespace: phase
    value: schema-design
relations:
  - target_id: DESIGN-20260322-art001
    relation_type: depends_on
    label: "Phase 1 결과 기반"
  - target_id: DESIGN-20260322-art003
    relation_type: triggers
    label: "Phase 2 → Phase 3"
---

# Phase 2: 스키마 구조 설계 및 포맷 정의

**Task ID**: T-aiorg_pm_bot-280
**작성 조직**: design (aiorg_design_bot)
**기준일**: 2026-03-22
**선행 결정**: blk-1 저장구조 채택, YAML Frontmatter 방식 확정 (ref: DESIGN-DEC-2026-03-22-001)

---

## 1. JSON vs YAML 포맷 비교표

> 참고: `docs/storage-design/schema_design_decision.md`에서 이미 **YAML Frontmatter 채택** 확정.
> 본 절은 산출물 인덱스 파일(`artifact_index.yaml`) 포맷 선정에 특화하여 재검토.

| 항목 | JSON | YAML |
|------|------|------|
| **가독성** | 중간 (따옴표·중괄호 다수) | ✅ 높음 (들여쓰기 기반, 주석 가능) |
| **주석 지원** | ❌ 없음 | ✅ `#` 주석 가능 |
| **기존 메모리 파일 호환** | 🟡 일부 (ProjectMemory JSON) | ✅ MemoryManager `.md` + frontmatter 표준 |
| **파싱 라이브러리** | `json` (내장) | `pyyaml` (설치 필요, 이미 deps에 포함) |
| **멀티라인 문자열** | `\n` 이스케이프 필요 | ✅ `|` 블록 스칼라 지원 |
| **배열 표현** | `["a", "b"]` | `- a\n- b` (더 읽기 쉬움) |
| **LLM 생성 친화성** | 중간 (따옴표 실수 多) | ✅ 높음 (들여쓰기 직관적) |
| **스키마 검증 도구** | jsonschema, pydantic | yamale, pydantic (YAML→dict 후) |
| **Frontmatter 표준** | ❌ 비표준 | ✅ Jekyll/Hugo/Obsidian 표준 |

**결론**: **YAML 채택** — 기존 결정과 일관, 가독성·LLM 친화성·주석 지원 우위

---

## 2. 최종 스키마 초안 (YAML Frontmatter 확장)

### 2.1 봇 산출물 파일 자체 Frontmatter (source file)

봇이 산출물 파일을 생성할 때 맨 앞에 삽입하는 YAML frontmatter:

```yaml
---
# ── 기본 식별 (MemoryNode v1.0 호환) ──────────────────────────────
id: "ART-20260322-a1b2c3"         # 형식: ART-{YYYYMMDD}-{6자 해시}
title: "봇 산출물 메타데이터 스키마 설계"
type: design_doc                   # report|design_doc|prd|code_review|retro|weekly|analysis|skill_doc|eval
status: completed                  # draft|in-progress|completed|archived|deprecated
org: design                        # 생성 조직: engineering|product|design|research|growth|ops|pm
schema_version: "artifact/v1.0"

# ── 시간 ────────────────────────────────────────────────────────────
created_at: "2026-03-22T14:30:00Z"
updated_at: "2026-03-22T14:30:00Z"
valid_until: null                  # null = 만료 없음

# ── 태스크 연결 ──────────────────────────────────────────────────────
task_id: "T-aiorg_pm_bot-280"
task_phase: "Phase 2"              # 선택, 멀티페이즈 태스크용

# ── 핵심 내용 추출 (LLM 자동 생성) ─────────────────────────────────
summary: |
  봇 산출물(보고서, 설계문서, 코드리뷰 등)에 대한 메타데이터 인덱싱
  스키마를 설계한다. key_entities / decisions / tags 세 축을 정의하고
  write-time 저장 트리거 및 retrieval 연계 방식을 확정한다.

key_entities:
  - name: "MemoryNode"
    type: schema
    context: "기존 메모리 저장 단위, 이 스키마가 확장하는 대상"
  - name: "artifact_index.yaml"
    type: file
    context: "전체 봇 산출물 인덱스 파일"
  - name: "notify_task_done"
    type: component
    context: "write-time 트리거 삽입 지점"

key_decisions:
  - decision: "YAML frontmatter 채택 (JSON 불채택)"
    rationale: "가독성, LLM 친화성, 기존 생태계 호환"
    decided_by: "aiorg_design_bot"
    status: confirmed
  - decision: "write-time trigger = T-1 (봇 응답 완료 직후)"
    rationale: "누락 없는 전수 인덱싱, 기존 notify_task_done 후크 활용"
    decided_by: "aiorg_design_bot"
    status: confirmed

# ── 태그 ────────────────────────────────────────────────────────────
tags:
  - namespace: domain
    value: memory
  - namespace: domain
    value: metadata
  - namespace: org
    value: design
  - namespace: phase
    value: schema-design
priority: P1

# ── 관계 ────────────────────────────────────────────────────────────
relations:
  - target_id: "DESIGN-DEC-2026-03-22-001"
    relation_type: extends
    label: "blk-1 저장구조 확장"
  - target_id: "T-aiorg_pm_bot-280"
    relation_type: implements
    label: "태스크 산출물"

# ── 메타데이터 품질 ──────────────────────────────────────────────────
meta_generated_by: "claude-sonnet-4-5"  # 추출 모델
meta_confidence: 0.92                    # 0.0~1.0
vector_id: null                          # 아직 임베딩 전
---
```

### 2.2 artifact_index.yaml — 전체 인덱스 파일

위치: `~/.ai-org/memory/artifact_index.yaml`

```yaml
# 봇 산출물 인덱스 — write-time 자동 갱신
# 직접 수정 금지, 스키마 버전: artifact_index/v1.0

schema_version: "artifact_index/v1.0"
last_updated: "2026-03-22T14:30:00Z"
total_count: 3

artifacts:
  - id: "ART-20260322-a1b2c3"
    title: "봇 산출물 메타데이터 스키마 설계"
    type: design_doc
    status: completed
    org: design
    task_id: "T-aiorg_pm_bot-280"
    file_path: "docs/design/artifact-metadata-phase2-schema.md"
    created_at: "2026-03-22T14:30:00Z"
    priority: P1
    # 검색용 요약 필드 (retrieval에서 직접 사용)
    summary_short: "봇 산출물 메타데이터 YAML 스키마 설계 및 artifact_index 구조 정의"
    keywords:
      - memory
      - metadata
      - schema
      - yaml
      - artifact
    key_decisions_summary:
      - "YAML frontmatter 채택"
      - "write-time trigger T-1 채택"
    key_entities_names:
      - "MemoryNode"
      - "artifact_index.yaml"
      - "notify_task_done"
    tags_flat:                   # 빠른 필터링용 플랫 배열
      - "domain:memory"
      - "domain:metadata"
      - "org:design"
      - "phase:schema-design"
```

---

## 3. 스키마 관계 다이어그램 (와이어프레임)

```
┌─────────────────────────────────────────────────────────────────────┐
│                        메모리 시스템 전체도                           │
└─────────────────────────────────────────────────────────────────────┘

  ┌─────────────┐    triggers     ┌────────────────────────┐
  │  PM 태스크   │ ──────────────▶ │  봇 산출물 파일 (.md)   │
  │ (task_id)   │                 │  [YAML Frontmatter 포함] │
  └─────────────┘                 └──────────┬─────────────┘
                                             │ write-time
                                             │ (T-1: notify_task_done 후)
                                             ▼
  ┌─────────────────────────────────────────────────────────┐
  │              artifact_index.yaml                         │
  │  (~/.ai-org/memory/artifact_index.yaml)                  │
  │                                                          │
  │  artifacts[]:                                            │
  │  ┌───────────────────────────────────────────────────┐  │
  │  │ id, title, type, status, org, task_id             │  │
  │  │ file_path ──────────────────────────────────────▶ │──┼──▶ 실제 .md 파일
  │  │ summary_short, keywords[]                         │  │
  │  │ key_decisions_summary[]                           │  │
  │  │ key_entities_names[]                              │  │
  │  │ tags_flat[]                                       │  │
  │  └───────────────────────────────────────────────────┘  │
  └─────────────────────────────────────────────────────────┘
                     │
       ┌─────────────┼──────────────┐
       │             │              │
       ▼             ▼              ▼
  ┌─────────┐  ┌──────────┐  ┌──────────────┐
  │ 태그    │  │ 엔티티   │  │ 의사결정     │
  │ 필터링  │  │ 키 조회  │  │ 키워드 검색  │
  │(tags_  │  │(key_enti │  │(BM25 +       │
  │ flat[])│  │ ties[])  │  │ summary)     │
  └─────────┘  └──────────┘  └──────────────┘
       │             │              │
       └─────────────┴──────────────┘
                     │
                     ▼
            ┌─────────────────┐
            │  MemoryManager  │
            │  build_context()│
            │  (프롬프트 주입) │
            └─────────────────┘

  ┌──────────────────────────────────────────────────┐
  │  기존 3계층 메모리 (CORE/SUMMARY/LOG .md 파일)    │
  │  ← artifact 인덱스와 별도, SUMMARY 승격 시 연동   │
  └──────────────────────────────────────────────────┘
```

### 필드 간 관계 명세

```
ArtifactIndexEntry (artifact_index.yaml의 각 항목)
├── id           ──▶ 산출물 파일 frontmatter의 id와 1:1 매핑
├── file_path    ──▶ 실제 .md 파일 위치
├── task_id      ──▶ ProjectMemory.TaskRecord.task_id와 외래키 관계
├── tags_flat[]  ──▶ "{namespace}:{value}" 형식, O(1) set 검색
├── keywords[]   ──▶ BM25 토큰화 대상
└── relations[]  ──▶ 타 ArtifactIndexEntry 또는 MemoryNode의 id 참조
```

---

## 4. Retrieval 연계 방식 정의서

### 4.1 검색 레이어 구조

| 레이어 | 방식 | 구현 | 사용 케이스 |
|--------|------|------|------------|
| L1: 태그 필터 | `tags_flat` set 교집합 | O(n) 배열 스캔 | "design 산출물 모두", "P1 이상만" |
| L2: 엔티티 키 조회 | `key_entities_names` 포함 검색 | in 연산자 | "MemoryNode 관련 산출물" |
| L3: 키워드 검색 | BM25 (기존 MemoryManager 재활용) | `rank_bm25` | "메모리 스키마 설계" |
| L4: 시맨틱 검색 | `vector_id` → vector DB 쿼리 | ChromaDB/Qdrant | 의미 기반 유사도 검색 (미래) |

### 4.2 인덱스 파일 위치 및 명명 규칙

```
~/.ai-org/memory/
├── artifact_index.yaml          ← 봇 산출물 전체 인덱스 (이 스키마)
├── {scope}.md                   ← 기존 MemoryManager 파일 (CORE/SUMMARY/LOG)
├── {project_id}.json            ← 기존 ProjectMemory 파일
└── lesson_memory.db             ← 기존 LessonMemory SQLite
```

### 4.3 산출물 파일 참조 링크 구조

```yaml
# artifact_index.yaml 내 참조
- id: "ART-20260322-a1b2c3"
  file_path: "docs/design/artifact-metadata-phase2-schema.md"  # 상대 경로
  relations:
    - target_id: "T-aiorg_pm_bot-280"
      relation_type: implements
    - target_id: "DESIGN-DEC-2026-03-22-001"
      relation_type: extends
```

### 4.4 retrieval 통합 시퀀스

```
태스크 수신
    │
    ▼
build_context(task) 호출
    │
    ├─ 1. MemoryManager.build_context() → CORE/SUMMARY/LOG
    │
    └─ 2. ArtifactIndex.search(task_keywords)
           ├─ L1 태그 필터 (org, domain)
           ├─ L2 엔티티 매칭 (key_entities_names)
           └─ L3 BM25 키워드 (summary_short + keywords)
               │
               ▼
           상위 3개 산출물 요약 → 프롬프트 주입
```

---

## 산출물 요약

- **JSON/YAML 포맷 비교표** ✅ (§1)
- **최종 스키마 초안 (YAML 채택)** ✅ (§2.1~2.2)
- **스키마 관계 다이어그램** ✅ (§3)
- **retrieval 연계 방식 정의서** ✅ (§4)
