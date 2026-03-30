# 디자인 환경 Pre-flight 검증 정책

> **버전**: v1.1 | **작성일**: 2026-03-29 | **관리 주체**: 디자인실 (aiorg_design_bot)
> **연동 파일**: `config/design-baseline.yaml` | **관련 태스크**: RETRO-05, RETRO-11, RETRO-17

---

## 1. 정책 목적

디자인 렌더링 환경(뷰포트/폰트/테마/컴포넌트/디자인툴) 불일치로 인한
렌더링 이상치를 **배포 전 자동으로 감지**하여, 사후 수습 비용을 제거한다.

> **핵심 원칙**: "기준은 세웠으나 변수 교차 맥락을 못 담았다" (RETRO-17 공통 반성) →
> 이 정책은 그 반성을 구조화된 자동 검증으로 전환한다.

---

## 2. Pre-flight 체크 전체 목록 (PC-D-001 ~ PC-D-016)

| ID | 대상 필드 | 조건 | 실패 동작 | 관련 WCAG |
|----|----------|------|----------|-----------|
| PC-D-001 | `viewport.default_width` | 허용값 목록 내 | **error** | — |
| PC-D-002 | `viewport.pixel_ratio` | 표준 DPR 값(1/1.5/2/3) | warn | — |
| PC-D-003 | `typography.base_font_size` | >= 14px | **error** | 1.4.4 |
| PC-D-004 | `typography.font_family_primary` | 허용값 목록 내 | warn | — |
| PC-D-005 | `theme.contrast_ratio_min` | >= 4.5 | **error** | 1.4.3 |
| PC-D-006 | `theme.wcag_level` | AA 또는 AAA | **error** | — |
| PC-D-007 | `theme.active_mode` | 허용값(light/dark/system) | **error** | — |
| PC-D-008 | `theme.focus_visible_outline` | 빈 값 절대 금지 | **error** | 2.4.7 |
| PC-D-009 | `typography.rendering_engine` | 허용값 목록 내 | warn | — |
| PC-D-010 | `theme.color_token_version` | vX.Y 형식 | warn | — |
| PC-D-011 | `typography.line_height_base` | >= 1.5 | warn | 1.4.8 |
| PC-D-012 | `theme.motion_safe` | true | warn | 2.3.3 |
| PC-D-013 | `component_library.version` | SemVer X.Y.Z 형식 | warn | — |
| PC-D-014 | `design_tools.figma.version` | 비어 있지 않음 | warn | — |
| PC-D-015 | `design_tools.storybook.version` | 비어 있지 않음 | warn | — |
| PC-D-016 | `retry_policy.max_retries` | 1~5 범위 | warn | — |

> **error**: pre-flight 실패 → 렌더링/배포 파이프라인 즉시 중단 + retry_policy 적용
> **warn**: 경고 로그 출력 후 계속 진행 (3회 연속 시 에스컬레이션)

---

## 3. 교차 참조 검증 (CROSS-REF, RETRO-17 구현)

토큰이 여러 컨텍스트에 걸쳐 사용될 때 버전 일치 여부를 추적한다.

| 교차 참조 ID | 소스 필드 | 대상 필드 | 규칙 | 위반 시 동작 |
|-------------|----------|----------|------|------------|
| CROSS-REF-001 | `infra_baseline_version` | `theme.color_token_version` | 인프라 업그레이드 시 토큰 버전 검토 필요 | warn + 담당자 알림 |
| CROSS-REF-002 | `component_library.version` | `design_tools.figma.plugin_required[Tokens Studio]` | 컴포넌트 업그레이드 시 플러그인 호환성 확인 | warn |
| CROSS-REF-003 | `theme.color_token_version` | `component_library.token_schema_version` | 두 값 반드시 일치 | warn + abort if mismatch |

---

## 4. 자동 취소·재시도 정책 (retry_policy, RETRO-11 구현)

### 4-1. 기본 설정

| 항목 | 값 |
|------|-----|
| max_retries | 2 |
| retry_delay_seconds | 30 |
| backoff_strategy | linear |

### 4-2. 시나리오별 처리

| 시나리오 | 감지 조건 | 동작 |
|---------|----------|------|
| PC-D error 발생 | error 등급 체크 ≥1개 실패 | abort → 30초 대기 → 재실행 (최대 2회) |
| infra_baseline_version 불일치 | yaml 버전 ≠ 실제 인프라 버전 | 즉시 중단, 재시도 없음, 운영실 에스컬레이션 |
| 토큰 교차 참조 불일치 | CROSS-REF 규칙 위반 | warn 로그 + 계속 진행 (3회 연속 시 에스컬레이션) |
| max_retries 소진 | 2회 재시도 후 동일 실패 | PR/배포 자동 취소 |

### 4-3. 에스컬레이션 알림 형식

```
[DESIGN-PREFLIGHT-FAIL] {check_id} 실패 — {condition}
baseline: design-baseline.yaml v{version}, infra: {infra_baseline_version}
재시도 횟수: {retry_count}/{max_retries}
```

---

## 5. 실행 방법

### 5-1. 수동 실행 (기존 제어면 활용)

```bash
# 오케스트레이션 설정 전체 검증
python tools/orchestration_cli.py validate-config

# design-baseline.yaml 전용 pre-flight (구현 예정)
python tools/design_preflight.py --config config/design-baseline.yaml
```

### 5-2. 자동 실행 트리거

- **PR 생성 시**: GitHub Actions 워크플로에서 `design-baseline.yaml` 변경 감지 시 자동 실행
- **배포 전**: 운영 파이프라인에서 infra-baseline.yaml + design-baseline.yaml 양쪽 pre-flight 순차 실행
- **주기적 검증**: 크론 등록 (`tools/memory_ttl_checker.py` 연동) — 매일 00:00 KST

---

## 6. 변경 이력

| 버전 | 날짜 | 변경 내용 | 작성자 |
|------|------|---------|-------|
| v1.1 | 2026-03-29 | PC-D-013~016 추가, 교차 참조 검증(CROSS-REF) 섹션 신설, retry_policy 정의 | 디자인실 |
| v1.0 | 2026-03-26 | 최초 작성 (PC-D-001~012) | 디자인실 |
