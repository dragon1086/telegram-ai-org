# CI/CD Guide

## 워크플로 전체 구성

이 프로젝트는 GitHub Actions 워크플로를 **6개**로 운영한다.
PR 검증(`ci.yml`) → main 배포(`cd-main.yml`) → 버전 릴리즈(`release.yml`) 세 계층으로 분리한다.

| 파일 | 트리거 | 역할 |
|---|---|---|
| `ci.yml` | PR to `main`, `workflow_dispatch` | lint → unit-test → docker-build 검증 → E2E 순서 |
| `cd-main.yml` | `push` to `main`, `workflow_dispatch` | 검증 후 Docker Hub `latest` 이미지 푸시 |
| `release.yml` | `v*` 태그 push, `workflow_dispatch` | Docker Hub 버전 태그 푸시 + GitHub Release 생성 |
| `ci-lint.yml` | PR, `push` to `main`, `workflow_dispatch` | Ruff 린트만 단독 실행 (빠른 피드백) |
| `ci-e2e.yml` | PR to `main`, `workflow_dispatch` | E2E 단독 실행 (설정 검증 포함, 커버리지 90%+) |
| `docker-publish.yml` | `push` to `main`, `workflow_dispatch` | Docker Hub 빌드/푸시 (레거시, `cd-main.yml`로 대체 권장) |
| `publish-pypi.yml` | `push` to `main`, `workflow_dispatch` | PyPI 패키지 빌드/배포 |

---

## 공통 환경 변수

모든 워크플로에 아래 값이 동일하게 정의되어 있다.

| 변수 | 값 | 설명 |
|---|---|---|
| `PYTHON_VERSION` | `"3.11"` | Python 버전 고정 |
| `DOCKER_IMAGE` | `telegram-ai-org` | Docker Hub 이미지 이름 (username 제외) |
| `PYTHONUTF8` | `"1"` | UTF-8 강제 |
| `PIP_DISABLE_PIP_VERSION_CHECK` | `"1"` | pip 버전 경고 억제 |
| `CLAUDE_CLI_PATH` | `claude` | Claude CLI 경로 (E2E용) |
| `CODEX_CLI_PATH` | `codex` | Codex CLI 경로 (E2E용) |
| `GEMINI_CLI_PATH` | `gemini` | Gemini CLI 경로 (E2E용) |

Docker Hub 전체 이미지 태그 형식:

```
${{ secrets.DOCKERHUB_USERNAME }}/${{ env.DOCKER_IMAGE }}:latest
${{ secrets.DOCKERHUB_USERNAME }}/${{ env.DOCKER_IMAGE }}:<version>
${{ secrets.DOCKERHUB_USERNAME }}/${{ env.DOCKER_IMAGE }}:<git-sha>
```

---

## GitHub Secrets 등록

등록 위치: **GitHub 저장소 → Settings → Secrets and variables → Actions → New repository secret**

| Secret 이름 | 사용 워크플로 | 발급 방법 | 비고 |
|---|---|---|---|
| `DOCKERHUB_USERNAME` | `ci.yml`, `cd-main.yml`, `release.yml`, `docker-publish.yml` | Docker Hub 계정 사용자명 | 이미지 prefix로 사용 |
| `DOCKERHUB_TOKEN` | `ci.yml`, `cd-main.yml`, `release.yml`, `docker-publish.yml` | Docker Hub → Account Settings → Personal access tokens → 신규 발급 | 비밀번호 대신 사용 (write 권한 필요) |
| `PYPI_TOKEN` | `publish-pypi.yml` | PyPI → Account settings → API tokens → 신규 발급 | 프로젝트 scoped token 권장 |

> **보안 권장사항**
> - Docker Hub 토큰은 해당 repository 단일 write 권한으로 최소화 발급
> - PyPI 토큰은 `telegram-ai-org` 프로젝트 scoped token으로 발급
> - Secret 이름은 대소문자 구분 — 워크플로 파일과 정확히 일치해야 함

---

## 워크플로 상세

### `ci.yml` — PR CI (lint → unit-test → docker-build → e2e)

PR이 `main` 대상으로 열리거나 업데이트될 때 실행된다.

```
lint ──────────────┐
                    ├──→ docker-build (푸시 없음)
unit-test ─────────┘
                    ├──→ e2e (tests/e2e/ 대상, 커버리지 90%+)
```

- **lint**: `python -m ruff check telegram_ai_org` + `ruff format --check`
- **unit-test**: `pytest tests/ --ignore=tests/e2e --ignore=tests/integration`
- **docker-build**: `docker/build-push-action` with `push: false` (빌드 검증만)
- **e2e**: `pytest tests/e2e/` + `orchestration_cli.py validate-config`

Branch protection에 `lint`, `unit-test`, `e2e` job을 required status check로 등록 권장.

### `cd-main.yml` — main 브랜치 배포

`main` 머지 후 자동 실행. `verify` job이 먼저 E2E를 재검증한 뒤 Docker Hub에 푸시한다.

푸시 태그:
- `<username>/telegram-ai-org:latest`
- `<username>/telegram-ai-org:<git-sha>` (롤백 추적용)

### `release.yml` — 버전 릴리즈

`v*` 형식 태그 푸시 시 실행 (예: `git tag v1.0.0 && git push origin v1.0.0`).

1. **docker-release**: 버전 태그 + `latest` 동시 푸시
2. **github-release**: `CHANGELOG.md` 최상단 섹션 또는 git log로 릴리즈 노트 생성 → GitHub Release 자동 생성

릴리즈 제목 = 태그명 (예: `v1.0.0`).
`-rc`, `-beta`, `-alpha` 포함 태그는 prerelease로 자동 표시.

---

## 로컬 CI 재현 방법

### 1. Lint

```bash
# ruff 설치 (없는 경우)
./.venv/bin/python -m pip install ruff

# lint 실행
./.venv/bin/python -m ruff check telegram_ai_org

# format 체크
./.venv/bin/python -m ruff format --check telegram_ai_org
```

### 2. Unit Tests

```bash
# 의존성 설치
./.venv/bin/python -m pip install -e ".[dev]"

# 단위 테스트 실행 (e2e, integration 제외)
./.venv/bin/python -m pytest tests/ \
  --ignore=tests/e2e \
  --ignore=tests/integration \
  -q --tb=short
```

### 3. E2E Tests

```bash
# 설정 검증 먼저
./.venv/bin/python tools/orchestration_cli.py validate-config

# E2E 전체 실행
./.venv/bin/python -m pytest tests/e2e/ \
  -q --tb=short \
  --cov=tools.gemini_cli_runner \
  --cov=tools.codex_runner \
  --cov=tools.base_runner \
  --cov=tools.claude_subprocess_runner \
  --cov-fail-under=90 \
  --cov-report=term-missing
```

### 4. Docker Build 검증

```bash
# 기본 이미지 빌드 (push 없음)
docker build -t telegram-ai-org:local .

# Claude 엔진 포함 빌드
docker build --build-arg ENGINE=claude -t telegram-ai-org:claude .

# Buildx 로컬 테스트
docker buildx build --load -t telegram-ai-org:local .
```

### 5. YAML 문법 검증

```bash
./.venv/bin/python - <<'PY'
from pathlib import Path
import yaml

for path in sorted(Path(".github/workflows").glob("*.yml")):
    yaml.safe_load(path.read_text())
    print(f"OK  {path}")
PY
```

---

## 릴리즈 절차

```bash
# 1. 버전 태그 생성
git tag v1.0.0

# 2. 태그 푸시 → release.yml 자동 트리거
git push origin v1.0.0

# 3. GitHub Actions에서 자동 처리:
#    - Docker Hub: dragon1086/telegram-ai-org:v1.0.0 + :latest 푸시
#    - GitHub Releases: CHANGELOG + Docker pull 안내 포함 릴리즈 노트 생성
```

---

## 운영 메모

- Branch protection: `lint`, `unit-test`, `e2e` (ci.yml) 을 required status check로 등록
- Docker 이미지는 항상 `latest` + commit SHA 두 태그를 함께 남겨 롤백 추적성 확보
- PyPI 배포는 버전 변경이 포함된 PR만 merge하는 운영 규칙 권장
- `release.yml`의 GitHub Release 생성 Action: `softprops/action-gh-release@v2`
  (`actions/create-release`는 archived — 이를 대체하는 현행 표준)
