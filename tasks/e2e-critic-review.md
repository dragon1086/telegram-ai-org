# Critic Review: E2E Comprehensive Test Plan

**VERDICT: ACCEPT-WITH-RESERVATIONS**

**Overall Assessment**: Categories A-D are solidly designed with accurate API references and appropriate test granularity. Category E contains a confirmed factual error (Architect-flagged) that must be fixed before execution. A handful of wiring and mechanism misunderstandings in B and A need minor corrections but do not block execution.

**Review Mode**: THOROUGH (no escalation to ADVERSARIAL — issues are localized, not systemic)

---

## Pre-commitment Predictions vs Actuals

| Prediction | Actual |
|-----------|--------|
| Category E message_id claim is false | **CONFIRMED** — `pm_tasks` has no `message_id` column (`core/context_db.py:65-76`) |
| TC-B tests reference wrong API signatures | **PARTIALLY** — `discussion_dispatch` signature is correct, but TC-B2 round advancement mechanism is misattributed |
| PM modes fixture complexity underestimated | **NOT CONFIRMED** — existing `test_collab_e2e.py` and `test_discussion_pingpong.py` already have reusable `_make_orchestrator()` patterns |
| Missing rollback/failure recovery | **PARTIALLY** — rollback is implicit (test isolation via tmp_path) but no checkpoint strategy for autonomous execution |
| Category D duplicates existing tests | **MINOR** — some overlap with `test_p2p_messenger.py`, `test_collab_e2e.py`, but E2E scope is broader |

---

## Critical Findings

### C1: Category E factual error — message_id ↔ task_id mapping does NOT exist
- **Confidence**: HIGH
- **Evidence**: `core/context_db.py:65-76` — `pm_tasks` schema:
  ```
  id TEXT PRIMARY KEY, parent_id TEXT, description TEXT, assigned_dept TEXT,
  status TEXT, result TEXT, created_by TEXT, created_at TEXT, updated_at TEXT,
  metadata TEXT DEFAULT '{}'
  ```
  No `message_id` column. The plan states: `"message_id ↔ task_id 매핑은 update_pm_task_metadata()로 이미 저장 중"` — this is incorrect. `update_pm_task_metadata()` writes to the `metadata` JSON blob but there is no structured message_id index or lookup.
- **Why this matters**: The entire Category E architecture (Option B: Reply-to + DB lookup) is premised on this mapping existing. Without it, `EnvelopeManager.receive(message_id)` has no efficient lookup path.
- **Fix**: Adopt Architect's E1/E2 split:
  - **E1 (this PR)**: `MessageEnvelope` dataclass + `extract_legacy_tags()` — pure parsing, no DB dependency. TC-E1, E3, E4, E5 can proceed.
  - **E2 (follow-up PR)**: Add `message_envelope` table with `(message_id INTEGER PRIMARY KEY, task_id TEXT, metadata TEXT)` + index. TC-E2 moves here.
  - Update plan Section 6.4 to reflect this split.

---

## Major Findings

### M1: TC-B2 round advancement mechanism is misattributed
- **Confidence**: HIGH
- **Evidence**: `core/pm_orchestrator.py:2031-2101` — `discussion_dispatch()` creates round-1 subtasks only. There is no `advance_discussion_round()` call within this method. Round advancement happens via `core/context_db.py:493` (`advance_discussion_round`) called from `core/discussion.py:170` (`DiscussionManager.advance_round`), which is triggered by the task poller on subtask completion — not by the orchestrator directly.
- **Why this matters**: TC-B2 says "advance_discussion_round() 호출 → 라운드 2 서브태스크 생성 시 description에 라운드 1 결과 포함 확인". The executor will not find a single method to call that does this. The actual flow is: subtask completes → task poller detects → triggers round advancement → new subtasks created. This requires either (a) mocking the full poller chain or (b) directly calling the internal DB method + re-invoking dispatch.
- **Fix**: Rewrite TC-B2 to specify the exact call sequence:
  1. Call `discussion_dispatch()` to create round-1 subtasks
  2. Mock subtask completion by updating status via `db.complete_pm_task(tid, result="AI 도입이 필요합니다")`
  3. Call the round-advancement handler (identify the exact method in `telegram_relay.py` or `pm_orchestrator.py` that handles subtask completion for discussions)
  4. Verify new round-2 subtasks contain round-1 results in description

### M2: TC-A3 fixture wiring gap — CollaborationTracker must receive persona_memory
- **Confidence**: HIGH
- **Evidence**: `core/collaboration_tracker.py:64` — `if self.persona_memory is not None: ... update_synergy()`. `core/collaboration_tracker.py:27` — `def __init__(self, db_path, persona_memory=None)`.
- **Why this matters**: TC-A3 says "CollaborationTracker.record()로 (bot_a, bot_b) 협업 성공 5회 기록 → AgentPersonaMemory의 synergy_scores 확인". This only works if `CollaborationTracker` is initialized with the same `AgentPersonaMemory` instance. The Phase 1 fixture list shows `collaboration_tracker(tmp_path)` and `persona_memory(tmp_path)` as independent fixtures.
- **Fix**: Update Phase 1 fixture definition:
  ```
  collaboration_tracker(tmp_path, persona_memory) — pass persona_memory fixture as dependency
  ```
  Or explicitly document in TC-A3 that the fixtures must be wired together.

---

## Minor Findings

### m1: TC-B5 conflates convergence detection with DECISION state transition
- Plan says: "PROPOSE → OPINION → DECISION 순서 메시지 추가 → DECISION 메시지 후 토론 상태가 'decided'로 전환"
- Actual: DECISION msg_type at `discussion.py:110-111` immediately delegates to `force_decision()` which sets status to "decided" (`discussion.py:196`). The convergence detection (`check_convergence()` at line 135) only triggers "converging" state, not "decided". So the test will pass, but the description implies convergence detection leads to "decided", when actually it is the DECISION message type that directly triggers it. This is a documentation accuracy issue, not a functional one.

### m2: TC-C1 uses `plan.route == "direct_reply"` — verify heuristic returns this
- `RequestPlan` at `pm_orchestrator.py:63` has `route: Literal["direct_reply", "local_execution", "delegate"]`. "direct_reply" is valid. But the heuristic path for greetings should be verified — it likely returns "direct_reply" but the plan doesn't cite the specific heuristic branch.

### m3: Category D has partial overlap with existing tests
- `test_p2p_messenger.py`, `test_collab_e2e.py`, `test_collab_request.py` already cover TC-D1, D2, D5 at unit level. The E2E versions add value by testing integration, but the plan should acknowledge existing coverage to avoid confusion.

### m4: 60-second timeout constraint is stated but not enforced
- Plan says "전체 테스트 스위트가 60초 이내 완료". No `pytest-timeout` configuration or `@pytest.mark.timeout` decorators are specified. This is aspirational without enforcement.

---

## What's Missing

1. **Autonomous execution checkpoint strategy**: The plan says Rocky is sleeping. There is no specification of what happens if Phase 3 fails mid-execution — does the executor skip to Phase 4? Retry? Stop entirely? The dependency graph (Section 6) shows Phase 3 depends on Phase 2, but the autonomous decision protocol for failure is absent.

2. **Existing test regression guard**: Section 4 says "기존 테스트 PASS 유지" with `pytest tests/ --ignore=tests/e2e/` but doesn't specify when to run this check — before starting? After each phase? Only at the end?

3. **Phase 6 E1/E2 split not reflected**: Architect already recommended this. The plan has not been updated to incorporate it. This is the primary reason for ITERATE on Category E.

4. **`conftest.py` fixture for `_FakeConfig`**: Multiple existing tests (`test_collab_e2e.py:26`, `test_discussion_pingpong.py`) each define their own `_FakeConfig` / `_FakeOrg`. The plan's Phase 1 fixture list doesn't mention extracting this common pattern, which means the executor will likely copy-paste yet again.

5. **No mention of `ENABLE_DISCUSSION_PROTOCOL` env var**: `core/discussion.py:12` gates discussion features behind this env var. TC-B tests that exercise DiscussionManager directly won't hit this gate, but TC-C3 (which goes through relay) might fail if this isn't set. The plan should specify `monkeypatch.setenv("ENABLE_DISCUSSION_PROTOCOL", "1")` or note that the TC bypasses relay.

---

## Ambiguity Risks

- `TC-B2: "advance_discussion_round() 호출"` → Interpretation A: call `ContextDB.advance_discussion_round()` directly. Interpretation B: call `DiscussionManager.advance_round()`. Interpretation C: trigger via task completion handler. Each produces different test structure. Risk: executor picks A (low-level DB call) and misses the business logic in DiscussionManager.

- `TC-A3: "CollaborationTracker.record()로 ... 협업 성공 5회 기록"` → Does "5회" mean 5 separate `record()` calls with 2 participants, or fewer calls with more participants? The `get_frequent_pairs` counts per-pair combinations from `participants` JSON, so the test setup must be precise about participant lists.

---

## Multi-Perspective Notes

- **Executor**: "Phase 1 fixture list looks complete but I'll need to figure out the wiring between `collaboration_tracker` and `persona_memory` myself since it's not specified. TC-B2 will require me to reverse-engineer the round advancement flow — I'll probably need to read `telegram_relay.py` extensively."

- **Stakeholder**: "29 TCs covering 5 categories is solid scope. The priority ordering (C > A > B > D > E) matches system criticality. Category E being a prototype-only scope is appropriate for a new architectural pattern."

- **Skeptic**: "The Envelope Pattern (Category E) is the riskiest part. The plan selected Option B (DB lookup) partly based on a false premise (message_id mapping exists). With that removed, the cost-benefit of Option B vs Option A (ZWC) should be re-evaluated — though I note the Architect's E1/E2 split sidesteps this by deferring DB work."

---

## Architect Review Assessment

The Architect review is **correct but insufficient**:
- **Correctly identified** the Category E factual error (message_id mapping)
- **Correctly recommended** E1/E2 split
- **Missed**: TC-B2 round advancement misattribution, TC-A3 fixture wiring gap, ENABLE_DISCUSSION_PROTOCOL gate, autonomous execution checkpoint strategy
- The review is only 18 lines — for a 400-line plan with 29 test cases, this is under-scoped. The A-D "APPROVE" was given without verifying individual TC specifications against actual API signatures.

The E1/E2 split recommendation is **sound and should be adopted**.

---

## Verdict Justification

**ACCEPT-WITH-RESERVATIONS** rather than ITERATE because:

1. The one CRITICAL finding (C1) has an already-documented fix path (Architect's E1/E2 split) that the executor can apply without re-planning.
2. The two MAJOR findings (M1, M2) are localized fixes — rewrite one TC description and add one fixture parameter. They don't require structural replanning.
3. Categories A, C, D are well-specified with accurate API references verified against source code.
4. The autonomous execution decision log (Section 8) is thorough.

**To upgrade to ACCEPT**: Fix C1 (apply E1/E2 split to plan), fix M1 (specify exact round advancement call sequence), fix M2 (wire fixtures), and add a one-line note about `ENABLE_DISCUSSION_PROTOCOL`.

**Realist Check**: C1 was pressure-tested — without the fix, TC-E2 literally cannot be implemented as designed (no DB column to query). This is correctly rated CRITICAL. M1 was pressure-tested — a competent executor could figure out the round advancement flow by reading code, but in autonomous mode (Rocky sleeping), getting stuck here wastes significant time. Correctly rated MAJOR.

---

## Recommendation for Autonomous Execution

The executor should:
1. **Apply E1/E2 split** before starting Phase 6 — implement only E1 (dataclass + legacy parser) in this PR
2. **Wire `persona_memory` into `collaboration_tracker` fixture** in Phase 1
3. **For TC-B2**: investigate the actual round advancement handler in `telegram_relay.py` or `pm_orchestrator.py` before writing the test
4. **Run `pytest tests/ --ignore=tests/e2e/ -q`** after Phase 1 and after Phase 6 to catch regressions early
5. **Set `ENABLE_DISCUSSION_PROTOCOL=1`** in test environment if any TC touches relay-level discussion flow

**Final Conclusion: ACCEPT-WITH-RESERVATIONS**

The plan is executable with the reservations above applied inline during implementation. No re-planning cycle needed — the fixes are surgical.

---

*Reviewed by: Critic Agent (opus) | 2026-03-19*
*Ralplan summary: N/A (not a ralplan-format document)*
