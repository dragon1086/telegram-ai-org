# RETRO-17: 변수 교차 맥락 가시화 — 렌더링 차이 교차 참조 표

> **작성**: 디자인실 (aiorg_design_bot) | **작성일**: 2026-03-29
> **참조**: `config/design-baseline.yaml v1.2` → `cross_rendering_matrix` 섹션
> **목적**: 어떤 변수 조합에서 어떤 렌더링 차이가 발생하는지 1페이지로 가시화

---

## 1. 3축 교차 매트릭스 개요

| 축 | 값 | 설명 |
|----|-----|------|
| **뷰포트** | mobile (375px) / tablet (768px) / desktop (1024px) | 렌더링 해상도 기준 |
| **폰트** | Pretendard / Inter / system-ui | 주 폰트 패밀리 |
| **테마** | light / dark / high-contrast | 색상 모드 + 대비 기준 |

전체 조합: **3 × 3 × 3 = 27개**

---

## 2. 조합별 렌더링 차이 및 위험도 요약

### 2-A. 뷰포트 × 폰트 × 테마 교차 참조 표

| 뷰포트 | 폰트 | 테마 | threshold_px | threshold_% | 위험도 | 주요 렌더링 차이 포인트 |
|--------|------|------|:---:|:---:|:---:|----------------------|
| mobile | Pretendard | light | 2px | 0.2% | 🟢 Low | 기본 조합 — 한국어 최적화, 안정 |
| mobile | Pretendard | dark | 3px | 0.3% | 🟡 Med | dark-overrides.json 토큰 오버라이드 동작 확인 |
| mobile | Pretendard | high-contrast | 2px | 0.2% | 🟢 Low | WCAG AAA(7:1) 강제 — 색상 토큰 변경 폭 큼 |
| mobile | Inter | light | 4px | 0.4% | 🟡 Med | 한국어 글리프 누락 → Pretendard fallback 발생 |
| mobile | Inter | dark | 5px | 0.5% | 🔴 High | fallback + 색상 오버라이드 이중 변수 — 집중 검증 |
| mobile | Inter | high-contrast | 3px | 0.3% | 🟡 Med | Inter fallback + 고대비 대비율 |
| mobile | system-ui | light | 6px | 0.6% | 🔴 High | OS/브라우저별 system-ui 렌더링 차이 최대 |
| mobile | system-ui | dark | 7px | 0.7% | 🔴 High | system-ui + dark — 허용 범위 전체 최대 |
| mobile | system-ui | high-contrast | 5px | 0.5% | 🔴 High | OS 접근성 설정 의존 + 자동 대비 보정 |
| tablet | Pretendard | light | 2px | 0.2% | 🟢 Low | 768px 브레이크포인트 레이아웃 전환 확인 |
| tablet | Pretendard | dark | 3px | 0.3% | 🟡 Med | 태블릿 다크모드 토큰 |
| tablet | Pretendard | high-contrast | 2px | 0.2% | 🟢 Low | 태블릿 AAA 대비 |
| tablet | Inter | light | 4px | 0.4% | 🟡 Med | 태블릿 + Inter 한국어 fallback |
| tablet | Inter | dark | 5px | 0.5% | 🔴 High | 태블릿 Inter 다크 — 이중 변수 |
| tablet | Inter | high-contrast | 3px | 0.3% | 🟡 Med | 태블릿 Inter 고대비 |
| tablet | system-ui | light | 6px | 0.6% | 🔴 High | OS별 system-ui 차이 |
| tablet | system-ui | dark | 7px | 0.7% | 🔴 High | system-ui + dark 최대 허용 |
| tablet | system-ui | high-contrast | 5px | 0.5% | 🔴 High | OS 접근성 의존 |
| desktop | Pretendard | light | 2px | 0.2% | 🟢 Low | **기준 조합** — 가장 안정적 |
| desktop | Pretendard | dark | 3px | 0.3% | 🟡 Med | 데스크탑 다크모드 |
| desktop | Pretendard | high-contrast | 2px | 0.2% | 🟢 Low | 데스크탑 AAA 대비 |
| desktop | Inter | light | 4px | 0.4% | 🟡 Med | 데스크탑 Inter fallback |
| desktop | Inter | dark | 5px | 0.5% | 🔴 High | 데스크탑 Inter 다크 |
| desktop | Inter | high-contrast | 3px | 0.3% | 🟡 Med | 데스크탑 Inter 고대비 |
| desktop | system-ui | light | 6px | 0.6% | 🔴 High | 데스크탑 OS별 system-ui |
| desktop | system-ui | dark | 7px | 0.7% | 🔴 High | **전체 최대 허용 범위** |
| desktop | system-ui | high-contrast | 5px | 0.5% | 🔴 High | OS 접근성 + system-ui 이중 의존 |

---

## 3. 위험도별 렌더링 차이 원인 요약

### 🔴 High (9개 조합) — 주요 원인

| 원인 | 관련 조합 | 대응 방안 |
|------|-----------|-----------|
| **system-ui OS별 차이** | system-ui × 모든 뷰포트 × 모든 테마 | CI 환경 OS 고정 (macOS/Linux 분리) |
| **Inter 한국어 fallback** | Inter × dark | Pretendard fallback 명시적 선언 확인 |
| **dark + fallback 이중 변수** | Inter × dark × 모든 뷰포트 | dark-overrides.json + fallback 동시 검증 |

### 🟡 Medium (9개 조합) — 주요 원인

| 원인 | 관련 조합 | 대응 방안 |
|------|-----------|-----------|
| **dark-overrides.json 토큰** | Pretendard × dark | PC-D-007 체크 통과 확인 |
| **Inter 한국어 글리프 누락** | Inter × light | `@font-face` fallback 체인 명시 |

### 🟢 Low (9개 조합) — 안정 조합

| 조합 | 특징 |
|------|------|
| Pretendard × light / high-contrast | 기본 권장 조합 |

---

## 4. 토큰 교차 참조 불일치 시 렌더링 영향

| 불일치 조합 | 영향 범위 | 감지 체크 |
|------------|----------|-----------|
| `theme.color_token_version` ≠ `component_library.token_schema_version` | 모든 컴포넌트 색상 이상 | PC-D-010 |
| `infra_baseline_version` ↔ `theme.color_token_version` 태깅 불일치 | 이상치 추적 불가 | CROSS-REF-001 |
| `component_library.version` ↔ Figma Tokens Studio 호환성 불일치 | Figma→코드 토큰 변환 오류 | CROSS-REF-002 |

---

## 5. CI 적용 권고

1. **기본 검증 조합**: `desktop_Pretendard_light` (Low, 기준값)
2. **고위험 집중 검증**: `mobile_Inter_dark`, `desktop_system-ui_dark` (High, 7px 허용)
3. **Chromatic 실행 시** `cross_rendering_matrix.combinations` threshold 값을 조합별로 적용
4. **SKIP_DESIGN_PREFLIGHT=1** 금지 (CI에서는 반드시 실행)

---

*이 문서는 `config/design-baseline.yaml v1.2` cross_rendering_matrix 섹션에서 자동 생성됩니다.*
