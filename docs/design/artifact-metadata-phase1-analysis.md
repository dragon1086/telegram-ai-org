---
id: DESIGN-20260322-art001
title: "봇 산출물 메타데이터 인덱싱 — Phase 1: 요구사항 분석 및 엔티티 정의"
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
  - target_id: DESIGN-20260322-art002
    relation_type: triggers
    label: "Phase 1 → Phase 2"
---

# Phase 1: 스키마 요구사항 분석 및 엔티티 정의

**Task ID**: T-aiorg_pm_bot-280
**작성 조직**: design (aiorg_design_bot)
**기준일**: 2026-03-22

---

## 1. 봇 산출물 유형 전수 조사

기존 `reports/`, `docs/`, `skills/` 디렉토리 및 실제 봇 운용 패턴을 기반으로 산출물 유형을 분류한다.

### 1.1 산출물 유형별 필드 목록표

| 유형 코드 | 예시 파일 | 주 생산 조직 | 고유 필드 |
|-----------|-----------|-------------|-----------|
| `report` | `reports/coding_agent_market_2026_03.md` | research, growth | `data_sources[]`, `period` |
| `design_doc` | `docs/storage-design/implementation_design_doc.md` | design, engineering | `components[]`, `wireframe_ref` |
| `prd` | `docs/PRD-storage-architecture-innovation.md` | product | `requirements[]`, `acceptance_criteria[]` |
| `code_review` | (이슈 태스크 내 인라인) | engineering | `files_reviewed[]`, `severity_counts` |
| `retro` | `docs/retros/` | pm | `went_well[]`, `went_wrong[]`, `action_items[]` |
| `weekly` | `docs/weekly/` | pm | `week_number`, `metrics{}` |
| `analysis` | `docs/multibot_group_chat_gap_analysis.md` | research, product | `scope`, `findings[]` |
| `skill_doc` | `skills/*/README.md` | engineering | `trigger_phrases[]`, `skill_id` |
| `eval` | `evals/` | engineering | `test_count`, `pass_rate`, `suite_name` |

### 1.2 공통 핵심 필드 (모든 유형 공유)

#### Key Entities 축
| 필드명 | 타입 | 설명 | 필수 |
|--------|------|------|------|
| `author_org` | `string` | 산출물을 생성한 조직 봇 ID | ✅ |
| `task_id` | `string` | 연관 태스크 ID (T-xxx 형식) | ✅ |
| `generated_at` | `datetime` | 봇 응답 완료 시각 (ISO 8601) | ✅ |
| `artifact_type` | `enum` | 위 유형 코드 중 하나 | ✅ |
| `file_path` | `string` | 프로젝트 루트 기준 상대 경로 | ✅ |
| `summary` | `string(max 500)` | LLM 자동 생성 한 문단 요약 | ✅ |
| `key_entities` | `object[]` | 산출물 내 핵심 명사/개체 | ✅ |
| `meta_generated_by` | `string` | 메타데이터 추출 모델명 | ✅ |
| `meta_confidence` | `float[0,1]` | 추출 신뢰도 | ✅ |

**key_entities 항목 구조**:
```yaml
key_entities:
  - name: "MemoryNode"       # 개체명
    type: "schema"           # schema | component | model | file | person | concept | metric
    context: "핵심 저장 단위" # 선택, 최대 100자
```

#### Decisions 축
| 필드명 | 타입 | 설명 | 필수 |
|--------|------|------|------|
| `key_decisions` | `object[]` | 산출물에서 확정된 의사결정 목록 | 조건부 |
| `decisions[].decision` | `string` | 결정 내용 (최대 200자) | ✅ |
| `decisions[].rationale` | `string` | 결정 근거 (최대 300자) | 권장 |
| `decisions[].decided_by` | `string` | 결정한 조직/사람 | 권장 |
| `decisions[].status` | `enum` | `confirmed` \| `proposed` \| `superseded` | ✅ |

#### Tags 축
| 필드명 | 타입 | 설명 | 필수 |
|--------|------|------|------|
| `tags[].namespace` | `enum` | `domain` \| `org` \| `phase` \| `tech` \| `priority` \| `status` | ✅ |
| `tags[].value` | `string(max 64)` | 태그 값 | ✅ |
| `priority` | `enum` | `P0` \| `P1` \| `P2` \| `P3` | 권장 |
| `schema_version` | `string` | 스키마 버전 (`artifact/v1.0`) | ✅ |

---

## 2. write-time 저장 트리거 시점 비교 분석

### 2.1 후보 시점 목록

| 시점 ID | 트리거 이벤트 | 구현 위치 |
|---------|-------------|-----------|
| **T-1** | 봇 응답 완료 직후 (PM 합성 후) | `pm_orchestrator.py` → `notify_task_done()` 호출 직후 |
| **T-2** | 사용자 확인(ACK) 수신 후 | `telegram_relay.py` → 사용자 리액션/답장 감지 후 |
| **T-3** | 크론 배치 (주기적 스캔) | 크론 잡, 파일시스템 diff 기반 |
| **T-4** | 파일 시스템 이벤트 (watchdog) | `watchdog` 라이브러리, 파일 생성/수정 감지 |

### 2.2 트리거 시점 비교 분석

| 항목 | T-1 (봇 응답 직후) | T-2 (사용자 ACK 후) | T-3 (크론 배치) | T-4 (FS watchdog) |
|------|------------------|--------------------|-----------------|--------------------|
| **실시간성** | ✅ 즉시 | 🟡 수초~수분 지연 | ❌ 배치 주기만큼 지연 | ✅ 즉시 |
| **정확성** | 🟡 실패 산출물도 인덱싱 가능 | ✅ 사용자 확인된 산출물만 | 🟡 파일 존재 여부 기준 | 🟡 파일 쓰기 완료 기준 |
| **구현 복잡도** | ✅ 낮음 (기존 콜백 활용) | 🟡 중간 (ACK 감지 로직 추가) | ✅ 낮음 (단순 스캔) | 🔴 높음 (OS별 차이, 데몬 관리) |
| **누락 위험** | ✅ 없음 | 🟡 있음 (ACK 없으면 미저장) | 🟡 있음 (배치 전 삭제 시) | ✅ 없음 |
| **기존 코드 통합** | ✅ 용이 (`notify_task_done` 후크) | 🟡 복잡 (채팅 이벤트 리스닝) | ✅ 용이 (scheduler.py 활용) | 🔴 신규 데몬 필요 |
| **비용** | ✅ 1회/산출물 | ✅ 1회/산출물 | 🟡 전체 스캔 비용 | ✅ 1회/변경 |
| **재시도 처리** | ✅ 태스크 이벤트와 연동 가능 | 🟡 타임아웃 필요 | ✅ 다음 배치에서 자동 커버 | 🔴 별도 큐 필요 |

### 2.3 권장 결정

> **T-1 (봇 응답 완료 직후) 채택 권장**

근거:
1. `notify_task_done()` 이미 존재 → 최소 코드 추가로 인덱싱 후크 삽입 가능
2. 누락 없이 전수 인덱싱 가능 (실패 산출물은 `status: failed` 태그로 구별)
3. 이벤트 기반 1회 처리 → 실시간 성능 영향 없음
4. T-3 크론은 **T-1 실패 시 복구 보완재**로 병행 운용 (주 1회 스캔)

---

## 산출물 요약

- **산출물 유형별 필드 목록표** ✅ (위 §1.1~1.2)
- **트리거 시점 비교 분석서** ✅ (위 §2)
- **권장 트리거**: T-1 (봇 응답 완료 직후) + T-3 (주 1회 크론 보완)
