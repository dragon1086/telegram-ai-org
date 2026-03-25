# GitHub Settings Audit - 2026-03-25

## Scope

- Repository: `dragon1086/telegram-ai-org`
- Goal:
  - Register GitHub Actions repository secrets `PYPI_TOKEN`, `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`
  - Add required branch protection check for E2E on `main`
- Audit time: `2026-03-25 America/Los_Angeles`

## Phase 1 - Actions Secrets

### Result

- `PYPI_TOKEN`: blocked
- `DOCKERHUB_USERNAME`: blocked
- `DOCKERHUB_TOKEN`: blocked

### Evidence

- `gh auth status` returned not logged in.
- Environment inspection found no `GH_TOKEN`, `GITHUB_TOKEN`, `PYPI_TOKEN`, `DOCKERHUB_USERNAME`, or `DOCKERHUB_TOKEN` exported in the current session.
- Unauthenticated GitHub REST call to `GET /repos/dragon1086/telegram-ai-org/actions/secrets` returned `401 Requires authentication`.

### Conclusion

Repository secret registration could not be executed from this runtime because:

1. No GitHub admin-capable authentication was available.
2. The three secret values were not present in the current runtime environment.

## Phase 2 - Branch Protection

### Result

- Required check registration for `e2e-tests`: blocked
- Branch protection save verification: blocked
- PR required-check verification: blocked

### Evidence

- Unauthenticated GitHub REST call to `GET /repos/dragon1086/telegram-ai-org/branches/main/protection` returned `401 Requires authentication`.
- Public GitHub API for workflows currently shows only two active workflows on remote `main`:
  - `ci-lint`
  - `publish-pypi`
- Remote `origin/main` is at `82e8c6e99d3e683934ac7241017c7450f1de6761`.
- Local repository is ahead of `origin/main` by 3 commits and contains unpushed workflow files such as `.github/workflows/ci.yml`, `.github/workflows/cd-main.yml`, and `.github/workflows/release.yml`.
- Local `.github/workflows/ci.yml` defines jobs `lint`, `unit-test`, `docker-build`, and `e2e`. There is no local job named `e2e-tests`.
- Public check-run data for remote `main` currently shows checks such as `Ruff lint`, `Verify before PyPI publish`, and `Build and publish to PyPI`; no `e2e-tests` check was observed.

### Conclusion

Branch protection could not be updated from this runtime because:

1. No GitHub admin-capable authentication was available.
2. The requested required check name `e2e-tests` is not currently observable on remote `main`.
3. The local E2E workflow/job definitions are not yet reflected on remote `main`, so a stable required check target is not yet available.

## Recommended Order

1. Push or merge the CI workflow changes so the remote repository exposes the real E2E check context.
2. Confirm the exact required-check name to use in branch protection:
   - likely `e2e` if using the current local `ci.yml`
   - not yet evidenced: `e2e-tests`
3. Authenticate GitHub CLI or provide an admin token.
4. Register repository secrets with real values.
5. Apply branch protection and verify on a fresh PR.
