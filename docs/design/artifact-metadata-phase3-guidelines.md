---
id: DESIGN-20260322-art003
title: "봇 산출물 메타데이터 인덱싱 — Phase 3: 검토 및 가이드라인 문서화"
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
schema_version: "artifact/v1.0"
relations:
  - target_id: DESIGN-20260322-art002
    relation_type: depends_on
    label: "Phase 2 스키마 기반"
---

# Phase 3: 검토 및 가이드라인 문서화

**Task ID**: T-aiorg_pm_bot-280
**작성 조직**: design (aiorg_design_bot)
**기준일**: 2026-03-22

---

## 1. 샘플 적용 검증 결과서

실제 존재하는 산출물 3종에 Phase 2 스키마를 직접 적용하여 유효성을 검증한다.

### 샘플 A: 보고서 (report)
**파일**: `reports/coding_agent_market_2026_03.md`

```yaml
---
id: "ART-20260322-rep001"
title: "Coding Agent 시장 분석 2026-03"
type: report
status: completed
org: research
schema_version: "artifact/v1.0"
created_at: "2026-03-22T00:00:00Z"
updated_at: "2026-03-22T00:00:00Z"
valid_until: "2026-06-22T00:00:00Z"  # 시장 보고서 3개월 유효
task_id: "T-aiorg_research_bot-unknown"
summary: |
  2026년 3월 기준 Coding Agent 시장 동향 분석 보고서.
  주요 플레이어, 시장 규모, 기술 트렌드를 조사하여
  자체 AI org 포지셔닝 전략 수립을 위한 기초 자료 제공.
key_entities:
  - name: "Coding Agent"
    type: concept
  - name: "GitHub Copilot"
    type: concept
  - name: "Claude Code"
    type: concept
    context: "주요 벤치마크 대상"
key_decisions: []  # 보고서 유형 = 의사결정 없음, 사실 기술
tags:
  - namespace: domain
    value: market-research
  - namespace: org
    value: research
  - namespace: phase
    value: analysis
priority: P2
meta_generated_by: "claude-sonnet-4-5"
meta_confidence: 0.88
---
```

**검증 결과**: ✅ 통과
- `key_decisions: []` 허용 필요 → 보고서 유형은 decisions 선택 필드로 확정
- `valid_until` 시장 보고서 TTL 패턴 확인됨 → 권장 TTL 가이드 추가 필요

---

### 샘플 B: 설계문서 (design_doc)
**파일**: `docs/storage-design/implementation_design_doc.md`

```yaml
---
id: "ART-20260322-des001"
title: "Storage Architecture Implementation Design"
type: design_doc
status: completed
org: engineering
schema_version: "artifact/v1.0"
created_at: "2026-03-22T00:00:00Z"
updated_at: "2026-03-22T00:00:00Z"
valid_until: null
task_id: "T-aiorg_engineering_bot-storage"
summary: |
  메모리 노드 기반 저장 아키텍처 구현 설계문서.
  blk-1 구조를 채택하여 YAML frontmatter + artifact_index.yaml
  이중 저장 방식을 정의한다.
key_entities:
  - name: "blk-1"
    type: concept
    context: "채택된 저장 아키텍처 블록"
  - name: "artifact_index.yaml"
    type: file
  - name: "MemoryNode"
    type: schema
  - name: "ProjectMemory"
    type: component
key_decisions:
  - decision: "YAML Frontmatter + artifact_index.yaml 이중 저장 채택"
    rationale: "단일 파일 원칙 + 빠른 인덱스 조회 병행"
    decided_by: "aiorg_engineering_bot"
    status: confirmed
  - decision: "valid_until 필드 필수화"
    rationale: "TTL 기반 자동 아카이빙으로 인덱스 크기 관리"
    decided_by: "aiorg_design_bot"
    status: confirmed
tags:
  - namespace: domain
    value: memory
  - namespace: domain
    value: storage
  - namespace: org
    value: engineering
priority: P1
meta_generated_by: "claude-sonnet-4-5"
meta_confidence: 0.95
---
```

**검증 결과**: ✅ 통과
- `key_decisions` 다중 항목 정상 처리
- `decided_by` 필드에 조직명 사용 — 가이드에 "조직 봇 ID 또는 사용자명" 명시 필요

---

### 샘플 C: 코드리뷰 (code_review)
**파일**: (인라인 태스크 결과, 별도 파일 없음 → 가상 파일 생성 케이스)

```yaml
---
id: "ART-20260322-cr001"
title: "core/telegram_relay.py 코드리뷰 — notify_task_done ACK 구현"
type: code_review
status: completed
org: engineering
schema_version: "artifact/v1.0"
created_at: "2026-03-22T00:00:00Z"
updated_at: "2026-03-22T00:00:00Z"
valid_until: "2026-06-22T00:00:00Z"  # 코드리뷰 3개월 후 archived
task_id: "T-aiorg_engineering_bot-259"
summary: |
  notify_task_done() 자동 호출 구현에 대한 코드 리뷰.
  telegram_relay.py의 _handle_pm_done_event 경로와
  핀메시지 경로 두 가지를 검토. 27/27 테스트 통과 확인.
key_entities:
  - name: "notify_task_done"
    type: component
    context: "ACK 자동 호출 구현 대상 함수"
  - name: "_handle_pm_done_event"
    type: component
  - name: "core/telegram_relay.py"
    type: file
key_decisions:
  - decision: "asyncio.ensure_future로 비동기 호출 처리"
    rationale: "이벤트 루프 블로킹 방지"
    decided_by: "aiorg_engineering_bot"
    status: confirmed
tags:
  - namespace: domain
    value: code-quality
  - namespace: org
    value: engineering
  - namespace: tech
    value: python
  - namespace: tech
    value: asyncio
priority: P1
meta_generated_by: "claude-sonnet-4-5"
meta_confidence: 0.91
---
```

**검증 결과**: ⚠️ 부분 통과 — 이슈 발견
- **이슈 1**: 코드리뷰는 별도 파일 없이 채팅 내 인라인으로 존재하는 경우 많음
  → **해결**: `file_path`가 없는 경우 `inline_content` 필드(최대 2000자)로 대체 허용
- **이슈 2**: `files_reviewed` 같은 코드리뷰 전용 필드가 공통 스키마에 없음
  → **해결**: `artifact_type_meta` 확장 필드로 유형별 추가 메타데이터 허용

---

### 1.4 발견된 이슈 및 스키마 보완

| 이슈 | 유형 | 해결 방법 |
|------|------|-----------|
| `key_decisions: []` 허용 여부 불명확 | 모호한 필드 정의 | `key_decisions` 선택(optional) 필드로 명시 |
| 인라인 산출물(파일 없음) 처리 | 누락 필드 케이스 | `file_path` nullable, `inline_content` 대안 필드 추가 |
| 유형별 전용 필드 필요 | 스키마 확장성 | `artifact_type_meta: {}` 자유형 객체 필드 추가 |
| `valid_until` 기본값 부재 | 모호한 기본값 | 유형별 권장 TTL 가이드 추가 (§3 참조) |
| `decided_by` 형식 불통일 | retrieval 충돌 케이스 | 조직 봇 ID 또는 slack username 형식 명시 |

---

## 2. 최종 확정 스키마 문서

Phase 1~2 결과 + 검증 이슈 반영 최종본.

### 2.1 필수 필드 (required)

```yaml
id:            string    # ART-{YYYYMMDD}-{6자해시}
title:         string    # 최대 200자
type:          enum      # report|design_doc|prd|code_review|retro|weekly|analysis|skill_doc|eval
status:        enum      # draft|in-progress|completed|archived|deprecated
org:           enum      # engineering|product|design|research|growth|ops|pm
schema_version: string   # "artifact/v1.0"
created_at:    datetime  # ISO 8601
updated_at:    datetime  # ISO 8601
task_id:       string    # T-{org}-{숫자} 형식
summary:       string    # 최대 500자, LLM 자동 생성
meta_generated_by: string
meta_confidence:   float  # 0.0~1.0
```

### 2.2 선택 필드 (optional)

```yaml
valid_until:     datetime | null   # null = 만료 없음
file_path:       string | null     # null 허용 (인라인 산출물)
inline_content:  string | null     # file_path null 시 대안, 최대 2000자
task_phase:      string            # "Phase 1", "Phase 2" 등 멀티페이즈용
priority:        enum              # P0|P1|P2|P3
key_entities:    object[]          # 생략 가능 (빈 배열 허용)
key_decisions:   object[]          # 생략 가능 (빈 배열 허용)
tags:            object[]          # 생략 가능
relations:       object[]          # 타 노드 참조
keywords:        string[]          # BM25용 키워드 (최대 20개)
vector_id:       string | null     # 벡터 DB ID
artifact_type_meta: object         # 유형별 자유형 확장 메타데이터
```

### 2.3 artifact_type_meta 예시 (유형별 확장)

```yaml
# code_review 전용
artifact_type_meta:
  files_reviewed: ["core/telegram_relay.py", "tests/test_relay.py"]
  severity_counts: {critical: 0, major: 1, minor: 3}
  test_pass_rate: 1.0

# report 전용
artifact_type_meta:
  data_sources: ["내부 실험", "공개 논문", "GitHub 트렌드"]
  period: "2026-01 ~ 2026-03"

# eval 전용
artifact_type_meta:
  suite_name: "e2e_session_20260319"
  test_count: 27
  pass_rate: 1.0
```

---

## 3. 스키마 적용 가이드라인

### 3.1 write-time 저장 트리거 — 확정 결정

**채택**: **T-1 (봇 응답 완료 직후)** + T-3 (주 1회 크론 보완)

**구현 지점**: `core/pm_orchestrator.py` → `notify_task_done()` 호출 직후

```python
# 의사코드 (실제 구현은 engineering_bot 담당)
async def notify_task_done(task_id, result, artifacts):
    # 기존 로직 ...

    # 산출물 인덱싱 후크 (추가)
    for artifact_path in artifacts:
        await artifact_indexer.index(
            file_path=artifact_path,
            task_id=task_id,
            trigger="bot_response_complete"
        )
```

### 3.2 유형별 권장 TTL (valid_until)

| 유형 | 권장 TTL | 근거 |
|------|---------|------|
| `report` | 90일 | 시장 데이터 유효기간 |
| `design_doc` | null (무기한) | 설계 결정은 취소 전까지 유효 |
| `prd` | null | PRD는 제품 존재 동안 유효 |
| `code_review` | 90일 | 코드 변경 후 의미 퇴색 |
| `retro` | null | 회고 기록은 영구 보존 |
| `weekly` | 365일 | 연간 아카이브 |
| `eval` | 180일 | 테스트 기준 변경 주기 |
| `analysis` | 180일 | 분석 데이터 유효기간 |

### 3.3 LLM 메타데이터 추출 프롬프트 패턴

```
다음 봇 산출물을 읽고 YAML 형식의 메타데이터를 추출하라.

[산출물 내용]
{artifact_content}

추출 항목:
1. summary: 한 문단 요약 (최대 500자)
2. key_entities: 핵심 명사/개체 (최대 10개, name/type/context 포함)
3. key_decisions: 확정된 의사결정 (결정 없으면 빈 배열)
4. keywords: BM25 검색용 키워드 (최대 20개)

규칙:
- 사실만 추출, 추론 금지
- key_decisions.status = "confirmed" | "proposed"만 허용
- 한국어 산출물은 한국어로 추출
```

### 3.4 기존 파일 마이그레이션 절차

1. `docs/`, `reports/` 내 기존 .md 파일 순회
2. frontmatter 없는 파일 탐지
3. LLM으로 메타데이터 자동 추출
4. frontmatter 자동 prepend (content 무변경)
5. `artifact_index.yaml` 항목 추가

---

## 4. 버전 관리 정책서

### 4.1 스키마 버전 필드

```yaml
schema_version: "artifact/v1.0"
# 형식: {스키마명}/{major}.{minor}
```

### 4.2 버전 업그레이드 기준

| 변경 유형 | 버전 변경 | 예시 |
|-----------|-----------|------|
| 필수 필드 추가 | Major up (v1 → v2) | `org` 필드를 required로 변경 |
| 선택 필드 추가 | Minor up (v1.0 → v1.1) | `artifact_type_meta` 추가 |
| 필드 타입 변경 | Major up | `priority` int → enum |
| 필드 제거 | Major up | deprecated 필드 제거 |
| enum 값 추가 | Minor up | type에 `presentation` 추가 |
| enum 값 제거 | Major up | breaking change |

### 4.3 하위 호환성 원칙

1. **Minor 버전**: 이전 버전 파일 파싱 가능 보장 (추가 필드는 무시)
2. **Major 버전**: 마이그레이션 스크립트 필수 제공
3. **Deprecated 필드**: 2 minor 버전 동안 유지 후 제거
4. **index 파일**: `artifact_index/v1.0` 별도 버전 관리

### 4.4 버전 호환성 매트릭스

```
artifact/v1.0  ──▶  artifact/v1.1  ──▶  artifact/v2.0
    │                    │                    │
    ▼                    ▼                    ▼
 현재 스키마         선택 필드 확장        Breaking Change
 (이 문서)          (하위 호환 O)         (마이그레이션 필요)
```

---

## 5. 전체 구현 체크리스트

| 항목 | 담당 | 우선순위 |
|------|------|---------|
| `artifact_index.yaml` 초기 생성 스크립트 | engineering | P1 |
| `notify_task_done()` 후 인덱싱 후크 삽입 | engineering | P1 |
| LLM 메타데이터 추출 모듈 | engineering | P1 |
| 기존 파일 마이그레이션 스크립트 | engineering | P2 |
| `ArtifactIndex.search()` retrieval 구현 | engineering | P1 |
| `build_context()` 산출물 인덱스 통합 | engineering | P2 |
| T-3 크론 보완 스캔 잡 등록 | ops | P2 |
| 유효기간(valid_until) 아카이빙 크론 | ops | P3 |

---

## 산출물 요약

- **샘플 적용 검증 결과서** ✅ (§1: 보고서·설계문서·코드리뷰 3종 검증)
- **최종 확정 스키마 문서** ✅ (§2: 필수/선택 필드 + artifact_type_meta)
- **스키마 적용 가이드라인** ✅ (§3: 트리거 확정·TTL·LLM 프롬프트·마이그레이션)
- **버전 관리 정책서** ✅ (§4: 버전 기준·하위 호환 원칙)
