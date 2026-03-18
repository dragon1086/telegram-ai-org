"""LLM 비용 추적기 및 Circuit Breaker — PM DecisionClient 호출 래퍼."""
from __future__ import annotations

import asyncio
import os
import time
from collections import deque
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from core.pm_decision import DecisionClientProtocol

PM_HOURLY_CALL_LIMIT = int(os.environ.get("PM_HOURLY_CALL_LIMIT", "100"))
DAILY_COST_LIMIT_USD = float(os.environ.get("DAILY_COST_LIMIT_USD", "50.0"))
# 토큰당 비용 추정 (claude-3-sonnet 기준, $/1K tokens)
COST_PER_1K_TOKENS_USD = float(os.environ.get("COST_PER_1K_TOKENS_USD", "0.003"))
CIRCUIT_BREAKER_ERROR_THRESHOLD = int(os.environ.get("CIRCUIT_BREAKER_ERROR_THRESHOLD", "3"))
CIRCUIT_BREAKER_RESET_SEC = float(os.environ.get("CIRCUIT_BREAKER_RESET_SEC", "600"))


class LLMCostTracker:
    """PM LLM 호출을 래핑하여 호출 수·추정 비용을 추적한다.

    - 시간당 PM_HOURLY_CALL_LIMIT 초과 시: heuristic fallback + Telegram 알림
    - 일일 DAILY_COST_LIMIT_USD 초과 시: 신규 태스크 수락 중단 + Telegram 알림
    - 연속 에러 CIRCUIT_BREAKER_ERROR_THRESHOLD 회: circuit breaker open
    - CIRCUIT_BREAKER_RESET_SEC 후 half-open 자동 시도
    """

    def __init__(
        self,
        wrapped: "DecisionClientProtocol",
        send_func=None,
        chat_id: int | None = None,
    ) -> None:
        self._wrapped = wrapped
        self._send = send_func
        self._chat_id = chat_id
        # 시간당 호출 추적: timestamp deque
        self._call_timestamps: deque[float] = deque()
        # 일일 누적 비용 (USD)
        self._daily_cost_usd: float = 0.0
        self._daily_reset_ts: float = time.time()
        # 총 호출 수
        self._total_calls: int = 0
        # Circuit breaker 상태
        self._consecutive_errors: int = 0
        self._circuit_open: bool = False
        self._circuit_open_at: float = 0.0
        self._fallback_active: bool = False

    @property
    def total_calls(self) -> int:
        return self._total_calls

    @property
    def daily_cost_usd(self) -> float:
        return self._daily_cost_usd

    @property
    def hourly_calls(self) -> int:
        """현재 1시간 rolling window 내 호출 수."""
        self._prune_old_timestamps()
        return len(self._call_timestamps)

    @property
    def circuit_open(self) -> bool:
        return self._circuit_open

    @property
    def daily_limit_reached(self) -> bool:
        self._reset_daily_if_needed()
        return self._daily_cost_usd >= DAILY_COST_LIMIT_USD

    def _prune_old_timestamps(self) -> None:
        cutoff = time.time() - 3600.0
        while self._call_timestamps and self._call_timestamps[0] < cutoff:
            self._call_timestamps.popleft()

    def _reset_daily_if_needed(self) -> None:
        now = time.time()
        if now - self._daily_reset_ts >= 86400.0:
            self._daily_cost_usd = 0.0
            self._daily_reset_ts = now
            logger.info("[LLMCostTracker] 일일 비용 카운터 리셋")

    def _estimate_cost(self, prompt: str, response: str) -> float:
        tokens = (len(prompt) + len(response)) / 4  # rough estimate: 1 token ≈ 4 chars
        return (tokens / 1000.0) * COST_PER_1K_TOKENS_USD

    async def _notify(self, message: str) -> None:
        if self._send and self._chat_id:
            try:
                await self._send(self._chat_id, f"⚡ [비용 경고] {message}")
            except Exception as e:
                logger.debug(f"[LLMCostTracker] 알림 전송 실패: {e}")

    def _check_circuit_breaker(self) -> bool:
        """True이면 circuit open (차단), False이면 정상."""
        if not self._circuit_open:
            return False
        # Half-open: reset_sec 이후 재시도 허용
        if time.time() - self._circuit_open_at >= CIRCUIT_BREAKER_RESET_SEC:
            logger.info("[LLMCostTracker] Circuit breaker half-open — 재시도 허용")
            self._circuit_open = False
            self._consecutive_errors = 0
            return False
        return True

    async def complete(
        self,
        prompt: str,
        *,
        system_prompt: str = "",
        workdir: str | None = None,
    ) -> str:
        self._reset_daily_if_needed()

        # Circuit breaker check
        if self._check_circuit_breaker():
            logger.warning("[LLMCostTracker] Circuit breaker OPEN — heuristic fallback")
            raise RuntimeError("[LLMCostTracker] Circuit breaker open — LLM 호출 차단됨")

        # 시간당 호출 상한 체크
        self._prune_old_timestamps()
        if len(self._call_timestamps) >= PM_HOURLY_CALL_LIMIT and not self._fallback_active:
            self._fallback_active = True
            logger.warning(
                f"[LLMCostTracker] 시간당 호출 상한 도달 ({PM_HOURLY_CALL_LIMIT}회) — fallback 모드"
            )
            asyncio.create_task(
                self._notify(f"PM 시간당 호출 상한({PM_HOURLY_CALL_LIMIT}회) 도달. Fallback 모드 전환.")
            )

        # 일일 비용 상한 체크
        if self._daily_cost_usd >= DAILY_COST_LIMIT_USD:
            logger.warning(
                f"[LLMCostTracker] 일일 비용 상한 도달 (${self._daily_cost_usd:.2f}/{DAILY_COST_LIMIT_USD}) — 호출 차단"
            )
            asyncio.create_task(
                self._notify(f"일일 비용 상한(${DAILY_COST_LIMIT_USD}) 도달. 신규 태스크 수락 중단.")
            )
            raise RuntimeError("[LLMCostTracker] 일일 비용 상한 도달")

        # 실제 LLM 호출
        try:
            response = await self._wrapped.complete(
                prompt, system_prompt=system_prompt, workdir=workdir,
            )
            # 성공 기록
            self._consecutive_errors = 0
            if self._circuit_open:
                self._circuit_open = False
                logger.info("[LLMCostTracker] Circuit breaker 복구됨")
            if self._fallback_active and len(self._call_timestamps) < PM_HOURLY_CALL_LIMIT:
                self._fallback_active = False
                logger.info("[LLMCostTracker] Fallback 모드 해제")
        except Exception as e:
            self._consecutive_errors += 1
            logger.warning(f"[LLMCostTracker] LLM 오류 (연속 {self._consecutive_errors}회): {e}")
            if self._consecutive_errors >= CIRCUIT_BREAKER_ERROR_THRESHOLD:
                self._circuit_open = True
                self._circuit_open_at = time.time()
                logger.error(
                    f"[LLMCostTracker] Circuit breaker OPEN "
                    f"(연속 {self._consecutive_errors}회 오류)"
                )
                asyncio.create_task(
                    self._notify(
                        f"LLM 연속 {self._consecutive_errors}회 오류. "
                        f"Circuit breaker 가동. {CIRCUIT_BREAKER_RESET_SEC//60:.0f}분 후 자동 재시도."
                    )
                )
            raise

        # 호출 기록
        now = time.time()
        self._call_timestamps.append(now)
        self._total_calls += 1
        cost = self._estimate_cost(prompt, response)
        self._daily_cost_usd += cost
        logger.debug(
            f"[LLMCostTracker] 호출 #{self._total_calls} | "
            f"시간당 {len(self._call_timestamps)}회 | "
            f"일일 ${self._daily_cost_usd:.4f} | 이번 ${cost:.4f}"
        )
        return response

    def stats(self) -> dict:
        """현재 통계 반환 (dashboard용)."""
        self._prune_old_timestamps()
        self._reset_daily_if_needed()
        return {
            "total_calls": self._total_calls,
            "hourly_calls": len(self._call_timestamps),
            "hourly_limit": PM_HOURLY_CALL_LIMIT,
            "daily_cost_usd": round(self._daily_cost_usd, 4),
            "daily_limit_usd": DAILY_COST_LIMIT_USD,
            "circuit_open": self._circuit_open,
            "fallback_active": self._fallback_active,
            "consecutive_errors": self._consecutive_errors,
        }
