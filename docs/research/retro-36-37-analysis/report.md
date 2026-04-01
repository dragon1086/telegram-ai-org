# RETRO-36/37 리서치실 분석 보고서
## decision_weight 필드 설계 + criteria_version 스냅샷 구조

**문서 ID**: retro-36-37-analysis
**작성일**: 2026-03-31
**작성자**: 리서치실 / aiorg_research_bot
**관련 태스크**: RETRO-36, RETRO-37
**관련 파일**:
- `criteria_tracking.yaml` (리서치실 섹션 보강)
- `docs/research/criteria-snapshots/v1.0.0-snapshot.yaml` (RETRO-37 산출물)
- `docs/research/research_context_schema.yaml` v1.2.0 (RETRO-36 산출물)

---

## 1. 핵심 결론

**리서치 → 기획 → 개발 파이프라인에서 리서치실의 역할은 두 가지로 명확화된다:**

1. **RETRO-36**: 모든 레퍼런스를 `criteria / reference / rejected` 3단계로 분류 → `criteria_tracking.yaml`이 레퍼런스 신뢰도를 즉시 판별 가능
2. **RETRO-37**: `criteria_version` 변경 시 해당 시점의 레퍼런스 목록을 불변 스냅샷으로 고정 → 기준 회귀 분석 시 "왜 그 값이었나"를 즉시 재현 가능

---

## 2. 레퍼런스 분석 (RETRO-36 — decision_weight 설계 근거)

### 2.1 유사 시스템 비교 (출처 기반)

| 시스템 | 레퍼런스 분류 방식 | 기준 확정 방식 | 리서치실 반영 |
|--------|------------------|--------------|-------------|
| **ADR (Arch Decision Records)** | Accepted / Proposed / Superseded | 단일 결정 문서 | decision_weight=criteria 분류 체계 |
| **RFC Process** (IETF/Rust) | Informational / Standards Track / Experimental | 커뮤니티 투표 후 확정 | rejected 항목 보존 원칙 |
| **Google Design Docs** | Required / Recommended / Optional | 설계자 판단 | rationale 필드 필수화 |
| **Amazon Working Backwards** | Primary / Supporting / Rejected | 역방향 설계 검증 | criteria/reference/rejected 3분류 |
| **기존 retro-14 research_context** | data_sources 목록 (분류 없음) | — | v1.2.0에서 decision_weight 추가 |

**핵심 인사이트**: 상위 4개 시스템 모두 "채택/미채택" 이분법보다 **3단계 이상 분류** (채택·참고·기각) 를 사용한다. 기각 레퍼런스를 남기는 이유는 "같은 논의를 반복하지 않기 위함"으로 일관된다.

### 2.2 3분류 체계 확정 근거

```
criteria  — 기준 확정용 (threshold 값에 직접 반영됨)
reference — 참고용 (맥락 이해, threshold 미반영)
rejected  — 기각됨 (검토 후 미채택, 사유 필수 기재)
```

**criteria vs reference 구분 기준**:
- criteria: "이 레퍼런스 없이는 해당 threshold 값을 설명할 수 없다"
- reference: "알면 도움이 되지만, 없어도 threshold 값 자체는 유지된다"

**rejected를 보존하는 이유**:
- "왜 이 값을 쓰지 않았나"를 미래에 재검토할 수 있어야 함
- 동일 레퍼런스를 반복 검토하는 비용 제거

---

## 3. 스냅샷 구조 설계 (RETRO-37 — 버전별 레퍼런스 고정 근거)

### 3.1 스냅샷 필요성

| 시나리오 | 스냅샷 없을 때 | 스냅샷 있을 때 |
|---------|-------------|-------------|
| "block_threshold=3은 왜?" | criteria_tracking.yaml refs 추적 + 레퍼런스 문서 탐색 필요 | v1.0.0-snapshot.yaml에서 즉시 확인 |
| "v1.0.0 → v1.1.0 변경 내용?" | changelog만 존재, 레퍼런스 diff 불가 | 두 스냅샷 비교로 추가/변경/삭제 즉시 파악 |
| "기준 v0.9.x 시절 근거 재현?" | 이미 덮어쓰여 불가 | v0.9.x-snapshot.yaml에서 재현 |

### 3.2 불변성(Immutable) 원칙

스냅샷 파일은 **한 번 커밋 후 수정 금지**. 이유:
- 레퍼런스 소급 수정 방지 (기준 변경 시 새 버전 스냅샷 생성)
- git 이력으로 변경 시점 추적 가능
- 운영실 ALERT-04 알림과 연동 시 "어느 버전에서 경고가 발생했나" 재현 가능

### 3.3 스냅샷 생성 트리거

```
criteria_tracking.yaml의 metadata.criteria_version 변경
    ↓
docs/research/criteria-snapshots/v{new_version}-snapshot.yaml 생성
    ↓
기존 스냅샷 복사 후 변경된 threshold 항목만 업데이트
    ↓
criteria_tracking.yaml의 metadata.research_snapshot_ref 경로 업데이트
```

---

## 4. 산출물 목록

| 파일 | 태스크 | 상태 |
|------|--------|------|
| `criteria_tracking.yaml` | RETRO-36/37 | ✅ 보강 완료 (decision_weight + rationale + snapshot_ref 추가) |
| `docs/research/criteria-snapshots/v1.0.0-snapshot.yaml` | RETRO-37 | ✅ 신규 생성 |
| `docs/research/research_context_schema.yaml` v1.2.0 | RETRO-36 | ✅ decision_weight 필드 추가 |

---

## 5. 다음 버전 운영 가이드

### criteria_version 1.x.0 변경 시 리서치실 체크리스트

- [ ] 변경 threshold의 `research_basis.refs` 중 신규 레퍼런스에 `decision_weight` + `rationale` 기재
- [ ] 기각된 레퍼런스는 `rejected` 분류 + 기각 사유 rationale에 기재 (누락 금지)
- [ ] `docs/research/criteria-snapshots/v{new_version}-snapshot.yaml` 생성
- [ ] `criteria_tracking.yaml`의 `metadata.research_snapshot_ref` 경로 업데이트
- [ ] `all_refs_summary` (criteria/reference/rejected 카운트) 재집계
