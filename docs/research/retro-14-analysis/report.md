# RETRO-14 리서치실 ACTION 완료 문서
# 조사 산출물 맥락 자동화 — 기준 완성 및 RETRO-20 연계

> **연결 태스크**: RETRO-14 (L1 Active → resolved)
> **작성일**: 2026-03-29 (최초: 2026-03-27)
> **메타데이터**: [research_context.yaml](./research_context.yaml)
> **연계 문서**: RETRO-20 최종 보고서, docs/research/research_context_schema.yaml v1.1.0

---

## 배경

2026-W12 회고에서 리서치실이 도출한 ACTION:

> **"조사 산출물에 맥락 자동화"** — 모든 리서치 결과물에 research_context.yaml을 첨부하여 조사 시점·모델 버전·인프라 버전을 추적 가능하게 한다.

이 ACTION의 발단: RETRO-08에서 `research_context_template.yaml`을 정의했으나, 실제 조사 시 **두 개 이상의 변수가 동시에 달라진 구간**에서 결과 차이의 원인을 이분할 수 없다는 한계가 드러남.

---

## ACTION 1: 모든 리서치 산출물에 research_context.yaml 표준 첨부

### 완료 기준
- [x] `docs/research_context_template.yaml` — 필드 정의 완료 (RETRO-08)
- [x] `docs/RESEARCH_STANDARDS.md` v1.1.0 — 적용 기준 문서화 완료
- [x] `docs/research/research_context_schema.yaml` v1.1.0 — 공식 스키마 정의 완료
- [x] `docs/research/retro-14-analysis/research_context.yaml` — 본 태스크에 메타데이터 첨부
- [x] `docs/research/retro-20-analysis/research_context.yaml` — RETRO-20 메타데이터 첨부

### 표준 필드 정의 (research_context.yaml)

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `research_date` | string (ISO 8601 KST) | ✅ | 조사 시작 일시 |
| `model_version` | string | ✅ | 사용 AI 모델 (예: claude-sonnet-4-5) |
| `infra_baseline_version` | string (semver) | ✅ | 조사 시점 인프라 기준선 버전 |
| `scope` | string | ✅ | 조사 범위 요약 |
| `sources` | list | ✅ | 출처 목록 (url, title, accessed_at) |
| `cross_variable_periods` | list (선택) | ☑️ | 교차 변수 구간 명시 (RETRO-20 신설) |
| `context_notes` | string | ☑️ | 이분 분석에 필요한 추가 맥락 |

---

## ACTION 2: 교차 변수 구간에서 이분 가능한 맥락 설계 추가

### 문제 → 해결

**문제**: 조사 시점(A)과 모델 버전(B)이 동시에 달라진 구간에서 결과 차이의 원인이 A인지 B인지 이분 불가.

**해결 (RETRO-20으로 후속 완료)**:
- `cross_variable_periods` 블록을 `research_context.yaml`에 추가
- 교차 변수가 없으면 `null` 또는 `[]`로 명시적 기재 — 추적 신뢰성 확보
- 교차 발생 시 기재 템플릿:

```yaml
cross_variable_periods:
  - period: "2026-03-27 ~ 2026-03-29"
    variables_changed:
      - name: model_version
        from: "gemini-2.0-flash"
        to: "claude-sonnet-4-5"
      - name: infra_baseline_version
        from: "v1.1.0"
        to: "v1.2.0"
    note: "두 변수 동시 변경 구간 — 이분 불가. 다음 조사 시 단일 변수만 변경할 것."
```

### 레퍼런스 근거 (RETRO-20 Phase 2 조사 결과)

이 설계는 업계 표준 패턴과 일치함:
- **DVC DAG** 패턴: `deps`/`outputs`로 변수 의존성을 명시적으로 선언 → 교차 구간 자동 추론
- **LangGraph TypedDict State**: reducer 함수로 상태 업데이트 이력 추적
- 두 패턴 모두 "명시적 선언이 이분의 전제"임을 시사

출처: [DVC DAG](https://dvc.org/doc/command-reference/dag) / [LangGraph State Management 2025](https://sparkco.ai/blog/mastering-langgraph-state-management-in-2025)

---

## 적용 현황

| 파일 | cross_variable_periods 적용 | 비고 |
|------|---------------------------|------|
| `docs/research/retro-14-analysis/research_context.yaml` | ✅ (교차 없음 명시) | RETRO-14 본 태스크 |
| `docs/research/retro-20-analysis/research_context.yaml` | ✅ (교차 구간 기재) | RETRO-20 후속 |
| `docs/research/research_context_schema.yaml` | ✅ (필드 스키마 정의) | v1.1.0 공식화 |

---

## 완료 선언

- **ACTION 1** (research_context.yaml 표준 첨부): ✅ 완료
- **ACTION 2** (교차 변수 구간 이분 맥락 설계): ✅ 완료 (RETRO-20으로 연계 완료)
- **RETRO-14 status**: `pending` → **`resolved`**

---

*Updated: 2026-03-29 | Model: claude-sonnet-4-5 | infra_baseline_version: v1.2.0*
*Linked: RETRO-14 (완료), RETRO-20 (완료) | See: research_context.yaml*
