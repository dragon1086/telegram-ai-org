# AGENTS.md

## Scope

This file applies to the entire repository rooted at `/Users/aerok/Desktop/rocky/telegram-ai-org`.

## Project Summary

- `telegram-ai-org` is a Python 3.11+ Telegram-based AI organization.
- The PM bot orchestrates worker agents, shared context, routing, and completion checks.
- Most core runtime code lives under `core/`, bot manifests live under `bots/`, and CLI/helpers live under `tools/` and `scripts/`.

## Key Paths

- `main.py`: local entrypoint
- `core/`: orchestration, routing, context, PM flow, Telegram relay
- `tools/`: external runner integrations and helper utilities
- `tests/`: pytest-based regression coverage
- `scripts/`: setup and local process helpers
- `bots/`: YAML bot definitions
- `README.md`, `ARCHITECTURE.md`: product and system context

## Working Rules

- Keep changes narrowly scoped; do not refactor unrelated areas while fixing a targeted issue.
- Preserve async behavior and existing public method signatures unless the task requires a contract change.
- Prefer small, readable functions and explicit control flow over clever abstractions.
- Follow the existing Python style with type hints where the surrounding code uses them.
- Keep line length compatible with Ruff settings in `pyproject.toml` (`100`).
- Never hardcode secrets or bot tokens. Use environment variables and `.env`-style configuration only.

## Validation

- Run targeted tests for the area you changed first, then broader coverage if the change crosses modules.
- Useful commands:
  - `./.venv/bin/pytest -q`
  - `./.venv/bin/pytest tests/test_pm_routing.py -q`
  - `./.venv/bin/pytest tests/test_pm_orchestrator.py -q`
  - `./.venv/bin/pytest tests/test_context_db_pm.py -q`

## Change Guidance

- When editing PM or routing logic, inspect related files together:
  - `core/pm_orchestrator.py`
  - `core/pm_router.py`
  - `core/nl_classifier.py`
  - `core/telegram_relay.py`
- When changing storage or context behavior, also review the matching tests under `tests/`.
- Keep documentation in sync when behavior changes materially, especially `README.md` and `ARCHITECTURE.md`.

## Operational Notes

- Local setup is documented in `README.md`.
- Prefer `rg`/`rg --files` for repository search.
- Do not remove untracked user files or unrelated local changes.
