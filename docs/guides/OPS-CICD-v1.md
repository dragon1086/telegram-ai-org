# CI/CD 파이프라인 설계서 — telegram-ai-org v1.0.0
> Phase 2 산출물 | 작성: 운영실(aiorg_ops_bot) | 날짜: 2026-03-29

---

## 1. 개요

PR → main 머지 → 배포까지의 전체 파이프라인을 정의한다.
핵심 원칙: **배포 전 항상 테스트. 인프라 변경은 단계적으로.**

---

## 2. 파이프라인 전체 흐름

```
[개발자 Push]
     │
     ▼
[PR 생성 → main]
     │
     ├─▶ [ci-lint.yml]  Ruff lint (빠른 피드백, ~1분)
     │
     └─▶ [ci.yml]  4단계 순차 검증
           │
           ├─ Job 1: Lint (ruff check + format check)
           ├─ Job 2: Unit Tests (pytest, e2e 제외)
           ├─ Job 3: Docker Build (이미지 빌드 검증)
           └─ Job 4: E2E Tests (pre-flight 포함, timeout 120s)
                         │
                         ▼
              [PR Merge → main 허용]
                         │
                         ▼
              [cd-main.yml]  메인 배포
```

---

## 3. CI 단계별 상세

### 3.1 Lint (ci.yml Job 1 / ci-lint.yml)
```yaml
- python -m ruff check telegram_ai_org
- python -m ruff format --check telegram_ai_org
```
- **실패 조건**: 린트 에러 / 포맷 불일치
- **소요시간**: ~1분
- **블로커**: 이후 모든 job 차단

### 3.2 Unit Tests (ci.yml Job 2)
```yaml
- pytest tests/unit/ --timeout=60 -v
```
- **실패 조건**: 단위 테스트 실패 (현재 12개)
- **소요시간**: ~2분
- **커버리지**: htmlcov/ 생성

### 3.3 Docker Build (ci.yml Job 3)
```yaml
- docker build -t telegram-ai-org .
```
- **실패 조건**: Dockerfile 빌드 에러
- **검증 항목**: 의존성 설치 성공 여부
- **소요시간**: ~3분 (캐시 활용 시 ~1분)

### 3.4 E2E Tests (ci.yml Job 4)
```yaml
# pre-flight 먼저 실행 (RETRO-01)
- bash scripts/preflight_check.sh
# E2E 전체 실행
- pytest tests/e2e/ --timeout=120 -v
```
- **실패 조건**: pre-flight FAIL 또는 E2E 테스트 실패
- **현재 통과 수**: 418개 E2E + 12개 단위 = **430개 전량 통과**
- **소요시간**: ~5~10분

---

## 4. CD 파이프라인 (cd-main.yml)

### 트리거 조건
```yaml
on:
  push:
    branches: [main]
```

### 배포 단계
1. **환경 검증**: infra-baseline.yaml 버전 확인
2. **pre-flight 실행**: `bash scripts/preflight_check.sh --fail-fast`
3. **서비스 재기동 요청**: `bash scripts/request_restart.sh --reason "CD 자동 배포"`
4. **헬스체크**: `python scripts/health_check.py`
5. **배포 완료 알림**: 텔레그램 채널 통보

---

## 5. Release 파이프라인 (release.yml)

### 트리거 조건
```yaml
on:
  push:
    tags: ['v*']
```

### 단계
1. 전체 테스트 스위트 재실행
2. GitHub Release 자동 생성 (changelog 포함)
3. PyPI 패키지 빌드 (publish-pypi.yml 연동)

**현황**: v1.0.0 릴리즈 2026-03-26 완료 (ST-11)

---

## 6. pre-flight → CI 연동 (RETRO-01 완성)

`tests/e2e/conftest.py`의 `_print_preflight_header()` 가 E2E 시작 전 자동 실행:
- infra-baseline.yaml 버전 로드
- timeout / filter 설정 검증
- E2E 로그 헤더에 자동 삽입 (RETRO-10)

```python
# conftest.py 핵심 로직
def pytest_configure(config):
    _print_preflight_header()

def _print_preflight_header():
    baseline = load_infra_baseline()  # infra-baseline.yaml 읽기
    print(f"[PREFLIGHT] baseline={baseline['baseline_version']}")
    print(f"[PREFLIGHT] timeout={baseline['e2e_timeout_sec']}s")
```

---

## 7. 환경변수 관리

| 변수 | 용도 | 주입 방법 |
|-----|------|---------|
| TELEGRAM_BOT_TOKEN_* | 각 봇 토큰 | GitHub Secrets / .env |
| CLAUDE_API_KEY | Anthropic API | GitHub Secrets / .env |
| OPENAI_API_KEY | OpenAI API | GitHub Secrets / .env |
| GEMINI_CLI_PATH | Gemini 바이너리 경로 | .env (`/opt/homebrew/bin/gemini`) |
| PYTHONUTF8 | Python UTF-8 강제 | ci.yml env 블록 (값: "1") |

---

## 8. Concurrency 정책

```yaml
concurrency:
  group: ci-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: true
```
- 동일 PR에 중복 CI 실행 방지
- 새 커밋 push 시 이전 실행 자동 취소
