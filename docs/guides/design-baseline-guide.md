# design-baseline.yaml 운영 가이드

> **버전**: v1.0 | **작성일**: 2026-03-26 | **관리 주체**: 디자인실 (aiorg_design_bot)
> **위치**: `config/design-baseline.yaml` | **연동 파일**: `config/infra-baseline.yaml`

---

## 1. 파일 구조 설명

`design-baseline.yaml`은 디자인 렌더링 환경의 **단일 진실 소스(Single Source of Truth)**입니다.
모든 뷰포트·폰트·테마 파라미터를 이 파일 하나에서 관리하고, 변경 시 PR 필수화로 추적성을 확보합니다.

```
config/
├── infra-baseline.yaml       ← 인프라 파라미터 기준선 (운영실 관리)
└── design-baseline.yaml      ← 디자인 렌더링 기준선 (디자인실 관리)  ← 이 파일
```

### 최상위 메타 필드

| 필드 | 예시값 | 설명 |
|------|--------|------|
| `schema_version` | `1` | 파일 스키마 버전 (하위 호환성 관리용) |
| `generated_at` | `"2026-03-26"` | 최초 생성 또는 마지막 수동 갱신일 |
| `infra_baseline_version` | `"v1.0"` | 연동 중인 `infra-baseline.yaml` 버전 태깅 |

---

## 2. 각 섹션별 항목 의미

### 2-1. `viewport` — 뷰포트 및 디바이스 렌더링 환경

| 항목 | 기본값 | 설명 |
|------|--------|------|
| `default_width` | `1440` | 기본 렌더링 너비(px). 와이어프레임·프로토타입 기준 해상도 |
| `default_height` | `900` | 기본 렌더링 높이(px) |
| `breakpoints.mobile` | `375` | 모바일 브레이크포인트 (iPhone SE/12 mini 기준) |
| `breakpoints.tablet` | `768` | 태블릿 브레이크포인트 (iPad mini 기준) |
| `breakpoints.desktop` | `1024` | 데스크탑 브레이크포인트 |
| `breakpoints.wide` | `1440` | 와이드 데스크탑 브레이크포인트 |
| `device_presets` | `"desktop"` | 렌더링 디바이스 프리셋 (mobile-s/m/l / tablet / desktop / wide) |
| `pixel_ratio` | `1` | 디바이스 픽셀 비율(DPR). Retina=2, 고해상도 모바일=3 |

### 2-2. `typography` — 폰트 및 타입 스케일

| 항목 | 기본값 | 설명 |
|------|--------|------|
| `font_family_primary` | `"Pretendard"` | 주 폰트 패밀리. 한국어 시 Pretendard/Noto Sans KR 권장 |
| `font_family_mono` | `"JetBrains Mono"` | 고정폭 폰트 (코드·수치 전용) |
| `base_font_size` | `16` | 1rem 기준값(px). 최소 14px 이상 필수 (WCAG 1.4.4) |
| `type_scale` | `"major-third"` | 모듈러 스케일 비율 (h1~h6 크기 계산 기준) |
| `font_weights` | `[400,500,600,700]` | 허용 웨이트 목록. 목록 외 사용 시 일관성 위반 |
| `rendering_engine` | `"antialiased"` | 폰트 안티앨리어싱 방식 |
| `line_height_base` | `1.5` | 기본 줄 높이 배수. 1.5 이상 권장 (WCAG 1.4.8) |

### 2-3. `theme` — 컬러 토큰·모드·접근성 대비 기준

| 항목 | 기본값 | 설명 |
|------|--------|------|
| `active_mode` | `"light"` | 색상 모드 (light/dark/system) |
| `color_token_version` | `"v1.0"` | 적용 컬러 토큰 버전. `infra_baseline_version`과 쌍 태깅 |
| `primary_color` | `"#2563EB"` | 브랜드 주 색상. 변경 시 토큰 파일과 반드시 동기화 |
| `contrast_ratio_min` | `4.5` | 텍스트 대비 최솟값. AA=4.5, AAA=7.0, 대형 텍스트=3.0 |
| `wcag_level` | `"AA"` | 목표 WCAG 등급. 최소 AA, 핵심 흐름은 AAA 권장 |
| `dark_mode_token_file` | `"design/tokens/dark-overrides.json"` | 다크 모드 토큰 오버라이드 파일 경로 |
| `focus_visible_outline` | `"2px solid #2563EB"` | 키보드 포커스 스타일. 빈 값 절대 금지 (WCAG 2.4.7) |
| `motion_safe` | `true` | prefers-reduced-motion 준수 여부 (WCAG 2.3.3) |

---

## 3. pre-flight 체크 실행 방법

### 3-1. 체크 항목 목록 (PC-D-001 ~ PC-D-012)

| ID | 대상 필드 | 조건 | 실패 동작 | WCAG 조항 |
|----|----------|------|----------|-----------|
| PC-D-001 | `viewport.default_width` | 허용값 목록 내 | error | — |
| PC-D-002 | `viewport.pixel_ratio` | 표준 DPR 값 | warn | — |
| PC-D-003 | `typography.base_font_size` | >= 14px | error | 1.4.4 |
| PC-D-004 | `typography.font_family_primary` | 허용값 목록 내 | warn | — |
| PC-D-005 | `theme.contrast_ratio_min` | >= 4.5 | error | 1.4.3 |
| PC-D-006 | `theme.wcag_level` | AA 또는 AAA | error | — |
| PC-D-007 | `theme.active_mode` | 허용값 목록 내 | error | — |
| PC-D-008 | `theme.focus_visible_outline` | 빈 값 금지 | error | 2.4.7 |
| PC-D-009 | `typography.rendering_engine` | 허용값 목록 내 | warn | — |
| PC-D-010 | `theme.color_token_version` | vX.Y 형식 | warn | — |
| PC-D-011 | `typography.line_height_base` | >= 1.5 | warn | 1.4.8 |
| PC-D-012 | `theme.motion_safe` | true | warn | 2.3.3 |

> **error**: pre-flight 실패 → 렌더링/배포 중단
> **warn**: 경고 로그 출력 후 계속 진행

### 3-2. 수동 실행

현재 pre-flight 체크는 `design-baseline.yaml` 파일 로드 시 설정 검증 스크립트에서 실행됩니다.
향후 자동화 시 아래 진입점을 사용합니다:

```bash
# 오케스트레이션 설정 검증 (기존 제어면 활용)
python tools/orchestration_cli.py validate-config

# design-baseline.yaml 전용 pre-flight (구현 예정)
python tools/design_preflight.py --config config/design-baseline.yaml
```

### 3-3. infra-baseline.yaml과의 연동

```yaml
# design-baseline.yaml에서 인프라 버전 태깅 방법
infra_baseline_version: "v1.0"   # config/infra-baseline.yaml의 version 필드와 일치시킬 것
theme:
  color_token_version: "v1.0"     # 동시에 업데이트
```

두 파일의 버전을 함께 태깅하면, 지표 이상치 발생 시 "인프라 변경 탓인가, 디자인 토큰 변경 탓인가"를 로그 레벨에서 즉시 분류할 수 있습니다.

---

## 4. 값 변경 절차

### 4-1. 일반 파라미터 변경

1. `config/design-baseline.yaml` 수정
2. 변경 항목의 pre-flight 체크(PC-D-XXX) 통과 확인
3. `infra_baseline_version` 및 `color_token_version` 최신 버전으로 갱신 여부 검토
4. PR 생성 → 디자인실 리뷰 필수
5. 머지 후 `generated_at` 날짜 업데이트

### 4-2. WCAG 등급 변경 시 추가 절차

- `wcag_level`을 AA → AAA로 상향 시: 모든 컬러 토큰의 대비율 7.0:1 재검증 필요
- `contrast_ratio_min` 변경 시: `/design-critique` 스킬로 전체 UI 접근성 리뷰 실행

### 4-3. 브레이크포인트 변경 시

- `viewport.breakpoints` 변경은 **CSS 토큰 파일**(`design/tokens/`)과 반드시 동기화
- Figma 디자인 시스템 프레임 크기도 함께 업데이트

### 4-4. 긴급 핫픽스 (error 등급 pre-flight 실패 시)

```bash
# 1. 실패 항목 확인
python tools/orchestration_cli.py validate-config

# 2. design-baseline.yaml에서 해당 필드 수정

# 3. pre-flight 재실행 후 error 0건 확인

# 4. 재기동 필요 시 (직접 재기동 금지)
bash scripts/request_restart.sh --reason "design-baseline 긴급 수정: [항목명]"
```

---

## 5. 관련 파일

| 파일 | 역할 |
|------|------|
| `config/design-baseline.yaml` | 디자인 렌더링 환경 기준선 (이 문서의 대상) |
| `config/infra-baseline.yaml` | 인프라 파라미터 기준선 (운영실 관리) |
| `design/tokens/` | 컬러 토큰 파일 디렉토리 |
| `skills/design-critique/` | WCAG 접근성 검토 스킬 |
| `tools/orchestration_cli.py` | 오케스트레이션 설정 검증 CLI |
| `docs/design/RELEASE_VISUAL_SPEC_v1.0.0.md` | 시각 스펙 릴리즈 문서 |
