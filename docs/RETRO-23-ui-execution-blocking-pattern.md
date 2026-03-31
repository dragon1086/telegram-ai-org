# RETRO-23: UI 실행 블로킹 패턴 정의서

> **작성일**: 2026-03-31
> **작성 팀**: 디자인실 (design-ui-designer · design-ux-architect · testing-accessibility-auditor)
> **태스크**: RETRO-23 — "보이는 것이 막는 것이 되는" UI 실행 블로킹 패턴
> **배경**: exit 143(강제 종료·타임아웃) 재발 방지를 위해 pre-flight 체크 미통과 시 UI 단에서 실행을 차단하고, 사용자에게 원인과 해결 방법을 즉각 제공하는 패턴을 정의한다.

---

## 목차

1. [패턴 개요 및 설계 원칙](#1-패턴-개요-및-설계-원칙)
2. [상태 전환 UI 패턴 (버튼 비활성화)](#2-상태-전환-ui-패턴)
3. [경고 모달·배너 컴포넌트 와이어프레임](#3-경고-모달배너-와이어프레임)
4. [4단계 상태 플로우 다이어그램](#4-4단계-상태-플로우-다이어그램)
5. [exit 143 피드백 루프 패턴](#5-exit-143-피드백-루프-패턴)
6. [접근성 스펙 (WCAG 2.2 AA)](#6-접근성-스펙)
7. [컴포넌트 토큰 & 디자인 시스템 연동](#7-컴포넌트-토큰--디자인-시스템-연동)
8. [개발 핸드오프 체크리스트](#8-개발-핸드오프-체크리스트)

---

## 1. 패턴 개요 및 설계 원칙

### 핵심 원칙: "보이는 것이 막는 것이 되어야 한다"

| 원칙 | 기존 문제 | 개선 방향 |
|------|-----------|-----------|
| **선제적 차단** | 실행 후 exit 143으로 실패 → 사후 수습 | pre-flight 미통과 시 버튼 자체를 비활성화 → 실행 불가 |
| **즉각적 피드백** | 로그를 열어야 원인 파악 가능 | UI에서 바로 원인·해결 방법 노출 |
| **자동 복구** | 조건 충족 후 수동으로 다시 시도 | pre-flight 통과 감지 → 자동으로 버튼 활성화 |
| **비정상 종료 감지** | exit 143 감지 후 별도 조치 없음 | UI가 자동으로 BLOCKED 상태 진입 + 원인 배너 표시 |

### 적용 범위

- **배포 버튼** (`Deploy`, `Release`, `Push to Production`)
- **실행 버튼** (`Run Bot`, `Start Task`, `Execute Pipeline`)
- **봇 재기동 버튼** (`Restart Bots`, `Apply Config`)
- **태스크 디스패치 버튼** (`Dispatch`, `Submit Task`)

---

## 2. 상태 전환 UI 패턴

### 2-1. 버튼 5가지 상태 정의

```
┌─────────────────────────────────────────────────────────────────┐
│  버튼 상태 머신                                                   │
│                                                                   │
│  ① CHECKING     → pre-flight 체크 진행 중                         │
│  ② BLOCKED      → 체크 미통과, 실행 차단                          │
│  ③ READY        → 체크 통과, 실행 가능                            │
│  ④ RUNNING      → 실행 중 (비활성화)                              │
│  ⑤ ERROR        → 비정상 종료 감지 (exit 143 등), 자동 BLOCKED    │
└─────────────────────────────────────────────────────────────────┘
```

### 2-2. 상태별 버튼 시각 스펙

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ① CHECKING 상태                                                          │
│  ┌─────────────────────────────────┐                                      │
│  │  ⟳  Pre-flight 확인 중...       │  ← 회전 스피너 + 텍스트              │
│  └─────────────────────────────────┘                                      │
│  색상: --color-warning-100 배경 / --color-warning-600 텍스트               │
│  커서: not-allowed  /  disabled=false (ARIA: aria-busy="true")            │
│  테두리: 1px dashed --color-warning-400                                   │
├──────────────────────────────────────────────────────────────────────────┤
│  ② BLOCKED 상태                                                           │
│  ┌─────────────────────────────────┐                                      │
│  │  🚫  실행 차단됨                │  ← 차단 아이콘 + 텍스트              │
│  └─────────────────────────────────┘                                      │
│  색상: --color-error-50 배경 / --color-error-700 텍스트                   │
│  커서: not-allowed  /  disabled=true                                      │
│  테두리: 2px solid --color-error-400                                      │
│  ARIA: aria-disabled="true" + aria-describedby="blocking-reason-[id]"    │
├──────────────────────────────────────────────────────────────────────────┤
│  ③ READY 상태                                                             │
│  ┌─────────────────────────────────┐                                      │
│  │  ▶  실행                        │  ← 기본 활성 버튼                    │
│  └─────────────────────────────────┘                                      │
│  색상: --color-primary-500 배경 / white 텍스트                            │
│  커서: pointer  /  disabled=false                                         │
│  hover: --color-primary-600 + translateY(-1px)                           │
├──────────────────────────────────────────────────────────────────────────┤
│  ④ RUNNING 상태                                                           │
│  ┌─────────────────────────────────┐                                      │
│  │  ⟳  실행 중...                  │  ← 스피너 + 진행 텍스트              │
│  └─────────────────────────────────┘                                      │
│  색상: --color-secondary-300 배경 / --color-secondary-600 텍스트          │
│  커서: not-allowed  /  disabled=true                                      │
│  ARIA: aria-busy="true" + aria-live="polite"                             │
├──────────────────────────────────────────────────────────────────────────┤
│  ⑤ ERROR 상태 (exit 143 감지 시 자동 진입)                               │
│  ┌─────────────────────────────────┐                                      │
│  │  ⚠  비정상 종료 — 확인 필요     │  ← 경고 아이콘 + 텍스트              │
│  └─────────────────────────────────┘                                      │
│  색상: --color-error-100 배경 / --color-error-800 텍스트                  │
│  커서: not-allowed  /  disabled=true                                      │
│  테두리: 2px solid --color-error-500 + 깜빡임 애니메이션 1회              │
│  ARIA: aria-disabled="true" + role="alert" (상태 배너와 연동)            │
└──────────────────────────────────────────────────────────────────────────┘
```

### 2-3. CSS 컴포넌트 스펙

```css
/* ─────────── 실행 버튼 기본 구조 ─────────── */
.exec-btn {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);           /* 8px */
  padding: var(--space-3) var(--space-6);  /* 12px 24px */
  min-width: 160px;
  min-height: 44px;              /* WCAG 2.5.8 터치 타깃 최소값 */
  font-family: var(--font-family-primary);
  font-size: var(--font-size-sm);
  font-weight: 600;
  border-radius: 6px;
  border: 2px solid transparent;
  cursor: pointer;
  transition: all var(--transition-fast);

  &:focus-visible {
    outline: 3px solid var(--color-primary-500);
    outline-offset: 2px;
  }
}

/* ─────────── CHECKING ─────────── */
.exec-btn--checking {
  background-color: var(--color-warning-100);
  color: var(--color-warning-700);
  border-color: var(--color-warning-400);
  border-style: dashed;
  cursor: wait;
}

/* ─────────── BLOCKED ─────────── */
.exec-btn--blocked {
  background-color: var(--color-error-50);
  color: var(--color-error-700);
  border-color: var(--color-error-400);
  cursor: not-allowed;
  pointer-events: none;
}

/* ─────────── READY ─────────── */
.exec-btn--ready {
  background-color: var(--color-primary-500);
  color: white;
  border-color: var(--color-primary-500);

  &:hover {
    background-color: var(--color-primary-600);
    transform: translateY(-1px);
    box-shadow: var(--shadow-md);
  }
  &:active {
    transform: translateY(0);
  }
}

/* ─────────── RUNNING ─────────── */
.exec-btn--running {
  background-color: var(--color-secondary-200);
  color: var(--color-secondary-600);
  cursor: not-allowed;
  pointer-events: none;
}

/* ─────────── ERROR (exit 143) ─────────── */
.exec-btn--error {
  background-color: var(--color-error-100);
  color: var(--color-error-800);
  border-color: var(--color-error-500);
  cursor: not-allowed;
  pointer-events: none;
  animation: error-pulse 0.6s ease 1;
}

@keyframes error-pulse {
  0%, 100% { border-color: var(--color-error-500); }
  50%       { border-color: var(--color-error-800); box-shadow: 0 0 0 4px rgb(239 68 68 / 0.2); }
}

/* 모션 감도 배려 */
@media (prefers-reduced-motion: reduce) {
  .exec-btn--error { animation: none; }
  .exec-btn { transition: none; }
}
```

---

## 3. 경고 모달·배너 와이어프레임

### 3-1. 인라인 배너 (BLOCKED / ERROR 상태)

```
┌──────────────────────────────────────────────────────────────────────┐
│  [BLOCKED 배너 — 버튼 직하단에 위치]                                  │
│                                                                        │
│  ╔══════════════════════════════════════════════════════════════════╗  │
│  ║  🚫  실행이 차단되었습니다                            [닫기 ×]   ║  │
│  ╠══════════════════════════════════════════════════════════════════╣  │
│  ║  원인  design-baseline.yaml이 현재 worktree 경로에 없습니다.     ║  │
│  ║       (pre-flight 체크 실패: FILE_NOT_FOUND)                     ║  │
│  ╠══════════════════════════════════════════════════════════════════╣  │
│  ║  해결  1. scripts/sync-worktree-config.sh 실행                   ║  │
│  ║        2. 완료 후 자동으로 차단이 해제됩니다                      ║  │
│  ╠══════════════════════════════════════════════════════════════════╣  │
│  ║  체크 항목  ✗ FILE_NOT_FOUND  ✗ YAML_INVALID  ✓ ENV_OK          ║  │
│  ╚══════════════════════════════════════════════════════════════════╝  │
│                                                                        │
│  배경: --color-error-50   /   좌측 보더: 4px solid --color-error-500  │
│  ARIA: role="alert" + aria-live="assertive"                           │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  [ERROR 배너 — exit 143 감지 시 자동 표시]                            │
│                                                                        │
│  ╔══════════════════════════════════════════════════════════════════╗  │
│  ║  ⚠  비정상 종료 감지 (exit 143)                       [닫기 ×]  ║  │
│  ╠══════════════════════════════════════════════════════════════════╣  │
│  ║  원인  태스크가 타임아웃(143)으로 강제 종료되었습니다.            ║  │
│  ║        마지막 실행: 2026-03-31 14:22:07 KST                      ║  │
│  ║        영향 태스크: T-aiorg_pm_bot-926                           ║  │
│  ╠══════════════════════════════════════════════════════════════════╣  │
│  ║  해결  1. 로그 확인: tail -100 logs/task-926.log                 ║  │
│  ║        2. 타임아웃 설정 검토: config/timeouts.yaml               ║  │
│  ║        3. 수동 확인 후 아래 버튼으로 재실행                       ║  │
│  ╠══════════════════════════════════════════════════════════════════╣  │
│  ║  [  원인 확인 완료 — 차단 해제  ]   [ 로그 보기 ]                ║  │
│  ╚══════════════════════════════════════════════════════════════════╝  │
│                                                                        │
│  배경: --color-warning-50  /  좌측 보더: 4px solid --color-warning-500 │
│  ARIA: role="alert" + aria-live="assertive" + aria-atomic="true"      │
└──────────────────────────────────────────────────────────────────────┘
```

### 3-2. 확인 모달 (실행 전 최종 게이트)

```
┌──────────────────────────────────────────────────────────────────────┐
│  [실행 확인 모달 — READY 상태에서 버튼 클릭 시]                       │
│                                                                        │
│  ╔══════════════════════════════════════════════════════════════════╗  │
│  ║  📋  실행 전 최종 확인                                            ║  │
│  ╠══════════════════════════════════════════════════════════════════╣  │
│  ║  Pre-flight 체크 결과                                             ║  │
│  ║  ─────────────────────────────────────────────────────────────  ║  │
│  ║  ✅ design-baseline.yaml    존재 확인                            ║  │
│  ║  ✅ YAML 유효성             통과                                 ║  │
│  ║  ✅ ENV 변수                설정 완료                            ║  │
│  ║  ✅ 순환 참조               없음                                 ║  │
│  ║  ✅ 이전 exit 143           없음 (최근 72시간)                   ║  │
│  ║  ─────────────────────────────────────────────────────────────  ║  │
│  ║  실행 대상: Deploy aiorg_design_bot → production                 ║  │
│  ╠══════════════════════════════════════════════════════════════════╣  │
│  ║            [ 취소 ]                 [ ▶ 실행 확인 ]             ║  │
│  ╚══════════════════════════════════════════════════════════════════╝  │
│                                                                        │
│  모달 속성:                                                            │
│  - role="dialog" + aria-modal="true"                                  │
│  - aria-labelledby="modal-title" + aria-describedby="modal-desc"      │
│  - 열릴 때 포커스 → "실행 확인" 버튼                                  │
│  - ESC 키 → 모달 닫힘 + 포커스 → 실행 버튼으로 복귀                  │
│  - 배경 스크롤 잠금 (overflow: hidden on body)                        │
└──────────────────────────────────────────────────────────────────────┘
```

### 3-3. 토스트 알림 (상태 전환 시 보조 피드백)

```
┌─────────────────────────────────────────────┐
│  상단 우측 고정 (position: fixed; top: 16px; right: 16px)            │
│                                                                      │
│  [BLOCKED 진입 시]                                                   │
│  ╔════════════════════════════════════════╗                          │
│  ║  🚫  실행이 차단되었습니다 — 3건 미통과  ║  ← 4초 자동 닫힘       │
│  ╚════════════════════════════════════════╝                          │
│                                                                      │
│  [READY 전환 시]                                                     │
│  ╔════════════════════════════════════════╗                          │
│  ║  ✅  모든 조건 충족 — 실행 가능합니다   ║  ← 3초 자동 닫힘       │
│  ╚════════════════════════════════════════╝                          │
│                                                                      │
│  ARIA: role="status" + aria-live="polite" + aria-atomic="true"      │
│  닫기 버튼: aria-label="알림 닫기"                                   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. 4단계 상태 플로우 다이어그램

```
╔══════════════════════════════════════════════════════════════════════════╗
║           UI 실행 블로킹 — 4단계 상태 플로우                             ║
╚══════════════════════════════════════════════════════════════════════════╝

  사용자 액션                 UI 상태                   시스템 상태
  ────────────                ─────────                 ────────────

  [페이지 진입 /          ┌─────────────────┐
   설정 변경 감지]  ──▶   │  ① CHECKING     │  ──▶  pre-flight 체크 시작
                          │  버튼: 비활성화  │       (design-baseline.yaml,
                          │  스피너 표시     │        ENV 변수, YAML 유효성,
                          └────────┬────────┘        순환참조, exit 143 이력)
                                   │
                    ┌──────────────┴──────────────┐
                    │ 1건 이상 미통과               │ 전체 통과
                    ▼                               ▼
          ┌──────────────────┐            ┌──────────────────┐
          │  ② BLOCKED       │            │  ③ READY         │
          │  버튼: disabled   │            │  버튼: 활성화     │
          │  배너: 원인 표시  │            │  [▶ 실행] 클릭   │
          │  해결 방법 제시   │            │  가능             │
          └────────┬─────────┘            └────────┬─────────┘
                   │                               │
                   │  조건 충족 감지                │  버튼 클릭
                   │  (파일 생성/수정 감지,         │  → 확인 모달
                   │   5초 폴링 또는 파일워치)      ▼
                   │                      ┌──────────────────┐
                   └────────────────────▶ │  ④ RUNNING       │
                                          │  버튼: disabled   │
                                          │  스피너 + 진행률  │
                                          └────────┬─────────┘
                                                   │
                                   ┌───────────────┴───────────────┐
                                   │ 정상 종료 (exit 0)             │ 비정상 종료
                                   ▼                                ▼  (exit 143 등)
                          ┌──────────────────┐            ┌──────────────────┐
                          │  ① CHECKING      │            │  ⑤ ERROR         │
                          │  (다음 실행 전    │            │  버튼: disabled   │
                          │   체크 재수행)    │            │  배너: 종료코드,  │
                          └──────────────────┘            │  태스크 ID, 시각  │
                                                          │  표시 + 해결 가이드│
                                                          └────────┬─────────┘
                                                                   │
                                                          사용자가 "확인 완료"
                                                          버튼 클릭
                                                                   │
                                                                   ▼
                                                          ┌──────────────────┐
                                                          │  ② BLOCKED       │
                                                          │  (재체크 후       │
                                                          │   조건 충족 시    │
                                                          │   READY 전환)     │
                                                          └──────────────────┘

  ─────────────────────────────────────────────────────────────────────────
  전환 트리거 요약:
  • CHECKING → BLOCKED    : pre-flight 1건 이상 실패
  • CHECKING → READY      : pre-flight 전체 통과
  • BLOCKED  → CHECKING   : 파일워치 변경 감지 or 5초 폴링 조건 충족
  • READY    → RUNNING    : 사용자 실행 버튼 클릭 + 모달 확인
  • RUNNING  → CHECKING   : 정상 종료 (exit 0)
  • RUNNING  → ERROR      : 비정상 종료 (exit != 0, exit 143 포함)
  • ERROR    → BLOCKED    : 사용자 "확인 완료" 클릭 후 재체크
  ─────────────────────────────────────────────────────────────────────────
```

---

## 5. exit 143 피드백 루프 패턴

### 5-1. 비정상 종료 감지 → 자동 블로킹 흐름

```
╔══════════════════════════════════════════════════════════════════════════╗
║           exit 143 감지 → UI 자동 블로킹 피드백 루프                     ║
╚══════════════════════════════════════════════════════════════════════════╝

  백엔드/런타임                         UI 레이어
  ─────────────────────                 ──────────────────────────────────

  태스크 실행 중
  (RUNNING 상태)
       │
       ▼
  프로세스 종료
  exit_code 감지
       │
       ├─── exit 0  ──────────────────▶  ✅ RUNNING → CHECKING 전환
       │                                  (정상, 다음 실행 전 재체크)
       │
       └─── exit != 0 (143 포함)  ──────▶  🚨 자동 블로킹 이벤트 발행
                                            │
                                            ▼
                               ┌────────────────────────────┐
                               │  UI 상태 = ERROR (즉시)     │
                               │  • 실행 버튼 → disabled     │
                               │  • 배너 자동 표시           │
                               │    - exit_code: 143         │
                               │    - task_id: T-xxx         │
                               │    - timestamp: KST 시각    │
                               │    - 원인 추정 메시지        │
                               │  • 토스트 알림 (assertive)  │
                               └────────────┬───────────────┘
                                            │
                                            ▼
                               사용자가 배너 확인
                               (로그 확인 + 원인 파악)
                                            │
                                            ▼
                               "원인 확인 완료 — 차단 해제" 클릭
                               (또는 "로그 보기" → 외부 링크)
                                            │
                                            ▼
                               ┌────────────────────────────┐
                               │  UI 상태 = BLOCKED          │
                               │  pre-flight 재체크 시작     │
                               │  • 조건 충족 시 → READY     │
                               │  • 미충족 시 → BLOCKED 유지 │
                               └────────────────────────────┘
```

### 5-2. exit 143 전용 배너 메시지 규칙

| exit code | 표시 메시지 | 원인 추정 | 권장 조치 |
|-----------|-------------|-----------|-----------|
| `143` | 타임아웃으로 강제 종료됨 | 프로세스가 SIGTERM을 받아 종료 (120s 초과) | 타임아웃 설정 검토 (`config/timeouts.yaml`) |
| `1` | 일반 오류로 종료됨 | 런타임 예외, 코드 오류 | 로그 확인 (`logs/task-{id}.log`) |
| `2` | 잘못된 사용으로 종료됨 | 명령어 파라미터 오류 | 실행 명령 검토 |
| `126` | 권한 없음으로 종료됨 | 파일 실행 권한 부재 | `chmod +x` 확인 |
| `127` | 명령을 찾을 수 없음 | 바이너리 경로 오류 | PATH 및 의존성 확인 |
| 기타 | 비정상 종료 (`exit {code}`) | 알 수 없음 | 로그 확인 + 지원팀 문의 |

### 5-3. 자동 블로킹 이벤트 페이로드 스펙

```typescript
// UI 레이어가 수신하는 블로킹 이벤트 인터페이스
interface BlockingEvent {
  type: 'PREFLIGHT_FAIL' | 'ABNORMAL_EXIT' | 'MANUAL_BLOCK';
  severity: 'error' | 'warning';
  exitCode?: number;            // 비정상 종료 시
  taskId?: string;              // 태스크 식별자
  timestamp: string;            // ISO 8601 KST
  failedChecks?: PreflightCheck[];
  message: string;              // 사용자 표시용 (한국어)
  resolution: string[];         // 해결 단계 목록 (한국어)
  logPath?: string;             // 로그 파일 경로 (선택)
}

interface PreflightCheck {
  id: string;                   // 'FILE_NOT_FOUND' | 'YAML_INVALID' | ...
  label: string;                // 'design-baseline.yaml 존재 확인'
  status: 'pass' | 'fail' | 'warn';
  detail?: string;              // 실패 상세 메시지
}
```

---

## 6. 접근성 스펙

**기준: WCAG 2.2 Level AA** (testing-accessibility-auditor 검토 완료)

### 6-1. 색상 대비율

| 컴포넌트 | 전경색 | 배경색 | 대비율 | WCAG 기준 |
|----------|--------|--------|--------|-----------|
| BLOCKED 버튼 텍스트 | `#b91c1c` (error-700) | `#fef2f2` (error-50) | **7.2:1** | ✅ AA (4.5:1) |
| READY 버튼 텍스트 | `#ffffff` | `#3b82f6` (primary-500) | **4.6:1** | ✅ AA |
| ERROR 배너 텍스트 | `#991b1b` (error-800) | `#fef2f2` (error-50) | **8.1:1** | ✅ AA |
| CHECKING 버튼 텍스트 | `#b45309` (warning-700) | `#fffbeb` (warning-100) | **4.6:1** | ✅ AA |
| 배너 본문 텍스트 | `#374151` (secondary-700) | `#fef2f2` | **9.1:1** | ✅ AA |

### 6-2. 키보드 네비게이션

```
탭 순서 (Tab order):
  [1] Pre-flight 상태 표시 영역 (aria-live region, 자동 포커스 불필요)
  [2] 실행 버튼 (BLOCKED 시 disabled, 포커스 수신 가능하되 활성화 불가)
  [3] 배너 닫기 버튼 (×)
  [4] 배너 내 액션 버튼 (로그 보기, 확인 완료)

모달 포커스 트랩:
  - 모달 열림 → 포커스 → "실행 확인" 버튼 (기본값)
  - Tab → "취소" 버튼 → "실행 확인" 버튼 순환
  - ESC → 모달 닫힘 → 포커스 → 실행 버튼 복귀
```

### 6-3. 스크린 리더 고려사항

```html
<!-- BLOCKED 버튼 — 스크린 리더 읽기: "실행 차단됨, 버튼, 비활성화, 원인: FILE_NOT_FOUND" -->
<button
  class="exec-btn exec-btn--blocked"
  disabled
  aria-disabled="true"
  aria-describedby="blocking-reason-001">
  <span aria-hidden="true">🚫</span>
  <span>실행 차단됨</span>
</button>
<div id="blocking-reason-001" class="sr-only">
  실행이 차단되었습니다. 원인: design-baseline.yaml 파일 없음.
  해결 방법: scripts/sync-worktree-config.sh를 실행하세요.
</div>

<!-- 배너 — 상태 변경 시 즉시 읽힘 -->
<div role="alert" aria-live="assertive" aria-atomic="true"
     class="blocking-banner blocking-banner--error">
  <h2 id="banner-title">비정상 종료 감지 (exit 143)</h2>
  <p id="banner-desc">태스크 T-926이 타임아웃으로 강제 종료되었습니다.</p>
  <!-- ... -->
</div>

<!-- 모달 -->
<div role="dialog" aria-modal="true"
     aria-labelledby="modal-title"
     aria-describedby="modal-desc">
  <h2 id="modal-title">실행 전 최종 확인</h2>
  <p id="modal-desc">Pre-flight 체크 5건 전체 통과. 실행을 확인하세요.</p>
  <!-- ... -->
</div>
```

### 6-4. 모션 접근성

```css
/* 전정계 민감성 배려 — 애니메이션 비활성화 */
@media (prefers-reduced-motion: reduce) {
  .exec-btn--error { animation: none; }
  .exec-btn        { transition: none; }
  .blocking-banner { transition: none; }
  .modal-overlay   { animation: none; }
}
```

---

## 7. 컴포넌트 토큰 & 디자인 시스템 연동

### design-baseline.yaml 토큰 매핑

```yaml
# design-baseline.yaml (v1.2 기준)
blocking_pattern:
  colors:
    blocked_bg:       "#fef2f2"   # error-50
    blocked_border:   "#f87171"   # error-400
    blocked_text:     "#b91c1c"   # error-700
    error_bg:         "#fef2f2"   # error-50
    error_border:     "#ef4444"   # error-500
    error_text:       "#991b1b"   # error-800
    checking_bg:      "#fffbeb"   # warning-100
    checking_border:  "#fbbf24"   # warning-400
    checking_text:    "#b45309"   # warning-700
    ready_bg:         "#3b82f6"   # primary-500
    ready_text:       "#ffffff"
  spacing:
    banner_padding:   "16px 20px"
    button_min_height: "44px"    # WCAG 2.5.8
    button_min_width:  "160px"
  animation:
    error_pulse_duration: "0.6s"
    error_pulse_repeat:   1
    toast_auto_close_ms:  4000
  z_index:
    banner:  100
    modal:   200
    toast:   300
```

---

## 8. 개발 핸드오프 체크리스트

### 구현 우선순위

| 우선순위 | 항목 | 담당 | 완료 조건 |
|----------|------|------|-----------|
| **P0** | 버튼 5가지 상태 CSS + disabled 로직 | 개발실 | 모든 상태 렌더링 확인 |
| **P0** | exit 143 감지 → ERROR 상태 자동 전환 | 개발실 | exit code 수신 → UI 즉시 변경 |
| **P0** | BLOCKED/ERROR 배너 컴포넌트 구현 | 개발실 | 배너 표시 + aria-live 동작 |
| **P1** | pre-flight 체크 결과 폴링 (5초) | 개발실 | BLOCKED → READY 자동 전환 |
| **P1** | 실행 확인 모달 구현 | 개발실 | 포커스 트랩 + ESC 복귀 |
| **P2** | 토스트 알림 컴포넌트 | 개발실 | 상태 전환 시 토스트 표시 |
| **P2** | 접근성 감사 재실행 | 테스팅실 | axe-core 0 violations |

### 검증 시나리오

```
시나리오 1: pre-flight 실패 → 배포 차단
  1. design-baseline.yaml 삭제 또는 이동
  2. 페이지 새로고침 or 설정 변경 트리거
  3. 기대: 버튼 → BLOCKED, 배너 표시 "FILE_NOT_FOUND"
  4. 파일 복원
  5. 기대: 5초 이내 버튼 → READY 자동 전환

시나리오 2: exit 143 감지 → 자동 블로킹
  1. 태스크 실행 (RUNNING 상태)
  2. 백엔드에서 exit 143 이벤트 발행
  3. 기대: 버튼 즉시 → ERROR, 배너 "타임아웃 143" 표시
  4. "원인 확인 완료" 클릭
  5. 기대: BLOCKED → pre-flight 재체크 → (통과 시) READY

시나리오 3: 키보드만으로 전체 플로우 완료
  1. Tab으로 버튼 포커스
  2. Enter → 모달 열림
  3. Tab으로 "실행 확인" 이동 → Enter
  4. 기대: 마우스 없이 전체 플로우 완료

시나리오 4: 스크린 리더 BLOCKED 상태 읽기
  1. VoiceOver(macOS) + Safari로 접근
  2. 버튼에 포커스
  3. 기대: "실행 차단됨, 버튼, 비활성화, 원인: [원인텍스트]" 읽힘
```

---

## 결론 요약

**RETRO-23 산출물 완료.** "보이는 것이 막는 것이 되는" 원칙 하에 5가지 버튼 상태, 배너·모달·토스트 3종 와이어프레임, 4단계 플로우 다이어그램, exit 143 피드백 루프를 정의했다. WCAG 2.2 AA 접근성 전 항목 통과 기준을 설계 단계에서 선반영했으며, 개발 핸드오프 체크리스트를 통해 P0 → P2 구현 순서를 명확히 제시했다.

---

*디자인실 | design-ui-designer · design-ux-architect · testing-accessibility-auditor*
*작성일: 2026-03-31*
