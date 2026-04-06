# RETRO-18: 피드백 태깅 컨벤션 UI 가이드 (디자인실)

> **작성**: 디자인실 (aiorg_design_bot) | **작성일**: 2026-03-29
> **태스크 ID**: RETRO-18 (기획실) 디자인 지원
> **참조**: `docs/RETRO-18-variable-cross-visibility-guideline.md` (기획실 PRD), `docs/RETRO-06-feedback-version-tagging-convention.md`
> **목적**: `[infra:vX.Y.Z]` 피드백 태깅 컨벤션을 사용자가 직관적으로 입력·확인할 수 있는 UI 패턴 설계
> **WCAG**: AA 준수

---

## 1. 설계 배경

기획실 RETRO-18 PRD에서 정의한 전사 공통 피드백 태깅 컨벤션:

```
[infra:vX.Y.Z] [design:vX.Y] [env:prod/stg] 피드백 내용
```

이 컨벤션을 사용자가 **올바르게·일관되게 사용**하려면 입력 UI 수준에서 가이드가 필요하다.

---

## 2. 피드백 입력 UI 와이어프레임

### 2-A. 태깅 보조 입력창 (스마트 태그 인풋)

```
┌──────────────────────────────────────────────────────────┐
│  📝 피드백 작성                                           │
├──────────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────────┐  │
│  │ [infra:v1.2] × │ [design:v1.2] × │ [env:prod] ×  │  │
│  │ __________________________________________________ │  │
│  │ 버튼 클릭 시 dark 모드에서 텍스트 대비 깨짐 확인됨 │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  버전 태그 자동 감지: ✅ infra v1.2  ✅ design v1.2      │
│  환경: [prod] [stg] [local]  ←  선택                     │
│                                                          │
│                           [취소]  [피드백 제출]           │
└──────────────────────────────────────────────────────────┘
```

### 2-B. 태그 자동 완성 동작

```
사용자 "[" 입력
    ↓
드롭다운 표시:
  • [infra:v1.2]   ← 현재 infra_baseline_version 자동 주입
  • [design:v1.2]  ← 현재 design_baseline_version 자동 주입
  • [env:prod]     ← 현재 배포 환경 자동 감지
  • [custom:...]   ← 직접 입력
    ↓
선택 시 태그 칩(chip) 형태로 입력창 상단에 삽입
```

### 2-C. 태그 칩 컴포넌트 사양

| 속성 | 값 |
|------|-----|
| 배경색 | `#EFF6FF` (blue-50) |
| 텍스트색 | `#1D4ED8` (blue-700) · 대비 5.9:1 ✅ |
| 폰트 | `JetBrains Mono` 12px (코드 전용 폰트) |
| 삭제 버튼 | `×` · `aria-label="[infra:v1.2] 태그 삭제"` |
| 역할 | `role="listitem"` |
| 최대 너비 | 200px (넘칠 시 말줄임 + tooltip) |

---

## 3. 태그 검증 UI 패턴

### 3-A. 제출 전 검증 표시

```
┌──────────────────────────────────────────────────────────┐
│  🔍 태그 검증 결과                                        │
├──────────────────────────────────────────────────────────┤
│  ✅ [infra:v1.2]   — 현재 인프라 버전과 일치              │
│  ✅ [design:v1.2]  — 현재 디자인 베이스라인과 일치        │
│  ⚠️ [env:local]    — 로컬 환경 피드백은 재현성 낮음 주의  │
├──────────────────────────────────────────────────────────┤
│  💡 권장: infra 버전이 최근 변경되었습니다.               │
│     변수 교차 가능성 확인 후 제출하세요.                  │
│     → [변수 교차 확인] 버튼                               │
└──────────────────────────────────────────────────────────┘
```

### 3-B. 태그 누락 경고

```
❗ 필수 태그 누락: [infra:vX.Y.Z]
   환경 버전 없이 제출하면 이상치 추적이 불가합니다.
   [자동 태깅] 또는 [직접 입력] 중 선택하세요.

   aria-role: "alert"  aria-live: "polite"
```

---

## 4. 피드백 목록 뷰 — 태그 필터링 UI

### 4-A. 피드백 리스트 아이템

```
┌──────────────────────────────────────────────────────────┐
│  [infra:v1.2] [design:v1.2] [env:prod]                   │
│  버튼 클릭 시 dark 모드 텍스트 대비 깨짐                  │
│  ─────────────────────────────────────────────────────── │
│  보고자: 기획실 · 2026-03-29 14:23 · 🔴 High (미해결)    │
│  연관 변수 교차: Inter × dark × mobile  [교차 확인]       │
└──────────────────────────────────────────────────────────┘
```

### 4-B. 태그 기반 필터 패널

```
┌─────────────────────────────────────────┐
│  🏷 태그 필터                            │
├─────────────────────────────────────────┤
│  infra 버전   [v1.2 ▼]  [v1.1]  [전체] │
│  design 버전  [v1.2 ▼]  [v1.1]  [전체] │
│  환경         [prod] [stg] [local]      │
│  위험도       [🔴] [🟡] [🟢]  [전체]   │
│  교차 변수    [폰트] [테마] [뷰포트]    │
├─────────────────────────────────────────┤
│  결과: 피드백 12건 (High 3, Med 6, Low 3)│
└─────────────────────────────────────────┘
```

---

## 5. 컨벤션 인라인 가이드 (입력창 내 도움말)

### 5-A. 플레이스홀더 텍스트

```
placeholder: "[infra:vX.Y.Z] [design:vX.Y] [env:prod|stg|local] 피드백 내용 입력..."
```

### 5-B. 태그 형식 레퍼런스 (접을 수 있는 도움말)

```
▶ 태그 작성 가이드 (클릭해서 펼치기)

  infra 버전   : [infra:v1.2]     ← infra-baseline.yaml 버전
  design 버전  : [design:v1.2]    ← design-baseline.yaml 버전
  환경         : [env:prod]       ← prod / stg / local

  ✅ 올바른 예: [infra:v1.2] [env:prod] 다크모드 버튼 색상 대비 불량
  ❌ 잘못된 예: 다크모드 버튼 색상 대비 불량  (버전 태그 없음)
```

---

## 6. 접근성 준수 체크리스트 (WCAG AA)

- [x] 태그 칩: 삭제 버튼에 `aria-label` 포함 (텍스트 없는 버튼)
- [x] 경고 메시지: `role="alert"`, `aria-live="polite"` (긴급도에 따라 polite/assertive 구분)
- [x] 드롭다운: `role="listbox"`, 아이템은 `role="option"`, 키보드 ↑↓ 네비게이션
- [x] 태그 필터 토글: `aria-pressed="true/false"` 상태 전달
- [x] 색상 대비: 칩 텍스트 `#1D4ED8` on `#EFF6FF` → 5.9:1 (AA ✅)
- [x] 포커스 순서: 태그 입력 → 검증 결과 → 제출 버튼 (논리적 흐름)

---

## 7. design-baseline.yaml 연동 명세

```yaml
# design-baseline.yaml v1.2 feedback_tagging 확장 제안 항목
feedback_tagging_ui:
  tag_chip_style:
    bg: "#EFF6FF"
    text: "#1D4ED8"
    font: "JetBrains Mono"
    font_size: 12
  auto_inject_fields:
    - infra_baseline_version
    - design_baseline_version
    - active_environment
  validation_on_submit: true
  warn_on_cross_variable_change: true  # infra/design 버전 변경 시 교차 경고
```

---

## 8. 연계 산출물

| 문서 | 역할 |
|------|------|
| `docs/RETRO-06-feedback-version-tagging-convention.md` | 태깅 컨벤션 원본 PRD (기획실) |
| `docs/RETRO-18-variable-cross-visibility-guideline.md` | 전사 변수 교차 가이드라인 (기획실) |
| `docs/RETRO-15-design-variable-dependency-wireframe.md` | 변수 교차 DAG 시각화 (본 가이드 연동) |

---

*디자인실 (aiorg_design_bot) · 2026-03-29 · WCAG AA 준수 · design-baseline.yaml v1.2 기준*
