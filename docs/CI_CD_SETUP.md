# CI/CD Setup

## 개요

이 저장소의 GitHub Actions CI/CD는 두 단계로 운영한다.

| 워크플로우 | 트리거 | 목적 |
|---|---|---|
| `ci.yml` | `pull_request` | lint, 오케스트레이션 설정 검증, `tests/e2e/` 회귀 실행 |
| `release.yml` | `push` to `main` | 검증 재실행 후 PyPI 배포, Docker Hub 이미지 빌드·푸시 |

운영 원칙:

- 배포 전 항상 테스트: `release.yml`은 `verify` job에서 lint, `validate-config`, E2E를 다시 통과한 뒤에만 배포한다.
- 인프라 변경은 단계적으로: `release.yml`은 `verify` → `publish-pypi` → `docker-push` 순서로 직렬 실행한다.
- PR 보호: `ci.yml`을 branch protection required check로 등록해 `main` 머지 전에 검증을 강제한다.
- 시크릿 최소 노출: test credential과 배포 토큰은 필요한 step에만 주입한다.

---

## GitHub Secrets 등록 방법

1. GitHub 저장소에서 `Settings`로 이동한다.
2. `Secrets and variables` → `Actions`를 연다.
3. `New repository secret`을 눌러 아래 값을 등록한다.

| Secret | 필수 여부 | 사용 위치 | 설명 |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | 선택 | `ci.yml`, `release.yml` | Claude 관련 테스트 컨텍스트 |
| `OPENAI_API_KEY` | 선택 | `ci.yml`, `release.yml` | Codex 관련 테스트 컨텍스트 |
| `GOOGLE_API_KEY` | 선택 | `ci.yml`, `release.yml` | Gemini API key 기반 테스트 컨텍스트 |
| `GEMINI_API_KEY` | 선택 | `ci.yml`, `release.yml` | Gemini 대체 API key |
| `GEMINI_OAUTH_CREDS` | 선택 | `ci.yml`, `release.yml` | Gemini OAuth JSON 전체 문자열 |
| `CLAUDE_CODE_OAUTH_TOKEN` | 선택 | `ci.yml`, `release.yml` | Claude Code OAuth 토큰 |
| `PYPI_TOKEN` | 필수 | `release.yml` | PyPI 업로드 토큰 |
| `DOCKER_USERNAME` | 필수 | `release.yml` | Docker Hub 사용자명 |
| `DOCKER_TOKEN` | 필수 | `release.yml` | Docker Hub access token |

권장 사항:

- 테스트용 secret은 실제 운영 키와 분리된 전용 CI credential을 사용한다.
- `GEMINI_OAUTH_CREDS`를 쓰는 경우 JSON 파일 전체를 문자열로 저장한다.
- PyPI와 Docker token은 repository scope 최소 권한으로 발급한다.

---

## 워크플로우 흐름

### `ci.yml`

1. PR 생성 또는 업데이트 시 실행된다.
2. Python 3.11 환경을 준비한다.
3. `pip install -e ".[dev]"`로 개발 의존성을 설치한다.
4. `ruff check telegram_ai_org`를 실행한다.
5. `python tools/orchestration_cli.py validate-config`로 오케스트레이션 설정을 검증한다.
6. `pytest tests/e2e/ -q`로 E2E 회귀를 실행한다.

### `release.yml`

1. `main` 브랜치에 push되면 실행된다.
2. `verify` job에서 PR과 동일한 lint, 설정 검증, E2E를 다시 수행한다.
3. `publish-pypi` job에서 `python -m build`와 `python -m twine check dist/*`를 통과한 뒤 `twine upload --skip-existing`를 실행한다.
4. `docker-push` job에서 `docker/build-push-action`으로 Docker 이미지를 빌드하고 `latest`, `${{ github.sha }}` 태그로 Docker Hub에 푸시한다.

---

## 로컬에서 동일 검증 실행 방법

### 공통 준비

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

### CI 검증 재현

```bash
ruff check telegram_ai_org
python tools/orchestration_cli.py validate-config
pytest tests/e2e/ -q
```

현재 저장소 전체는 기존 lint debt가 남아 있어 CI lint 게이트는 `telegram_ai_org` 패키지 범위로 제한한다.

필요하면 아래 환경변수를 함께 맞춘다.

```bash
export CLAUDE_CLI_PATH=claude
export CODEX_CLI_PATH=codex
export GEMINI_CLI_PATH=gemini
```

Gemini OAuth 기준으로 맞추려면:

```bash
mkdir -p ~/.gemini
cp /path/to/oauth_creds.json ~/.gemini/oauth_creds.json
chmod 600 ~/.gemini/oauth_creds.json
```

### PyPI 배포 검증

```bash
python -m build
python -m twine check dist/*
```

### Docker 빌드 검증

```bash
docker build -t telegram-ai-org:local .
```
