# Telegram AI Org — Comprehensive Codebase Analysis

## Executive Summary

This is a **multi-bot Telegram orchestration system** that routes incoming Telegram messages to specialist AI agents (research, engineering, product, etc.). Each message triggers a **run** (stored in `.ai-org/runs/`), which progresses through phases: intake → planning → design → implementation → verification → feedback. Responses are sent back to Telegram via `update.message.reply_text()`.

**Critical finding:** Runs complete but Telegram responses may fail if the `feedback` phase encounters errors or if the Telegram relay layer drops exceptions without sending fallback messages.

---

## 1. Overall Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                   Telegram User Message                         │
│                   (in allowed chat_id)                          │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
         ┌──────────────────────────┐
         │  TelegramRelay (main.py) │ ◄─── Application.builder().token()
         │  async message handler   │      listens for MessageHandler events
         └──────────────────┬───────┘
                            │
                ┌───────────┴──────────────┐
                │                          │
                ▼                          ▼
    [on_message (routing)]      [/command handlers]
    decides which bot            /start, /status, /reset
    should handle                /org, /prompt, /verbose
                │
                ▼
    ┌──────────────────────────┐
    │  PM Orchestrator         │ ◄─── Classifies request intent
    │  (pm_orchestrator.py)    │      Decomposes into sub-tasks
    │                          │      Routes to specialist bots
    └──────────────────────────┘
                │
    ┌───────────┴──────────────────────┐
    │                                  │
    ▼                                  ▼
[direct_reply]              [delegate to org]
(simple Q&A)                └─► aiorg_research_bot
                               aiorg_engineering_bot
                               aiorg_product_bot
                               aiorg_design_bot
                               aiorg_growth_bot
                               aiorg_pm_bot
                               aiorg_ops_bot
                │
                ▼
    ┌──────────────────────────┐
    │  Session Manager         │
    │  (session_manager.py)    │
    │  Runs tmux Claude Code   │
    └──────────────────────────┘
                │
    ┌───────────┴────────────────────────────┐
    │                                        │
    ▼                                        ▼
[Send to tmux session]          [Collect response]
(send-keys → claude)             (wait_for_response)
                                 (_wait_for_prompt)
                                 (_extract_response)
                │
                ▼
    ┌──────────────────────────────┐
    │  Telegram Reply             │
    │  (await update.message      │
    │   .reply_text(response))    │
    └──────────────────────────────┘
                │
                ▼
    ┌──────────────────────────────┐
    │  .ai-org/runs/              │
    │  [run-<timestamp>-<prompt>]  │
    │  └─ state.json (phases+     │
    │     metadata)               │
    │  └─ docs/ (artifacts,       │
    │     research, code)         │
    └──────────────────────────────┘
```

---

## 2. Entry Point: Bot Startup

### File: `scripts/start_pm.sh`
```bash
export PM_ORG_NAME="aiorg_pm_bot"
export PM_BOT_TOKEN="${PM_BOT_TOKEN:?required}"
export ENABLE_PM_ORCHESTRATOR=1
exec python3 main.py
```

### Bot Manager: `scripts/bot_manager.py`
- **Entry:** `python scripts/bot_manager.py start <token> <org_id> <chat_id>`
- Scans live processes for `main.py` with `PM_ORG_NAME=<org_id>`
- Stores PID in `/tmp/telegram-ai-org-<org_id>.pid`
- Multiple bots can run concurrently (one per org)

### Main Bot Loop: Missing `main.py`
**⚠️ KEY MISSING PIECE:** There is no `main.py` in the root directory. The actual entry point must be:
- `core/telegram_relay.py` — TelegramRelay class (3379 lines)
- OR a wrapper that imports it (check if there's a `run_bot()` function)

**To find:** Search for `if __name__ == "__main__"` or `def run_bot()` that calls `TelegramRelay`

---

## 3. Message Flow: Telegram → Response

### Phase 1: Telegram Message Received
**File:** `/Users/rocky/telegram-ai-org/core/telegram_relay.py` (line 2266+)

```python
builder = Application.builder().token(self.token).request(req)
builder.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._setup_receive_token))
# ... other handlers ...
application.run_polling()
```

- **Token source:** Environment variable `PM_BOT_TOKEN` (set in `start_pm.sh`)
- **Chat filter:** `self.allowed_chat_id` — Only processes messages from one authorized Telegram group
- **Message handler:** Routes to `on_message()` or command handlers

### Phase 2: Message Classification & Routing
**File:** `/Users/rocky/telegram-ai-org/core/pm_orchestrator.py` (line 96+)

```python
async def plan_request(self, user_message: str) -> RequestPlan:
    """Classify request intent and decompose into subtasks."""
    # 1. Detect department (research, engineering, product, etc.)
    # 2. Heuristic or LLM classification (lane: direct_reply | local_execution | delegate)
    # 3. Return RequestPlan with subtasks
```

**Routing decision tree:**
- `"direct_reply"` → Answer immediately without execution
- `"local_execution"` → Execute in tmux claude session
- `"delegate"` → Send to specialist bot org

### Phase 3: Execution (if needed)
**File:** `/Users/rocky/telegram-ai-org/core/session_manager.py` (line 307)

```python
async def send_message(self, team_id: str, message: str) -> str:
    """Send message to tmux Claude Code session, collect response."""
    name = self.ensure_session(team_id)

    # 1. Wait for claude prompt ready
    if not self._wait_for_prompt(name, timeout=5):
        return "❌ claude session not ready"

    # 2. Send message (via send-keys or tempfile if >200 chars)
    self._run_tmux("send-keys", "-t", name, message, "Enter")

    # 3. Collect response (wait for prompt reappearance)
    response = await asyncio.wait_for(
        self._wait_for_response(name, before),
        timeout=OUTPUT_TIMEOUT,
    )
    return response
```

**Key methods:**
- `_wait_for_prompt(name, timeout)` — Polls pane until "claude>" prompt seen
- `_capture_pane(name)` — Snapshot of tmux pane output
- `_extract_response(current, before)` — Diff-based response extraction (TUI artifacts removed)
- `_wait_for_response(name, before)` — Async wait loop checking for stable output

### Phase 4: Reply to Telegram
**File:** `/Users/rocky/telegram-ai-org/core/telegram_relay.py` (line 1661, 1692, 1761, etc.)

```python
# All replies use the same pattern:
await update.message.reply_text(response)
await update.message.reply_text(chunk)  # For long responses (split_message)

# OR for collab mode:
await update.message.reply_text(requester_mention + make_collab_claim(self.org_id))
```

**Response delivery locations:**
1. **Line 1661:** File attachment processing → `msg.reply_text("📎 파일 수신...")`
2. **Line 1692:** Planning phase → `msg.reply_text(brief)`
3. **Line 1761:** Implementation result → `msg.reply_text(chunk)` (split into 4000 char chunks)
4. **Line 2557:** Collab claim → `update.message.reply_text(claim_text)`
5. **Line 2637:** Collab done → `update.message.reply_text(done_text)`
6. **Lines 1789-2995:** Command handlers (`/status`, `/reset`, `/org`, `/prompt`, etc.)

**Message splitting:**
```python
for chunk in split_message(response, 4000):
    await msg.reply_text(chunk)
```

---

## 4. Specialist Bots Configuration

**Location:** `/Users/rocky/telegram-ai-org/bots/*.yaml`

### Bot Profiles:
- `aiorg_research_bot.yaml` — Market research, competitive analysis
- `aiorg_engineering_bot.yaml` — Code, architecture, technical decisions
- `aiorg_product_bot.yaml` — Feature design, user experience
- `aiorg_design_bot.yaml` — UI/UX, visual design
- `aiorg_growth_bot.yaml` — Marketing, growth strategy
- `aiorg_pm_bot.yaml` — Project management, orchestration
- `aiorg_ops_bot.yaml` — Operations, infrastructure
- `marketing_team.yaml`, `dev_team.yaml` — Team compositions

**Usage:** Each has a unique `org_id` (e.g., `aiorg_pm_bot`). When delegated, a task is sent to the bot's tmux Claude Code session via `session_manager.send_message(org_id, task)`.

---

## 5. Run State Storage: `.ai-org/runs/`

**Location:** `.ai-org/runs/run-<timestamp>-<prompt>/`

### Run Structure:
```
run-20260315T142902Z-최근-2026년-3월-기준-코딩-에이전트-시장-조사해줘/
├── state.json              (run metadata & phases)
├── docs/                   (artifacts, research, code)
│   ├── <phase-name>.md     (runbook entries)
│   └── ...
```

### state.json Format:
```json
{
  "run_id": "run-20260315T142902Z-...",
  "org_id": "aiorg_pm_bot",
  "request": "최근 2026년 3월 기준 코딩 에이전트 시장 조사해줘",
  "status": "completed",
  "current_phase": "feedback",
  "phases": [
    {
      "name": "intake",
      "status": "completed",
      "started_at": "2026-03-15T14:29:02.302453+00:00",
      "completed_at": "2026-03-15T14:29:02.326569+00:00"
    },
    { "name": "planning", ... },
    { "name": "design", ... },
    { "name": "implementation", ... },
    { "name": "verification", ... },
    { "name": "feedback", ... }
  ],
  "created_at": "...",
  "updated_at": "..."
}
```

### Phases:
1. **intake** — Request received, parsed, stored
2. **planning** — Decompose into subtasks, build team, assign roles
3. **design** — LLM plan validation, acceptance criteria
4. **implementation** — Execute tasks in Claude Code tmux session(s)
5. **verification** — Verify outputs, test, validate completeness
6. **feedback** — **CRITICAL** — User feedback collection, final response sent

---

## 6. Critical Failure Points: Why Telegram Response May Not Send

### Failure Point 1: Exception in Feedback Phase
**File:** `core/telegram_relay.py` (feedback phase logic)

**Risk:** If the feedback phase raises an exception (e.g., network error, Claude timeout), the code may:
- Log the error
- NOT catch and send a fallback Telegram message
- Result in: Run marked `"status": "completed"` but **no message sent to user**

**Evidence:** Lines 2635-2640 show response sending but no try-catch around `reply_text()`.

### Failure Point 2: Session Manager Timeout
**File:** `core/session_manager.py` (line 338-346)

```python
try:
    response = await asyncio.wait_for(
        self._wait_for_response(name, before),
        timeout=OUTPUT_TIMEOUT,
    )
    return response
except asyncio.TimeoutError:
    logger.warning(f"응답 타임아웃: {name}")
    current = self._capture_pane(name)
    return self._extract_response(current, before)  # ◄ Fallback extraction
```

**Risk:** If `OUTPUT_TIMEOUT` is exceeded and `_extract_response()` fails (corrupted output), an empty or malformed response string may be returned. Caller doesn't validate.

### Failure Point 3: Missing Prompt Readiness Check
**File:** `core/session_manager.py` (line 319-321)

```python
if not self._wait_for_prompt(name, timeout=5):
    logger.warning(f"claude 세션 준비 미완료: {name}")
    return "❌ claude 세션 준비 안됨"
```

**Risk:** If tmux Claude session crashes or hangs, this returns early. But does the caller send this error message to Telegram?

### Failure Point 4: Telegram Reply Text Exceptions Not Caught
**File:** `core/telegram_relay.py` (1661, 1761, 2557, etc.)

```python
await update.message.reply_text(response)  # ◄ No try-catch
```

**Risk:** If Telegram API returns 429 (rate limit), 400 (bad request), or network error, the exception propagates. No fallback message.

### Failure Point 5: Run State Not Updated on Send Failure
**File:** `core/orchestration_runbook.py` (state.json updates)

**Risk:** Run marked `"completed"` even if `reply_text()` fails. User can't know the Telegram delivery failed just by checking state.json.

---

## 7. Completion Protocol: When Does Feedback Happen?

**File:** `/Users/rocky/telegram-ai-org/core/completion.py` (71 lines)

```python
class CompletionProtocol:
    def __init__(self, task_manager: TaskManager, send_message_fn):
        self.send_message = send_message_fn  # async fn(text: str)

    async def initiate_completion(self, task: Task) -> None:
        """Start completion verification — send query to all bots."""
        await self.task_manager.update_status(task.id, TaskStatus.WAITING_ACK)
        msg = f"[TO: ALL | FROM: @pm_bot | TASK: {task.id}]\n確認請..."
        await self.send_message(msg)  # ◄ Broadcast to all bots

    async def receive_ack(self, task_id: str, bot_handle: str) -> bool:
        """Collect bot acknowledgments."""
        task = await self.task_manager.record_ack(task_id, bot_handle)
        if task.all_acked():
            await self.send_message(f"✅ {task_id} CLOSED")
            return True
        return False

    async def wait_for_completion(self, task_id: str, timeout: int = 120) -> bool:
        """Wait up to 120 seconds for all bot ACKs."""
        deadline = datetime.now(UTC) + timedelta(seconds=timeout)
        while datetime.now(UTC) < deadline:
            task = self.task_manager.get_task(task_id)
            if task and task.status == TaskStatus.CLOSED:
                return True
            await asyncio.sleep(5)

        # Timeout — force close
        logger.warning(f"Timeout: {task_id}")
        await self.task_manager.update_status(task_id, TaskStatus.CLOSED, ...)
        return False
```

**⚠️ Risk:** `send_message_fn` is passed in (dependency injection). If it's not properly wired to Telegram `reply_text()`, ACKs are sent to logs/tmux but NOT to the user.

---

## 8. All Files & Their Roles

### Core Orchestration:
- **`core/telegram_relay.py`** (3379 lines) — Main Telegram bot, message routing, all `reply_text()` calls
- **`core/pm_orchestrator.py`** (1171 lines) — Request classification, task decomposition, bot selection
- **`core/session_manager.py`** — Tmux Claude Code session management, message send/response collect
- **`core/completion.py`** — ACK protocol for task completion verification
- **`core/orchestration_runbook.py`** — State.json lifecycle, run tracking
- **`core/orchestration_config.py`** — Run config, phase order, feedback policies

### Message Processing:
- **`core/nl_classifier.py`** — Natural language request classification
- **`core/task_planner.py`** — Task decomposition LLM prompt
- **`core/task_manager.py`** — In-memory task tracking (not persistence)
- **`core/verification.py`** — Output verification logic

### Session & Memory:
- **`core/session_manager.py`** — Tmux Claude Code session lifecycle
- **`core/memory_manager.py`** — Persistent memory for orgs (markdown files)
- **`core/session_store.py`** — Session metadata store (context usage, verbosity)

### Tools & Utilities:
- **`tools/orchestration_cli.py`** — CLI for running orchestration locally
- **`tools/team_strategy.py`** — Team composition strategy
- **`tools/telegram_uploader.py`** — File upload to Telegram
- **`tools/claude_code_runner.py`** — Wrapper for Claude Code invocation
- **`tools/codex_runner.py`** — Wrapper for Codex (alternative LLM)

### Bots:
- **`bots/*.yaml`** — Specialist bot configurations

### Scripts:
- **`scripts/bot_manager.py`** — Process management (start/stop/restart bots)
- **`scripts/start_pm.sh`** — PM bot launcher
- **`scripts/setup_wizard.py`** — Onboarding wizard for new bots

---

## 9. Complete Message → Response Flow (Step-by-Step)

```
1. User sends message to Telegram chat
   └─► TelegramRelay.message_handler() triggered

2. Authentication check
   └─► Verify user in allowed_chat_id
   └─► Verify user has permission
       → FAIL: return no response

3. Message classification
   └─► PMOrchestrator.plan_request()
   └─► Classify intent (direct_reply vs delegate)
   └─► Decompose subtasks

4a. IF direct_reply:
    └─► Generate answer via LLM
    └─► await update.message.reply_text(answer)
    └─► return

4b. IF delegate:
    └─► Find target bot org_id
    └─► SessionManager.send_message(org_id, task)
    └─► Collect response from tmux Claude session
    └─► proceed to step 5

5. Response formatting
   └─► Synthesize output from all subtasks
   └─► Build Telegram message (≤4000 chars per Telegram limit)
   └─► Split if needed: for chunk in split_message(response, 4000)

6. Send reply to Telegram
   └─► await update.message.reply_text(chunk)
   └─► ⚠️ NO exception handling → failure here = no response sent

7. Run completion
   └─► Update state.json: current_phase = "feedback", status = "completed"
   └─► Save artifacts to docs/
   └─► Write run_id to memory_manager

8. [If completion protocol enabled]
   └─► Send ACK request to all assigned bots
   └─► Wait up to 120 seconds for ACKs
   └─► Mark as CLOSED once all ACK
       → TIMEOUT: Force close with warning log
```

---

## 10. Potential Response Delivery Issues

### Issue 1: Telegram Reply Text Not Wrapped in Try-Except
**Lines affected:** 1661, 1692, 1704, 1761, 1789, 2557, 2575, 2586, 2637, 2640, etc.

**Fix:** Wrap all `reply_text()` calls:
```python
try:
    await update.message.reply_text(response)
except Exception as e:
    logger.error(f"Failed to send Telegram reply: {e}")
    # Fallback: log to memory, mark run as "response_failed"
```

### Issue 2: Session Manager Doesn't Validate Response
**Line 346:** `return self._extract_response(current, before)` may return empty string or garbage.

**Fix:** Validate response before returning:
```python
if not response or len(response.strip()) < 10:
    logger.warning(f"Suspicious response (empty/too short): {response[:100]}")
    return "⚠️ Claude session returned empty output"
```

### Issue 3: Feedback Phase Not Guaranteed to Complete
**Evidence:** No try-catch around feedback phase in `telegram_relay.py` feedback logic.

**Fix:** Add feedback phase error handler:
```python
try:
    response = await session_manager.send_message(org_id, feedback_prompt)
    await update.message.reply_text(response)
except Exception as e:
    logger.error(f"Feedback phase failed: {e}")
    await update.message.reply_text("❌ Feedback phase error (logged)")
```

### Issue 4: Session Timeout Not Sent to User
**Line 343-346:** Timeout returns via fallback extraction, but no Telegram message sent.

**Fix:** In feedback phase, check response validity:
```python
if response.startswith("❌"):  # Error response from session_manager
    await update.message.reply_text(response)
    logger.warning(f"Session error for {org_id}: {response}")
```

---

## 11. How to Verify a Run Completed But No Response Was Sent

### Check 1: State.json Exists and Shows "completed"
```bash
cat ".ai-org/runs/run-*/state.json" | grep '"status"'
# Expected: "status": "completed"
```

### Check 2: No Telegram Message Sent
```bash
# Telegram bot logs (if available)
grep "reply_text" /path/to/bot.log | grep -i error
# Look for failed API calls
```

### Check 3: Session Response Was Collected
```bash
# Check tmux pane for that session
tmux capture-pane -t <session_name> -p
# Look for partial output, errors, or claude> prompt visible
```

### Check 4: Run Artifacts Exist But Metadata Shows Failure
```bash
ls -la ".ai-org/runs/run-*/docs/"
# If docs/ exists but state.json shows error in feedback phase → response delivery failed
```

---

## 12. Summary: Critical Gaps

| Issue | Severity | Location | Impact |
|-------|----------|----------|--------|
| No try-catch around `reply_text()` | HIGH | telegram_relay.py:1661+ | Silent failures in Telegram delivery |
| Session timeout not validated | HIGH | session_manager.py:343 | Empty response sent to user |
| Feedback phase error handling missing | HIGH | telegram_relay.py:feedback section | Run marked completed but no message sent |
| Completion protocol may not wire to Telegram | MEDIUM | completion.py:__init__ | ACKs sent internally but not to user |
| No response fallback on rate limits/network errors | MEDIUM | All reply_text() calls | User sees no update during network hiccup |
| Run state doesn't track "response_send_failed" | MEDIUM | state.json schema | Can't diagnose why run completed but silent |

---

## 13. Recommended Fixes

### Fix 1: Wrap All Telegram Replies
Create a helper method in `TelegramRelay`:
```python
async def safe_reply(self, update: Update, text: str, **kwargs) -> bool:
    """Send reply with error handling and fallback."""
    try:
        await update.message.reply_text(text, **kwargs)
        return True
    except Exception as e:
        logger.error(f"Telegram reply failed: {e}", extra={"text": text[:100]})
        # Record failure in run state
        await self.memory_manager.add_log(f"TELEGRAM_SEND_FAILED: {e}")
        return False
```

### Fix 2: Validate Session Responses
```python
async def send_message(self, team_id: str, message: str) -> str:
    """..."""
    response = await asyncio.wait_for(...)

    # Validate
    if not response or (not response.startswith("❌") and len(response.strip()) < 5):
        logger.warning(f"Empty response from {team_id}")
        return "⚠️ Claude returned empty output"
    return response
```

### Fix 3: Add Feedback Phase Error Recovery
```python
try:
    response = await self.session_manager.send_message(self.org_id, feedback_prompt)
except asyncio.TimeoutError:
    response = "⏱️ Feedback collection timed out"
except Exception as e:
    response = f"❌ Feedback error: {e}"
finally:
    await self.safe_reply(update, response)
    self._advance_runbook(run_id, "feedback complete")
```

### Fix 4: Track Telegram Delivery in State
Add to state.json schema:
```json
{
  "run_id": "...",
  ...
  "telegram_delivery": {
    "message_sent": true,
    "sent_at": "2026-03-15T14:36:12Z",
    "send_errors": []
  }
}
```

---

## Conclusion

The system is **architecturally sound** but has **critical gaps in error handling** at the Telegram delivery layer. Runs complete successfully with artifacts, but if the final `reply_text()` call fails or times out, the user receives no response and no indication of failure. Run state tracks execution phases but not Telegram delivery status.

**Immediate action:** Add try-catch and fallback mechanisms to all `reply_text()` calls and track delivery success in run state.
