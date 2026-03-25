# CI/CD Setup

`docs/CI_CD_SETUP.md` 는 호환용 엔트리다.

최신 GitHub Actions 구성, secret 이름, 로컬 재현 절차는 아래 문서를 기준으로 본다.

- `docs/CI_CD_GUIDE.md`

핵심 변경:

- `ci-lint.yml`: `pull_request`, `main` push, `workflow_dispatch`, Ruff lint
- `ci-e2e.yml`: `pull_request`, `main` push, `workflow_dispatch`, 3엔진 E2E matrix
- `publish-pypi.yml`: `v*` 태그 또는 수동 `workflow_dispatch`, 검증 후 PyPI 릴리즈
- `docker-build.yml`: `v*` 태그 또는 수동 `workflow_dispatch`, 검증 후 Docker Buildx 푸시
- secrets: `PYPI_TOKEN`, `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`
