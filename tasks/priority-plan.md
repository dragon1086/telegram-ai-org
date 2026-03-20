# 4-Priority Autonomous Execution Plan

**Date**: 2026-03-19
**Status**: ✅ P2/P1/P4 완료 (2026-03-20) | P3 미완료 (봇 미실행)
**Baseline**: 625 passed, 16 failed → **665 passed, 0 failed**

---

## RALPLAN-DR Summary

### Principles
1. **Minimal invasion** -- touch only what is broken or missing; do not refactor adjacent code
2. **Test-first verification** -- every change must be provable via pytest before moving on
3. **Envelope-first design** -- MessageEnvelope is already implemented; integrate it, do not reinvent
4. **DB schema additive only** -- new tables append to context_db.py; never alter existing tables
5. **E2E as final gate** -- real Telegram tests run last, after unit tests are green

### Decision Drivers
1. **16 failing tests block CI** -- P2 must land before P1 to avoid masking new regressions
2. **MessageEnvelope already exists** -- P1 is integration work, not greenfield
3. **DB persistence (P4) depends on P1** -- envelope schema must match the dataclass fields

### Options per Priority

#### P1: Natural Language Communication Integration
| Option | Pros | Cons |
|--------|------|------|
| A. Wrap `_pm_send_message` to use `MessageEnvelope.to_display()` | Minimal diff (~20 lines), single choke point | Only covers PM-originated messages |
| B. Add envelope layer at `telegram_delivery.resolve_delivery_target` | Covers all outbound paths | Bigger surface, higher risk |
| **Chosen: A** | Safest; PM bot is the primary sender. Extend to B later if needed. |

#### P2: Fix 16 Failing Tests
| Option | Pros | Cons |
|--------|------|------|
| A. Fix tests to match current code behavior | Fast, no production risk | Tests may paper over real bugs |
| B. Fix production code to match test expectations | Correct if tests reflect spec | Risk of breaking working features |
| **Chosen: Mix** | Per-cluster analysis below determines A vs B for each group. |

#### P3: Telegram E2E Verification
| Option | Pros | Cons |
|--------|------|------|
| A. Use `e2e_full_suite.py` (S1-S11) | Comprehensive, priority filtering | Longer runtime (~15 min) |
| B. Use `e2e_telegram_test.py` (4 scenarios) | Fast (~5 min), focused | Less coverage |
| **Chosen: B first, then A for P0 scenarios** | Quick smoke, then full validation. |

#### P4: MessageEnvelope DB Persistence
| Option | Pros | Cons |
|--------|------|------|
| A. New `message_envelopes` table in context_db.py | Consistent with existing pattern | Schema migration needed |
| B. Store envelopes as JSON in `conversation_messages.metadata` | No schema change | Harder to query, breaks separation |
| **Chosen: A** | Clean separation, queryable, matches existing DB pattern (pm_tasks, pm_discussions, pm_verifications). |

---

## Execution Order

**P2 -> P1 -> P4 -> P3** (tests first to establish green baseline)

---

## P2: Fix 16 Failing Tests

### Cluster Analysis

**Cluster 1: test_verification.py (6 failures)**
- **Root cause**: `BOT_ENGINE_MAP` loaded from `core/constants.py` via `load_bot_engines()` which reads `bots/*.yaml`. Tests run without those YAML files or with incomplete configs, so `select_verifier()` returns `None`.
- **Fix (Option B)**: Make `CrossModelVerifier.select_verifier` robust to empty/incomplete `BOT_ENGINE_MAP`. OR provide test fixtures that populate the map.
- **Acceptance**: All 6 verification tests pass.

**Cluster 2: test_nl_classifier.py (3 failures)**
- `test_long_text_is_task` -- long Korean text classified wrong
- `test_short_non_matching_is_chat` -- short non-matching text not classified as CHAT
- `test_emoji_only_is_chat` -- emoji-only text not classified as CHAT
- **Fix (Option A)**: Adjust classifier thresholds/patterns for edge cases OR fix test expectations if classifier behavior is intentional.
- **Acceptance**: All 3 NL classifier tests pass.

**Cluster 3: test_telegram_relay_formatting.py (2 failures)**
- `test_split_message_prefers_paragraph_boundaries` / `test_split_message_falls_back_when_no_good_breakpoint`
- **Root cause**: `split_message()` logic changed; tests expect old boundary behavior.
- **Fix (Option A)**: Update test expectations to match current `split_message` behavior.
- **Acceptance**: Both formatting tests pass.

**Cluster 4: Singletons (4 failures)**
- `test_discussion_dispatch.py::test_discussion_summarize_sends_and_marks_done`
- `test_discussion_pingpong.py::test_discussion_summarize_final_round`
- `test_interaction_mode.py::test_delegate_mode_heuristic`
- `test_llm_decompose.py::TestParseDecompose::test_all_five_depts`
- **Fix**: Each requires individual root-cause analysis. Likely mock/fixture mismatches from recent refactors.
- **Acceptance**: Each individual test passes.

### Step-by-step
1. Run `pytest --tb=short` on each cluster independently to capture exact error messages
2. Apply minimal fixes per cluster (code or test, per analysis above)
3. Run full suite: target 641/641 pass (625 existing + 16 fixed)

---

## P1: Natural Language Communication Integration

### Context
- `MessageEnvelope` exists at `core/message_envelope.py` with `wrap()`, `to_display()`, `to_wire()`, `from_wire()`
- `TelegramRelay._pm_send_message()` (line 273) is the main outbound path
- Currently no import of `MessageEnvelope` in `telegram_relay.py`

### Steps

1. **Wire MessageEnvelope into `_pm_send_message`**
   - Import `MessageEnvelope` in `telegram_relay.py`
   - Before sending, wrap outgoing text in `MessageEnvelope.wrap(content=text, sender_bot=self.org_id, intent="DIRECT_REPLY")`
   - Call `env.to_display()` for Telegram output (strips any metadata tags)
   - Store `env.to_wire()` for internal logging/DB
   - **Acceptance**: Outgoing messages contain no `[TYPE:value]` tags visible to users

2. **Handle inbound legacy tags**
   - In message receive path, call `MessageEnvelope.extract_legacy_tags()` on raw text
   - If tags found, parse into structured envelope; strip tags from display
   - **Acceptance**: Inbound `[COLLAB_REQUEST:bot_a]` parsed correctly, not shown to user

3. **Add unit tests**
   - `tests/test_message_envelope_integration.py`: test wrap -> display round-trip, legacy tag extraction, wire serialization
   - **Acceptance**: New tests pass, no regression in existing 641

---

## P4: MessageEnvelope DB Persistence (EnvelopeManager)

### Schema Addition to `context_db.py`

```sql
CREATE TABLE IF NOT EXISTS message_envelopes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL,
    sender_bot TEXT NOT NULL,
    intent TEXT NOT NULL,
    task_id TEXT,
    reply_to INTEGER,
    metadata TEXT DEFAULT '{}',
    chat_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_envelope_sender ON message_envelopes(sender_bot);
CREATE INDEX IF NOT EXISTS idx_envelope_task ON message_envelopes(task_id);
CREATE INDEX IF NOT EXISTS idx_envelope_chat ON message_envelopes(chat_id);
```

### Steps

1. **Add table to `ContextDB.initialize()`**
   - Append the CREATE TABLE to the existing executescript block
   - **Acceptance**: `initialize()` creates the table without errors

2. **Implement `EnvelopeManager` class**
   - Location: `core/envelope_manager.py`
   - Methods:
     - `async save(envelope: MessageEnvelope, chat_id: int) -> int` -- insert, return row id
     - `async get_by_task(task_id: str) -> list[MessageEnvelope]` -- query by task_id
     - `async get_recent(chat_id: int, limit: int = 50) -> list[MessageEnvelope]` -- recent envelopes for a chat
     - `async search_by_intent(intent: str, limit: int = 20) -> list[MessageEnvelope]`
   - **Acceptance**: Each method has a corresponding unit test

3. **Wire into TelegramRelay**
   - In `__init__`, create `EnvelopeManager(context_db)` if context_db is provided
   - In `_pm_send_message`, after sending, call `envelope_manager.save(env, chat_id)`
   - **Acceptance**: Messages are persisted; queryable via `EnvelopeManager.get_recent()`

4. **Unit tests**
   - `tests/test_envelope_manager.py`: CRUD operations with temp DB
   - **Acceptance**: All new tests pass

---

## P3: Telegram E2E Verification

### Prerequisites
- P2 complete (all unit tests green)
- P1 complete (envelope integration active)
- Bots running via `scripts/start_all.sh`

### Steps

1. **Quick smoke test** via `e2e_telegram_test.py`
   - Run 4 scenarios: greeting, coding_task, task_delegation, multi_dept
   - **Acceptance**: All 4 get responses; no `[TYPE:value]` tags in output

2. **Full suite** via `e2e_full_suite.py --priority P0`
   - Run P0 scenarios only for time efficiency
   - **Acceptance**: P0 scenarios pass eval functions

3. **Natural language output check**
   - Manual inspection of responses: no metadata tags, natural Korean/English
   - **Acceptance**: Responses read like human messages

4. **Write E2E report**
   - Save results to `docs/retros/2026-03-20-e2e-report.md`
   - **Acceptance**: Report includes pass/fail per scenario, response samples

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| BOT_ENGINE_MAP empty in CI | P2 tests keep failing | Provide fixture with hardcoded map |
| MessageEnvelope breaks existing message flow | P1 regression | Wrap only in new code path; fallback to raw text |
| DB migration on existing context.db | P4 data loss | CREATE IF NOT EXISTS is safe; additive only |
| E2E flaky due to bot response timing | P3 false failures | Generous timeouts (60-210s already set) |

---

## Success Criteria (Overall)

- [ ] 641/641 unit tests pass (16 fixed + 625 existing)
- [ ] MessageEnvelope integrated in outbound path
- [ ] No metadata tags visible in Telegram messages
- [ ] message_envelopes table created and populated
- [ ] E2E smoke test passes on 4 core scenarios
