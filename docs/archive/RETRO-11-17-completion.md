# RETRO-11 · RETRO-17 통합 ACTION 반영 완료 확인서

> **작성일**: 2026-03-29 | **관리 주체**: 디자인실 (aiorg_design_bot)
> **태스크**: RETRO-05 (design-baseline.yaml), RETRO-11 (렌더링 환경 표준화), RETRO-17 (토큰 교차 참조)

---

## 1. 배경 및 원인

주간 회고에서 팀 전체가 공통으로 확인한 반성:

> **"기준은 세웠으나 변수 교차 맥락을 못 담았다"** (RETRO-15~20 공통 패턴)

- **개발실(RETRO-11)**: 디자인 렌더링 환경이 코드 환경과 분리되어 pre-flight 체크에서 누락됨
- **디자인실(RETRO-17)**: 디자인 토큰이 여러 컨텍스트(컴포넌트/테마/인프라)에 걸쳐 사용될 때 교차 맥락이 비가시적이어서 이상치 원인 분류 불가

---

## 2. ACTION 이행 결과

### RETRO-11: 디자인 렌더링 환경 표준화 + pre-flight 연동

| 항목 | 이전 상태 | 이행 후 상태 | 산출물 |
|------|----------|-------------|-------|
| design-baseline.yaml | v1.0 (viewport/typography/theme만 포함) | **v1.1** (component_library + design_tools + retro_actions + retry_policy 추가) | `config/design-baseline.yaml` |
| pre-flight 체크 항목 | PC-D-001~012 (12개) | **PC-D-001~016 (16개)** — 4개 신규 추가 | `config/design-baseline.yaml#preflight_checks` |
| infra_baseline_version 동기화 | v1.0 (구버전) | **v1.2** (infra-baseline.yaml v1.2.0과 정확히 동기화) | `config/design-baseline.yaml#infra_baseline_version` |
| last_updated 필드 | 없음 | **2026-03-29 추가** | `config/design-baseline.yaml#last_updated` |
| 컴포넌트 라이브러리 버전 명세 | 없음 | **SECTION 5 신설** (name/version/peer_deps/token_schema_version) | `config/design-baseline.yaml#component_library` |
| 디자인 툴 버전 명세 | 없음 | **SECTION 6 신설** (Figma v116/Storybook v7.6/Chromatic v11) | `config/design-baseline.yaml#design_tools` |

**검증 방법**:
```bash
python tools/orchestration_cli.py validate-config
# → PC-D-001~016 전체 통과 확인
```

---

### RETRO-17: 변수 교차 맥락 가시화 — 디자인 토큰 교차 참조 체계 명세

| 항목 | 이전 상태 | 이행 후 상태 | 산출물 |
|------|----------|-------------|-------|
| 토큰 교차 참조 체계 | 없음 (비가시적) | **RETRO_17.token_cross_reference_map 3개 규칙** | `config/design-baseline.yaml#retro_actions.RETRO_17` |
| component_library.token_schema_version | 없음 | **"v1.2" 추가** (theme.color_token_version과 쌍 태깅) | `config/design-baseline.yaml#component_library.token_schema_version` |
| CROSS-REF-001 | 없음 | infra_baseline_version ↔ theme.color_token_version 일치 규칙 | `config/design-baseline.yaml#retro_actions.RETRO_17` |
| CROSS-REF-002 | 없음 | component_library.version ↔ Figma Tokens Studio 호환성 | `config/design-baseline.yaml#retro_actions.RETRO_17` |
| CROSS-REF-003 | 없음 | color_token_version ↔ token_schema_version 일치 강제 | `config/design-baseline.yaml#retro_actions.RETRO_17` |

**교차 참조 현재 상태 검증**:

| 교차 참조 | 소스 값 | 대상 값 | 일치 여부 |
|----------|--------|--------|---------|
| CROSS-REF-001 | `infra_baseline_version: "v1.2"` | `color_token_version: "v1.0"` | ⚠️ 불일치 → 토큰 버전 업그레이드 검토 필요 |
| CROSS-REF-002 | `component_library: "1.4.2"` | `Tokens Studio: ">=2.0.0"` | ✅ 범위 내 |
| CROSS-REF-003 | `color_token_version: "v1.0"` | `token_schema_version: "v1.2"` | ⚠️ 불일치 → warn 발생 예정 |

> **CROSS-REF-001/003 불일치 조치**: `theme.color_token_version`과 `component_library.token_schema_version`을 "v1.2"로 업그레이드하여 infra_baseline_version과 동기화할 것. 별도 태스크(RETRO-17-follow-up)로 추적 권장.

---

### 자동 취소·재시도 (retry_policy, RETRO-11 연동)

| 항목 | 이행 내용 | 산출물 |
|------|---------|-------|
| retry_policy 섹션 | SECTION 8 신설 — max_retries/delay/backoff/trigger/escalation/auto_cancel | `config/design-baseline.yaml#retry_policy` |
| 자동 취소 규칙 | 2개 규칙 정의 (retries 소진 후 취소, 버전 불일치 즉시 취소) | `config/design-baseline.yaml#retry_policy.auto_cancel_rules` |
| PC-D-016 | retry_policy.max_retries 범위 검증 체크 추가 | `config/design-baseline.yaml#preflight_checks` |

---

## 3. 산출물 목록

| # | 산출물 | 경로 | 상태 |
|---|-------|------|------|
| 1 | design-baseline.yaml v1.1 | `config/design-baseline.yaml` | ✅ 완료 |
| 2 | pre-flight 디자인 환경 검증 정책 문서 | `docs/design-preflight-policy.md` | ✅ 완료 |
| 3 | RETRO-11·17 통합 ACTION 반영 완료 확인서 | `docs/RETRO-11-17-completion.md` | ✅ 완료 (이 문서) |

---

## 4. 후속 권고 사항

1. **토큰 버전 동기화**: `theme.color_token_version`과 `component_library.token_schema_version`을 `v1.2`로 일괄 업그레이드 (CROSS-REF-001/003 해소)
2. **tools/design_preflight.py 구현**: 현재 validate-config로 대체 운영 중 — 전용 스크립트 구현 시 PC-D 체크 자동화 완성
3. **GitHub Actions 연동**: PR 시 design-baseline.yaml 변경 감지 → pre-flight 자동 실행 워크플로 추가

---

## 5. 승인 및 이력

| 역할 | 담당 | 날짜 | 서명 |
|------|------|------|------|
| 작성 | 디자인실 (aiorg_design_bot) | 2026-03-29 | ✅ |
| 검토 | 운영실 (infra-baseline 연동 확인) | — | 대기 중 |
| 승인 | 총괄 PM | — | 대기 중 |
