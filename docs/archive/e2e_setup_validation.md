# E2E Setup Validation — 원클릭 셋팅 플로우 검증 보고서

> 작성일: 2026-04-01
> 대상 브랜치: `fix/auto-2026-03-30-telegram_relay`
> 검증 범위: `bash scripts/setup.sh` 원클릭 플로우 전체

---

## 1. 원클릭 설치 플로우 개요

```
bash scripts/setup.sh
    │
    ├── [Step 1] Python 3.10+ 탐색 & 가상환경 생성 (.venv)
    ├── [Step 2] pip 업그레이드 + pyproject.toml 의존성 설치
    │            pip install -e ".[dev]"  ─── requirements.txt 상당
    ├── [Step 3] .env 파일 생성 (없으면 .env.example 복사)
    ├── [Step 4] 엔진 CLI 자동 감지
    │            claude / codex / gemini 순서 탐색
    ├── [Step 5] Docker 환경 감지 + compose 명령 안내
    ├── [Step 6] agency-agents 설치 (~/.claude/agents/)
    ├── [Cold-start] cold_start_benchmark.py 자동 실행  ← 신규 추가
    └── [완료] 엔진 요약표 출력 + 다음 단계 안내
```

---

## 2. Pre-flight 체크 항목 (conftest.py 연동)

> 출처: `tests/e2e/conftest.py` `_print_preflight_header()`

| 체크 항목 | 검증 방법 | 통과 기준 |
|----------|----------|---------|
| Python 버전 | `sys.version_info >= (3, 10)` | 3.10+ |
| .env 파일 존재 | `Path(".env").exists()` | 파일 존재 |
| GROUP_CHAT_ID 설정 | `os.environ.get("GROUP_CHAT_ID")` | 비어있지 않음 |
| 엔진 경로 최소 1개 | CLAUDE_PATH / CODEX_PATH / GEMINI_CLI_PATH | 1개 이상 존재 |
| pyproject.toml 파싱 | `tomllib.open("pyproject.toml")` | 파싱 성공 |

### 2.1 E2E 테스트 차단 조건 (SystemExit)

`conftest.py`의 pre-flight 검사는 테스트 실행 전 자동 수행됨.
아래 조건 충족 시 `pytest.exit()` 또는 `sys.exit(1)` 호출로 전체 테스트 스위트 차단:

- GROUP_CHAT_ID 미설정 (REQUIRED)
- 엔진 경로 0개 감지 (REQUIRED)
- `.env` 파일 없음 (REQUIRED)

---

## 3. 환경변수 검증 (env_validator.py)

> 도구: `tools/env_validator.py` (신규 추가)

```bash
# 기본 검증 (REQUIRED 항목만)
python tools/env_validator.py

# strict 모드 (RECOMMENDED 포함)
python tools/env_validator.py --strict
```

### 검증 계층 정의

| Severity | 항목 | 누락 시 동작 |
|----------|------|------------|
| REQUIRED | PM_BOT_TOKEN, GROUP_CHAT_ID, 엔진경로 1개 | EnvValidationError → exit 1 |
| RECOMMENDED | DEV_BOT_TOKEN, CLAUDE_PATH | 경고 출력 (strict 모드: exit 1) |
| OPTIONAL | DESIGN_BOT_TOKEN, PLAN_BOT_TOKEN 등 | 정보성 메시지 |

---

## 4. 설치 검증 체크리스트

### 4.1 로컬 환경 (macOS / Linux)

- [ ] `bash scripts/setup.sh` 정상 완료 (exit 0)
- [ ] `.venv/` 디렉토리 생성됨
- [ ] `python tools/cold_start_benchmark.py` 실행 가능
- [ ] `python tools/env_validator.py` exit 0 반환
- [ ] `python -m pytest tests/ -x -q` 통과 (279개 이상)
- [ ] `.env` 파일 생성됨 (`.env.example` 기반)
- [ ] 엔진 경로 최소 1개 감지됨 (setup.sh 요약표 확인)

### 4.2 Docker 환경

- [ ] `docker build -t telegram-ai-org .` 성공
- [ ] `.dockerignore` 적용 확인 (`.env`, `.git`, `.venv` 제외)
- [ ] `docker compose --profile claude up -d` 정상 기동
- [ ] 컨테이너 내부 `python tools/env_validator.py` exit 0

### 4.3 CI/CD (GitHub Actions)

- [ ] `.github/workflows/ci.yml` pytest 단계 통과
- [ ] `pip install -e ".[test]"` 성공
- [ ] `pytest tests/ -m "not integration"` 통과

---

## 5. Cold-start 성능 검증

> 기준: `docs/benchmark_results.md` Before/After 비교표

| 검증 항목 | 목표값 | 실측값 (2026-04-01) | 통과 여부 |
|---------|--------|-------------------|---------|
| 핵심 의존성 total cold-start | < 700 ms | ~555.5 ms | PASS |
| 최대 단일 모듈 (핵심 의존성) | < 300 ms | 233.8 ms (mcp) | PASS |
| 엔진 SDK 제외 시 절감율 | > 50% | 59.7% | PASS |

---

## 6. setup.sh 변경 사항 (신규)

`scripts/setup.sh` 완료 메시지 출력 직전에 cold-start 벤치마크 단계 삽입:

```bash
# Cold-start 벤치마크 자동 실행
step "Cold-start 성능 측정"
if python tools/cold_start_benchmark.py 2>/dev/null; then
    ok "Cold-start 벤치마크 완료"
else
    warn "벤치마크 실패 (선택 사항 — 설치는 정상)"
fi
```

- 벤치마크 실패 시 `warn` (비차단) — 설치 자체는 영향 없음
- 벤치마크 성공 시 각 모듈 ms 수치 콘솔 출력

---

## 7. 파일 목록 (신규 산출물)

| 파일 경로 | 설명 |
|----------|------|
| `requirements.txt` | 핵심 의존성 (pip 형식) |
| `requirements-optional.txt` | 엔진별 선택 의존성 |
| `tools/cold_start_benchmark.py` | 모듈 import 시간 벤치마크 |
| `tools/env_validator.py` | 환경변수 검증 모듈 |
| `docs/dependency_audit_report.md` | 의존성 감사 보고서 |
| `docs/benchmark_results.md` | Before/After 벤치마크 결과 |
| `docs/e2e_setup_validation.md` | 이 문서 — 원클릭 플로우 검증 |

---

*이 문서는 Phase 1~4 경량화 + 원클릭 셋팅 구현 태스크의 검증 기록임.*
