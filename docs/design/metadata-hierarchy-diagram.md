# 메타데이터 계층 구조 다이어그램

**문서 ID**: DESIGN-2026-03-22-HIER-001
**작성일**: 2026-03-22
**작성자**: aiorg_design_bot
**버전**: v1.0
**상태**: 완성본

---

## 범례 (Legend)

```
【색상 체계】
┌──────────────────────┬──────────────────────────────────────┐
│ 색상 코드             │ 의미                                  │
├──────────────────────┼──────────────────────────────────────┤
│ ██ #2C3E50 (다크네이비)│ L0 — 루트 계층 (메모리 엔티티)        │
│ ██ #2980B9 (블루)     │ L1 — 필드 그룹 (6대 카테고리)         │
│ ██ #27AE60 (그린)     │ L2 — 개별 필드 (LLM 자동 생성)        │
│ ██ #F39C12 (앰버)     │ L2 — 개별 필드 (시스템 자동 기록)     │
│ ██ #8E44AD (퍼플)     │ L2 — 개별 필드 (사람/Rocky 입력)      │
│ ██ #E74C3C (레드)     │ L3 — 열거형 허용값                    │
│ ── 실선              │ 필수 (NOT NULL) 관계                  │
│ ┄┄ 점선              │ 선택 (nullable) 관계                  │
└──────────────────────┴──────────────────────────────────────┘
```

---

## 1. 메타데이터 6대 그룹 계층도 (트리 구조)

```
┌─────────────────────────────────────────────────────────────┐
│               MEMORY ENTITY (메모리 단위)                    │
│                     [L0 — 루트]                              │
└───────────┬──────────────────────────────────────────────────┘
            │
     ┌──────┴──────────────────────────────────────────┐
     │                                                 │
     ▼                                                 ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  🆔 식별자   │  │ 🏷 분류       │  │ ⏰ 시간       │  │ 👤 소유권    │
│  Identifiers │  │ Classification│  │ Timestamps   │  │ Ownership   │
│  [L1 그룹]  │  │  [L1 그룹]   │  │  [L1 그룹]   │  │  [L1 그룹]  │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                  │                  │
       │          ┌──────┴──────┐           │           ┌──────┴──────┐
       │          │             │           │           │             │
       ▼          ▼             ▼           ▼           ▼             ▼
┌──────────────────────┐ ┌──────────────────────┐ ┌──────────────────────┐
│  🔗 관계              │ │  🔍 검색 최적화        │                       │
│  Relations           │ │  Search              │                       │
│  [L1 그룹]           │ │  [L1 그룹]           │                       │
└──────────────────────┘ └──────────────────────┘                       │
                                                                        │
(6대 그룹 전체 트리 = 아래 상세도 참조)
```

---

## 2. 그룹별 상세 계층도

### 2.1 🆔 식별자 그룹

```
🆔 식별자 (Identifiers) [L1]
│
├── id [L2 — 시스템 자동🟧]
│     └─ 형식: "mem-{YYYY-MM-DD}-{SEQ3}"
│        ├─ YYYY: 연도 4자리
│        ├─ MM: 월 2자리
│        ├─ DD: 일 2자리
│        └─ SEQ3: 당일 시퀀스 001~999
│
├── version [L2 — 시스템 자동🟧]
│     └─ 형식: "{major}.{minor}"
│        ├─ 최초 생성: 1.0
│        └─ 수정 시: minor +1 (1.0→1.1→1.2...)
│
└── parent_id [L2 — 시스템 자동🟧] ┄┄(nullable)
      └─ FK → MEMORY.id
         └─ null이면: 독립 메모리 (루트)
         └─ 값이면: 파생 메모리 (부모 체인 추적 가능)
```

### 2.2 🏷 분류 그룹

```
🏷 분류 (Classification) [L1]
│
├── type [L2 — LLM 자동🟩] ── 필수
│     └─ 허용값 [L3] ────────────────────────────────┐
│        ├─ "decision"    → 의사결정 사항             │
│        ├─ "fact"        → 관찰된 사실/현상 (기본값) │
│        ├─ "task"        → 태스크/액션 아이템        │
│        ├─ "feedback"    → 피드백/회고              │
│        ├─ "knowledge"   → 개념/지식 기반           │
│        └─ "rule"        → 운영 규칙/정책           │
│                                                    └─ (6가지만 허용)
│
├── domain [L2 — LLM 자동🟩] ── 필수
│     └─ 허용값 [L3]
│        ├─ "engineering" → 개발, 코딩, 아키텍처
│        ├─ "design"      → UI/UX
│        ├─ "ops"         → 운영, 인프라
│        ├─ "growth"      → 마케팅, 지표
│        ├─ "strategy"    → 전략, 비즈니스
│        └─ "meta"        → 시스템 자체 (기본값)
│
├── scope [L2 — LLM 자동🟩] ── 필수
│     └─ 허용값 [L3]
│        ├─ "global"      → 전 조직 공통 (기본값)
│        ├─ "pm"          → 기획실 전용
│        ├─ "engineering" → 개발실 전용
│        ├─ "research"    → 리서치실 전용
│        ├─ "design"      → 디자인팀 전용
│        ├─ "growth"      → 그로스팀 전용
│        └─ "ops"         → 운영팀 전용
│
├── importance [L2 — LLM 자동🟩] ── 필수
│     └─ 타입: INTEGER (0-10)
│        ├─ 9-10: 프로덕션 영향 / Rocky 직접 결정
│        ├─ 7-8:  아키텍처/구조 변경
│        ├─ 5-6:  일반 기능 결정 (기본값: 5)
│        ├─ 3-4:  참고 사항
│        ├─ 0-2:  임시/일회성
│        └─ ⚠️ 임계값: importance ≥ 6만 자동 저장
│
└── status [L2 — 시스템 자동🟧] ── 필수
      └─ 허용값 [L3] ── 상태 전환 다이어그램
         ┌─────────────────────────────────┐
         │  [pending] ──→ [active]         │
         │      ↓              ↓           │
         │      └──────→ [deprecated]      │
         │                    ↓            │
         │              [superseded]       │
         └─────────────────────────────────┘
         ※ "superseded" 시 superseded_by 필드 필수
```

### 2.3 ⏰ 시간 그룹

```
⏰ 시간 (Timestamps) [L1]
│
├── created_at [L2 — 시스템 자동🟧] ── 필수
│     └─ ISO 8601 형식 / 불변 (수정 불가)
│
├── updated_at [L2 — 시스템 자동🟧] ── 필수
│     └─ ISO 8601 형식 / 수정 시 자동 갱신
│
├── valid_from [L2 — 시스템 자동🟧]
│     └─ YYYY-MM-DD 형식 / 기본값: created_at의 날짜
│
└── valid_until [L2 — 시스템 자동🟧] ┄┄(nullable)
      └─ YYYY-MM-DD 형식 또는 null
         ├─ null = 무기한 유효
         └─ ⚠️ 크론 자동 처리:
              매일 자정 → valid_until 초과 항목
              → status: deprecated 자동 전환
```

### 2.4 👤 소유권 그룹

```
👤 소유권 (Ownership) [L1]
│
├── author [L2 — 시스템 자동🟧] ── 필수
│     └─ FK → BOT_AGENT.agent_id
│        ├─ 불변 (최초 작성자, 이후 수정 불가)
│        └─ 예: "aiorg_pm_bot", "aiorg_design_bot"
│
├── approved_by [L2 — 사람 입력🟣] ┄┄(nullable)
│     └─ "rocky" 또는 null
│        └─ ⚠️ 승인 규칙: importance ≥ 9 → Rocky 검토 권장
│
└── contributors [L2 — 시스템 추가🟧] ┄┄(선택)
      └─ JSON array
         └─ 내용 수정 시 기여자 추가 + version minor++
```

### 2.5 🔗 관계 그룹

```
🔗 관계 (Relations) [L1]
│
└── related[] [L2 — LLM 자동🟩] ── 배열 (0~N개)
      │
      └─ 각 항목 구조:
         ├── id [L3]           → 연결 대상 ID
         │     ├─ "mem-{date}-{seq}"  : 다른 메모리
         │     └─ "task-T-{number}"   : 태스크
         │
         ├── relation [L3]     → 관계 타입
         │     ├─ "implements"   → A가 B를 구현함      (A→B)
         │     ├─ "references"   → A가 B를 참조함      (A→B)
         │     ├─ "extends"      → A가 B를 확장/심화함 (A→B)
         │     ├─ "contradicts"  → A가 B와 충돌함      (A↔B)
         │     ├─ "triggers"     → A가 B를 발생시킴    (A→B)
         │     └─ "validated_by" → A가 B에 의해 검증됨 (A←B)
         │
         └── confidence [L3]   → 0.0~1.0 (LLM 채점)
               ├─ ≥ 0.8: 고신뢰 관계 (자동 연결)
               ├─ 0.5~0.8: 보통 (표시 후 검토 권장)
               └─ < 0.5: 미검증 참조 (경고 표시)
```

### 2.6 🔍 검색 최적화 그룹

```
🔍 검색 최적화 (Search) [L1]
│
├── summary [L2 — LLM 자동🟩] ┄┄(선택)
│     └─ 1-2줄 핵심 요약
│        └─ FTS5 인덱싱 대상
│
├── keywords [L2 — LLM 자동🟩] ┄┄(선택)
│     └─ JSON array — 핵심 키워드 목록
│        ├─ BM25 검색 대상
│        └─ 예: ["cache", "SharedMemory", "context_db"]
│
└── embedding_updated_at [L2 — 시스템 자동🟧] ┄┄(nullable)
      └─ null = 아직 임베딩 안 됨
         └─ Phase 2 이후 → Chroma 벡터 생성 시 기록
```

---

## 3. 태그(Tags) 계층 구조

```
태그 계층 구조 (최대 depth 3)
══════════════════════════════════════════════

  예약 카테고리 (L1 — 고정)
  │
  ├── memory/
  │     ├── memory/architecture
  │     ├── memory/schema
  │     └── memory/search
  │
  ├── project/
  │     ├── project/telegram-ai-org
  │     └── project/ai-org-v2
  │
  ├── phase/
  │     ├── phase/phase0
  │     ├── phase/phase1
  │     ├── phase/phase2
  │     └── phase/phase3
  │
  ├── org/
  │     ├── org/engineering
  │     ├── org/design
  │     ├── org/pm
  │     └── org/ops
  │
  └── task/
        ├── task/T-260
        ├── task/T-272
        └── task/T-xxx

  사용자 정의 태그 (L1 자유형)
  └── {custom}/{subcategory}/{detail}
        └─ depth 3까지만 허용
```

---

## 4. 메타데이터 입력 주체별 분류표

| 그룹 | 필드 | 입력 주체 | 시점 |
|------|------|---------|------|
| 식별자 | `id`, `version`, `parent_id` | 시스템 자동 | 저장 시 |
| 분류 | `type`, `domain`, `importance` | **LLM 자동** (Gemini Flash) | 저장 시 |
| 분류 | `scope`, `status` | 시스템 자동 | 저장 시 / 크론 |
| 시간 | `created_at`, `updated_at` | 시스템 자동 | 저장/수정 시 |
| 시간 | `valid_from`, `valid_until` | LLM 제안 + 사람 검토 | 저장 시 |
| 소유권 | `author` | 시스템 자동 | 저장 시 |
| 소유권 | `approved_by` | **Rocky (사람)** | 검토 시 |
| 소유권 | `contributors` | 시스템 자동 | 수정 시 |
| 관계 | `related[]` | **LLM 자동** | 저장 시 |
| 검색 | `summary`, `keywords` | **LLM 자동** | 저장 시 |
| 검색 | `embedding_updated_at` | 시스템 자동 | Phase 2 이후 |

---

*다음 문서: [storage-retrieval-wireframe.md](storage-retrieval-wireframe.md)*
