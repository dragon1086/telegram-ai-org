# Schema Design Decision: Frontmatter vs. Sidecar File

**문서 ID**: DESIGN-DEC-2026-03-22-001
**작성일**: 2026-03-22
**작성자**: aiorg_engineering_bot
**상태**: 확정

---

## 1. 검토 대상 방식 비교

| 항목 | Frontmatter (YAML in .md) | Sidecar (.meta.json) |
|------|--------------------------|----------------------|
| **파일 수** | 1개 (md 내 포함) | 2개 (md + .meta.json) |
| **가독성** | 높음 — 파일 열면 바로 확인 | 낮음 — 2개 파일 관리 필요 |
| **파싱 복잡도** | 낮음 — python-frontmatter / gray-matter | 낮음 — JSON.parse |
| **기존 파일 호환** | 부분 호환 (frontmatter 없는 파일 존재) | 완전 분리 — 기존 md 변경 없음 |
| **관계 그래프 갱신** | md 파일 자체를 수정해야 함 | .meta.json만 수정, md 무변경 |
| **Git diff 가독성** | 관계 변경 시 md 파일에 노이즈 | 분리 — md는 내용 변경만 반영 |
| **LLM 자동 생성** | md 파일 rewrite 필요 | JSON만 write — 원본 훼손 없음 |
| **IDE/에디터 지원** | 옵시디언, VSCode 등 직접 지원 | 지원 없음 (별도 플러그인 필요) |
| **도구 생태계** | Jekyll, Hugo, Obsidian 표준 | 비표준, 자체 tooling 필요 |
| **Atomic rename** | 1개만 이동 | 2개 동기화 이동 필요 |
| **LLM context 효율** | md 로드 시 메타데이터 함께 로드 | 메타데이터 별도 로드 필요 |

---

## 2. 결정: **Frontmatter 방식 채택 (YAML in .md)**

### 2.1 핵심 결정 근거

**① 단일 파일 원칙 (Source of Truth 명확성)**
메모리 노드의 내용과 메타데이터가 분리될 경우, 두 파일의 동기화 실패가 silent corruption을 야기한다. 예: `.meta.json`을 git에 커밋하지 않거나, md 파일을 수동으로 복사하면서 `.meta.json`은 복사 누락.

**② LLM 호출 시 컨텍스트 효율**
LLM이 메모리를 읽을 때 frontmatter + body를 한 번의 파일 읽기로 처리. Sidecar 방식은 관련 파일 2개를 조합해야 하므로 I/O 비용 2배, 오케스트레이션 로직 복잡도 증가.

**③ 기존 마크다운 생태계 호환**
현재 `/docs`, `/memory` 내 파일 다수가 이미 YAML frontmatter를 사용 중 (예: `phase4-architecture-recommendation.md`의 `---title/type/tags---` 블록). 표준을 통일하는 방향이 마이그레이션 비용 최소화.

**④ Obsidian/도구 체인 호환**
현재 팀이 Obsidian 기반 노트 관리를 고려하고 있으며, frontmatter는 Obsidian 표준. Dataview 플러그인으로 쿼리 가능.

### 2.2 Sidecar 방식의 유일한 장점 처리

> **"기존 md 파일 내용을 건드리지 않아도 된다"**

이 장점은 **마이그레이션 스크립트**로 대응한다:
- 기존 frontmatter 없는 파일: LLM이 자동으로 frontmatter 블록 prepend
- 기존 파일은 content 변경 없이 frontmatter만 추가되므로 `git diff`는 깔끔하게 유지

---

## 3. 마이그레이션 전략

```
기존 파일 (frontmatter 없음)          마이그레이션 후
─────────────────────────────    ──────────────────────────────────
# 제목                           ---
본문 내용                         id: MEM-20260322-abc123
                                  title: "제목"
                                  type: memory
                                  created_at: "2026-03-22T00:00:00Z"
                                  updated_at: "2026-03-22T00:00:00Z"
                                  tags:
                                    - namespace: domain
                                      value: memory
                                  importance: MEDIUM
                                  status: active
                                  relations: []
                                  ---
                                  # 제목
                                  본문 내용
```

마이그레이션 스크립트: `scripts/migrate_add_frontmatter.py`
- 인자: `--dry-run` (실제 쓰기 없이 변환 결과 출력)
- 인자: `--dir` (대상 디렉토리)
- 기존 frontmatter가 있는 파일은 스킵 (idempotent)

---

## 4. 스키마 저장 위치

| 파일 | 위치 |
|------|------|
| `metadata_schema.json` | `docs/storage-design/metadata_schema.json` |
| `relation_schema.json` | `docs/storage-design/relation_schema.json` |
| YAML frontmatter 예시 템플릿 | `docs/storage-design/frontmatter_template.yaml` |

---

## 5. YAML Frontmatter 실제 예시

```yaml
---
id: TASK-20260322-a1b2c3
title: "SharedMemory 캐시 레이어 구현"
type: task
importance: HIGH
status: completed
org: engineering
file_path: memory/tasks/T-260.md
created_at: "2026-03-22T09:00:00Z"
updated_at: "2026-03-22T12:30:00Z"
valid_until: null
tags:
  - namespace: domain
    value: memory
  - namespace: tech
    value: python
  - namespace: phase
    value: phase3
summary: "SharedMemory 클래스에 인메모리 LRU 캐시 레이어를 추가하여 반복 조회 성능을 개선한 태스크. 12개 테스트 전체 PASS."
keywords: ["SharedMemory", "캐시", "LRU", "python", "성능", "context_db"]
relations:
  - target_id: PRD-20260320-x9y8z7
    relation_type: implements
    strength: 1.0
  - target_id: RETRO-20260319-91k2m3
    relation_type: triggers
    strength: 0.9
    label: "retro에서 캐시 부재 문제 제기"
meta_generated_by: gemini-2.5-flash
meta_confidence: 0.87
vector_id: null
---
```
