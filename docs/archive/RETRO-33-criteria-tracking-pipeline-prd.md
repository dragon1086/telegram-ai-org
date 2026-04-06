# PRD: 기준 추적 파이프라인 (Criteria Tracking Pipeline)

**문서 ID**: RETRO-33-criteria-tracking-pipeline-prd
**버전**: v1.0
**작성일**: 2026-03-31
**작성자**: 기획실 (aiorg_product_bot)
**관련 태스크**: RETRO-27, RETRO-33, RETRO-36, RETRO-37
**상태**: Draft

---

## 1. 배경 및 문제 정의

### 1.1 현재 상황

2026-03-31 일일회고에서 식별된 구조적 문제:

> "리서치실이 레퍼런스를 조사하고, 기획실이 PRD를 작성하고,
> 개발실이 `block_threshold`를 코드에 하드코딩한다.
> 세 단계가 각각 따로 움직여서 기준이 바뀌어도 어디에 반영됐는지 추적이 불가능하다."

### 1.2 핵심 문제 3가지

| # | 문제 | 영향 |
|---|------|------|
| P-01 | `block_threshold` 값의 근거(레퍼런스)가 코드에 없음 | 기준 변경 시 "왜 이 값?"을 추적 불가 |
| P-02 | PRD 버전과 코드 threshold가 비동기 상태로 분리됨 | PRD v1.2 → 개발실 반영 여부 확인 불가 |
| P-03 | 레퍼런스 조사 결과가 의사결정에 실제로 반영됐는지 검증 수단 없음 | 리서치 → 기획 → 개발 연결 끊김 |

### 1.3 해결 방향

**단일 YAML(`criteria_tracking.yaml`)을 진실의 단일 소스(Single Source of Truth)로 삼아**
리서치 → 기획 → 개발 세 단계의 기준을 버전 추적한다.

---

## 2. 목표 및 성공 지표

### 2.1 목표

1. **추적 가능성**: 모든 `block_threshold` 값이 어떤 레퍼런스에서 왔고, 어떤 PRD 버전에 근거하는지 파악 가능
2. **자동 검증**: 개발실 conftest.py가 YAML에서 threshold를 읽어 자동 검증
3. **변경 이력**: `criteria_version` 필드로 버전 변경 이력 추적
4. **다부서 연동**: 운영실 알림, 성장실 대시보드, 디자인실 severity 레벨이 같은 YAML 참조

### 2.2 성공 지표

| 지표 | 현재 | 목표 |
|------|------|------|
| threshold → 레퍼런스 추적 가능 여부 | ❌ 불가 | ✅ 100% 추적 가능 |
| PRD 버전 ↔ 코드 threshold 동기화 | ❌ 수동 | ✅ YAML 단일 소스 |
| 기준 변경 시 알림 자동화 | ❌ 없음 | ✅ criteria_version 변경 감지 |
| E2E 로그에 기준 버전 기록 | ❌ 없음 | ✅ 로그 헤더 자동 삽입 |

---

## 3. 스펙: criteria_tracking.yaml

### 3.1 파일 위치

```
/telegram-ai-org/criteria_tracking.yaml
```

### 3.2 전체 스키마

```yaml
# =============================================================================
# criteria_tracking.yaml
# 리서치실 레퍼런스 → 기획실 PRD → 개발실 block_threshold 단일 추적 파일
#
# 운영 원칙:
#   - 이 파일이 모든 부서의 "기준" 단일 소스 (Single Source of Truth)
#   - threshold 변경 시 반드시 이 파일을 먼저 수정하고 PR로 리뷰
#   - criteria_version은 MAJOR.MINOR.PATCH 시맨틱 버전 사용
#     - MAJOR: 기준 방향성 전환 (리서치 재조사 필요)
#     - MINOR: PRD 정책 변경 (기획실 승인 필요)
#     - PATCH: threshold 수치 미세 조정 (개발실 자율)
# =============================================================================

metadata:
  criteria_version: "1.0.0"          # 기준 추적 버전 (시맨틱 버전)
  last_updated: "2026-03-31"
  updated_by: "aiorg_product_bot"    # 마지막 수정 주체
  prd_ref: "RETRO-exit-code-143-prevention-prd v1.0"  # 근거 PRD 문서
  research_snapshot_ref: "docs/research/retro-27-snapshot.yaml"  # 근거 레퍼런스 스냅샷
  change_reason: "RETRO-33 기준 추적 파이프라인 초기 설정"

# --- 변경 이력 (최신 순) ---
changelog:
  - version: "1.0.0"
    date: "2026-03-31"
    author: "aiorg_product_bot"
    summary: "기준 추적 파이프라인 초기 설정"
    prd_ref: "RETRO-exit-code-143-prevention-prd v1.0"
    research_refs:
      - "retro-26-reference-decision-pipeline"
      - "retro-14-analysis/research_context.yaml"

# --- 핵심 차단 기준 (block_threshold) ---
thresholds:

  exit_code_143:
    description: "SIGTERM 기반 exit code 143 차단 기준"
    block_threshold: 3               # N회 이상 동일 exit code → 파이프라인 차단
    warn_threshold: 1                # N회 이상 → 경고 알림
    unit: "occurrences"
    criteria_version: "1.0.0"       # 이 값이 확정된 기준 버전
    prd_policy_ref: "RETRO-exit-code-143-prevention-prd §2.1"
    research_basis:
      decision_weight: "criteria"   # criteria(기준확정용) | reference(참고용) | rejected(기각됨)
      refs:
        - id: "retro-26-C-04"
          title: "amp_caller.py 하드코딩 타임아웃 120s 분석"
          weight: "criteria"
        - id: "retro-26-C-01"
          title: "SDK hang watchdog CancelledError 전파"
          weight: "criteria"

  error_pattern_repeat:
    description: "반복 에러 패턴 자동 수정 차단 기준"
    block_threshold: 3
    warn_threshold: 1
    unit: "occurrences"
    lookback_days: 14
    criteria_version: "1.0.0"
    prd_policy_ref: "improvement_thresholds.yaml §error_pattern"
    research_basis:
      decision_weight: "reference"
      refs:
        - id: "improvement_thresholds_v1"
          title: "기존 improvement_thresholds.yaml 기준값"
          weight: "reference"

  task_timeout_hard:
    description: "단일 태스크 절대 타임아웃 차단 기준"
    block_threshold: 1800            # 초 (30분)
    warn_threshold: 1200             # 초 (20분)
    unit: "seconds"
    criteria_version: "1.0.0"
    prd_policy_ref: "infra-baseline.yaml §timeouts.bot_max_task_sec"
    research_basis:
      decision_weight: "criteria"
      refs:
        - id: "infra-baseline-v1.1.0"
          title: "infra-baseline.yaml bot_max_task_sec 기준"
          weight: "criteria"

# --- 부서별 연동 설정 ---
integrations:

  development:                       # 개발실 conftest.py 연동
    auto_validate: true              # conftest.py가 이 파일을 읽어 자동 검증
    validate_on: ["pytest", "pre-flight"]
    fail_on_version_mismatch: true   # criteria_version 불일치 시 테스트 실패

  operations:                        # 운영실 알림 연동 (RETRO-29)
    alert_rule_ref: "ALERT-04"
    sync_field: "block_threshold"    # 이 필드 변경 시 ALERT-04 자동 동기화
    notify_on_change: true

  growth:                            # 성장실 대시보드 연동 (RETRO-34, RETRO-35)
    experiment_log_field: "criteria_version"
    insert_change_marker: true       # 기준 변경 시 대시보드에 마커 자동 삽입

  design:                            # 디자인실 severity 연동 (RETRO-31)
    severity_mapping:
      1: "info"                      # warn_threshold 이하
      2: "warning"                   # warn ~ block 사이
      3: "critical"                  # block_threshold 이상
    token_source: "block_threshold"  # UI 컴포넌트가 이 값을 읽어 severity 결정

  research:                          # 리서치실 스냅샷 연동 (RETRO-36, RETRO-37)
    decision_weight_required: true   # 모든 research_basis.refs에 decision_weight 필수
    snapshot_on_version_change: true # criteria_version 변경 시 레퍼런스 스냅샷 자동 생성
    snapshot_path: "docs/research/criteria-snapshots/"
```

### 3.3 `criteria_version` 필드 설명

```
MAJOR.MINOR.PATCH
  │      │     └─ PATCH: threshold 수치 미세 조정 (개발실 자율, 리뷰 불요)
  │      └─────── MINOR: PRD 정책 변경 (기획실 승인 필요)
  └────────────── MAJOR: 기준 방향성 전환 (리서치 재조사 후 승인)
```

---

## 4. Prevention PRD 연동: `criteria_version` 필드 추가

기존 `docs/RETRO-exit-code-143-prevention-prd.md`에 아래 필드를 추가한다.

### 4.1 문서 헤더 추가

```markdown
**criteria_version**: 1.0.0
**criteria_tracking_ref**: criteria_tracking.yaml §thresholds.exit_code_143
```

### 4.2 정책 섹션 업데이트

기존 "2.1 정책 목표" 하단에 다음 항목 추가:

```markdown
4. **기준 추적**: 모든 `block_threshold` 값은 `criteria_tracking.yaml`에서 읽어오며,
   `criteria_version` 필드로 변경 이력을 추적한다.
   - 수치 조정 시 → `criteria_tracking.yaml` PATCH 버전 업
   - 정책 변경 시 → 기획실 승인 후 MINOR 버전 업
```

---

## 5. 구현 요구사항 (개발실 위임 스펙)

### 5.1 파일 생성

| 파일 | 역할 | 담당 |
|------|------|------|
| `criteria_tracking.yaml` | 단일 추적 YAML (본 PRD §3.2) | 개발실 (RETRO-27) |
| `tools/criteria_loader.py` | YAML 로드 + 버전 검증 유틸 | 개발실 (RETRO-27) |
| `docs/research/criteria-snapshots/` | 버전별 레퍼런스 스냅샷 저장 디렉토리 | 리서치실 (RETRO-37) |

### 5.2 `criteria_loader.py` 인터페이스

```python
class CriteriaLoader:
    def load(self, path: str = "criteria_tracking.yaml") -> dict
    def get_threshold(self, key: str) -> dict
        # 반환: {"block_threshold": N, "warn_threshold": N, "criteria_version": "x.y.z"}
    def validate_version(self, expected_version: str) -> bool
        # criteria_version 불일치 시 ValidationError 발생
    def get_research_basis(self, key: str) -> list[dict]
        # 해당 threshold의 근거 레퍼런스 목록 반환
```

### 5.3 conftest.py 연동 (RETRO-28)

```python
# conftest.py 수정 사항
import pytest
from tools.criteria_loader import CriteriaLoader

def pytest_configure(config):
    loader = CriteriaLoader()
    criteria = loader.load()
    # pre-flight 헤더에 criteria_version 자동 삽입
    config._criteria_version = criteria["metadata"]["criteria_version"]

def pytest_sessionstart(session):
    # E2E 로그 헤더에 criteria_version 출력
    print(f"[CRITERIA] version={session.config._criteria_version}")
```

### 5.4 검증 규칙

| 규칙 | 설명 |
|------|------|
| V-01 | `criteria_tracking.yaml` 없으면 pre-flight 실패 (SystemExit) |
| V-02 | `block_threshold` 값이 코드 하드코딩값과 다르면 경고 출력 |
| V-03 | `research_basis.refs`가 비어있으면 PATCH 이상 버전 업 차단 |
| V-04 | `criteria_version` 변경 시 `changelog` 섹션 업데이트 필수 |

---

## 6. 부서별 연동 요약

| 부서 | 태스크 | 연동 내용 |
|------|--------|-----------|
| **개발실** | RETRO-27, RETRO-28 | `criteria_loader.py` 구현 + conftest.py config-watch 훅 |
| **운영실** | RETRO-29, RETRO-30 | ALERT-04 ↔ `block_threshold` 자동 동기화 + E2E 로그 헤더 기록 |
| **디자인실** | RETRO-31, RETRO-32 | `block_threshold` → severity 3단계 UI 매핑 + WCAG 가이드 |
| **기획실** | RETRO-33 (본 문서) | Prevention PRD `criteria_version` 필드 추가 |
| **성장실** | RETRO-34, RETRO-35 | `experiment_log.yaml criteria_version` 필드 + 변경 마커 |
| **리서치실** | RETRO-36, RETRO-37 | `decision_weight` 필드 + 버전 변경 시 레퍼런스 스냅샷 |

---

## 7. 마일스톤

| 단계 | 완료 기준 | 담당 | 목표일 |
|------|-----------|------|--------|
| **M1** | `criteria_tracking.yaml` + `criteria_loader.py` 생성 | 개발실 | 2026-04-03 |
| **M2** | conftest.py config-watch 훅 통합 | 개발실 | 2026-04-05 |
| **M3** | Prevention PRD `criteria_version` 필드 반영 | 기획실 | 2026-04-03 |
| **M4** | 운영실 ALERT-04 자동 동기화 | 운영실 | 2026-04-07 |
| **M5** | 성장실/디자인실/리서치실 각 연동 완료 | 각 부서 | 2026-04-10 |
| **M6** | 전체 E2E 테스트 (`criteria_version` 헤더 포함) 통과 | 개발실 | 2026-04-10 |

---

## 8. 리스크 및 대응

| 리스크 | 확률 | 영향 | 대응 |
|--------|------|------|------|
| YAML 스키마 변경 시 하위 호환 파괴 | 중 | 고 | `criteria_loader.py`에 스키마 버전 검증 추가 |
| 레퍼런스 스냅샷 누락으로 추적 불가 | 중 | 중 | V-03 검증 규칙으로 배포 전 차단 |
| 부서별 연동 시점 불일치 | 고 | 중 | M1(YAML 생성) 완료 후 순차 연동 |

---

## 9. 승인 및 다음 조치

**기획실 산출물**: 본 PRD v1.0 완성 → 개발실 구현 위임 준비 완료

**즉시 위임 필요**:
1. **개발실** (RETRO-27): `criteria_tracking.yaml` 초안 생성 + `criteria_loader.py` 구현
2. **개발실** (RETRO-28): conftest.py config-watch 훅 추가

**기획실 후속**:
- Prevention PRD (`docs/RETRO-exit-code-143-prevention-prd.md`)에 `criteria_version: 1.0.0` 필드 직접 추가 (§4 참조)
