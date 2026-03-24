# CI/CD Guide

## 개요

이번 구성은 PR 검증 1종과 `main` 머지 후 배포 2종으로 단순화했다.

| 워크플로우 | 트리거 | 역할 |
|---|---|---|
| `ci-e2e.yml` | `pull_request` to `main`, `workflow_dispatch` | 설정 검증 + `tests/e2e/` 실행 |
| `publish-pypi.yml` | `push` to `main`, `workflow_dispatch` | 검증 후 PyPI 패키지 빌드/배포 |
| `docker-publish.yml` | `push` to `main`, `workflow_dispatch` | 검증 후 Docker Hub 이미지 빌드/푸시 |

운영 원칙:

- 배포 전 항상 테스트: `publish-pypi.yml`, `docker-publish.yml` 모두 `verify` job을 선행한다.
- 인프라 변경은 단계적으로: 배포 job은 검증이 끝난 뒤에만 실행되도록 `needs` 로 직렬화한다.
- PR 머지 차단: `ci-e2e.yml` 의 `e2e-tests` job을 branch protection required status check로 등록한다.
- PyPI 배포 정책: `main` 머지마다 배포를 시도하되 `twine upload --skip-existing` 로 이미 배포된 동일 버전은 건너뛴다.

---

## GitHub Secrets

등록 위치:

1. GitHub 저장소로 이동한다.
2. `Settings` → `Secrets and variables` → `Actions` 를 연다.
3. `New repository secret` 으로 아래 값을 추가한다.

| Secret | 사용 워크플로우 | 발급 방법 | 비고 |
|---|---|---|---|
| `PYPI_TOKEN` | `publish-pypi.yml` | [PyPI](https://pypi.org/) 로그인 → Account settings → `API tokens` → 신규 토큰 발급 | `twine upload` 에서 `__token__` 계정으로 사용 |
| `DOCKERHUB_USERNAME` | `docker-publish.yml` | [Docker Hub](https://hub.docker.com/) 계정 사용자명 확인 | 이미지 이름 prefix로 사용 |
| `DOCKERHUB_TOKEN` | `docker-publish.yml` | Docker Hub → Account Settings → `Personal access tokens` → 신규 토큰 발급 | 비밀번호 대신 로그인용 토큰 사용 |

권장 사항:

- PyPI 토큰은 프로젝트별 scoped token으로 발급한다.
- Docker Hub 토큰은 write 권한이 필요한 저장소로만 범위를 최소화한다.
- Secret 이름은 워크플로우와 동일하게 대소문자까지 정확히 등록한다.

---

## Workflow 상세

### `ci-e2e.yml`

1. PR이 `main` 대상으로 열리거나 갱신될 때 자동 실행된다.
2. Python 3.11 환경을 준비하고 `.[dev]` 의존성을 설치한다.
3. `python tools/orchestration_cli.py validate-config` 로 오케스트레이션 설정을 검증한다.
4. `python -m pytest tests/e2e/ -q --tb=short` 를 실행한다.
5. 실패 시 `e2e-tests` status check가 실패 상태로 남아 PR 머지를 차단할 수 있다.

### `publish-pypi.yml`

1. `main` 브랜치에 머지되면 자동 실행된다.
2. `verify` job에서 설정 검증과 E2E 테스트를 먼저 실행한다.
3. `publish` job에서 `python -m build` 와 `python -m twine check dist/*` 를 수행한다.
4. `PYPI_TOKEN` 을 사용해 `python -m twine upload --skip-existing dist/*` 로 업로드한다.

### `docker-publish.yml`

1. `main` 브랜치에 머지되면 자동 실행된다.
2. `verify` job에서 설정 검증과 E2E 테스트를 먼저 실행한다.
3. `docker/build-push-action` 으로 이미지를 빌드한다.
4. Docker Hub 에 `${DOCKERHUB_USERNAME}/telegram-ai-org:latest` 와 `${DOCKERHUB_USERNAME}/telegram-ai-org:${GITHUB_SHA}` 두 태그로 푸시한다.

---

## 로컬 검증 절차

### 공통 검증

```bash
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -e ".[dev]"
./.venv/bin/python tools/orchestration_cli.py validate-config
./.venv/bin/python -m pytest tests/e2e/ -q --tb=short
```

### YAML 문법 검증

```bash
./.venv/bin/python - <<'PY'
from pathlib import Path
import yaml

for path in sorted(Path(".github/workflows").glob("*.yml")):
    yaml.safe_load(path.read_text())
    print(f"OK {path}")
PY
```

### 패키지 빌드 검증

```bash
./.venv/bin/python -m build
./.venv/bin/python -m twine check dist/*
```

---

## 운영 메모

- GitHub branch protection 에 `e2e-tests` 를 required status check 로 등록한다.
- PyPI 배포는 `main` 머지 직후 자동 시도되므로, 버전 변경이 포함된 PR만 merge 하는 운영 규칙을 권장한다.
- Docker 이미지는 항상 `latest` 와 커밋 SHA 두 태그를 함께 남겨 롤백 추적성을 확보한다.
