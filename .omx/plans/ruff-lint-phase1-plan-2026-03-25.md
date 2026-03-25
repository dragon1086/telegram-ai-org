# Ruff Lint Phase 1 Cleanup Plan

Date: 2026-03-25
Task: T-aiorg_pm_bot-591

## Goal
- Reach `ruff check .` == 0 errors from the current baseline.
- Keep behavior unchanged unless a lint fix requires a small code correction.
- Leave unrelated user changes untouched.

## Baseline
- `./.venv/bin/python tools/orchestration_cli.py validate-config` => `warn`
- `./.venv/bin/ruff check . --statistics` => 523 errors, 425 auto-fixable
- Existing working tree already contains unrelated tracked and untracked changes

## Execution Steps
1. Run `./.venv/bin/ruff check . --fix`.
2. Re-run Ruff in concise mode and group remaining issues by rule and file.
3. Apply small manual patches by rule family:
   - import ordering / late imports
   - unused imports / variables
   - undefined names / typing-only forward refs
   - lambda assignments / ambiguous names / formatting escapes
4. After each risky manual cluster, run focused pytest targets.
5. Finish with full `ruff check .` and a final pytest pass, then commit only the lint-cleanup changes.

## Risk Notes
- `E402` and `F821` can hide runtime assumptions and need file-by-file review.
- The repo has unrelated pending changes; do not overwrite or revert them.
- Missing `tasks/lessons.md` in the main worktree is a documentation drift item, not a blocker for this task.
