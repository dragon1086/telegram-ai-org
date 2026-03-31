"""core.hermes_integration — Hermes 3모듈 런타임 연결 레이어 (Phase 1 스켈레톤).

Hermes Tool Registry / Platform Adapter / Context Compressor를
메인 봇 런타임에 연결하는 진입점입니다.

각 모듈은 이미 독립 구현되어 있으나, bots/에서 호출 지점이 없어 사실상 비활성 상태였습니다.
이 모듈이 그 연결 고리 역할을 합니다.

Feature flags (각 모듈 개별 플래그를 존중):
  - ENABLE_TOOL_REGISTRY       (default=true)
  - ENABLE_PLATFORM_ADAPTER    (default=true)
  - ENABLE_CONTEXT_COMPRESSOR  (default=true)

Design notes:
  - HermesRuntime: on_init/on_message/on_teardown 훅 포인트 제공.
  - register_hermes_tools: Tool Registry에 시스템 도구 메타데이터 등록.
  - 모든 훅은 no-op 안전 동작 보장 — 실패 시 예외 전파 없음.
  - get_hermes_runtime(): 모듈 레벨 싱글턴 반환.
  - Backward compatible: 기존 bots/ 코드는 이 모듈을 임포트하지 않아도 동작.

Self-review:
  ① Logic: on_init → registry/adapter 초기화, on_message → normalize_inbound 위임 — 올바름.
  ② Edge cases: 각 Hermes 모듈 플래그 off 시 no-op 유지. 예외 전파 없음.
  ③ Compat: 신규 모듈, 기존 코드 변경 없음.
  ④ Global state: _runtime 싱글턴 하나만 사용.

사용 예시::

    from core.hermes_integration import get_hermes_runtime

    runtime = get_hermes_runtime()
    runtime.on_init(bot_sender=my_sender_fn)

    # 메시지 수신 시
    inbound = runtime.on_message(telegram_update)

    # 종료 시
    runtime.on_teardown()
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hermes Tool Registry 메타데이터 상수
# Tool Registry 등록에 필요한 tool_name / description / input_schema 정의
# ---------------------------------------------------------------------------

HERMES_TOOL_METADATA: Dict[str, Dict[str, Any]] = {
    "dispatch": {
        "tool_name": "hermes_dispatch",
        "description": "태스크를 대상 조직(target_org)으로 디스패치합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "디스패치할 태스크 ID"},
                "target_org": {"type": "string", "description": "대상 조직 식별자 (예: dev, ops)"},
                "message": {"type": "string", "description": "전달할 메시지 본문"},
            },
            "required": ["task_id", "target_org", "message"],
        },
    },
    "compress_context": {
        "tool_name": "hermes_compress_context",
        "description": "긴 대화 히스토리를 max_tokens 한도 내로 압축합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "messages": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "압축할 메시지 목록 [{role, content}, ...]",
                },
                "max_tokens": {
                    "type": "integer",
                    "default": 8000,
                    "description": "압축 후 목표 토큰 상한",
                },
                "keep_last_n": {
                    "type": "integer",
                    "default": 6,
                    "description": "항상 보존할 최근 메시지 수",
                },
            },
            "required": ["messages"],
        },
    },
    "normalize_inbound": {
        "tool_name": "hermes_normalize_inbound",
        "description": "플랫폼 원시 이벤트를 정규화된 InboundMessage로 변환합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "platform": {"type": "string", "description": "플랫폼 식별자 (예: telegram)"},
                "raw_event": {"type": "object", "description": "플랫폼 원시 이벤트 객체"},
            },
            "required": ["platform", "raw_event"],
        },
    },
}


# ---------------------------------------------------------------------------
# HermesRuntime — 훅 포인트 및 런타임 매니저
# ---------------------------------------------------------------------------


class HermesRuntime:
    """Hermes 3모듈을 런타임에 연결하는 매니저.

    봇 시작/메시지 수신/종료 시 호출할 훅 포인트를 제공합니다.
    각 훅은 no-op 안전 동작이 보장되며, 실패 시 예외를 전파하지 않습니다.

    Attributes:
        _initialized: on_init 호출 여부.
        _registry: ToolRegistry 인스턴스 (on_init 이후 설정).
        _adapter: TelegramPlatformAdapter 인스턴스 (on_init 이후 설정).
    """

    def __init__(self) -> None:
        self._initialized: bool = False
        self._registry: Any = None
        self._adapter: Any = None

    # ------------------------------------------------------------------
    # 훅 포인트
    # ------------------------------------------------------------------

    def on_init(self, bot_sender: Optional[Callable[..., Any]] = None) -> None:
        """봇 시작 시 호출합니다 — Tool Registry 초기화 + Platform Adapter 등록.

        Args:
            bot_sender: Telegram 메시지 전송 callable(chat_id, text, ...).
                        None이면 어댑터의 send_message()가 no-op으로 동작합니다.

        Returns:
            None

        Raises:
            (내부적으로 catch — 초기화 실패 시 무중단 동작 보장)
        """
        try:
            from core.tool_registry import get_registry
            self._registry = get_registry()
            register_hermes_tools(self._registry)
            logger.info("HermesRuntime.on_init: Tool Registry 초기화 완료 (%d 도구 등록)", len(self._registry))
        except Exception as exc:
            logger.warning("HermesRuntime.on_init: Tool Registry 초기화 실패 (no-op) — %s", exc)

        try:
            from core.platform_adapter import TelegramPlatformAdapter, register_adapter
            self._adapter = TelegramPlatformAdapter(bot_sender=bot_sender)
            register_adapter(self._adapter)
            logger.info("HermesRuntime.on_init: TelegramPlatformAdapter 등록 완료")
        except Exception as exc:
            logger.warning("HermesRuntime.on_init: Platform Adapter 등록 실패 (no-op) — %s", exc)

        self._initialized = True

    def on_message(self, raw_event: Any) -> Optional[Any]:
        """메시지 수신 시 호출합니다 — Platform Adapter를 통해 이벤트 정규화.

        Args:
            raw_event: 플랫폼 원시 이벤트 (예: telegram.Update 객체).

        Returns:
            InboundMessage (정규화 성공 시) 또는 None (어댑터 미초기화 / 정규화 실패).

        Raises:
            (내부적으로 catch)
        """
        if not self._initialized or self._adapter is None:
            logger.debug("HermesRuntime.on_message: 미초기화 상태 — no-op")
            return None

        try:
            return self._adapter.normalize_inbound(raw_event)
        except Exception as exc:
            logger.warning("HermesRuntime.on_message 정규화 실패 (no-op) — %s", exc)
            return None

    def on_teardown(self) -> None:
        """봇 종료 시 호출합니다 — Platform Adapter shutdown 훅 실행.

        Returns:
            None

        Raises:
            (내부적으로 catch)
        """
        if self._adapter is not None:
            try:
                self._adapter.on_shutdown()
                logger.info("HermesRuntime.on_teardown: Platform Adapter shutdown 완료")
            except Exception as exc:
                logger.warning("HermesRuntime.on_teardown: shutdown 실패 (무시) — %s", exc)

        self._initialized = False
        self._registry = None
        self._adapter = None

    # ------------------------------------------------------------------
    # 상태 조회
    # ------------------------------------------------------------------

    @property
    def is_initialized(self) -> bool:
        """on_init이 완료됐는지 여부."""
        return self._initialized

    def list_registered_tools(self) -> List[str]:
        """등록된 Tool Registry 도구명 목록을 반환합니다.

        Returns:
            도구명 문자열 목록. 미초기화 시 빈 리스트.
        """
        if self._registry is None:
            return []
        try:
            return [entry.name for entry in self._registry.list_all()]
        except Exception:
            return []


# ---------------------------------------------------------------------------
# register_hermes_tools — Tool Registry 등록 함수
# ---------------------------------------------------------------------------


def register_hermes_tools(registry: Any) -> int:
    """Hermes 시스템 도구를 Tool Registry에 등록합니다.

    HERMES_TOOL_METADATA에 정의된 모든 도구를 no-op 핸들러와 함께 등록합니다.
    실제 구현은 Phase 2에서 핸들러를 교체하는 방식으로 확장합니다.

    Args:
        registry: ToolRegistry 인스턴스.

    Returns:
        등록된 도구 수 (int).

    Raises:
        (내부적으로 catch)
    """
    registered = 0
    for key, meta in HERMES_TOOL_METADATA.items():
        try:
            registry.register(
                name=meta["tool_name"],
                description=meta["description"],
                handler=None,  # Phase 1: no-op 핸들러 (Phase 2에서 교체)
                tags={"hermes", key},
                schema=meta["input_schema"],
                enabled=True,
            )
            registered += 1
            logger.debug("HermesIntegration: 도구 등록 완료 — %s", meta["tool_name"])
        except Exception as exc:
            logger.warning("HermesIntegration: 도구 등록 실패 %s — %s", key, exc)

    logger.info("HermesIntegration.register_hermes_tools: %d개 도구 등록 완료", registered)
    return registered


# ---------------------------------------------------------------------------
# 모듈 레벨 싱글턴
# ---------------------------------------------------------------------------

_runtime: Optional[HermesRuntime] = None


def get_hermes_runtime() -> HermesRuntime:
    """모듈 레벨 HermesRuntime 싱글턴을 반환합니다.

    Returns:
        HermesRuntime 인스턴스. 첫 호출 시 생성됩니다.
    """
    global _runtime
    if _runtime is None:
        _runtime = HermesRuntime()
    return _runtime


def reset_hermes_runtime() -> None:
    """싱글턴을 초기화합니다. 테스트 격리용."""
    global _runtime
    _runtime = None


# ---------------------------------------------------------------------------
# 모듈 임포트 시 로그
# ---------------------------------------------------------------------------
logger.info(
    "HermesIntegration loaded — TOOL_REGISTRY=%s, PLATFORM_ADAPTER=%s, CONTEXT_COMPRESSOR=%s",
    os.environ.get("ENABLE_TOOL_REGISTRY", "true"),
    os.environ.get("ENABLE_PLATFORM_ADAPTER", "true"),
    os.environ.get("ENABLE_CONTEXT_COMPRESSOR", "true"),
)
