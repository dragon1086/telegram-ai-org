# 실행 흐름 속도 개선 구현 계획

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** telegram-ai-org 메시지 처리 흐름을 ~50% 단축 (첫 ACK <1초, 완료 ~100초)

**Architecture:** (1) BID/폴링 상수 튜닝 → (2) LLM 2회 병렬 호출을 1회 통합 호출로 → (3) 즉시 ACK + 서브태스크 스트리밍 → (4) 세션 예열 풀

**Tech Stack:** Python asyncio, python-telegram-bot, aiosqlite, Claude Code CLI

---

## Task 1: 상수 튜닝 (BID_WAIT + POLL_INTERVAL)

**Files:**
- Modify: `core/telegram_relay.py:1290`
- Modify: `core/task_poller.py:24`

**Step 1: BID_WAIT_SEC 변경**

`core/telegram_relay.py` 1290번 줄:
```python
# Before
BID_WAIT_SEC = 2.5
# After
BID_WAIT_SEC = 0.8
```

**Step 2: DEFAULT_POLL_INTERVAL 변경**

`core/task_poller.py` 24번 줄:
```python
# Before
DEFAULT_POLL_INTERVAL = 10.0
# After
DEFAULT_POLL_INTERVAL = 2.0
```

**Step 3: 테스트 실행**

```bash
.venv/bin/pytest tests/test_task_poller.py -q
```
Expected: 11 passed

**Step 4: 커밋**

```bash
git add core/telegram_relay.py core/task_poller.py
git commit -m "perf: BID_WAIT 2.5s→0.8s, TaskPoller 폴링 10s→2s"
```

---

## Task 2: 통합 LLM 분류 `_llm_unified_classify`

현재 `_classify_lane`(25s) + `_llm_plan_request`(35s)를 asyncio.gather로 병렬 실행 중이나,
두 개의 별도 LLM 호출이 각각 세션을 점유한다.
단일 호출로 합쳐 **1회 LLM 호출**로 lane + route + complexity를 동시에 반환.

**Files:**
- Modify: `core/pm_orchestrator.py` (add `_llm_unified_classify`, `_heuristic_unified_classify`, update `plan_request`)
- Test: `tests/test_pm_orchestrator.py`

**Step 1: 실패 테스트 작성** (`tests/test_pm_orchestrator.py`에 추가)

```python
import pytest
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_unified_classify_returns_lane_and_plan(orchestrator_with_mock_client):
    """_llm_unified_classify가 lane, route, complexity를 단일 호출로 반환"""
    mock_response = '{"lane":"single_org_execution","route":"delegate","complexity":"medium","rationale":"test"}'
    orchestrator_with_mock_client._decision_client.complete = AsyncMock(return_value=mock_response)

    result = await orchestrator_with_mock_client._llm_unified_classify("코드 짜줘", [])
    assert result.lane == "single_org_execution"
    assert result.route == "delegate"
    assert result.complexity == "medium"
    # LLM이 정확히 1번만 호출됐는지 확인
    assert orchestrator_with_mock_client._decision_client.complete.call_count == 1

@pytest.mark.asyncio
async def test_unified_classify_falls_back_on_failure(orchestrator_with_mock_client):
    """LLM 실패 시 heuristic fallback 반환"""
    orchestrator_with_mock_client._decision_client.complete = AsyncMock(side_effect=Exception("timeout"))
    result = await orchestrator_with_mock_client._llm_unified_classify("안녕", [])
    assert result is not None  # heuristic이 None 반환하지 않음
    assert result.route in {"direct_reply", "local_execution", "delegate"}
```

**Step 2: 테스트 실패 확인**

```bash
.venv/bin/pytest tests/test_pm_orchestrator.py::test_unified_classify_returns_lane_and_plan -v
```
Expected: FAILED (AttributeError: `_llm_unified_classify` 없음)

**Step 3: `_llm_unified_classify` 구현** (`core/pm_orchestrator.py`에 추가)

`_classify_lane` 메서드 바로 앞(~223줄)에 삽입:

```python
async def _llm_unified_classify(
    self,
    user_message: str,
    dept_hints: list[str],
    *,
    workdir: str | None = None,
) -> "RequestPlan":
    """lane + route + complexity를 단일 LLM 호출로 처리. 실패 시 heuristic fallback."""
    if self._decision_client is None:
        return self._heuristic_unified_classify(user_message, dept_hints)

    dept_list = ", ".join(dept_hints) if dept_hints else "없음"
    prompt = (
        "Classify the following user request and return JSON only.\n"
        "Fields:\n"
        '  lane: one of [clarify, direct_answer, review_or_audit, attachment_analysis, single_org_execution, multi_org_execution]\n'
        '  route: one of [direct_reply, local_execution, delegate]\n'
        '  complexity: one of [low, medium, high]\n'
        '  rationale: brief Korean explanation (max 30 chars)\n\n'
        f"dept_hints: {dept_list}\n"
        f"User request: {user_message[:800]}\n\n"
        "Return only valid JSON, no markdown."
    )
    try:
        response = await asyncio.wait_for(
            self._decision_client.complete(prompt, workdir=workdir),
            timeout=35.0,
        )
        text = response.strip()
        if "```" in text:
            import re as _re
            m = _re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if m:
                text = m.group(1).strip()
        start, end = text.find("{"), text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]
        data = json.loads(text)

        lane = data.get("lane", "single_org_execution")
        valid_lanes = {"clarify", "direct_answer", "review_or_audit", "attachment_analysis", "single_org_execution", "multi_org_execution"}
        if lane not in valid_lanes:
            lane = "single_org_execution"

        route = data.get("route", "delegate")
        if route not in {"direct_reply", "local_execution", "delegate"}:
            route = "delegate"

        complexity = data.get("complexity", "medium")
        if complexity not in {"low", "medium", "high"}:
            complexity = "medium"

        return RequestPlan(
            lane=lane,
            route=route,
            complexity=complexity,
            rationale=str(data.get("rationale", "")).strip() or "통합 LLM 판단",
            dept_hints=dept_hints,
            confidence=0.8,
        )
    except Exception as e:
        logger.warning(f"[PM] 통합 분류 LLM 실패, heuristic fallback: {e}")
        return self._heuristic_unified_classify(user_message, dept_hints)

def _heuristic_unified_classify(
    self, user_message: str, dept_hints: list[str]
) -> "RequestPlan":
    """통합 heuristic fallback — lane + route + complexity 동시 결정."""
    lane = self._heuristic_lane(user_message, dept_hints)
    plan = self._heuristic_plan_request(user_message, dept_hints, lane=lane)
    plan.lane = lane
    return plan
```

**Step 4: `plan_request` 수정** (기존 asyncio.gather → 단일 호출)

`plan_request` 메서드(~96줄):
```python
async def plan_request(self, user_message: str) -> RequestPlan:
    """유저 요청을 직접 답변/PM 직접 실행/조직 위임 중 어디로 보낼지 결정한다."""
    dept_hints = self._detect_relevant_depts(user_message)
    workdir = self._extract_workdir(user_message)
    result = await self._llm_unified_classify(user_message, dept_hints, workdir=workdir)
    return self._normalize_request_plan(result)
```

**Step 5: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/test_pm_orchestrator.py -q
```
Expected: 기존 테스트 포함 모두 통과

**Step 6: 커밋**

```bash
git add core/pm_orchestrator.py tests/test_pm_orchestrator.py
git commit -m "perf: PMRouter+classify_lane+plan_request → 단일 LLM 통합 분류"
```

---

## Task 3: 즉시 ACK + 스트리밍 결과

**Files:**
- Modify: `core/telegram_relay.py:1140-1156` (`_with_progress_feedback` 교체)

현재 `_with_progress_feedback`는 3초 후 피드백을 보내는 방식.
BID 완료 직후 즉시 ACK 메시지를 전송하고, 처리 완료 시 해당 메시지를 **편집**으로 대체.

**Step 1: 실패 테스트 작성** (`tests/test_pm_routing.py`에 추가)

```python
@pytest.mark.asyncio
async def test_immediate_ack_sent_before_processing(mock_relay):
    """BID 완료 직후 즉시 ACK 메시지가 전송돼야 한다"""
    sent_messages = []
    mock_relay.display.send_reply = AsyncMock(side_effect=lambda msg, text: sent_messages.append(text))

    await mock_relay._handle_with_immediate_ack(mock_update, slow_coro())
    assert sent_messages[0] == "🤔 분석 중..."  # 첫 번째가 즉시 ACK
```

**Step 2: 테스트 실패 확인**

```bash
.venv/bin/pytest tests/test_pm_routing.py::test_immediate_ack_sent_before_processing -v
```
Expected: FAILED

**Step 3: `_with_immediate_ack` 구현** (`core/telegram_relay.py`, `_with_progress_feedback` 다음에 추가)

```python
async def _with_immediate_ack(self, update: Update, coro):
    """
    BID 완료 직후 즉시 '🤔 분석 중...' ACK를 전송하고,
    처리 완료 후 해당 메시지를 삭제한다 (최종 결과는 별도 전송).
    """
    ack_msg = None
    try:
        ack_msg = await self.display.send_reply(update.message, "🤔 분석 중...")
    except Exception:
        pass  # ACK 실패해도 처리는 계속

    try:
        return await coro
    finally:
        if ack_msg is not None:
            try:
                await ack_msg.delete()
            except Exception:
                pass  # 삭제 실패 무시
```

**Step 4: `_with_progress_feedback` 호출부를 `_with_immediate_ack`으로 교체**

`on_message` 및 관련 핸들러에서 `_with_progress_feedback` 호출을 찾아 교체:
```bash
grep -n "_with_progress_feedback" core/telegram_relay.py
```
해당 호출들을 `_with_immediate_ack`으로 교체.

**Step 5: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/ -q --tb=short -x
```

**Step 6: 커밋**

```bash
git add core/telegram_relay.py tests/test_pm_routing.py
git commit -m "perf: 즉시 ACK 패턴 - 분석 중 메시지를 BID 완료 직후 전송"
```

---

## Task 4: Warm Session Pool

**Files:**
- Modify: `core/session_manager.py` (WarmSessionPool 클래스 추가)
- Modify: `core/telegram_relay.py` (봇 시작 시 예열 시작)

**Step 1: 현재 세션 생성 방식 파악**

```bash
grep -n "create_session\|get_or_create\|start_session" core/session_manager.py | head -20
```

**Step 2: `WarmSessionPool` 클래스 추가** (`core/session_manager.py` 끝에 추가)

```python
class WarmSessionPool:
    """
    세션 1개를 항상 예열 상태로 유지.
    get() 호출 시 즉시 반환 후 백그라운드에서 다음 세션 예열.
    """
    def __init__(self, session_manager: "SessionManager", org_id: str):
        self._sm = session_manager
        self._org_id = org_id
        self._warm: str | None = None   # session_id
        self._preheating = False

    async def start(self) -> None:
        """봇 시작 시 호출 — 백그라운드 예열 시작."""
        asyncio.create_task(self._preheat())

    async def get_warm_session(self) -> str | None:
        """
        예열된 세션 ID 반환. 없으면 None (caller가 cold-start).
        반환 후 즉시 다음 예열 시작.
        """
        if self._warm:
            session_id = self._warm
            self._warm = None
            asyncio.create_task(self._preheat())
            return session_id
        return None

    async def _preheat(self) -> None:
        if self._preheating:
            return
        self._preheating = True
        try:
            # 새 세션 시작 (no-op 초기화)
            session_id = await self._sm.ensure_session(self._org_id)
            self._warm = session_id
            logger.debug(f"[WarmPool] 세션 예열 완료: {session_id[:8]}")
        except Exception as e:
            logger.warning(f"[WarmPool] 예열 실패: {e}")
        finally:
            self._preheating = False
```

**Step 3: 테스트 작성**

```python
@pytest.mark.asyncio
async def test_warm_pool_returns_preheated_session():
    mock_sm = AsyncMock()
    mock_sm.ensure_session = AsyncMock(return_value="warm-session-id")
    pool = WarmSessionPool(mock_sm, "test_org")
    await pool._preheat()

    session = await pool.get_warm_session()
    assert session == "warm-session-id"
    # 반환 후 _warm이 None이 되어 다음 get은 None
    assert pool._warm is None
```

**Step 4: 테스트 통과 확인**

```bash
.venv/bin/pytest tests/ -q -k "warm_pool"
```

**Step 5: telegram_relay.py에서 봇 시작 시 예열 등록**

`start()` 또는 `post_init()` 메서드 내:
```python
# WarmSessionPool 초기화 및 예열 시작
if hasattr(self, 'session_manager') and self.session_manager:
    self._warm_pool = WarmSessionPool(self.session_manager, self.org_id)
    asyncio.create_task(self._warm_pool.start())
```

**Step 6: 커밋**

```bash
git add core/session_manager.py core/telegram_relay.py
git commit -m "perf: WarmSessionPool — 세션 예열로 cold start 제거"
```

---

## Task 5: 전체 테스트 + push

**Step 1: 전체 테스트 실행**

```bash
.venv/bin/pytest tests/ -q --tb=short
```
Expected: 475+ passed, 기존 11개 pre-existing fail만 남음

**Step 2: main push**

```bash
git push origin main
```

**Step 3: architecture-deep-analysis.md 업데이트**

`docs/architecture-deep-analysis.md` 섹션 5에 이번 개선 항목 추가:
- 5.5 LLM 호출 체인 통합 (plan_request → _llm_unified_classify) ✅
- 즉시 ACK + 스트리밍 패턴 ✅
- BID_WAIT / TaskPoller 상수 튜닝 ✅
- WarmSessionPool ✅

---

## 예상 성능 개선

| 개선 | 절약 |
|------|------|
| Task 1: 상수 튜닝 | BID 1.7초 + Poll 평균 4초 = **5.7초** |
| Task 2: LLM 통합 | LLM 1회 제거 = **~25초** |
| Task 3: 즉시 ACK | 체감 첫 응답 **~60초** 단축 |
| Task 4: Warm Pool | cold start **5~15초** 제거 |
| **합계** | **체감 ~90초, 실제 ~35초 단축** |
