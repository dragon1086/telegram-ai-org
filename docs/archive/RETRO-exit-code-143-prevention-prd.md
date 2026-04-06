# PRD: Exit Code 143 재발 방지 정책
**문서 ID**: RETRO-exit-code-143-prevention-prd
**버전**: v1.0
**작성일**: 2026-03-31
**작성자**: 기획실(aiorg_product_bot)
**승인자**: (Rocky 검토 후 서명)
**정책 시행 목표일**: 2026-04-07
**상태**: Draft → Review 요청 중
**criteria_version**: 1.0.0
**criteria_tracking_ref**: criteria_tracking.yaml §thresholds.exit_code_143

---

## 1. 배경 및 문제 정의

### 1.1 에러 발생 맥락

2026-03-31 기준, `T-aiorg_pm_bot-884`, `T-aiorg_pm_bot-904`, `T-aiorg_pm_bot-916` 등 복수의 태스크에서 동일 패턴의 `exit code 143`이 반복 발생했다.

```
Command failed with exit code 143 (exit code: 143)
Error output: Check stderr output for details
```

**exit code 143 = 128 + 15(SIGTERM)**: 프로세스가 외부에서 `SIGTERM` 신호를 받아 종료됨.

### 1.2 근본 원인 분석 (리서치실 T-915 결과)

| # | 원인 계층 | 설명 |
|---|-----------|------|
| **C-01** | SDK hang watchdog 취소 | `claude_agent_sdk`의 hang watchdog이 복잡 태스크 감지 시 `asyncio.CancelledError` 전파 |
| **C-02** | CancelledError 전파 | Python asyncio 취소 신호가 subprocess까지 전달됨 |
| **C-03** | SDK graceful shutdown | SDK 종료 과정에서 subprocess에 `SIGTERM` 전송 → exit 143 |
| **C-04** | 하드코딩 타임아웃** | `amp_caller.py`의 120s 하드코딩 — 복잡 구현 태스크의 실제 소요 시간 초과 |
| **C-05** | 연쇄 종료** | 운영실 후속 태스크(T-904)가 동일 패턴으로 2차 SIGTERM 수신 |

> **C-04는 즉시 수정 가능한 단기 원인**, C-01~C-03은 SDK 레벨 설계 제약 (중장기 대응 필요)

### 1.3 현행 타임아웃 설정 현황

| 컴포넌트 | 현행 타임아웃 | 설정 방식 | 위험도 |
|----------|-------------|----------|--------|
| `amp_caller.py` | **120s 하드코딩** | 코드 내 고정값 | 🔴 HIGH |
| `preflight_check.py` | 120s (DEFAULT) | 코드 상수 | 🟠 MEDIUM |
| `claude_code_runner.py` | 14400s (4h) | env: `CLAUDE_DEFAULT_TIMEOUT_SEC` | 🟢 LOW |
| `codex_runner.py` | 1800s (30m) | env: `CODEX_DEFAULT_TIMEOUT_SEC` | 🟡 MEDIUM |
| `gemini_cli_runner.py` | 1800s (30m) | env: `GEMINI_CLI_DEFAULT_TIMEOUT_SEC` | 🟡 MEDIUM |
| orchestration hang_watchdog | 60s (추정) | orchestration.yaml | 🔴 HIGH |

---

## 2. 정책 목표 및 범위

### 2.1 정책 목표

1. **단기(~2026-04-07)**: `amp_caller.py` 하드코딩 제거 + 경보 레벨 도입
2. **중기(~2026-04-21)**: hang watchdog 임계값 재조정 + 사전 경보 알림 구현
3. **장기(~2026-05-31)**: SDK graceful shutdown 개선 + 태스크 유형별 동적 타임아웃 정책

### 2.2 적용 범위

- 모든 `claude_agent_sdk` 기반 태스크 실행 경로
- `amp_caller.py`, `claude_code_runner.py`, `codex_runner.py`, `gemini_cli_runner.py`
- orchestration.yaml hang_watchdog 설정
- E2E 테스트 타임아웃 설정

### 2.3 범위 외 항목

- SDK 내부 코드 수정 (외부 라이브러리)
- 텔레그램 Bot API 직접 호출 경로

---

## 3. 타임아웃 임계값 기준 (서비스별/단계별)

### 3.1 태스크 유형별 타임아웃 기준표

| 태스크 유형 | 예시 | 권장 타임아웃 | 현행 | 변경 필요 |
|------------|------|-------------|------|---------|
| **단순 조회/보고** | 리서치, 분석 보고 | 300s (5분) | 120s | ✅ 변경 |
| **기획/문서 작성** | PRD, 가이드라인 작성 | 600s (10분) | 120s | ✅ 변경 |
| **코드 구현 (소형)** | 단일 파일 수정 | 900s (15분) | 120s | ✅ 변경 |
| **코드 구현 (중형)** | 모듈 작성, 리팩토링 | 1800s (30분) | 120s | ✅ 변경 |
| **코드 구현 (대형)** | 전체 기능 구현 | 3600s (1시간) | 14400s | 🟢 유지 |
| **E2E 테스트** | 전체 회귀 테스트 | 600s (10분) | 120s | ✅ 변경 |
| **배포/운영 작업** | 재기동, 배포 | 300s (5분) | 120s | ✅ 변경 |

> **기준 원칙**: 실제 95th percentile 완료 시간 × 1.5 배율 적용

### 3.2 hang_watchdog 기준값 재설계

| 단계 | 현행 | 권장 | 근거 |
|------|------|------|------|
| 소형 태스크 무응답 감지 | 60s | **120s** | 단순 조회도 LLM 응답 시간 고려 |
| 중형 태스크 무응답 감지 | 60s | **300s** | 코드 구현 중간 단계 정상 소요 |
| 대형 태스크 무응답 감지 | 60s | **600s** | 복잡 구현 태스크 연속 실행 허용 |
| 전체 총 타임아웃 | 120s | **태스크 유형별 위 기준표 적용** | - |

### 3.3 즉시 적용 권장 변경사항

```
# amp_caller.py 하드코딩 제거 → 환경변수화
AMP_DEFAULT_TIMEOUT_SEC = int(os.environ.get("AMP_DEFAULT_TIMEOUT_SEC", "600"))

# preflight_check.py 상수 조정
_DEFAULT_TIMEOUT = 300  # 120 → 300

# orchestration.yaml hang_watchdog 기준 (개발실 협의 후 반영)
hang_watchdog:
  simple_task: 120s
  complex_task: 300s
  implementation_task: 600s
```

---

## 4. 사전 경보 조건 (경보 레벨·트리거·알림 채널)

### 4.1 경보 레벨 정의

| 레벨 | 이름 | 조건 | 트리거 임계값 | 알림 채널 |
|------|------|------|-------------|----------|
| ⚠️ **WARN-80** | 조기 경보 | 태스크 실행 시간 ≥ 타임아웃의 **80%** | 예: 600s 기준 → 480s 경과 | 텔레그램 채팅방 (INFO) |
| 🔴 **WARN-95** | 긴급 경보 | 태스크 실행 시간 ≥ 타임아웃의 **95%** | 예: 600s 기준 → 570s 경과 | 텔레그램 채팅방 (CRITICAL) |
| 💀 **TIMEOUT** | 타임아웃 종료 | 타임아웃 100% 도달 → 강제 종료 | - | 텔레그램 에러 리포트 |
| 🔁 **RETRY** | 재시도 경보 | 동일 태스크 3회 이상 exit 143 | 연속 실패 횟수 기준 | 텔레그램 + 관리자 알림 |

### 4.2 트리거 조건 상세

```yaml
# 경보 조건 정의 (정책 기준)
alert_conditions:
  warn_80:
    trigger: elapsed_time >= timeout * 0.80
    action: log_warn + telegram_notify(level=INFO)
    message: "⚠️ [{task_id}] 실행 시간 {elapsed}s — 타임아웃 {timeout}s의 80% 도달. 완료 대기 중."

  warn_95:
    trigger: elapsed_time >= timeout * 0.95
    action: log_critical + telegram_notify(level=CRITICAL)
    message: "🔴 [{task_id}] 실행 시간 {elapsed}s — 타임아웃 {timeout}s의 95% 도달. 5% 내 강제 종료 예정."

  exit_143_detected:
    trigger: exit_code == 143
    action: log_error + telegram_error_report + increment_failure_counter
    message: "💀 [{task_id}] exit code 143 발생. SIGTERM 수신. 런북 절차 시작."

  retry_alert:
    trigger: failure_counter[task_type] >= 3
    action: escalate + telegram_critical + pause_dispatch
    message: "🔁 [{task_type}] 동일 유형 3회 연속 exit 143. 디스패치 일시 중단. 관리자 확인 필요."
```

### 4.3 알림 채널 매핑

| 상황 | 채널 | 담당 |
|------|------|------|
| WARN-80 (80% 경보) | 텔레그램 채팅방 INFO | 봇 자동 보고 |
| WARN-95 (95% 경보) | 텔레그램 채팅방 CRITICAL | 봇 자동 보고 |
| exit 143 발생 | 텔레그램 에러 리포트 | 봇 자동 보고 → PM 수신 |
| 3회 연속 실패 | 텔레그램 + PM 직접 알림 | PM 수동 조치 필요 |

---

## 5. 에러 대응 런북 (5단계 절차)

### RUNBOOK-143: Exit Code 143 (SIGTERM) 대응 절차

> **발동 조건**: 태스크 실행 중 `exit code 143` 감지
> **최초 대응 목표**: **감지 후 5분 이내 원인 확인, 15분 이내 조치 완료**

---

#### STEP 1: 감지 (Detect) — 0~1분

**자동 감지 조건**:
- 태스크 종료 시 `exit_code == 143` 확인
- `ERROR: Command failed with exit code 143` 로그 출력

**수동 감지 방법**:
```bash
# 최근 실패 태스크 확인
grep "exit code 143" logs/*.log | tail -20

# 프로세스 종료 이력 확인
grep "SIGTERM\|143" logs/bot_*.log | tail -20
```

**감지 시 즉시 기록**:
- 태스크 ID, 발생 시각, 태스크 유형
- 직전 타임아웃 설정값, 실제 실행 시간

---

#### STEP 2: 확인 (Confirm) — 1~5분

**원인 분류 체크리스트**:

| 체크 항목 | 명령 | 결과 해석 |
|----------|------|---------|
| ① 실행 시간 vs 타임아웃 비교 | 로그에서 `elapsed_time` 확인 | 초과 시 → C-04 (타임아웃 설정 문제) |
| ② hang_watchdog 로그 확인 | `grep "hang_watchdog\|CancelledError" logs/` | 감지 시 → C-01/C-02 (SDK watchdog) |
| ③ 태스크 복잡도 확인 | 태스크 유형 + 예상 소요 시간 검토 | 복잡 구현 태스크 → 타임아웃 기준 재검토 필요 |
| ④ 연속 실패 여부 확인 | 동일 태스크 유형 최근 실패 이력 | 3회 이상 → STEP 3-C 적용 |

**원인 코드 분류**:
- **P-01**: 타임아웃 값 부족 (실행 시간 > 설정값)
- **P-02**: hang_watchdog 오탐 (정상 실행 중 취소)
- **P-03**: 태스크 자체 hang (실제 무한 대기)
- **P-04**: SDK/인프라 레벨 문제 (재현 불가 일시적)

---

#### STEP 3: 조치 (Mitigate) — 5~15분

**P-01 (타임아웃 값 부족) 조치**:
```bash
# 환경변수로 즉시 타임아웃 확장 (재기동 없이 적용)
export AMP_DEFAULT_TIMEOUT_SEC=900      # amp_caller 600→900s
export CLAUDE_DEFAULT_TIMEOUT_SEC=7200  # claude_runner 유지 or 확장

# 태스크 재실행
# (orchestration 디스패처가 자동 재시도 or 수동 재트리거)
```

**P-02 (hang_watchdog 오탐) 조치**:
```bash
# orchestration.yaml hang_watchdog 임계값 임시 완화
# → 개발실에 COLLAB 요청: hang_watchdog simple→120s, complex→300s 변경
# 즉시 적용: 환경변수 오버라이드 사용
export HANG_WATCHDOG_TIMEOUT_SEC=300
```

**P-03 (실제 hang) 조치**:
```bash
# 해당 봇 프로세스 정상 종료 요청
bash scripts/request_restart.sh --reason "P-03 hang 감지: 태스크 {task_id}"

# 태스크 재실행 전 preflight 체크
python tools/preflight_check.py
```

**P-04 (일시적 문제) 조치**:
- 5분 대기 후 동일 태스크 재시도 1회
- 재시도 후 동일 증상 → P-01/P-02로 재분류

---

#### STEP 4: 복구 (Recover) — 15~30분

**태스크 재실행 절차**:
1. STEP 3 조치 완료 확인
2. preflight 체크 통과 확인: `python tools/preflight_check.py`
3. 실패 태스크 재트리거 (orchestration 디스패처 또는 수동)
4. 재실행 중 WARN-80 경보 모니터링
5. 성공 종료 (exit 0) 확인

**재실행 실패 시**:
- 태스크를 더 작은 단위로 분할 검토
- 타임아웃을 해당 태스크 유형 상한값까지 확장
- 여전히 실패 → 개발실 에스컬레이션

---

#### STEP 5: 사후 보고 (Post-mortem) — 30분~24시간

**즉시 보고 (30분 내)**:
- 텔레그램 채팅방에 간단 요약 보고:
  ```
  [exit 143 대응 완료]
  태스크: {task_id}
  원인 분류: P-0X
  조치 내용: 타임아웃 {before}s → {after}s 변경
  복구 결과: 재실행 {success/fail}
  ```

**정식 사후 보고 (24시간 내)**:
- 원인 코드, 임시 조치, 영구 조치 계획
- 동일 유형 재발 방지를 위한 기준표 업데이트 여부 결정
- `error-gotcha` 스킬 실행하여 스킬 파일에 교훈 기록

---

## 6. 정책 적용 우선순위 및 예외 처리

### 6.1 적용 우선순위 (시행 일정)

| 우선순위 | 항목 | 담당 | 목표일 | 방식 |
|---------|------|------|--------|------|
| **P0** | `amp_caller.py` 하드코딩 제거 → 환경변수화 | 개발실 | 2026-04-03 | 코드 수정 |
| **P0** | 경보 레벨 (80%/95%) 로깅 구현 | 개발실 | 2026-04-03 | 코드 수정 |
| **P1** | orchestration hang_watchdog 기준값 재조정 | 개발실+운영실 | 2026-04-07 | yaml 수정 |
| **P1** | preflight_check.py 기본 타임아웃 300s 조정 | 개발실 | 2026-04-07 | 코드 수정 |
| **P2** | 태스크 유형별 동적 타임아웃 자동 선택 로직 | 개발실 | 2026-04-21 | 기능 개발 |
| **P2** | 3회 연속 실패 시 디스패치 일시 중단 로직 | 개발실 | 2026-04-21 | 기능 개발 |
| **P3** | SDK hang watchdog 장기 개선 검토 | 개발실 | 2026-05-31 | 아키텍처 검토 |

### 6.2 예외 처리 규칙

| 예외 상황 | 처리 방법 |
|----------|----------|
| 사용자가 명시적으로 긴 태스크 요청 | 해당 태스크 타임아웃을 3600s로 임시 확장 허용 |
| CI/CD 환경에서의 E2E 테스트 | CI 환경변수 `CI_TIMEOUT_OVERRIDE=true` 설정 시 600s 적용 |
| 긴급 운영 배포 (핫픽스) | 타임아웃 정책 예외 허용 + 사후 보고 필수 |
| SDK 업데이트 직후 | 72시간 모니터링 강화 기간 운영, 임계값 25% 완화 |

---

## 7. 부서 간 검토 의견 반영 요약표

| # | 검토 관점 | 피드백 항목 | 반영 여부 | 비고 |
|---|---------|-----------|---------|------|
| 1 | **개발실** (실현 가능성) | `amp_caller.py` 하드코딩 → 환경변수화 즉시 가능 | ✅ 반영 (P0) | 코드 2줄 수정 수준 |
| 2 | **개발실** (실현 가능성) | 경보 레벨 80%/95% — asyncio elapsed_time 측정 가능 | ✅ 반영 (P0) | `time.monotonic()` 활용 |
| 3 | **개발실** (실현 가능성) | 태스크 유형별 동적 타임아웃 — orchestration.yaml 태스크 메타 활용 | ✅ 반영 (P2) | 중기 개발 필요 |
| 4 | **운영실** (모니터링 연동) | 경보를 OPS-RUNBOOK-v1.md 알림 레벨과 통합 | ✅ 반영 | WARN-80 → INFO / WARN-95 → CRITICAL 매핑 |
| 5 | **운영실** (모니터링 연동) | preflight 로그 헤더에 타임아웃 기준값 자동 기록 | ✅ 반영 (P1) | `[PREFLIGHT] timeout_policy=...` 헤더 추가 |
| 6 | **운영실** (모니터링 연동) | 3회 연속 실패 시 watchdog이 자동 에스컬레이션 | ✅ 반영 (P2) | bot_watchdog.py 연동 검토 |

---

## 8. 정책 시행 일정

```
2026-04-03  P0 완료: amp_caller 환경변수화 + 80%/95% 경보 로깅
2026-04-07  P1 완료: hang_watchdog 재조정 + preflight 300s
             → 본 PRD v1.0 정식 발효
2026-04-21  P2 완료: 동적 타임아웃 + 연속 실패 중단 로직
2026-05-31  P3 검토 완료: SDK 장기 개선 방향 결정
```

---

## 9. 용어 정의

| 용어 | 정의 |
|------|------|
| exit code 143 | SIGTERM 신호 수신으로 인한 프로세스 종료 (128 + signal 15) |
| SIGTERM | 프로세스에 정상 종료를 요청하는 Unix 신호 |
| hang_watchdog | `claude_agent_sdk` 내 무응답 프로세스 감지·취소 컴포넌트 |
| asyncio.CancelledError | Python asyncio 이벤트 루프에서 태스크 취소 시 발생하는 예외 |
| WARN-80/95 | 타임아웃 임계값 대비 80%/95% 경과 시 발동하는 사전 경보 레벨 |
| P-01~P-04 | 런북 원인 코드: 타임아웃 부족/오탐/실제hang/일시적 문제 |

---

*이 문서는 기획실(aiorg_product_bot)이 작성했습니다.*
*개발실·운영실 실현 가능성 검토 후 Rocky 최종 승인으로 발효됩니다.*
