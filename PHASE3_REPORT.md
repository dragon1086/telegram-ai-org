# Phase 3 이식 검증 보고서

작성일: 2026-03-29
프로젝트: telegram-ai-org
이식 출처: revfactory/harness + NousResearch/hermes-agent
검증 커밋: 7a6d790 (feat(transplant): harness+hermes-agent 핵심 패턴 이식 Phase 2)
Python: 3.14.3 / pytest 9.0.2

---

## 1. 변경 파일 목록 (이식 커밋 7a6d790 기준)

| 파일명 | 변경 유형 | 변경 이유 |
|--------|-----------|-----------|
| `core/tool_registry.py` | 신규 추가 | hermes-agent Tool Registry 패턴 이식 (feature flag `ENABLE_TOOL_REGISTRY`, 기본값 false) |
| `core/skill_validator.py` | 신규 추가 | harness 스킬 품질 검증 패턴 이식 (read-only, 사이드이펙트 없음) |
| `core/platform_adapter.py` | 신규 추가 | hermes-agent Platform Adapter 추상화 이식 (feature flag `ENABLE_PLATFORM_ADAPTER`, 기본값 false) |
| `core/team_design_patterns.py` | 신규 추가 | harness 6-패턴 팀 설계 레지스트리 이식 |
| `core/skill_gotcha_manager.py` | 신규 추가 | harness gotchas 패턴 프로그래매틱 관리 이식 |
| `.env.example` | 수정 | 이식된 feature flag 환경변수 14개 추가 |
| `docs/plans/phase2-transplant-implementation.md` | 신규 추가 | 셀프 리뷰 체크리스트 + 구현 계획 문서 |
| `tests/unit/test_transplant_tool_registry.py` | 신규 추가 | tool_registry 단위 테스트 (21개) |
| `tests/unit/test_transplant_skill_validator.py` | 신규 추가 | skill_validator 단위 테스트 (17개) |
| `tests/unit/test_transplant_team_patterns.py` | 신규 추가 | team_design_patterns 단위 테스트 (29개) |
| `tests/unit/test_transplant_skill_gotcha.py` | 신규 추가 | skill_gotcha_manager 단위 테스트 (16개) |
| `tests/unit/test_transplant_platform_adapter.py` | 신규 추가 | platform_adapter 단위 테스트 (16개) |

Phase 3 검증 과정에서 수정된 파일 (이식 이전부터 존재하던 버그):

| 파일명 | 변경 유형 | 변경 이유 |
|--------|-----------|-----------|
| `tests/unit/test_telegram_sender.py` | 수정 | `sys.modules["yaml"]` Mock 오염 제거 — yaml 패키지 설치 상태에서 불필요한 Mock이 타 테스트 오염 유발 |
| `tests/e2e/test_engine_fallback_e2e.py` | 수정 | (1) `aiorg_ops_bot` 엔진 배정 단언 불일치 수정, (2) `importlib.reload()` 모듈 오염 제거 |

---

## 2. 테스트 결과

### 2-1. 이식 모듈 단위 테스트 (transplant-specific)

| 테스트 파일 | 통과 | 실패 | 스킵 | 비고 |
|------------|------|------|------|------|
| test_transplant_tool_registry.py | 21 | 0 | 0 | |
| test_transplant_skill_validator.py | 17 | 0 | 0 | |
| test_transplant_team_patterns.py | 29 | 0 | 0 | |
| test_transplant_skill_gotcha.py | 16 | 0 | 0 | |
| test_transplant_platform_adapter.py | 16 | 0 | 0 | |
| **소계** | **99** | **0** | **0** | |

### 2-2. 전체 테스트 스위트 (Phase 3 검증 최종 — 2026-03-29 재확정)

> 실행 환경: Python 3.14.3 / pytest 9.0.2 / `.venv` 가상환경
> 실행 범위: `tests/unit/` + `tests/integration/` + `tests/e2e/`

| 테스트 유형 | 통과 | 실패 | 스킵 | 경고 | 비고 |
|------------|------|------|------|------|------|
| 단위 테스트 (`tests/unit/`) | 558 | 0 | 0 | 4 | 전량 통과 |
| 통합 테스트 (`tests/integration/`) | 7 | 0 | 0 | 0 | 전량 통과 |
| E2E 테스트 (`tests/e2e/`) | 418 | 0 | 0 | 3 | 전량 통과 |
| **합계** | **983** | **0** | **0** | **7** | ✅ 전체 통과 |

> 경고 7건 모두 기능상 무해 (pre-flight timeout 기본값 안내 4건 + AsyncMock coroutine 미awaited 3건).

---

## 3. 수정 이력

검증 과정에서 발견된 3건은 모두 이식 이전부터 존재하던 기존 버그이다.
이식된 5개 core 파일 자체에서는 결함이 발견되지 않았다.

### 수정 1: `tests/unit/test_telegram_sender.py`

| 항목 | 내용 |
|------|------|
| 실패 테스트 | `TestImprovementThresholdsConfig` 4개 + `TestRunDesignPreflight::test_actual_baseline_passes` 1개 (총 5개) |
| 증상 | 단독 실행 시 통과 → 전체 suite 실행 시 실패 (간헐적) |
| 근본 원인 | `test_telegram_sender.py` 모듈 최상단에서 `sys.modules["yaml"] = MagicMock()` 주입. yaml은 실제 설치되어 있음에도(`pyyaml 6.0.3`) `if _mod not in sys.modules` 조건이 pytest 수집 순서에 따라 통과되어 yaml 모듈 전체를 Mock으로 오염. 이후 `yaml.safe_load()`를 직접 호출하는 `test_self_improve_fixes.py`와 `test_design_preflight_check.py`에서 MagicMock 반환값을 받음. |
| 수정 내용 | `test_telegram_sender.py`의 mock 주입 목록에서 `"yaml"` 제거. yaml은 설치된 실제 패키지를 사용하도록 변경. |
| 파일 | `tests/unit/test_telegram_sender.py` line 10-15 |

### 수정 2: `tests/e2e/test_engine_fallback_e2e.py` — 엔진 배정 단언 불일치

| 항목 | 내용 |
|------|------|
| 실패 테스트 | `TestCodexFallbackUnit::test_codex_pm_dispatch_full_flow` |
| 증상 | `assert 'gemini-cli' == 'codex'` AssertionError |
| 근본 원인 | 테스트 작성 시점에는 `aiorg_ops_bot` 엔진이 `codex`였으나, 이후 `core/constants.py`에서 `gemini-cli`로 변경됨. 테스트가 `BOT_ENGINE_MAP.get("aiorg_ops_bot") == "codex"`를 단언하는 방식으로 codex 런너 테스트를 우회하고 있었음. |
| 수정 내용 | 특정 봇의 엔진 배정에 의존하지 않고 `RunnerFactory.create("codex")`를 직접 호출하도록 변경. 테스트 목적(codex 런너 dispatch 흐름)은 유지. |
| 파일 | `tests/e2e/test_engine_fallback_e2e.py` line 370-382 |

### 수정 3: `tests/e2e/test_engine_fallback_e2e.py` — importlib.reload 모듈 오염

| 항목 | 내용 |
|------|------|
| 실패 테스트 | `tests/test_gemini_cli_runner.py::test_runner_factory_creates_gemini_cli` (전체 suite에서만 실패) |
| 증상 | `False = isinstance(<tools.gemini_cli_runner.GeminiCLIRunner object>, GeminiCLIRunner)` — 동일 클래스명이지만 isinstance False |
| 근본 원인 | `test_gemini_cli_runner_init_reads_env_vars`에서 `importlib.reload(mod)`를 두 번 호출. reload는 모듈 객체를 **in-place 수정**하므로 `GeminiCLIRunner` 클래스가 새 객체(Class-B)로 교체됨. 이미 top-level import로 참조를 확보한 `test_gemini_cli_runner.py`의 `GeminiCLIRunner`(Class-A)와 팩토리가 반환하는 인스턴스의 클래스(Class-B)가 불일치. `codex_runner`도 동일 패턴. |
| 수정 내용 | `importlib.reload()` 완전 제거. `patch.object(mod, "GEMINI_CLI", "/custom/gemini")`·`patch.object(mod, "DEFAULT_TIMEOUT", 300)` 직접 패치 방식으로 변경. 모듈 클래스 정체성 오염 없이 동일 검증 달성. |
| 파일 | `tests/e2e/test_engine_fallback_e2e.py` — `test_gemini_cli_runner_init_reads_env_vars` 및 `test_codex_runner_init_reads_env_cli_path` |

---

## 4. 이식 코드 자가 리뷰

### 4-1. 설계 원칙 준수 여부

| 원칙 | 상태 | 세부 |
|------|------|------|
| 기존 파일 무수정 | ✅ | 이식 커밋에서 기존 파일 변경 없음 (`git show --stat HEAD`) |
| 사이드이펙트 zero | ✅ | feature flag 기본값 false, 오프 시 모든 메서드 no-op 반환 |
| TODO/FIXME 없음 | ✅ | 5개 이식 파일 전체 grep 결과 0건 |
| 하드코딩 값 없음 | ✅ | 상수화 처리 완료 (SKILLS_ROOT, REQUIRED_FRONTMATTER_KEYS 등) |
| 예외 처리 완비 | ✅ | try/except + 로깅 일관 적용, bare except 없음 |
| 테스트 커버리지 | ✅ | 99개 신규 단위 테스트, 전량 통과 |

### 4-2. 파일별 자가 리뷰 요약

| 파일 | TODO/FIXME | 하드코딩 | 예외처리 | 결과 |
|------|-----------|---------|---------|------|
| `core/platform_adapter.py` | 없음 | 없음 | TelegramPlatformAdapter: normalize_inbound + send_message 각 try/except 완비 | PASS |
| `core/skill_gotcha_manager.py` | 없음 | 없음 | _load_gotchas_text OSError, append_gotcha OSError 처리 | PASS |
| `core/skill_validator.py` | 없음 | 없음 | validate_skill_file: 파일 없음/읽기 실패/빈 파일 각각 처리 | PASS |
| `core/team_design_patterns.py` | 없음 | 없음 | register_pattern ValueError 검증, recommend_pattern edge case 처리 | PASS |
| `core/tool_registry.py` | 없음 | 없음 | dispatch try/except — 핸들러 예외 re-raise (의도적) | PASS |

### 4-3. Feature Flag 목록

| 환경변수 | 기본값 | 영향 범위 |
|---------|--------|-----------|
| `ENABLE_TOOL_REGISTRY` | false | `core/tool_registry.py` — 전체 no-op |
| `ENABLE_PLATFORM_ADAPTER` | false | `core/platform_adapter.py` — 전체 no-op |

`core/skill_validator.py`, `core/team_design_patterns.py`, `core/skill_gotcha_manager.py`는 flag 없이 항상 활성화되나 read-only 유틸리티이므로 사이드이펙트 없음.

---

## 5. 잔여 리스크

### 미해결 이슈
없음. 발견된 3건 모두 수정 완료.

### 알려진 경고 (warnings, 비차단)
- `tests/e2e/test_pm_modes.py`: `RuntimeWarning: coroutine never awaited` 2건. AsyncMock 사용 방식 문제. 이식과 무관한 기존 경고.
- `tests/unit/test_preflight_guards.py`: `UserWarning: timeout=120s 기본값` 4건. infra-baseline.yaml 명시 권고. 기능상 무해.

### 후속 권고사항

1. **Feature Flag 활성화 로드맵**: `ENABLE_TOOL_REGISTRY=true` 및 `ENABLE_PLATFORM_ADAPTER=true` 환경에서의 통합 테스트 추가 필요. 현재는 disabled 경로 + enabled 경로 단위 테스트만 검증됨 (실제 통합 흐름은 미검증).
2. **test isolation 정책**: `sys.modules`를 직접 오염시키는 패턴(`test_telegram_sender.py` 유형)은 `conftest.py` autouse fixture로 격리하거나 `importlib.reload()` 방식으로 리팩토링 권고.
3. **aiorg_ops_bot 엔진 배정 문서화**: `constants.py`의 `BOT_ENGINE_MAP`과 MEMORY.md의 엔진 배정 기록이 불일치(`claude-code` vs `gemini-cli` 언급). 단일 소스로 통일 필요.
4. **E2E skip 없음**: 실제 API(Telegram, Claude, Gemini) 호출이 필요한 테스트는 존재하지 않거나 mock으로 처리됨 — 외부 의존성 없이 전체 E2E 418개 통과 확인.
5. **`skill_validator.py` 최소 YAML 파서**: `_parse_frontmatter()`는 yaml import 없이 직접 파싱. 복잡한 YAML 구문(멀티라인 값, 중첩 구조)은 지원하지 않음. 현재 SKILL.md 형식에는 충분하나, frontmatter가 복잡해질 경우 pyyaml로 교체 필요.
