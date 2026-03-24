# CI/CD Setup

빠른 설정 체크리스트 문서다. 상세 운영 절차는 `docs/CI_CD_GUIDE.md`를 기준으로 한다.

## 워크플로우

| 워크플로우 | 역할 | 핵심 포인트 |
|---|---|---|
| `e2e-test.yml` | 3엔진 E2E 테스트 | `push` / `pull_request` / `workflow_dispatch`, `validate-config` 후 E2E 실행 |
| `publish-pypi.yml` | PyPI 배포 | `main` / `v*`, `build` → `twine check` → `twine upload --skip-existing` |
| `docker-build-push.yml` | Docker 이미지 배포 | `main` / `v*`, `claude` / `codex` / `gemini` 이미지 matrix push |

## 필수 secret

| Secret | 사용처 |
|---|---|
| `ANTHROPIC_API_KEY` | `e2e-test.yml` |
| `OPENAI_API_KEY` | `e2e-test.yml` |
| `GEMINI_OAUTH_CREDS` | `e2e-test.yml` |
| `PYPI_API_TOKEN` | `publish-pypi.yml` |
| `DOCKER_USERNAME` | `docker-build-push.yml` |
| `DOCKER_PASSWORD` | `docker-build-push.yml` |

## 운영 체크

- `e2e-test.yml`을 branch protection required check로 등록한다.
- Gemini는 CI에서도 OAuth 기준을 유지하고, `GEMINI_OAUTH_CREDS`를 파일로 복원한다.
- Docker 이미지는 엔진별로 분리돼 있어 롤백을 단계적으로 수행할 수 있다.
