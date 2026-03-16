# 실행 흐름 속도 개선 설계

> 작성일: 2026-03-17
> 목표: 전체 처리 체감 속도 50%+ 단축

---

## 배경 및 목표

현재 메시지 처리 흐름의 end-to-end 지연은 ~2~4분. 주요 병목:

| 구간 | 현재 | 원인 |
|------|------|------|
| BID 대기 | 2.5초 | 고정 대기 |
| PMRouter LLM | ~25초 | 별도 LLM 호출 |
| classify_lane + plan | ~35초 | (이미 병렬화) |
| decompose | ~35초 | 별도 LLM 호출 |
| TaskPoller 폴링 | 평균 5초 | 10초 간격 |
| ResultSynthesizer | ~25초 | 전체 완료 후 실행 |
| 세션 cold start | ~5~15초 | 매 실행마다 초기화 |

**목표:** 첫 ACK < 1초, 완료까지 ~100초 (현재 ~180~240초 대비 50%+ 단축)

---

## 아키텍처 개요

```
[현재]
메시지 → BID(2.5s) → PMRouter LLM(25s) → classify+plan(35s) → decompose(35s)
       → Poll(5s) → Bot실행(60s) → Synthesize(25s) ≈ 3분

[개선]
메시지 → BID(0.8s) → 즉시 ACK("분석 중...") → 통합 LLM 1회(35s) → decompose(35s)
       → Poll(2s) → Bot실행(60s) → 부분결과 스트리밍 ≈ 100초
```

---

## 변경 1: 통합 LLM 분류 (US-SPD-001)

**파일:** `core/pm_orchestrator.py`, `core/pm_router.py`

PMRouter + `_classify_lane` + `_llm_plan_request` 3개의 순차 LLM 호출을 단일 `_llm_unified_classify` 호출로 통합.

```python
async def _llm_unified_classify(
    self, user_message: str, dept_hints: list[str], workdir: str | None = None
) -> UnifiedClassification:
    """
    PMRouter + classify_lane + plan_request를 단일 LLM 호출로 처리.
    반환: intent, lane, route, complexity, dept_hints, rationale
    """
    prompt = build_unified_classify_prompt(user_message, dept_hints)
    response = await self._decision_client.complete(prompt, workdir=workdir)
    return parse_unified_classification(response, dept_hints)
    # 실패 시 → _heuristic_unified_classify() fallback
```

**예상 절약:** ~50초 (LLM 2회 제거)

**fallback:** `_heuristic_unified_classify()` — 기존 `_heuristic_lane` + `_heuristic_plan_request` 결합

---

## 변경 2: 즉시 ACK + 스트리밍 결과 (US-SPD-002)

**파일:** `core/telegram_relay.py`

메시지 수신 즉시 ACK 전송 후, 서브태스크 완료 시마다 메시지 편집.

```python
async def on_message(self, message):
    # 즉시 ACK (BID 완료 후 ~1초 이내)
    ack_msg = await bot.send_message(chat_id, "🤔 분석 중...")

    # 비동기 파이프라인 실행 (ACK 블로킹 없음)
    asyncio.create_task(
        self._process_and_stream(message, ack_msg.message_id)
    )

async def _process_and_stream(self, message, ack_msg_id):
    # 서브태스크 완료 콜백 등록
    async def on_subtask_done(subtask_result):
        await bot.edit_message_text(
            chat_id=...,
            message_id=ack_msg_id,
            text=self._build_partial_result(completed_results)
        )

    await self._full_pipeline(message, on_subtask_done=on_subtask_done)
```

**예상 절약:** 체감 응답 ~60초 단축 (즉각 피드백)

---

## 변경 3: 상수 튜닝 (US-SPD-003)

**파일:** `core/telegram_relay.py`, `core/task_poller.py`

```python
# telegram_relay.py
BID_WAIT_SEC = 0.8   # 기존 2.5 → 1.7초 절약

# task_poller.py
POLL_INTERVAL = 2    # 기존 10 → 평균 대기 5초 → 1초로 단축
```

**주의:** BID_WAIT_SEC을 너무 낮추면 여러 PM봇 간 race condition 가능. 0.8초는 네트워크 지연 고려한 최소치.

---

## 변경 4: Warm Session Pool (US-SPD-004)

**파일:** `core/session_manager.py` (신규 또는 기존 확장)

```python
class WarmSessionPool:
    """
    세션 1개를 항상 예열 상태로 유지.
    get() 호출 시 즉시 반환 + 백그라운드에서 다음 세션 예열.
    """
    def __init__(self, session_manager: SessionManager):
        self._sm = session_manager
        self._warm: Session | None = None
        self._preheating = False

    async def start(self):
        """봇 시작 시 백그라운드 예열 시작"""
        asyncio.create_task(self._preheat())

    async def get(self) -> Session:
        if self._warm:
            session = self._warm
            self._warm = None
            asyncio.create_task(self._preheat())  # 다음 예열
            return session
        return await self._sm.create_session()    # cold fallback

    async def _preheat(self):
        if self._preheating:
            return
        self._preheating = True
        try:
            self._warm = await self._sm.create_session()
        finally:
            self._preheating = False
```

**예상 절약:** cold start 5~15초 제거

---

## 구현 우선순위

| 순서 | Story | 난이도 | 예상 절약 |
|------|-------|--------|---------|
| 1 | US-SPD-003: 상수 튜닝 | 낮음 | ~7초 |
| 2 | US-SPD-001: 통합 LLM | 중간 | ~50초 |
| 3 | US-SPD-002: 즉시 ACK + 스트리밍 | 높음 | 체감 ~60초 |
| 4 | US-SPD-004: Warm Session Pool | 중간 | ~10초 |

---

## 테스트 전략

- `test_pm_orchestrator.py`: `_llm_unified_classify` mock 테스트
- `test_pm_routing.py`: 통합 분류 결과 라우팅 검증
- `test_task_poller.py`: 2초 폴링 간격 동작 확인
- 수동: 실제 Telegram에서 ACK 시간 측정
