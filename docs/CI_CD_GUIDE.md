# CI/CD Guide

## 워크플로우 개요

이 저장소의 GitHub Actions CI/CD는 아래 세 워크플로우로 운영한다.

| 워크플로우 | 트리거 | 목적 | 핵심 명령 |
|---|---|---|---|
| `e2e-test.yml` | `push`, `pull_request`, `workflow_dispatch` | 3엔진 호환 E2E + 설정 검증 | `python tools/orchestration_cli.py validate-config`, `pytest tests/e2e/test_engine_compat_e2e.py tests/e2e/test_pm_dispatch_e2e.py -q` |
| `publish-pypi.yml` | `push` to `main`, tags `v*`, `workflow_dispatch` | PyPI 배포 | `python -m build`, `python -m twine check dist/*`, `python -m twine upload --skip-existing dist/*` |
| `docker-build-push.yml` | `push` to `main`, tags `v*`, `workflow_dispatch` | Docker Hub 이미지 빌드·푸시 | `docker/build-push-action` + `ENGINE=claude|codex|gemini` 매트릭스 |

운영 순서:

1. `e2e-test.yml`을 branch protection required check로 설정해 `main` 머지 전 테스트를 강제한다.
2. `main` 머지 또는 `v*` 태그 생성 후 `publish-pypi.yml`, `docker-build-push.yml`이 후속 배포를 수행한다.
3. 인프라 변경은 엔진별 이미지(`claude`, `codex`, `gemini`)로 분리해 단계적으로 롤백 가능하게 유지한다.

---

## 필수 GitHub Secrets

GitHub 저장소에서 아래 경로로 등록한다.

1. `Settings`
2. `Secrets and variables`
3. `Actions`
4. `New repository secret`

| Secret | 사용 위치 | 설명 |
|---|---|---|
| `ANTHROPIC_API_KEY` | `e2e-test.yml` | `claude-code` 매트릭스 엔진용 secret |
| `OPENAI_API_KEY` | `e2e-test.yml` | `codex` 매트릭스 엔진용 secret |
| `GEMINI_OAUTH_CREDS` | `e2e-test.yml` | `gemini-cli`용 OAuth credential JSON 전체 |
| `PYPI_API_TOKEN` | `publish-pypi.yml` | PyPI 업로드 토큰 |
| `DOCKER_USERNAME` | `docker-build-push.yml` | Docker Hub 로그인 계정 |
| `DOCKER_PASSWORD` | `docker-build-push.yml` | Docker Hub access token 또는 비밀번호 |

운영 원칙:

- E2E는 offline-safe 성격이라 secret이 비어 있어도 notice만 남기고 계속 진행한다.
- 로컬 Gemini CLI는 계속 OAuth 기준이다. CI에서는 `GEMINI_OAUTH_CREDS`를 `~/.gemini/oauth_creds.json`으로 복원한다.
- PyPI와 Docker secret은 실제 배포 워크플로우에서만 사용한다.

---

## 로컬에서 동일 검증 재현하기

### 공통 준비

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### E2E 테스트 재현

```bash
python tools/orchestration_cli.py validate-config
python -m pytest \
  tests/e2e/test_engine_compat_e2e.py \
  tests/e2e/test_pm_dispatch_e2e.py \
  -q
```

필요하면 아래 환경변수를 함께 맞춘다.

```bash
export CLAUDE_CLI_PATH=claude
export CODEX_CLI_PATH=codex
export GEMINI_CLI_PATH=gemini
```

Gemini OAuth secret을 로컬에서 흉내 내려면:

```bash
mkdir -p ~/.gemini
cp /path/to/oauth_creds.json ~/.gemini/oauth_creds.json
chmod 600 ~/.gemini/oauth_creds.json
```

### PyPI 배포 재현

```bash
python -m build
python -m twine check dist/*
python -m twine upload --skip-existing dist/*
```

### Docker 이미지 재현

```bash
docker buildx build --build-arg ENGINE=claude -t telegram-ai-org:claude --load .
docker buildx build --build-arg ENGINE=codex -t telegram-ai-org:codex --load .
docker buildx build --build-arg ENGINE=gemini -t telegram-ai-org:gemini --load .
```
