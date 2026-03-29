# Phase 2 Transplant Implementation Plan

**Date**: 2026-03-29
**Branch**: fix/auto-2026-03-26-telegram_relay
**Source repos**: revfactory/harness, NousResearch/hermes-agent

---

## What Was Implemented

### P0-1: Tool Registry Pattern (`core/tool_registry.py`)
**Source**: hermes-agent `tools/registry.py` + `toolsets.py`
**Feature flag**: `ENABLE_TOOL_REGISTRY=false` (default off)

Centralized tool/capability registry with:
- `ToolEntry` dataclass: name, description, handler, capability_tags, schema, enabled
- `ToolRegistry` class: register/unregister/get/dispatch/get_tools_by_tag/list_all/all_tags
- Module-level singleton via `get_registry()` + `reset_registry()` for tests
- All methods are safe no-ops when the flag is off

Key design decision: `get_tools_by_tag(*tags)` with no arguments returns all enabled tools, matching "wildcard" semantics from hermes-agent's `resolve_toolset("all")`.

---

### P0-2: Structured Skill Validation (`core/skill_validator.py`)
**Source**: harness skill quality checklist patterns
**Feature flag**: none (read-only validation, always safe to call)

Validates SKILL.md files against required structure:
- YAML frontmatter with: `name`, `description`, `allowed-tools`
- Body with at least one trigger/step/procedure section
- Output format section (warning if absent)
- Returns `SkillValidationResult` with typed `ValidationIssue` list
- `validate_all_skills()` scans entire skills/ directory
- `audit_report()` formats human-readable output for CI/harness-audit

---

### P0-3: Platform Adapter Abstraction (`core/platform_adapter.py`)
**Source**: hermes-agent ACP adapter pattern
**Feature flag**: `ENABLE_PLATFORM_ADAPTER=false` (default off)

Abstract base + Telegram adapter:
- `PlatformAdapter` ABC with `normalize_inbound()`, `send_message()`, `can_handle()`
- `InboundMessage` / `OutboundMessage` DTOs for platform-agnostic message handling
- `TelegramPlatformAdapter` — converts python-telegram-bot Update objects
- Global adapter registry: `register_adapter()`, `get_adapter()`, `list_adapters()`
- `telegram_relay.py` is **not touched** — adapter is opt-in only

---

### P1-1: Agent Team Design Patterns (`core/team_design_patterns.py`)
**Source**: harness 6-pattern team taxonomy
**Feature flag**: none (pure data/logic, no side effects)

Pattern registry with validation:
- 6 built-in patterns: solo, pair, trio, squad, assembly, pipeline
- `TeamPattern` dataclass: name, description, min/max_agents, roles, use_cases
- `register_pattern()` with validation (raises ValueError on invalid constraints)
- `recommend_pattern(agent_count)` — suggests best-fit pattern
- `build_team_spec()` — validates and assigns roles to concrete agent lists
- `dynamic_team_builder.py` is **not touched** — new module is additive

---

### P1-2: Skill Gotcha Auto-Learning (`core/skill_gotcha_manager.py`)
**Source**: harness gotchas.md pattern + error-gotcha skill
**Feature flag**: none (filesystem-only, no side effects on running bots)

Programmatic gotcha management:
- `GotchaEntry` dataclass: title, situation, symptom, solution, added_at
- `append_gotcha()` — idempotent append (deduplication by title), auto-creates file
- `list_gotchas()` — returns title list for a skill
- `get_gotchas_text()` — raw gotchas.md content
- `list_skills_with_gotchas()` — discovery across all skills

Auto-learning hook: `error-gotcha` skill can call `append_gotcha()` directly after any bug fix to ensure the gotcha is machine-readable and queryable.

---

## Self-Review Results

### P0-1 Tool Registry
| Check | Result |
|-------|--------|
| ① Logic correctness | PASS — register/dispatch/tag-filter all correct |
| ② Edge cases | PASS — empty name, None handler, unknown tool, disabled tool all handled |
| ③ Interface compatibility | PASS — new standalone module, no existing code changed |
| ④ No unnecessary global state | PASS — only module-level singleton, not touching other modules |

### P0-2 Skill Validator
| Check | Result |
|-------|--------|
| ① Logic correctness | PASS — frontmatter parse + body pattern check correct |
| ② Edge cases | PASS — missing file, empty file, malformed YAML, missing keys |
| ③ Interface compatibility | PASS — new standalone module |
| ④ No unnecessary global state | PASS — pure read-only functions |

### P0-3 Platform Adapter
| Check | Result |
|-------|--------|
| ① Logic correctness | PASS — normalize correctly extracts chat_id/sender/text |
| ② Edge cases | PASS — None event, missing chat_id, no bot_sender, empty text |
| ③ Interface compatibility | PASS — telegram_relay.py untouched |
| ④ No unnecessary global state | PASS — _adapters dict in this module only |

### P1-1 Team Design Patterns
| Check | Result |
|-------|--------|
| ① Logic correctness | PASS — 6 patterns cover 1→∞ agents, role assignment is correct |
| ② Edge cases | PASS — unknown pattern, empty agents, blank strings, 0/negative count |
| ③ Interface compatibility | PASS — dynamic_team_builder.py untouched |
| ④ No unnecessary global state | PASS — _pattern_registry dict in this module only |

**Bug fixed during implementation**: `build_team_spec` filtered `""` but not whitespace-only strings (e.g. `"  "`). Fixed to use `a.strip()` check.

### P1-2 Skill Gotcha Manager
| Check | Result |
|-------|--------|
| ① Logic correctness | PASS — sequential indexing, deduplication, header on first entry |
| ② Edge cases | PASS — missing dir (auto-created), empty title, whitespace-only title, None |
| ③ Interface compatibility | PASS — new standalone module |
| ④ No unnecessary global state | PASS — filesystem-only, no in-memory state |

---

## Feature Flag Documentation

| Flag | Module | Default | Effect when `true` |
|------|--------|---------|---------------------|
| `ENABLE_TOOL_REGISTRY` | `core/tool_registry.py` | `false` | Activates the central tool registry; `register()` and `dispatch()` become functional |
| `ENABLE_PLATFORM_ADAPTER` | `core/platform_adapter.py` | `false` | Activates platform adapter routing; `normalize_inbound()` and `send_message()` become functional |

Both flags are added to `.env.example` under `[Phase 2 이식]` section.

Modules without feature flags (`skill_validator.py`, `team_design_patterns.py`, `skill_gotcha_manager.py`) are pure/read-only and safe to call unconditionally.

---

## Test Coverage

| Test file | Module tested | Tests |
|-----------|--------------|-------|
| `tests/unit/test_transplant_tool_registry.py` | `core/tool_registry.py` | 18 |
| `tests/unit/test_transplant_skill_validator.py` | `core/skill_validator.py` | 16 |
| `tests/unit/test_transplant_platform_adapter.py` | `core/platform_adapter.py` | 17 |
| `tests/unit/test_transplant_team_patterns.py` | `core/team_design_patterns.py` | 27 |
| `tests/unit/test_transplant_skill_gotcha.py` | `core/skill_gotcha_manager.py` | 21 |
| **Total** | | **99 tests, all passing** |

---

## Implementation Notes

- All 5 modules use `from __future__ import annotations` for forward-reference support.
- No existing files were modified except `.env.example` (feature flag docs appended).
- `telegram_relay.py` and all running bot files were not touched.
- The `reset_registry()` function in `tool_registry.py` is provided solely for test isolation.
