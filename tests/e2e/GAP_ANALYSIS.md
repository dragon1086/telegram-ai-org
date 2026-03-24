# E2E 테스트 갭 분석 보고서

> 작성일: 2026-03-25
> 분석 대상: `tests/e2e/test_engine_compat_e2e.py`, `tests/e2e/test_pm_dispatch_e2e.py`

---

## 1. 현재 커버리지 현황

### 1.1 test_engine_compat_e2e.py (47개 테스트)

| 클래스 | 케이스 수 | 커버 엔진 | 비고 |
|---|---|---|---|
| TestEngineInstantiation | 4 | claude-code, codex, gemini-cli | 기본 생성 OK |
| TestRunContextInterface | 8 | 전체 parametrized | run/capabilities/metrics 인터페이스 |
| TestGeminiCLISpecific | 4 | gemini-cli | sanitize/extract_json/모델 검증 |
| TestBotEngineAssignment | 3 | organizations.yaml | 리서치/성장/운영실 엔진 |
| TestBaseRunnerMethods | 5 | _ConcreteRunner | run_single/run_task |
| TestRunnerErrorHierarchy | 6 | 공통 | Error 계층 |
| TestRunnerFactoryExtended | 4 | 공통 | register/create/fallback |
| TestGeminiCLIRunnerDispatch | 10 | gemini-cli | mock subprocess 기반 10개 시나리오 |

### 1.2 test_pm_dispatch_e2e.py (12개 테스트)

| 클래스 | 케이스 수 | 커버 항목 | 비고 |
|---|---|---|---|
| TestNLClassifier | 3 | 분류기 인텐트 | 개발/디자인/리서치 |
| TestPMRouter | 3 | PMRouter 인스턴스 + 상수 | KNOWN_DEPTS, BOT_ENGINE_MAP |
| TestDispatchEngine | 1 | 시그니처 검증 | 실 인스턴스화 없음 |
| TestContextWindow | 2 | 컨텍스트 창 생성 | empty / with messages |
| TestOrchestrationConfig | 3 | YAML 유효성 | orchestration.yaml + organizations.yaml |

---

## 2. 식별된 갭 (누락 테스트)

### 2.1 엔진별 mock 기반 dispatch 테스트 불균형

| 엔진 | mock dispatch 테스트 수 | 상태 |
|---|---|---|
| gemini-cli | 10개 (TestGeminiCLIRunnerDispatch) | ✅ 충분 |
| codex | **0개** | ❌ 누락 |
| claude-code | **0개** | ❌ 누락 |

**필요 추가:**
- `TestCodexRunnerDispatch`: run() 정상/에러/타임아웃/FileNotFoundError/model파라미터/capabilities/sanitize 검증
- Claude는 subprocess mock이 복잡하므로 ClaudeSubprocessRunner 인터페이스 검증 수준으로 추가

### 2.2 PM 디스패치: 조직별 엔진 배정 전체 검증 누락

현재 organizations.yaml 엔진 배정 테스트:
- `test_research_and_growth_use_gemini` → research + growth 2개만 검증
- `test_ops_uses_codex` → ops 1개만 검증
- **pm_bot, engineering_bot, design_bot, product_bot** → **미검증**

**필요 추가:**
- 7개 전 조직 엔진 배정 parametrized 테스트

### 2.3 BOT_ENGINE_MAP 완결성 검증 누락

현재 `test_bot_engine_map_loaded`는 len > 0만 검증.
- 각 봇 ID가 맵에 존재하는지 미검증
- 값이 유효한 엔진명인지 미검증
- gemini-cli/codex 보트 정확성 미검증

### 2.4 크로스팀 협업 엔진 전환 시나리오 누락

PM → 다른 부서(엔진 다름) 협업 시 RunnerFactory가 올바른 엔진을 생성하는지 미검증.

### 2.5 conftest.py 공통 픽스처 부족

| 부족 항목 | 영향 |
|---|---|
| 엔진별 RunContext 픽스처 | 각 테스트가 수동으로 RunContext 생성 |
| 엔진 가용성 skip 헬퍼 | CLI 미설치 환경에서 명확한 SKIP 없음 |
| mock subprocess 재사용 픽스처 | TestGeminiCLIRunnerDispatch._make_mock_proc() 중복 |
| standard I/O 검증 헬퍼 | run() 결과 타입/내용 공통 검증 없음 |
| fixtures/ 디렉토리 | 엔진별 mock 응답 데이터 없음 |

### 2.6 CodexRunner 인터페이스 불일치

- `CodexRunner.get_last_run_metrics()` vs BaseRunner 표준 `get_last_metrics()` 불일치
- `CodexRunner.get_last_metrics()`는 BaseRunner 기본값(`{}`)만 반환 — 런타임 메트릭 누락

---

## 3. 보완 계획

### Phase 2: conftest.py 보완
- `make_run_context` 픽스처 추가
- `mock_proc_factory` 픽스처 추가
- `validate_run_result` 헬퍼 추가
- `engine_available` 조건부 skip 헬퍼 추가
- `tests/e2e/fixtures/` 디렉토리 + mock 데이터 파일 추가

### Phase 3: test_engine_compat_e2e.py 보완
- `TestCodexRunnerDispatch` 클래스 (8개 테스트)
- `TestClaudeRunnerInterface` 클래스 (3개 테스트)

### Phase 4: test_pm_dispatch_e2e.py 보완
- `TestEngineRoutingAllOrgs` (7개 parametrized)
- `TestBotEngineMapCompleteness` (4개)
- `TestCrossTeamCollabEngineSwitch` (5개)

---

## 4. 요약

| 항목 | 현재 | 보완 후 목표 |
|---|---|---|
| 총 테스트 수 | 59개 | ~83개 |
| codex mock dispatch 커버리지 | 0% | 8개 |
| PM 라우팅 조직별 검증 | 3/7 조직 | 7/7 조직 |
| conftest 공통 픽스처 | 4개 | 10개+ |
| fixtures/ 디렉토리 | 없음 | 3개 파일 |
