# E2E 테스트 — 실행 방법 및 커버리지 요약

> 마지막 업데이트: 2026-03-25 | 태스크 T-459

---

## 빠른 시작

```bash
# 가상환경 활성화 후 전체 E2E 실행 (mock 기반, 외부 의존성 없음)
.venv/bin/python -m pytest tests/e2e/ -m "not integration" -q

# 통합 테스트 포함 전체 실행 (실제 CLI 필요 — 없으면 자동 스킵)
.venv/bin/python -m pytest tests/e2e/ -q
```

---

## 파일 구성

| 파일 | 역할 | 테스트 수 |
|---|---|---|
| `test_engine_compat_e2e.py` | 3엔진 러너 인터페이스·mock dispatch | ~178개 |
| `test_pm_dispatch_e2e.py` | PM 오케스트레이션·BOT_ENGINE_MAP 검증 | ~85개 |
| `test_engine_fallback_e2e.py` | 3엔진 폴백·에러 처리·통합 레벨 실행 | 43개 |
| `conftest.py` | 공통 픽스처·헬퍼 | — |
| `fixtures/` | mock 응답 데이터 파일 | 3개 |

---

## 마커 분류

```bash
# 단위 테스트만 (가장 빠름, CI 기본)
pytest tests/e2e/ -m unit

# E2E 테스트만 (mock 기반)
pytest tests/e2e/ -m e2e

# 통합 테스트만 (실제 CLI 필요)
pytest tests/e2e/ -m integration

# 느린 테스트 제외
pytest tests/e2e/ -m "not slow"
```

### 마커 정의 (`pyproject.toml`)

| 마커 | 설명 | 외부 의존성 |
|---|---|---|
| `@pytest.mark.unit` | mock/stub 기반 순수 단위 테스트 | 없음 |
| `@pytest.mark.e2e` | E2E 플로우 (mock 엔진 사용) | 없음 |
| `@pytest.mark.integration` | 실제 CLI 바이너리 호출 | CLI 바이너리 필요 |
| `@pytest.mark.slow` | 실행 시간 30초+ | — |

---

## 3엔진별 실행 조건 및 스킵 규칙

| 엔진 | 환경변수 | 기본 명령 | 스킵 조건 |
|---|---|---|---|
| `gemini-cli` | `GEMINI_CLI_PATH` | `gemini` | PATH에 `gemini` 없음 |
| `codex` | `CODEX_CLI_PATH` | `codex` | PATH에 `codex` 없음 |
| `claude-code` | `CLAUDE_CLI_PATH` | `claude` | PATH에 `claude` 없음 |

통합 테스트(`@pytest.mark.integration`)는 해당 CLI가 없으면 **자동 스킵**됩니다.
수동으로 skip하려면:

```bash
# gemini-cli 통합 테스트 강제 스킵
GEMINI_CLI_PATH="" pytest tests/e2e/ -q
```

---

## CI 환경별 커맨드

### GitHub Actions (mock 기반만, 빠름)

```yaml
- name: E2E 테스트 실행
  run: |
    pip install -r requirements-test.txt
    pytest tests/e2e/ -m "not integration" -q --tb=short
```

### 로컬 개발 (전체, 통합 포함)

```bash
# 의존성 설치
pip install -r requirements-test.txt

# 전체 실행 (통합 테스트는 CLI 미설치 시 자동 스킵)
pytest tests/e2e/ -v

# 특정 엔진만
pytest tests/e2e/ -k "gemini" -v
pytest tests/e2e/ -k "codex" -v
pytest tests/e2e/ -k "claude" -v
```

### CI에서 통합 테스트 포함 실행 (CLI 설치 완료 후)

```bash
# Gemini CLI 설치
npm install -g @google/gemini-cli

# Codex CLI 설치
npm install -g @openai/codex

# Claude Code CLI 설치
npm install -g @anthropic-ai/claude-code

# 통합 테스트 포함 전체 실행
pytest tests/e2e/ -q --timeout=300
```

---

## 엔진별 커버리지 현황 (2026-03-25 기준)

### 4-시나리오 커버리지

| 시나리오 | claude-code | codex | gemini-cli |
|---|---|---|---|
| (1) 인스턴스 생성·초기화 검증 | ✅ | ✅ | ✅ |
| (2) 기본 태스크 실행·응답 포맷 | ✅ mock + integration | ✅ mock + integration | ✅ mock + integration |
| (3) 엔진 불가용 시 폴백·에러 처리 | ✅ | ✅ | ✅ |
| (4) PM 디스패치 → 엔진 실행 → 결과 반환 | ✅ | ✅ | ✅ |

### 테스트 레벨 분포

| 레벨 | 파일 | 수량 |
|---|---|---|
| 단위 (mock) | test_engine_compat_e2e.py + test_engine_fallback_e2e.py | 252개+ |
| PM 라우팅 (mock) | test_pm_dispatch_e2e.py | 85개+ |
| 통합 (실제 CLI) | test_engine_fallback_e2e.py | 6개 (CLI 없으면 자동 스킵) |
| **합계** | | **278개** |

---

## 공통 픽스처 (`conftest.py`)

| 픽스처 | 타입 | 설명 |
|---|---|---|
| `make_run_context` | factory | `RunContext` 팩토리 |
| `mock_proc_factory` | factory | asyncio subprocess mock |
| `gemini_json_response` | bytes | Gemini CLI JSON 응답 mock |
| `codex_plain_response` | bytes | Codex 응답 mock |
| `gemini_cli_available` | bool | Gemini CLI 가용 여부 |
| `codex_available` | bool | Codex CLI 가용 여부 |
| `engine_name` | str (params) | 3엔진 parametrize |
| `make_orchestrator` | factory | PMOrchestrator 팩토리 |

---

## 헬퍼 함수

```python
from tests.e2e.conftest import validate_run_result, validate_metrics, skip_if_cli_unavailable

# run() 결과 표준 검증
validate_run_result(result)  # str, 비어있지 않아야 함

# get_last_metrics() 표준 검증
validate_metrics(metrics)  # dict여야 함

# CLI 없으면 자동 스킵
skip_if_cli_unavailable("gemini", "GEMINI_CLI_PATH")
```
