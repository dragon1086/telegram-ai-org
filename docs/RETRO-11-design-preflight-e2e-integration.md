# RETRO-11: 디자인 Pre-flight → E2E 테스트 헤더 연동 방안

> **작성**: 디자인실 (aiorg_design_bot) | **작성일**: 2026-03-29
> **상태**: 연동 방안 확정 — 실제 코드 수정은 개발실 위임
> **참조**: `config/design-baseline.yaml v1.2`, `tests/e2e/conftest.py`

---

## 1. 배경 및 목표

운영실 conftest.py는 `_print_preflight_header()` 패턴으로 E2E 테스트 로그 최상단에
**인프라 pre-flight 결과를 자동 삽입**한다 (RETRO-09/10 완료).

디자인실은 이와 동일한 패턴으로 **디자인 렌더링 환경 pre-flight 결과**도
E2E 로그 헤더에 포함되도록 연동 방안을 확정한다.

---

## 2. 현행 운영실 패턴 분석

`tests/e2e/conftest.py`의 `_print_preflight_header()` 출력 형식:

```
==================================================
=== PRE-FLIGHT CHECK ===
==================================================
  baseline_version : v1.2
  timeout          : 120s
  filter           : <없음>
  env_vars         : [TELEGRAM_BOT_TOKEN, ...]
  checked_at       : 2026-03-29T00:00:00+00:00
  status           : ✅ PASS
--------------------------------------------------
```

---

## 3. 디자인 pre-flight 헤더 확장 방안

### 3-A. 헤더 블록 추가 항목

기존 인프라 헤더 **아래에** 디자인 전용 블록을 이어서 출력한다.

```
==================================================
=== DESIGN PRE-FLIGHT CHECK ===
==================================================
  design_baseline  : v1.2
  viewport         : desktop (1024px)
  font             : Pretendard / 16px
  theme            : light (WCAG AA, 4.5:1)
  token_version    : v1.0
  component_lib    : @aiorg/design-system@1.4.2
  blocking_checks  : 6 / 6 ✅ PASS
  warning_checks   : 8 / 8 ✅ PASS
  checked_at       : 2026-03-29T00:00:00+00:00
  status           : ✅ PASS
--------------------------------------------------
```

### 3-B. 구현 위치

| 파일 | 수정 내용 | 담당 |
|------|-----------|------|
| `tests/e2e/conftest.py` | `_print_design_preflight_header()` 함수 추가 | **개발실** |
| `tests/e2e/conftest.py` | `_run_preflight()` 내 디자인 체크 호출 추가 | **개발실** |
| `tools/design_preflight_check.py` | 디자인 pre-flight 실행 모듈 (신규) | **개발실** |

### 3-C. 신규 함수 명세 (디자인실 확정)

```python
def _print_design_preflight_header(result: dict) -> None:
    """디자인 pre-flight 결과를 E2E 로그 헤더 블록으로 출력.

    Parameters
    ----------
    result : dict
        {
          "design_baseline_version": "v1.2",
          "viewport": "desktop",
          "font": "Pretendard",
          "base_font_size": 16,
          "theme": "light",
          "wcag_level": "AA",
          "token_version": "v1.0",
          "component_lib_version": "1.4.2",
          "blocking_pass": 6,
          "blocking_total": 6,
          "warning_pass": 8,
          "warning_total": 8,
          "checked_at": "2026-03-29T00:00:00+00:00",
          "status": "PASS"  # "PASS" | "FAIL"
        }
    """
```

### 3-D. design_preflight_check.py 인터페이스 (디자인실 확정)

```python
def run_design_preflight_checks(
    baseline_path: str = "config/design-baseline.yaml",
    exit_on_fail: bool = True
) -> dict:
    """design-baseline.yaml PC-D-001~016 전체 체크 실행.

    Returns
    -------
    dict
        {
          "passed": bool,
          "blocking_results": [...],  # severity=blocking 체크 결과
          "warning_results": [...],   # severity=warning 체크 결과
          "info_results": [...],      # severity=info 체크 결과
          "design_baseline_version": str,
          "checked_at": str
        }
    """
```

---

## 4. SKIP 조건

| 환경변수 | 동작 |
|----------|------|
| `SKIP_DESIGN_PREFLIGHT=1` | 디자인 pre-flight 전체 건너뜀 |
| `SKIP_PREFLIGHT=1` | 인프라 + 디자인 pre-flight 모두 건너뜀 |

---

## 5. 개발실 위임 태스크 목록

1. `tools/design_preflight_check.py` 신규 생성 (위 인터페이스 기준)
2. `tests/e2e/conftest.py` — `_print_design_preflight_header()` 추가
3. `tests/e2e/conftest.py` — `_run_preflight()` 내 디자인 체크 호출
4. `tests/unit/test_design_preflight.py` 신규 생성 (PC-D-001~016 단위 테스트)

---

## 6. 검증 기준

- `pytest tests/e2e/ -v` 실행 시 E2E 로그 최상단에 `=== DESIGN PRE-FLIGHT CHECK ===` 헤더 출력
- blocking 체크 6개 전체 PASS
- SKIP_DESIGN_PREFLIGHT=1 환경변수로 우회 가능
